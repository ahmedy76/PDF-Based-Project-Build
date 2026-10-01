import reflex as rx

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from decimal import Decimal
from app import models
from app.states.auth import digest
from app.states.ledger import LedgerState, next_recurring_date
from app.states.categories import CategoryState


class MoneyRulesTests(unittest.TestCase):
    def test_token_digest(self):
        self.assertEqual(len(digest("a random invitation")), 64)
        self.assertNotEqual(digest("first"), digest("second"))

    def test_decimal_validation(self):
        self.assertEqual(
            LedgerState._money(None, "10.1250", True), Decimal("10.1250")
        )
        self.assertEqual(LedgerState._money(None, "-50"), Decimal("-50"))
        for value in (
            "NaN",
            "Infinity",
            "0",
            "-1",
            "1.00001",
            "1000000000000000",
        ):
            with self.assertRaises(ValueError):
                LedgerState._money(None, value, True)

    def test_schema_keeps_tenant_constraints(self):
        table = models.Transaction.__table__
        targets = {
            tuple(c.name for c in fk.columns)
            for fk in table.foreign_key_constraints
        }
        self.assertIn(("household_id", "account_id"), targets)
        self.assertIn(("household_id", "category_id", "kind"), targets)
        self.assertIn(("household_id", "created_by_user_id"), targets)

    def test_category_name_rules(self):
        self.assertEqual(CategoryState._validate_name("  مشتريات  "), "مشتريات")
        for invalid in ("", "   ", "س" * 101):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                CategoryState._validate_name(invalid)
        self.assertEqual(len(CategoryState._validate_name("س" * 100)), 100)

    def test_category_uniqueness_includes_archived(self):
        from unittest.mock import Mock
        from uuid import uuid4

        db = Mock()
        db.scalar.return_value = uuid4()
        with self.assertRaisesRegex(ValueError, "مؤرشفة"):
            CategoryState._unique(None, db, uuid4(), "expense", "طعام")
        query = str(db.scalar.call_args.args[0])
        self.assertIn("mh_categories.household_id", query)
        self.assertIn("mh_categories.kind", query)
        self.assertIn("lower(mh_categories.name)", query)
        self.assertNotIn("is_archived", query)

    def test_session_digests_not_plain_tokens(self):
        table = models.UserSession.__table__
        self.assertEqual(table.c.access_token_hash.type.length, 64)
        self.assertEqual(table.c.refresh_token_hash.type.length, 64)
        self.assertTrue(issubclass(AuthStateForTest(), rx.State))

    def test_closed_account_balances_names_reports_and_filter(self):
        hid, uid, active_id, closed_id, category_id = (
            uuid4() for _ in range(5)
        )
        today = date.today()
        active = SimpleNamespace(
            id=active_id,
            name="محفظة",
            account_type="cash",
            opening_balance=Decimal("100.00"),
            opening_date=today,
            is_archived=False,
        )
        closed = SimpleNamespace(
            id=closed_id,
            name="حساب قديم",
            account_type="bank",
            opening_balance=Decimal("30.00"),
            opening_date=today,
            is_archived=True,
        )
        category = SimpleNamespace(
            id=category_id,
            name="مصاريف",
            kind="expense",
            is_archived=False,
        )
        archived_category_id = uuid4()
        archived_category = SimpleNamespace(
            id=archived_category_id,
            name="مصروفات قديمة",
            kind="expense",
            is_archived=True,
        )
        txs = [
            SimpleNamespace(
                id=uuid4(),
                account_id=active_id,
                category_id=category_id,
                kind="expense",
                amount=Decimal("20.00"),
                description="نشط",
                transaction_date=today,
            ),
            SimpleNamespace(
                id=uuid4(),
                account_id=closed_id,
                category_id=archived_category_id,
                kind="expense",
                amount=Decimal("10.00"),
                description="قديم",
                transaction_date=today,
            ),
        ]
        db = Mock()
        db.execute.return_value.all.return_value = []
        db.get.return_value = SimpleNamespace(name="البيت", currency="SAR")
        result_sets = [
            [SimpleNamespace(id=hid, name="البيت")],
            [category, archived_category],
            [active, closed],
            [],
            txs,
            [],
            [],
            [],
            [],
            [],
        ]
        db.scalars.side_effect = [
            Mock(all=Mock(return_value=rows)) for rows in result_sets
        ]
        state = LedgerState()
        state._load(
            db,
            SimpleNamespace(id=uid),
            SimpleNamespace(household_id=hid, role="owner"),
        )
        self.assertEqual(state.accounts[0]["balance"], "80.00")
        self.assertEqual(state.archived_accounts[0]["balance"], "20.00")
        self.assertEqual(state.total, "80.00")
        self.assertEqual(state.archived_total, "20.00")
        self.assertTrue(state.has_archived_balance)
        self.assertEqual(
            [a["name"] for a in state.filter_account_options],
            ["محفظة", "حساب قديم"],
        )
        self.assertEqual(state.transactions[1]["account"], "حساب قديم")
        self.assertEqual(state.transactions[1]["category"], "مصروفات قديمة")
        self.assertEqual([c["name"] for c in state.categories], ["مصاريف"])
        self.assertEqual(
            [c["name"] for c in state.archived_categories], ["مصروفات قديمة"]
        )
        self.assertEqual(len(state.filter_category_options), 2)
        state.filter_category = str(archived_category_id)
        self.assertEqual(
            [t["name"] for t in state.visible_transactions], ["قديم"]
        )
        state.filter_category = ""
        self.assertEqual(state.report_expense, "30.00")
        self.assertIn(
            "deleted_at IS NULL", str(db.scalars.call_args_list[4].args[0])
        )
        state.filter_account = str(closed_id)
        self.assertEqual(
            [t["name"] for t in state.visible_transactions], ["قديم"]
        )
        self.assertEqual(
            [a["name"] for a in state.transaction_account_options], ["محفظة"]
        )
        state.editor = "transaction"
        state.edit_id = str(txs[1].id)
        state.draft = {**state.draft, "account_id": str(closed_id)}
        self.assertEqual(
            [a["name"] for a in state.transaction_account_options],
            ["حساب قديم"],
        )

    def test_archived_category_editor_options_are_limited_to_original_transaction(
        self,
    ):
        active_id, archived_id, other_archived_id = (uuid4() for _ in range(3))
        transaction_id = uuid4()
        state = LedgerState()
        state.categories = [
            {"id": str(active_id), "name": "طعام", "kind": "expense"}
        ]
        state.archived_categories = [
            {"id": str(archived_id), "name": "قديمة", "kind": "expense"},
            {"id": str(other_archived_id), "name": "أخرى", "kind": "expense"},
        ]
        state.transactions = [
            {"id": str(transaction_id), "category_id": str(archived_id)}
        ]
        state.editor = "transaction"
        state.edit_id = str(transaction_id)
        state.draft = {**state.draft, "category_id": str(archived_id)}
        self.assertTrue(state.editing_archived_category)
        options = state.transaction_category_options
        self.assertEqual(
            [c["id"] for c in options], [str(active_id), str(archived_id)]
        )
        self.assertIn("مؤرشفة · لهذه المعاملة فقط", options[1]["name"])
        self.assertEqual(state.categories[0]["name"], "طعام")
        state.edit_id = str(uuid4())
        self.assertEqual(state.transaction_category_options, state.categories)
        state.edit_id = str(transaction_id)
        state.draft = {**state.draft, "category_id": str(other_archived_id)}
        self.assertEqual(state.transaction_category_options, state.categories)
        state.edit_id = ""
        self.assertEqual(state.transaction_category_options, state.categories)
        state.editor = "budget"
        state.edit_id = str(transaction_id)
        state.draft = {**state.draft, "category_id": str(archived_id)}
        self.assertEqual(state.transaction_category_options, state.categories)

    def test_archived_category_server_validation(self):
        archived_id, other_id, active_id = (uuid4() for _ in range(3))
        archived = SimpleNamespace(
            id=archived_id, kind="expense", is_archived=True
        )
        other_archived = SimpleNamespace(
            id=other_id, kind="expense", is_archived=True
        )
        active = SimpleNamespace(
            id=active_id, kind="expense", is_archived=False
        )
        historical = SimpleNamespace(category_id=archived_id)
        LedgerState._validate_transaction_category(
            None, historical, archived, "expense"
        )
        historical.amount = Decimal("125.00")
        historical.description = "تصحيح الوصف"
        LedgerState._validate_transaction_category(
            None, historical, archived, "expense"
        )
        self.assertEqual(historical.amount, Decimal("125.00"))
        self.assertEqual(historical.description, "تصحيح الوصف")
        with self.assertRaisesRegex(ValueError, "مؤرشفة"):
            LedgerState._validate_transaction_category(
                None, None, archived, "expense"
            )
        with self.assertRaisesRegex(ValueError, "مؤرشفة"):
            LedgerState._validate_transaction_category(
                None, historical, other_archived, "expense"
            )
        different = SimpleNamespace(category_id=active_id)
        with self.assertRaisesRegex(ValueError, "مؤرشفة"):
            LedgerState._validate_transaction_category(
                None, different, archived, "expense"
            )
        LedgerState._validate_transaction_category(
            None, historical, active, "expense"
        )
        with self.assertRaisesRegex(ValueError, "نوع المعاملة"):
            LedgerState._validate_transaction_category(
                None, historical, archived, "income"
            )
        with self.assertRaisesRegex(ValueError, "نوع المعاملة"):
            LedgerState._validate_transaction_category(
                None, historical, active, "income"
            )

    def test_closed_account_rejects_new_and_reassignment_but_allows_correction(
        self,
    ):
        closed_id, active_id = uuid4(), uuid4()
        closed = SimpleNamespace(id=closed_id, is_archived=True)
        active = SimpleNamespace(id=active_id, is_archived=False)
        record = SimpleNamespace(account_id=closed_id)
        with self.assertRaisesRegex(ValueError, "حساب مغلق"):
            LedgerState._validate_transaction_account(None, None, closed, None)
        with self.assertRaisesRegex(ValueError, "نقل معاملة"):
            LedgerState._validate_transaction_account(
                None, SimpleNamespace(account_id=active_id), closed, active
            )
        with self.assertRaisesRegex(ValueError, "الحساب نفسه"):
            LedgerState._validate_transaction_account(
                None, record, active, closed
            )
        LedgerState._validate_transaction_account(None, record, closed, closed)
        LedgerState._validate_transaction_account(None, None, active, None)


