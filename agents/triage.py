from __future__ import annotations

from typing import Any

from agents.base import SubAgent


INTENTS = ["auth_issue", "billing_or_refund", "feature_request", "outage_report", "data_question", "other"]
RISKS = ["low", "medium", "high"]
URGENCIES = ["low", "medium", "high"]


CLASSIFY_INTENT = {
    "name": "classify_intent",
    "description": "Classify the user's intent. Choose ONE from: " + ", ".join(INTENTS),
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
        "Classify the operational risk of acting autonomously on this case. "
        "High = irreversible actions, money movement, account changes, security incidents. "
        "Medium = customer-visible writes, configuration changes. "
        "Low = informational answers, KB pointers."
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
        '"urgency": "low|medium|high", "rationale": "one-sentence summary"}</result>\n'
        "Guidelines: a Sev-1 outage or VIP account → urgency=high. Refunds and account changes → risk=high. "
        "Login/MFA/SSO troubleshooting → risk=low. Out-of-scope topics (weather, news, jokes) → in_scope=false."
    )

    def __init__(self, client) -> None:
        super().__init__(client)
        self._classifications: dict[str, Any] = {}

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        # These "tools" are model-self-classifications. We echo them back as confirmation
        # and store them so the parse_output step can fall back to them if the model
        # forgets the <result> wrapper.
        self._classifications[tool_name] = tool_input
        return {"recorded": tool_input}

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
