import reflex as rx

import logging
import calendar
import re
import secrets
from contextlib import suppress
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, TypedDict
from uuid import UUID

import reflex_xy
from sqlalchemy import select, func, tuple_, or_
from app import models as m
from app.states.auth import (
    AuthState,
    digest,
    now,
    require_permission,
    require_account,
    visible_account_ids,
    blocked_budget_currencies,
)


def next_recurring_date(
    current: date, start: date, frequency: str
) -> date | None:
    if frequency in ("daily", "weekly"):
        step = 1 if frequency == "daily" else 7
        return (
            current + timedelta(days=step)
            if (date.max - current).days >= step
            else None
        )
    if frequency == "monthly":
        year, month = (
            current.year + (current.month == 12),
            current.month % 12 + 1,
        )
        if year > 9999:
            return None
        return date(
            year, month, min(start.day, calendar.monthrange(year, month)[1])
        )
    raise ValueError("تكرار غير صالح.")


class HistoryChange(TypedDict):
    field: str
    before: str
    after: str


class HistoryEntry(TypedDict):
    id: str
    action: str
    actor: str
    date: str
    changes: list[HistoryChange]


class LedgerState(rx.State):
    ready: bool
    message: str = ""
    household_name: str = ""
    currency: str = "SAR"
    view_currency: str = ""
    currency_household: str = ""
    view_currencies: list[str] = []
    active_currencies: list[dict[str, str]] = []
    owner: bool = False
    can_add_transactions: bool = False
    can_edit_budgets: bool = False
    budget_alert_note: str = ""
    households: list[dict[str, str]] = []
    accounts: list[dict[str, str]] = []
    archived_accounts: list[dict[str, str]] = []
    archived_total: str = "0.00"
    has_archived_balance: bool = False
    closing_name: str = ""
    closing_balance: str = ""
    closing_currency: str = ""
    categories: list[dict[str, str]] = []
    archived_categories: list[dict[str, str]] = []
    transactions: list[dict[str, str]] = []
    transfers: list[dict[str, str]] = []
    transfer_open: bool = False
    transfer_error: str = ""
    transfer_draft: dict[str, str] = {
        "source_account_id": "",
        "destination_account_id": "",
        "amount": "",
        "transfer_date": "",
        "note": "",
    }
    history_id: str = ""
    history_title: str = ""
    history_legacy: str = ""
    history_events: list[HistoryEntry] = []
    recurring_rules: list[dict[str, str]] = []
    budgets: list[dict[str, str]] = []
    dashboard_budgets: list[dict[str, str]] = []
    invitations: list[dict[str, str]] = []
    notifications: list[dict[str, str]] = []
    preferences: list[dict[str, str]] = []
    total: str = "0.00"
    income: str = "0.00"
    expense: str = "0.00"
    saving: str = "0.00"
    saving_rate: str = "0.0"
    period: str = "current"
    report_start: str = ""
    report_end: str = ""
    report_range_label: str = ""
    report_income: str = "0.00"
    report_expense: str = "0.00"
    report_saving: str = "0.00"
    report_labels: list[str] = []
    report_values: list[float] = []
    trend_dates: list[str] = []
    trend_income: list[float] = []
    trend_expense: list[float] = []
    filter_kind: str = ""
    filter_account: str = ""
    filter_category: str = ""
    filter_start: str = ""
    filter_end: str = ""
    budget_month: str = ""
    editor: str = ""
    edit_id: str = ""
    draft: dict[str, str] = {
        "name": "",
        "account_type": "cash",
        "currency": "SAR",
        "opening_balance": "0",
        "opening_date": "",
        "account_id": "",
        "category_id": "",
        "kind": "expense",
        "amount": "",
        "transaction_date": "",
        "description": "",
        "frequency": "monthly",
        "start_date": "",
        "end_date": "",
        "month": "",
        "threshold": "80",
    }
    delete_kind: str = ""
    delete_id: str = ""
    invite_link: str = ""

    @reflex_xy.data
    def spending_data(self) -> dict[str, list[str] | list[float]]:
        return {"category": self.report_labels, "amount": self.report_values}

    @reflex_xy.data
    def trend_data(self) -> dict[str, list[str] | list[float]]:
        return {
            "day": self.trend_dates,
            "income": self.trend_income,
            "expense": self.trend_expense,
        }

    @rx.var
    def transaction_currency(self) -> str:
        return next(
            (
                a["currency"]
                for a in self.accounts + self.archived_accounts
                if a["id"] == self.draft["account_id"]
            ),
            "",
        )

    @rx.var
    def transfer_currency(self) -> str:
        return next(
            (
                a["currency"]
                for a in self.accounts
                if a["id"] == self.transfer_draft["source_account_id"]
            ),
            "",
        )

    @rx.var
    def transfer_destinations(self) -> list[dict[str, str]]:
        return [
            a
            for a in self.accounts
            if a["currency"] == self.transfer_currency
            and a["id"] != self.transfer_draft["source_account_id"]
        ]

    @rx.var
    def pending_count(self) -> int:
        return sum(x["status"] == "pending" for x in self.invitations)

    @rx.var
    def visible_transactions(self) -> list[dict[str, str]]:
        return [
            x
            for x in self.transactions
            if (not self.filter_kind or x["kind"] == self.filter_kind)
            and (
                not self.filter_account
                or x["account_id"] == self.filter_account
            )
            and (
                not self.filter_category
                or x["category_id"] == self.filter_category
            )
            and (
                not self.filter_start
                or x["transaction_date"] >= self.filter_start
            )
            and (
                not self.filter_end or x["transaction_date"] <= self.filter_end
            )
        ]

    @rx.var
    def filter_account_options(self) -> list[dict[str, str]]:
        return self.accounts + self.archived_accounts

    @rx.var
    def transaction_account_options(self) -> list[dict[str, str]]:
        closed = [
            a
            for a in self.archived_accounts
            if self.editor == "transaction"
            and self.edit_id
            and a["id"] == self.draft["account_id"]
        ]
        return closed if closed else self.accounts

    @rx.var
    def editing_archived_category(self) -> bool:
        if self.editor != "transaction" or not self.edit_id:
            return False
        original = next(
            (t for t in self.transactions if t["id"] == self.edit_id), None
        )
        return bool(
            original
            and original["category_id"] == self.draft.get("category_id", "")
            and any(
                c["id"] == original["category_id"]
                for c in self.archived_categories
            )
        )

    @rx.var
    def transaction_category_options(self) -> list[dict[str, str]]:
        active = [c for c in self.categories if c["kind"] == self.draft["kind"]]
        if not self.editing_archived_category:
            return active
        return active + [
            {**c, "name": f"{c['name']} (مؤرشفة · لهذه المعاملة فقط)"}
            for c in self.archived_categories
            if c["id"] == self.draft["category_id"]
            and c["kind"] == self.draft["kind"]
        ]

    @rx.var
    def filter_category_options(self) -> list[dict[str, str]]:
        return self.categories + self.archived_categories

    def _validate_transaction_category(self, record, category, kind):
        if category.kind != kind:
            raise ValueError("اختر فئة متوافقة مع نوع المعاملة.")
        if category.is_archived and (
            record is None or record.category_id != category.id
        ):
            raise ValueError(
                "لا يمكن استخدام فئة مؤرشفة لمعاملة جديدة أو نقل معاملة إليها."
            )

    @staticmethod
    def _transaction_snapshot(record) -> dict[str, str]:
        return {
            "account_id": str(record.account_id),
            "category_id": str(record.category_id),
            "kind": record.kind,
            "amount": str(record.amount.quantize(Decimal("0.0001"))),
            "transaction_date": record.transaction_date.isoformat(),
            "description": record.description,
        }

    def _append_transaction_event(
        self,
        db,
        record,
        action: str,
        actor_id,
        before: dict[str, str] | None = None,
    ) -> bool:
        previous = before or {}
        after = (
            {} if action == "deleted" else self._transaction_snapshot(record)
        )
        changed = [
            k
            for k in self._transaction_snapshot(record)
            if previous.get(k) != after.get(k)
        ]
        if action == "updated" and not changed:
            return False
        db.add(
            m.TransactionAuditEvent(
                household_id=record.household_id,
                transaction_id=record.id,
                actor_user_id=actor_id,
                action=action,
                before_data=previous,
                after_data=after,
                changed_fields=changed,
            )
        )
        return True

    @staticmethod
    def _history_value(
        field: str,
        value: str,
        accounts: dict[str, str],
        categories: dict[str, str],
    ) -> str:
        if not value:
            return "—"
        if field == "account_id":
            return accounts.get(value, "حساب سابق")
        if field == "category_id":
            return categories.get(value, "فئة سابقة")
        if field == "kind":
            return {"income": "دخل", "expense": "مصروف"}.get(value, value)
        return value

    def _history_rows(
        self, events, names, accounts, categories, allowed_ids=None
    ):
        labels = {
            "account_id": "الحساب",
            "category_id": "الفئة",
            "kind": "النوع",
            "amount": "المبلغ",
            "transaction_date": "التاريخ",
            "description": "الوصف",
        }
        return [
            {
                "id": str(e.id),
                "action": {
                    "created": "إضافة يدوية",
                    "updated": "تعديل",
                    "deleted": "حذف",
                    "auto_created": "إنشاء آلي",
                }.get(e.action, "تغيير"),
                "actor": "إنشاء آلي"
                if e.action == "auto_created"
                else names.get(e.actor_user_id, "عضو سابق"),
                "date": e.created_at.strftime("%Y-%m-%d %H:%M"),
                "changes": [
                    {
                        "field": labels[k],
                        "before": self._history_value(
                            k, e.before_data.get(k, ""), accounts, categories
                        ),
                        "after": self._history_value(
                            k, e.after_data.get(k, ""), accounts, categories
                        ),
                    }
                    for k in e.changed_fields
                    if k in labels
                ],
            }
            for e in events
            if allowed_ids is None
            or all(
                not snapshot.get("account_id")
                or snapshot["account_id"] in allowed_ids
                for snapshot in (e.before_data, e.after_data)
            )
        ]

    def _account_balances(self, accounts, txs, transfers=()):
        balances = {a.id: a.opening_balance for a in accounts}
        for t in txs:
            if t.account_id in balances:
                balances[t.account_id] += (
                    t.amount if t.kind == "income" else -t.amount
                )
        for transfer in transfers:
            if (
                transfer.source_account_id in balances
                and transfer.destination_account_id in balances
            ):
                balances[transfer.source_account_id] -= transfer.amount
                balances[transfer.destination_account_id] += transfer.amount
        return balances

    def _validate_transaction_account(self, record, account, original_account):
        if account.is_archived and (
            record is None or record.account_id != account.id
        ):
            raise ValueError(
                "لا يمكن تسجيل معاملة جديدة على حساب مغلق أو نقل معاملة إليه."
            )
        if (
            original_account is not None
            and original_account.is_archived
            and record.account_id != account.id
        ):
            raise ValueError(
                "تصحيح معاملة الحساب المغلق يجب أن يبقى على الحساب نفسه."
            )

    def _money(self, value: str, positive: bool = False) -> Decimal:
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)", value):
            raise ValueError("أدخل مبلغًا رقميًا صالحًا.")
        amount = Decimal(value)
        if (
            not amount.is_finite()
            or abs(amount) >= Decimal("1000000000000000")
            or amount.as_tuple().exponent < -4
            or (positive and amount <= 0)
        ):
            raise ValueError(
                "المبلغ غير صالح. استخدم حتى أربع منازل عشرية ومبلغًا موجبًا للمعاملات والميزانيات."
            )
        return amount

    def _record(self, db, model, record_id, household_id):
        record = db.scalar(
            select(model)
            .where(
                model.id == UUID(record_id), model.household_id == household_id
            )
            .with_for_update()
        )
        if record is None:
            raise ValueError("العنصر غير موجود أو غير متاح لهذه الأسرة.")
        return record

    def _notify(self, db, household_id, user_id, kind, title, **refs):
        pref = db.scalar(
            select(m.NotificationPreference).where(
                m.NotificationPreference.user_id == user_id,
                m.NotificationPreference.kind == kind,
                m.NotificationPreference.channel == "in_app",
            )
        )
        if pref and not pref.enabled:
            return
        db.add(
            m.Notification(
                household_id=household_id,
                recipient_user_id=user_id,
                member_user_id=user_id,
                kind=kind,
                title=title,
                channel="in_app",
                delivery_status="sent",
                sent_at=now(),
                **refs,
            )
        )

    def _expire(self, db, household_id):
        for invite in db.scalars(
            select(m.PartnerInvitation)
            .where(
                m.PartnerInvitation.household_id == household_id,
                m.PartnerInvitation.status == "pending",
                m.PartnerInvitation.expires_at <= now(),
            )
            .with_for_update()
        ).all():
            invite.status, invite.resolved_at = "expired", now()

    @staticmethod
    def _validate_report_range(
        start_value: str, end_value: str, today: date
    ) -> tuple[date, date]:
        if not start_value or not end_value:
            raise ValueError("اختر تاريخ البداية والنهاية لعرض الفترة.")
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", start_value
        ) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_value):
            raise ValueError(
                "أدخل تاريخَي البداية والنهاية بصيغة صحيحة (YYYY-MM-DD)."
            )
        try:
            start, end = (
                date.fromisoformat(start_value),
                date.fromisoformat(end_value),
            )
        except ValueError as e:
            raise ValueError(
                "أدخل تاريخَي البداية والنهاية بصيغة صحيحة (YYYY-MM-DD)."
            ) from e
        if start > end:
            raise ValueError(
                "تاريخ البداية يجب أن يسبق تاريخ النهاية أو يساويه."
            )
        if end > today:
            raise ValueError("تاريخ النهاية لا يمكن أن يكون بعد اليوم.")
        if (end - start).days + 1 > 366:
            raise ValueError(
                "الفترة المخصصة لا يمكن أن تتجاوز 366 يومًا شاملة البداية والنهاية."
            )
        return start, end

    def _report_bounds(self, today: date) -> tuple[date, date]:
        start = today.replace(day=1)
        end = today
        if self.period == "custom":
            return self._validate_report_range(
                self.report_start, self.report_end, today
            )
        if self.period == "previous":
            end = start - timedelta(days=1)
            start = end.replace(day=1)
        elif self.period == "three":
            for _ in range(2):
                start = (start - timedelta(days=1)).replace(day=1)
        return start, end

    def _budget_row(self, budget, category_names, spending):
        spent = spending.get(
            (budget.year, budget.month, budget.category_id, budget.currency),
            Decimal(0),
        )
        pct = (
            spent / budget.amount * 100
            if budget.amount
            else Decimal(100 if spent else 0)
        )
        status = (
            "تجاوز الحد"
            if spent > budget.amount
            else (
                "قرب الحد"
                if pct >= budget.alert_threshold_percent
                else "ضمن الميزانية"
            )
        )
        return {
            "id": str(budget.id),
            "name": category_names.get(budget.category_id, ""),
            "category_id": str(budget.category_id),
            "currency": budget.currency,
            "amount": str(budget.amount),
            "limit": f"{budget.amount:,.2f}",
            "spent": f"{spent:,.2f}",
            "percent": f"{pct:.1f}",
            "progress": str(min(100, pct)),
            "status": status,
            "month": f"{budget.year:04d}-{budget.month:02d}",
            "threshold": str(budget.alert_threshold_percent),
        }

    def _materialize_due(self, db, household_id, today: date) -> str:
        db.scalar(
            select(m.Household)
            .where(m.Household.id == household_id)
            .with_for_update()
        )
        rules = db.scalars(
            select(m.RecurringTransactionRule)
            .where(
                m.RecurringTransactionRule.household_id == household_id,
                m.RecurringTransactionRule.is_active.is_(True),
                m.RecurringTransactionRule.next_date <= today,
            )
            .order_by(m.RecurringTransactionRule.next_date)
            .with_for_update()
        ).all()
        accounts = {
            a.id: a
            for a in db.scalars(
                select(m.FinancialAccount).where(
                    m.FinancialAccount.household_id == household_id
                )
            ).all()
        }
        categories = {
            c.id: c
            for c in db.scalars(
                select(m.Category).where(
                    m.Category.household_id == household_id
                )
            ).all()
        }
        posted = 0
        processed = 0
        paused = 0
        for rule in rules:
            account, category = (
                accounts.get(rule.account_id),
                categories.get(rule.category_id),
            )
            if (
                account is None
                or account.is_archived
                or category is None
                or category.is_archived
                or category.kind != rule.kind
                or rule.next_date < account.opening_date
            ):
                rule.is_active = False
                paused += 1
                continue
            while rule.next_date <= today and (
                rule.end_date is None or rule.next_date <= rule.end_date
            ):
                if processed >= 500:
                    raise ValueError(
                        "تراكمت أكثر من 500 استحقاق متكرر. لم يُسجّل أي منها؛ تواصل مع الدعم لمعالجة التراكم دون فقدان المواعيد."
                    )
                processed += 1
                scheduled = rule.next_date
                exists = db.scalar(
                    select(m.Transaction.id).where(
                        m.Transaction.household_id == household_id,
                        m.Transaction.recurring_rule_id == rule.id,
                        m.Transaction.scheduled_for == scheduled,
                    )
                )
                if not exists:
                    transaction = m.Transaction(
                        household_id=household_id,
                        created_by_user_id=rule.created_by_user_id,
                        account_id=rule.account_id,
                        category_id=rule.category_id,
                        kind=rule.kind,
                        amount=rule.amount,
                        description=rule.description,
                        transaction_date=scheduled,
                        recurring_rule_id=rule.id,
                        scheduled_for=scheduled,
                    )
                    db.add(transaction)
                    db.flush()
                    self._append_transaction_event(
                        db, transaction, "auto_created", None
                    )
                    posted += 1
                following = next_recurring_date(
                    scheduled, rule.start_date, rule.frequency
                )
                if following is None:
                    rule.is_active = False
                    break
                rule.next_date = following
            if rule.end_date is not None and rule.next_date > rule.end_date:
                rule.is_active = False
        if posted:
            db.flush()
            self._budget_alerts(db, household_id)
        return (
            f"أُوقفت {paused} قاعدة متكررة لأن الحساب أو الفئة لم يعد صالحًا. عدّلها ثم استأنفها."
            if paused
            else ""
        )

    def _load(self, db, user, member):
        hid = member.household_id
        household = db.get(m.Household, hid)
        self.household_name, self.currency = household.name, household.currency
        if self.currency_household != str(hid):
            self.view_currency = ""
            self.currency_household = str(hid)
        self.owner = member.role == "owner"
        self.can_add_transactions = self.owner or getattr(
            member, "can_add_transactions", True
        )
        self.can_edit_budgets = self.owner or getattr(
            member, "can_edit_budgets", True
        )
        self.budget_alert_note = ""
        self.households = [
            {"id": str(h.id), "name": h.name}
            for h in db.scalars(
                select(m.Household)
                .join(
                    m.HouseholdMembership,
                    m.HouseholdMembership.household_id == m.Household.id,
                )
                .where(
                    m.HouseholdMembership.user_id == user.id,
                    m.HouseholdMembership.status == "active",
                    m.Household.status == "active",
                )
            ).all()
        ]
        categories = db.scalars(
            select(m.Category)
            .where(m.Category.household_id == hid)
            .order_by(m.Category.name)
        ).all()
        self.categories = [
            {"id": str(c.id), "name": c.name, "kind": c.kind}
            for c in categories
            if not c.is_archived
        ]
        self.archived_categories = [
            {"id": str(c.id), "name": c.name, "kind": c.kind}
            for c in categories
            if c.is_archived
        ]
        category_names = {c.id: c.name for c in categories}
        accounts = db.scalars(
            select(m.FinancialAccount)
            .where(m.FinancialAccount.household_id == hid)
            .order_by(m.FinancialAccount.created_at)
        ).all()
        allowed_ids = visible_account_ids(db, member, accounts)
        if self.filter_account and self.filter_account not in {
            str(aid) for aid in allowed_ids
        }:
            self.filter_account = ""
        accounts = [a for a in accounts if a.id in allowed_ids]
        account_names = {a.id: a.name for a in accounts}
        account_currencies = {a.id: a.currency for a in accounts}
        self.view_currencies = sorted({a.currency for a in accounts})
        self.active_currencies = [
            {"id": code, "name": code}
            for code in sorted(
                {a.currency for a in accounts if not a.is_archived}
            )
        ]
        if self.view_currency not in self.view_currencies:
            self.view_currency = (
                household.currency
                if household.currency in self.view_currencies
                else self.view_currencies[0]
                if self.view_currencies
                else household.currency
            )
        self.recurring_rules = [
            {
                "id": str(r.id),
                "account_id": str(r.account_id),
                "category_id": str(r.category_id),
                "kind": r.kind,
                "amount": str(r.amount),
                "display_amount": f"{r.amount:,.2f}",
                "description": r.description,
                "name": r.description
                or category_names.get(r.category_id, "معاملة متكررة"),
                "account": account_names.get(r.account_id, "حساب سابق"),
                "currency": account_currencies.get(
                    r.account_id, household.currency
                ),
                "category": category_names.get(r.category_id, "فئة سابقة"),
                "frequency": r.frequency,
                "frequency_label": {
                    "daily": "يوميًا",
                    "weekly": "أسبوعيًا",
                    "monthly": "شهريًا",
                }.get(r.frequency, ""),
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat() if r.end_date else "",
                "next_date": r.next_date.isoformat(),
                "status": "نشطة"
                if r.is_active
                else (
                    "متوقفة · الحساب مغلق"
                    if r.account_id
                    not in {a.id for a in accounts if not a.is_archived}
                    else "متوقفة · الفئة مؤرشفة"
                    if r.category_id
                    not in {c.id for c in categories if not c.is_archived}
                    else "متوقفة"
                ),
                "active": "yes" if r.is_active else "no",
            }
            for r in db.scalars(
                select(m.RecurringTransactionRule)
                .where(
                    m.RecurringTransactionRule.household_id == hid,
                    m.RecurringTransactionRule.account_id.in_(allowed_ids),
                )
                .order_by(m.RecurringTransactionRule.created_at.desc())
            ).all()
        ]
        txs = db.scalars(
            select(m.Transaction)
            .where(
                m.Transaction.household_id == hid,
                m.Transaction.deleted_at.is_(None),
                m.Transaction.account_id.in_(allowed_ids),
            )
            .order_by(
                m.Transaction.transaction_date.desc(),
                m.Transaction.created_at.desc(),
            )
        ).all()
        transfers = db.scalars(
            select(m.AccountTransfer)
            .where(
                m.AccountTransfer.household_id == hid,
                m.AccountTransfer.source_account_id.in_(allowed_ids),
                m.AccountTransfer.destination_account_id.in_(allowed_ids),
            )
            .order_by(
                m.AccountTransfer.transfer_date.desc(),
                m.AccountTransfer.created_at.desc(),
            )
        ).all()
        self.transfers = [
            {
                "id": str(t.id),
                "source": account_names[t.source_account_id],
                "destination": account_names[t.destination_account_id],
                "currency": t.currency,
                "amount": f"{t.amount:,.4f}",
                "transfer_date": t.transfer_date.isoformat(),
                "note": t.note or "",
            }
            for t in transfers
            if t.source_account_id in account_names
            and t.destination_account_id in account_names
        ]
        audit_rows = (
            db.execute(
                select(m.TransactionAuditEvent, m.User.display_name)
                .outerjoin(
                    m.HouseholdMembership,
                    (
                        m.HouseholdMembership.household_id
                        == m.TransactionAuditEvent.household_id
                    )
                    & (
                        m.HouseholdMembership.user_id
                        == m.TransactionAuditEvent.actor_user_id
                    ),
                )
                .outerjoin(m.User, m.User.id == m.HouseholdMembership.user_id)
                .where(
                    m.TransactionAuditEvent.household_id == hid,
                    m.TransactionAuditEvent.transaction_id.in_(
                        [t.id for t in txs]
                    ),
                )
                .order_by(
                    m.TransactionAuditEvent.created_at,
                    m.TransactionAuditEvent.id,
                )
            ).all()
            if txs
            else []
        )
        audit = {}
        permitted_snapshots = {str(account_id) for account_id in allowed_ids}
        for event, actor_name in audit_rows:
            if any(
                snapshot.get("account_id")
                and snapshot["account_id"] not in permitted_snapshots
                for snapshot in (event.before_data, event.after_data)
            ):
                continue
            entry = audit.setdefault(
                event.transaction_id, {"origin": "", "editor": ""}
            )
            if event.action == "auto_created":
                entry["origin"] = "سُجّلت آليًا"
            elif event.action == "created":
                entry["origin"] = (
                    f"أضافها {actor_name or 'عضو سابق'} · {event.created_at:%Y-%m-%d %H:%M}"
                )
            elif event.action == "updated":
                entry["editor"] = (
                    f"آخر تعديل {actor_name or 'عضو سابق'} · {event.created_at:%Y-%m-%d %H:%M}"
                )
        audited_origins = {
            e.transaction_id
            for e, _ in audit_rows
            if e.action in ("created", "auto_created")
            and all(
                not snapshot.get("account_id")
                or snapshot["account_id"] in permitted_snapshots
                for snapshot in (e.before_data, e.after_data)
            )
        }
        creator_names = (
            dict(
                db.execute(
                    select(m.HouseholdMembership.user_id, m.User.display_name)
                    .join(m.User, m.User.id == m.HouseholdMembership.user_id)
                    .where(
                        m.HouseholdMembership.household_id == hid,
                        m.HouseholdMembership.user_id.in_(
                            [
                                getattr(t, "created_by_user_id", None)
                                for t in txs
                            ]
                        ),
                    )
                ).all()
            )
            if txs
            else {}
        )
        balances = self._account_balances(accounts, txs, transfers)
        account_rows = [
            {
                "id": str(a.id),
                "name": a.name,
                "account_type": a.account_type,
                "currency": a.currency,
                "opening_balance": str(a.opening_balance),
                "opening_date": a.opening_date.isoformat(),
                "balance": f"{balances[a.id]:,.2f}",
            }
            for a in accounts
        ]
        self.accounts = [
            row for row, a in zip(account_rows, accounts) if not a.is_archived
        ]
        self.archived_accounts = [
            row for row, a in zip(account_rows, accounts) if a.is_archived
        ]
        active_balance = sum(
            (
                balances[a.id]
                for a in accounts
                if not a.is_archived and a.currency == self.view_currency
            ),
            Decimal(0),
        )
        archived_balance = sum(
            (
                balances[a.id]
                for a in accounts
                if a.is_archived and a.currency == self.view_currency
            ),
            Decimal(0),
        )
        self.total = f"{active_balance:,.2f}"
        self.archived_total = f"{archived_balance:,.2f}"
        self.has_archived_balance = any(
            a.is_archived
            and a.currency == self.view_currency
            and balances[a.id] != 0
            for a in accounts
        )
        self.transactions = [
            {
                "id": str(t.id),
                "name": t.description
                or category_names.get(t.category_id, "معاملة"),
                "description": t.description,
                "kind": t.kind,
                "amount": str(t.amount),
                "display_amount": f"{t.amount:,.2f}",
                "account_id": str(t.account_id),
                "account": account_names.get(t.account_id, "حساب سابق"),
                "currency": account_currencies.get(
                    t.account_id, household.currency
                ),
                "category_id": str(t.category_id),
                "category": category_names.get(t.category_id, ""),
                "transaction_date": t.transaction_date.isoformat(),
                "entry_created_at": t.created_at.isoformat()
                if getattr(t, "created_at", None)
                else t.transaction_date.isoformat(),
                "recurring_rule_id": str(
                    getattr(t, "recurring_rule_id", None) or ""
                ),
                "scheduled_for": getattr(t, "scheduled_for", None).isoformat()
                if getattr(t, "scheduled_for", None)
                else "",
                "metadata": audit.get(t.id, {}).get("origin")
                or (
                    (
                        f"سُجّلت آليًا · {t.created_at:%Y-%m-%d %H:%M}"
                        if getattr(t, "created_at", None)
                        else "سُجّلت آليًا"
                    )
                    if getattr(t, "recurring_rule_id", None)
                    else f"أضافها {creator_names.get(getattr(t, 'created_by_user_id', None), 'عضو سابق')} · {t.created_at:%Y-%m-%d %H:%M}"
                    if getattr(t, "created_at", None)
                    else "إضافة سابقة"
                ),
                "editor_metadata": audit.get(t.id, {}).get("editor", ""),
                "legacy_metadata": "التعديلات السابقة غير متاحة"
                if t.id not in audited_origins
                else "",
            }
            for t in txs
        ]
        today = date.today()
        start = today.replace(day=1)
        month_txs = [
            t
            for t in txs
            if start <= t.transaction_date <= today
            and account_currencies.get(t.account_id) == self.view_currency
        ]
        inc = sum(
            (t.amount for t in month_txs if t.kind == "income"), Decimal(0)
        )
        exp = sum(
            (t.amount for t in month_txs if t.kind == "expense"), Decimal(0)
        )
        self.income, self.expense, self.saving = (
            f"{inc:,.2f}",
            f"{exp:,.2f}",
            f"{inc - exp:,.2f}",
        )
        self.saving_rate = f"{(inc - exp) / inc * 100:.1f}" if inc else "0.0"
        if not self.budget_month:
            self.budget_month = today.strftime("%Y-%m")
        budget_date = date.fromisoformat(f"{self.budget_month}-01")
        requested_months = {
            (budget_date.year, budget_date.month),
            (today.year, today.month),
        }
        budget_records = db.scalars(
            select(m.MonthlyCategoryBudget).where(
                m.MonthlyCategoryBudget.household_id == hid,
                tuple_(
                    m.MonthlyCategoryBudget.year,
                    m.MonthlyCategoryBudget.month,
                ).in_(sorted(requested_months)),
            )
        ).all()
        spending = {}
        for t in txs:
            month_key = (t.transaction_date.year, t.transaction_date.month)
            if t.kind == "expense" and month_key in requested_months:
                key = (
                    *month_key,
                    t.category_id,
                    account_currencies.get(t.account_id),
                )
                spending[key] = spending.get(key, Decimal(0)) + t.amount
        budget_rows = [
            self._budget_row(b, category_names, spending)
            for b in budget_records
            if b.currency in self.view_currencies
        ]
        self.budgets = [
            row
            for row in budget_rows
            if row["month"] == self.budget_month
            and row["currency"] == self.view_currency
        ]
        self.dashboard_budgets = [
            row
            for row in budget_rows
            if row["month"] == today.strftime("%Y-%m")
            and row["currency"] == self.view_currency
        ]
        self._expire(db, hid)
        self.invitations = [
            {
                "id": str(i.id),
                "email": i.email,
                "status": i.status,
                "expires": i.expires_at.strftime("%Y-%m-%d"),
            }
            for i in db.scalars(
                select(m.PartnerInvitation)
                .where(m.PartnerInvitation.household_id == hid)
                .order_by(m.PartnerInvitation.created_at.desc())
            ).all()
        ]
        blocked_currencies = blocked_budget_currencies(db, member)
        if blocked_currencies:
            self.budget_alert_note = "تنبيهات ميزانيات العملات التي تحتوي حسابات محجوبة مخفية حفاظًا على خصوصية الأسرة."
        visible_notifications = []
        for notification in db.scalars(
            select(m.Notification)
            .where(
                m.Notification.household_id == hid,
                m.Notification.recipient_user_id == user.id,
                m.Notification.channel == "in_app",
            )
            .order_by(m.Notification.created_at.desc())
        ).all():
            if self._notification_visible(
                db, notification, hid, allowed_ids, blocked_currencies
            ):
                visible_notifications.append(notification)
        self.notifications = [
            {
                "id": str(n.id),
                "title": n.title,
                "body": n.body,
                "date": n.created_at.strftime("%Y-%m-%d"),
                "read": "yes" if n.read_at else "no",
            }
            for n in visible_notifications
        ]
        prefs = {
            p.kind: p.enabled
            for p in db.scalars(
                select(m.NotificationPreference).where(
                    m.NotificationPreference.user_id == user.id,
                    m.NotificationPreference.channel == "in_app",
                )
            ).all()
        }
        self.preferences = [
            {
                "kind": k,
                "name": label,
                "enabled": "yes" if prefs.get(k, True) else "no",
            }
            for k, label in [
                ("invitation_accepted", "قبول الدعوة"),
                ("partner_transaction", "معاملات الشريك"),
                ("budget_warning", "الاقتراب من الميزانية"),
                ("budget_exceeded", "تجاوز الميزانية"),
                ("reminder", "تذكيرات الفواتير والأقساط"),
            ]
        ]
        start, end = self._report_bounds(today)
        selected = [
            t
            for t in txs
            if start <= t.transaction_date <= end
            and account_currencies.get(t.account_id) == self.view_currency
        ]
        ri = sum((t.amount for t in selected if t.kind == "income"), Decimal(0))
        rexp = sum(
            (t.amount for t in selected if t.kind == "expense"), Decimal(0)
        )
        self.report_income, self.report_expense, self.report_saving = (
            f"{ri:,.2f}",
            f"{rexp:,.2f}",
            f"{ri - rexp:,.2f}",
        )
        spending = {
            c.name: sum(
                (
                    t.amount
                    for t in selected
                    if t.category_id == c.id and t.kind == "expense"
                ),
                Decimal(0),
            )
            for c in categories
            if c.kind == "expense"
        }
        self.report_labels = list(spending)
        self.report_values = [float(v) for v in spending.values()]
        days = [
            start + timedelta(days=i) for i in range((end - start).days + 1)
        ]
        self.trend_dates = [d.isoformat() for d in days]
        self.trend_income = [
            float(
                sum(
                    (
                        t.amount
                        for t in selected
                        if t.transaction_date == d and t.kind == "income"
                    ),
                    Decimal(0),
                )
            )
            for d in days
        ]
        self.trend_expense = [
            float(
                sum(
                    (
                        t.amount
                        for t in selected
                        if t.transaction_date == d and t.kind == "expense"
                    ),
                    Decimal(0),
                )
            )
            for d in days
        ]
        db.commit()
        self.report_range_label = (
            f"من {start.isoformat()} إلى {end.isoformat()}"
        )
        self.ready = True

    def _clear_visible(self):
        self.accounts = []
        self.archived_accounts = []
        self.transactions = []
        self.transfers = []
        self.transfer_open = False
        self.transfer_error = ""
        self.transfer_draft = {
            "source_account_id": "",
            "destination_account_id": "",
            "amount": "",
            "transfer_date": "",
            "note": "",
        }
        self.recurring_rules = []
        self.budgets = []
        self.dashboard_budgets = []
        self.notifications = []
        self.view_currencies = []
        self.active_currencies = []
        self.report_labels = []
        self.report_values = []
        self.categories = []
        self.archived_categories = []
        self.households = []
        self.invitations = []
        self.preferences = []
        self.trend_dates = []
        self.trend_income = []
        self.trend_expense = []
        self.total = self.archived_total = self.income = self.expense = (
            self.saving
        ) = "0.00"
        self.report_income = self.report_expense = self.report_saving = "0.00"
        self.has_archived_balance = False
        self.owner = self.can_add_transactions = self.can_edit_budgets = False
        self.budget_alert_note = ""
        self.history_id = self.history_title = self.history_legacy = ""
        self.history_events = []
        self.editor = self.edit_id = self.delete_id = ""

    def _notification_visible(
        self, db, notification, hid, allowed_ids, blocked_currencies
    ):
        if notification.kind == "partner_transaction":
            if not notification.transaction_id:
                return False
            transaction = db.scalar(
                select(m.Transaction).where(
                    m.Transaction.id == notification.transaction_id,
                    m.Transaction.household_id == hid,
                )
            )
            return (
                transaction is not None
                and transaction.account_id in allowed_ids
            )
        if notification.kind in ("budget_warning", "budget_exceeded"):
            if not notification.budget_id:
                return False
            budget = db.scalar(
                select(m.MonthlyCategoryBudget).where(
                    m.MonthlyCategoryBudget.id == notification.budget_id,
                    m.MonthlyCategoryBudget.household_id == hid,
                )
            )
            return (
                budget is not None
                and budget.currency not in blocked_currencies
                and any(
                    a["currency"] == budget.currency
                    for a in self.accounts + self.archived_accounts
                )
            )
        return True

    @rx.event
    async def load(self):
        self._clear_visible()
        self.ready = False
        self.editor = ""
        self.history_id = ""
        self.history_events = []
        self.history_title = ""
        self.history_legacy = ""
        try:
            auth = await self.get_state(AuthState)
            success = False
            async with rx.asession() as db:

                def load_sync(sync_db):
                    nonlocal success
                    with suppress(PermissionError):
                        user, member = auth._household(sync_db)
                        warning = self._materialize_due(
                            sync_db, member.household_id, date.today()
                        )
                        self._load(sync_db, user, member)
                        self.message = warning
                        success = True

                await db.run_sync(load_sync)
            if not success:
                self.message = ""
                return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر تحميل البيانات. أعد المحاولة."

    @rx.event
    async def switch_household(self, data: dict[str, Any]):
        auth = await self.get_state(AuthState)
        auth.selected_household = str(data.get("household", ""))
        self.invite_link = ""
        self.history_id = ""
        self.history_events = []
        self._clear_visible()
        self.filter_account = self.filter_category = self.filter_kind = ""
        self.categories = []
        self.archived_categories = []
        self.invitations = []
        self.ready = False
        from app.states.member_access import MemberAccessState

        access = await self.get_state(MemberAccessState)
        access.members = []
        access.owner = False
        access.message = ""
        from app.states.receipts import ReceiptState

        yield ReceiptState.close_receipt
        yield LedgerState.load
        yield MemberAccessState.load

    @rx.event
    async def set_view_currency(self, code: str):
        if code not in self.view_currencies:
            self.message = "عملة العرض غير متاحة لهذه الأسرة."
            return
        if code != self.view_currency:
            self.view_currency = code
            self.message = ""
            yield LedgerState.load

    @rx.event
    async def set_period(self, period: str):
        if period not in ("current", "previous", "three"):
            return
        self.period = period
        self.message = ""
        yield LedgerState.load

    @rx.event
    async def set_custom_period(self, data: dict[str, Any]):
        try:
            start, end = self._validate_report_range(
                str(data.get("start", "")).strip(),
                str(data.get("end", "")).strip(),
                date.today(),
            )
        except ValueError as e:
            self.message = str(e)
            return
        self.report_start, self.report_end = start.isoformat(), end.isoformat()
        self.period = "custom"
        self.message = ""
        yield LedgerState.load

    @rx.event
    def apply_filters(self, data: dict[str, Any]):
        self.filter_kind = str(data.get("kind", ""))
        self.filter_account = str(data.get("account", ""))
        self.filter_category = str(data.get("category", ""))
        self.filter_start = str(data.get("start", ""))
        self.filter_end = str(data.get("end", ""))
        self.message = (
            "الفترة غير صحيحة."
            if self.filter_start
            and self.filter_end
            and self.filter_start > self.filter_end
            else ""
        )

    @rx.event
    async def change_month(self, data: dict[str, Any]):
        try:
            value = str(data.get("month", ""))
            date.fromisoformat(f"{value}-01")
            self.budget_month = value
            yield LedgerState.load
        except ValueError:
            self.message = "اختر شهرًا صالحًا."
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "اختر شهرًا صالحًا."

    @rx.event
    def open_editor(self, kind: str, record_id: str = ""):
        self._prepare_editor(kind, record_id)

    def _prepare_editor(self, kind: str, record_id: str = ""):
        self.message = ""
        self.editor, self.edit_id = kind, record_id
        today = date.today().isoformat()
        self.draft = {
            "name": "",
            "account_type": "cash",
            "currency": self.currency,
            "opening_balance": "0",
            "opening_date": today,
            "account_id": "",
            "category_id": "",
            "kind": "expense",
            "amount": "",
            "transaction_date": today,
            "description": "",
            "frequency": "monthly",
            "start_date": today,
            "end_date": "",
            "month": self.budget_month or today[:7],
            "threshold": "80",
        }
        rows = {
            "account": self.accounts,
            "transaction": self.transactions,
            "recurring": self.recurring_rules,
            "budget": self.budgets + self.dashboard_budgets,
        }.get(kind, [])
        record = next((x for x in rows if x["id"] == record_id), {})
        for key in self.draft:
            if key in record:
                self.draft[key] = record[key]
        if kind == "budget" and not record_id:
            self.draft = {
                **self.draft,
                "currency": self.view_currency
                if self.view_currency
                in {a["id"] for a in self.active_currencies}
                else (
                    self.active_currencies[0]["id"]
                    if self.active_currencies
                    else ""
                ),
            }
        if (
            kind in ("transaction", "recurring")
            and not record_id
            and self.accounts
        ):
            self.draft = {**self.draft, "account_id": self.accounts[0]["id"]}
        if kind == "transaction" and not record_id:
            account_ids = {a["id"] for a in self.accounts}
            category_ids = {
                c["id"] for c in self.categories if c["kind"] == "expense"
            }
            recent = sorted(
                self.transactions,
                key=lambda t: t.get("entry_created_at", t["transaction_date"]),
                reverse=True,
            )
            account_id = next(
                (
                    t["account_id"]
                    for t in recent
                    if t["account_id"] in account_ids
                ),
                "",
            )
            category_id = next(
                (
                    t["category_id"]
                    for t in recent
                    if t["kind"] == "expense"
                    and t["category_id"] in category_ids
                ),
                "",
            )
            self.draft = {
                **self.draft,
                "account_id": account_id
                if account_id in account_ids
                else (self.accounts[0]["id"] if self.accounts else ""),
                "category_id": category_id
                if category_id in category_ids
                else (
                    next(
                        (
                            c["id"]
                            for c in self.categories
                            if c["kind"] == "expense"
                        ),
                        "",
                    )
                ),
            }

    @rx.event
    def open_transfer(self):
        self.transfer_error = ""
        self.message = ""
        self.transfer_open = True
        source = next(
            (
                a
                for a in self.accounts
                if any(
                    b["id"] != a["id"] and b["currency"] == a["currency"]
                    for b in self.accounts
                )
            ),
            None,
        )
        destination = next(
            (
                a
                for a in self.accounts
                if source
                and a["id"] != source["id"]
                and a["currency"] == source["currency"]
            ),
            None,
        )
        self.transfer_draft = {
            "source_account_id": source["id"] if source else "",
            "destination_account_id": destination["id"] if destination else "",
            "amount": "",
            "transfer_date": date.today().isoformat(),
            "note": "",
        }

    @rx.event
    def close_transfer(self):
        self.transfer_open = False
        self.transfer_error = ""

    @rx.event
    def change_transfer_source(self, value: str):
        source = next((a for a in self.accounts if a["id"] == value), None)
        destination = next(
            (
                a
                for a in self.accounts
                if source
                and a["id"] != source["id"]
                and a["currency"] == source["currency"]
            ),
            None,
        )
        self.transfer_draft = {
            **self.transfer_draft,
            "source_account_id": value if source else "",
            "destination_account_id": destination["id"] if destination else "",
        }
        self.transfer_error = ""

    @rx.event
    async def save_transfer(self, data: dict[str, Any]):
        try:
            auth = await self.get_state(AuthState)

            def save_sync(db):
                user, member = auth._household(db)
                hid = member.household_id
                require_permission(member, "can_add_transactions")
                try:
                    source_id = UUID(str(data.get("source_account_id", "")))
                    destination_id = UUID(
                        str(data.get("destination_account_id", ""))
                    )
                except (ValueError, TypeError) as e:
                    raise ValueError("اختر حسابين صالحين للتحويل.") from e
                if source_id == destination_id:
                    raise ValueError("اختر حسابين مختلفين للتحويل.")
                db.scalar(
                    select(m.Household)
                    .where(m.Household.id == hid)
                    .with_for_update()
                )
                locked = db.scalars(
                    select(m.FinancialAccount)
                    .where(
                        m.FinancialAccount.household_id == hid,
                        m.FinancialAccount.id.in_([source_id, destination_id]),
                        m.FinancialAccount.is_archived.is_(False),
                    )
                    .order_by(m.FinancialAccount.id)
                    .with_for_update()
                ).all()
                accounts = {a.id: a for a in locked}
                if source_id not in accounts or destination_id not in accounts:
                    raise ValueError("الحساب غير متاح أو مغلق في هذه الأسرة.")
                require_account(db, member, source_id)
                require_account(db, member, destination_id)
                source, destination = (
                    accounts[source_id],
                    accounts[destination_id],
                )
                if source.currency != destination.currency:
                    raise ValueError(
                        "التحويل متاح فقط بين حسابين بالعملة نفسها."
                    )
                amount = self._money(str(data.get("amount", "")).strip(), True)
                date_value = str(data.get("transfer_date", ""))
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
                    raise ValueError("أدخل تاريخ تحويل صالحًا بصيغة YYYY-MM-DD.")
                try:
                    day = date.fromisoformat(date_value)
                except ValueError as e:
                    raise ValueError(
                        "أدخل تاريخ تحويل صالحًا بصيغة YYYY-MM-DD."
                    ) from e
                if (
                    day < max(source.opening_date, destination.opening_date)
                    or day > date.today()
                ):
                    raise ValueError(
                        "تاريخ التحويل يجب أن يكون بين افتتاح الحسابين واليوم."
                    )
                note = str(data.get("note", "")).strip()
                if len(note) > 500:
                    raise ValueError("الملاحظة لا يمكن أن تتجاوز 500 حرف.")
                db.add(
                    m.AccountTransfer(
                        household_id=hid,
                        created_by_user_id=user.id,
                        source_account_id=source_id,
                        destination_account_id=destination_id,
                        currency=source.currency,
                        amount=amount,
                        transfer_date=day,
                        note=note or None,
                    )
                )
                db.commit()
                self._load(db, user, member)

            async with rx.asession() as db:
                await db.run_sync(save_sync)
            self.transfer_open = False
            self.transfer_error = ""
            self.message = (
                "تم التحويل بين الحسابين بنجاح، دون تسجيل دخل أو مصروف."
            )
        except PermissionError:
            logging.exception("Unexpected error")
            self.transfer_error = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.transfer_error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.transfer_error = "تعذر حفظ التحويل. راجع الحقول وحاول مجددًا."

    @rx.event
    def change_editor_account(self, value: str):
        options = (
            self.transaction_account_options
            if self.editor == "transaction"
            else self.accounts
        )
        if self.editor in ("transaction", "recurring") and value in {
            a["id"] for a in options
        }:
            self.draft = {**self.draft, "account_id": value}

    @rx.event
    def change_transaction_kind(self, value: str):
        if value not in ("expense", "income") or self.editor != "transaction":
            return
        choices = [c["id"] for c in self.categories if c["kind"] == value]
        current = self.draft["category_id"]
        if self.edit_id and any(
            c["id"] == current and c["kind"] == value
            for c in self.archived_categories
        ):
            choices.append(current)
        self.draft = {
            **self.draft,
            "kind": value,
            "category_id": current
            if current in choices
            else (choices[0] if choices else ""),
        }

    @rx.event
    def change_transaction_category(self, value: str):
        if self.editor == "transaction" and value in {
            c["id"] for c in self.transaction_category_options
        }:
            self.draft = {**self.draft, "category_id": value}

    @rx.event
    def reuse_transaction(self, record_id: str):
        source = next(
            (t for t in self.transactions if t["id"] == record_id), None
        )
        if source is None:
            self.message = "المعاملة غير متاحة. حدّث الدفتر."
            return
        self._prepare_editor("transaction")
        choices = [
            c["id"] for c in self.categories if c["kind"] == source["kind"]
        ]
        self.draft = {
            **self.draft,
            "kind": source["kind"],
            "account_id": source["account_id"]
            if source["account_id"] in {a["id"] for a in self.accounts}
            else self.draft["account_id"],
            "category_id": source["category_id"]
            if source["category_id"] in choices
            else (choices[0] if choices else ""),
            "description": source["description"],
            "amount": "",
        }

    @rx.event
    async def show_transaction_history(self, record_id: str):
        self.history_id = ""
        self.history_events = []
        self.history_legacy = ""
        try:
            auth = await self.get_state(AuthState)

            def history_sync(db):
                user, member = auth._household(db)
                hid = member.household_id
                transaction = db.scalar(
                    select(m.Transaction).where(
                        m.Transaction.id == UUID(record_id),
                        m.Transaction.household_id == hid,
                        m.Transaction.deleted_at.is_(None),
                    )
                )
                if transaction is None:
                    raise ValueError("المعاملة غير متاحة لهذه الأسرة.")
                require_account(db, member, transaction.account_id)
                allowed_ids = visible_account_ids(
                    db,
                    member,
                    db.scalars(
                        select(m.FinancialAccount).where(
                            m.FinancialAccount.household_id == hid
                        )
                    ).all(),
                )
                events = db.scalars(
                    select(m.TransactionAuditEvent)
                    .where(
                        m.TransactionAuditEvent.household_id == hid,
                        m.TransactionAuditEvent.transaction_id
                        == transaction.id,
                    )
                    .order_by(
                        m.TransactionAuditEvent.created_at.desc(),
                        m.TransactionAuditEvent.id.desc(),
                    )
                ).all()
                names = dict(
                    db.execute(
                        select(
                            m.HouseholdMembership.user_id, m.User.display_name
                        )
                        .join(
                            m.User, m.User.id == m.HouseholdMembership.user_id
                        )
                        .where(
                            m.HouseholdMembership.household_id == hid,
                            m.HouseholdMembership.user_id.in_(
                                [
                                    e.actor_user_id
                                    for e in events
                                    if e.actor_user_id
                                ]
                                + [transaction.created_by_user_id]
                            ),
                        )
                    ).all()
                )
                accounts = dict(
                    db.execute(
                        select(
                            m.FinancialAccount.id, m.FinancialAccount.name
                        ).where(
                            m.FinancialAccount.household_id == hid,
                            m.FinancialAccount.id.in_(allowed_ids),
                        )
                    ).all()
                )
                categories = dict(
                    db.execute(
                        select(m.Category.id, m.Category.name).where(
                            m.Category.household_id == hid
                        )
                    ).all()
                )
                legacy = (
                    ""
                    if any(
                        e.action in ("created", "auto_created") for e in events
                    )
                    else (
                        "التعديلات السابقة غير متاحة. "
                        f"سُجّلت آليًا · {transaction.created_at:%Y-%m-%d %H:%M}"
                        if transaction.recurring_rule_id
                        else "التعديلات السابقة غير متاحة. "
                        f"أضافها {names.get(transaction.created_by_user_id, 'عضو سابق')} · {transaction.created_at:%Y-%m-%d %H:%M}"
                    )
                )
                permitted = {str(account_id) for account_id in allowed_ids}
                hidden_history = any(
                    snapshot.get("account_id")
                    and snapshot["account_id"] not in permitted
                    for event in events
                    for snapshot in (event.before_data, event.after_data)
                )
                if hidden_history:
                    legacy = (
                        f"{legacy} بعض التعديلات مخفية لأنها تخص حسابًا محجوبًا."
                    )
                return (
                    transaction.description
                    or categories.get(transaction.category_id, "معاملة"),
                    legacy,
                    self._history_rows(
                        events,
                        names,
                        {str(k): v for k, v in accounts.items()},
                        {str(k): v for k, v in categories.items()},
                        permitted,
                    ),
                )

            async with rx.asession() as db:
                title, legacy, events = await db.run_sync(history_sync)
            self.history_title, self.history_legacy = title, legacy
            self.history_events = events
            self.history_id = record_id
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except (ValueError, TypeError) as e:
            self.message = (
                str(e) if isinstance(e, ValueError) else "معرّف معاملة غير صالح."
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر عرض سجل التعديلات."

    @rx.event
    def close_transaction_history(self):
        self.history_id = ""
        self.history_title = ""
        self.history_events = []
        self.history_legacy = ""

    @rx.event
    def close_editor(self):
        self.editor = ""
        self.delete_id = ""

    @rx.event
    async def save(self, data: dict[str, Any]):
        try:
            auth = await self.get_state(AuthState)

            def save_sync(sync_db):
                user, member = auth._household(sync_db)
                hid = member.household_id
                # Serialize household mutations, including balance-affecting edits.
                sync_db.scalar(
                    select(m.Household)
                    .where(m.Household.id == hid)
                    .with_for_update()
                )
                if self.editor == "account":
                    name = str(data.get("name", "")).strip()
                    kind = str(data.get("account_type", ""))
                    if (
                        not name
                        or len(name) > 120
                        or kind
                        not in (
                            "cash",
                            "bank",
                            "credit_card",
                            "savings",
                            "other",
                        )
                    ):
                        raise ValueError("اسم الحساب ونوعه مطلوبان.")
                    code = (
                        str(data.get("currency_custom", "")).strip().upper()
                        or str(data.get("currency", "")).strip().upper()
                    )
                    if not re.fullmatch(r"[A-Z]{3}", code):
                        raise ValueError(
                            "أدخل رمز عملة ISO من ثلاثة أحرف إنجليزية."
                        )
                    record = (
                        self._record(
                            sync_db, m.FinancialAccount, self.edit_id, hid
                        )
                        if self.edit_id
                        else m.FinancialAccount(
                            household_id=hid,
                            created_by_user_id=user.id,
                            currency=sync_db.get(m.Household, hid).currency,
                        )
                    )
                    if self.edit_id:
                        require_account(sync_db, member, record.id)
                    if record.is_archived:
                        raise ValueError("الحساب غير متاح.")
                    if self.edit_id and code != record.currency:
                        raise ValueError(
                            "عملة الحساب ثابتة بعد إنشائه حفاظًا على الرصيد والتاريخ. أنشئ حسابًا جديدًا بعملة أخرى."
                        )
                    if not self.edit_id:
                        record.currency = code
                    opening = date.fromisoformat(
                        str(data.get("opening_date", ""))
                    )
                    if opening > date.today():
                        raise ValueError(
                            "تاريخ الافتتاح لا يمكن أن يكون في المستقبل."
                        )
                    earliest = (
                        sync_db.scalar(
                            select(
                                func.min(m.Transaction.transaction_date)
                            ).where(
                                m.Transaction.household_id == hid,
                                m.Transaction.account_id == record.id,
                                m.Transaction.deleted_at.is_(None),
                            )
                        )
                        if self.edit_id
                        else None
                    )
                    earliest_transfer = (
                        sync_db.scalar(
                            select(
                                func.min(m.AccountTransfer.transfer_date)
                            ).where(
                                m.AccountTransfer.household_id == hid,
                                or_(
                                    m.AccountTransfer.source_account_id
                                    == record.id,
                                    m.AccountTransfer.destination_account_id
                                    == record.id,
                                ),
                            )
                        )
                        if self.edit_id
                        else None
                    )
                    if (earliest and opening > earliest) or (
                        earliest_transfer and opening > earliest_transfer
                    ):
                        raise ValueError(
                            "تاريخ الافتتاح يجب أن يسبق معاملات الحساب وتحويلاته."
                        )
                    record.name, record.account_type = name, kind
                    record.opening_balance = self._money(
                        str(data.get("opening_balance", "0"))
                    )
                    record.opening_date = opening
                    sync_db.add(record)
                elif self.editor == "transaction":
                    require_permission(member, "can_add_transactions")
                    account = self._record(
                        sync_db,
                        m.FinancialAccount,
                        str(data.get("account_id", "")),
                        hid,
                    )
                    category = self._record(
                        sync_db,
                        m.Category,
                        str(data.get("category_id", "")),
                        hid,
                    )
                    kind = str(data.get("kind", ""))
                    record = (
                        self._record(sync_db, m.Transaction, self.edit_id, hid)
                        if self.edit_id
                        else None
                    )
                    if record is not None and record.deleted_at:
                        raise ValueError("المعاملة محذوفة.")
                    require_account(sync_db, member, account.id)
                    self._validate_transaction_category(record, category, kind)
                    original_account = (
                        self._record(
                            sync_db,
                            m.FinancialAccount,
                            str(record.account_id),
                            hid,
                        )
                        if record is not None
                        else None
                    )
                    if original_account is not None:
                        require_account(sync_db, member, original_account.id)
                    self._validate_transaction_account(
                        record, account, original_account
                    )
                    day = date.fromisoformat(
                        str(data.get("transaction_date", ""))
                    )
                    if day < account.opening_date or day > date.today():
                        raise ValueError(
                            "التاريخ يجب أن يكون بين افتتاح الحساب واليوم."
                        )
                    before = (
                        self._transaction_snapshot(record)
                        if record is not None
                        else None
                    )
                    if record is None:
                        record = m.Transaction(
                            household_id=hid, created_by_user_id=user.id
                        )
                    record.account_id, record.category_id, record.kind = (
                        account.id,
                        category.id,
                        kind,
                    )
                    record.amount = self._money(
                        str(data.get("amount", "")), True
                    )
                    record.transaction_date = day
                    record.description = str(
                        data.get("description", "")
                    ).strip()[:2000]
                    sync_db.add(record)
                    sync_db.flush()
                    changed = self._append_transaction_event(
                        sync_db,
                        record,
                        "updated" if before is not None else "created",
                        user.id,
                        before,
                    )
                    if changed:
                        restricted_users = set(
                            sync_db.scalars(
                                select(
                                    m.HouseholdAccountRestriction.member_user_id
                                ).where(
                                    m.HouseholdAccountRestriction.household_id
                                    == hid,
                                    m.HouseholdAccountRestriction.account_id
                                    == record.account_id,
                                )
                            ).all()
                        )
                        for other in sync_db.scalars(
                            select(m.HouseholdMembership).where(
                                m.HouseholdMembership.household_id == hid,
                                m.HouseholdMembership.status == "active",
                                m.HouseholdMembership.user_id != user.id,
                            )
                        ).all():
                            if (
                                other.role != "owner"
                                and other.user_id in restricted_users
                            ):
                                continue
                            self._notify(
                                sync_db,
                                hid,
                                other.user_id,
                                "partner_transaction",
                                "حدّث شريكك دفتر المعاملات",
                                transaction_id=record.id,
                            )
                        self._budget_alerts(sync_db, hid)
                elif self.editor == "recurring":
                    require_permission(member, "can_add_transactions")
                    account = self._record(
                        sync_db,
                        m.FinancialAccount,
                        str(data.get("account_id", "")),
                        hid,
                    )
                    category = self._record(
                        sync_db,
                        m.Category,
                        str(data.get("category_id", "")),
                        hid,
                    )
                    kind = str(data.get("kind", ""))
                    require_account(sync_db, member, account.id)
                    self._validate_transaction_account(None, account, None)
                    self._validate_transaction_category(None, category, kind)
                    frequency = str(data.get("frequency", ""))
                    if frequency not in ("daily", "weekly", "monthly"):
                        raise ValueError("اختر تكرارًا صالحًا.")
                    start_value = str(data.get("start_date", ""))
                    end_value = str(data.get("end_date", "")).strip()
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_value) or (
                        end_value
                        and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_value)
                    ):
                        raise ValueError("أدخل التاريخ بصيغة YYYY-MM-DD.")
                    start = date.fromisoformat(start_value)
                    end = date.fromisoformat(end_value) if end_value else None
                    if start < date.today() or start < account.opening_date:
                        raise ValueError(
                            "بداية التكرار يجب أن تكون اليوم أو بعده، وبعد افتتاح الحساب."
                        )
                    if end and end < start:
                        raise ValueError(
                            "نهاية التكرار يجب أن تكون بعد البداية أو مساوية لها."
                        )
                    description = str(data.get("description", "")).strip()
                    if len(description) > 2000:
                        raise ValueError("الوصف لا يمكن أن يتجاوز 2000 حرف.")
                    record = (
                        self._record(
                            sync_db,
                            m.RecurringTransactionRule,
                            self.edit_id,
                            hid,
                        )
                        if self.edit_id
                        else m.RecurringTransactionRule(
                            household_id=hid, created_by_user_id=user.id
                        )
                    )
                    if self.edit_id:
                        require_account(sync_db, member, record.account_id)
                    record.account_id, record.category_id, record.kind = (
                        account.id,
                        category.id,
                        kind,
                    )
                    record.amount = self._money(
                        str(data.get("amount", "")), True
                    )
                    record.description, record.frequency = (
                        description,
                        frequency,
                    )
                    record.start_date, record.next_date, record.end_date = (
                        start,
                        start,
                        end,
                    )
                    sync_db.add(record)
                    sync_db.flush()
                    self._materialize_due(sync_db, hid, date.today())
                elif self.editor == "budget":
                    require_permission(member, "can_edit_budgets")
                    category = self._record(
                        sync_db,
                        m.Category,
                        str(data.get("category_id", "")),
                        hid,
                    )
                    if category.kind != "expense" or category.is_archived:
                        raise ValueError("الميزانية لفئات المصروف فقط.")
                    month = date.fromisoformat(f"{data.get('month', '')}-01")
                    threshold = int(data.get("threshold", 80))
                    if (
                        not 1900 <= month.year <= 9999
                        or not 1 <= threshold <= 100
                    ):
                        raise ValueError("الشهر أو نسبة التنبيه غير صحيحة.")
                    code = str(data.get("currency", "")).strip().upper()
                    active_accounts = sync_db.scalars(
                        select(m.FinancialAccount).where(
                            m.FinancialAccount.household_id == hid,
                            m.FinancialAccount.is_archived.is_(False),
                        )
                    ).all()
                    allowed = visible_account_ids(
                        sync_db, member, active_accounts
                    )
                    available = {
                        a.currency for a in active_accounts if a.id in allowed
                    }
                    if not available and not self.edit_id:
                        raise ValueError("أضف حسابًا نشطًا قبل إنشاء ميزانية.")
                    if code not in available:
                        raise ValueError("اختر عملة حساب نشط لهذه الميزانية.")
                    duplicate = sync_db.scalar(
                        select(m.MonthlyCategoryBudget).where(
                            m.MonthlyCategoryBudget.household_id == hid,
                            m.MonthlyCategoryBudget.category_id == category.id,
                            m.MonthlyCategoryBudget.year == month.year,
                            m.MonthlyCategoryBudget.month == month.month,
                            m.MonthlyCategoryBudget.currency == code,
                        )
                    )
                    if duplicate and str(duplicate.id) != self.edit_id:
                        raise ValueError(
                            "توجد ميزانية لهذه الفئة والشهر والعملة. عدّلها بدلًا من التكرار."
                        )
                    record = (
                        self._record(
                            sync_db, m.MonthlyCategoryBudget, self.edit_id, hid
                        )
                        if self.edit_id
                        else m.MonthlyCategoryBudget(
                            household_id=hid, created_by_user_id=user.id
                        )
                    )
                    if self.edit_id and record.currency not in available:
                        raise ValueError("ميزانية عملة غير متاحة لك.")
                    if self.edit_id and (
                        record.currency != code
                        or record.category_id != category.id
                        or record.year != month.year
                        or record.month != month.month
                    ):
                        for notification in sync_db.scalars(
                            select(m.Notification).where(
                                m.Notification.household_id == hid,
                                m.Notification.budget_id == record.id,
                            )
                        ).all():
                            notification.budget_id = None
                        sync_db.flush()
                    record.currency = code
                    record.category_id, record.year, record.month = (
                        category.id,
                        month.year,
                        month.month,
                    )
                    record.amount = self._money(
                        str(data.get("amount", "")), True
                    )
                    record.alert_threshold_percent = threshold
                    sync_db.add(record)
                    sync_db.flush()
                    self._budget_alerts(sync_db, hid)
                    self.budget_month = month.strftime("%Y-%m")
                    self.view_currency = code
                else:
                    raise ValueError("اختر العملية المطلوبة.")
                sync_db.commit()
                self._load(sync_db, user, member)

            async with rx.asession() as db:
                await db.run_sync(save_sync)
            self.editor = ""
            self.message = "تم الحفظ بنجاح."
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر الحفظ. راجع الحقول وحاول مجددًا."

    @rx.event
    async def toggle_recurring(self, record_id: str):
        try:
            auth = await self.get_state(AuthState)

            def toggle_sync(db):
                user, member = auth._household(db)
                hid = member.household_id
                db.scalar(
                    select(m.Household)
                    .where(m.Household.id == hid)
                    .with_for_update()
                )
                require_permission(member, "can_add_transactions")
                rule = self._record(
                    db, m.RecurringTransactionRule, record_id, hid
                )
                require_account(db, member, rule.account_id)
                if rule.is_active:
                    rule.is_active = False
                    message = "أُوقف التكرار؛ لن تُنشأ معاملات جديدة حتى تستأنفه."
                else:
                    account = self._record(
                        db, m.FinancialAccount, str(rule.account_id), hid
                    )
                    category = self._record(
                        db, m.Category, str(rule.category_id), hid
                    )
                    self._validate_transaction_account(None, account, None)
                    self._validate_transaction_category(
                        None, category, rule.kind
                    )
                    if rule.next_date < account.opening_date:
                        raise ValueError(
                            "تاريخ الاستحقاق أقدم من افتتاح الحساب؛ عدّل القاعدة أولًا."
                        )
                    if rule.end_date and rule.next_date > rule.end_date:
                        raise ValueError(
                            "انتهت فترة التكرار؛ عدّل تاريخ النهاية أولًا."
                        )
                    rule.is_active = True
                    message = (
                        self._materialize_due(db, hid, date.today())
                        or "استؤنف التكرار؛ سُجّلت الاستحقاقات السابقة عند فتح الدفتر."
                    )
                db.commit()
                self._load(db, user, member)
                return message

            async with rx.asession() as db:
                self.message = await db.run_sync(toggle_sync)
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر تحديث التكرار."

    def _budget_alerts(self, db, hid):
        for b in db.scalars(
            select(m.MonthlyCategoryBudget).where(
                m.MonthlyCategoryBudget.household_id == hid
            )
        ).all():
            start = date(b.year, b.month, 1)
            end = (
                (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                if b.year < 9999
                else date.max
            )
            spent = db.scalar(
                select(func.coalesce(func.sum(m.Transaction.amount), 0))
                .join(
                    m.FinancialAccount,
                    (m.FinancialAccount.id == m.Transaction.account_id)
                    & (
                        m.FinancialAccount.household_id
                        == m.Transaction.household_id
                    ),
                )
                .where(
                    m.FinancialAccount.currency == b.currency,
                    m.Transaction.household_id == hid,
                    m.Transaction.category_id == b.category_id,
                    m.Transaction.kind == "expense",
                    m.Transaction.deleted_at.is_(None),
                    m.Transaction.transaction_date >= start,
                    m.Transaction.transaction_date < end,
                )
            )
            kind = "budget_exceeded" if spent > b.amount else "budget_warning"
            if (
                spent <= 0
                or spent < b.amount * Decimal(b.alert_threshold_percent) / 100
            ):
                continue
            restricted_users = set(
                db.scalars(
                    select(m.HouseholdAccountRestriction.member_user_id)
                    .join(
                        m.FinancialAccount,
                        (
                            m.FinancialAccount.id
                            == m.HouseholdAccountRestriction.account_id
                        )
                        & (
                            m.FinancialAccount.household_id
                            == m.HouseholdAccountRestriction.household_id
                        ),
                    )
                    .where(
                        m.HouseholdAccountRestriction.household_id == hid,
                        m.FinancialAccount.currency == b.currency,
                    )
                ).all()
            )
            for member in db.scalars(
                select(m.HouseholdMembership).where(
                    m.HouseholdMembership.household_id == hid,
                    m.HouseholdMembership.status == "active",
                )
            ).all():
                if (
                    member.role != "owner"
                    and member.user_id in restricted_users
                ):
                    continue
                exists = db.scalar(
                    select(m.Notification.id).where(
                        m.Notification.household_id == hid,
                        m.Notification.recipient_user_id == member.user_id,
                        m.Notification.budget_id == b.id,
                        m.Notification.kind == kind,
                    )
                )
                if not exists:
                    category = db.get(m.Category, b.category_id)
                    title = (
                        f"تجاوزت ميزانية {category.name} ({b.currency})"
                        if kind == "budget_exceeded"
                        else f"اقتربت من حد ميزانية {category.name} ({b.currency})"
                    )
                    self._notify(
                        db, hid, member.user_id, kind, title, budget_id=b.id
                    )

    @rx.event
    def ask_delete(self, kind: str, record_id: str):
        self.message = ""
        self.delete_kind, self.delete_id = kind, record_id
        account = (
            next((a for a in self.accounts if a["id"] == record_id), {})
            if kind == "account"
            else {}
        )
        self.closing_name = account.get("name", "")
        self.closing_balance = account.get("balance", "")
        self.closing_currency = account.get("currency", "")

    @rx.event
    async def confirm_delete(self):
        try:
            auth = await self.get_state(AuthState)

            def delete_sync(sync_db):
                user, member = auth._household(sync_db)
                hid = member.household_id
                sync_db.scalar(
                    select(m.Household)
                    .where(m.Household.id == hid)
                    .with_for_update()
                )
                if self.delete_kind == "account":
                    record = self._record(
                        sync_db, m.FinancialAccount, self.delete_id, hid
                    )
                    require_account(sync_db, member, record.id)
                    if record.is_archived:
                        raise ValueError("الحساب مغلق بالفعل.")
                    record.is_archived = True
                elif self.delete_kind == "transaction":
                    require_permission(member, "can_add_transactions")
                    record = self._record(
                        sync_db, m.Transaction, self.delete_id, hid
                    )
                    require_account(sync_db, member, record.account_id)
                    if record.deleted_at is not None:
                        raise ValueError("المعاملة محذوفة بالفعل.")
                    before = self._transaction_snapshot(record)
                    record.deleted_at = now()
                    self._append_transaction_event(
                        sync_db, record, "deleted", user.id, before
                    )
                elif self.delete_kind == "budget":
                    require_permission(member, "can_edit_budgets")
                    record = self._record(
                        sync_db, m.MonthlyCategoryBudget, self.delete_id, hid
                    )
                    active_accounts = sync_db.scalars(
                        select(m.FinancialAccount).where(
                            m.FinancialAccount.household_id == hid,
                            m.FinancialAccount.is_archived.is_(False),
                            m.FinancialAccount.currency == record.currency,
                        )
                    ).all()
                    if not visible_account_ids(
                        sync_db, member, active_accounts
                    ):
                        raise ValueError("ميزانية عملة غير متاحة لك.")
                    for n in sync_db.scalars(
                        select(m.Notification).where(
                            m.Notification.household_id == hid,
                            m.Notification.budget_id == record.id,
                        )
                    ).all():
                        n.budget_id = None
                    sync_db.flush()
                    sync_db.delete(record)
                else:
                    raise ValueError("عملية غير صالحة.")
                sync_db.commit()
                self._load(sync_db, user, member)

            async with rx.asession() as db:
                await db.run_sync(delete_sync)
            self.message = (
                "تم إغلاق الحساب مع الاحتفاظ بمعاملاته"
                if self.delete_kind == "account"
                else "تم الحذف وتحديث الأرصدة."
            )
            self.delete_id = ""
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر الحذف."

    @rx.event
    async def invite(self, data: dict[str, Any]):
        try:
            email = str(data.get("email", "")).strip().lower()
            if (
                not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
                or len(email) > 320
            ):
                raise ValueError("أدخل بريد الشريك بصورة صحيحة.")
            auth = await self.get_state(AuthState)

            def invite_sync(sync_db) -> str:
                user, member = auth._household(sync_db)
                if member.role != "owner" or email == user.email:
                    raise ValueError(
                        "الدعوة متاحة للمالك فقط، ولا يمكنك دعوة نفسك."
                    )
                hid = member.household_id
                sync_db.scalar(
                    select(m.Household)
                    .where(m.Household.id == hid)
                    .with_for_update()
                )
                self._expire(sync_db, hid)
                sync_db.flush()
                if sync_db.scalar(
                    select(m.PartnerInvitation.id).where(
                        m.PartnerInvitation.household_id == hid,
                        m.PartnerInvitation.email == email,
                        m.PartnerInvitation.status == "pending",
                    )
                ):
                    raise ValueError(
                        "توجد دعوة معلقة لهذا البريد. ألغها لإنشاء رابط جديد."
                    )
                target = sync_db.scalar(
                    select(m.User).where(m.User.email == email)
                )
                if target and sync_db.scalar(
                    select(m.HouseholdMembership.id).where(
                        m.HouseholdMembership.household_id == hid,
                        m.HouseholdMembership.user_id == target.id,
                        m.HouseholdMembership.status == "active",
                    )
                ):
                    raise ValueError("هذا الحساب عضو بالفعل في الأسرة.")
                raw = secrets.token_urlsafe(32)
                sync_db.add(
                    m.PartnerInvitation(
                        household_id=hid,
                        invited_by_user_id=user.id,
                        email=email,
                        token_hash=digest(raw),
                        expires_at=now() + timedelta(days=7),
                    )
                )
                sync_db.commit()
                self._load(sync_db, user, member)
                return f"/accept-invitation?token={raw}"

            async with rx.asession() as db:
                invite_link = await db.run_sync(invite_sync)
            self.invite_link = invite_link
            self.message = "دعوة قابلة للمشاركة صالحة 7 أيام. انسخ الرابط الآن؛ لم يُرسل بريد إلكتروني."
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر إنشاء الدعوة."

    @rx.event
    async def revoke(self, record_id: str):
        try:
            auth = await self.get_state(AuthState)

            def revoke_sync(sync_db):
                user, member = auth._household(sync_db)
                if member.role != "owner":
                    raise ValueError("الإلغاء متاح لمالك الأسرة فقط.")
                invite = self._record(
                    sync_db, m.PartnerInvitation, record_id, member.household_id
                )
                if invite.status == "pending":
                    invite.status = (
                        "expired" if invite.expires_at <= now() else "revoked"
                    )
                    invite.resolved_at = now()
                sync_db.commit()
                self._load(sync_db, user, member)

            async with rx.asession() as db:
                await db.run_sync(revoke_sync)
            self.invite_link = ""
            self.message = "تم تحديث حالة الدعوة."
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر إلغاء الدعوة."

    @rx.event
    async def accept_invitation(self, data: dict[str, Any]):
        try:
            auth = await self.get_state(AuthState)
            token = str(data.get("token", "")).strip() or auth.pending_invite
            if "token=" in token:
                token = token.split("token=", 1)[1].split("&", 1)[0]

            def accept_sync(sync_db) -> str:
                user = auth._identity(sync_db)
                invitation = sync_db.scalar(
                    select(m.PartnerInvitation)
                    .where(m.PartnerInvitation.token_hash == digest(token))
                    .with_for_update()
                )
                if not invitation or invitation.email != user.email:
                    raise ValueError(
                        "الدعوة غير صالحة أو البريد لا يطابق بريد حسابك المسجل."
                    )
                if invitation.status != "pending":
                    raise ValueError(
                        "هذه الدعوة مقبولة أو ملغاة أو منتهية الصلاحية."
                    )
                if invitation.expires_at <= now():
                    invitation.status, invitation.resolved_at = "expired", now()
                    sync_db.commit()
                    raise ValueError("انتهت صلاحية الدعوة. اطلب رابطًا جديدًا.")
                household = sync_db.scalar(
                    select(m.Household)
                    .where(m.Household.id == invitation.household_id)
                    .with_for_update()
                )
                if (
                    household.status != "active"
                    or user.id == invitation.invited_by_user_id
                ):
                    raise ValueError("لا يمكن قبول هذه الدعوة.")
                membership = sync_db.scalar(
                    select(m.HouseholdMembership).where(
                        m.HouseholdMembership.household_id == household.id,
                        m.HouseholdMembership.user_id == user.id,
                    )
                )
                if membership:
                    membership.status, membership.ended_at = "active", None
                else:
                    sync_db.add(
                        m.HouseholdMembership(
                            household_id=household.id,
                            user_id=user.id,
                            role="partner",
                        )
                    )
                sync_db.flush()
                (
                    invitation.status,
                    invitation.resolved_at,
                    invitation.accepted_by_user_id,
                ) = "accepted", now(), user.id
                self._notify(
                    sync_db,
                    household.id,
                    invitation.invited_by_user_id,
                    "invitation_accepted",
                    "أصبح شريكك جزءًا من دفتر الأسرة",
                    invitation_id=invitation.id,
                )
                sync_db.commit()
                return str(household.id)

            async with rx.asession() as db:
                household_id = await db.run_sync(accept_sync)
            auth.selected_household = household_id
            auth.pending_invite = ""
            self.message = "تم قبول الدعوة. أهلًا بك في الأسرة."
            return rx.redirect("/dashboard")
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر قبول الدعوة."

    @rx.event
    async def mark_read(self, record_id: str):
        try:
            auth = await self.get_state(AuthState)

            def mark_read_sync(sync_db):
                user, member = auth._household(sync_db)
                query = select(m.Notification).where(
                    m.Notification.household_id == member.household_id,
                    m.Notification.recipient_user_id == user.id,
                    m.Notification.read_at.is_(None),
                )
                if record_id:
                    query = query.where(m.Notification.id == UUID(record_id))
                accounts = sync_db.scalars(
                    select(m.FinancialAccount).where(
                        m.FinancialAccount.household_id == member.household_id
                    )
                ).all()
                allowed_ids = visible_account_ids(sync_db, member, accounts)
                blocked = blocked_budget_currencies(sync_db, member)
                for n in sync_db.scalars(query).all():
                    if self._notification_visible(
                        sync_db, n, member.household_id, allowed_ids, blocked
                    ):
                        n.read_at = now()
                sync_db.commit()
                self._load(sync_db, user, member)

            async with rx.asession() as db:
                await db.run_sync(mark_read_sync)
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر تحديث الإشعارات."

    @rx.event
    async def toggle_preference(self, kind: str):
        try:
            if kind not in (
                "invitation_accepted",
                "partner_transaction",
                "budget_warning",
                "budget_exceeded",
                "reminder",
            ):
                raise ValueError("تفضيل غير صالح.")
            auth = await self.get_state(AuthState)

            def preference_sync(sync_db):
                user, member = auth._household(sync_db)
                sync_db.scalar(
                    select(m.User).where(m.User.id == user.id).with_for_update()
                )
                p = sync_db.scalar(
                    select(m.NotificationPreference).where(
                        m.NotificationPreference.user_id == user.id,
                        m.NotificationPreference.kind == kind,
                        m.NotificationPreference.channel == "in_app",
                    )
                )
                if p:
                    p.enabled = not p.enabled
                else:
                    sync_db.add(
                        m.NotificationPreference(
                            user_id=user.id, kind=kind, enabled=False
                        )
                    )
                sync_db.commit()
                self._load(sync_db, user, member)

            async with rx.asession() as db:
                await db.run_sync(preference_sync)
            self.message = "حُفظت تفضيلات الإشعارات داخل التطبيق."
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر حفظ التفضيلات."
