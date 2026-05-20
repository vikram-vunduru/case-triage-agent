"""Orchestrator. Runs the multi-agent pipeline end-to-end and emits SSE events
that drive the live architecture UI.

The orchestrator itself is deterministic Python — it routes between specialized
LLM-powered sub-agents (triage, investigator, resolver, critic, action,
escalation) and applies guardrails + a trust gate between stages.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic

from agents.action import ActionAgent
from agents.base import EventEmitter
from agents.critic import CriticAgent
from agents.escalation import EscalationAgent
from agents.investigator import InvestigatorAgent
from agents.resolver import ResolverAgent
from agents.triage import TriageAgent
from config import settings
from evals.golden import for_case
from evals.scoring import (
    EvalScore,
    score_escalation_decision,
    score_groundedness,
    score_latency,
    score_retrieval_recall,
    score_safety,
    score_tool_correctness,
)
from guardrails.input_guardrails import redact_pii, run_input_guardrails
from guardrails.output_guardrails import run_output_guardrails
from guardrails.policy import trust_gate
from tools.confluence_tool import ConfluenceTool
from tools.salesforce_tool import SalesforceTool


@dataclass
class PipelineState:
    case_id: str
    triage: dict | None = None
    case: dict | None = None
    account: dict | None = None
    related_cases: list[dict] = field(default_factory=list)
    kb_hits: list[dict] = field(default_factory=list)
    draft: dict | None = None
    critic_scores: dict | None = None
    tool_calls: list[dict] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    escalated: bool = False
    confidence: float | None = None
    input_guardrails: list[dict] = field(default_factory=list)
    output_guardrails: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    final_resolution: str = ""


class Orchestrator:
    def __init__(
        self,
        anthropic_client: Anthropic,
        sf: SalesforceTool,
        kb: ConfluenceTool,
    ) -> None:
        self.client = anthropic_client
        self.sf = sf
        self.kb = kb

        self.triage_agent = TriageAgent(self.client)
        self.investigator_agent = InvestigatorAgent(self.client, sf, kb)
        self.resolver_agent = ResolverAgent(self.client)
        self.critic_agent = CriticAgent(self.client)
        self.action_agent = ActionAgent(self.client, sf)
        self.escalation_agent = EscalationAgent(self.client, sf)

    async def run(self, case_id: str, emit: EventEmitter) -> PipelineState:
        t0 = time.time()
        state = PipelineState(case_id=case_id)

        await emit(
            "session_start",
            {
                "case_id": case_id,
                "model": settings.anthropic_model,
                "mode": {"salesforce": self.sf.mode, "confluence": self.kb.mode},
                "pipeline": [
                    "input_guardrails", "orchestrator", "triage", "investigator",
                    "resolver", "output_guardrails", "critic", "trust_gate",
                    "action", "escalation", "output",
                ],
            },
        )

        # -------- Stage 0: read case ahead of guardrails to derive user text
        try:
            initial_case = self.sf.get_case(case_id)
        except Exception as exc:  # noqa: BLE001
            await emit("error", {"stage": "input", "message": f"Case not found: {exc}"})
            return state
        raw_text = f"{initial_case.get('Subject', '')}\n\n{initial_case.get('Description', '')}"

        # -------- Stage 1: input guardrails
        await emit("stage_enter", {"node": "input_guardrails", "label": "Input guardrails"})
        ig = run_input_guardrails(raw_text)
        state.input_guardrails = [c.to_dict() for c in ig]
        for c in ig:
            await emit("guardrail_check", {"phase": "input", **c.to_dict()})
        ig_fail = any(c.status == "fail" for c in ig)
        await emit(
            "stage_exit",
            {
                "node": "input_guardrails",
                "status": "error" if ig_fail else ("warn" if any(c.status == "warn" for c in ig) else "ok"),
                "summary": f"{sum(c.status == 'pass' for c in ig)}/{len(ig)} clean",
            },
        )

        await emit("stage_enter", {"node": "orchestrator", "label": "Plan & route"})
        await emit("stage_exit", {"node": "orchestrator", "status": "ok", "summary": "pipeline planned"})

        if ig_fail:
            await self._escalate(
                state=state,
                emit=emit,
                reason="input_guardrails_failed",
                summary=f"Input guardrail blocked: {[c.name for c in ig if c.status == 'fail']}",
            )
            return await self._finish(state, emit, t0)

        # PII-redact the case text we'll feed into the resolver later.
        redacted_subject = redact_pii(initial_case.get("Subject", ""))
        redacted_description = redact_pii(initial_case.get("Description", ""))

        # -------- Stage 2: triage
        triage_msg = (
            f"Case {case_id} - classify it.\n\n"
            f"Subject: {redacted_subject}\n\n"
            f"Description: {redacted_description}"
        )
        triage_res = await self.triage_agent.run(triage_msg, emit)
        state.triage = triage_res.output
        state.tool_calls.extend(triage_res.tool_calls)
        state.input_tokens += triage_res.input_tokens
        state.output_tokens += triage_res.output_tokens

        intent = (state.triage.get("intent") or "").lower()
        risk = (state.triage.get("risk") or "").lower()
        in_scope = bool(state.triage.get("in_scope", True))

        # Hard route: out-of-scope or high-risk intents skip straight to escalation.
        if not in_scope or risk == "high" or intent in {"billing_or_refund", "outage_report"}:
            await self._escalate(
                state=state,
                emit=emit,
                reason=f"triage routed to escalation (intent={intent}, risk={risk}, in_scope={in_scope})",
                summary=raw_text[:280],
            )
            return await self._finish(state, emit, t0)

        # -------- Stage 3: investigator
        investigator_msg = (
            f"Investigate case {case_id} (intent={intent}, risk={risk}). "
            f"Read it, read the account, look for related cases, and search Confluence."
        )
        inv_res = await self.investigator_agent.run(investigator_msg, emit)
        state.input_tokens += inv_res.input_tokens
        state.output_tokens += inv_res.output_tokens
        state.tool_calls.extend(inv_res.tool_calls)
        state.case = inv_res.output.get("case") or initial_case
        state.account = inv_res.output.get("account") or {}
        state.related_cases = inv_res.output.get("related_cases") or []
        state.kb_hits = inv_res.output.get("kb_hits") or []
        # Fallback: pull kb hits from tool calls if model omitted them in <result>
        if not state.kb_hits:
            for tc in inv_res.tool_calls:
                if tc["tool"] == "confluence_search" and tc.get("status") == "ok":
                    # The preview string isn't structured; just record what we know.
                    pass

        # -------- Stage 4: resolver
        resolver_msg = json.dumps(
            {
                "case": state.case,
                "account": state.account,
                "related_cases": state.related_cases,
                "kb_hits": state.kb_hits,
                "evidence_quality": inv_res.output.get("evidence_quality", "partial"),
            },
            default=str,
        )
        res_res = await self.resolver_agent.run(
            f"Draft a customer reply for this case. Evidence package follows.\n\n{resolver_msg}",
            emit,
        )
        state.input_tokens += res_res.input_tokens
        state.output_tokens += res_res.output_tokens
        state.tool_calls.extend(res_res.tool_calls)
        state.draft = res_res.output
        state.confidence = res_res.output.get("confidence")
        state.citations = list(res_res.output.get("citations") or [])

        # -------- Stage 5: output guardrails
        kb_ids = [h.get("article_id", "") for h in state.kb_hits]
        await emit("stage_enter", {"node": "output_guardrails", "label": "Output guardrails"})
        og = run_output_guardrails(
            draft=state.draft.get("draft", ""),
            kb_hit_ids=kb_ids,
            cited=state.citations,
        )
        state.output_guardrails = [c.to_dict() for c in og]
        for c in og:
            await emit("guardrail_check", {"phase": "output", **c.to_dict()})
        og_failed = sum(1 for c in og if c.status == "fail")
        await emit(
            "stage_exit",
            {
                "node": "output_guardrails",
                "status": "error" if og_failed else ("warn" if any(c.status == "warn" for c in og) else "ok"),
                "summary": f"{sum(c.status == 'pass' for c in og)}/{len(og)} clean",
            },
        )

        # -------- Stage 6: critic (LLM-as-judge)
        critic_msg = json.dumps(
            {
                "case": {"Subject": state.case.get("Subject"), "Description": state.case.get("Description")},
                "kb_hits": state.kb_hits,
                "draft": state.draft.get("draft", ""),
                "claimed_citations": state.citations,
            },
            default=str,
        )
        critic_res = await self.critic_agent.run(
            f"Score this resolver draft.\n\n{critic_msg}", emit,
        )
        state.input_tokens += critic_res.input_tokens
        state.output_tokens += critic_res.output_tokens
        state.tool_calls.extend(critic_res.tool_calls)
        state.critic_scores = critic_res.output

        # -------- Stage 7: trust gate
        await emit("stage_enter", {"node": "trust_gate", "label": "Trust gate"})
        gate = trust_gate(
            intent=intent,
            risk=risk,
            in_scope=in_scope,
            confidence=state.confidence,
            critic_overall=(state.critic_scores or {}).get("overall"),
            critic_passed=bool((state.critic_scores or {}).get("passed")),
            output_guardrails_failed=og_failed,
        )
        await emit(
            "stage_exit",
            {
                "node": "trust_gate",
                "status": "ok" if gate.passed else "warn",
                "summary": "; ".join(gate.reasons)[:160],
                "decision": gate.to_dict(),
            },
        )

        # -------- Stage 8: action or escalation
        if gate.passed:
            action_msg = json.dumps(
                {
                    "case_id": case_id,
                    "approved_reply": state.draft.get("draft", ""),
                    "citations": state.citations,
                    "critic_overall": (state.critic_scores or {}).get("overall"),
                },
                default=str,
            )
            act_res = await self.action_agent.run(
                f"Execute the approved customer reply.\n\n{action_msg}", emit,
            )
            state.input_tokens += act_res.input_tokens
            state.output_tokens += act_res.output_tokens
            state.tool_calls.extend(act_res.tool_calls)
            state.actions_taken = act_res.output.get("actions_taken") or [
                c["tool"] for c in act_res.tool_calls if c["agent"] == "action"
            ]
            state.final_resolution = state.draft.get("draft", "")
        else:
            await self._escalate(
                state=state,
                emit=emit,
                reason="; ".join(gate.reasons),
                summary=state.draft.get("draft", "")[:280] if state.draft else raw_text[:280],
            )

        return await self._finish(state, emit, t0)

    # ---------- helpers ----------

    async def _escalate(self, state: PipelineState, emit: EventEmitter, reason: str, summary: str) -> None:
        state.escalated = True
        msg = json.dumps(
            {
                "case_id": state.case_id,
                "triage": state.triage,
                "case_summary": summary,
                "kb_hits": state.kb_hits,
                "draft": state.draft,
                "critic_scores": state.critic_scores,
                "reason": reason,
            },
            default=str,
        )
        esc_res = await self.escalation_agent.run(
            f"Escalate this case with a clean human handoff.\n\n{msg}", emit,
        )
        state.input_tokens += esc_res.input_tokens
        state.output_tokens += esc_res.output_tokens
        state.tool_calls.extend(esc_res.tool_calls)
        state.actions_taken = ["escalate_to_queue"] + [
            c["tool"] for c in esc_res.tool_calls if c["agent"] == "escalation" and c["tool"] != "escalate_to_queue"
        ]
        state.final_resolution = (
            f"Escalated to {esc_res.output.get('queue', 'Tier2')} "
            f"({esc_res.output.get('priority', 'P2')}). Reason: {reason}"
        )

    async def _finish(self, state: PipelineState, emit: EventEmitter, t0: float) -> PipelineState:
        state.duration_ms = int((time.time() - t0) * 1000)

        # Output node
        await emit("stage_enter", {"node": "output", "label": "Final"})
        await emit(
            "stage_exit",
            {"node": "output", "status": "ok" if not state.escalated else "warn"},
        )

        # Live evals
        eval_scores = self._compute_live_evals(state)
        for s in eval_scores:
            await emit("eval_score", s.to_dict())

        await emit(
            "final",
            {
                "resolution": state.final_resolution,
                "citations": state.citations,
                "confidence": state.confidence,
                "escalated": state.escalated,
                "actions_taken": state.actions_taken,
                "critic_scores": state.critic_scores,
                "evals": [s.to_dict() for s in eval_scores],
            },
        )
        await emit(
            "done",
            {
                "duration_ms": state.duration_ms,
                "input_tokens": state.input_tokens,
                "output_tokens": state.output_tokens,
                "tool_count": len(state.tool_calls),
            },
        )
        return state

    def _compute_live_evals(self, state: PipelineState) -> list[EvalScore]:
        golden = for_case(state.case_id)
        kb_ids = [h.get("article_id", "") for h in state.kb_hits]
        scores: list[EvalScore] = []
        if golden:
            scores.append(score_retrieval_recall(state.kb_hits, golden.expected_articles))
            scores.append(score_tool_correctness(
                [c["tool"] for c in state.tool_calls],
                golden.expected_action_tools,
            ))
            scores.append(score_escalation_decision(state.escalated, golden.should_escalate))
        scores.append(score_groundedness(state.citations, kb_ids))
        og_fail = sum(1 for c in state.output_guardrails if c["status"] == "fail")
        scores.append(score_safety(og_fail))
        scores.append(score_latency(state.duration_ms))
        return scores
