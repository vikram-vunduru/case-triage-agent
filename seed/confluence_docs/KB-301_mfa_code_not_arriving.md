# KB-301: MFA Code Not Arriving

**Category:** Authentication & Access
**Audience:** End users, Tier 1 support
**Last reviewed:** 2026-03-30
**Owner:** Identity Platform Team

## Symptoms

- User receives the "Enter verification code" prompt during login.
- SMS or email verification code is delayed by more than 90 seconds, or never arrives.
- User has tried "Resend code" two or more times without success.

## Root cause

Three common causes, in order of frequency:

1. The user's MFA delivery channel (phone number / email) on file is outdated.
2. The user is on a corporate network that quarantines short codes through the SMS gateway.
3. The user has hit the rate limit (more than 5 code requests in 10 minutes), which puts them in a 15-minute backoff.

## Resolution steps

1. Verify the MFA delivery channel on file under the user's profile (`/users/me/mfa`). If the phone or email is wrong, update it.
2. Have the user try the backup authenticator app option (TOTP) if enrolled.
3. If on the corporate network, ask them to switch to a personal device on cellular to bypass the SMS gateway.
4. If rate-limited, wait 15 minutes and retry. Do not bypass the limit — it is in place for security.
5. If still failing, generate a one-time bypass code via the admin console.

## When to escalate

- User is not enrolled in any backup method.
- Rate-limit backoff has expired but codes still don't arrive.
- Suspected SIM-swap or account takeover (user reports unexpected MFA prompts).

## Related articles

- KB-247 (Invalid credentials after password reset)
- KB-356 (Account lockout recovery)
