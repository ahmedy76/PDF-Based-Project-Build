import reflex as rx

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.states.auth import (
    blocked_budget_currencies,
    require_account,
    require_permission,
    visible_account_ids,
)
from app.states.ledger import LedgerState
from app.test_multi_currency import MultiCurrencyTests


class PermissionChecks(unittest.TestCase):
    def setUp(self):
        self.hid, self.uid, self.visible, self.hidden = (
            uuid4() for _ in range(4)
        )
        self.member = SimpleNamespace(
            household_id=self.hid,
            user_id=self.uid,
            role="partner",
            can_add_transactions=False,
            can_edit_budgets=False,
        )
        self.db = Mock()
        self.db.scalars.return_value.all.return_value = [self.hidden]

    def test_owner_full_partner_flags_and_tenant_scoped_denials(self):
        for flag in ("can_add_transactions", "can_edit_budgets"):
            with self.assertRaises(ValueError):
                require_permission(self.member, flag)
        owner = SimpleNamespace(
            role="owner", household_id=self.hid, user_id=self.uid
        )
        require_permission(owner, "can_add_transactions")
        require_permission(owner, "can_edit_budgets")
        require_account(self.db, owner, self.hidden)
        self.db.scalars.assert_not_called()
        require_account(self.db, self.member, self.visible)
        with self.assertRaises(ValueError):
            require_account(self.db, self.member, self.hidden)
        ids = visible_account_ids(
            self.db,
            self.member,
            [
                SimpleNamespace(id=self.visible),
                SimpleNamespace(id=self.hidden),
            ],
        )
        self.assertEqual(ids, {self.visible})
        query = str(self.db.scalars.call_args.args[0])
        self.assertIn("mh_household_account_restrictions.household_id", query)
        self.assertIn("mh_household_account_restrictions.member_user_id", query)
        self.assertIn("mh_household_account_restrictions.account_id", query)

    def test_budget_currency_denial_scoped_to_household_and_user(self):
        self.db.scalars.return_value.all.return_value = ["USD"]
        self.assertEqual(
            blocked_budget_currencies(self.db, self.member), {"USD"}
        )
        sql = str(self.db.scalars.call_args.args[0])
        self.assertIn("mh_financial_accounts.household_id", sql)
        self.assertIn("mh_household_account_restrictions.member_user_id", sql)
        self.assertEqual(
            blocked_budget_currencies(self.db, SimpleNamespace(role="owner")),
            set(),
        )

    def test_hidden_audit_snapshots_never_render(self):
        event = SimpleNamespace(
            id=uuid4(),
            action="updated",
            actor_user_id=self.uid,
            created_at=__import__("datetime").datetime.now(),
            before_data={"account_id": str(self.hidden), "amount": "9999"},
            after_data={"account_id": str(self.visible), "amount": "1"},
            changed_fields=["account_id", "amount"],
        )
        state = LedgerState()
        self.assertEqual(
            state._history_rows([event], {}, {}, {}, {str(self.visible)}), []
        )
        self.assertEqual(len(state._history_rows([event], {}, {}, {})), 1)


class RestrictedLedgerLoad(unittest.TestCase):
    def test_two_currencies_and_hidden_transactions_are_excluded_from_every_aggregate(
        self,
    ):
        fixture = MultiCurrencyTests()
        fixture.setUp()
        state = LedgerState()
        state.budget_month = fixture.today.strftime("%Y-%m")
        member = SimpleNamespace(
            household_id=fixture.hid,
            user_id=fixture.uid,
            role="partner",
            can_add_transactions=False,
            can_edit_budgets=False,
        )
        db = Mock()
        db.get.return_value = SimpleNamespace(name="أسرة", currency="SAR")
        db.execute.return_value.all.return_value = []
        db.scalars.side_effect = [
            Mock(all=Mock(return_value=rows))
            for rows in (
                [SimpleNamespace(id=fixture.hid, name="أسرة")],
                [fixture.category],
                fixture.accounts,
                [fixture.accounts[0].id, fixture.accounts[2].id],
                [],
                fixture.txs[1:2],
                [
                    SimpleNamespace(
                        id=uuid4(),
                        source_account_id=fixture.accounts[1].id,
                        destination_account_id=fixture.accounts[0].id,
                        amount=__import__("decimal").Decimal("999"),
                        currency="USD",
                        transfer_date=fixture.today,
                        note="معلومة محجوبة",
                    )
                ],
                fixture.budgets,
                [],
                [],
                ["SAR"],
                [],
                [],
            )
        ]
        state.view_currency = "SAR"
        state.currency_household = str(fixture.hid)
        state._load(db, SimpleNamespace(id=fixture.uid), member)
        self.assertEqual(state.view_currencies, ["USD"])
        self.assertEqual(state.view_currency, "USD")
        self.assertEqual([a["name"] for a in state.accounts], ["دولار"])
        self.assertEqual(
            [t["account_id"] for t in state.transactions],
            [str(fixture.accounts[1].id)],
        )
        self.assertEqual(state.total, "150.00")
        self.assertEqual(state.expense, "50.00")
        self.assertEqual(state.report_expense, "50.00")
        self.assertEqual(state.report_values, [50.0])
        self.assertEqual(state.trend_expense[-1], 50.0)
        self.assertEqual(state.budgets[0]["spent"], "50.00")
        self.assertFalse(state.can_add_transactions)
        self.assertFalse(state.can_edit_budgets)
        self.assertEqual(state.transfers, [])
        transfer_sql = str(db.scalars.call_args_list[6].args[0])
        self.assertIn("mh_account_transfers.household_id", transfer_sql)
        self.assertIn("mh_account_transfers.source_account_id IN", transfer_sql)
        self.assertIn(
            "mh_account_transfers.destination_account_id IN", transfer_sql
        )
        sql = str(db.scalars.call_args_list[5].args[0])
        self.assertIn("mh_transactions.account_id IN", sql)


