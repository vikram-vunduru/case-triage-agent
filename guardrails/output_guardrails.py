"""Deterministic output guardrails. Run on the Resolver's draft before any write action."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from guardrails.input_guardrails import PII_PATTERNS, PII_EMAIL_ALLOWLIST


NEGATIVE_TONE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(stupid|dumb|idiot|moron)\b",
        r"\b(your fault|user error|pebcak)\b",
        r"\bobviously\b",
        r"\bjust\s+(do|try|click)\b",  # patronizing
    ]
]

INTERNAL_ID_PATTERNS = [
    re.compile(r"\b500[0-9A-Za-z]{12,15}\b"),   # SF Case Id
    re.compile(r"\b001[0-9A-Za-z]{12,15}\b"),   # SF Account Id
    re.compile(r"\b003[0-9A-Za-z]{12,15}\b"),   # SF Contact Id
]


@dataclass
class GuardrailCheck:
    name: str
    label: str
    status: str       # "pass" | "warn" | "fail"
    details: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "status": self.status, "details": self.details}


def check_groundedness(draft: str, kb_hit_ids: Iterable[str], cited: Iterable[str]) -> GuardrailCheck:
    """A draft is grounded if it cites at least one retrieved article AND
    every cited article was actually in the retrieval set."""
    kb_set = {x.upper() for x in kb_hit_ids}
    cite_set = {x.upper() for x in cited}
    if not cite_set:
        return GuardrailCheck("groundedness", "Groundedness", "fail", "no citations in draft")
    invalid = cite_set - kb_set
    if invalid:
        return GuardrailCheck(
            "groundedness",
            "Groundedness",
            "fail",
            f"hallucinated citations: {sorted(invalid)}",
        )
    return GuardrailCheck(
        "groundedness",
        "Groundedness",
        "pass",
        f"{len(cite_set)} citation(s), all in retrieval set",
    )


def check_citations_exist(cited: Iterable[str]) -> GuardrailCheck:
    cites = list(cited)
    if not cites:
        return GuardrailCheck("citations", "Citations present", "fail", "draft has zero citations")
    return GuardrailCheck("citations", "Citations present", "pass", f"{len(cites)} citation(s)")


def check_pii_leak(draft: str) -> GuardrailCheck:
    findings: list[str] = []
    for label, pat in PII_PATTERNS.items():
        for m in pat.finditer(draft):
            v = m.group(0)
            if label == "email" and any(v.lower().endswith(a) for a in PII_EMAIL_ALLOWLIST):
                continue
            findings.append(f"{label}")
    for pat in INTERNAL_ID_PATTERNS:
        if pat.search(draft):
            findings.append("internal_id")
            break
    if findings:
        return GuardrailCheck(
            "pii_leak",
            "PII / internal ID leakage",
            "fail",
            f"draft contains: {', '.join(sorted(set(findings)))}",
        )
    return GuardrailCheck("pii_leak", "PII / internal ID leakage", "pass", "clean")


def check_tone(draft: str) -> GuardrailCheck:
    for pat in NEGATIVE_TONE_PATTERNS:
        m = pat.search(draft)
        if m:
            return GuardrailCheck(
                "tone",
                "Tone",
                "warn",
                f"potentially patronizing language near '{m.group(0)}'",
            )
    return GuardrailCheck("tone", "Tone", "pass", "professional tone")


def run_output_guardrails(
    draft: str,
    kb_hit_ids: Iterable[str],
    cited: Iterable[str],
) -> list[GuardrailCheck]:
    return [
        check_groundedness(draft, kb_hit_ids, cited),
        check_citations_exist(cited),
        check_pii_leak(draft),
        check_tone(draft),
    ]
