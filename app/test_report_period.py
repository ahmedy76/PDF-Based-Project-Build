import reflex as rx

import logging
import os
import secrets
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import bcrypt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models as m
from app.states.auth import AuthState, digest, now
from app.states.ledger import LedgerState


class FixedToday(date):
    @classmethod
    def today(cls):
        return cls(2026, 3, 15)


class ReportPeriodValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_form_keeps_current_results_and_selection(self):
        cases = [
            ({"start": "", "end": "2026-03-15"}, "البداية والنهاية"),
            ({"start": "2026-03-01", "end": ""}, "البداية والنهاية"),
            ({"start": "20260301", "end": "2026-03-15"}, "صيغة صحيحة"),
            ({"start": "2026-02-30", "end": "2026-03-15"}, "صيغة صحيحة"),
            ({"start": "2026-03-16", "end": "2026-03-15"}, "يسبق"),
            ({"start": "2026-03-01", "end": "2026-03-16"}, "بعد اليوم"),
            ({"start": "2025-03-14", "end": "2026-03-15"}, "366"),
        ]
        state = LedgerState()
        state.period = "previous"
        state.report_start, state.report_end = "2026-01-01", "2026-01-31"
        state.report_range_label = "من 2026-02-01 إلى 2026-02-28"
        state.report_income = "120.00"
        state.trend_dates = ["2026-02-01"]
        with patch("app.states.ledger.date", FixedToday):
            for data, text in cases:
                with self.subTest(data=data):
                    event = LedgerState.set_custom_period.fn(state, data)
                    with self.assertRaises(StopAsyncIteration):
                        await anext(event)
                    self.assertIn(text, state.message)
                    self.assertEqual(state.period, "previous")
                    self.assertEqual(
                        (state.report_start, state.report_end),
                        ("2026-01-01", "2026-01-31"),
                    )
                    self.assertEqual(
                        state.report_range_label, "من 2026-02-01 إلى 2026-02-28"
                    )
                    self.assertEqual(state.report_income, "120.00")
                    self.assertEqual(state.trend_dates, ["2026-02-01"])

    async def test_inclusive_limit_and_preset_switching(self):
        state = LedgerState()
        with patch("app.states.ledger.date", FixedToday):
            event = LedgerState.set_custom_period.fn(
                state, {"start": "2025-03-15", "end": "2026-03-15"}
            )
            self.assertIsNotNone(await anext(event))
            with self.assertRaises(StopAsyncIteration):
                await anext(event)
            self.assertEqual(state.period, "custom")
            self.assertEqual(
                (state.report_start, state.report_end),
                ("2025-03-15", "2026-03-15"),
            )
            self.assertEqual(state.message, "")
            event = LedgerState.set_period.fn(state, "custom")
            with self.assertRaises(StopAsyncIteration):
                await anext(event)
            self.assertEqual(state.period, "custom")
            event = LedgerState.set_period.fn(state, "three")
            self.assertIsNotNone(await anext(event))
            self.assertEqual(state.period, "three")
            self.assertEqual(
                state._report_bounds(FixedToday.today()),
                (date(2026, 1, 1), date(2026, 3, 15)),
            )
            for mode, expected in (
                ("previous", (date(2026, 2, 1), date(2026, 2, 28))),
                ("current", (date(2026, 3, 1), date(2026, 3, 15))),
            ):
                event = LedgerState.set_period.fn(state, mode)
                self.assertIsNotNone(await anext(event))
                self.assertEqual(
                    state._report_bounds(FixedToday.today()), expected
                )
            self.assertEqual(
                (state.report_start, state.report_end),
                ("2025-03-15", "2026-03-15"),
            )

    def test_direct_custom_state_cannot_bypass_date_limit(self):
        state = LedgerState()
        state.period = "custom"
        state.report_start = "2020-01-01"
        state.report_end = "2026-03-15"
        with self.assertRaisesRegex(ValueError, "366"):
            state._report_bounds(FixedToday.today())


