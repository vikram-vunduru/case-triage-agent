"""Offline eval harness. Run every golden case through the orchestrator and
print a pass/fail matrix.

Usage:
    python -m evals.run_evals
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anthropic import Anthropic

from agents.orchestrator import Orchestrator
from config import settings
from evals.golden import GOLDEN, GoldenCase
from evals.scoring import (
    score_escalation_decision,
    score_groundedness,
    score_latency,
    score_retrieval_recall,
    score_tool_correctness,
)
from tools.confluence_tool import ConfluenceTool
from tools.salesforce_tool import SalesforceTool


async def _silent(_event: str, _data: dict) -> None:
    pass


async def run_case(orchestrator: Orchestrator, golden: GoldenCase) -> dict:
    state = await orchestrator.run(golden.case_id, _silent)
    scores = [
        score_retrieval_recall(state.kb_hits, golden.expected_articles),
        score_tool_correctness(
            [c["tool"] for c in state.tool_calls],
            golden.expected_action_tools,
        ),
        score_groundedness(state.citations, [h.get("article_id") for h in state.kb_hits]),
        score_escalation_decision(state.escalated, golden.should_escalate),
        score_latency(state.duration_ms),
    ]
    overall = round(sum(s.score for s in scores) / len(scores), 3)
    passed = all(s.status != "fail" for s in scores)
    return {
        "case": golden.case_number,
        "case_id": golden.case_id,
        "expected": {
            "intent": golden.expected_intent,
            "risk": golden.expected_risk,
            "articles": golden.expected_articles,
            "escalate": golden.should_escalate,
            "tools": golden.expected_action_tools,
        },
        "actual": {
            "intent": state.triage.get("intent") if state.triage else None,
            "risk": state.triage.get("risk") if state.triage else None,
            "kb_hits": [h.get("article_id") for h in state.kb_hits],
            "escalated": state.escalated,
            "tools": sorted({c["tool"] for c in state.tool_calls}),
            "confidence": state.confidence,
        },
        "scores": [s.to_dict() for s in scores],
        "overall": overall,
        "passed": passed,
    }


async def main() -> None:
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set in .env — cannot run live eval.")
        sys.exit(1)
    sf = SalesforceTool()
    kb = ConfluenceTool()
    client = Anthropic(api_key=settings.anthropic_api_key)
    orchestrator = Orchestrator(client, sf, kb)

    results = []
    for golden in GOLDEN.values():
        print(f"→ {golden.case_number}: {golden.note}")
        r = await run_case(orchestrator, golden)
        results.append(r)
        verdict = "PASS" if r["passed"] else "FAIL"
        print(f"  {verdict} · overall {r['overall']} · {r['actual']}")

    pass_count = sum(1 for r in results if r["passed"])
    print()
    print(f"=== {pass_count}/{len(results)} cases passed ===")

    out_path = ROOT / "evals" / "last_run.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Full report written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
