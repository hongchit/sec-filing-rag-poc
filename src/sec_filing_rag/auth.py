from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from .repositories.database import Database


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    csrf_token: str


class QuotaExceeded(RuntimeError):
    def __init__(self, summary: dict[str, str]) -> None:
        self.summary = summary
        super().__init__("lifetime quota exceeded")


class AuthRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_google_user(
        self, *, issuer: str, subject: str, email: str, name: str | None
    ) -> dict[str, Any]:
        with self.database.transaction() as connection:
            row = connection.execute(
                "INSERT INTO public.app_user(id,oidc_issuer,oidc_subject,email,email_verified,display_name,last_login_at) "
                "VALUES (%s,%s,%s,%s,true,%s,now()) "
                "ON CONFLICT (oidc_issuer,oidc_subject) DO UPDATE SET email=EXCLUDED.email,email_verified=true,"
                "display_name=EXCLUDED.display_name,last_login_at=now(),updated_at=now() "
                "RETURNING id,email,display_name,status::text AS status",
                (uuid.uuid4(), issuer, subject, email.lower(), name),
            ).fetchone()
        return dict(row)

    def create_session(self, user_id: uuid.UUID, lifetime_days: int) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.auth_session(id,user_id,token_sha256,csrf_token_sha256,expires_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    uuid.uuid4(),
                    user_id,
                    _digest(token),
                    _digest(csrf),
                    datetime.now(UTC) + timedelta(days=lifetime_days),
                ),
            )
        return token, csrf

    def authenticate(
        self, token: str, csrf: str | None, admin_emails: frozenset[str]
    ) -> Principal | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT u.id,u.email,u.display_name,u.status::text AS status,s.csrf_token_sha256 "
                "FROM public.auth_session s JOIN public.app_user u ON u.id=s.user_id "
                "WHERE s.token_sha256=%s AND s.revoked_at IS NULL AND s.expires_at>now()",
                (_digest(token),),
            ).fetchone()
            if row is not None:
                connection.execute(
                    "UPDATE public.auth_session SET last_seen_at=now() WHERE token_sha256=%s",
                    (_digest(token),),
                )
        if row is None or row["status"] != "active" or not row["email"]:
            return None
        if csrf is not None and not hmac.compare_digest(_digest(csrf), row["csrf_token_sha256"]):
            return None
        return Principal(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            is_admin=row["email"].lower() in admin_emails,
            csrf_token=csrf or "",
        )

    def session_csrf(self, token: str) -> str | None:
        """CSRF values cannot be recovered from hashes; callers retain it in a readable companion cookie."""
        return None

    def revoke_session(self, token: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.auth_session SET revoked_at=now() WHERE token_sha256=%s",
                (_digest(token),),
            )

    def budget(self, user_id: uuid.UUID, default: Decimal) -> dict[str, str]:
        with self.database.transaction() as connection:
            return budget_summary(connection, user_id, default)

    def audit(
        self,
        event_type: str,
        outcome: str,
        *,
        actor: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.audit_event(actor_user_id,event_type,outcome,target_type,target_id,request_id,metadata) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    actor,
                    event_type,
                    outcome,
                    target_type,
                    target_id,
                    request_id,
                    json.dumps(metadata or {}),
                ),
            )

    def users(self, *, limit: int, search: str | None, default: Decimal) -> list[dict[str, Any]]:
        pattern = f"%{search}%" if search else None
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT id,email,display_name,status::text AS status,lifetime_budget_override_usd,"
                "created_at,last_login_at FROM public.app_user WHERE oidc_issuer<>'legacy' "
                "AND (%s::text IS NULL OR email ILIKE %s OR display_name ILIKE %s) "
                "ORDER BY created_at DESC LIMIT %s",
                (pattern, pattern, pattern, limit),
            ).fetchall()
        values = []
        for row in rows:
            value = dict(row)
            value["budget"] = self.budget(row["id"], default)
            values.append(value)
        return values

    def user_activity(self, user_id: uuid.UUID, *, limit: int) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            user = connection.execute(
                "SELECT id,email,display_name,status::text AS status,lifetime_budget_override_usd,created_at,last_login_at "
                "FROM public.app_user WHERE id=%s AND oidc_issuer<>'legacy'",
                (user_id,),
            ).fetchone()
            if user is None:
                return None
            research = connection.execute(
                "SELECT rr.id,rr.ticker,rr.goal,rr.question,rr.status::text AS status,rr.created_at,rr.finished_at,"
                "ca.status::text AS cost_status,ca.reserved_usd,ca.charged_usd "
                "FROM public.research_request rr LEFT JOIN public.cost_action ca ON ca.research_id=rr.id "
                "WHERE rr.user_id=%s ORDER BY rr.created_at DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
            batches = connection.execute(
                "SELECT b.id,b.mode::text AS mode,b.fiscal_year,b.status::text AS status,b.request_id,"
                "b.kestra_execution_id,b.safe_error,b.created_at,b.finished_at,"
                "ca.status::text AS cost_status,ca.reserved_usd,ca.charged_usd "
                "FROM public.filing_batch b LEFT JOIN public.cost_action ca ON ca.filing_batch_id=b.id "
                "WHERE b.user_id=%s ORDER BY b.created_at DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
            batch_values = [dict(row) for row in batches]
            batch_ids = [row["id"] for row in batch_values]
            items = (
                connection.execute(
                    "SELECT bi.id,bi.batch_id,bi.position,c.ticker,bi.status::text AS status,"
                    "bi.selected_accession,bi.acquisition_id,bi.corpus_version_id,bi.safe_error,"
                    "bi.started_at,bi.finished_at FROM public.filing_batch_item bi "
                    "JOIN public.company c ON c.id=bi.company_id WHERE bi.batch_id=ANY(%s) "
                    "ORDER BY bi.batch_id,bi.position",
                    (batch_ids,),
                ).fetchall()
                if batch_ids
                else []
            )
        items_by_batch: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for row in items:
            item = dict(row)
            items_by_batch.setdefault(item.pop("batch_id"), []).append(item)
        for batch in batch_values:
            batch["items"] = items_by_batch.get(batch["id"], [])
        return {
            "user": dict(user),
            "research": [dict(row) for row in research],
            "filing_batches": batch_values,
        }

    def update_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None,
        budget_override: Decimal | None,
        clear_budget_override: bool,
    ) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                "UPDATE public.app_user SET status=COALESCE(%s::public.user_status,status),"
                "lifetime_budget_override_usd=CASE WHEN %s THEN NULL WHEN %s::numeric IS NOT NULL THEN %s ELSE lifetime_budget_override_usd END,"
                "updated_at=now() WHERE id=%s AND oidc_issuer<>'legacy' RETURNING id",
                (status, clear_budget_override, budget_override, budget_override, user_id),
            ).fetchone()
            if row is not None and status == "disabled":
                connection.execute(
                    "UPDATE public.auth_session SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
                    (user_id,),
                )
        return row is not None


