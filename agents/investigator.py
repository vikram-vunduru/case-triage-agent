from __future__ import annotations

from typing import Any

from agents.base import SubAgent
from tools.confluence_tool import ConfluenceTool
from tools.salesforce_tool import SalesforceTool


SF_GET_CASE = {
    "name": "sf_get_case",
    "description": "Read a Salesforce Case by Id or CaseNumber.",
    "input_schema": {
        "type": "object",
        "properties": {"case_id": {"type": "string"}},
        "required": ["case_id"],
    },
}

SF_GET_ACCOUNT = {
    "name": "sf_get_account",
    "description": "Read the related Salesforce Account to understand tier, SLA, owner.",
    "input_schema": {
        "type": "object",
        "properties": {"account_id": {"type": "string"}},
        "required": ["account_id"],
    },
}

SF_GET_RELATED_CASES = {
    "name": "sf_get_related_cases",
    "description": "List recent cases for the same Account to detect patterns or repeat issues.",
    "input_schema": {
        "type": "object",
        "properties": {
            "account_id": {"type": "string"},
            "exclude_case_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
        "required": ["account_id"],
    },
}

CONFLUENCE_SEARCH = {
    "name": "confluence_search",
    "description": (
        "Search the Confluence knowledge base for troubleshooting articles. "
        "Use specific symptom keywords. Returns top_k hits with article_id, title, score, snippet."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
        },
        "required": ["query"],
    },
}


class InvestigatorAgent(SubAgent):
    name = "investigator"
    node_id = "investigator"
    max_turns = 8
    tools_schema = [SF_GET_CASE, SF_GET_ACCOUNT, SF_GET_RELATED_CASES, CONFLUENCE_SEARCH]
    system_prompt = (
        "You are the INVESTIGATOR agent. Your job is to gather all the context needed to resolve a support case. "
        "Follow this procedure:\n"
        "1. Call sf_get_case with the provided case_id.\n"
        "2. Call sf_get_account with the AccountId from the case.\n"
        "3. Call sf_get_related_cases for the same account to spot patterns.\n"
        "4. Call confluence_search at least once using specific symptoms (not the whole subject). "
        "You may call it again with a different query if the first results are weak (score < 0.4).\n"
        "When complete, respond with this JSON inside <result></result>:\n"
        '<result>{\n'
        '  "case": {"Id": "...", "CaseNumber": "...", "Subject": "...", "Description": "...", '
        '"Priority": "...", "Status": "...", "AccountId": "..."},\n'
        '  "account": {"Id": "...", "Name": "...", "Tier__c": "...", "Notes": "..."},\n'
        '  "related_cases": [...],\n'
        '  "kb_hits": [{"article_id": "...", "title": "...", "score": ..., "snippet": "..."}],\n'
        '  "evidence_quality": "strong|partial|weak",\n'
        '  "notes": "what stands out about this case"\n'
        '}</result>'
    )

    def __init__(self, client, sf: SalesforceTool, kb: ConfluenceTool) -> None:
        super().__init__(client)
        self.sf = sf
        self.kb = kb

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "sf_get_case":
            return {"case": self.sf.get_case(tool_input["case_id"])}
        if tool_name == "sf_get_account":
            return {"account": self.sf.get_account(tool_input["account_id"])}
        if tool_name == "sf_get_related_cases":
            return {
                "related": self.sf.get_related_cases(
                    account_id=tool_input["account_id"],
                    exclude_case_id=tool_input.get("exclude_case_id"),
                    limit=int(tool_input.get("limit", 5)),
                )
            }
        if tool_name == "confluence_search":
            return {
                "query": tool_input["query"],
                "results": self.kb.search_kb(
                    query=tool_input["query"],
                    top_k=int(tool_input.get("top_k", 3)),
                ),
            }
        raise ValueError(f"Unknown tool: {tool_name}")