class MutationBypass(unittest.IsolatedAsyncioTestCase):
    async def test_direct_transaction_budget_and_recurring_bypass_rejected(
        self,
    ):
        state = LedgerState()
        uid, hid = uuid4(), uuid4()
        member = SimpleNamespace(
            role="partner",
            household_id=hid,
            user_id=uid,
            can_add_transactions=False,
            can_edit_budgets=False,
        )
        auth = Mock()
        auth._household.return_value = (SimpleNamespace(id=uid), member)
        db = Mock()
        session = Mock()

        async def run_sync(callback):
            return callback(db)

        session.run_sync = AsyncMock(side_effect=run_sync)
        context = AsyncMock()
        context.__aenter__.return_value = session
        with (
            patch.object(
                LedgerState,
                "get_state",
                new_callable=AsyncMock,
                return_value=auth,
            ),
            patch("app.states.ledger.rx.asession", return_value=context),
        ):
            for editor in ("transaction", "recurring", "budget"):
                state.editor = editor
                await LedgerState.save.fn(state, {})
                self.assertIn("صلاحية", state.message)
            await LedgerState.toggle_recurring.fn(state, str(uuid4()))
            self.assertIn("صلاحية", state.message)
            for kind in ("transaction", "budget"):
                state.delete_kind, state.delete_id = kind, str(uuid4())
                await LedgerState.confirm_delete.fn(state)
                self.assertIn("صلاحية", state.message)
        db.commit.assert_not_called()

    async def test_direct_account_edit_and_close_reject_hidden_account(self):
        state = LedgerState()
        uid, hid, aid = uuid4(), uuid4(), uuid4()
        member = SimpleNamespace(
            role="partner",
            household_id=hid,
            user_id=uid,
            can_add_transactions=True,
            can_edit_budgets=True,
        )
        auth = Mock()
        auth._household.return_value = (SimpleNamespace(id=uid), member)
        db = Mock()
        db.scalars.return_value.all.return_value = [aid]
        account = SimpleNamespace(id=aid, currency="SAR", is_archived=False)
        session = Mock()

        async def run_sync(callback):
            return callback(db)

        session.run_sync = AsyncMock(side_effect=run_sync)
        context = AsyncMock()
        context.__aenter__.return_value = session
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
            state.editor, state.edit_id = "account", str(aid)
            await LedgerState.save.fn(
                state,
                {"name": "محفظة", "account_type": "cash", "currency": "SAR"},
            )
            self.assertIn("غير متاح", state.message)
            state.delete_kind, state.delete_id = "account", str(aid)
            await LedgerState.confirm_delete.fn(state)
            self.assertIn("غير متاح", state.message)
        self.assertFalse(account.is_archived)
        db.commit.assert_not_called()

    async def test_history_id_cannot_open_blocked_account(self):
        state = LedgerState()
        uid, hid, aid, tid = uuid4(), uuid4(), uuid4(), uuid4()
        member = SimpleNamespace(role="partner", household_id=hid, user_id=uid)
        auth = Mock()
        auth._household.return_value = (SimpleNamespace(id=uid), member)
        db = Mock()
        db.scalar.return_value = SimpleNamespace(id=tid, account_id=aid)
        db.scalars.return_value.all.return_value = [aid]
        session = Mock()

        async def run_sync(callback):
            return callback(db)

        session.run_sync = AsyncMock(side_effect=run_sync)
        context = AsyncMock()
        context.__aenter__.return_value = session
        with (
            patch.object(
                LedgerState,
                "get_state",
                new_callable=AsyncMock,
                return_value=auth,
            ),
            patch("app.states.ledger.rx.asession", return_value=context),
        ):
            await LedgerState.show_transaction_history.fn(state, str(tid))
        self.assertEqual(state.history_events, [])
        self.assertEqual(state.history_id, "")
        self.assertIn("غير متاح", state.message)
        sql = str(db.scalar.call_args_list[0].args[0])
        self.assertIn("mh_transactions.household_id", sql)
        self.assertIn("mh_transactions.deleted_at IS NULL", sql)
