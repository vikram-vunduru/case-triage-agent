const $ = (sel) => document.querySelector(sel);

const NODE_IDS = [
  "input_guardrails", "orchestrator", "triage", "investigator", "resolver",
  "output_guardrails", "critic", "trust_gate", "action", "escalation", "output",
];

const nodeEl = (id) => document.querySelector(`[data-node="${id}"]`);
const subEl  = (id) => document.querySelector(`[data-sub="${id}"]`);
const outEl  = (id) => document.querySelector(`[data-out="${id}"]`);

let CASES = [];
let MODE = { salesforce: "?", confluence: "?", model: "?" };

document.addEventListener("DOMContentLoaded", async () => {
  resetDiagram();
  await loadCases();
  bindUI();
});

function bindUI() {
  $("#run-btn").addEventListener("click", runAgent);
  $("#clear-btn").addEventListener("click", clearAll);
  $("#case-select").addEventListener("change", showCasePreview);
}

function clearAll() {
  resetDiagram();
  $("#trace").innerHTML = "";
  $("#final").hidden = true;
  $("#evals").hidden = true;
  $("#trace-meta").textContent = "";
  $("#evals-overall").textContent = "";
  $("#eval-grid").innerHTML = "";
}

async function loadCases() {
  try {
    const res = await fetch("api/cases");
    if (!res.ok) throw new Error("Failed to load cases");
    const data = await res.json();
    CASES = data.cases;
    MODE = data.mode;
    populateCaseSelect(CASES);
    showCasePreview();
    const approval = MODE.require_human_approval ? " · approval=on" : "";
    const modeStr = `SF ${MODE.salesforce} · KB ${MODE.confluence} · ${MODE.model}${approval}`;
    $("#mode-text").textContent = modeStr;
    $("#mode-detail").textContent = modeStr;
  } catch (err) {
    $("#mode-text").textContent = "offline";
    $("#case-preview").textContent = "Could not load cases: " + err.message;
  }
}

function populateCaseSelect(cases) {
  const sel = $("#case-select");
  sel.innerHTML = "";
  for (const c of cases) {
    const opt = document.createElement("option");
    opt.value = c.Id;
    opt.textContent = `${c.CaseNumber} — ${c.Subject}`;
    sel.appendChild(opt);
  }
}

function showCasePreview() {
  const id = $("#case-select").value;
  const c = CASES.find(x => x.Id === id);
  if (!c) { $("#case-preview").textContent = ""; $("#prior-run").hidden = true; return; }
  const note = c.golden ? `<div class="cp-note">golden: ${escapeHtml(c.golden.note)}</div>` : "";

  // Initial render with what we have from /api/cases — enriched details come in
  // from loadPriorRun() which calls /api/case/{id}/history.
  $("#case-preview").innerHTML = `
    <div class="cp-header">
      <span class="cp-number">${escapeHtml(c.CaseNumber)}</span>
      <span class="cp-id">${escapeHtml(c.Id)}</span>
    </div>
    <div class="cp-tags">
      <span class="cp-tag prio-${escapeHtml((c.Priority || "").toLowerCase())}">Priority: ${escapeHtml(c.Priority)}</span>
      <span class="cp-tag" id="cp-status">Status: ${escapeHtml(c.Status)}</span>
      <span class="cp-tag" id="cp-origin" hidden></span>
      <span class="cp-tag" id="cp-type" hidden></span>
    </div>
    <div class="cp-subject"><span class="cp-label">Subject</span><span>${escapeHtml(c.Subject)}</span></div>
    <div class="cp-meta" id="cp-meta" hidden>
      <div><span class="cp-label">Account</span><span id="cp-account">—</span></div>
      <div><span class="cp-label">Contact</span><span id="cp-contact">—</span></div>
      <div><span class="cp-label">Created</span><span id="cp-created">—</span></div>
      <div><span class="cp-label">Owner</span><span id="cp-owner">—</span></div>
    </div>
    <div class="cp-desc" id="cp-desc-wrap" hidden>
      <div class="cp-label">Description (customer's message)</div>
      <div class="cp-desc-body" id="cp-description"></div>
    </div>
    ${note}
  `;
  loadPriorRun(id);
}

