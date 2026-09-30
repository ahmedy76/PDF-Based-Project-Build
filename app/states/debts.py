import reflex as rx

import calendar
import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import delete, func, select

from app import models as m
from app.states.auth import AuthState


class InstallmentRow(TypedDict):
    sequence: int
    due: str
    amount: str
    paid: str
    remaining: str
    status: str


class PaymentRow(TypedDict):
    id: str
    amount: str
    date: str
    note: str
    voided: bool


class DebtRow(TypedDict):
    id: str
    title: str
    direction: str
    counterparty: str
    note: str
    principal: str
    principal_raw: str
    first_due_date: str
    installment_count: str
    paid: str
    remaining: str
    overdue: str
    next_due: str
    status: str
    has_payments: bool
    installments: list[InstallmentRow]
    history: list[PaymentRow]


def money(raw: str) -> Decimal:
    try:
        if not re.fullmatch(r"\d+(?:\.\d{1,4})?", raw.strip()):
            raise ValueError(
                "أدخل مبلغًا موجبًا بدقة لا تتجاوز أربع خانات عشرية."
            )
        value = Decimal(raw.strip())
        if value <= 0 or value >= Decimal("1000000000000000"):
            raise ValueError(
                "المبلغ يجب أن يكون أكبر من صفر وأقل من 1,000,000,000,000,000."
            )
        return value.quantize(Decimal("0.0001"))
    except (InvalidOperation, OverflowError) as e:
        logging.exception("Unexpected error")
        raise ValueError("أدخل مبلغًا صالحًا بدقة أربع خانات عشرية.") from e


def parse_date(raw: str, *, past_allowed: bool = True) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError("أدخل تاريخًا صالحًا بصيغة YYYY-MM-DD.")
    try:
        result = date.fromisoformat(raw)
    except ValueError as e:
        raise ValueError("أدخل تاريخًا صالحًا بصيغة YYYY-MM-DD.") from e
    if not past_allowed and result > date.today():
        raise ValueError("تاريخ الدفعة لا يمكن أن يكون في المستقبل.")
    return result


def schedule(
    principal: Decimal, first: date, count: int
) -> list[tuple[date, Decimal]]:
    if not 1 <= count <= 120:
        raise ValueError("عدد الأقساط يجب أن يكون عددًا صحيحًا بين 1 و120.")
    units = int(principal * 10000)
    if (
        units < count
        or principal <= 0
        or principal >= Decimal("1000000000000000")
        or principal != Decimal(units) / 10000
    ):
        raise ValueError(
            "المبلغ لا يكفي لأقساط موجبة بدقة أربع خانات أو يتجاوز الحد المسموح."
        )
    base, extra = divmod(units, count)
    result: list[tuple[date, Decimal]] = []
    for index in range(count):
        year = first.year + (first.month - 1 + index) // 12
        month = (first.month - 1 + index) % 12 + 1
        if year > 9999:
            raise ValueError(
                "جدول الأقساط يتجاوز السنة 9999؛ اختر تاريخًا أبكر أو أقساطًا أقل."
            )
        due = date(
            year, month, min(first.day, calendar.monthrange(year, month)[1])
        )
        result.append((due, Decimal(base + int(index < extra)) / 10000))
    return result


