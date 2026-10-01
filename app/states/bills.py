import reflex as rx

import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import delete, func, select

from app import models as m
from app.states.auth import (
    AuthState,
    require_account,
    require_permission,
    visible_account_ids,
)
from app.states.debts import money, parse_date


class BillRow(TypedDict):
    id: str
    title: str
    amount: str
    amount_raw: str
    currency: str
    account: str
    account_id: str
    due_date: str
    status: str
    paid_on: str
    remind_days: str
    notes: str


class ReminderRow(TypedDict):
    id: str
    title: str
    detail: str
    amount: str
    currency: str
    due_date: str
    path: str
    kind: str


class BillState(rx.State):
    bills: list[BillRow] = []
    accounts: list[dict[str, str]] = []
    reminders: list[ReminderRow] = []
    error: str = ""
    message: str = ""
    editor: str = ""
    edit_id: str = ""
    draft: dict[str, str] = {
        "title": "",
        "amount": "",
        "due_date": "",
        "account_id": "",
        "remind_days": "3",
        "notes": "",
    }

    @rx.var
    def today(self) -> str:
        return date.today().isoformat()

    def _id(self, raw: str) -> UUID:
        try:
            return UUID(raw)
        except (ValueError, TypeError, AttributeError) as e:
            logging.exception(f"Error: {e}")
            raise ValueError("الفاتورة غير موجودة أو غير متاحة.") from e

    def _guard(self, db, member) -> None:
        if (
            db.scalar(
                select(m.Household.id).where(
                    m.Household.id == member.household_id,
                    m.Household.status == "active",
                )
            )
            is None
            or member.status != "active"
        ):
            raise PermissionError("لا توجد عضوية أسرة نشطة.")

    def _account(self, db, member, raw: str) -> m.FinancialAccount:
        account = db.scalar(
            select(m.FinancialAccount).where(
                m.FinancialAccount.household_id == member.household_id,
                m.FinancialAccount.id == self._id(raw),
                m.FinancialAccount.is_archived.is_(False),
            )
        )
        if account is None:
            raise ValueError("اختر حسابًا نشطًا ومتاحًا في أسرتك.")
        require_account(db, member, account.id)
        return account

    def _bill(self, db, member, raw: str) -> m.Bill:
        bill = db.scalar(
            select(m.Bill)
            .where(
                m.Bill.household_id == member.household_id,
                m.Bill.id == self._id(raw),
            )
            .with_for_update()
        )
        if bill is None:
            raise ValueError("الفاتورة غير موجودة أو غير متاحة.")
        require_account(db, member, bill.account_id)
        return bill

    def _save(
        self, db, member, uid: UUID, data: dict[str, Any], edit_id: str = ""
    ) -> None:
        self._guard(db, member)
        require_permission(member, "can_add_transactions")
        title = str(data.get("title", "")).strip()
        notes = str(data.get("notes", "")).strip()
        if not 1 <= len(title) <= 200 or len(notes) > 2000:
            raise ValueError(
                "عنوان الفاتورة مطلوب (حتى 200 حرف)، والملاحظة حتى 2000 حرف."
            )
        amount = money(str(data.get("amount", "")))
        due = parse_date(str(data.get("due_date", "")))
        raw_days = str(data.get("remind_days", ""))
        if (
            not re.fullmatch(r"\d{1,3}", raw_days)
            or not 0 <= int(raw_days) <= 365
        ):
            raise ValueError("اختر عدد أيام تذكير بين 0 و365.")
        account = self._account(db, member, str(data.get("account_id", "")))
        bill = self._bill(db, member, edit_id) if edit_id else None
        if bill is None:
            bill = m.Bill(
                household_id=member.household_id,
                created_by_user_id=uid,
                account_id=account.id,
                title=title,
                amount=amount,
                currency=account.currency,
                due_date=due,
                remind_days=int(raw_days),
                notes=notes or None,
            )
            db.add(bill)
        else:
            bill.account_id = account.id
            bill.currency = account.currency
            bill.title = title
            bill.amount = amount
            bill.due_date = due
            bill.remind_days = int(raw_days)
            bill.notes = notes or None
        db.flush()

    def _set_paid(self, db, member, raw: str, paid: bool) -> None:
        self._guard(db, member)
        require_permission(member, "can_add_transactions")
        bill = self._bill(db, member, raw)
        bill.status = "paid" if paid else "unpaid"
        bill.paid_on = date.today() if paid else None
        db.flush()

    def _delete(self, db, member, raw: str) -> None:
        self._guard(db, member)
        require_permission(member, "can_add_transactions")
        bill = self._bill(db, member, raw)
        db.execute(
            delete(m.ReminderDelivery).where(
                m.ReminderDelivery.household_id == member.household_id,
                m.ReminderDelivery.bill_id == bill.id,
            )
        )
        db.delete(bill)
        db.flush()

    def _candidates(self, db, member, today: date, currency: str):
        hid = member.household_id
        accounts = db.scalars(
            select(m.FinancialAccount)
            .where(
                m.FinancialAccount.household_id == hid,
                m.FinancialAccount.is_archived.is_(False),
            )
            .order_by(m.FinancialAccount.name)
            .limit(500)
        ).all()
        visible = visible_account_ids(db, member, accounts)
        self.accounts = [
            {"id": str(a.id), "name": f"{a.name} · {a.currency}"}
            for a in accounts
            if a.id in visible
        ]
        bills = (
            db.scalars(
                select(m.Bill)
                .where(
                    m.Bill.household_id == hid, m.Bill.account_id.in_(visible)
                )
                .order_by(m.Bill.due_date, m.Bill.id)
                .limit(500)
            ).all()
            if visible
            else []
        )
        names = {a.id: a.name for a in accounts if a.id in visible}
        self.bills = [
            {
                "id": str(b.id),
                "title": b.title,
                "amount": f"{b.amount:,.4f}",
                "amount_raw": f"{b.amount:.4f}",
                "currency": b.currency,
                "account": names[b.account_id],
                "account_id": str(b.account_id),
                "due_date": b.due_date.isoformat(),
                "status": b.status,
                "paid_on": b.paid_on.isoformat() if b.paid_on else "",
                "remind_days": str(b.remind_days),
                "notes": b.notes or "",
            }
            for b in bills
        ]
        candidates: dict[
            tuple[str, UUID, date], tuple[str, str, Decimal, str, str]
        ] = {}
        for b in bills:
            if (
                b.status == "unpaid"
                and today <= b.due_date <= today + timedelta(days=b.remind_days)
            ):
                candidates[("bill", b.id, b.due_date)] = (
                    f"فاتورة: {b.title}",
                    f"{names[b.account_id]} · موعد السداد {b.due_date.isoformat()}",
                    b.amount,
                    b.currency,
                    "/bills",
                )
        debts = db.scalars(
            select(m.Debt)
            .where(
                m.Debt.household_id == hid,
                m.Debt.direction == "payable",
                m.Debt.is_archived.is_(False),
            )
            .limit(500)
        ).all()
        debt_map = {d.id: d for d in debts}
        if debt_map:
            installments = db.scalars(
                select(m.DebtInstallment)
                .where(
                    m.DebtInstallment.household_id == hid,
                    m.DebtInstallment.debt_id.in_(debt_map),
                )
                .order_by(
                    m.DebtInstallment.debt_id, m.DebtInstallment.sequence_no
                )
            ).all()
            totals = dict(
                db.execute(
                    select(
                        m.DebtPayment.debt_id,
                        func.coalesce(func.sum(m.DebtPayment.amount), 0),
                    )
                    .where(
                        m.DebtPayment.household_id == hid,
                        m.DebtPayment.debt_id.in_(debt_map),
                        m.DebtPayment.voided_at.is_(None),
                    )
                    .group_by(m.DebtPayment.debt_id)
                ).all()
            )
            consumed: dict[UUID, Decimal] = {}
            for item in installments:
                paid = totals.get(item.debt_id, Decimal("0"))
                before = consumed.get(item.debt_id, Decimal("0"))
                remaining = item.amount - min(
                    item.amount, max(Decimal("0"), paid - before)
                )
                consumed[item.debt_id] = before + item.amount
                if (
                    remaining > 0
                    and today <= item.due_date <= today + timedelta(days=3)
                ):
                    debt = debt_map[item.debt_id]
                    candidates[("installment", item.id, item.due_date)] = (
                        f"قسط: {debt.title}",
                        f"القسط {item.sequence_no} · موعد السداد {item.due_date.isoformat()}",
                        remaining,
                        currency,
                        "/debts",
                    )
        return candidates

    def _load(self, db, member, uid: UUID) -> None:
        self._guard(db, member)
        hid = member.household_id
        household = db.scalar(
            select(m.Household).where(m.Household.id == hid).with_for_update()
        )
        candidates = self._candidates(
            db, member, date.today(), household.currency
        )
        preference = db.scalar(
            select(m.NotificationPreference).where(
                m.NotificationPreference.user_id == uid,
                m.NotificationPreference.kind == "reminder",
                m.NotificationPreference.channel == "in_app",
            )
        )
        self.reminders = []
        if preference is not None and not preference.enabled:
            return
        existing = db.scalars(
            select(m.ReminderDelivery).where(
                m.ReminderDelivery.household_id == hid,
                m.ReminderDelivery.recipient_user_id == uid,
                m.ReminderDelivery.channel == "in_app",
                m.ReminderDelivery.due_date >= date.today(),
            )
        ).all()
        by_key = {(r.source_kind, r.source_id, r.due_date): r for r in existing}
        for key in candidates:
            if key in by_key and by_key[key].status != "sent":
                by_key[key].status = "sent"
                by_key[key].delivered_at = datetime.now(timezone.utc)
            if key not in by_key:
                kind, source_id, due = key
                delivery = m.ReminderDelivery(
                    household_id=hid,
                    recipient_user_id=uid,
                    channel="in_app",
                    source_kind=kind,
                    source_id=source_id,
                    due_date=due,
                    bill_id=source_id if kind == "bill" else None,
                    installment_id=source_id if kind == "installment" else None,
                    status="sent",
                    delivered_at=datetime.now(timezone.utc),
                )
                db.add(delivery)
                by_key[key] = delivery
        db.flush()
        self.reminders = [
            {
                "id": str(by_key[key].id),
                "title": value[0],
                "detail": value[1],
                "amount": f"{value[2]:,.4f}",
                "currency": value[3],
                "due_date": key[2].isoformat(),
                "path": value[4],
                "kind": key[0],
            }
            for key, value in sorted(
                candidates.items(), key=lambda entry: entry[0][2]
            )
            if key in by_key
        ]

    @rx.event
    async def load(self):
        self.bills, self.accounts, self.reminders = [], [], []
        self.editor = self.edit_id = self.error = self.message = ""
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def load_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._load(sync_db, member, user.id)

                await db.run_sync(load_sync)
                await db.commit()
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.bills, self.accounts, self.reminders = [], [], []
            self.error = "تعذر تحميل الفواتير والتذكيرات. حاول مجددًا."

    @rx.event
    def open_bill(self, bill_id: str = ""):
        self.error = self.message = ""
        self.edit_id = ""
        self.draft = {
            "title": "",
            "amount": "",
            "due_date": date.today().isoformat(),
            "account_id": self.accounts[0]["id"] if self.accounts else "",
            "remind_days": "3",
            "notes": "",
        }
        if bill_id:
            row = next((b for b in self.bills if b["id"] == bill_id), None)
            if row is None:
                self.error = "الفاتورة غير متاحة. حدّث الصفحة."
                return
            self.edit_id = bill_id
            self.draft = {k: row[k] for k in self.draft}
            self.draft["amount"] = row["amount_raw"]
        self.editor = "bill"

    @rx.event
    def close_bill(self):
        self.editor = self.edit_id = self.error = ""

    @rx.event
    async def save_bill(self, data: dict[str, Any]):
        try:
            if self.editor != "bill":
                raise ValueError("افتح نموذج الفاتورة أولًا.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def save_sync(sync_db):
                    user, member = auth._household(sync_db)
                    sync_db.scalar(
                        select(m.Household)
                        .where(m.Household.id == member.household_id)
                        .with_for_update()
                    )
                    self._save(sync_db, member, user.id, data, self.edit_id)
                    self._load(sync_db, member, user.id)

                await db.run_sync(save_sync)
                await db.commit()
            self.editor = self.edit_id = self.error = ""
            self.message = (
                "حُفظت الفاتورة. لم تتغير أرصدة الحسابات أو معاملات الدفتر."
            )
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر حفظ الفاتورة. حاول مجددًا."

    @rx.event
    async def set_paid(self, bill_id: str, paid: bool):
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def update_sync(sync_db):
                    user, member = auth._household(sync_db)
                    sync_db.scalar(
                        select(m.Household)
                        .where(m.Household.id == member.household_id)
                        .with_for_update()
                    )
                    self._set_paid(sync_db, member, bill_id, paid)
                    self._load(sync_db, member, user.id)

                await db.run_sync(update_sync)
                await db.commit()
            self.error = ""
            self.message = "حُدّثت حالة الفاتورة دون تسجيل معاملة مالية."
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر تحديث حالة الفاتورة."

    @rx.event
    async def delete_bill(self, bill_id: str):
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def delete_sync(sync_db):
                    user, member = auth._household(sync_db)
                    sync_db.scalar(
                        select(m.Household)
                        .where(m.Household.id == member.household_id)
                        .with_for_update()
                    )
                    self._delete(sync_db, member, bill_id)
                    self._load(sync_db, member, user.id)

                await db.run_sync(delete_sync)
                await db.commit()
            self.error = ""
            self.message = "حُذفت الفاتورة وتذكيراتها. لم تتغير الأرصدة."
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر حذف الفاتورة."
