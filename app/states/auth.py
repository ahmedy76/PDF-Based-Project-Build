import reflex as rx

import hashlib
import re

from app.observability import report_unexpected
import secrets
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
from sqlalchemy import select, text
from app import models as m

import logging

LOGIN_FAILURE_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)
INVALID_CREDENTIALS = "البريد أو كلمة المرور غير صحيحة."
LOCKED_LOGIN = "محاولات كثيرة. انتظر 15 دقيقة ثم حاول مجددًا."
DUMMY_PASSWORD_HASH = bcrypt.hashpw(
    b"unused-login-placeholder", bcrypt.gensalt()
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)


def require_permission(member, permission: str) -> None:
    role = getattr(member, "role", None)
    if role not in ("owner", "partner") or (
        role == "partner" and not getattr(member, permission, False)
    ):
        raise ValueError("ليس لديك صلاحية تنفيذ هذه العملية في الأسرة.")


def denied_account_ids(db, household_id, user_id) -> set[UUID]:
    return set(
        db.scalars(
            select(m.HouseholdAccountRestriction.account_id).where(
                m.HouseholdAccountRestriction.household_id == household_id,
                m.HouseholdAccountRestriction.member_user_id == user_id,
            )
        ).all()
    )


def visible_account_ids(db, member, accounts) -> set[UUID]:
    if getattr(member, "role", None) not in ("owner", "partner"):
        raise ValueError("الحساب غير متاح لك في هذه الأسرة.")
    ids = {account.id for account in accounts}
    if member.role == "owner":
        return ids
    return ids - denied_account_ids(db, member.household_id, member.user_id)


def require_account(db, member, account_id: UUID) -> None:
    role = getattr(member, "role", None)
    if role not in ("owner", "partner"):
        raise ValueError("الحساب غير متاح لك في هذه الأسرة.")
    if role == "partner" and account_id in denied_account_ids(
        db, member.household_id, member.user_id
    ):
        raise ValueError("الحساب غير متاح لك في هذه الأسرة.")


def blocked_budget_currencies(db, member) -> set[str]:
    if getattr(member, "role", None) not in ("owner", "partner"):
        raise ValueError("ليس لديك صلاحية تنفيذ هذه العملية في الأسرة.")
    if member.role == "owner":
        return set()
    return set(
        db.scalars(
            select(m.FinancialAccount.currency)
            .join(
                m.HouseholdAccountRestriction,
                (
                    m.HouseholdAccountRestriction.account_id
                    == m.FinancialAccount.id
                )
                & (
                    m.HouseholdAccountRestriction.household_id
                    == m.FinancialAccount.household_id
                ),
            )
            .where(
                m.FinancialAccount.household_id == member.household_id,
                m.HouseholdAccountRestriction.member_user_id == member.user_id,
            )
        ).all()
    )


