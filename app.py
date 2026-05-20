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


ROOT = Path(__file__).resolve().parent
# When deployed behind Cloudflare Tunnel at e.g. agents.vikramvunduru.com/case-triage-agent
# set ROUTE_PREFIX=/case-triage-agent in .env. Empty = serve at root (local dev).
ROUTE_PREFIX = settings.route_prefix.rstrip("/")

_sessions: dict[str, dict] = {}

# In-memory unlock-token store. {token: expiry_unix_ts}. Lives until process restart;
# unlocked browsers will re-prompt after a redeploy, which is acceptable for a demo.
_demo_tokens: dict[str, float] = {}


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
    api_app.state.client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
    api_app.state.orchestrator = (
        Orchestrator(api_app.state.client, api_app.state.sf, api_app.state.kb)
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


# ---- outer app: mount api_app under ROUTE_PREFIX when deployed behind a tunnel ----
if ROUTE_PREFIX:
    outer = FastAPI(title="Agents Hub", lifespan=lifespan)
    outer.mount(ROUTE_PREFIX, api_app)

    @outer.get(ROUTE_PREFIX)
    def _redirect_to_slash():
        # Browser visits /case-triage-agent (no trailing slash) — redirect so
        # relative URLs in the served HTML resolve correctly.
        return RedirectResponse(url=f"{ROUTE_PREFIX}/")

    @outer.get("/")
    def _root_index():
        # Friendly landing for anyone hitting the apex of the tunnel hostname.
        return JSONResponse({"agents": [{"path": ROUTE_PREFIX, "name": "Case Triage Multi-Agent"}]})

    app = outer
else:
    app = api_app