class ReportAggregationTests(unittest.TestCase):
    def test_custom_spans_months_includes_both_ends_and_archived_category(self):
        hid, uid, account_id, income_id, active_id, archived_id = (
            uuid4() for _ in range(6)
        )
        categories = [
            SimpleNamespace(
                id=income_id, name="راتب", kind="income", is_archived=False
            ),
            SimpleNamespace(
                id=active_id, name="طعام", kind="expense", is_archived=False
            ),
            SimpleNamespace(
                id=archived_id, name="قديم", kind="expense", is_archived=True
            ),
        ]
        account = SimpleNamespace(
            id=account_id,
            name="محفظة",
            account_type="cash",
            currency="SAR",
            opening_balance=Decimal("0"),
            opening_date=date(2025, 1, 1),
            is_archived=False,
        )

        def tx(day, amount, kind, category_id):
            return SimpleNamespace(
                id=uuid4(),
                account_id=account_id,
                category_id=category_id,
                amount=Decimal(amount),
                kind=kind,
                transaction_date=day,
                description="حركة",
            )

        transactions = [
            tx(date(2026, 1, 30), "900", "income", income_id),
            tx(date(2026, 1, 31), "100", "income", income_id),
            tx(date(2026, 1, 31), "15", "expense", archived_id),
            tx(date(2026, 2, 1), "25", "expense", active_id),
            tx(date(2026, 2, 1), "10", "expense", archived_id),
            tx(date(2026, 2, 2), "80", "income", income_id),
            tx(date(2026, 2, 3), "5", "expense", archived_id),
            tx(date(2026, 2, 4), "500", "expense", active_id),
            tx(date(2026, 3, 10), "40", "income", income_id),
            tx(date(2026, 3, 11), "7", "expense", active_id),
        ]
        budget = SimpleNamespace(
            id=uuid4(),
            category_id=active_id,
            year=2026,
            month=3,
            currency="SAR",
            amount=Decimal("100"),
            alert_threshold_percent=80,
        )
        db = Mock()
        db.execute.return_value.all.return_value = []
        db.get.return_value = SimpleNamespace(name="البيت", currency="SAR")
        db.scalars.side_effect = [
            Mock(all=Mock(return_value=rows))
            for rows in (
                [SimpleNamespace(id=hid, name="البيت")],
                categories,
                [account],
                [],
                transactions,
                [budget],
                [],
                [],
                [],
                [],
            )
        ]
        state = LedgerState()
        state.period = "custom"
        state.report_start, state.report_end = "2026-01-31", "2026-02-03"
        state.budget_month = "2026-03"
        with patch("app.states.ledger.date", FixedToday):
            state._load(
                db,
                SimpleNamespace(id=uid),
                SimpleNamespace(household_id=hid, role="owner"),
            )
        self.assertEqual(
            state.report_range_label, "من 2026-01-31 إلى 2026-02-03"
        )
        self.assertEqual(
            (state.report_income, state.report_expense, state.report_saving),
            ("180.00", "55.00", "125.00"),
        )
        self.assertEqual(
            dict(zip(state.report_labels, state.report_values)),
            {"طعام": 25.0, "قديم": 30.0},
        )
        self.assertEqual(
            state.trend_dates,
            ["2026-01-31", "2026-02-01", "2026-02-02", "2026-02-03"],
        )
        self.assertEqual(state.trend_income, [100.0, 0.0, 80.0, 0.0])
        self.assertEqual(state.trend_expense, [15.0, 35.0, 0.0, 5.0])
        self.assertEqual(
            (state.income, state.expense, state.saving),
            ("40.00", "7.00", "33.00"),
        )
        self.assertEqual(state.dashboard_budgets[0]["spent"], "7.00")
        self.assertEqual(state.budgets[0]["month"], "2026-03")
        self.assertEqual(state.budget_month, "2026-03")


