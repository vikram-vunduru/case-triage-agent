"""Deterministic input guardrails. Fast, explainable, auditable.

In production these would be supplemented by a small classifier or a managed
service (e.g. Prompt Shields). For the demo, regex + keyword lists are enough
to demonstrate the pattern visibly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Allow-list domains so the seed fixtures don't trip the PII guard.
PII_EMAIL_ALLOWLIST = ("@example", "@acmecorp.example", "@globex.example", "@initech.example")

PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
}

INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore (the )?(previous|above|prior) (instructions|prompt|system)",
        r"disregard (all|previous|above|prior) instructions",
        r"you are now (DAN|in developer mode|jailbroken)",
        r"<\|system\|>",
        r"###\s*system",
        r"forget (your|all) (instructions|rules|guardrails)",
        r"act as (if you have|though you have) no (guardrails|restrictions)",
        r"reveal your (system prompt|instructions)",
    ]
]

OFF_TOPIC_KEYWORDS = [
    "weather forecast",
    "stock price",
    "stock tips",
    "tell me a joke",
    "write a poem",
    "recipe for",
    "song lyrics",
    "movie recommendation",
]

ABUSE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(fuck|shit|asshole|bitch|bastard)\b",
        r"\b(idiot|stupid|moron)\b.*(support|you|agent)",
        r"\bi'?ll sue you\b",
        r"\bthreaten\b",
    ]
]


@dataclass
class GuardrailCheck:
    name: str
    label: str
    status: str       # "pass" | "warn" | "fail"
    details: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "status": self.status, "details": self.details}


def check_pii(text: str) -> GuardrailCheck:
    findings: list[str] = []
    for label, pat in PII_PATTERNS.items():
        for m in pat.finditer(text):
            value = m.group(0)
            if label == "email" and any(value.lower().endswith(allow) for allow in PII_EMAIL_ALLOWLIST):
                continue
            if label == "phone" and len(re.sub(r"\D", "", value)) < 7:
                continue
            findings.append(f"{label}: {value[:8]}…")
    if findings:
        return GuardrailCheck(
            name="pii",
            label="PII",
            status="warn",
            details=f"{len(findings)} match(es) — redacted before agent run",
        )
    return GuardrailCheck(name="pii", label="PII", status="pass", details="no PII detected")


def check_prompt_injection(text: str) -> GuardrailCheck:
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            return GuardrailCheck(
                name="injection",
                label="Prompt injection",
                status="fail",
                details=f"matched pattern: {pat.pattern}",
            )
    return GuardrailCheck(name="injection", label="Prompt injection", status="pass", details="no injection markers")


def check_topic_in_scope(text: str) -> GuardrailCheck:
    low = text.lower()
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in low:
            return GuardrailCheck(
                name="scope",
                label="Topic scope",
                status="warn",
                details=f"matched off-topic keyword: '{kw}'",
            )
    return GuardrailCheck(name="scope", label="Topic scope", status="pass", details="in scope")


def check_abuse(text: str) -> GuardrailCheck:
    for pat in ABUSE_PATTERNS:
        if pat.search(text):
            return GuardrailCheck(
                name="abuse",
                label="Abuse/profanity",
                status="warn",
                details="abusive language — flagged for human review",
            )
    return GuardrailCheck(name="abuse", label="Abuse/profanity", status="pass", details="clean")


def run_input_guardrails(text: str) -> list[GuardrailCheck]:
    return [
        check_pii(text),
        check_prompt_injection(text),
        check_topic_in_scope(text),
        check_abuse(text),
    ]


def redact_pii(text: str) -> str:
    """Best-effort PII redaction. Used before passing user-controlled text to the model."""
    out = text
    for label, pat in PII_PATTERNS.items():
        def _sub(m: re.Match) -> str:
            v = m.group(0)
            if label == "email" and any(v.lower().endswith(allow) for allow in PII_EMAIL_ALLOWLIST):
                return v
            return f"[REDACTED_{label.upper()}]"
        out = pat.sub(_sub, out)
    return out
