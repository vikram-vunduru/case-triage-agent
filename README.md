# Case Triage Agent

A multi-agent system that triages Salesforce Service Cloud Cases end-to-end. It reads incoming Cases, retrieves matching articles from a Confluence knowledge base, drafts a grounded customer reply, posts an audit trail, updates the Case — and escalates anything risky to a human, with a structured handoff.

Built with Anthropic Claude, FastAPI, real Salesforce REST API (OAuth Client Credentials Flow), and Chroma for local vector search.

---

## What it does

The agent runs every incoming Case through a six-stage pipeline:

1. **Input guardrails** — PII detection, prompt-injection screening, topic-scope check, abuse filter.
2. **Triage agent** — classifies the case by intent (auth issue · billing · feature request · outage · other), risk (low/medium/high), and topic scope.
3. **Investigator agent** — reads the Case + Account + recent related cases from Salesforce, then searches Confluence for matching troubleshooting articles.
4. **Resolver agent** — drafts a grounded customer reply citing the retrieved articles.
5. **Output guardrails** — verifies the draft cites only real retrieved articles (no hallucinated citations), contains no PII leakage, uses professional tone.
6. **Critic agent (LLM-as-judge)** — independently scores the draft on five dimensions.
7. **Trust gate** — combines confidence, critic score, and guardrail results into a single pass/fail policy decision.
8. **Action agent** OR **Escalation agent** — on pass, writes back to Salesforce (Chatter audit + Case comment + status update); on fail, produces a structured human handoff.

Every step is observable via Server-Sent Events to a live UI that visualizes the architecture as the agent runs.

---

## Architecture

```
[ Customer message ]
        ↓
[ Input guardrails ]   PII · Prompt injection · Scope · Abuse
        ↓
[ Orchestrator ]   deterministic Python pipeline
        ↓
[ Triage agent ]   3 classification tools
        ↓
   ┌──── if risk=high OR billing/refund/outage OR out-of-scope ────┐
   ↓                                                                ↓
[ Investigator ]                                              [ Escalation ]
4 read tools (SF + Confluence)                                queue handoff
   ↓
[ Resolver ]   no tools, structured output
   ↓
[ Output guardrails ]   Groundedness · Citations · PII · Tone
   ↓
[ Critic ]   LLM-as-judge, 5 dims
   ↓
[ Trust gate ]   policy combiner
   ↓                  ↓
[ Action ]      [ Escalation ]
2 SF writes      handoff
        ↓
[ Live evals ]   6 dimensions
```

### Design choices

- **Deterministic orchestrator with LLM sub-agents.** The orchestrator is plain Python; routing decisions are auditable. Sub-agents are LLM calls only where reasoning is needed.
- **Scoped tools per agent.** Resolver has zero tools (pure generation). Critic has one (scoring). Action has only two Salesforce writes. Least privilege at the tool level.
- **Separate critic.** A fresh model call without the draft author's context produces a more calibrated score than self-grading.
- **Layered defense.** Input guardrails (deterministic) → tool scoping → output guardrails (deterministic) → critic (semantic) → trust gate (policy). Each layer catches a different failure mode.

---

## Features

- **Multi-agent orchestration** — 6 specialized agents, each with its own scoped tools.
- **Two-layer guardrails** — 4 input checks + 4 output checks, all deterministic and explainable.
- **LLM-as-judge critic** — independent quality scoring on 5 dimensions.
- **Policy-driven trust gate** — combines confidence + critic + guardrails into one pass/fail call.
- **Real Salesforce integration** — OAuth 2.0 Client Credentials Flow against an External Client App.
- **Confluence RAG** — vector search over your knowledge base via local Chroma.
- **Live architecture visualization** — SSE-driven UI shows each pipeline stage activating in real time.
- **Live evals** — 6 metrics (retrieval recall, tool correctness, groundedness, escalation correctness, safety, latency) scored on every run.
- **Offline eval harness** — golden-dataset CLI runner for CI-style regression checks.
- **Case history preview** — when a Case has been processed before, the prior agent activity is shown before re-running.
- **Session auto-refresh** — Salesforce CCF tokens transparently re-fetched on expiry.

---

## Tech stack