class ManagedDatabaseReportTests(unittest.TestCase):
    def _seed_household(
        self, db: Session, user: m.User, name: str
    ) -> m.Household:
        household = m.Household(name=name, owner_user_id=user.id)
        db.add(household)
        db.flush()
        db.add(
            m.HouseholdMembership(
                household_id=household.id, user_id=user.id, role="owner"
            )
        )
        db.flush()
        return household

    def _seed_transaction(
        self,
        db: Session,
        household: m.Household,
        user: m.User,
        account: m.FinancialAccount,
        category: m.Category,
        amount: str,
        day: date,
        description: str,
        deleted: bool = False,
    ) -> m.Transaction:
        transaction = m.Transaction(
            household_id=household.id,
            created_by_user_id=user.id,
            account_id=account.id,
            category_id=category.id,
            kind=category.kind,
            amount=Decimal(amount),
            transaction_date=day,
            description=description,
            deleted_at=now() if deleted else None,
        )
        db.add(transaction)
        return transaction

    def _exercise_load(self, db: Session):
        suffix = uuid4().hex
        user = m.User(
            display_name="اختبار التقرير",
            email=f"report-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                secrets.token_bytes(24), bcrypt.gensalt()
            ).decode(),
            language="ar",
        )
        db.add(user)
        db.flush()
        household = self._seed_household(db, user, "أسرة اختبار التقرير")
        income = m.Category(
            household_id=household.id, name="راتب", kind="income"
        )
        food = m.Category(
            household_id=household.id, name="طعام", kind="expense"
        )
        archived = m.Category(
            household_id=household.id,
            name="قديم",
            kind="expense",
            is_archived=True,
        )
        db.add_all([income, food, archived])
        db.flush()
        active_account = m.FinancialAccount(
            household_id=household.id,
            created_by_user_id=user.id,
            name="محفظة",
            opening_balance=Decimal("200"),
            opening_date=date(2025, 1, 1),
        )
        closed_account = m.FinancialAccount(
            household_id=household.id,
            created_by_user_id=user.id,
            name="حساب مغلق",
            opening_balance=Decimal("50"),
            opening_date=date(2025, 1, 1),
            is_archived=True,
        )
        db.add_all([active_account, closed_account])
        db.flush()
        entries = [
            (
                active_account,
                income,
                "900",
                date(2026, 1, 30),
                "دخل قبل الفترة",
                False,
            ),
            (
                active_account,
                income,
                "100",
                date(2026, 1, 31),
                "دخل البداية",
                False,
            ),
            (
                active_account,
                archived,
                "15",
                date(2026, 1, 31),
                "قديم البداية",
                False,
            ),
            (
                active_account,
                food,
                "25",
                date(2026, 2, 1),
                "طعام فبراير",
                False,
            ),
            (
                active_account,
                archived,
                "10",
                date(2026, 2, 1),
                "قديم فبراير",
                False,
            ),
            (
                active_account,
                income,
                "80",
                date(2026, 2, 2),
                "دخل فبراير",
                False,
            ),
            (
                active_account,
                archived,
                "5",
                date(2026, 2, 3),
                "قديم النهاية",
                False,
            ),
            (
                active_account,
                food,
                "500",
                date(2026, 2, 4),
                "بعد الفترة",
                False,
            ),
            (
                closed_account,
                food,
                "12",
                date(2026, 2, 4),
                "حركة الحساب المغلق",
                False,
            ),
            (
                active_account,
                income,
                "40",
                date(2026, 3, 10),
                "دخل مارس",
                False,
            ),
            (active_account, food, "7", date(2026, 3, 11), "طعام مارس", False),
            (
                active_account,
                food,
                "999",
                date(2026, 2, 2),
                "معاملة محذوفة",
                True,
            ),
        ]
        for account, category, amount, day, description, deleted in entries:
            self._seed_transaction(
                db,
                household,
                user,
                account,
                category,
                amount,
                day,
                description,
                deleted,
            )
        db.add_all(
            [
                m.MonthlyCategoryBudget(
                    household_id=household.id,
                    created_by_user_id=user.id,
                    category_id=food.id,
                    year=2026,
                    month=2,
                    amount=Decimal("70"),
                ),
                m.MonthlyCategoryBudget(
                    household_id=household.id,
                    created_by_user_id=user.id,
                    category_id=food.id,
                    year=2026,
                    month=3,
                    amount=Decimal("100"),
                ),
            ]
        )
        db.flush()

        other_user = m.User(
            display_name="أسرة أخرى",
            email=f"other-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                secrets.token_bytes(24), bcrypt.gensalt()
            ).decode(),
        )
        db.add(other_user)
        db.flush()
        other = self._seed_household(db, other_user, "أسرة معزولة")
        other_category = m.Category(
            household_id=other.id, name="فئة الأسرة الأخرى", kind="expense"
        )
        db.add(other_category)
        db.flush()
        other_account = m.FinancialAccount(
            household_id=other.id,
            created_by_user_id=other_user.id,
            name="حساب الأسرة الأخرى",
            opening_balance=Decimal("9999"),
            opening_date=date(2025, 1, 1),
        )
        db.add(other_account)
        db.flush()
        self._seed_transaction(
            db,
            other,
            other_user,
            other_account,
            other_category,
            "777",
            date(2026, 2, 1),
            "مصروف الأسرة الأخرى",
        )
        db.add(
            m.MonthlyCategoryBudget(
                household_id=other.id,
                created_by_user_id=other_user.id,
                category_id=other_category.id,
                year=2026,
                month=2,
                amount=Decimal("888"),
            )
        )

        raw_token = secrets.token_urlsafe(48)
        db.add(
            m.UserSession(
                user_id=user.id,
                access_token_hash=digest(raw_token),
                refresh_token_hash=digest(secrets.token_urlsafe(48)),
                access_expires_at=now() + timedelta(days=1),
                refresh_expires_at=now() + timedelta(days=2),
            )
        )
        db.flush()
        auth = AuthState()
        auth.token = raw_token
        auth.selected_household = str(household.id)
        self.assertEqual(auth._identity(db).id, user.id)
        identified, membership = auth._household(db)
        self.assertTrue(auth.authenticated)
        self.assertEqual(identified.id, user.id)
        self.assertEqual(membership.household_id, household.id)
        self.assertEqual(membership.role, "owner")
        state = LedgerState()
        state.period = "custom"
        state.report_start, state.report_end = "2026-01-31", "2026-02-03"
        state.budget_month = "2026-02"
        with patch("app.states.ledger.date", FixedToday):
            state._load(db, identified, membership)

        self.assertTrue(state.ready)
        self.assertEqual(state.household_name, household.name)
        self.assertEqual(
            state.households,
            [{"id": str(household.id), "name": household.name}],
        )
        self.assertEqual(state.total, "758.00")
        self.assertEqual(state.archived_total, "38.00")
        self.assertTrue(state.has_archived_balance)
        self.assertEqual(len(state.accounts), 1)
        self.assertEqual(len(state.archived_accounts), 1)
        self.assertEqual(state.archived_accounts[0]["balance"], "38.00")
        self.assertEqual(len(state.transactions), 11)
        self.assertTrue(
            any(
                t["category_id"] == str(archived.id) for t in state.transactions
            )
        )
        self.assertTrue(
            any(
                t["account_id"] == str(closed_account.id)
                for t in state.transactions
            )
        )
        self.assertFalse(
            any(t["name"] == "معاملة محذوفة" for t in state.transactions)
        )
        self.assertEqual(state.archived_categories[0]["id"], str(archived.id))
        self.assertIn(
            str(archived.id), [c["id"] for c in state.filter_category_options]
        )
        self.assertIn(
            str(closed_account.id),
            [a["id"] for a in state.filter_account_options],
        )
        state.filter_category = str(archived.id)
        state.filter_kind = ""
        state.filter_account = ""
        state.filter_start = ""
        state.filter_end = ""
        self.assertEqual(
            {t["name"] for t in state.visible_transactions},
            {"قديم البداية", "قديم فبراير", "قديم النهاية"},
        )
        state.filter_category = ""
        self.assertEqual(
            state.report_range_label, "من 2026-01-31 إلى 2026-02-03"
        )
        self.assertEqual(
            (state.report_income, state.report_expense, state.report_saving),
            ("180.00", "55.00", "125.00"),
        )
        self.assertEqual(
            dict(zip(state.report_labels, state.report_values)),
            {"طعام": 25.0, "قديم": 30.0},
        )
        self.assertEqual(
            state.trend_dates,
            [
                "2026-01-31",
                "2026-02-01",
                "2026-02-02",
                "2026-02-03",
            ],
        )
        self.assertEqual(state.trend_income, [100.0, 0.0, 80.0, 0.0])
        self.assertEqual(state.trend_expense, [15.0, 35.0, 0.0, 5.0])
        self.assertEqual(
            (state.income, state.expense, state.saving),
            ("40.00", "7.00", "33.00"),
        )
        self.assertEqual(state.budget_month, "2026-02")
        self.assertEqual(len(state.budgets), 1)
        self.assertEqual(
            (state.budgets[0]["month"], state.budgets[0]["spent"]),
            ("2026-02", "537.00"),
        )
        self.assertEqual(len(state.dashboard_budgets), 1)
        self.assertEqual(
            (
                state.dashboard_budgets[0]["month"],
                state.dashboard_budgets[0]["spent"],
            ),
            ("2026-03", "7.00"),
        )
        self.assertNotIn(str(other.id), [h["id"] for h in state.households])
        self.assertNotIn(
            str(other_account.id), [a["id"] for a in state.accounts]
        )
        self.assertNotIn(
            str(other_category.id), [c["id"] for c in state.categories]
        )
        self.assertFalse(
            any(t["name"] == "مصروف الأسرة الأخرى" for t in state.transactions)
        )
        self.assertNotIn("فئة الأسرة الأخرى", state.report_labels)

    def _exercise_recurring(self, db: Session):
        suffix = uuid4().hex
        user = m.User(
            display_name="تكرار",
            email=f"repeat-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                secrets.token_bytes(24), bcrypt.gensalt()
            ).decode(),
        )
        other_user = m.User(
            display_name="أسرة ثانية",
            email=f"repeat-other-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                secrets.token_bytes(24), bcrypt.gensalt()
            ).decode(),
        )
        db.add_all([user, other_user])
        db.flush()
        household = self._seed_household(db, user, "دفتر التكرار")
        other = self._seed_household(db, other_user, "دفتر آخر")
        category = m.Category(
            household_id=household.id, name="طعام", kind="expense"
        )
        account = m.FinancialAccount(
            household_id=household.id,
            created_by_user_id=user.id,
            name="محفظة",
            opening_date=date(2026, 3, 1),
        )
        db.add_all([category, account])
        db.flush()
        db.add(
            m.MonthlyCategoryBudget(
                household_id=household.id,
                created_by_user_id=user.id,
                category_id=category.id,
                year=2026,
                month=3,
                amount=Decimal("15"),
            )
        )
        rule = m.RecurringTransactionRule(
            household_id=household.id,
            created_by_user_id=user.id,
            account_id=account.id,
            category_id=category.id,
            kind="expense",
            amount=Decimal("10"),
            description="طعام متكرر",
            frequency="daily",
            start_date=date(2026, 3, 14),
            next_date=date(2026, 3, 14),
        )
        db.add(rule)
        other_category = m.Category(
            household_id=other.id, name="طعام آخر", kind="expense"
        )
        other_account = m.FinancialAccount(
            household_id=other.id,
            created_by_user_id=other_user.id,
            name="محفظة ثانية",
            opening_date=date(2026, 3, 1),
        )
        db.add_all([other_category, other_account])
        db.flush()
        other_rule = m.RecurringTransactionRule(
            household_id=other.id,
            created_by_user_id=other_user.id,
            account_id=other_account.id,
            category_id=other_category.id,
            kind="expense",
            amount=Decimal("999"),
            frequency="daily",
            start_date=date(2026, 3, 14),
            next_date=date(2026, 3, 14),
        )
        db.add(other_rule)
        db.flush()
        state = LedgerState()
        state.period = "current"
        state.budget_month = "2026-03"
        state.report_start, state.report_end = "", ""
        with patch("app.states.ledger.date", FixedToday):
            state._materialize_due(db, household.id, date(2026, 3, 15))
            db.flush()
            state._materialize_due(db, household.id, date(2026, 3, 15))
            self.assertEqual(
                db.query(m.Transaction)
                .filter(m.Transaction.household_id == other.id)
                .count(),
                0,
            )
            with self.assertRaises(ValueError):
                state._record(
                    db,
                    m.RecurringTransactionRule,
                    str(other_rule.id),
                    household.id,
                )
            state._load(
                db,
                user,
                SimpleNamespace(household_id=household.id, role="owner"),
            )
        self.assertEqual(len(state.transactions), 2)
        events = db.scalars(
            select(m.TransactionAuditEvent).where(
                m.TransactionAuditEvent.household_id == household.id
            )
        ).all()
        self.assertEqual(len(events), 2)
        self.assertTrue(
            all(
                e.action == "auto_created" and e.actor_user_id is None
                for e in events
            )
        )
        self.assertTrue(
            all(e.after_data["amount"] == "10.0000" for e in events)
        )
        self.assertEqual(state.transactions[0]["metadata"], "سُجّلت آليًا")
        self.assertEqual(state.expense, "20.00")
        self.assertEqual(
            state.report_range_label, "من 2026-03-01 إلى 2026-03-15"
        )
        self.assertEqual(state.report_expense, "20.00")
        self.assertEqual(state.budgets[0]["spent"], "20.00")
        self.assertEqual(state.budgets[0]["status"], "تجاوز الحد")
        self.assertEqual(state.recurring_rules[0]["next_date"], "2026-03-16")
        self.assertTrue(
            all(
                t["recurring_rule_id"] == str(rule.id)
                for t in state.transactions
            )
        )
        db.query(m.Transaction).filter(
            m.Transaction.recurring_rule_id == rule.id,
            m.Transaction.scheduled_for == date(2026, 3, 14),
        ).one().deleted_at = now()
        rule.next_date = date(2026, 3, 14)
        db.flush()
        state._materialize_due(db, household.id, date(2026, 3, 15))
        db.flush()
        self.assertEqual(
            db.query(m.Transaction)
            .filter(m.Transaction.recurring_rule_id == rule.id)
            .count(),
            2,
        )
        rule.is_active = False
        rule.next_date = date(2026, 3, 16)
        db.flush()
        state._materialize_due(db, household.id, date(2026, 3, 20))
        self.assertEqual(
            db.query(m.Transaction)
            .filter(m.Transaction.recurring_rule_id == rule.id)
            .count(),
            2,
        )
        account.is_archived = True
        rule.is_active = True
        db.flush()
        warning = state._materialize_due(db, household.id, date(2026, 3, 20))
        self.assertFalse(rule.is_active)
        self.assertIn("أُوقفت", warning)

    def test_custom_load_on_isolated_managed_dev_postgres(self):
        dev_url = os.getenv("REFLEX_DEV_DB_URL")
        if not dev_url:
            self.skipTest("REFLEX_DEV_DB_URL is unavailable")
        dev_url = dev_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_engine(dev_url)
        try:
            with engine.connect() as connection:
                outer = connection.begin()
                try:
                    with Session(
                        bind=connection,
                        join_transaction_mode="create_savepoint",
                    ) as db:
                        self._exercise_load(db)
                        self._exercise_recurring(db)
                finally:
                    outer.rollback()
        except Exception as e:
            logging.exception(f"Error: {e}")
            raise
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
