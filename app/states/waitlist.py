import reflex as rx

import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import WaitlistLead


PROBLEMS: tuple[tuple[str, str], ...] = (
    ("forgot_expenses", "ننسى تسجيل المصروفات"),
    ("budget", "صعوبة وضع ميزانية"),
    ("partner", "عدم وضوح المصروف مع الشريك"),
    ("saving", "صعوبة الادخار"),
    ("installments", "متابعة الأقساط والديون"),
)
PROBLEM_CODES = frozenset(code for code, _ in PROBLEMS)
FOUNDER_LIMIT = 500
RESERVATION_LOCK = 6823341297005001


def normalize_contact(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if (
        not value
        or len(value) > 320
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("أدخل بريدًا إلكترونيًا أو رقم جوال دوليًا صالحًا.")
    if "@" in value:
        value = value.lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value, flags=re.ASCII):
            raise ValueError("أدخل بريدًا إلكترونيًا صالحًا.")
        return "email", value
    value = re.sub(r"[\s\-]", "", value)
    if not re.fullmatch(r"\+[1-9][0-9]{1,14}", value):
        raise ValueError("أدخل رقمًا دوليًا يبدأ بـ + ورمز الدولة (مثل +9665…).")
    return "phone", value


class WaitlistState(rx.State):
    stage: int = 1
    selected_problems: list[str] = []
    referral_code: str = ""
    error: str = ""
    completed_choice: str = ""
    full: bool = False
    lead_id: str = ""

    def _lead(self, db) -> WaitlistLead:
        if not self.lead_id:
            raise ValueError(
                "ابدأ بالتسجيل أولًا. إذا أعدت تحميل الصفحة، سجّل بوسيلة تواصل أخرى؛ تسجيلك السابق محفوظ."
            )
        lead = db.get(WaitlistLead, UUID(self.lead_id))
        if lead is None:
            raise ValueError("تعذر متابعة التسجيل في هذه الجلسة.")
        return lead

    def _create(
        self, db, raw: str, consent: bool, referral: str = ""
    ) -> tuple[str, str]:
        kind, value = normalize_contact(raw)
        if not consent:
            raise ValueError(
                "وافق صراحةً على التواصل معك بشأن الإطلاق للمتابعة."
            )
        if db.scalar(
            select(WaitlistLead.id).where(
                WaitlistLead.contact_kind == kind,
                WaitlistLead.contact_value == value,
            )
        ):
            raise ValueError(
                "تعذر إكمال التسجيل بوسيلة التواصل هذه. تحقق منها أو جرّب وسيلة أخرى."
            )
        referrer = None
        code = referral.strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code):
            referrer = db.scalar(
                select(WaitlistLead).where(WaitlistLead.referral_code == code)
            )
        if (
            referrer is not None
            and referrer.contact_kind == kind
            and referrer.contact_value == value
        ):
            referrer = None
        lead = WaitlistLead(
            contact_kind=kind,
            contact_value=value,
            consent_contact=True,
            referral_code=secrets.token_urlsafe(18),
            referred_by_id=referrer.id if referrer is not None else None,
        )
        db.add(lead)
        db.flush()
        return str(lead.id), lead.referral_code

    def _save_answers(self, db, codes: list[str]) -> None:
        lead = self._lead(db)
        if (
            not codes
            or len(set(codes)) != len(codes)
            or any(code not in PROBLEM_CODES for code in codes)
        ):
            raise ValueError("اختر مشكلة واحدة على الأقل من الخيارات المتاحة.")
        if lead.founder_decision != "pending":
            raise ValueError("لقد أنهيت اختيارك بالفعل.")
        lead.problem_codes = list(codes)
        db.flush()

    def _mark_invite(self, db) -> None:
        lead = self._lead(db)
        if lead.invite_clicked_at is None:
            lead.invite_clicked_at = datetime.now(timezone.utc)
            db.flush()

    def _decide(self, db, choice: str, limit: int = FOUNDER_LIMIT) -> str:
        if choice not in ("reserved", "free"):
            raise ValueError("اختر أحد الخيارين المتاحين.")
        if choice == "reserved":
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": RESERVATION_LOCK},
            )
        lead = self._lead(db)
        db.refresh(lead, with_for_update=True)
        if not lead.problem_codes:
            raise ValueError("أكمل اختيار التحديات أولًا.")
        if lead.founder_decision != "pending":
            return lead.founder_decision
        if choice == "reserved":
            count = db.scalar(
                select(func.count())
                .select_from(WaitlistLead)
                .where(WaitlistLead.founder_decision == "reserved")
            )
            if count >= limit:
                return "full"
            lead.reserved_at = datetime.now(timezone.utc)
        lead.founder_decision = choice
        db.flush()
        return choice

    @rx.event
    def toggle_problem(self, code: str):
        if self.stage != 2 or code not in PROBLEM_CODES:
            return
        self.error = ""
        self.selected_problems = (
            [item for item in self.selected_problems if item != code]
            if code in self.selected_problems
            else [*self.selected_problems, code]
        )

    @rx.event
    async def register_interest(self, data: dict[str, Any]):
        self.error = ""
        if self.stage != 1 or self.lead_id:
            return
        try:
            contact = str(data.get("contact", ""))
            consent = data.get("consent") in (True, "on", "true", "yes")
            referral = str(self.router.page.params.get("ref", ""))
            async with rx.asession() as db:
                lead_id, code = await db.run_sync(
                    lambda sync_db: self._create(
                        sync_db, contact, consent, referral
                    )
                )
                await db.commit()
            self.lead_id = lead_id
            self.referral_code = code
            self.stage = 2
        except ValueError as e:
            self.error = str(e)
        except IntegrityError:
            logging.exception("Unexpected error")
            self.error = "تعذر إكمال التسجيل بوسيلة التواصل هذه. تحقق منها أو جرّب وسيلة أخرى."
        except Exception as e:
            logging.exception("Unexpected error")
            logging.error("Waitlist registration failed (%s)", type(e).__name__)
            self.error = "تعذر حفظ التسجيل الآن. حاول مجددًا."

    @rx.event
    async def save_problems(self):
        self.error = ""
        if self.stage != 2:
            return
        try:
            async with rx.asession() as db:
                await db.run_sync(
                    lambda sync_db: self._save_answers(
                        sync_db, self.selected_problems
                    )
                )
                await db.commit()
            self.stage = 3
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            logging.error("Waitlist answers failed (%s)", type(e).__name__)
            self.error = "تعذر حفظ اختياراتك الآن. حاول مجددًا."

    @rx.event
    async def mark_invite_click(self):
        if self.stage != 2 or not self.lead_id:
            return
        try:
            async with rx.asession() as db:
                await db.run_sync(self._mark_invite)
                await db.commit()
        except Exception as e:
            logging.exception("Unexpected error")
            logging.error("Waitlist share click failed (%s)", type(e).__name__)
            self.error = (
                "لم نتمكن من تسجيل نقرة المشاركة. لم نرسل دعوة نيابةً عنك."
            )

    @rx.event
    async def choose_founder(self, choice: str):
        self.error = ""
        if self.stage != 3 or choice not in ("reserved", "free"):
            return
        try:
            async with rx.asession() as db:
                result = await db.run_sync(
                    lambda sync_db: self._decide(sync_db, choice)
                )
                if result != "full":
                    await db.commit()
            if result == "full":
                self.full = True
                self.error = "اكتملت أماكن عضوية المؤسسين. يمكنك اختيار النسخة المجانية؛ لم يُحجز لك مكان ولم تُحصّل أي مبالغ."
            else:
                self.completed_choice = result
                self.stage = 4
                self.full = False
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            logging.error("Waitlist decision failed (%s)", type(e).__name__)
            self.error = "تعذر حفظ اختيارك الآن. حاول مجددًا."
