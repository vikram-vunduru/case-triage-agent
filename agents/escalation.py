from __future__ import annotations

from agents.base import SubAgent
from tools.salesforce_tool import SalesforceTool


ESCALATE_TOOL = {
    "name": "escalate_to_queue",
    "description": (
        "Hand off the case to a human queue. Provide a structured handoff: queue name, "
        "summary of what the agent learned, what it tried, and the specific question for the human."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "case_id": {"type": "string"},
            "queue": {"type": "string", "description": "e.g. Tier2-Identity, Billing, Security"},
            "summary": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "human_question": {"type": "string", "description": "The specific decision the human must make."},
            "priority": {"type": "string", "enum": ["P1", "P2", "P3"]},
        },
        "required": ["case_id", "queue", "summary", "human_question", "priority"],
    },
}

SF_POST_CHATTER_ESC = {
    "name": "sf_post_chatter",
    "description": "Post an internal Chatter note that records the escalation summary on the Case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "case_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["case_id", "message"],
    },
}


class EscalationAgent(SubAgent):
    name = "escalation"
    node_id = "escalation"
    max_turns = 3
    tools_schema = [ESCALATE_TOOL, SF_POST_CHATTER_ESC]
    system_prompt = (
        "You are the ESCALATION agent. You receive a case that cannot be auto-resolved "
        "(low confidence, failed guardrails, out-of-scope, high-risk action, or critic rejected the draft). "
        "Create a high-quality human handoff:\n"
        "1. Call escalate_to_queue with: case_id, queue (Tier2-Identity for auth issues, Billing for refunds, "
        "Security for suspected takeover, Tier2-General otherwise), summary, evidence (list of facts), "
        "human_question (the specific decision), and priority.\n"
        "2. Call sf_post_chatter to leave the same handoff as an internal Chatter note on the Case.\n\n"
        "After both, return <result>{\"escalated\": true, \"queue\": \"...\", \"priority\": \"...\", "
        "\"reason\": \"...\"}</result>"
    )

    def __init__(self, client, sf: SalesforceTool) -> None:
        super().__init__(client)
        self.sf = sf
        self._last_queue: str | None = None
        self._last_priority: str | None = None

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "escalate_to_queue":
            self._last_queue = tool_input.get("queue")
            self._last_priority = tool_input.get("priority")
            return {
                "escalated": True,
                "queue": tool_input.get("queue"),
                "priority": tool_input.get("priority"),
                "case_id": tool_input.get("case_id"),
            }
        if tool_name == "sf_post_chatter":
            return {"posted": self.sf.post_chatter(
                case_id=tool_input["case_id"],
                message=tool_input["message"],
            )}
        raise ValueError(f"Unknown tool: {tool_name}")

    def parse_output(self, text: str) -> dict:
        parsed = super().parse_output(text)
        parsed.setdefault("escalated", True)
        parsed.setdefault("queue", self._last_queue)
        parsed.setdefault("priority", self._last_priority)
        return parsed