| Layer | Tool |
|---|---|
| LLM | Anthropic Claude (default `claude-sonnet-4-6`, configurable) |
| Backend | Python 3.11+ · FastAPI · Uvicorn · sse-starlette |
| Salesforce | `simple-salesforce` over OAuth 2.0 Client Credentials Flow |
| Confluence | `atlassian-python-api` |
| Vector DB | ChromaDB (persistent, local SQLite + HNSW) |
| Embeddings | all-MiniLM-L6-v2 (Chroma default, runs locally via ONNX) |
| Config | `pydantic-settings` with `.env` loading |
| Frontend | Vanilla HTML + CSS + JS — no build step |

---

## Setup

### Prerequisites

- Python 3.11 or later
- An [Anthropic API key](https://console.anthropic.com/)
- A Salesforce Developer Edition org (free at [developer.salesforce.com/signup](https://developer.salesforce.com/signup))
- A Confluence Cloud space (free tier at [atlassian.com](https://www.atlassian.com/software/confluence/free))

### Install

```bash
git clone https://github.com/vikram-vunduru/case-triage-agent.git
cd case-triage-agent

# Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# edit .env — see "Configuration" below
```

### Salesforce — one-time setup

1. **Sign up** for a Salesforce Developer Edition org.
2. **Create an External Client App** at *Setup → External Client App Manager → New*:
   - Enable OAuth.
   - Enable **Client Credentials Flow** under Flow Enablement.
   - Selected OAuth Scopes: `Manage user data via APIs (api)` + `Perform requests at any time (refresh_token, offline_access)`. *Do not select `full` — Client Credentials Flow rejects it.*
   - Callback URL: any HTTPS placeholder (CCF doesn't actually call it).
3. **Configure the app's Policies tab:**
   - Set the **Run-As User** to a Salesforce user with API access.
   - Permitted Users: *All users may self-authorize*.
   - IP Relaxation: *Relax IP restrictions*.
4. **Copy the Consumer Key and Consumer Secret** into `.env` as `SF_CONSUMER_KEY` and `SF_CONSUMER_SECRET`.
5. **Find your My Domain URL** in *Setup → My Domain* and put it in `.env` as `SF_LOGIN_URL`.

### Confluence — one-time setup

1. Create a Confluence Cloud space (e.g. space key `SUP`).
2. Generate an API token at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
3. Set the Confluence variables in `.env`.
4. (Optional) seed the space with the bundled sample knowledge articles:
   ```bash
   python seed/seed_confluence.py
   ```

### Salesforce sample data

To populate your org with sample Cases that match the bundled KB articles:

```bash
python seed/seed_salesforce.py
```

This creates 3 sample Accounts and 6 sample Cases (5 auth-themed + 1 refund) via the OAuth API. Idempotent — safe to re-run.

---

## Configuration

All configuration is via `.env`. See [`.env.example`](.env.example) for the full template.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key |
| `ANTHROPIC_MODEL` | no | `claude-sonnet-4-6` | Claude model to use |
| `SALESFORCE_MODE` | no | `mock` | `mock` uses bundled JSON; `real` connects to Salesforce |
| `SF_CONSUMER_KEY` | if real | — | External Client App consumer key |
| `SF_CONSUMER_SECRET` | if real | — | External Client App consumer secret |
| `SF_LOGIN_URL` | if real | — | Your org's My Domain URL (e.g. `https://orgxxx.my.salesforce.com`) |
| `CONFLUENCE_MODE` | no | `mock` | `mock` uses bundled markdown; `real` syncs from Confluence |
| `CONFLUENCE_URL` | if real | — | e.g. `https://yoursite.atlassian.net/wiki` |
| `CONFLUENCE_USERNAME` | if real | — | Your Atlassian email |
| `CONFLUENCE_API_TOKEN` | if real | — | API token (not your password) |
| `CONFLUENCE_SPACE_KEY` | if real | — | Confluence space key (e.g. `SUP`) |
| `CONFIDENCE_THRESHOLD` | no | `0.6` | Below this, the trust gate escalates |
| `REQUIRE_HUMAN_APPROVAL` | no | `false` | When `true`, every write requires an approval event |
| `ROUTE_PREFIX` | no | empty | When deploying at a subpath (e.g. `/case-triage-agent`) |

---

## Running

### Local development

```bash
# Build the Chroma index from bundled sample KB (mock mode)
python seed/build_index.py

# Start the server
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open <http://127.0.0.1:8000/> in your browser. Pick a case from the dropdown and click **Run pipeline**.

### One-shot script

```bash
./run.sh
```

Creates the venv, installs dependencies, indexes the KB, and starts the server.

### Offline eval harness

```bash
python -m evals.run_evals
```

Runs every case in the golden dataset through the orchestrator and prints a pass/fail matrix per case. Suitable for CI gating.

### Deploying

For deployment behind a path-based reverse proxy (e.g. Cloudflare Tunnel, nginx), set `ROUTE_PREFIX=/your-path` in `.env`. The FastAPI app mounts the inner application at that prefix and serves all assets with relative URLs.

---

## Project structure

```
case_triage_agent/
├── agents/
│   ├── base.py              SubAgent base class with the tool-use loop
│   ├── orchestrator.py      Pipeline runner — coordinates all sub-agents
│   ├── triage.py            Intent / risk / scope classifier
│   ├── investigator.py      Salesforce + Confluence context gatherer
│   ├── resolver.py          Drafts the customer-facing reply
│   ├── critic.py            LLM-as-judge — 5-dim scoring
│   ├── action.py            Salesforce writes (Chatter + Case update)
│   └── escalation.py        Human handoff
├── guardrails/
│   ├── input_guardrails.py  PII · injection · scope · abuse + redact_pii()
│   ├── output_guardrails.py Groundedness · citations · leak · tone
│   └── policy.py            Trust gate combiner
├── evals/
│   ├── scoring.py           6 scoring functions
│   ├── golden.py            Ground-truth expectations
│   └── run_evals.py         Offline eval CLI
├── tools/
│   ├── salesforce_tool.py   OAuth CCF + reads/writes + session retry
│   └── confluence_tool.py   Confluence sync + Chroma query
├── rag/
│   └── chroma_store.py      Chroma persistent index helpers
├── seed/
│   ├── build_index.py       Index bundled markdown into Chroma (mock mode)
│   ├── seed_confluence.py   Push bundled markdown as pages to Confluence
│   ├── seed_salesforce.py   Create sample Accounts + Cases in Salesforce
│   ├── sample_cases.json    Mock-mode case data
│   ├── sample_accounts.json Mock-mode account data
│   └── confluence_docs/     5 markdown knowledge articles
├── static/
│   ├── index.html           Two-panel UI
│   ├── styles.css           Theme
│   └── app.js               SSE client + live architecture diagram
├── app.py                   FastAPI entry point
├── agent.py                 Convenience builder
├── config.py                Pydantic Settings
├── requirements.txt
├── .env.example
└── run.sh                   One-shot setup + start
```

---

## How a request flows through the system

1. UI sends `POST /api/run` with a Case Id.
2. Server creates an SSE session and kicks off `Orchestrator.run(case_id, emit)` in the background.
3. Orchestrator reads the Case from Salesforce to get the customer text.
4. Input guardrails scan the text — emit a `guardrail_check` event per check.
5. If anything fails → orchestrator routes to the Escalation Agent and returns.
6. Triage Agent classifies (3 tool calls inside its loop). If `risk=high` or refund/outage or out-of-scope → orchestrator routes to Escalation.
7. Investigator Agent gathers context (4 tool calls: 3 SF reads + 1 Confluence search).
8. Resolver Agent drafts the reply.
9. Output guardrails scan the draft. Failures → escalation.
10. Critic Agent scores the draft on 5 dimensions.
11. Trust gate combines confidence + critic + guardrails → pass/fail decision.
12. Action Agent (on pass) writes Chatter + updates Case. Escalation Agent (on fail) posts a structured handoff to a queue.
13. Live evals are computed against the golden dataset.
14. UI receives `final` and `done` events; renders the resolution panel and the eval bars.

---

## Extending

### Adding a new sub-agent

1. Create `agents/your_agent.py` extending `SubAgent`.
2. Define `tools_schema`, `system_prompt`, and `execute_tool()`.
3. Add a node id to `static/index.html` matching the agent's `node_id`.
4. Add the node id to `NODE_IDS` in `static/app.js`.
5. Wire it into `agents/orchestrator.py`.

### Adding a new tool

1. Add the method to `SalesforceTool` or `ConfluenceTool`. Wrap Salesforce calls in `self._call()` to inherit session-retry behavior.
2. Define the JSON schema for the tool in the agent that uses it.
3. Add a dispatch case in that agent's `execute_tool()`.

---

## License

MIT