async function loadPriorRun(caseId) {
  const panel = $("#prior-run");
  panel.hidden = true;
  $("#prior-comment-section").hidden = true;
  $("#prior-chatter-section").hidden = true;

  try {
    const res = await fetch(`api/case/${encodeURIComponent(caseId)}/history`);
    if (!res.ok) return;
    const h = await res.json();

    const case_ = h.case || {};
    const statusNow = case_.Status;
    const comments = h.comments || [];
    const chatter = h.chatter || [];

    // ----- enrich the case preview with the fields only the history endpoint has
    if (statusNow && $("#cp-status")) {
      $("#cp-status").textContent = `Status: ${statusNow}`;
    }
    if (case_.Origin) {
      const el = $("#cp-origin");
      el.textContent = `Origin: ${case_.Origin}`;
      el.hidden = false;
    }
    if (case_.Type) {
      const el = $("#cp-type");
      el.textContent = `Type: ${case_.Type}`;
      el.hidden = false;
    }

    const accountName = (case_.Account && case_.Account.Name) || case_.AccountId || "—";
    const contactName = (case_.Contact && case_.Contact.Name) || case_.ContactId || "—";
    const contactEmail = case_.Contact && case_.Contact.Email;
    const ownerName = (case_.Owner && case_.Owner.Name) || case_.OwnerId || "—";

    $("#cp-account").textContent = accountName;
    $("#cp-contact").textContent = contactEmail ? `${contactName} · ${contactEmail}` : contactName;
    $("#cp-created").textContent = case_.CreatedDate ? formatTs(case_.CreatedDate) : "—";
    $("#cp-owner").textContent = ownerName;
    $("#cp-meta").hidden = false;

    if (case_.Description) {
      $("#cp-description").textContent = case_.Description;
      $("#cp-desc-wrap").hidden = false;
    }

    // ----- "previously processed" panel below the preview
    const wasTouched =
      (statusNow && statusNow !== "New") ||
      comments.length > 0 ||
      chatter.length > 0;
    if (!wasTouched) return;

    panel.hidden = false;
    const lastMod = h.case && (h.case.LastModifiedDate || h.case.LastModifiedById);
    const bits = [];
    if (statusNow && statusNow !== "New") bits.push(`status: ${statusNow}`);
    if (comments.length) bits.push(`${comments.length} comment${comments.length === 1 ? "" : "s"}`);
    if (chatter.length) bits.push(`${chatter.length} chatter post${chatter.length === 1 ? "" : "s"}`);
    if (lastMod) bits.push(`updated ${formatTs(lastMod)}`);
    $("#prior-meta").textContent = bits.join(" · ");

    if (comments.length) {
      const c0 = comments[0];
      const body = c0.CommentBody || c0.text || "";
      $("#prior-comment").textContent = body;
      $("#prior-comment-section").hidden = !body;
    }
    if (chatter.length) {
      const f0 = chatter[0];
      const body = f0.Body || "";
      $("#prior-chatter").textContent = body;
      $("#prior-chatter-section").hidden = !body;
    }
  } catch {
    // history is supplementary — silently ignore failures
  }
}

function formatTs(ts) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString();
  } catch { return ts; }
}

// ---------- diagram state ----------
function resetDiagram() {
  document.querySelectorAll("[data-node]").forEach(el => {
    el.classList.remove("active", "done", "warn", "error");
  });
  document.querySelectorAll(".check").forEach(el => {
    el.classList.remove("pass", "warn", "fail");
  });
  for (const id of NODE_IDS) {
    const sub = subEl(id);
    if (sub && sub.dataset.default) sub.textContent = sub.dataset.default;
    const out = outEl(id);
    if (out) out.textContent = "Waiting";
  }
}

