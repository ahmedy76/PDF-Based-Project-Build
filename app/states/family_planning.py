import reflex as rx

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import delete, or_, select
from app import models as m
from app.observability import report_unexpected
from app.states.auth import AuthState, require_account


class TaskRow(TypedDict):
    id: str
    title: str
    details: str
    due_date: str
    currency: str
    account_id: str
    account: str
    assignee_user_id: str
    assignee: str
    status: str
    editable: bool
    actionable: bool


class ShareRow(TypedDict):
    name: str
    income: str
    percentage: str
    amount: str


class SplitBillRow(TypedDict):
    id: str
    title: str
    currency: str
    amount: str
    account: str
    due_date: str
    mode: str
    stale: bool
    shares: list[ShareRow]


def positive_money(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        logging.exception("Unexpected error")
        raise ValueError("planning.invalid_income") from None
    if (
        not value.is_finite()
        or not 0 < value < Decimal("1000000000000000")
        or value.as_tuple().exponent < -4
    ):
        raise ValueError("planning.invalid_income")
    return value


def calculate_split(
    amount: Decimal, mode: str, incomes: list[Decimal]
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if mode not in ("equal", "income") or len(incomes) != 2:
        raise ValueError("planning.invalid_split")
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -4:
        raise ValueError("planning.invalid_split")
    if mode == "income":
        for income in incomes:
            positive_money(income)
        ratio = incomes[0] / sum(incomes)
    else:
        ratio = Decimal("0.5")
    percent = (ratio * 100).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    first = (amount * ratio).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return percent, Decimal(100) - percent, first, amount - first


class FamilyPlanningState(rx.State):
    tasks: list[TaskRow] = []
    bills: list[SplitBillRow] = []
    accounts: list[dict[str, str]] = []
    participants: list[dict[str, str]] = []
    owner: bool = False
    loading: bool = False
    error: str = ""
    message: str = ""
    currency_filter: str = ""
    status_filter: str = ""
    editor: bool = False
    edit_id: str = ""
    form_key: int = 0
    draft: dict[str, str] = {
        "title": "",
        "details": "",
        "due_date": "",
        "currency": "",
        "account_id": "",
        "assignee_user_id": "",
    }
    delete_id: str = ""

    def _id(self, raw: str) -> UUID:
        try:
            return UUID(raw)
        except (ValueError, TypeError, AttributeError):
            logging.exception("Unexpected error")
            raise ValueError("planning.unavailable") from None

    def _context(self, db, auth):
        user, candidate = auth._household(db)
        home = db.scalar(
            select(m.Household)
            .where(
                m.Household.id == candidate.household_id,
                m.Household.status == "active",
            )
            .with_for_update()
        )
        member = db.scalar(
            select(m.HouseholdMembership)
            .where(
                m.HouseholdMembership.household_id == candidate.household_id,
                m.HouseholdMembership.user_id == user.id,
                m.HouseholdMembership.status == "active",
            )
            .with_for_update()
        )
        if (
            home is None
            or member is None
            or member.role not in ("owner", "partner")
        ):
            raise PermissionError("planning.unavailable")
        if member.role == "owner" and home.owner_user_id != user.id:
            raise PermissionError("planning.unavailable")
        return user, member

    def _visible_clause(self, member, account_column):
        if member.role == "owner":
            return account_column.is_not(None)
        denied = select(m.HouseholdAccountRestriction.account_id).where(
            m.HouseholdAccountRestriction.household_id == member.household_id,
            m.HouseholdAccountRestriction.member_user_id == member.user_id,
        )
        return account_column.not_in(denied)

    def _account(self, db, member, aid: UUID, currency: str):
        account = db.scalar(
            select(m.FinancialAccount).where(
                m.FinancialAccount.household_id == member.household_id,
                m.FinancialAccount.id == aid,
            )
        )
        if account is None or account.currency != currency:
            raise ValueError("planning.account_currency")
        try:
            require_account(db, member, aid)
        except ValueError:
            raise ValueError("planning.unavailable") from None
        return account

    def _task(self, db, member, raw: str):
        task = db.scalar(
            select(m.HouseholdTask)
            .where(
                m.HouseholdTask.household_id == member.household_id,
                m.HouseholdTask.id == self._id(raw),
            )
            .with_for_update()
        )
        if task is None:
            raise ValueError("planning.unavailable")
        if task.account_id is not None:
            self._account(db, member, task.account_id, task.currency)
        return task

    def _authorize_task(self, member, task, status_only: bool = False):
        allowed = (
            member.role == "owner" or task.created_by_user_id == member.user_id
        )
        if status_only:
            allowed = allowed or task.assignee_user_id == member.user_id
        if not allowed:
            raise ValueError("planning.forbidden")

    def _save_task(self, db, member, data: dict[str, Any], edit_id: str):
        task = self._task(db, member, edit_id) if edit_id else None
        if task is not None:
            self._authorize_task(member, task)
        title = str(data.get("title", "")).strip()
        details = str(data.get("details", "")).strip()
        currency = str(data.get("currency", "")).strip().upper()
        if (
            not 1 <= len(title) <= 200
            or len(details) > 4000
            or not re.fullmatch("[A-Z]{3}", currency)
        ):
            raise ValueError("planning.invalid_task")
        raw_due = str(data.get("due_date", ""))
        try:
            due = date.fromisoformat(raw_due) if raw_due else None
        except ValueError:
            raise ValueError("planning.invalid_date") from None
        raw_account = str(data.get("account_id", ""))
        aid = self._id(raw_account) if raw_account else None
        if aid is not None:
            account = self._account(db, member, aid, currency)
            if account.is_archived and (task is None or task.account_id != aid):
                raise ValueError("planning.unavailable")
        raw_assignee = str(data.get("assignee_user_id", ""))
        assignee = self._id(raw_assignee) if raw_assignee else None
        if assignee is not None:
            target = db.scalar(
                select(m.HouseholdMembership)
                .join(m.User, m.User.id == m.HouseholdMembership.user_id)
                .where(
                    m.HouseholdMembership.household_id == member.household_id,
                    m.HouseholdMembership.user_id == assignee,
                    m.HouseholdMembership.status == "active",
                    m.User.status == "active",
                )
            )
            if target is None:
                raise ValueError("planning.invalid_participants")
            if aid is not None:
                self._account(db, target, aid, currency)
        if task is None:
            task = m.HouseholdTask(
                household_id=member.household_id,
                created_by_user_id=member.user_id,
                title=title,
                currency=currency,
            )
            db.add(task)
        task.title, task.details, task.currency = title, details, currency
        task.due_date, task.account_id, task.assignee_user_id = (
            due,
            aid,
            assignee,
        )
        db.flush()

    def _change_task(self, db, member, raw: str, action: str):
        task = self._task(db, member, raw)
        self._authorize_task(member, task, action != "delete")
        if action == "delete":
            db.delete(task)
        elif action in ("pending", "complete"):
            task.status = action
        else:
            raise ValueError("planning.invalid_task")
        db.flush()

    def _bill(self, db, member, raw: str):
        bill = db.scalar(
            select(m.Bill)
            .where(
                m.Bill.household_id == member.household_id,
                m.Bill.id == self._id(raw),
            )
            .with_for_update()
        )
        if bill is None:
            raise ValueError("planning.unavailable")
        self._account(db, member, bill.account_id, bill.currency)
        return bill

    def _configure_split(
        self, db, member, data: dict[str, Any], revoke: bool = False
    ):
        if member.role != "owner":
            raise ValueError("planning.owner_only")
        bill = self._bill(db, member, str(data.get("bill_id", "")))
        rule = db.scalar(
            select(m.BillSplitRule)
            .where(
                m.BillSplitRule.household_id == member.household_id,
                m.BillSplitRule.bill_id == bill.id,
            )
            .with_for_update()
        )
        if revoke:
            if rule is not None:
                db.execute(
                    delete(m.BillSplitShare).where(
                        m.BillSplitShare.household_id == member.household_id,
                        m.BillSplitShare.rule_id == rule.id,
                    )
                )
                db.delete(rule)
            db.flush()
            return
        if data.get("confirm") not in (True, "on", "true"):
            raise ValueError("planning.confirm_required")
        if str(data.get("currency", "")) != bill.currency:
            raise ValueError("planning.account_currency")
        ids = [self._id(str(data.get(f"participant_{i}", ""))) for i in (1, 2)]
        if ids[0] == ids[1]:
            raise ValueError("planning.invalid_participants")
        targets = db.scalars(
            select(m.HouseholdMembership)
            .join(m.User, m.User.id == m.HouseholdMembership.user_id)
            .where(
                m.HouseholdMembership.household_id == member.household_id,
                m.HouseholdMembership.user_id.in_(ids),
                m.HouseholdMembership.status == "active",
                m.User.status == "active",
            )
            .with_for_update()
        ).all()
        if len(targets) != 2:
            raise ValueError("planning.invalid_participants")
        for target in targets:
            if target.role != "owner" and not target.can_view_commitments:
                raise ValueError("planning.consent_required")
            self._account(db, target, bill.account_id, bill.currency)
        mode = str(data.get("mode", ""))
        incomes = (
            [positive_money(str(data.get(f"income_{i}", ""))) for i in (1, 2)]
            if mode == "income"
            else [Decimal(1), Decimal(1)]
        )
        p1, p2, a1, a2 = calculate_split(bill.amount, mode, incomes)
        if rule is None:
            rule = m.BillSplitRule(
                household_id=member.household_id,
                bill_id=bill.id,
                currency=bill.currency,
                mode=mode,
                created_by_user_id=member.user_id,
            )
            db.add(rule)
            db.flush()
        else:
            db.execute(
                delete(m.BillSplitShare).where(
                    m.BillSplitShare.household_id == member.household_id,
                    m.BillSplitShare.rule_id == rule.id,
                )
            )
            rule.currency, rule.mode = bill.currency, mode
        for uid, percentage, amount, income in zip(
            ids, (p1, p2), (a1, a2), incomes
        ):
            db.add(
                m.BillSplitShare(
                    household_id=member.household_id,
                    rule_id=rule.id,
                    member_user_id=uid,
                    percentage=percentage,
                    share_amount=amount,
                    declared_income=income if mode == "income" else None,
                )
            )
        db.flush()

    def _read(self, db, member):
        hid = member.household_id
        self.owner = member.role == "owner"
        accounts = db.scalars(
            select(m.FinancialAccount)
            .where(
                m.FinancialAccount.household_id == hid,
                self._visible_clause(member, m.FinancialAccount.id),
            )
            .order_by(m.FinancialAccount.name)
            .limit(500)
        ).all()
        account_map = {a.id: a for a in accounts}
        self.accounts = [
            {"id": str(a.id), "name": f"{a.name} · {a.currency}"}
            for a in accounts
        ]
        people = db.execute(
            select(m.HouseholdMembership.user_id, m.User.display_name)
            .join(m.User, m.User.id == m.HouseholdMembership.user_id)
            .where(
                m.HouseholdMembership.household_id == hid,
                m.HouseholdMembership.status == "active",
                m.User.status == "active",
            )
            .order_by(m.User.display_name)
            .limit(100)
        ).all()
        names = dict(people)
        self.participants = [
            {"id": str(uid), "name": name} for uid, name in people
        ]
        query = (
            select(m.HouseholdTask)
            .outerjoin(
                m.FinancialAccount,
                (m.FinancialAccount.id == m.HouseholdTask.account_id)
                & (m.FinancialAccount.household_id == hid),
            )
            .where(
                m.HouseholdTask.household_id == hid,
                or_(
                    m.HouseholdTask.account_id.is_(None),
                    (m.HouseholdTask.account_id.in_(account_map))
                    & (m.HouseholdTask.currency == m.FinancialAccount.currency),
                ),
            )
        )
        if self.currency_filter:
            query = query.where(
                m.HouseholdTask.currency == self.currency_filter.upper()
            )
        if self.status_filter:
            query = query.where(m.HouseholdTask.status == self.status_filter)
        rows = db.scalars(
            query.order_by(
                m.HouseholdTask.due_date.asc().nulls_last(), m.HouseholdTask.id
            ).limit(200)
        ).all()
        self.tasks = [
            {
                "id": str(x.id),
                "title": x.title,
                "details": x.details,
                "due_date": x.due_date.isoformat() if x.due_date else "",
                "currency": x.currency,
                "account_id": str(x.account_id) if x.account_id else "",
                "account": account_map[x.account_id].name
                if x.account_id
                else "",
                "assignee_user_id": str(x.assignee_user_id)
                if x.assignee_user_id
                else "",
                "assignee": names.get(x.assignee_user_id, ""),
                "status": x.status,
                "editable": self.owner
                or x.created_by_user_id == member.user_id,
                "actionable": self.owner
                or member.user_id in (x.created_by_user_id, x.assignee_user_id),
            }
            for x in rows
        ]
        bills = db.scalars(
            select(m.Bill)
            .join(
                m.FinancialAccount,
                (m.FinancialAccount.id == m.Bill.account_id)
                & (m.FinancialAccount.household_id == hid),
            )
            .where(
                m.Bill.household_id == hid,
                m.Bill.account_id.in_(account_map),
                m.Bill.currency == m.FinancialAccount.currency,
            )
            .order_by(m.Bill.due_date, m.Bill.id)
            .limit(200)
        ).all()
        query = select(m.BillSplitRule).where(
            m.BillSplitRule.household_id == hid,
            m.BillSplitRule.bill_id.in_([b.id for b in bills]),
        )
        if not self.owner:
            query = query.where(
                m.BillSplitRule.id.in_(
                    select(m.BillSplitShare.rule_id).where(
                        m.BillSplitShare.household_id == hid,
                        m.BillSplitShare.member_user_id == member.user_id,
                    )
                )
            )
        rules = (
            db.scalars(query).all()
            if self.owner or member.can_view_commitments
            else []
        )
        rule_map = {r.bill_id: r for r in rules}
        shares = (
            db.execute(
                select(m.BillSplitShare, m.User.display_name)
                .join(m.User, m.User.id == m.BillSplitShare.member_user_id)
                .where(
                    m.BillSplitShare.household_id == hid,
                    m.BillSplitShare.rule_id.in_([r.id for r in rules]),
                )
                .order_by(m.BillSplitShare.member_user_id)
            ).all()
            if rules
            else []
        )
        grouped: dict[UUID, list[ShareRow]] = {}
        totals: dict[UUID, Decimal] = {}
        for share, name in shares:
            grouped.setdefault(share.rule_id, []).append(
                {
                    "name": name,
                    "income": f"{share.declared_income:.4f}"
                    if share.declared_income is not None
                    else "",
                    "percentage": f"{share.percentage:.6f}",
                    "amount": f"{share.share_amount:.4f}",
                }
            )
            totals[share.rule_id] = (
                totals.get(share.rule_id, Decimal(0)) + share.share_amount
            )
        self.bills = []
        for bill in bills:
            rule = rule_map.get(bill.id)
            self.bills.append(
                {
                    "id": str(bill.id),
                    "title": bill.title,
                    "currency": bill.currency,
                    "amount": f"{bill.amount:.4f}",
                    "account": account_map[bill.account_id].name,
                    "due_date": bill.due_date.isoformat(),
                    "mode": rule.mode if rule else "",
                    "stale": bool(
                        rule
                        and (
                            rule.currency != bill.currency
                            or totals.get(rule.id) != bill.amount
                        )
                    ),
                    "shares": grouped.get(rule.id, [])
                    if rule and rule.currency == bill.currency
                    else [],
                }
            )

    def _clear(self):
        self.tasks, self.bills, self.accounts, self.participants = (
            [],
            [],
            [],
            [],
        )
        self.owner = False
        self.editor = False
        self.edit_id = self.delete_id = ""
        self.draft = {
            "title": "",
            "details": "",
            "due_date": "",
            "currency": "",
            "account_id": "",
            "assignee_user_id": "",
        }

    async def _perform(
        self, action: str, data: dict[str, Any], raw: str = ""
    ) -> bool:
        self.error = self.message = ""
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as session:

                def work(db):
                    user, member = self._context(db, auth)
                    if action == "save":
                        self._save_task(db, member, data, raw)
                    elif action in ("pending", "complete", "delete"):
                        self._change_task(db, member, raw, action)
                    elif action in ("split", "revoke"):
                        self._configure_split(
                            db, member, data, action == "revoke"
                        )
                    elif action == "open":
                        task = self._task(db, member, raw)
                        self._authorize_task(member, task)
                        self.draft = {
                            "title": task.title,
                            "details": task.details,
                            "currency": task.currency,
                            "due_date": task.due_date.isoformat()
                            if task.due_date
                            else "",
                            "account_id": str(task.account_id)
                            if task.account_id
                            else "",
                            "assignee_user_id": str(task.assignee_user_id)
                            if task.assignee_user_id
                            else "",
                        }
                    self._read(db, member)

                await session.run_sync(work)
                if action not in ("read", "open"):
                    await session.commit()
            return True
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            self._clear()
            self.error = (
                str(e)
                if str(e).startswith("planning.")
                else "planning.unavailable"
            )
        except Exception as e:
            logging.exception("Family planning operation failed")
            report_unexpected("family_planning.operation", e)
            self._clear()
            self.error = "planning.failed"
        return False

    @rx.event
    async def load(self):
        self._clear()
        self.loading = True
        yield
        await self._perform("read", {})
        self.loading = False

    @rx.event
    async def apply_filters(self, data: dict[str, Any]):
        self.currency_filter = str(data.get("currency", "")).strip().upper()
        self.status_filter = str(data.get("status", ""))
        if self.status_filter not in ("", "pending", "complete") or (
            self.currency_filter
            and not re.fullmatch("[A-Z]{3}", self.currency_filter)
        ):
            self.error = "planning.invalid_task"
            return
        yield FamilyPlanningState.load

    @rx.event
    async def open_task(self, raw: str = ""):
        self.editor = False
        self.edit_id = ""
        self.draft = {
            "title": "",
            "details": "",
            "due_date": "",
            "currency": "",
            "account_id": "",
            "assignee_user_id": "",
        }
        if await self._perform("open" if raw else "read", {}, raw):
            self.edit_id = raw
            self.form_key += 1
            self.editor = True

    @rx.event
    def close_task(self):
        self.editor = False

    @rx.event
    async def save_task(self, data: dict[str, Any]):
        if await self._perform("save", data, self.edit_id):
            self.editor = False
            self.message = "planning.saved"

    @rx.event
    async def set_status(self, raw: str, status: str):
        if status not in ("pending", "complete"):
            self.error = "planning.invalid_task"
            return
        if await self._perform(status, {}, raw):
            self.message = "planning.saved"

    @rx.event
    async def ask_delete(self, raw: str):
        if await self._perform("open", {}, raw):
            self.delete_id = raw

    @rx.event
    def cancel_delete(self):
        self.delete_id = ""

    @rx.event
    async def delete_task(self):
        if await self._perform("delete", {}, self.delete_id):
            self.delete_id = ""
            self.message = "planning.saved"

    @rx.event
    async def save_split(self, data: dict[str, Any]):
        if await self._perform("split", data):
            self.message = "planning.saved"
            self.form_key += 1

    @rx.event
    async def revoke_split(self, raw: str):
        if await self._perform("revoke", {"bill_id": raw}):
            self.message = "planning.saved"
