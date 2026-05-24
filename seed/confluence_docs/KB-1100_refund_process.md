# KB-1100: Processing Customer Refund Requests

**Category:** Billing — High-risk procedure
**Audience:** Support agents (Tier 1, Tier 2), Finance team
**Last reviewed:** 2026-05-12
**Owner:** Finance Operations

## ⚠️ Policy — read first

**DO NOT process any refund automatically.** Every refund request must be reviewed by a human and routed through Finance. AI agents and self-service flows are explicitly prohibited from refunding any amount, regardless of size, by Finance policy as of 2026-04-01.

This is a hard rule. The policy exists because:

- Refunds are irreversible from an accounting perspective.
- They reverse the revenue recognition that has already been reported in financial filings.
- Patterns of unauthorized refunds are a known fraud vector.

## Symptoms

The customer asks for any of:

- A full refund of their subscription (annual or monthly).
- A partial refund / credit for downtime or service degradation.
- A refund for an accidental upgrade or duplicate charge.
- A refund following a cancellation that wasn't honored.

## Required information before escalation

The reviewing human will need all of the following. Collect it from the customer before handing off:

1. **Customer email** and **Account ID** (so Finance can locate the original transaction).
2. **Original order or invoice number** (visible to the customer in their billing history).
3. **Reason for the refund request**, in the customer's own words.
4. **Amount requested** (full, partial, or "whatever is fair").
5. **Whether they have cancelled** — refunds without cancellation create accounting complications.

## Approval levels

| Refund amount | Required approver |
|---|---|
| ≤ $500 | Finance Ops on-call (response: same business day) |
| $501 – $10,000 | Finance Manager (response: 1 business day) |
| > $10,000 | Finance Director + Customer Success VP sign-off (response: 2-3 business days) |

## How to escalate

1. Acknowledge the request to the customer politely. Do **not** promise an outcome or a timeline — Finance owns that decision.
2. Route the case to the **Billing** queue with priority equal to the customer's account tier (P1 for Enterprise, P2 for Premier, P3 for Standard).
3. Include in the handoff: all five items from "Required information" above, plus any contextual notes from the conversation.

## Customer-facing language template

> "Thank you for reaching out. I've received your request for a refund of $[AMOUNT] and I've routed it to our Finance team for review. They'll be in touch directly within [SLA window] with next steps. Your reference for this request is Case [CASE_NUMBER] — please use it for any follow-up. I appreciate your patience."

## When to escalate

**Always.** There are no exceptions where a Support agent can process a refund without Finance approval. If the customer is upset and demands immediate resolution, escalate to a Support Manager who can coordinate with Finance on a faster review — but the refund itself still goes through Finance.
