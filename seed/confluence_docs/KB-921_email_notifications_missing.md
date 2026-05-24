# KB-921: Email Notifications Not Arriving

**Category:** Notifications & Email
**Audience:** End users, Tier 1 support
**Last reviewed:** 2026-05-03
**Owner:** Notification Platform Team

## Symptoms

- User reports they have stopped receiving system emails (daily digest, comment replies, mention notifications, weekly summary).
- Sometimes a subset of notification types still works — e.g. password reset emails arrive, but digest emails don't.
- The user can confirm they were getting the emails before.

## Root cause

Four common causes:

1. **Notification preferences** were silently changed during an account migration or a workspace transfer.
2. **Corporate spam filter** flagged our sender domain after a Microsoft/Google policy update.
3. **Sender domain not in user's allowlist** (`notifications@app.example.com`).
4. **Inbox rule** the user set up months ago is silently moving our emails into Archive or a folder.

## Resolution steps

1. Have the user verify **notification preferences**: Settings → Notifications. Confirm each notification type they expect is enabled and the delivery channel is **Email** (not just In-App).
2. Search the user's mailbox for `from:notifications@app.example.com` over the last 30 days. If results appear, the emails are arriving but being filed elsewhere — check inbox rules and Archive folder.
3. If no results: check the **Spam / Junk** folder explicitly. Mark one of our emails as "Not spam" if found.
4. Have the user **allowlist the sender domain**:
   - Gmail: add a filter for `from:@app.example.com` → "Never send to Spam".
   - Outlook: Settings → Mail → Junk → Safe senders → add `@app.example.com`.
5. Send a **test notification** from Settings → Notifications → Send test email. If the test arrives but real notifications don't, it's a content-based spam filter — escalate.

## When to escalate

Escalate to Notification Platform if:

- All steps above completed and the test email arrives but real notifications don't (content-based spam classifier issue).
- Multiple users in the same domain report the issue simultaneously (sender reputation problem affecting that domain).
- Customer is on a Premier-tier account and has been impacted for more than 24 hours.

## Related articles

- KB-247 (Authentication issues that may block notification delivery for blocked users)
