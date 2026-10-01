import reflex as rx

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app import models as m
from app.states.ledger import LedgerState


class TransactionAuditTests(unittest.TestCase):
    def setUp(self):
        self.state = LedgerState()
        self.hid, self.uid, self.aid, self.cid = (uuid4() for _ in range(4))
        self.transaction = SimpleNamespace(
            id=uuid4(),
            household_id=self.hid,
            account_id=self.aid,
            category_id=self.cid,
            kind="expense",
            amount=Decimal("12.5000"),
            transaction_date=date(2026, 2, 1),
            description="مشتريات",
        )

    def test_snapshot_is_only_six_json_safe_fields(self):
        snapshot = self.state._transaction_snapshot(self.transaction)
        self.assertEqual(
            snapshot,
            {
                "account_id": str(self.aid),
                "category_id": str(self.cid),
                "kind": "expense",
                "amount": "12.5000",
                "transaction_date": "2026-02-01",
                "description": "مشتريات",
            },
        )
        self.assertNotIn("household_id", snapshot)

    def test_create_update_noop_and_delete(self):
        db = Mock()
        self.assertTrue(
            self.state._append_transaction_event(
                db, self.transaction, "created", self.uid
            )
        )
        created = db.add.call_args.args[0]
        self.assertIsInstance(created, m.TransactionAuditEvent)
        self.assertEqual(
            (created.household_id, created.actor_user_id), (self.hid, self.uid)
        )
        self.assertEqual(created.before_data, {})
        self.assertEqual(len(created.changed_fields), 6)
        before = self.state._transaction_snapshot(self.transaction)
        db.reset_mock()
        self.transaction.amount = Decimal("12.50")
        self.assertFalse(
            self.state._append_transaction_event(
                db, self.transaction, "updated", self.uid, before
            )
        )
        db.add.assert_not_called()
        self.transaction.description = "جديد"
        self.assertTrue(
            self.state._append_transaction_event(
                db, self.transaction, "updated", self.uid, before
            )
        )
        self.assertEqual(
            db.add.call_args.args[0].changed_fields, ["description"]
        )
        self.assertTrue(
            self.state._append_transaction_event(
                db, self.transaction, "deleted", self.uid, before
            )
        )
        deleted = db.add.call_args.args[0]
        self.assertEqual(deleted.before_data, before)
        self.assertEqual(deleted.after_data, {})

    def test_history_labels_and_archived_names(self):
        event = SimpleNamespace(
            id=uuid4(),
            action="updated",
            actor_user_id=self.uid,
            created_at=datetime(2026, 2, 2, 12, 30, tzinfo=timezone.utc),
            before_data={"account_id": str(self.aid), "kind": "expense"},
            after_data={"account_id": str(uuid4()), "kind": "income"},
            changed_fields=["account_id", "kind"],
        )
        row = self.state._history_rows(
            [event], {self.uid: "شريك"}, {str(self.aid): "حساب مؤرشف"}, {}
        )[0]
        self.assertEqual(row["actor"], "شريك")
        self.assertEqual(row["changes"][0]["before"], "حساب مؤرشف")
        self.assertEqual(row["changes"][0]["after"], "حساب سابق")
        self.assertEqual(row["changes"][1]["after"], "دخل")

    def test_prefill_and_kind_switch_excludes_archives_and_amount(self):
        state = self.state
        state.accounts = [{"id": str(self.aid), "name": "محفظة"}]
        state.archived_accounts = [{"id": str(uuid4()), "name": "مغلق"}]
        state.categories = [
            {"id": str(self.cid), "name": "طعام", "kind": "expense"},
            {"id": str(uuid4()), "name": "راتب", "kind": "income"},
        ]
        state.transactions = [
            {
                "id": str(self.transaction.id),
                "account_id": str(self.aid),
                "category_id": str(self.cid),
                "kind": "expense",
                "amount": "99.00",
                "description": "غداء",
                "transaction_date": "2026-01-01",
            }
        ]
        LedgerState.open_editor.fn(state, "transaction")
        self.assertEqual(state.draft["account_id"], str(self.aid))
        self.assertEqual(state.draft["category_id"], str(self.cid))
        self.assertEqual(state.draft["amount"], "")
        LedgerState.reuse_transaction.fn(state, str(self.transaction.id))
        self.assertEqual(state.edit_id, "")
        self.assertEqual(state.draft["description"], "غداء")
        self.assertEqual(state.draft["amount"], "")
        self.assertEqual(
            state.draft["transaction_date"], date.today().isoformat()
        )
        LedgerState.change_transaction_kind.fn(state, "income")
        self.assertEqual(state.draft["category_id"], state.categories[1]["id"])
        self.assertEqual(
            [c["kind"] for c in state.transaction_category_options], ["income"]
        )
        state.accounts = []
        state.categories = []
        LedgerState.open_editor.fn(state, "transaction")
        self.assertEqual(state.draft["account_id"], "")
        self.assertEqual(state.draft["category_id"], "")


class AuditEventIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_noop_and_soft_delete_actor(self):
        state = LedgerState()
        state.editor = "transaction"
        user, member = (
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(household_id=uuid4()),
        )
        account = SimpleNamespace(
            id=uuid4(), opening_date=date(2020, 1, 1), is_archived=False
        )
        category = SimpleNamespace(
            id=uuid4(), kind="expense", is_archived=False
        )
        record = m.Transaction(
            id=uuid4(),
            household_id=member.household_id,
            created_by_user_id=uuid4(),
            account_id=account.id,
            category_id=category.id,
            kind="expense",
            amount=Decimal("20.0000"),
            transaction_date=date.today(),
            description="شراء",
            deleted_at=None,
        )
        state.edit_id = str(record.id)
        auth = Mock()
        auth._household.return_value = (user, member)
        sync_db = Mock()
        sync_db.scalar.return_value = None
        sync_db.scalars.return_value.all.return_value = []
        db = Mock()

        async def run_sync(callback):
            return callback(sync_db)

        db.run_sync = AsyncMock(side_effect=run_sync)
        context = AsyncMock()
        context.__aenter__.return_value = db

        def get_record(session, model, ident, hid):
            self.assertEqual(hid, member.household_id)
            return {
                m.FinancialAccount: account,
                m.Category: category,
                m.Transaction: record,
            }[model]

        data = {
            "account_id": str(account.id),
            "category_id": str(category.id),
            "kind": "expense",
            "amount": "20.00",
            "description": "شراء",
            "transaction_date": date.today().isoformat(),
        }
        with (
            patch.object(
                LedgerState,
                "get_state",
                new_callable=AsyncMock,
                return_value=auth,
            ),
            patch.object(LedgerState, "_record", side_effect=get_record),
            patch.object(LedgerState, "_budget_alerts"),
            patch.object(LedgerState, "_load"),
            patch("app.states.ledger.rx.asession", return_value=context),
        ):
            await LedgerState.save.fn(state, data)
            self.assertEqual(state.message, "تم الحفظ بنجاح.")
            self.assertFalse(
                any(
                    isinstance(c.args[0], m.TransactionAuditEvent)
                    for c in sync_db.add.call_args_list
                )
            )
            sync_db.reset_mock()
            state.editor, state.edit_id = "transaction", str(record.id)
            await LedgerState.save.fn(state, {**data, "description": "تغيير"})
            events = [
                c.args[0]
                for c in sync_db.add.call_args_list
                if isinstance(c.args[0], m.TransactionAuditEvent)
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(
                (events[0].action, events[0].actor_user_id),
                ("updated", user.id),
            )
            self.assertEqual(events[0].changed_fields, ["description"])
            sync_db.reset_mock()
            state.delete_kind, state.delete_id = "transaction", str(record.id)
            await LedgerState.confirm_delete.fn(state)
            events = [
                c.args[0]
                for c in sync_db.add.call_args_list
                if isinstance(c.args[0], m.TransactionAuditEvent)
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(
                (events[0].action, events[0].actor_user_id),
                ("deleted", user.id),
            )
            self.assertEqual(events[0].before_data["description"], "تغيير")
            self.assertIsNotNone(record.deleted_at)

    async def test_manual_save_and_history_tenant_guard(self):
        state = LedgerState()
        state.editor = "transaction"
        state.edit_id = ""
        user, member = (
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(household_id=uuid4()),
        )
        account = SimpleNamespace(
            id=uuid4(), opening_date=date(2020, 1, 1), is_archived=False
        )
        category = SimpleNamespace(
            id=uuid4(), kind="expense", is_archived=False
        )
        auth = Mock()
        auth._household.return_value = (user, member)
        sync_db = Mock()
        sync_db.scalar.return_value = None
        sync_db.scalars.return_value.all.return_value = []
        sync_db.execute.return_value.all.return_value = []
        db = Mock()

        async def run_sync(callback):
            return callback(sync_db)

        db.run_sync = AsyncMock(side_effect=run_sync)
        context = AsyncMock()
        context.__aenter__.return_value = db

        def get_record(session, model, ident, hid):
            self.assertEqual(hid, member.household_id)
            return account if model is m.FinancialAccount else category

        with (
            patch.object(
                LedgerState,
                "get_state",
                new_callable=AsyncMock,
                return_value=auth,
            ),
            patch.object(LedgerState, "_record", side_effect=get_record),
            patch.object(LedgerState, "_budget_alerts"),
            patch.object(LedgerState, "_load"),
            patch("app.states.ledger.rx.asession", return_value=context),
        ):
            await LedgerState.save.fn(
                state,
                {
                    "account_id": str(account.id),
                    "category_id": str(category.id),
                    "kind": "expense",
                    "amount": "20",
                    "description": "شراء",
                    "transaction_date": date.today().isoformat(),
                },
            )
            self.assertEqual(state.message, "تم الحفظ بنجاح.")
            events = [
                call.args[0]
                for call in sync_db.add.call_args_list
                if isinstance(call.args[0], m.TransactionAuditEvent)
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(
                (events[0].action, events[0].actor_user_id),
                ("created", user.id),
            )
            self.assertEqual(events[0].household_id, member.household_id)
            self.assertEqual(sync_db.commit.call_count, 1)
            state.history_id = "stale"
            await LedgerState.show_transaction_history.fn(state, str(uuid4()))
            self.assertEqual(state.history_id, "")
            self.assertEqual(state.history_events, [])
            self.assertIn("غير متاحة", state.message)
            history_query = sync_db.scalar.call_args.args[0]
            self.assertIn("mh_transactions.household_id", str(history_query))
            self.assertIn(
                "mh_transactions.deleted_at IS NULL", str(history_query)
            )
