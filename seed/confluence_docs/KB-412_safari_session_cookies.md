# KB-412: Session Cookie Issues on Safari (and Strict Privacy Browsers)

**Category:** Authentication & Access
**Audience:** Tier 1 support, Web frontend team
**Last reviewed:** 2026-02-22
**Owner:** Identity Platform Team

## Symptoms

- User signs in successfully but is logged out within seconds.
- User cannot stay logged in across tabs.
- Specific to Safari, Brave, or Firefox with Enhanced Tracking Protection enabled.

## Root cause

Safari's Intelligent Tracking Prevention (ITP) and similar features in Brave/Firefox treat our auth subdomain (`auth.example.com`) as a third-party tracker because it differs from the app subdomain (`app.example.com`). The session cookie is dropped between redirects.

## Resolution steps

1. Ask the user to enable "Allow cross-site tracking" for the domain (Safari: Preferences → Privacy → uncheck "Prevent cross-site tracking" — note this is org-wide, not per-domain in Safari 17+).
2. As a workaround, ask the user to add the domain to the trusted sites in their browser if available.
3. Recommend using Chrome or Edge for sustained sessions until the first-party redirect migration is complete (Q3 2026 roadmap).

## When to escalate

- The user cannot change browser settings (managed corporate device).
- The user is on Safari iOS where the cross-site tracking toggle does not exist.

## Related articles

- KB-247 (Invalid credentials after password reset)
