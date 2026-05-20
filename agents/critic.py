from __future__ import annotations

from agents.base import SubAgent


SCORE_DIMENSIONS = ["groundedness", "citation_validity", "tone", "completeness", "safety"]


SCORE_TOOL = {
    "name": "score_resolution",
    "description": (
        "Score the resolver's draft across five dimensions on a 0.0-1.0 scale. "
        "Call this exactly once."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "groundedness": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Every actionable step is supported by retrieved KB content.",
            },
            "citation_validity": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Cited article_ids actually appear in the retrieval results.",
            },
            "tone": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Professional, empathetic, action-oriented language.",
            },
            "completeness": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Addresses the customer's specific symptoms.",
            },
            "safety": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "No PII leakage, no privileged advice, no harmful suggestions.",
            },
            "comments": {"type": "string"},
        },
        "required": SCORE_DIMENSIONS + ["comments"],
    },
}


class CriticAgent(SubAgent):
    name = "critic"
    node_id = "critic"
    max_turns = 3
    tools_schema = [SCORE_TOOL]
    system_prompt = (
        "You are the CRITIC agent — an LLM-as-judge that scores the Resolver's draft. "
        "You receive the case, account, retrieved KB articles, and the Resolver's draft "
        "(including the claimed citations). Score it on five dimensions: groundedness, "
        "citation_validity, tone, completeness, safety. Be strict but fair.\n\n"
        "Call score_resolution EXACTLY ONCE with all five scores plus a one-line comment. "
        "After the tool call, return a final <result></result> JSON that REPEATS the scores "
        "and adds an 'overall' score (the mean), 'passed' (true if overall >= 0.7 AND every "
        "individual score >= 0.6), and 'top_issue' (a short string)."
    )

    def __init__(self, client) -> None:
        super().__init__(client)
        self._scored: dict = {}

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "score_resolution":
            self._scored = tool_input
            # Return the scores so the live trace shows them, instead of just "recorded".
            return tool_input
        raise ValueError(f"Unknown tool: {tool_name}")

    def parse_output(self, text: str) -> dict:
        parsed = super().parse_output(text)
        # Always reconcile with what the model passed to the tool.
        scored = self._scored
        scores = {dim: float(scored.get(dim, parsed.get(dim, 0.0))) for dim in SCORE_DIMENSIONS}
        overall = round(sum(scores.values()) / len(scores), 3)
        passed = overall >= 0.7 and all(v >= 0.6 for v in scores.values())
        return {
            "scores": scores,
            "overall": overall,
            "passed": passed,
            "top_issue": parsed.get("top_issue") or scored.get("comments", "")[:80],
        }
