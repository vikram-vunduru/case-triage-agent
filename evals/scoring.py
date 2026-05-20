"""Live + offline scoring functions. Each returns a numeric score in [0, 1]
plus an explanatory string."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class EvalScore:
    name: str
    label: str
    score: float
    threshold: float
    status: str   # pass | warn | fail
    detail: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "score": round(self.score, 3),
            "threshold": self.threshold,
            "status": self.status,
            "detail": self.detail,
        }


def _status(score: float, threshold: float, warn_band: float = 0.1) -> str:
    if score >= threshold:
        return "pass"
    if score >= threshold - warn_band:
        return "warn"
    return "fail"


def score_retrieval_recall(
    kb_hits: Iterable[dict],
    expected_articles: Iterable[str],
    threshold: float = 0.8,
) -> EvalScore:
    """Did the expected KB article(s) appear in the retrieval top-k?"""
    expected = {a.upper() for a in expected_articles}
    if not expected:
        return EvalScore(
            "retrieval_recall",
            "Retrieval recall",
            1.0,
            threshold,
            "pass",
            "no expected articles defined",
        )
    retrieved = {h.get("article_id", "").upper() for h in kb_hits}
    hits = expected & retrieved
    score = len(hits) / len(expected)
    return EvalScore(
        "retrieval_recall",
        "Retrieval recall",
        score,
        threshold,
        _status(score, threshold),
        f"{len(hits)}/{len(expected)} expected article(s) retrieved",
    )


def score_tool_correctness(
    tools_called: Iterable[str],
    expected_tools: Iterable[str],
    threshold: float = 0.8,
) -> EvalScore:
    expected = list(expected_tools)
    if not expected:
        return EvalScore("tool_correctness", "Tool correctness", 1.0, threshold, "pass", "no expectation")
    called = set(tools_called)
    hits = [t for t in expected if t in called]
    score = len(hits) / len(expected)
    return EvalScore(
        "tool_correctness",
        "Tool correctness",
        score,
        threshold,
        _status(score, threshold),
        f"{len(hits)}/{len(expected)} expected tools called",
    )


def score_groundedness(
    cited: Iterable[str],
    kb_hit_ids: Iterable[str],
    threshold: float = 1.0,
) -> EvalScore:
    cites = list(cited)
    kb = {x.upper() for x in kb_hit_ids}
    if not cites:
        return EvalScore("groundedness", "Groundedness", 0.0, threshold, "fail", "no citations")
    valid = [c for c in cites if c.upper() in kb]
    score = len(valid) / len(cites)
    return EvalScore(
        "groundedness",
        "Groundedness",
        score,
        threshold,
        _status(score, threshold, warn_band=0.001),
        f"{len(valid)}/{len(cites)} citations in retrieval set",
    )


def score_safety(guardrail_failures: int, threshold: float = 1.0) -> EvalScore:
    score = 1.0 if guardrail_failures == 0 else max(0.0, 1.0 - 0.25 * guardrail_failures)
    status = "pass" if guardrail_failures == 0 else ("warn" if guardrail_failures == 1 else "fail")
    return EvalScore(
        "safety",
        "Safety",
        score,
        threshold,
        status,
        f"{guardrail_failures} guardrail failure(s)",
    )


def score_escalation_decision(
    escalated: bool,
    should_escalate: bool | None,
    threshold: float = 1.0,
) -> EvalScore:
    if should_escalate is None:
        return EvalScore("escalation", "Escalation decision", 1.0, threshold, "pass", "no expectation")
    correct = escalated == should_escalate
    return EvalScore(
        "escalation",
        "Escalation decision",
        1.0 if correct else 0.0,
        threshold,
        "pass" if correct else "fail",
        f"agent escalated={escalated}, expected={should_escalate}",
    )


def score_latency(duration_ms: int, target_ms: int = 25_000) -> EvalScore:
    if duration_ms <= target_ms:
        score = 1.0
        status = "pass"
    elif duration_ms <= target_ms * 1.5:
        score = 0.7
        status = "warn"
    else:
        score = 0.4
        status = "fail"
    return EvalScore(
        "latency",
        "Latency",
        score,
        1.0,
        status,
        f"{duration_ms / 1000:.1f}s (target {target_ms / 1000:.0f}s)",
    )


def score_cost(total_tokens: int, target_tokens: int = 20_000) -> EvalScore:
    if total_tokens <= target_tokens:
        score, status = 1.0, "pass"
    elif total_tokens <= target_tokens * 1.5:
        score, status = 0.7, "warn"
    else:
        score, status = 0.4, "fail"
    return EvalScore(
        "cost",
        "Cost",
        score,
        1.0,
        status,
        f"{total_tokens} tokens (target {target_tokens})",
    )