function setNode(id, state, info) {
  const el = nodeEl(id);
  if (!el) return;
  el.classList.remove("active", "done", "warn", "error");
  if (state) el.classList.add(state);
  if (info !== undefined) {
    const out = outEl(id);
    if (out) out.textContent = info;
    const sub = subEl(id);
    if (sub) sub.textContent = info;
  }
}

function setCheck(checkName, state, detail) {
  const el = document.querySelector(`.check[data-check="${checkName}"]`);
  if (!el) return;
  el.classList.remove("pass", "warn", "fail");
  if (state) el.classList.add(state);
  if (detail) el.title = detail;
}

// ---------- run + stream ----------
async function runAgent() {
  const caseId = $("#case-select").value;
  if (!caseId) return;

  clearAll();
  setNode("orchestrator", "active");
  $("#run-btn").disabled = true;
  $("#run-btn").textContent = "Running…";

  const startedAt = performance.now();
  let toolCount = 0;
  let agentCount = 0;
  let tokens = { input: 0, output: 0 };

  try {
    const res = await fetch("api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: caseId }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail || "Failed to start run");
    }
    const { session_id } = await res.json();
    const stream = new EventSource(`api/stream/${session_id}`);

    const handlers = {
      session_start: (d) => {
        addTrace("session", `pipeline=${(d.pipeline || []).length} stages · ${d.model}`, "ok");
      },
      stage_enter: (d) => {
        setNode(d.node, "active", d.label);
      },
      stage_exit: (d) => {
        const state = d.status === "error" ? "error" : d.status === "warn" ? "warn" : "done";
        setNode(d.node, state, d.summary);
        if (d.summary) addTrace(d.node, d.summary, "guard");
      },
      guardrail_check: (d) => {
        setCheck(d.name, d.status, d.details);
        const cat = d.status === "fail" ? "error" : d.status === "warn" ? "guard" : "ok";
        addTrace(`${d.phase}:${d.name}`, `${d.label} · ${d.status} · ${d.details || ""}`, cat);
      },
      agent_start: (d) => {
        agentCount++;
        setNode(d.node, "active", `running…`);
        addTrace(d.agent, "agent_start", "agent");
      },
      agent_end: (d) => {
        setNode(d.node, "done", d.output_summary || `${d.duration_ms}ms`);
        tokens.input += d.input_tokens || 0;
        tokens.output += d.output_tokens || 0;
        addTrace(d.agent, `done · ${d.duration_ms}ms · ${d.output_summary || ""}`, "agent");
      },
      agent_error: (d) => {
        setNode(d.node, "error", `error: ${(d.message || "").slice(0, 60)}`);
        addTrace(d.agent || "agent", `error: ${d.message}`, "error");
      },
      tool_start: (d) => {
        addTrace(`${d.agent}/${d.tool_name}`, prettyArgs(d.args), "tool");
      },
      tool_end: (d) => {
        toolCount++;
        const cat = d.status === "error" ? "error" : "ok";
        addTrace(`${d.agent}/${d.tool_name}`, `${d.preview || d.status} · ${d.duration_ms}ms`, cat);
      },
      eval_score: (d) => {
        renderEvalCard(d);
      },
      log: (d) => addTrace("log", d.text || "", "ok"),
      error: (d) => {
        addTrace("error", d.message || "unknown error", "error");
      },
      final: (d) => {
        renderFinal(d);
      },
      done: (d) => {
        const total = ((performance.now() - startedAt) / 1000).toFixed(1);
        $("#trace-meta").textContent =
          `${agentCount} agents · ${toolCount} tool calls · ${total}s · ${tokens.input}/${tokens.output} tok`;
      },
      end: () => {
        stream.close();
        $("#run-btn").disabled = false;
        $("#run-btn").textContent = "Run pipeline";
      },
    };

    for (const [evt, handler] of Object.entries(handlers)) {
      stream.addEventListener(evt, (e) => {
        let data = {};
        try { data = e.data ? JSON.parse(e.data) : {}; } catch {}
        handler(data);
      });
    }
    stream.onerror = () => {
      stream.close();
      $("#run-btn").disabled = false;
      $("#run-btn").textContent = "Run pipeline";
    };
  } catch (err) {
    addTrace("error", err.message, "error");
    $("#run-btn").disabled = false;
    $("#run-btn").textContent = "Run pipeline";
  }
}