class AuthState(rx.State):
    token: str = rx.Cookie(
        "", name="mh_session", secure=True, same_site="strict", max_age=86400
    )
    selected_household: str = rx.Cookie(
        "", name="mh_household", secure=True, same_site="strict", max_age=86400
    )
    authenticated: bool = False
    name: str = ""
    email: str = ""
    error: str = ""
    pending_invite: str = rx.SessionStorage("")

    def _identity(self, db):
        session = db.scalar(
            select(m.UserSession).where(
                m.UserSession.access_token_hash == digest(self.token),
                m.UserSession.revoked_at.is_(None),
                m.UserSession.access_expires_at > now(),
            )
        )
        if not session:
            self.authenticated = False
            raise PermissionError("انتهت الجلسة. يرجى تسجيل الدخول.")
        user = db.get(m.User, session.user_id)
        if not user or user.status != "active":
            self.authenticated = False
            raise PermissionError("يرجى تسجيل الدخول.")
        self.authenticated = True
        self.name, self.email = user.display_name, user.email
        return user

    def _household(self, db):
        user = self._identity(db)
        memberships = db.scalars(
            select(m.HouseholdMembership)
            .join(
                m.Household,
                m.Household.id == m.HouseholdMembership.household_id,
            )
            .where(
                m.HouseholdMembership.user_id == user.id,
                m.HouseholdMembership.status == "active",
                m.Household.status == "active",
            )
            .order_by(m.HouseholdMembership.joined_at)
        ).all()
        membership = next(
            (
                x
                for x in memberships
                if str(x.household_id) == self.selected_household
            ),
            None,
        )
        if membership is None and memberships:
            membership = memberships[0]
        if membership is None or membership.role not in ("owner", "partner"):
            raise PermissionError("لا توجد عضوية أسرة نشطة.")
        self.selected_household = str(membership.household_id)
        return user, membership

    def _new_session(self, db, user):
        old = db.scalar(
            select(m.UserSession).where(
                m.UserSession.access_token_hash == digest(self.token),
                m.UserSession.revoked_at.is_(None),
            )
        )
        if old:
            old.revoked_at = now()
        raw = secrets.token_urlsafe(48)
        db.add(
            m.UserSession(
                user_id=user.id,
                access_token_hash=digest(raw),
                refresh_token_hash=digest(secrets.token_urlsafe(48)),
                access_expires_at=now() + timedelta(days=1),
                refresh_expires_at=now() + timedelta(days=1, minutes=1),
            )
        )
        db.commit()
        self.token = raw
        self.authenticated = True
        self.name, self.email = user.display_name, user.email
        self.error = ""

    def _login_attempt(self, db, email: str, password: bytes) -> str:
        identifier_hash = digest(email)
        lock_key = int.from_bytes(
            bytes.fromhex(identifier_hash)[:8], "big", signed=True
        )
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key}
        )
        attempt = db.scalar(
            select(m.AuthenticationAttempt).where(
                m.AuthenticationAttempt.identifier_digest == identifier_hash
            )
        )
        clock = now()
        if (
            attempt is not None
            and attempt.locked_until is not None
            and attempt.locked_until > clock
        ):
            db.commit()
            return "locked"
        user = db.scalar(
            select(m.User).where(
                m.User.email == email, m.User.status == "active"
            )
        )
        verified = bcrypt.checkpw(
            password,
            user.password_hash.encode() if user else DUMMY_PASSWORD_HASH,
        )
        if user is not None and verified:
            if attempt is not None:
                db.delete(attempt)
            self._new_session(db, user)
            return "success"
        if attempt is None:
            attempt = m.AuthenticationAttempt(
                identifier_digest=identifier_hash,
                attempt_count=1,
                window_started_at=clock,
            )
            db.add(attempt)
        elif (
            attempt.locked_until is not None
            or clock >= attempt.window_started_at + LOGIN_WINDOW
        ):
            attempt.window_started_at = clock
            attempt.attempt_count = 1
            attempt.locked_until = None
        else:
            attempt.attempt_count = min(
                attempt.attempt_count + 1, LOGIN_FAILURE_LIMIT
            )
        if attempt.attempt_count >= LOGIN_FAILURE_LIMIT:
            attempt.locked_until = clock + LOGIN_WINDOW
        outcome = "locked" if attempt.locked_until is not None else "invalid"
        db.commit()
        return outcome

    @rx.event
    def register(self, data: dict[str, Any]):
        self.error = ""
        try:
            name = str(data.get("name", "")).strip()
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            if (
                not 2 <= len(name) <= 120
                or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
                or len(email) > 320
            ):
                raise ValueError("أدخل اسمًا وبريدًا إلكترونيًا صالحين.")
            if (
                len(password) < 8
                or len(password.encode()) > 72
                or password != data.get("confirm")
            ):
                raise ValueError(
                    "كلمة المرور: 8 أحرف على الأقل، حتى 72 بايت، مع تأكيد مطابق."
                )
            if not data.get("terms"):
                raise ValueError("الموافقة على شروط الاستخدام مطلوبة.")
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            with rx.session() as db:
                if db.scalar(select(m.User.id).where(m.User.email == email)):
                    raise ValueError(
                        "تعذر إنشاء الحساب بهذا البريد. جرّب تسجيل الدخول."
                    )
                user = m.User(
                    display_name=name,
                    email=email,
                    password_hash=hashed,
                    language="ar",
                    terms_accepted_at=now(),
                )
                db.add(user)
                db.flush()
                household = m.Household(
                    name=f"أسرة {name}", owner_user_id=user.id
                )
                db.add(household)
                db.flush()
                db.add(
                    m.HouseholdMembership(
                        household_id=household.id, user_id=user.id, role="owner"
                    )
                )
                for kind, names in [
                    ("income", ["راتب", "عمل إضافي", "دخل آخر"]),
                    (
                        "expense",
                        [
                            "البقالة",
                            "السكن",
                            "الفواتير",
                            "المواصلات",
                            "الصحة",
                            "التعليم",
                            "الترفيه",
                            "مصروف آخر",
                        ],
                    ),
                ]:
                    for label in names:
                        db.add(
                            m.Category(
                                household_id=household.id, kind=kind, name=label
                            )
                        )
                self.selected_household = str(household.id)
                self._new_session(db, user)
            return rx.redirect(
                "/accept-invitation" if self.pending_invite else "/onboarding"
            )
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("auth.register", e)
            self.error = "تعذر إنشاء الحساب. حاول مجددًا."

    @rx.event
    def login(self, data: dict[str, Any]):
        self.error = ""
        raw_email = str(data.get("email", ""))
        raw_password = str(data.get("password", ""))
        if len(raw_email) > 320 or len(raw_password) > 72:
            self.error = INVALID_CREDENTIALS
            return
        email = raw_email.strip().lower()
        if (
            not email
            or len(email) > 320
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        ):
            self.error = INVALID_CREDENTIALS
            return
        password = raw_password.encode()
        if len(password) > 72:
            self.error = INVALID_CREDENTIALS
            return
        try:
            with rx.session() as db:
                outcome = self._login_attempt(db, email, password)
            if outcome == "success":
                return rx.redirect(
                    "/accept-invitation"
                    if self.pending_invite
                    else "/dashboard"
                )
            self.error = (
                LOCKED_LOGIN if outcome == "locked" else INVALID_CREDENTIALS
            )
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("auth.login", e)
            self.error = "تعذر تسجيل الدخول. حاول مجددًا."

    @rx.event
    def logout(self):
        try:
            with rx.session() as db:
                record = db.scalar(
                    select(m.UserSession).where(
                        m.UserSession.access_token_hash == digest(self.token),
                        m.UserSession.revoked_at.is_(None),
                    )
                )
                if record:
                    record.revoked_at = now()
                    db.commit()
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("auth.logout", e)
            self.error = "تعذر إلغاء الجلسة. حاول مرة أخرى."
            return
        self.token = ""
        self.selected_household = ""
        self.authenticated = False
        self.name = self.email = ""
        return rx.redirect("/login")

    @rx.event
    def clear_error(self):
        self.error = ""

    @rx.event
    def prepare_invitation(self):
        token = self.router.url.query_parameters.get("token", "")
        if token:
            self.pending_invite = str(token)
        authenticated = False
        try:
            with rx.session() as db:
                with suppress(PermissionError):
                    self._identity(db)
                    authenticated = True
            if not authenticated:
                self.error = ""
                return rx.redirect("/login")
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("auth.prepare_invitation", e)
            return rx.redirect("/login")
