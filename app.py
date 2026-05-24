from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agents.orchestrator import Orchestrator
from config import settings
from evals.golden import for_case
from tools.confluence_tool import ConfluenceTool
from tools.salesforce_tool import SalesforceTool
from tools.slack_tool import ApprovalDecision, SlackTool


ROOT = Path(__file__).resolve().parent
# When deployed behind Cloudflare Tunnel at e.g. agents.vikramvunduru.com/case-triage-agent
# set ROUTE_PREFIX=/case-triage-agent in .env. Empty = serve at root (local dev).
ROUTE_PREFIX = settings.route_prefix.rstrip("/")

_sessions: dict[str, dict] = {}

# In-memory unlock-token store. {token: expiry_unix_ts}. Lives until process restart;
# unlocked browsers will re-prompt after a redeploy, which is acceptable for a demo.
_demo_tokens: dict[str, float] = {}

# Pending Slack approvals — orchestrator stores a Future here keyed by
# approval_id, then `await`s it. The /api/slack/interactivity callback
# resolves it when Slack POSTs the user's button click.
_pending_approvals: dict[str, asyncio.Future] = {}


def _password_required() -> bool:
    return bool(settings.demo_password)


def _is_token_valid(token: str | None) -> bool:
    if not token:
        return False
    expiry = _demo_tokens.get(token)
    if not expiry:
        return False
    if time.time() > expiry:
        _demo_tokens.pop(token, None)
        return False
    return True


def _require_unlock(request: Request) -> None:
    """Raises 401 if the demo is locked and the request lacks a valid token."""
    if not _password_required():
        return
    token = (
        request.headers.get("x-demo-token")
        or request.headers.get("X-Demo-Token")
        or request.cookies.get("demo_token")
    )
    if not _is_token_valid(token):
        raise HTTPException(status_code=401, detail="locked")


# Define lifespan first with a forward reference to api_app. Python resolves
# `api_app` at call time, so the closure picks up whichever api_app is bound when
# the lifespan actually runs.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Always set state on api_app (where the routes live), regardless of whether
    # uvicorn is booting the inner app directly or the outer wrapper.
    api_app.state.sf = SalesforceTool()
    api_app.state.kb = ConfluenceTool()
    api_app.state.slack = SlackTool()
    api_app.state.pending_approvals = _pending_approvals
    api_app.state.client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
    api_app.state.orchestrator = (
        Orchestrator(
            api_app.state.client,
            api_app.state.sf,
            api_app.state.kb,
            slack=api_app.state.slack,
            pending_approvals=api_app.state.pending_approvals,
        )
        if api_app.state.client else None
    )
    yield


# Create the inner api app with the lifespan wired at construction time
# (post-hoc assignment to router.lifespan_context does not work in Starlette ≥ 0.30).
api_app = FastAPI(title="Case Triage Multi-Agent", lifespan=lifespan)
api_app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@api_app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@api_app.get("/support")
@api_app.get("/support/")
def portal_index() -> FileResponse:
    """Customer-facing support portal — submit a ticket that lands in Salesforce."""
    return FileResponse(ROOT / "static" / "support.html")


class PortalCaseRequest(BaseModel):
    subject: str
    description: str
    name: str = ""
    email: str = ""
    priority: str = "Medium"
    type: str = ""