class DebtState(rx.State):
    debts: list[DebtRow] = []
    archived_debts: list[DebtRow] = []
    payable_total: str = "0.0000"
    receivable_total: str = "0.0000"
    overdue_count: int = 0
    payable_overdue_count: int = 0
    receivable_overdue_count: int = 0
    filter_direction: str = "all"
    error: str = ""
    message: str = ""
    editor: str = ""
    edit_id: str = ""
    void_id: str = ""
    draft: dict[str, str] = {
        "title": "",
        "direction": "payable",
        "counterparty": "",
        "principal": "",
        "first_due_date": "",
        "installment_count": "1",
        "note": "",
    }

    @rx.var
    def today(self) -> str:
        return date.today().isoformat()

    @rx.var
    def visible_debts(self) -> list[DebtRow]:
        return [
            row
            for row in self.debts
            if self.filter_direction == "all"
            or row["direction"] == self.filter_direction
        ]

    def _uuid(self, raw: str) -> UUID:
        try:
            return UUID(raw)
        except (ValueError, TypeError, AttributeError) as e:
            logging.exception("Unexpected error")
            raise ValueError("السجل غير موجود أو غير متاح لهذه الأسرة.") from e

    def _guard(self, db, hid: UUID, uid: UUID):
        household = db.scalar(
            select(m.Household)
            .where(m.Household.id == hid, m.Household.status == "active")
            .with_for_update()
        )
        member = db.scalar(
            select(m.HouseholdMembership.id).where(
                m.HouseholdMembership.household_id == hid,
                m.HouseholdMembership.user_id == uid,
                m.HouseholdMembership.status == "active",
            )
        )
        if household is None or member is None:
            raise PermissionError("لا توجد عضوية أسرة نشطة.")

    def _debt(self, db, hid: UUID, raw: str) -> m.Debt:
        debt = db.scalar(
            select(m.Debt)
            .where(m.Debt.household_id == hid, m.Debt.id == self._uuid(raw))
            .with_for_update()
        )
        if debt is None:
            raise ValueError("الدين غير موجود أو غير متاح لهذه الأسرة.")
        return debt

    def _paid(self, db, hid: UUID, debt_id: UUID) -> Decimal:
        return db.scalar(
            select(func.coalesce(func.sum(m.DebtPayment.amount), 0)).where(
                m.DebtPayment.household_id == hid,
                m.DebtPayment.debt_id == debt_id,
                m.DebtPayment.voided_at.is_(None),
            )
        )

    def _save(
        self, db, hid: UUID, uid: UUID, data: dict[str, Any], edit_id: str = ""
    ):
        self._guard(db, hid, uid)
        debt = self._debt(db, hid, edit_id) if edit_id else None
        if debt is not None and debt.is_archived:
            raise ValueError("استعد الدين المؤرشف قبل تعديله.")
        title = str(data.get("title", "")).strip()
        counterparty = str(data.get("counterparty", "")).strip()
        note = str(data.get("note", "")).strip()
        direction = str(data.get("direction", ""))
        if (
            not 1 <= len(title) <= 120
            or not 1 <= len(counterparty) <= 120
            or len(note) > 500
        ):
            raise ValueError(
                "العنوان والطرف الآخر مطلوبان (حتى 120 حرفًا)، والملاحظة حتى 500 حرف."
            )
        if direction not in ("payable", "receivable"):
            raise ValueError("اختر نوع الدين: علينا أو لنا.")
        principal = money(str(data.get("principal", "")))
        first = parse_date(str(data.get("first_due_date", "")))
        raw_count = str(data.get("installment_count", ""))
        if (
            not re.fullmatch(r"[1-9]\d*", raw_count)
            or len(raw_count) > 3
            or not 1 <= int(raw_count) <= 120
        ):
            raise ValueError("عدد الأقساط يجب أن يكون عددًا صحيحًا بين 1 و120.")
        count = int(raw_count)
        entries = schedule(principal, first, count)
        changed = debt is None or (
            debt.direction,
            debt.principal,
            debt.first_due_date,
            debt.installment_count,
        ) != (direction, principal, first, count)
        if (
            debt is not None
            and changed
            and db.scalar(
                select(m.DebtPayment.id)
                .where(
                    m.DebtPayment.household_id == hid,
                    m.DebtPayment.debt_id == debt.id,
                )
                .limit(1)
            )
            is not None
        ):
            raise ValueError(
                "لا يمكن إعادة تخطيط المبلغ أو النوع أو التاريخ أو الأقساط بعد تسجيل أي دفعة، حتى لو أُلغيت. يمكنك تعديل الاسم والطرف والملاحظة."
            )
        if debt is None:
            debt = m.Debt(
                household_id=hid,
                created_by_user_id=uid,
                title=title,
                counterparty=counterparty,
                direction=direction,
                principal=principal,
                first_due_date=first,
                installment_count=count,
                note=note or None,
            )
            db.add(debt)
            db.flush()
        else:
            debt.title, debt.counterparty, debt.note = (
                title,
                counterparty,
                note or None,
            )
            (
                debt.direction,
                debt.principal,
                debt.first_due_date,
                debt.installment_count,
            ) = direction, principal, first, count
        if changed:
            if edit_id:
                db.execute(
                    delete(m.DebtInstallment).where(
                        m.DebtInstallment.household_id == hid,
                        m.DebtInstallment.debt_id == debt.id,
                    )
                )
            for index, (due, amount) in enumerate(entries, 1):
                db.add(
                    m.DebtInstallment(
                        household_id=hid,
                        debt_id=debt.id,
                        sequence_no=index,
                        due_date=due,
                        amount=amount,
                    )
                )
        db.flush()
        return debt

    def _payment(
        self, db, hid: UUID, uid: UUID, debt_id: str, data: dict[str, Any]
    ):
        self._guard(db, hid, uid)
        debt = self._debt(db, hid, debt_id)
        if debt.is_archived:
            raise ValueError("استعد الدين المؤرشف أولًا.")
        amount = money(str(data.get("amount", "")))
        paid_on = parse_date(str(data.get("paid_on", "")), past_allowed=False)
        note = str(data.get("note", "")).strip()
        if len(note) > 500:
            raise ValueError("الملاحظة لا تتجاوز 500 حرف.")
        if amount > debt.principal - self._paid(db, hid, debt.id):
            raise ValueError("الدفعة تتجاوز المبلغ المتبقي من أصل الدين.")
        entry = m.DebtPayment(
            household_id=hid,
            debt_id=debt.id,
            created_by_user_id=uid,
            amount=amount,
            paid_on=paid_on,
            note=note or None,
        )
        db.add(entry)
        db.flush()
        return entry

    def _void(self, db, hid: UUID, uid: UUID, debt_id: str, payment_id: str):
        self._guard(db, hid, uid)
        debt = self._debt(db, hid, debt_id)
        if debt.is_archived:
            raise ValueError("استعد الدين المؤرشف قبل تصحيح دفعة.")
        payment = db.scalar(
            select(m.DebtPayment)
            .where(
                m.DebtPayment.household_id == hid,
                m.DebtPayment.debt_id == debt.id,
                m.DebtPayment.id == self._uuid(payment_id),
            )
            .with_for_update()
        )
        if payment is None:
            raise ValueError("الدفعة غير موجودة أو غير متاحة لهذه الأسرة.")
        if payment.voided_at is not None:
            raise ValueError("هذه الدفعة ملغاة بالفعل.")
        payment.voided_at = datetime.now(timezone.utc)
        db.flush()

    def _archive(self, db, hid: UUID, uid: UUID, debt_id: str, archived: bool):
        self._guard(db, hid, uid)
        debt = self._debt(db, hid, debt_id)
        if debt.is_archived == archived:
            raise ValueError("حالة الدين محدّثة بالفعل.")
        if archived and self._paid(db, hid, debt.id) != debt.principal:
            raise ValueError("لا يمكن أرشفة الدين قبل سداده بالكامل.")
        debt.is_archived = archived
        db.flush()

    def _load(self, db, hid: UUID):
        debts = db.scalars(
            select(m.Debt)
            .where(m.Debt.household_id == hid)
            .order_by(m.Debt.created_at.desc(), m.Debt.id.desc())
        ).all()
        installments = db.scalars(
            select(m.DebtInstallment)
            .where(m.DebtInstallment.household_id == hid)
            .order_by(m.DebtInstallment.debt_id, m.DebtInstallment.sequence_no)
        ).all()
        payments = db.scalars(
            select(m.DebtPayment)
            .where(m.DebtPayment.household_id == hid)
            .order_by(
                m.DebtPayment.paid_on.desc(),
                m.DebtPayment.created_at.desc(),
                m.DebtPayment.id.desc(),
            )
        ).all()
        by_installments: dict[UUID, list[m.DebtInstallment]] = {
            d.id: [] for d in debts
        }
        by_payments: dict[UUID, list[m.DebtPayment]] = {d.id: [] for d in debts}
        for item in installments:
            if item.debt_id in by_installments:
                by_installments[item.debt_id].append(item)
        for item in payments:
            if item.debt_id in by_payments:
                by_payments[item.debt_id].append(item)
        active: list[DebtRow] = []
        archived: list[DebtRow] = []
        payable = receivable = Decimal("0")
        overdue_count = 0
        payable_overdue = receivable_overdue = 0
        today = date.today()
        for debt in debts:
            history = by_payments[debt.id]
            paid = sum(
                (p.amount for p in history if p.voided_at is None), Decimal("0")
            )
            available = paid
            overdue = Decimal("0")
            next_due = ""
            lines: list[InstallmentRow] = []
            for item in by_installments[debt.id]:
                applied = min(item.amount, available)
                available -= applied
                remaining = item.amount - applied
                if remaining > 0 and not next_due:
                    next_due = item.due_date.isoformat()
                if remaining > 0 and item.due_date < today:
                    overdue += remaining
                status = (
                    "مدفوع"
                    if remaining == 0
                    else "متأخر"
                    if item.due_date < today
                    else "مستحق اليوم"
                    if item.due_date == today
                    else "جزئي"
                    if applied > 0
                    else "قادم"
                )
                lines.append(
                    {
                        "sequence": item.sequence_no,
                        "due": item.due_date.isoformat(),
                        "amount": f"{item.amount:,.4f}",
                        "paid": f"{applied:,.4f}",
                        "remaining": f"{remaining:,.4f}",
                        "status": status,
                    }
                )
            outstanding = debt.principal - paid
            row: DebtRow = {
                "id": str(debt.id),
                "title": debt.title,
                "direction": debt.direction,
                "counterparty": debt.counterparty,
                "note": debt.note or "",
                "principal": f"{debt.principal:,.4f}",
                "principal_raw": f"{debt.principal:.4f}",
                "first_due_date": debt.first_due_date.isoformat(),
                "installment_count": str(debt.installment_count),
                "paid": f"{paid:,.4f}",
                "remaining": f"{outstanding:,.4f}",
                "overdue": f"{overdue:,.4f}",
                "next_due": next_due,
                "status": "مدفوع"
                if outstanding == 0
                else "متأخر"
                if overdue > 0
                else "جزئي"
                if paid > 0
                else "مستحق اليوم"
                if next_due == today.isoformat()
                else "قادم",
                "has_payments": bool(history),
                "installments": lines,
                "history": [
                    {
                        "id": str(p.id),
                        "amount": f"{p.amount:,.4f}",
                        "date": p.paid_on.isoformat(),
                        "note": p.note or "",
                        "voided": p.voided_at is not None,
                    }
                    for p in history
                ],
            }
            if debt.is_archived:
                archived.append(row)
            else:
                active.append(row)
                if debt.direction == "payable":
                    payable += outstanding
                    payable_overdue += int(overdue > 0)
                else:
                    receivable += outstanding
                    receivable_overdue += int(overdue > 0)
                overdue_count += int(overdue > 0)
        self.debts, self.archived_debts = active, archived
        self.payable_total, self.receivable_total = (
            f"{payable:,.4f}",
            f"{receivable:,.4f}",
        )
        self.overdue_count = overdue_count
        self.payable_overdue_count, self.receivable_overdue_count = (
            payable_overdue,
            receivable_overdue,
        )

    @rx.event
    async def load(self):
        self.debts, self.archived_debts = [], []
        self.payable_total = self.receivable_total = "0.0000"
        self.overdue_count = self.payable_overdue_count = (
            self.receivable_overdue_count
        ) = 0
        self.editor = self.edit_id = self.void_id = self.error = (
            self.message
        ) = ""
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def load_sync(sync_db):
                    _, member = auth._household(sync_db)
                    self._load(sync_db, member.household_id)

                await db.run_sync(load_sync)
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر تحميل الديون. حاول مجددًا."

    @rx.event
    def set_filter(self, direction: str):
        if direction in ("all", "payable", "receivable"):
            self.filter_direction = direction

    @rx.event
    def open_debt(self, debt_id: str = ""):
        self.error = self.message = ""
        self.edit_id = ""
        self.draft = {
            "title": "",
            "direction": "payable",
            "counterparty": "",
            "principal": "",
            "first_due_date": "",
            "installment_count": "1",
            "note": "",
        }
        if debt_id:
            row = next((d for d in self.debts if d["id"] == debt_id), None)
            if row is None:
                self.error = "الدين غير موجود أو غير متاح لهذه الأسرة."
                return
            self.edit_id = debt_id
            self.draft = {
                "title": row["title"],
                "direction": row["direction"],
                "counterparty": row["counterparty"],
                "principal": row["principal_raw"],
                "first_due_date": row["first_due_date"],
                "installment_count": row["installment_count"],
                "note": row["note"],
            }
        self.editor = "debt"

    @rx.event
    def open_payment(self, debt_id: str):
        self.error = self.message = ""
        if not any(d["id"] == debt_id for d in self.debts):
            self.error = "الدين غير موجود أو غير متاح لهذه الأسرة."
            return
        self.edit_id, self.editor = debt_id, "payment"

    @rx.event
    def ask_void(self, debt_id: str, payment_id: str):
        self.error = self.message = ""
        if not any(
            d["id"] == debt_id
            and any(
                p["id"] == payment_id and not p["voided"] for p in d["history"]
            )
            for d in self.debts
        ):
            self.error = "الدفعة غير موجودة أو ملغاة بالفعل."
            return
        self.edit_id, self.void_id, self.editor = debt_id, payment_id, "void"

    @rx.event
    def close_editor(self):
        self.editor = self.edit_id = self.void_id = self.error = ""

    @rx.event
    async def save_debt(self, data: dict[str, Any]):
        try:
            if self.editor != "debt":
                raise ValueError("افتح نموذج الدين أولًا.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def save_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._save(
                        sync_db,
                        member.household_id,
                        user.id,
                        data,
                        self.edit_id,
                    )
                    self._load(sync_db, member.household_id)

                await db.run_sync(save_sync)
                await db.commit()
            self.editor = self.edit_id = self.void_id = self.error = ""
            self.message = "حُفظ الدين وجدول أقساطه؛ لم يتغير رصيد أي حساب."
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر حفظ الدين. حاول مجددًا."

    @rx.event
    async def save_payment(self, data: dict[str, Any]):
        try:
            if self.editor != "payment":
                raise ValueError("افتح نموذج الدفعة أولًا.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def save_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._payment(
                        sync_db,
                        member.household_id,
                        user.id,
                        self.edit_id,
                        data,
                    )
                    self._load(sync_db, member.household_id)

                await db.run_sync(save_sync)
                await db.commit()
            self.close_editor.fn(self)
            self.message = "سُجّلت الدفعة يدويًا. إن حدث تحويل فعلي، سجّله منفصلًا في دفتر المعاملات لتجنب العد المزدوج."
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر تسجيل الدفعة. حاول مجددًا."

    @rx.event
    async def confirm_void(self):
        try:
            if self.editor != "void" or not self.void_id:
                raise ValueError("اختر الدفعة ثم أكّد إلغاءها.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def void_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._void(
                        sync_db,
                        member.household_id,
                        user.id,
                        self.edit_id,
                        self.void_id,
                    )
                    self._load(sync_db, member.household_id)

                await db.run_sync(void_sync)
                await db.commit()
            self.close_editor.fn(self)
            self.message = "أُلغيت الدفعة مع إبقاء سجلها؛ أُعيد احتساب الأقساط."
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر إلغاء الدفعة. حاول مجددًا."

    @rx.event
    async def set_archived(self, debt_id: str, archived: bool):
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def archive_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._archive(
                        sync_db, member.household_id, user.id, debt_id, archived
                    )
                    self._load(sync_db, member.household_id)

                await db.run_sync(archive_sync)
                await db.commit()
            self.error = ""
            self.message = (
                "تمت أرشفة الدين مع حفظ السجل."
                if archived
                else "تمت استعادة الدين وسجله."
            )
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر تحديث حالة الدين. حاول مجددًا."
