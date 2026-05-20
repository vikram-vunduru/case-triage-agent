"""Seed sample Accounts + Cases into the live Salesforce org via OAuth CCF.

Creates exactly the cases the agent demo expects:
  - 5 auth/login cases that match the seeded KB-247/301/356/412/509 articles.
  - 1 refund case that triggers the escalation branch (high-risk intent, no KB match).

Idempotent: re-running won't create duplicates (looks up by Subject / Name first).

Usage:
    python seed/seed_salesforce.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.salesforce_tool import SalesforceTool


# Only standard Account fields — Tier__c is a custom field that doesn't exist
# in a vanilla Dev Edition org. We pack tier/SLA info into the standard Description.
ACCOUNTS = [
    {
        "Name": "Acme Corp",
        "Industry": "Manufacturing",
        "NumberOfEmployees": 4200,
        "AnnualRevenue": 850000000,
        "Description": (
            "Strategic Enterprise account. SLA: P1 response within 1 hour, "
            "P2 within 4 hours. Federated SSO via Okta. Tier: Enterprise."
        ),
    },
    {
        "Name": "Globex Industries",
        "Industry": "Energy",
        "NumberOfEmployees": 11500,
        "AnnualRevenue": 2100000000,
        "Description": (
            "Premier account. Renewal approaching Q3. SAML SSO via Azure AD. "
            "Corporate VPN egress IPs not yet on auth allow-list. Tier: Premier."
        ),
    },
    {
        "Name": "Initech Inc",
        "Industry": "Technology",
        "NumberOfEmployees": 480,
        "AnnualRevenue": 95000000,
        "Description": "Standard tier. Self-serve customer.",
    },
]


CASES = [
    {
        "_account": "Acme Corp",
        "Subject": "Invalid credentials after password reset",
        "Description": (
            "Hi support team. I reset my password yesterday using the link in the email. "
            "The new password works fine on the mobile app, but when I try to log in on Chrome "
            "on my work laptop, I keep getting 'Invalid credentials'. I have tried the new password "
            "at least 10 times and I am sure it is correct. This is blocking me from accessing my "
            "reports. Please help, I have a board meeting Thursday."
        ),
        "Status": "New",
        "Priority": "High",
        "Origin": "Email",
    },
    {
        "_account": "Globex Industries",
        "Subject": "MFA code never arrives",
        "Description": (
            "I am trying to log in but the verification code text message never arrives. "
            "I have clicked Resend Code 4 times. I am on the corporate WiFi at our HQ. "
            "I tried switching to my iPhone hotspot and it still does not work."
        ),
        "Status": "New",
        "Priority": "Medium",
        "Origin": "Web",
    },
    {
        "_account": "Initech Inc",
        "Subject": "Locked out of account",
        "Description": (
            "I forgot my password and tried a few times before giving up. Now I see "
            "'Your account has been temporarily locked'. How long do I have to wait? "
            "I have a customer escalation I need to respond to right now."
        ),
        "Status": "New",
        "Priority": "High",
        "Origin": "Phone",
    },
    {
        "_account": "Acme Corp",
        "Subject": "Safari keeps logging me out",
        "Description": (
            "Every time I switch tabs in Safari I get logged out and have to sign in again. "
            "It only happens on my MacBook in Safari. Chrome on the same laptop is fine. "
            "This started last week after I updated to macOS Sequoia."
        ),
        "Status": "New",
        "Priority": "Medium",
        "Origin": "Email",
    },
    {
        "_account": "Globex Industries",
        "Subject": "Cannot SSO from VPN",
        "Description": (
            "When I am connected to the corporate VPN I cannot log in. I get an error AADSTS50105. "
            "If I disconnect VPN, SSO works fine. I need VPN for our internal apps so this is a problem."
        ),
        "Status": "New",
        "Priority": "High",
        "Origin": "Email",
    },
    {
        "_account": "Initech Inc",
        "Subject": "Need a refund for our annual subscription",
        "Description": (
            "We were charged for our renewal yesterday but we cancelled in March. "
            "We need a full refund of $48,000 processed back to our card. Please confirm the timeline."
        ),
        "Status": "New",
        "Priority": "High",
        "Origin": "Email",
    },
]


def _safe_soql_literal(value: str) -> str:
    """Escape single quotes for inline SOQL literals."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def main() -> None:
    sf = SalesforceTool()
    if sf.mode != "real":
        print(f"SalesforceTool is in '{sf.mode}' mode — set SALESFORCE_MODE=real in .env first.")
        sys.exit(1)

    client = sf._sf  # underlying simple_salesforce client

    name_to_id: dict[str, str] = {}

    print(f"Seeding {len(ACCOUNTS)} accounts + {len(CASES)} cases into Salesforce…\n")

    # ---------- Accounts (idempotent by Name) ----------
    print("Accounts:")
    for acc in ACCOUNTS:
        name_lit = _safe_soql_literal(acc["Name"])
        existing = client.query(f"SELECT Id FROM Account WHERE Name = '{name_lit}' LIMIT 1")
        if existing.get("records"):
            acc_id = existing["records"][0]["Id"]
            print(f"  · existing  {acc['Name']:<25} ({acc_id})")
        else:
            result = client.Account.create(acc)
            acc_id = result["id"]
            print(f"  ✓ created   {acc['Name']:<25} ({acc_id})")
        name_to_id[acc["Name"]] = acc_id

    # ---------- Cases (idempotent by Subject among open cases) ----------
    print("\nCases:")
    for c in CASES:
        case_data = {k: v for k, v in c.items() if not k.startswith("_")}
        case_data["AccountId"] = name_to_id[c["_account"]]

        subj_lit = _safe_soql_literal(c["Subject"])
        existing = client.query(
            f"SELECT Id FROM Case WHERE Subject = '{subj_lit}' AND IsClosed = FALSE LIMIT 1"
        )
        if existing.get("records"):
            case_id = existing["records"][0]["Id"]
            print(f"  · existing  [{c['_account']:<18}] {c['Subject'][:50]:<50} ({case_id})")
        else:
            result = client.Case.create(case_data)
            case_id = result["id"]
            print(f"  ✓ created   [{c['_account']:<18}] {c['Subject'][:50]:<50} ({case_id})")

    print()
    print("Done. Refresh http://127.0.0.1:8000 — the new cases should appear in the dropdown.")


if __name__ == "__main__":
    main()
