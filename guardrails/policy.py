"""Policy engine + trust gate. Deterministic decisions about whether the
pipeline can auto-execute or must escalate.

This is where Salesforce's Einstein Trust Layer concepts live in our demo:
risk classification, action budgets, confidence thresholds, approval gates.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import settings


HIGH_RISK_INTENTS = {"billing_or_refund", "outage_report"}


@dataclass
class TrustGateDecision:
    passed: bool
    reasons: list[str]
    require_approval: bool = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reasons": self.reasons,
            "require_approval": self.require_approval,
        }


def trust_gate(
    intent: str,
    risk: str,
    in_scope: bool,
    confidence: float | None,
    critic_overall: float | None,
    critic_passed: bool,
    output_guardrails_failed: int,
) -> TrustGateDecision:
    reasons: list[str] = []
    passed = True

    if not in_scope:
        passed = False
        reasons.append("topic out of scope")

    if intent in HIGH_RISK_INTENTS:
        passed = False
        reasons.append(f"intent '{intent}' requires human")

    if risk == "high":
        passed = False
        reasons.append("triage flagged risk=high")

    if confidence is not None and confidence < settings.confidence_threshold:
        passed = False
        reasons.append(f"confidence {confidence:.2f} < threshold {settings.confidence_threshold}")

    if critic_overall is not None and critic_overall < 0.7:
        passed = False
        reasons.append(f"critic overall {critic_overall:.2f} < 0.70")

    if not critic_passed:
        passed = False
        reasons.append("critic rejected the draft")

    if output_guardrails_failed > 0:
        passed = False
        reasons.append(f"{output_guardrails_failed} output guardrail(s) failed")

    if passed and not reasons:
        reasons.append("all checks passed")

    return TrustGateDecision(
        passed=passed,
        reasons=reasons,
        require_approval=settings.require_human_approval,
    )
