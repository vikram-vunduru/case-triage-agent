# KB-509: SSO Login Failures from Corporate VPN

**Category:** Authentication & Access
**Audience:** Tier 1 support, Identity Platform Team
**Last reviewed:** 2026-04-18
**Owner:** Identity Platform Team

## Symptoms

- User connected to the corporate VPN cannot complete SAML SSO login.
- Login redirects to the IdP and back, then lands on an error page with code `AADSTS50105` or `SAML_RESPONSE_INVALID`.
- The same user can log in successfully off-VPN.

## Root cause

The VPN routes outbound traffic through an egress proxy whose IP range is not in our IdP's allow-list. The IdP rejects the SAML response because the InResponseTo source IP doesn't match the original request.

## Resolution steps

1. Confirm the user's VPN profile and the egress IP they are using.
2. Check the IdP allow-list (Identity Console → Trust Settings → Allowed IP Ranges).
3. If the VPN egress IP range is missing, add it (requires Identity admin role).
4. If the user is on a temporary VPN gateway (travel, contractor), have them disconnect VPN for SSO login as a temporary workaround.

## When to escalate

- Adding the IP range to the allow-list — requires Identity admin role.
- Multiple users from the same VPN gateway report the issue — likely a broader IdP allow-list misconfiguration.

## Related articles

- KB-247 (Invalid credentials after password reset)
- KB-412 (Session cookie issues on Safari)