def budget_summary(connection: Any, user_id: uuid.UUID, default: Decimal) -> dict[str, str]:
    row = connection.execute(
        "SELECT lifetime_budget_override_usd FROM public.app_user WHERE id=%s FOR UPDATE",
        (user_id,),
    ).fetchone()
    if row is None:
        raise ValueError("unknown user")
    limit = row["lifetime_budget_override_usd"]
    limit = Decimal(str(limit)) if limit is not None else default
    amounts = connection.execute(
        "SELECT COALESCE(sum(CASE WHEN status='reserved' THEN reserved_usd ELSE charged_usd END),0) AS used,"
        "COALESCE(sum(reserved_usd) FILTER (WHERE status='reserved'),0) AS reserved "
        "FROM public.cost_action WHERE user_id=%s",
        (user_id,),
    ).fetchone()
    used = Decimal(str(amounts["used"]))
    reserved = Decimal(str(amounts["reserved"]))
    return {
        "limit_usd": format(limit, "f"),
        "used_usd": format(used, "f"),
        "reserved_usd": format(reserved, "f"),
        "remaining_usd": format(limit - used, "f"),
    }


def reserve_cost(
    connection: Any, user_id: uuid.UUID, default: Decimal, amount: Decimal
) -> dict[str, str]:
    summary = budget_summary(connection, user_id, default)
    if Decimal(summary["remaining_usd"]) < amount:
        raise QuotaExceeded(summary)
    return summary
