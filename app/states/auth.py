import reflex as rx

import hashlib
import logging
import re
import secrets
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
from sqlalchemy import select
from app import models as m


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)


class AuthState(rx.State):
    token: str = rx.Cookie(
        "", name="mh_session", secure=True, same_site="strict", max_age=86400
    )
    selected_household: str = rx.Cookie(
        "", name="mh_household", same_site="strict"
    )
    authenticated: bool = False
    name: str = ""
    email: str = ""
    error: str = ""
    pending_invite: str = rx.SessionStorage("")
    _attempts: int = 0
    _retry_at: float = 0.0

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
        if membership is None:
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
            logging.exception(f"Error: {e}")
            self.error = "تعذر إنشاء الحساب. حاول مجددًا."

    @rx.event
    def login(self, data: dict[str, Any]):
        try:
            if now().timestamp() < self._retry_at:
                raise ValueError("محاولات كثيرة. انتظر دقيقة ثم حاول مجددًا.")
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", "")).encode()
            self._attempts += 1
            if self._attempts >= 5:
                self._retry_at = now().timestamp() + 60
                self._attempts = 0
            with rx.session() as db:
                user = db.scalar(
                    select(m.User).where(
                        m.User.email == email, m.User.status == "active"
                    )
                )
                if (
                    not user
                    or len(password) > 72
                    or not bcrypt.checkpw(password, user.password_hash.encode())
                ):
                    raise ValueError("البريد أو كلمة المرور غير صحيحة.")
                self._new_session(db, user)
            self._attempts = 0
            return rx.redirect(
                "/accept-invitation" if self.pending_invite else "/dashboard"
            )
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
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
            logging.exception(f"Error: {e}")
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
            logging.exception(f"Error: {e}")
            return rx.redirect("/login")