// ---------- trace + finals ----------
function addTrace(category, text, cat = "ok") {
  const li = document.createElement("li");
  const ts = new Date();
  const hh = String(ts.getHours()).padStart(2, "0");
  const mm = String(ts.getMinutes()).padStart(2, "0");
  const ss = String(ts.getSeconds()).padStart(2, "0");
  // Show full category on hover since it can be longer than the column width.
  li.innerHTML = `
    <span class="tcat ${cat}" title="${escapeHtml(category)}">${escapeHtml(category)}</span>
    <span class="tbody" title="${escapeHtml(text)}">${escapeHtml(text)}</span>
    <span class="tmeta">${hh}:${mm}:${ss}</span>
  `;
  $("#trace").appendChild(li);
  $("#trace").scrollTop = $("#trace").scrollHeight;
}

function renderFinal(d) {
  $("#final").hidden = false;
  const conf = d.confidence != null ? `${Math.round(d.confidence * 100)}%` : "—";
  const goodConf = d.confidence != null && d.confidence >= 0.75;
  setBadge("#final-conf", `confidence: ${conf}`,
    goodConf ? "good" : (d.confidence != null && d.confidence < 0.6 ? "bad" : "warn"));
  setBadge("#final-actions", `actions: ${(d.actions_taken || []).join(", ") || "none"}`, "good");
  setBadge("#final-escalated", `escalated: ${d.escalated ? "yes" : "no"}`, d.escalated ? "warn" : "good");
  const cs = d.critic_scores;
  const overall = cs && cs.overall != null ? `${(cs.overall * 100).toFixed(0)}%` : "—";
  setBadge("#final-gate", `critic: ${overall}`,
    cs && cs.passed ? "good" : "warn");

  $("#final-body").textContent = d.resolution || "(no resolution returned)";
  const cites = (d.citations || []).map(c => `<span class="citation">${escapeHtml(c)}</span>`).join("");
  $("#final-citations").innerHTML = cites;
}

function setBadge(sel, text, cls) {
  const el = $(sel);
  el.textContent = text;
  el.classList.remove("good", "warn", "bad");
  if (cls) el.classList.add(cls);
}

function renderEvalCard(d) {
  $("#evals").hidden = false;
  const grid = $("#eval-grid");
  const pct = Math.max(0, Math.min(100, Math.round(d.score * 100)));
  const id = `eval-${d.name}`;
  let card = document.getElementById(id);
  if (!card) {
    card = document.createElement("div");
    card.id = id;
    card.className = "eval-card";
    card.innerHTML = `
      <div class="eval-name">${escapeHtml(d.label)}</div>
      <div class="eval-bar-wrap"><div class="eval-bar" style="width:0%"></div></div>
      <div class="eval-meta">
        <span class="eval-detail"></span>
        <span class="eval-score"></span>
      </div>
    `;
    grid.appendChild(card);
  }
  card.classList.remove("pass", "warn", "fail");
  card.classList.add(d.status);
  card.querySelector(".eval-bar").style.width = `${pct}%`;
  card.querySelector(".eval-detail").textContent = d.detail || "";
  card.querySelector(".eval-score").textContent = `${pct}%`;
  // Compute and display overall
  const cards = grid.querySelectorAll(".eval-card");
  let sum = 0, n = 0;
  cards.forEach(c => {
    const s = parseInt(c.querySelector(".eval-score").textContent, 10);
    if (!isNaN(s)) { sum += s; n++; }
  });
  const failures = grid.querySelectorAll(".eval-card.fail").length;
  $("#evals-overall").textContent = n ? `· overall ${Math.round(sum / n)}% · ${failures} fail` : "";
}

function prettyArgs(args) {
  if (!args) return "";
  try {
    const s = JSON.stringify(args);
    return s.length > 90 ? s.slice(0, 87) + "…" : s;
  } catch { return ""; }
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
