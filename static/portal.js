// Customer-facing support portal — submits a ticket that creates a
// Case in Salesforce via /api/portal/case. No authentication required.

const $ = (sel) => document.querySelector(sel);

document.addEventListener("DOMContentLoaded", () => {
  $("#ticket-form").addEventListener("submit", submitTicket);
  $("#submit-another").addEventListener("click", resetForm);
});

async function submitTicket(event) {
  event.preventDefault();
  hideError();

  const subject = $("#subject").value.trim();
  const description = $("#description").value.trim();
  const name = $("#name").value.trim();
  const email = $("#email").value.trim();
  const priority = $("#priority").value || "Medium";
  const type = $("#type").value || "";

  // Quick client-side validation (server validates again).
  if (!subject || subject.length < 4) {
    fieldError("subject", "Please add a short subject (4+ characters).");
    return;
  }
  if (!description || description.length < 10) {
    fieldError("description", "Please describe the issue in a bit more detail (10+ characters).");
    return;
  }
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    fieldError("email", "Please enter a valid email address.");
    return;
  }

  const submitBtn = $("#submit-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting…";

  try {
    const res = await fetch("api/portal/case", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, description, name, email, priority, type }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: res.statusText }));
      showError(data.detail || "Could not submit your ticket. Please try again.");
      return;
    }
    const data = await res.json();
    showSuccess(data);
  } catch (err) {
    showError("Could not reach the support system. Please check your connection and try again.");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Submit ticket";
  }
}

function showSuccess(data) {
  $("#form-card").hidden = true;
  $("#success-card").hidden = false;
  $("#success-case-number").textContent = data.case_number || data.case_id || "—";
  const meta = [];
  if (data.status) meta.push(`Status: ${data.status}`);
  meta.push(`Created at ${new Date().toLocaleString()}`);
  $("#success-case-meta").textContent = meta.join(" · ");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetForm() {
  $("#ticket-form").reset();
  $("#success-card").hidden = true;
  $("#form-card").hidden = false;
  hideError();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function fieldError(id, message) {
  const el = document.getElementById(id);
  if (el) { el.classList.add("error"); el.focus(); }
  showError(message);
}

function showError(message) {
  const err = $("#form-error");
  err.textContent = message;
  err.hidden = false;
}

function hideError() {
  $("#form-error").hidden = true;
  document.querySelectorAll(".field input.error, .field textarea.error")
    .forEach(el => el.classList.remove("error"));
}
