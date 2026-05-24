from __future__ import annotations

from typing import Any

from agents.base import SubAgent


INTENTS = ["auth_issue", "billing_or_refund", "feature_request", "outage_report", "data_question", "other"]
RISKS = ["low", "medium", "high"]
URGENCIES = ["low", "medium", "high"]


CLASSIFY_INTENT = {
    "name": "classify_intent",
    "description": (
        "Classify the user's intent. Choose ONE from: " + ", ".join(INTENTS) + ".\n\n"
        "Guidance per intent:\n"
        "- auth_issue: login, password reset, MFA, SSO, account lockout, session/cookie problems.\n"
        "- billing_or_refund: ONLY when money movement is requested or disputed — refunds, credits, "
        "billing disputes, charge inquiries, invoice questions.\n"
        "- feature_request: explicit asks like 'I wish you supported X' or 'when will you add Y'.\n"
        "- outage_report: CONFIRMED widespread service unavailability impacting multiple users. "
        "A single user reporting a bug or a slow page is NOT an outage_report — that is 'other' or 'data_question'.\n"
        "- data_question: how data behaves — exports, queries, reports, filters, calculations, missing records.\n"
        "- other: anything else, including general how-to questions, single-user technical bugs, "
        "performance complaints, notifications not arriving."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": INTENTS},
            "rationale": {"type": "string"},
        },
        "required": ["intent", "rationale"],
    },
}

CLASSIFY_RISK = {
    "name": "classify_risk",
    "description": (
        "Classify the OPERATIONAL RISK of letting an AI agent act autonomously on this case. "
        "Risk is ONLY about whether the agent's action would be hard to reverse. "
        "It is INDEPENDENT of how urgent the customer says it is or how upset they sound.\n\n"
        "HIGH (must escalate to human): "
        "money movement (refunds, credits, charges); permanent data deletion "
        "(GDPR right-to-erasure, account removal); irreversible record restoration; "
        "account ownership transfers; permission or role grants; any production-system change; "
        "security incidents (suspected breach, account takeover, SIM-swap).\n\n"
        "MEDIUM: customer-visible writes that are reversible — a Chatter post, a Case comment, "
        "a Case status change. Minor configuration changes.\n\n"
        "LOW (safe for the agent to handle autonomously): informational answers, KB pointers, "
        "self-service troubleshooting steps the user runs themselves, feature explanations, "
        "performance complaints, UI bugs, display issues, CSV/data export problems, notification setup, "
        "browser cache issues, authentication troubleshooting (password reset, MFA, lockout). "
        "Customer urgency does NOT raise risk: a 'tomorrow morning' CSV bug is still LOW — "
        "the worst the agent can do is tell them to clear cache."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "risk": {"type": "string", "enum": RISKS},
            "rationale": {"type": "string"},
        },
        "required": ["risk", "rationale"],
    },
}

CHECK_SCOPE = {
    "name": "check_topic_in_scope",
    "description": (
        "Decide whether the case is a support topic the agent is permitted to handle. "
        "Out-of-scope examples: general knowledge questions, weather, jokes, anything unrelated to the product."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "in_scope": {"type": "boolean"},
            "topic": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["in_scope", "topic", "rationale"],
    },
}


class TriageAgent(SubAgent):
    name = "triage"
    node_id = "triage"
    max_turns = 4
    tools_schema = [CLASSIFY_INTENT, CLASSIFY_RISK, CHECK_SCOPE]
    system_prompt = (
        "You are the TRIAGE agent in a multi-agent Service Cloud system. "
        "Your job is to classify a customer support case along three axes: "
        "intent, risk, and topic scope. "
        "Call each of classify_intent, classify_risk, and check_topic_in_scope EXACTLY ONCE. "
        "Then respond with a single final message in this format wrapped in <result></result>:\n"
        '<result>{"intent": "...", "risk": "...", "in_scope": true|false, '
        '"urgency": "low|medium|high", "rationale": "one-sentence summary"}</result>\n\n'
        "IMPORTANT — read these definitions carefully, they are easy to confuse:\n"
        "- urgency is how time-sensitive the CUSTOMER says it is (deadlines, business impact).\n"
        "- risk is how DANGEROUS it would be for the AI to act autonomously on this case.\n"
        "- These two are INDEPENDENT. They must be judged separately:\n"
        "    • A 'we need this by tomorrow' CSV bug = urgency HIGH, risk LOW (the agent can safely tell the user to clear cache).\n"
        "    • A 'whenever you can get to it' refund request = urgency LOW, risk HIGH (no AI should refund money without human review).\n\n"
        "Concrete examples of correct classification:\n"
        "  'Dashboard loads slowly'           → intent=other,            risk=low,    urgency=low/medium\n"
        "  'CSV export returns empty file'     → intent=data_question,    risk=low,    urgency=medium\n"
        "  'Not getting email notifications'   → intent=other,            risk=low,    urgency=low\n"
        "  'Cannot log in after password reset' → intent=auth_issue,      risk=low,    urgency=high (if they say blocked)\n"
        "  'Refund our annual subscription'    → intent=billing_or_refund, risk=high,  urgency=high\n"
        "  'GDPR delete my account'            → intent=other,            risk=high,   urgency=medium\n"
        "  'Restore deleted records'           → intent=other,            risk=high,   urgency=high\n"
        "  'All our users cannot log in'       → intent=outage_report,    risk=high,   urgency=high\n\n"
        "Out-of-scope topics (weather, news, jokes, recipes) → in_scope=false."
    )

    def __init__(self, client) -> None:
        super().__init__(client)
        self._classifications: dict[str, Any] = {}

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        # These "tools" are model-self-classifications. We store them so the
        # parse_output step can fall back to them if the model forgets the
        # <result> wrapper. Returning tool_input itself (rather than a wrapper)
        # makes the live trace show the actual decision, e.g. "intent: auth_issue".
        self._classifications[tool_name] = tool_input
        return tool_input

    def parse_output(self, text: str) -> dict:
        parsed = super().parse_output(text)
        if "intent" not in parsed and "classify_intent" in self._classifications:
            parsed["intent"] = self._classifications["classify_intent"].get("intent")
        if "risk" not in parsed and "classify_risk" in self._classifications:
            parsed["risk"] = self._classifications["classify_risk"].get("risk")
        if "in_scope" not in parsed and "check_topic_in_scope" in self._classifications:
            parsed["in_scope"] = self._classifications["check_topic_in_scope"].get("in_scope")
        parsed.setdefault("urgency", "medium")
        parsed.setdefault("in_scope", True)
        return parsed
