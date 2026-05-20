# KB-356: Account Lockout Recovery

**Category:** Authentication & Access
**Audience:** End users, Tier 1 support
**Last reviewed:** 2026-04-05
**Owner:** Identity Platform Team

## Symptoms

- User sees "Your account has been temporarily locked" message.
- Login attempts return immediately without prompting for password.
- Sometimes a `429` is visible in the browser dev console.

## Root cause

Five failed password attempts within 10 minutes triggers a 30-minute lockout. This is intentional brute-force protection and is enforced at the identity gateway.

## Resolution steps

1. Confirm with the user that they were the source of the failed attempts (rule out account takeover).
2. If yes and the user remembers their password: ask them to wait 30 minutes and try again. Do not bypass the lockout.
3. If the user does not remember their password: have them complete the password reset flow (KB-247 covers the post-reset issues).
4. If account takeover is suspected: trigger the "Force password reset + invalidate all sessions" admin action and notify the security team.

## When to escalate

- Account takeover suspected.
- Lockout occurs repeatedly even after a successful reset (indicates a compromised session token).
- User is a privileged admin — privileged-account lockouts should always be reviewed by Tier 2.

## Related articles

- KB-247 (Invalid credentials after password reset)
- KB-301 (MFA code not arriving)