@api_app.post("/api/portal/case")
def portal_create_case(req: PortalCaseRequest) -> JSONResponse:
    """Public endpoint — anyone can submit a ticket from the portal."""
    subject = (req.subject or "").strip()
    description = (req.description or "").strip()
    if not subject or len(subject) < 4:
        raise HTTPException(status_code=400, detail="subject must be at least 4 characters")
    if not description or len(description) < 10:
        raise HTTPException(status_code=400, detail="description must be at least 10 characters")
    priority = req.priority if req.priority in {"Low", "Medium", "High"} else "Medium"
    try:
        new_case = api_app.state.sf.create_case(
            subject=subject,
            description=description,
            priority=priority,
            origin="Web",
            supplied_name=(req.name or "").strip(),
            supplied_email=(req.email or "").strip(),
            type_=(req.type or "").strip() or None,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to create case: {exc}")
    return JSONResponse({
        "ok": True,
        "case_id": new_case.get("Id"),
        "case_number": new_case.get("CaseNumber"),
        "status": new_case.get("Status", "New"),
    })


@api_app.get("/api/cases")
def list_cases() -> JSONResponse:
    cases = api_app.state.sf.list_open_cases(limit=20)
    enriched = []
    for c in cases:
        g = for_case(c["Id"])
        enriched.append({
            **c,
            "golden": {
                "expected_intent": g.expected_intent if g else None,
                "expected_articles": g.expected_articles if g else [],
                "should_escalate": g.should_escalate if g else None,
                "note": g.note if g else "",
            } if g else None,
        })
    return JSONResponse(
        {
            "mode": {
                "salesforce": api_app.state.sf.mode,
                "confluence": api_app.state.kb.mode,
                "model": settings.anthropic_model,
                "require_human_approval": settings.require_human_approval,
            },
            "cases": enriched,
        }
    )


@api_app.get("/api/case/{case_id}/history")
def case_history(case_id: str) -> JSONResponse:
    try:
        data = api_app.state.sf.get_case_history(case_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(data)


@api_app.get("/api/unlock-status")
def unlock_status() -> JSONResponse:
    """Tell the UI whether a password is required."""
    return JSONResponse({"locked": _password_required()})


class UnlockRequest(BaseModel):
    password: str


@api_app.post("/api/unlock")
def unlock(req: UnlockRequest) -> JSONResponse:
    """Exchange a correct password for a session token."""
    if not _password_required():
        return JSONResponse({"unlocked": True, "token": ""})
    # Constant-time compare to keep brute-force attacks from leaking timing info.
    if not secrets.compare_digest(req.password.strip(), settings.demo_password):
        raise HTTPException(status_code=401, detail="invalid password")
    token = secrets.token_urlsafe(32)
    _demo_tokens[token] = time.time() + settings.demo_token_ttl_hours * 3600
    return JSONResponse({"unlocked": True, "token": token, "ttl_hours": settings.demo_token_ttl_hours})


@api_app.post("/api/slack/interactivity")
async def slack_interactivity(request: Request) -> JSONResponse:
    """Slack POSTs here when a user clicks Approve or Reject. Must respond
    within 3 s with HTTP 200 or Slack shows the user an error."""
    raw_body = await request.body()
    timestamp = request.headers.get("x-slack-request-timestamp") or request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("x-slack-signature") or request.headers.get("X-Slack-Signature", "")

    slack: SlackTool = api_app.state.slack
    if not slack.verify_signature(timestamp, signature, raw_body):
        raise HTTPException(status_code=401, detail="invalid slack signature")

    # Slack sends application/x-www-form-urlencoded with a `payload` field.
    form = await request.form()
    payload_str = form.get("payload", "")
    payload = SlackTool.parse_interaction(str(payload_str) if payload_str else "")
    if not payload:
        return JSONResponse({"ok": True})

    actions = payload.get("actions") or []
    if not actions:
        return JSONResponse({"ok": True})

    action = actions[0]
    try:
        action_value = json.loads(action.get("value") or "{}")
    except json.JSONDecodeError:
        return JSONResponse({"ok": True})

    approval_id = action_value.get("approval_id")
    decision_str = action_value.get("decision")
    if not approval_id or decision_str not in {"approved", "rejected"}:
        return JSONResponse({"ok": True})

    user = payload.get("user") or {}
    decision = ApprovalDecision(
        status=decision_str,
        user_id=user.get("id", ""),
        user_name=user.get("username") or user.get("name") or "",
    )

    fut = _pending_approvals.get(approval_id)

    # Update the original Slack message so the buttons can't be re-clicked.
    container = payload.get("container") or {}
    message = payload.get("message") or {}
    case_number = ""
    for block in (message.get("blocks") or []):
        if block.get("type") == "header":
            header_text = (block.get("text") or {}).get("text", "")
            if "Case" in header_text:
                case_number = header_text.split("Case", 1)[-1].strip().split()[0]
                break
    channel_id = container.get("channel_id") or (payload.get("channel") or {}).get("id", "")
    message_ts = container.get("message_ts") or message.get("ts", "")

    if fut and not fut.done():
        fut.set_result(decision)
        if channel_id and message_ts:
            asyncio.create_task(slack.update_with_decision(channel_id, message_ts, case_number, decision))
    else:
        # Orphaned approval — the run that posted this message is no longer
        # active (server restart, timeout already fired, or duplicate click).
        # Make this visible in Slack instead of silently no-op'ing.
        if channel_id and message_ts:
            async def _mark_orphan():
                import httpx as _httpx
                async with _httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{slack.SLACK_API if hasattr(slack, 'SLACK_API') else 'https://slack.com/api'}/chat.update",
                        headers={
                            "Authorization": f"Bearer {slack.bot_token}",
                            "Content-Type": "application/json; charset=utf-8",
                        },
                        json={
                            "channel": channel_id,
                            "ts": message_ts,
                            "text": "This approval is no longer active (the agent run has ended).",
                            "blocks": [{
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": (
                                        ":information_source: *This approval is no longer active.* "
                                        "The agent run has ended (server restart, timeout, or already decided). "
                                        "Start a new run in the demo UI to get a fresh approval prompt."
                                    ),
                                },
                            }],
                        },
                    )
            asyncio.create_task(_mark_orphan())

    return JSONResponse({"ok": True})


