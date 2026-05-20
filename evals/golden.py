"""Golden dataset: ground truth expectations for the seed cases.

These power both the offline eval harness (evals/run_evals.py) and the
optional live scoring against the case under test."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoldenCase:
    case_id: str
    case_number: str
    expected_intent: str
    expected_risk: str
    expected_articles: list[str]
    should_escalate: bool
    expected_action_tools: list[str]
    note: str


GOLDEN: dict[str, GoldenCase] = {
    "5003a00000A1B2C": GoldenCase(
        case_id="5003a00000A1B2C",
        case_number="CASE-1001",
        expected_intent="auth_issue",
        expected_risk="low",
        expected_articles=["KB-247"],
        should_escalate=False,
        expected_action_tools=["sf_post_chatter", "sf_update_case"],
        note="Password reset / Invalid credentials — KB-247 directly applies.",
    ),
    "5003a00000A1B2D": GoldenCase(
        case_id="5003a00000A1B2D",
        case_number="CASE-1002",
        expected_intent="auth_issue",
        expected_risk="low",
        expected_articles=["KB-301"],
        should_escalate=False,
        expected_action_tools=["sf_post_chatter", "sf_update_case"],
        note="MFA code delivery — KB-301 applies.",
    ),
    "5003a00000A1B2E": GoldenCase(
        case_id="5003a00000A1B2E",
        case_number="CASE-1003",
        expected_intent="auth_issue",
        expected_risk="low",
        expected_articles=["KB-356"],
        should_escalate=False,
        expected_action_tools=["sf_post_chatter", "sf_update_case"],
        note="Account lockout — KB-356 applies.",
    ),
    "5003a00000A1B2F": GoldenCase(
        case_id="5003a00000A1B2F",
        case_number="CASE-1004",
        expected_intent="auth_issue",
        expected_risk="low",
        expected_articles=["KB-412"],
        should_escalate=False,
        expected_action_tools=["sf_post_chatter", "sf_update_case"],
        note="Safari session cookies — KB-412 applies.",
    ),
    "5003a00000A1B30": GoldenCase(
        case_id="5003a00000A1B30",
        case_number="CASE-1005",
        expected_intent="auth_issue",
        expected_risk="medium",
        expected_articles=["KB-509"],
        should_escalate=True,  # IP allow-list change requires admin
        expected_action_tools=["escalate_to_queue"],
        note="VPN SSO failure — KB-509 documents the fix but it requires an Identity admin to change the IP allow-list.",
    ),
    "5003a00000A1B31": GoldenCase(
        case_id="5003a00000A1B31",
        case_number="CASE-1006",
        expected_intent="billing_or_refund",
        expected_risk="high",
        expected_articles=[],
        should_escalate=True,
        expected_action_tools=["escalate_to_queue"],
        note="$48,000 refund — no KB applies; escalate to Billing.",
    ),
}


def for_case(case_id: str) -> GoldenCase | None:
    return GOLDEN.get(case_id)
