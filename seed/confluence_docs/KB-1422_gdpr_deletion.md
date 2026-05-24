# KB-1422: GDPR / CCPA Right-to-Erasure and Data-Export Requests

**Category:** Compliance — High-risk procedure
**Audience:** Support agents, Compliance team, Legal
**Last reviewed:** 2026-05-08
**Owner:** Privacy & Compliance

## ⚠️ Policy — read first

**Never process a GDPR right-to-erasure (RTBF) or CCPA delete-my-data request automatically.** Every request must be reviewed by Privacy & Compliance.

This is enforced because:

- The request is **permanent and irreversible**. Once data is purged, there is no recovery path even from backups (we delete from cold backups within 30 days of a verified RTBF request, per our published policy).
- Some customer data is legally required to be retained (e.g. financial records under SOX, dispute records under contract law). Compliance must determine what is actually erasable.
- Acting on a forged request would itself be a regulatory violation.

## Applicable regulations

| Regulation | Region | Response SLA | Notes |
|---|---|---|---|
| GDPR Article 17 (Right to Erasure) | EU + EEA + UK | 30 days from verified request | Can extend by 60 days for complex requests; must notify requester |
| CCPA / CPRA (Right to Delete) | California, USA | 45 days from verified request | Can extend by 45 days |
| LGPD | Brazil | 15 days | Less common but legally binding |
| PIPEDA | Canada | 30 days | Less common but legally binding |

## Symptoms / how requests come in

- "Per GDPR, please delete my account and all associated data."
- "I want to exercise my right to be forgotten."
- "Please send me a copy of all data you have on me, then delete my account."
- "I'm a California resident — delete my data per CCPA."

## Identity verification (mandatory)

Before any action, the requester's identity must be verified:

1. The request must come from the email on file on the account, **or**
2. The requester must respond to a verification email sent to that on-file address, **or**
3. For high-value accounts, two-factor verification including a phone call.

Compliance handles this step. Do **not** attempt to verify identity at the Support tier — incorrect verification creates legal exposure.

## Required information before escalation

Collect from the requester:

1. **Regulation cited** (GDPR / CCPA / other), if specified.
2. **Account email** they want associated with the request.
3. **Whether they also want a data export** before deletion (combined request is common).
4. **Region of residence** (to confirm which regulation applies).

## Approval levels

| Request type | Required approver |
|---|---|
| RTBF on a personal account | Privacy Officer (Compliance team) |
| RTBF on a business account where requester is the admin | Privacy Officer + Legal review |
| Data export only (no deletion) | Privacy Officer; faster path |
| Disputed request (e.g. business account, multiple owners) | Privacy Officer + Legal + Customer Success VP |

## How to escalate

1. Acknowledge receipt of the request. Cite the applicable regulation's SLA so the requester knows you have heard them.
2. Route the case to the **Privacy & Compliance** queue with priority P1 (regulatory SLAs are non-negotiable).
3. Include all four items from "Required information" plus the original message in the customer's own words.

## Customer-facing language template

> "Thank you for your request. We take privacy seriously. Your [GDPR / CCPA / ...] request has been received and routed to our Privacy & Compliance team. They will verify your identity and respond within the [30 / 45]-day regulatory window. Your reference is Case [CASE_NUMBER]. If you would also like a copy of your data before deletion, please confirm — we can include the export in the same response."

## When to escalate

**Always, immediately.** Regulatory deadlines start the moment the request is received. Do not delay routing.
