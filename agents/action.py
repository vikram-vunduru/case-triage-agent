from __future__ import annotations

from agents.base import SubAgent
from tools.salesforce_tool import SalesforceTool


SF_POST_CHATTER = {
    "name": "sf_post_chatter",
    "description": (
        "Post an INTERNAL Chatter note on the Case as an audit trail. Include your reasoning, "
        "the KB article ids you used, and any caveats. Visible to internal users only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "case_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["case_id", "message"],
    },
}

SF_UPDATE_CASE = {
    "name": "sf_update_case",
    "description": (
        "Update the Case with a public customer-facing comment, and set status. "
        "Allowed status values: 'Working', 'Awaiting Customer', 'Resolved'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "case_id": {"type": "string"},
            "status": {"type": "string"},
            "comment": {"type": "string", "description": "Public reply the customer will see."},
            "resolution": {"type": "string", "description": "Internal resolution summary."},
        },
        "required": ["case_id", "comment"],
    },
}


class ActionAgent(SubAgent):
    name = "action"
    node_id = "action"
    max_turns = 4
    tools_schema = [SF_POST_CHATTER, SF_UPDATE_CASE]
    system_prompt = (
        "You are the ACTION agent. You receive a vetted customer reply (already passed guardrails + critic) "
        "and the case context. Execute exactly TWO writes against Salesforce:\n"
        "1. Call sf_post_chatter to record an internal audit trail including: the KB article ids used, "
        "the critic's overall score, and any caveats. Mark this clearly as 'Agent audit'.\n"
        "2. Call sf_update_case with the customer-facing reply as the comment, status='Awaiting Customer', "
        "and a one-line resolution summary.\n\n"
        "Do NOT modify the customer reply — it has already been approved. "
        "After both writes complete, return <result>{\"actions_taken\": [\"sf_post_chatter\", \"sf_update_case\"], "
        "\"case_id\": \"...\"}</result>"
    )

    def __init__(self, client, sf: SalesforceTool) -> None:
        super().__init__(client)
        self.sf = sf

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "sf_post_chatter":
            return {"posted": self.sf.post_chatter(
                case_id=tool_input["case_id"],
                message=tool_input["message"],
            )}
        if tool_name == "sf_update_case":
            return {"updated": self.sf.update_case(
                case_id=tool_input["case_id"],
                status=tool_input.get("status", "Working"),
                comment=tool_input.get("comment"),
                resolution=tool_input.get("resolution"),
            )}
        raise ValueError(f"Unknown tool: {tool_name}")
