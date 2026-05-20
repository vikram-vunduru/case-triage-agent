# KB-247: "Invalid Credentials" After a Password Reset

**Category:** Authentication & Access
**Audience:** End users, Tier 1 support
**Last reviewed:** 2026-04-12
**Owner:** Identity Platform Team

## Symptoms

- User completed the password reset flow from the email link.
- The new password works on the mobile app but the web login returns "Invalid credentials" or "Authentication failed".
- The user is sometimes redirected back to the login page silently.

## Root cause

The web session retains stale authentication cookies (`auth_session`, `sf_csrf`) bound to the old password hash. After a reset, the browser's stored cookies cause the auth gateway to attempt token refresh against an invalidated session, which surfaces as "Invalid credentials" even though the new password is correct.

## Resolution steps

1. Ask the user to fully sign out of all web sessions (top-right avatar → Log out).
2. Clear cookies for the domain in the affected browser:
   - Chrome: `chrome://settings/cookies` → search for the domain → Remove all.
   - Safari: Preferences → Privacy → Manage Website Data → search domain → Remove.
   - Firefox: Preferences → Privacy → Cookies and Site Data → Manage Data.
3. Restart the browser.
4. Open a private/incognito window and sign in again with the new password.
5. If the issue persists, confirm the user is on the correct realm (some tenants are on `eu.app.example.com` instead of `app.example.com`).

## When to escalate

Escalate to Tier 2 / Identity Platform if:

- The user has confirmed steps 1-4 and still cannot log in.
- The user is a federated SSO user (SAML/OIDC) — they should not be using the password reset flow.
- The Account is on a custom domain or a sandbox where the cookie clearing must include the sandbox subdomain.

## Related articles

- KB-301 (MFA prompt not arriving)
- KB-356 (Account lockout recovery)
- KB-412 (Session cookie issues on Safari)
