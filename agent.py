"""Thin entry point. Constructs the Anthropic client + tools + Orchestrator.

Kept for symmetry with imports elsewhere. Real logic lives in
agents/orchestrator.py and agents/*.
"""
from __future__ import annotations

from anthropic import Anthropic

from agents.orchestrator import Orchestrator
from config import settings
from tools.confluence_tool import ConfluenceTool
from tools.salesforce_tool import SalesforceTool


def build_orchestrator() -> Orchestrator:
    client = Anthropic(api_key=settings.anthropic_api_key)
    sf = SalesforceTool()
    kb = ConfluenceTool()
    return Orchestrator(client, sf, kb)