@api_app.get("/api/unlock-verify")
def unlock_verify(request: Request) -> JSONResponse:
    """Lets the UI check whether a cached token is still valid (e.g. after reload)."""
    if not _password_required():
        return JSONResponse({"valid": True})
    token = request.headers.get("x-demo-token") or request.headers.get("X-Demo-Token")
    return JSONResponse({"valid": _is_token_valid(token)})


class RunRequest(BaseModel):
    case_id: str


@api_app.post("/api/run")
async def start_run(req: RunRequest, request: Request) -> JSONResponse:
    _require_unlock(request)
    if api_app.state.orchestrator is None:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY is not set. Copy .env.example to .env and set it.",
        )
    session_id = uuid.uuid4().hex[:12]
    queue: asyncio.Queue = asyncio.Queue()
    _sessions[session_id] = {"queue": queue, "done": False}

    async def emit(event: str, data: dict) -> None:
        await queue.put({"event": event, "data": data})

    async def runner() -> None:
        try:
            await api_app.state.orchestrator.run(req.case_id, emit)
        except Exception as exc:  # noqa: BLE001
            await emit("error", {"message": str(exc)})
        finally:
            _sessions[session_id]["done"] = True
            await queue.put(None)

    asyncio.create_task(runner())
    return JSONResponse({"session_id": session_id})


@api_app.get("/api/stream/{session_id}")
async def stream(session_id: str) -> EventSourceResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Unknown session")
    queue: asyncio.Queue = _sessions[session_id]["queue"]

    async def event_gen():
        while True:
            item = await queue.get()
            if item is None:
                yield {"event": "end", "data": "{}"}
                break
            yield {"event": item["event"], "data": json.dumps(item["data"], default=str)}

    return EventSourceResponse(event_gen())


# ---- outer app: mount api_app at BOTH the production prefix and the root
# so the same code serves agents.vikramvunduru.com/case-triage-agent/ (via
# Cloudflare Tunnel) AND http://127.0.0.1:8000/ (for local development).
if ROUTE_PREFIX:
    outer = FastAPI(title="Agents Hub", lifespan=lifespan)

    @outer.get(ROUTE_PREFIX)
    def _redirect_to_slash():
        # Visitors that hit /case-triage-agent (no trailing slash) need a
        # trailing slash so the HTML's relative asset URLs resolve correctly.
        return RedirectResponse(url=f"{ROUTE_PREFIX}/")

    @outer.get("/support")
    @outer.get("/support/")
    def _redirect_support_to_prefix():
        # Canonical portal URL is /case-triage-agent/support so it sits
        # under the agent demo path. Anyone hitting bare /support is
        # bounced there so the URL bar always shows the canonical form.
        return RedirectResponse(url=f"{ROUTE_PREFIX}/support")

    # Production: agents.vikramvunduru.com/case-triage-agent/...
    outer.mount(ROUTE_PREFIX, api_app)
    # Local dev: http://127.0.0.1:8000/...  (same routes, served at the root)
    outer.mount("/", api_app)

    app = outer
else:
    app = api_app
