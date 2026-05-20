from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "seed"


class SalesforceTool:
    """Wraps Salesforce reads + writes. Defaults to mock mode using local JSON."""

    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or settings.salesforce_mode).lower()
        self._cases: dict[str, dict] = {}
        self._accounts: dict[str, dict] = {}
        self._chatter: list[dict] = []
        self._sf = None

        if self.mode == "mock":
            self._cases = json.loads((SEED_DIR / "sample_cases.json").read_text())
            self._accounts = json.loads((SEED_DIR / "sample_accounts.json").read_text())
        elif self.mode == "real":
            self._sf = self._connect_real()
        else:
            raise ValueError(f"Unknown salesforce_mode: {self.mode}")

    def _connect_real(self):
        """Authenticate to Salesforce.

        Prefers OAuth 2.0 Client Credentials Flow when consumer key/secret are
        present (works on modern orgs where SOAP login is disabled). Falls back
        to legacy username/password/security_token + SOAP login otherwise.
        """
        from simple_salesforce import Salesforce

        if settings.sf_consumer_key and settings.sf_consumer_secret:
            import httpx

            login_url = (
                settings.sf_login_url.rstrip("/")
                if settings.sf_login_url
                else f"https://{settings.sf_domain}.salesforce.com"
            )
            token_url = f"{login_url}/services/oauth2/token"
            resp = httpx.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.sf_consumer_key,
                    "client_secret": settings.sf_consumer_secret,
                },
                timeout=30.0,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Salesforce CCF token request failed [{resp.status_code}]: {resp.text[:400]}"
                )
            data = resp.json()
            return Salesforce(
                session_id=data["access_token"],
                instance_url=data["instance_url"],
            )

        # Legacy SOAP login (will fail on agentforce.com orgs where SOAP is disabled)
        return Salesforce(
            username=settings.sf_username,
            password=settings.sf_password,
            security_token=settings.sf_security_token,
            domain=settings.sf_domain,
        )

    def _call(self, fn):
        """Run a Salesforce API call. If the cached session has expired, re-auth
        via CCF and retry exactly once. Anything else propagates."""
        from simple_salesforce.exceptions import SalesforceExpiredSession
        try:
            return fn()
        except SalesforceExpiredSession:
            self._sf = self._connect_real()
            return fn()

    # ---------- Reads ----------

    def get_case(self, case_id: str) -> dict[str, Any]:
        if self.mode == "mock":
            return self._lookup_case_mock(case_id)
        case = self._call(lambda: self._sf.Case.get(case_id))
        return _clean_sobject(case)

    def get_account(self, account_id: str) -> dict[str, Any]:
        if self.mode == "mock":
            acc = self._accounts.get(account_id)
            if not acc:
                raise KeyError(f"Account {account_id} not found")
            return acc
        acc = self._call(lambda: self._sf.Account.get(account_id))
        return _clean_sobject(acc)

    def get_related_cases(self, account_id: str, exclude_case_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """Return recent cases for the same account (useful context for the Investigator)."""
        if self.mode == "mock":
            cases = [c for c in self._cases.values() if c.get("AccountId") == account_id]
            if exclude_case_id:
                cases = [c for c in cases if c["Id"] != exclude_case_id]
            cases.sort(key=lambda c: c.get("CreatedDate", ""), reverse=True)
            return [
                {
                    "Id": c["Id"],
                    "CaseNumber": c["CaseNumber"],
                    "Subject": c["Subject"],
                    "Priority": c["Priority"],
                    "Status": c["Status"],
                    "CreatedDate": c.get("CreatedDate"),
                }
                for c in cases[:limit]
            ]
        exclude_clause = f"AND Id != '{exclude_case_id}'" if exclude_case_id else ""
        soql = (
            "SELECT Id, CaseNumber, Subject, Priority, Status, CreatedDate "
            f"FROM Case WHERE AccountId = '{account_id}' {exclude_clause} "
            f"ORDER BY CreatedDate DESC LIMIT {limit}"
        )
        res = self._call(lambda: self._sf.query(soql))
        return [_clean_sobject(r) for r in res.get("records", [])]

    def get_case_history(self, case_id: str) -> dict[str, Any]:
        """Return the current Case + recent Chatter posts + Case Comments so
        the UI can show 'previously processed by the agent' indicators."""
        if self.mode == "mock":
            case = self._lookup_case_mock(case_id)
            return {
                "case": case,
                "chatter": [c for c in self._chatter if c.get("ParentId") == case["Id"]],
                "comments": case.get("Comments", []),
            }

        # Real mode — single relationship-aware SOQL for the Case, then 2 child queries.
        case_soql = (
            "SELECT Id, CaseNumber, Subject, Description, Status, Priority, Origin, "
            "Type, Reason, CreatedDate, LastModifiedDate, ClosedDate, "
            "AccountId, Account.Name, Account.Industry, "
            "ContactId, Contact.Name, Contact.Email, Contact.Phone, "
            "OwnerId, Owner.Name "
            f"FROM Case WHERE Id = '{case_id}' LIMIT 1"
        )
        case_res = self._call(lambda: self._sf.query(case_soql))
        if not case_res.get("records"):
            raise KeyError(f"Case {case_id} not found")
        case = _flatten_relationships(case_res["records"][0])

        feed_soql = (
            "SELECT Id, Body, CreatedDate, CreatedById, CreatedBy.Name "
            f"FROM FeedItem WHERE ParentId = '{case_id}' "
            "ORDER BY CreatedDate DESC LIMIT 5"
        )
        comments_soql = (
            "SELECT Id, CommentBody, CreatedDate, CreatedById, CreatedBy.Name, IsPublished "
            f"FROM CaseComment WHERE ParentId = '{case_id}' "
            "ORDER BY CreatedDate DESC LIMIT 5"
        )
        try:
            feed_res = self._call(lambda: self._sf.query(feed_soql))
            feed_records = [_clean_sobject(r) for r in feed_res.get("records", [])]
        except Exception:
            feed_records = []
        try:
            comments_res = self._call(lambda: self._sf.query(comments_soql))
            comment_records = [_clean_sobject(r) for r in comments_res.get("records", [])]
        except Exception:
            comment_records = []
        return {
            "case": case,
            "chatter": feed_records,
            "comments": comment_records,
        }

    def list_open_cases(self, limit: int = 10) -> list[dict[str, Any]]:
        if self.mode == "mock":
            cases = sorted(self._cases.values(), key=lambda c: c["CreatedDate"])
            return [
                {
                    "Id": c["Id"],
                    "CaseNumber": c["CaseNumber"],
                    "Subject": c["Subject"],
                    "Priority": c["Priority"],
                    "Status": c["Status"],
                }
                for c in cases[:limit]
            ]
        soql = (
            "SELECT Id, CaseNumber, Subject, Priority, Status "
            "FROM Case WHERE IsClosed = FALSE ORDER BY CreatedDate DESC LIMIT %d"
            % limit
        )
        res = self._call(lambda: self._sf.query(soql))
        return [_clean_sobject(r) for r in res.get("records", [])]

    # ---------- Writes ----------

    def post_chatter(self, case_id: str, message: str) -> dict[str, Any]:
        post = {
            "Id": f"FEED-{len(self._chatter) + 1:04d}",
            "ParentId": case_id,
            "Body": message,
            "CreatedDate": _now(),
        }
        if self.mode == "mock":
            self._chatter.append(post)
            return post
        feed = self._call(lambda: self._sf.FeedItem.create(
            {"ParentId": case_id, "Body": message, "Type": "TextPost"}
        ))
        return _clean_sobject(feed)

    def update_case(
        self,
        case_id: str,
        status: str | None = None,
        comment: str | None = None,
        resolution: str | None = None,
    ) -> dict[str, Any]:
        if self.mode == "mock":
            case = self._lookup_case_mock(case_id)
            if status:
                case["Status"] = status
            if resolution:
                case["Resolution__c"] = resolution
            case["LastModifiedDate"] = _now()
            if comment:
                case.setdefault("Comments", []).append(
                    {"text": comment, "createdAt": _now()}
                )
            return case

        update_fields: dict[str, Any] = {}
        if status:
            update_fields["Status"] = status
        if resolution:
            update_fields["Description"] = resolution
        if update_fields:
            self._call(lambda: self._sf.Case.update(case_id, update_fields))
        if comment:
            self._call(lambda: self._sf.CaseComment.create({"ParentId": case_id, "CommentBody": comment}))
        return {"Id": case_id, "updated": True, **update_fields}

    # ---------- internal ----------

    def _lookup_case_mock(self, case_id: str) -> dict[str, Any]:
        # Accept either the 15-char Id or the human-readable CaseNumber.
        if case_id in self._cases:
            return self._cases[case_id]
        for case in self._cases.values():
            if case.get("CaseNumber") == case_id:
                return case
        raise KeyError(f"Case {case_id} not found")


def _clean_sobject(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k != "attributes"}


def _flatten_relationships(rec: dict) -> dict:
    """Strip `attributes` recursively from related sub-objects returned by SOQL.

    Salesforce returns related records as nested dicts (e.g. ``case["Account"] = {"Name": "Acme", "attributes": {...}}``).
    The frontend just wants the names/emails, so we drop ``attributes`` everywhere.
    """
    out: dict = {}
    for k, v in rec.items():
        if k == "attributes":
            continue
        if isinstance(v, dict):
            out[k] = _flatten_relationships(v)
        else:
            out[k] = v
    return out


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
