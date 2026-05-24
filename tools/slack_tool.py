"""Slack integration for the human-in-the-loop approval gate.

The orchestrator posts an interactive message to a Slack channel when a
sensitive case needs a human decision, then `await`s an asyncio.Future
which is resolved when Slack POSTs back to /api/slack/interactivity.

Security: Slack's signing-secret-HMAC is verified on every interactivity
callback to prevent forged approvals from public callers.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from config import settings


SLACK_API = "https://slack.com/api"


@dataclass
class ApprovalDecision:
    status: str = "timeout"          # "approved" | "rejected" | "timeout"
    user_name: str = ""
    user_id: str = ""
    reason: str = ""
    decided_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "user_name": self.user_name,
            "user_id": self.user_id,
            "reason": self.reason,
            "decided_at": self.decided_at,
        }


class SlackTool:
    """Thin wrapper around chat.postMessage + chat.update + signature verify."""

    def __init__(self) -> None:
        self.bot_token = settings.slack_bot_token
        self.signing_secret = settings.slack_signing_secret
        self.approval_channel = settings.slack_approval_channel_id

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.signing_secret and self.approval_channel)

    # ----------- posting -----------

    async def post_approval(
        self,
        approval_id: str,
        case: dict,
        triage: dict | None = None,
    ) -> dict:
        """Post an Approve/Reject interactive message to the approval channel.

        Returns the Slack API response (contains `ts` + `channel`) so the
        orchestrator can later update the same message with the decision.
        """
        triage = triage or {}
        case_number = case.get("CaseNumber", "?")
        subject = case.get("Subject", "")
        description = (case.get("Description") or "")[:600]
        account = (case.get("Account") or {}).get("Name") or case.get("AccountId") or "(no account)"
        priority = case.get("Priority", "?")
        intent = triage.get("intent", "?")
        risk = triage.get("risk", "?")
        urgency = triage.get("urgency", "?")

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Approval needed · Case {case_number}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Subject:* {subject}\n"
                        f"*Account:* {account}  ·  *Priority:* {priority}\n"
                        f"*Triage:* intent=`{intent}` · risk=`{risk}` · urgency=`{urgency}`"
                    ),
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Customer message:*\n```{description}```"},
            },
            {"type": "divider"},
            {
                "type": "actions",
                "block_id": f"approval_{approval_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve · auto-process"},
                        "style": "primary",
                        "action_id": "approve",
                        "value": json.dumps({"approval_id": approval_id, "decision": "approved"}),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject · escalate"},
                        "style": "danger",
                        "action_id": "reject",
                        "value": json.dumps({"approval_id": approval_id, "decision": "rejected"}),
                    },
                ],
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f":hourglass: Times out in {settings.slack_approval_timeout_seconds // 60} min · Case Triage Agent"}
                ],
            },
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SLACK_API}/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={
                    "channel": self.approval_channel,
                    "blocks": blocks,
                    "text": f"Approval needed for Case {case_number}: {subject}",
                },
            )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack chat.postMessage failed: {data.get('error')}")
        return data

    async def update_with_decision(
        self,
        channel: str,
        ts: str,
        case_number: str,
        decision: ApprovalDecision,
    ) -> None:
        """Replace the buttons with a final status line so they can't be clicked again."""
        emoji = {"approved": ":white_check_mark:", "rejected": ":x:", "timeout": ":hourglass_flowing_sand:"}.get(decision.status, "")
        by_clause = f" by <@{decision.user_id}>" if decision.user_id else ""
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(decision.decided_at))

        status_text = {
            "approved": f"{emoji} *Approved*{by_clause} at {when}. Agent is now processing Case {case_number}.",
            "rejected": f"{emoji} *Rejected*{by_clause} at {when}. Case {case_number} was escalated to a human queue.",
            "timeout": f"{emoji} *Timed out* — no decision within {settings.slack_approval_timeout_seconds // 60} min. Case {case_number} was escalated.",
        }.get(decision.status, "Decision recorded.")

        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": status_text}}
        ]
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{SLACK_API}/chat.update",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={"channel": channel, "ts": ts, "blocks": blocks, "text": status_text},
            )

    # ----------- inbound -----------

    def verify_signature(self, timestamp: str, signature: str, raw_body: bytes) -> bool:
        """Verify a Slack interactivity HMAC. Mandatory — the callback is public."""
        if not (timestamp and signature and self.signing_secret):
            return False
        try:
            # Reject requests older than 5 minutes (replay protection).
            if abs(time.time() - int(timestamp)) > 300:
                return False
        except ValueError:
            return False
        sig_basestring = b"v0:" + timestamp.encode() + b":" + raw_body
        my_sig = "v0=" + hmac.new(
            self.signing_secret.encode(), sig_basestring, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(my_sig, signature)

    @staticmethod
    def parse_interaction(payload_str: str) -> dict | None:
        try:
            return json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            return None
