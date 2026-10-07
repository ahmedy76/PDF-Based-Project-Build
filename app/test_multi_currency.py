import reflex as rx

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app import models as m
from app.states.ledger import LedgerState


class MultiCurrencyTests(unittest.TestCase):
    def setUp(self):
        self.hid, self.uid, self.category_id = uuid4(), uuid4(), uuid4()
        self.today = date.today()
        self.accounts = [
            SimpleNamespace(
                id=uuid4(),
                name=name,
                currency=currency,
                account_type="cash",
                opening_balance=Decimal(opening),
                opening_date=self.today,
                is_archived=archived,
            )
            for name, currency, opening, archived in (
                ("محفظة", "SAR", "100", False),
                ("دولار", "USD", "200", False),
                ("دولار مغلق", "USD", "30", True),
            )
        ]
        self.category = SimpleNamespace(
            id=self.category_id, name="طعام", kind="expense", is_archived=False
        )
        self.txs = [
            SimpleNamespace(
                id=uuid4(),
                account_id=account.id,
                category_id=self.category_id,
                kind="expense",
                amount=Decimal(amount),
                transaction_date=self.today,
                description=account.name,
            )
            for account, amount in zip(self.accounts, ("10", "50", "5"))
        ]
        self.budgets = [
            SimpleNamespace(
                id=uuid4(),
                category_id=self.category_id,
                currency=currency,
                year=self.today.year,
                month=self.today.month,
                amount=Decimal("40"),
                alert_threshold_percent=80,
            )
            for currency in ("SAR", "USD")
        ]

    def load(self, state, transfers=()):
        db = Mock()
        db.get.return_value = SimpleNamespace(name="أسرة", currency="SAR")
        db.execute.return_value.all.return_value = []
        db.scalars.side_effect = [
            Mock(all=Mock(return_value=rows))
            for rows in (
                [SimpleNamespace(id=self.hid, name="أسرة")],
                [self.category],
                self.accounts,
                [],
                self.txs,
                transfers,
                self.budgets,
                [],
                [],
                [],
                [],
            )
        ]
        state._load(
            db,
            SimpleNamespace(id=self.uid),
            SimpleNamespace(household_id=self.hid, role="owner"),
        )
        return db

    def test_balances_spending_reports_and_archives_are_separate(self):
        state = LedgerState()
        state.period = "current"
        state.budget_month = self.today.strftime("%Y-%m")
        self.load(state)
        self.assertEqual(state.view_currencies, ["SAR", "USD"])
        self.assertEqual(state.total, "90.00")
        self.assertEqual(state.expense, "10.00")
        self.assertEqual(state.report_expense, "10.00")
        self.assertEqual(state.report_values, [10.0])
        self.assertEqual(state.trend_expense[-1], 10.0)
        self.assertEqual(state.archived_total, "0.00")
        self.assertEqual(state.budgets[0]["spent"], "10.00")
        self.assertEqual(state.budgets[0]["currency"], "SAR")
        self.assertEqual(
            [t["currency"] for t in state.transactions], ["SAR", "USD", "USD"]
        )
        state.view_currency = "USD"
        self.load(state)
        self.assertEqual(state.total, "150.00")
        self.assertEqual(state.archived_total, "25.00")
        self.assertTrue(state.has_archived_balance)
        self.assertEqual(state.expense, "55.00")
        self.assertEqual(state.report_expense, "55.00")
        self.assertEqual(state.report_values, [55.0])
        self.assertEqual(state.trend_expense[-1], 55.0)
        self.assertEqual(state.budgets[0]["spent"], "55.00")
        self.assertEqual(state.budgets[0]["status"], "تجاوز الحد")
        self.assertEqual(state.dashboard_budgets[0]["currency"], "USD")
        self.assertEqual(
            state.active_currencies,
            [{"id": "SAR", "name": "SAR"}, {"id": "USD", "name": "USD"}],
        )

    def test_archived_only_currency_still_available_for_history(self):
        self.accounts[1].is_archived = True
        state = LedgerState()
        state.period = "current"
        self.load(state)
        self.assertEqual(state.view_currencies, ["SAR", "USD"])
        self.assertEqual(
            state.active_currencies, [{"id": "SAR", "name": "SAR"}]
        )
        state.view_currency = "USD"
        self.load(state)
        self.assertEqual(state.total, "0.00")
        self.assertEqual(state.archived_total, "175.00")
        self.assertEqual(state.report_expense, "55.00")

    def test_alert_query_joins_account_and_filters_currency(self):
        db = Mock()
        db.scalars.side_effect = [
            Mock(all=Mock(return_value=self.budgets)),
            Mock(all=Mock(return_value=[])),
            Mock(all=Mock(return_value=[])),
            Mock(all=Mock(return_value=[])),
            Mock(all=Mock(return_value=[])),
        ]
        db.scalar.return_value = Decimal("55")
        state = LedgerState()
        state._budget_alerts(db, self.hid)
        sql = str(db.scalar.call_args_list[0].args[0])
        self.assertIn("mh_financial_accounts.currency", sql)
        self.assertIn(
            "mh_financial_accounts.id = mh_transactions.account_id", sql
        )
        self.assertIn("mh_transactions.deleted_at IS NULL", sql)
        self.assertIn("mh_transactions.household_id", sql)

    def test_migrated_budget_schema_uniqueness_includes_currency(self):
        constraints = m.MonthlyCategoryBudget.__table__.constraints
        self.assertTrue(
            any(
                c.name == "uq_mh_budget_category_month_currency"
                and {col.name for col in c.columns}
                == {"household_id", "category_id", "year", "month", "currency"}
                for c in constraints
                if hasattr(c, "columns")
            )
        )


class AccountCurrencyProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_currency_switch_rejects_unavailable_code_and_keeps_dates(
        self,
    ):
        state = LedgerState()
        state.view_currencies = ["SAR", "USD"]
        state.view_currency = "SAR"
        state.budget_month = "2025-12"
        state.report_start, state.report_end = "2025-10-01", "2025-10-31"
        event = LedgerState.set_view_currency.fn(state, "EUR")
        with self.assertRaises(StopAsyncIteration):
            await anext(event)
        self.assertEqual(state.view_currency, "SAR")
        event = LedgerState.set_view_currency.fn(state, "USD")
        self.assertIsNotNone(await anext(event))
        self.assertEqual(state.view_currency, "USD")
        self.assertEqual(state.budget_month, "2025-12")
        self.assertEqual(
            (state.report_start, state.report_end), ("2025-10-01", "2025-10-31")
        )

    async def test_saved_account_currency_cannot_change_even_without_transactions(
        self,
    ):
        state = LedgerState()
        account_id = uuid4()
        state.editor = "account"
        state.edit_id = str(account_id)
        account = SimpleNamespace(
            id=account_id, currency="SAR", is_archived=False
        )
        user, member = (
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(household_id=uuid4(), role="owner"),
        )
        auth = Mock()
        auth._household.return_value = (user, member)
        sync_db = Mock()
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
            patch.object(LedgerState, "_record", return_value=account),
            patch("app.states.ledger.rx.asession", return_value=context),
        ):
            await LedgerState.save.fn(
                state,
                {
                    "name": "محفظة",
                    "account_type": "cash",
                    "currency": "USD",
                    "opening_balance": "100",
                    "opening_date": date.today().isoformat(),
                },
            )
        self.assertIn("ثابتة", state.message)
        self.assertEqual(account.currency, "SAR")
        sync_db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