class RecurringScheduleTests(unittest.TestCase):
    def test_month_end_and_leap(self):
        start = date(2024, 1, 31)
        feb = next_recurring_date(start, start, "monthly")
        self.assertEqual(feb, date(2024, 2, 29))
        self.assertEqual(
            next_recurring_date(feb, start, "monthly"), date(2024, 3, 31)
        )
        start = date(2023, 1, 31)
        self.assertEqual(
            next_recurring_date(start, start, "monthly"), date(2023, 2, 28)
        )
        self.assertEqual(
            next_recurring_date(date(2023, 2, 28), start, "monthly"),
            date(2023, 3, 31),
        )

    def test_daily_weekly_and_max(self):
        self.assertEqual(
            next_recurring_date(date(2026, 1, 1), date(2026, 1, 1), "daily"),
            date(2026, 1, 2),
        )
        self.assertEqual(
            next_recurring_date(date(2026, 1, 1), date(2026, 1, 1), "weekly"),
            date(2026, 1, 8),
        )
        self.assertIsNone(next_recurring_date(date.max, date.max, "daily"))
        self.assertIsNone(next_recurring_date(date.max, date.max, "monthly"))


class BudgetMonthRegressionTests(unittest.IsolatedAsyncioTestCase):
    class January2026(date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 15)

    def make_load_db(self, current_budget=True):
        hid, uid, account_id, category_id = (uuid4() for _ in range(4))
        category = SimpleNamespace(
            id=category_id, name="طعام", kind="expense", is_archived=False
        )
        account = SimpleNamespace(
            id=account_id,
            name="محفظة",
            account_type="cash",
            opening_balance=Decimal("200.00"),
            opening_date=date(2025, 1, 1),
            is_archived=False,
        )

        def transaction(day, amount):
            return SimpleNamespace(
                id=uuid4(),
                account_id=account_id,
                category_id=category_id,
                kind="expense",
                amount=Decimal(amount),
                description="شراء",
                transaction_date=day,
            )

        def budget(year, month):
            return SimpleNamespace(
                id=uuid4(),
                category_id=category_id,
                year=year,
                month=month,
                amount=Decimal("100.00"),
                alert_threshold_percent=80,
            )

        december = budget(2025, 12)
        january = budget(2026, 1)
        rows = [december, january] if current_budget else [december]
        db = Mock()
        db.execute.return_value.all.return_value = []
        db.get.return_value = SimpleNamespace(name="البيت", currency="SAR")
        db.scalars.side_effect = [
            Mock(all=Mock(return_value=items))
            for items in (
                [SimpleNamespace(id=hid, name="البيت")],
                [category],
                [account],
                [],
                [
                    transaction(date(2025, 12, 5), "45.00"),
                    transaction(date(2025, 12, 28), "40.00"),
                    transaction(date(2026, 1, 10), "70.00"),
                    transaction(date(2026, 1, 12), "60.00"),
                ],
                rows,
                [],
                [],
                [],
                [],
            )
        ]
        return (
            db,
            SimpleNamespace(id=uid),
            SimpleNamespace(household_id=hid, role="owner"),
            december,
            january,
        )

    def load_months(self, state, current_budget=True):
        db, user, member, december, january = self.make_load_db(current_budget)
        with patch("app.states.ledger.date", self.January2026):
            state._load(db, user, member)
        return db, december, january

    def test_selected_december_and_dashboard_january_have_independent_spending(
        self,
    ):
        state = LedgerState()
        state.budget_month = "2025-12"
        db, december, january = self.load_months(state)
        self.assertEqual(state.budget_month, "2025-12")
        self.assertEqual([b["id"] for b in state.budgets], [str(december.id)])
        self.assertEqual(
            [b["id"] for b in state.dashboard_budgets], [str(january.id)]
        )
        self.assertEqual(state.budgets[0]["spent"], "85.00")
        self.assertEqual(state.budgets[0]["percent"], "85.0")
        self.assertEqual(state.budgets[0]["progress"], "85.00")
        self.assertEqual(state.budgets[0]["status"], "قرب الحد")
        self.assertEqual(state.dashboard_budgets[0]["spent"], "130.00")
        self.assertEqual(state.dashboard_budgets[0]["percent"], "130.0")
        self.assertEqual(state.dashboard_budgets[0]["progress"], "100")
        self.assertEqual(state.dashboard_budgets[0]["status"], "تجاوز الحد")
        self.assertEqual(state.dashboard_budgets[0]["month"], "2026-01")
        query = db.scalars.call_args_list[5].args[0]
        compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("2025", compiled)
        self.assertIn("2026", compiled)
        self.assertEqual(db.scalars.call_count, 10)

    def test_previous_month_does_not_fill_empty_current_month(self):
        state = LedgerState()
        state.budget_month = "2025-12"
        self.load_months(state, current_budget=False)
        self.assertEqual(len(state.budgets), 1)
        self.assertEqual(state.dashboard_budgets, [])
        self.assertEqual(state.budget_month, "2025-12")
        self.load_months(state, current_budget=False)
        self.assertEqual(len(state.budgets), 1)
        self.assertEqual(state.dashboard_budgets, [])

    async def test_change_month_and_budget_editor_keep_chosen_period(self):
        state = LedgerState()
        db, _, january = self.load_months(state)
        self.assertEqual(state.budget_month, "2026-01")
        self.assertEqual([b["id"] for b in state.budgets], [str(january.id)])
        self.assertEqual(state.budgets, state.dashboard_budgets)
        self.assertEqual(db.scalars.call_count, 10)
        event = LedgerState.change_month.fn(state, {"month": "2025-12"})
        self.assertIsNotNone(await anext(event))
        with self.assertRaises(StopAsyncIteration):
            await anext(event)
        self.load_months(state)
        self.assertEqual(state.budget_month, "2025-12")
        self.assertEqual(state.budgets[0]["month"], "2025-12")
        self.assertEqual(state.dashboard_budgets[0]["month"], "2026-01")
        LedgerState.open_editor.fn(state, "budget")
        self.assertEqual(state.draft["month"], "2025-12")
        self.assertEqual(state.edit_id, "")
        LedgerState.open_editor.fn(state, "budget", state.budgets[0]["id"])
        self.assertEqual(state.draft["month"], "2025-12")
        self.assertEqual(state.draft["amount"], "100.00")
        LedgerState.open_editor.fn(
            state, "budget", state.dashboard_budgets[0]["id"]
        )
        self.assertEqual(state.draft["month"], "2026-01")
        self.assertEqual(state.budget_month, "2025-12")
        bad_event = LedgerState.change_month.fn(state, {"month": "2025-13"})
        with self.assertRaises(StopAsyncIteration):
            await anext(bad_event)
        self.assertEqual(state.message, "اختر شهرًا صالحًا.")
        self.assertEqual(state.budget_month, "2025-12")

    async def test_save_budget_uses_form_month_and_keeps_dashboard_separate(
        self,
    ):
        state = LedgerState()
        state.budget_month = "2025-12"
        LedgerState.open_editor.fn(state, "budget")
        self.assertEqual(state.draft["month"], "2025-12")
        category_id = uuid4()
        category = SimpleNamespace(
            id=category_id, kind="expense", is_archived=False
        )
        user = SimpleNamespace(id=uuid4())
        member = SimpleNamespace(household_id=uuid4())
        auth = Mock()
        auth._household.return_value = (user, member)
        sync_db = Mock()
        sync_db.scalar.return_value = None
        db = Mock()

        async def run_sync(callback):
            return callback(sync_db)

        db.run_sync = AsyncMock(side_effect=run_sync)
        context = AsyncMock()
        context.__aenter__.return_value = db
        with (
            patch.object(
                LedgerState,
                "get_state",
                new_callable=AsyncMock,
                return_value=auth,
            ),
            patch.object(LedgerState, "_record", return_value=category),
            patch.object(LedgerState, "_budget_alerts"),
            patch.object(LedgerState, "_load") as reload_state,
            patch("app.states.ledger.rx.asession", return_value=context),
        ):
            await LedgerState.save.fn(
                state,
                {
                    "category_id": str(category_id),
                    "month": state.draft["month"],
                    "amount": "100.00",
                    "threshold": "80",
                },
            )
        self.assertEqual(state.message, "تم الحفظ بنجاح.")
        self.assertEqual(state.budget_month, "2025-12")
        self.assertEqual(state.editor, "")
        saved = sync_db.add.call_args.args[0]
        self.assertEqual((saved.year, saved.month), (2025, 12))
        reload_state.assert_called_once_with(sync_db, user, member)
        self.load_months(state)
        self.assertEqual(state.budgets[0]["month"], "2025-12")
        self.assertEqual(state.dashboard_budgets[0]["month"], "2026-01")


def AuthStateForTest():
    from app.states.auth import AuthState

    return AuthState


if __name__ == "__main__":
    unittest.main()
