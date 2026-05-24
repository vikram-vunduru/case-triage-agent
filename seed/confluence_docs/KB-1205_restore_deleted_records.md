# KB-1205: Restoring Deleted Records

**Category:** Data Recovery — High-risk procedure
**Audience:** Support agents (Tier 1, Tier 2), Account Admins
**Last reviewed:** 2026-04-18
**Owner:** Data Operations

## ⚠️ Policy — read first

**Never restore a deleted record without explicit owner confirmation.** The Account Admin (not the requesting user) must approve every restoration request, even if the requester says it was their record.

This is enforced because:

- Restorations can re-introduce data that was deliberately deleted for compliance reasons (GDPR right-to-erasure, expired retention, etc.).
- A restored record overwrites any changes made by other users after the deletion.
- Audit logs of who deleted, restored, and re-modified records become tangled — making downstream incident response harder.

## Symptoms

A customer reports any of:

- "I accidentally deleted [X] yesterday and need it back."
- "Our integration deleted records it wasn't supposed to."
- "A team member deleted important records before leaving the company."
- "We need to restore everything that was deleted between [date] and [date]."

## Recovery window

Deleted records are retained in our soft-delete store for **30 days**. After 30 days they are purged from backups and cannot be recovered by any means.

| Time since deletion | Recoverable? |
|---|---|
| 0 – 30 days | Yes, with Account Admin approval |
| 31 – 90 days | Only from cold backup; requires Director sign-off; 5-business-day SLA |
| > 90 days | **Not recoverable.** |

## Required information before escalation

Collect from the customer before routing:

1. **Record type** (e.g. Contact, Opportunity, Custom Object name).
2. **Record IDs** if the customer has them, OR a precise filter (date range + owner + name pattern) if not.
3. **Approximate deletion timestamp** (within a few hours).
4. **Account Admin email** — the person who will approve the restoration.
5. **Reason for restoration** in the customer's words.
6. **Acknowledgement** from the requester that any changes made by other users after the deletion will be lost.

## How to escalate

1. Acknowledge the request and explain that a restoration requires Account Admin approval.
2. Route the case to the **Data Operations** queue with priority based on the size and urgency of the request:
   - < 100 records: P3.
   - 100 – 10,000 records: P2.
   - > 10,000 records or "all data": P1.
3. Include in the handoff: all six items above. Cc the Account Admin email so they receive the request directly.

## Customer-facing language template

> "Thank you for letting us know. Because record restorations are irreversible and can affect other users, our policy requires explicit approval from your Account Admin before we proceed. I've routed your request to our Data Operations team and copied [ADMIN_EMAIL]. Expect to hear from them within [SLA window]. Your reference is Case [CASE_NUMBER]."

## When to escalate

**Always.** Restoration is irreversible from an audit perspective and must be reviewed by a human even for small numbers of records.
