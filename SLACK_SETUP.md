# Slack approval gate — setup

The agent pauses on **sensitive cases** (refunds, outages, anything Triage flags as high-risk) and posts an interactive **Approve / Reject** message to a Slack channel. A human clicks a button; the agent resumes:

- **Approve** → Action Agent processes the case with a pre-approved acknowledgment, audit-trails the approver's identity to Chatter.
- **Reject** → Escalation Agent escalates with the rejection reason.
- **Timeout** (10 min default) → Escalation Agent escalates with the timeout reason.

The feature is opt-in. If `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` / `SLACK_APPROVAL_CHANNEL_ID` aren't set, the orchestrator falls back to direct escalation (the original behavior). No code path breaks.

---

## One-time Slack setup (~5 min)

### 1. Create a Slack App

1. Go to <https://api.slack.com/apps> → **Create New App** → **From scratch**.
2. **App Name:** `Case Triage Approver`
3. **Workspace:** pick the one you want approvals to land in.
4. **Create App**.

### 2. Add bot scopes

1. Left menu → **OAuth & Permissions**.
2. Scroll to **Scopes** → **Bot Token Scopes** → **Add an OAuth Scope**.
3. Add: **`chat:write`** (that's it — one scope is enough).
4. Scroll up → **Install to Workspace** → **Allow**.
5. Copy the **Bot User OAuth Token** (starts with `xoxb-…`). This is `SLACK_BOT_TOKEN`.

### 3. Grab the signing secret

1. Left menu → **Basic Information** → scroll to **App Credentials**.
2. **Signing Secret** → click **Show** → copy. This is `SLACK_SIGNING_SECRET`.

### 4. Enable Interactivity

1. Left menu → **Interactivity & Shortcuts**.
2. Toggle **Interactivity** on.
3. **Request URL:**
   ```
   https://agents.vikramvunduru.com/case-triage-agent/api/slack/interactivity
   ```
   *(For local testing without Cloudflare, you can use the same URL — Slack will reach the tunnel and the tunnel forwards to your laptop. If you want a localhost-only test, point this at an ngrok tunnel instead.)*
4. **Save Changes**.

### 5. Create a channel + invite the bot

1. In Slack, create a channel — e.g. `#agent-approvals`. Public or private both work.
2. Invite the bot: in the channel, type `/invite @Case Triage Approver` and hit enter.
3. Get the **channel ID:** right-click the channel name → **View channel details** → scroll to the very bottom; the ID is shown as **Channel ID** (starts with `C…`). Copy it. This is `SLACK_APPROVAL_CHANNEL_ID`.

### 6. Put the three values in `.env`

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APPROVAL_CHANNEL_ID=C...
SLACK_APPROVAL_TIMEOUT_SECONDS=600   # optional, default 10 min
```

### 7. Restart uvicorn

```bash
lsof -ti:8000 | xargs kill 2>/dev/null
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8000
```

(Leave `cloudflared` running — it doesn't care about app restarts.)

---

## How to demo it

1. Open <https://agents.vikramvunduru.com/case-triage-agent/>.
2. Unlock the demo with your password.
3. Pick **Case 00001031 — Need a refund for our annual subscription** (or any refund / high-risk case).
4. Click **Run pipeline**.

What you'll see in the UI:

- Input guardrails → Orchestrator → Triage all light up green.
- The new **Slack approval** node turns **amber and pulses** with *"Awaiting Slack approval…"*.

Meanwhile in `#agent-approvals`:

- A message appears with case context, triage classification, the customer message, and two buttons: **Approve · auto-process** and **Reject · escalate**.

Click one:

- **Approve** → Slack message edits to *"Approved by @you at …"*. Back in the demo UI, the approval node turns green, then the **Action Agent** activates and writes back to Salesforce (Chatter audit + customer comment + status). The internal Chatter note explicitly mentions the approver's name.
- **Reject** → Slack message edits to *"Rejected by @you. Case … was escalated."*. Demo UI marks the approval node yellow and routes to **Escalation Agent** with the rejection as the reason.
- **Wait 10 min** → message edits to *"Timed out — escalated to human queue."* and the demo escalates with the timeout reason.

---

## Security

- Every callback from Slack to `/api/slack/interactivity` is **HMAC-verified** with the signing secret. Forged callbacks return 401.
- Approval IDs are 16-byte random tokens; an attacker can't guess a pending approval ID.
- Pending approvals are kept in process memory — a server restart cancels any pending one (the user clicking after restart gets nothing; the original run timed out and escalated).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Bot posts but buttons do nothing | Interactivity URL not set, or signing secret wrong | Verify URL is exactly `https://agents.vikramvunduru.com/case-triage-agent/api/slack/interactivity` and `SLACK_SIGNING_SECRET` matches **Basic Information → Signing Secret** |
| Bot doesn't post at all | Bot not in channel, or wrong channel id, or missing `chat:write` scope | `/invite @Case Triage Approver` in the channel; double-check `SLACK_APPROVAL_CHANNEL_ID` starts with `C…`; reinstall the app if you added the scope after install |
| 401 from `/api/slack/interactivity` | Signing secret mismatch | Re-copy from Basic Information; restart uvicorn |
| Run never escalates after 10 min | Browser closed the SSE stream | The orchestrator still completes server-side; the case in Salesforce is updated correctly — only the live diagram missed the update. Refresh the page; the case-history panel will show the result |
| Buttons keep firing on the same message | Slack retries on 3+ sec response | Our handler is fire-and-forget on the message-update — should respond in <100 ms |
