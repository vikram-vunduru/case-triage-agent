from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from anthropic import Anthropic

from config import settings


EventEmitter = Callable[[str, dict], Awaitable[None]]


@dataclass
class AgentResult:
    output: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


class SubAgent:
    """Base class for a specialized agent with its own scoped tools."""

    name: str = "base"
    node_id: str = "base"  # matches UI architecture node id
    model: str | None = None
    max_turns: int = 6
    system_prompt: str = ""
    tools_schema: list[dict[str, Any]] = []

    def __init__(self, client: Anthropic) -> None:
        self.client = client

    # Sub-classes override this to dispatch tool calls.
    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        raise NotImplementedError(f"{self.name} does not handle tool {tool_name}")

    # Sub-classes override to parse the final assistant message into a dict.
    def parse_output(self, text: str) -> dict[str, Any]:
        match = re.search(r"<result>(.*?)</result>", text, re.DOTALL)
        candidate = match.group(1).strip() if match else text.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            match2 = re.search(r"\{.*\}", candidate, re.DOTALL)
            if match2:
                try:
                    return json.loads(match2.group(0))
                except json.JSONDecodeError:
                    pass
        return {"text": text.strip()}

    async def run(
        self,
        user_message: str,
        emit: EventEmitter,
        extra_system: str = "",
    ) -> AgentResult:
        result = AgentResult()
        t0 = time.time()
        messages: list[dict] = [{"role": "user", "content": user_message}]
        sys_prompt = self.system_prompt + ("\n\n" + extra_system if extra_system else "")

        await emit(
            "agent_start",
            {"agent": self.name, "node": self.node_id, "model": self.model or settings.anthropic_model},
        )

        last_text = ""
        for turn in range(self.max_turns):
            kwargs = {
                "model": self.model or settings.anthropic_model,
                "max_tokens": 1500,
                "system": sys_prompt,
                "messages": messages,
            }
            if self.tools_schema:
                kwargs["tools"] = self.tools_schema

            try:
                response = await asyncio.to_thread(self.client.messages.create, **kwargs)
            except Exception as exc:  # noqa: BLE001
                result.error = str(exc)
                await emit("agent_error", {"agent": self.name, "message": str(exc)})
                break

            result.input_tokens += response.usage.input_tokens
            result.output_tokens += response.usage.output_tokens

            messages.append({"role": "assistant", "content": response.content})

            tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]
            last_text = "\n".join(b.text for b in text_blocks).strip()

            if not tool_use_blocks:
                break

            tool_results: list[dict] = []
            for block in tool_use_blocks:
                await emit(
                    "tool_start",
                    {
                        "agent": self.name,
                        "node": self.node_id,
                        "tool_name": block.name,
                        "args": block.input,
                    },
                )
                t_tool = time.time()
                try:
                    tool_out = await asyncio.to_thread(self.execute_tool, block.name, block.input)
                    status = "ok"
                    err = None
                except Exception as exc:  # noqa: BLE001
                    tool_out = {"error": str(exc)}
                    status = "error"
                    err = str(exc)
                duration = int((time.time() - t_tool) * 1000)

                preview = _preview_tool_result(block.name, tool_out)
                result.tool_calls.append(
                    {
                        "agent": self.name,
                        "tool": block.name,
                        "args": block.input,
                        "status": status,
                        "duration_ms": duration,
                        "preview": preview,
                    }
                )
                await emit(
                    "tool_end",
                    {
                        "agent": self.name,
                        "node": self.node_id,
                        "tool_name": block.name,
                        "status": status,
                        "duration_ms": duration,
                        "preview": preview,
                        "error": err,
                    },
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_out, default=str),
                        "is_error": status == "error",
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        result.duration_ms = int((time.time() - t0) * 1000)
        result.output = self.parse_output(last_text)

        await emit(
            "agent_end",
            {
                "agent": self.name,
                "node": self.node_id,
                "duration_ms": result.duration_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "output_summary": _summarize_agent_output(self.name, result.output),
                "tool_count": len(result.tool_calls),
            },
        )
        return result


def _preview_tool_result(tool_name: str, result: dict) -> str:
    if isinstance(result, dict) and "error" in result:
        return f"error: {str(result['error'])[:120]}"
    if tool_name == "sf_get_case":
        c = result.get("case", {}) if isinstance(result, dict) else {}
        return f"{c.get('CaseNumber', '')}: {c.get('Subject', '')[:60]}"
    if tool_name == "sf_get_account":
        a = result.get("account", {}) if isinstance(result, dict) else {}
        return f"{a.get('Name', '')} · {a.get('Tier__c', '')}"
    if tool_name == "sf_get_related_cases":
        rs = result.get("related", []) if isinstance(result, dict) else []
        return f"{len(rs)} related case(s)"
    if tool_name == "confluence_search":
        hits = result.get("results", []) if isinstance(result, dict) else []
        return ", ".join(f"{h.get('article_id')} ({h.get('score')})" for h in hits[:3])
    if tool_name == "sf_post_chatter":
        return "Chatter post created"
    if tool_name == "sf_update_case":
        u = result.get("updated", {}) if isinstance(result, dict) else {}
        return f"Status → {u.get('Status', '?')}"
    if tool_name == "escalate_to_queue":
        return f"queue: {result.get('queue', '')}"
    if tool_name.startswith("classify_") or tool_name.startswith("score_") or tool_name.startswith("check_"):
        return json.dumps({k: v for k, v in (result or {}).items() if not isinstance(v, (list, dict))})[:120]
    if isinstance(result, dict):
        keys = list(result.keys())[:3]
        return f"keys={keys}"
    return str(result)[:120]


def _summarize_agent_output(agent_name: str, output: dict) -> str:
    if not output:
        return ""
    if "intent" in output or "risk" in output:
        return (
            f"intent={output.get('intent', '?')} · risk={output.get('risk', '?')} · "
            f"urgency={output.get('urgency', '?')} · in_scope={output.get('in_scope', True)}"
        )
    if "case" in output and isinstance(output.get("case"), dict):
        case = output["case"]
        kb = output.get("kb_hits", [])
        return f"{case.get('CaseNumber', '?')} · KB={len(kb)} hit(s) · account={output.get('account', {}).get('Name', '?')}"
    if "draft" in output or "response" in output:
        c = output.get("confidence")
        cites = output.get("citations", [])
        return f"draft built · conf={c} · cites={cites}"
    if "scores" in output and isinstance(output["scores"], dict):
        s = output["scores"]
        return " · ".join(f"{k}={v}" for k, v in s.items())
    if "escalated" in output:
        return f"escalated → {output.get('queue', '?')}"
    if "actions_taken" in output:
        return f"actions={output['actions_taken']}"
    return str(output)[:120]
