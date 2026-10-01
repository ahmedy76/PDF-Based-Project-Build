import reflex as rx

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app import models as m
from app.states.ledger import LedgerState
from app.test_multi_currency import MultiCurrencyTests


class TransferBalanceTests(unittest.TestCase):
    def test_transfer_moves_balance_without_changing_income_expense_or_reports(
        self,
    ):
        fixture = MultiCurrencyTests()
        fixture.setUp()
        fixture.accounts[1].currency = "SAR"
        transfer = SimpleNamespace(
            id=uuid4(),
            source_account_id=fixture.accounts[0].id,
            destination_account_id=fixture.accounts[1].id,
            currency="SAR",
            amount=Decimal("25.1250"),
            transfer_date=fixture.today,
            note="نقل داخلي",
        )
        state = LedgerState()
        baseline = LedgerState()
        fixture.load(baseline)
        db = fixture.load(state, [transfer])
        self.assertEqual(state.accounts[0]["balance"], "64.88")
        self.assertEqual(state.accounts[1]["balance"], "175.12")
        self.assertEqual(state.total, baseline.total)
        self.assertEqual(state.expense, baseline.expense)
        self.assertEqual(state.income, baseline.income)
        self.assertEqual(state.report_expense, baseline.report_expense)
        self.assertEqual(state.report_income, baseline.report_income)
        self.assertEqual(state.report_values, baseline.report_values)
        self.assertEqual(state.trend_expense, baseline.trend_expense)
        self.assertEqual(state.budgets, baseline.budgets)
        self.assertEqual(len(state.transactions), len(baseline.transactions))
        self.assertEqual(state.transfers[0]["note"], "نقل داخلي")
        sql = str(db.scalars.call_args_list[5].args[0])
        self.assertIn("mh_account_transfers.household_id", sql)
        self.assertIn("mh_account_transfers.source_account_id IN", sql)
        self.assertIn("mh_account_transfers.destination_account_id IN", sql)
        state.view_currency = "USD"
        fixture.load(state, [transfer])
        self.assertEqual(state.total, "0.00")
        self.assertEqual(state.archived_total, "25.00")

    def test_partial_transfer_never_changes_visible_balance_or_history(self):
        fixture = MultiCurrencyTests()
        fixture.setUp()
        hidden_transfer = SimpleNamespace(
            id=uuid4(),
            source_account_id=fixture.accounts[0].id,
            destination_account_id=fixture.accounts[2].id,
            currency="USD",
            amount=Decimal("999"),
            transfer_date=fixture.today,
            note="سري",
        )
        state = LedgerState()
        balances = state._account_balances(
            fixture.accounts[:1], fixture.txs[:1], [hidden_transfer]
        )
        self.assertEqual(balances[fixture.accounts[0].id], Decimal("90"))
        self.assertEqual(state.transfers, [])


class TransferSaveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = LedgerState()
        self.hid, self.uid = uuid4(), uuid4()
        self.accounts = [
            SimpleNamespace(
                id=uuid4(),
                household_id=self.hid,
                currency="SAR",
                opening_date=date(2020, 1, 1),
                is_archived=False,
            )
            for _ in range(2)
        ]
        self.member = SimpleNamespace(
            role="partner",
            household_id=self.hid,
            user_id=self.uid,
            can_add_transactions=True,
        )
        self.auth = Mock()
        self.auth._household.return_value = (
            SimpleNamespace(id=self.uid),
            self.member,
        )
        self.db = Mock()
        self.db.scalars.return_value.all.return_value = self.accounts

        def scalar_rows(query):
            sql = str(query)
            if "mh_household_account_restrictions" in sql:
                return Mock(all=Mock(return_value=[]))
            if "mh_financial_accounts" in sql:
                return Mock(
                    all=Mock(
                        side_effect=lambda: (
                            self.db.scalars.return_value.all.return_value
                        )
                    )
                )
            raise AssertionError(f"Unexpected scalars query: {sql}")

        self.db.scalars.side_effect = scalar_rows
        session = Mock()

        async def run_sync(callback):
            return callback(self.db)

        session.run_sync = AsyncMock(side_effect=run_sync)
        self.context = AsyncMock()
        self.context.__aenter__.return_value = session
        self.data = {
            "source_account_id": str(self.accounts[0].id),
            "destination_account_id": str(self.accounts[1].id),
            "amount": "12.1234",
            "transfer_date": date.today().isoformat(),
            "note": " بين الحسابات ",
        }

    async def save(self, data=None):
        with (
            patch.object(
                LedgerState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch.object(LedgerState, "_load"),
            patch("app.states.ledger.rx.asession", return_value=self.context),
        ):
            await LedgerState.save_transfer.fn(
                self.state, self.data if data is None else data
            )

    async def test_valid_transfer_creates_one_record_without_transaction(self):
        await self.save()
        self.db.commit.assert_called_once()
        self.db.add.assert_called_once()
        record = self.db.add.call_args.args[0]
        self.assertIsInstance(record, m.AccountTransfer)
        self.assertEqual(record.amount, Decimal("12.1234"))
        self.assertEqual(record.currency, "SAR")
        self.assertEqual(record.household_id, self.hid)
        self.assertEqual(record.note, "بين الحسابات")
        self.assertIn("بنجاح", self.state.message)
        sql = str(self.db.scalars.call_args_list[0].args[0])
        self.assertIn("mh_financial_accounts.household_id", sql)
        self.assertIn("mh_financial_accounts.is_archived IS false", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertEqual(self.db.scalars.call_count, 3)
        for call in self.db.scalars.call_args_list[1:]:
            self.assertIn(
                "mh_household_account_restrictions", str(call.args[0])
            )

    async def test_currency_self_invalid_amount_and_dates_are_denied(self):
        for change in (
            {"destination_account_id": str(self.accounts[0].id)},
            {"amount": "0"},
            {"amount": "1.12345"},
            {"amount": "NaN"},
            {"amount": "Infinity"},
            {"transfer_date": "2020-02-30"},
            {"transfer_date": "1999-01-01"},
            {"note": "n" * 501},
        ):
            with self.subTest(change=change):
                await self.save({**self.data, **change})
                self.assertNotEqual(self.state.transfer_error, "")
                self.db.commit.assert_not_called()
                self.db.add.assert_not_called()
        self.accounts[1].currency = "USD"
        await self.save()
        self.assertIn("العملة نفسها", self.state.transfer_error)
        self.db.commit.assert_not_called()

    async def test_cross_household_archived_hidden_and_permission_bypass(self):
        self.member.can_add_transactions = False
        await self.save()
        self.assertIn("صلاحية", self.state.transfer_error)
        self.db.scalars.assert_not_called()
        self.member.can_add_transactions = True
        for bad in ("cross", "archived"):
            with self.subTest(bad=bad):
                self.db.scalars.return_value.all.return_value = self.accounts[
                    :1
                ]
                await self.save()
                self.assertIn("غير متاح", self.state.transfer_error)
                self.db.commit.assert_not_called()
        self.db.scalars.side_effect = [
            Mock(all=Mock(return_value=self.accounts)),
            Mock(all=Mock(return_value=[self.accounts[1].id])),
            Mock(all=Mock(return_value=[self.accounts[1].id])),
        ]
        await self.save()
        self.assertIn("غير متاح", self.state.transfer_error)
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
