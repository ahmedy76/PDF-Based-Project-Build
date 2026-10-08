import reflex as rx

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.components.member_access import (
    account_switch,
    member_access_panel,
    member_card,
)
from app.states.member_access import MemberAccessState


class MemberAccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.household_id = uuid4()
        self.owner_id = uuid4()
        self.partner_id = uuid4()
        self.account_id = uuid4()
        self.household = SimpleNamespace(
            id=self.household_id, owner_user_id=self.owner_id
        )
        self.user = SimpleNamespace(id=self.owner_id)
        self.owner = SimpleNamespace(
            household_id=self.household_id, user_id=self.owner_id, role="owner"
        )
        self.partner = SimpleNamespace(
            household_id=self.household_id,
            user_id=self.partner_id,
            role="partner",
            status="active",
            can_add_transactions=True,
            can_edit_budgets=True,
        )
        self.account = SimpleNamespace(
            id=self.account_id,
            household_id=self.household_id,
            name="حساب توفير",
            currency="SAR",
            is_archived=True,
        )
        self.auth = Mock()
        self.auth._household.return_value = (self.user, self.owner)
        self.db = Mock()
        self.db.scalar.side_effect = self.scalar
        self.db.execute.return_value.all.return_value = [
            (self.partner, "شريك الأسرة")
        ]
        self.denied = []
        self.db.scalars.side_effect = self.scalars
        self.db.get.return_value = self.household
        self.session = Mock()

        async def run_sync(callback):
            return callback(self.db)

        self.session.run_sync = AsyncMock(side_effect=run_sync)
        self.context = AsyncMock()
        self.context.__aenter__.return_value = self.session
        self.state = MemberAccessState()
        self.patches = [
            patch.object(
                MemberAccessState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch(
                "app.states.member_access.rx.asession",
                return_value=self.context,
            ),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(
            lambda: [item.stop() for item in reversed(self.patches)]
        )

    def scalar(self, query):
        sql = str(query)
        parameters = query.compile().params.values()
        if "FROM mh_households" in sql:
            return self.household if self.household_id in parameters else None
        if "FROM mh_household_memberships" in sql:
            return (
                self.partner
                if self.partner_id in parameters
                and self.partner
                and self.partner.status == "active"
                and self.partner.household_id == self.household_id
                else None
            )
        if "FROM mh_financial_accounts" in sql:
            return (
                self.account
                if self.account_id in parameters
                and self.account
                and self.account.household_id == self.household_id
                else None
            )
        if "FROM mh_household_account_restrictions" in sql:
            return self.denied[0] if self.denied else None
        raise AssertionError(sql)

    def scalars(self, query):
        sql = str(query)
        if "FROM mh_financial_accounts" in sql:
            return Mock(all=Mock(return_value=[self.account]))
        if "FROM mh_household_account_restrictions" in sql:
            return Mock(all=Mock(return_value=self.denied))
        raise AssertionError(sql)

    async def test_owner_load_only_names_default_permissions_and_archived_account(
        self,
    ):
        await MemberAccessState.load.fn(self.state)
        self.assertTrue(self.state.owner)
        self.assertEqual(self.state.members[0]["name"], "شريك الأسرة")
        self.assertNotIn("email", self.state.members[0])
        self.assertTrue(self.state.members[0]["can_add_transactions"])
        self.assertTrue(self.state.members[0]["can_edit_budgets"])
        self.assertTrue(self.state.members[0]["accounts"][0]["visible"])
        self.assertTrue(self.state.members[0]["accounts"][0]["archived"])
        self.denied = [
            SimpleNamespace(
                member_user_id=self.partner_id, account_id=self.account_id
            )
        ]
        await MemberAccessState.load.fn(self.state)
        self.assertFalse(self.state.members[0]["accounts"][0]["visible"])

    async def test_partner_load_clears_prior_owner_controls_without_query(self):
        self.state.members = [
            {
                "id": str(self.partner_id),
                "name": "قديم",
                "can_add_transactions": True,
                "can_edit_budgets": True,
                "accounts": [],
            }
        ]
        self.state.owner = True
        self.auth._household.return_value = (
            SimpleNamespace(id=self.partner_id),
            SimpleNamespace(
                user_id=self.partner_id,
                role="partner",
                household_id=self.household_id,
            ),
        )
        await MemberAccessState.load.fn(self.state)
        self.assertEqual(self.state.members, [])
        self.assertFalse(self.state.owner)
        self.db.execute.assert_not_called()
        self.db.scalars.assert_not_called()

    async def test_disclosure_default_off_owner_only_and_no_role_assignment(
        self,
    ):
        await MemberAccessState.load.fn(self.state)
        self.assertFalse(self.state.members[0]["can_view_commitments"])
        self.partner.can_view_commitments = False
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_view_commitments"
        )
        self.assertTrue(self.partner.can_view_commitments)
        self.assertEqual(self.partner.role, "partner")
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_view_commitments"
        )
        self.assertFalse(self.partner.can_view_commitments)
        self.db.commit.reset_mock()
        self.auth._household.return_value = (
            SimpleNamespace(id=self.partner_id),
            self.partner,
        )
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_view_commitments"
        )
        self.assertTrue(self.state.error)
        self.db.commit.assert_not_called()
        self.assertFalse(self.partner.can_view_commitments)

    async def test_independent_permissions_persist_and_reload(self):
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_add_transactions"
        )
        self.assertFalse(self.partner.can_add_transactions)
        self.assertTrue(self.partner.can_edit_budgets)
        self.assertFalse(self.state.members[0]["can_add_transactions"])
        self.assertFalse(self.state.error)
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_edit_budgets"
        )
        self.assertFalse(self.partner.can_edit_budgets)
        self.assertEqual(self.db.commit.call_count, 2)
        self.assertIn(
            "FOR UPDATE", str(self.db.scalar.call_args_list[0].args[0])
        )

    async def test_rejects_partner_owner_foreign_and_inactive_targets(self):
        self.auth._household.return_value = (
            SimpleNamespace(id=self.partner_id),
            SimpleNamespace(
                user_id=self.partner_id,
                household_id=self.household_id,
                role="partner",
            ),
        )
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_add_transactions"
        )
        self.assertTrue(self.state.error)
        self.db.commit.assert_not_called()
        self.auth._household.return_value = (self.user, self.owner)
        for target_id in (self.owner_id, uuid4()):
            await MemberAccessState.toggle_permission.fn(
                self.state, str(target_id), "can_add_transactions"
            )
            self.assertTrue(self.state.error)
        self.partner.status = "removed"
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_add_transactions"
        )
        self.partner.status = "active"
        self.partner.household_id = uuid4()
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "can_add_transactions"
        )
        self.db.commit.assert_not_called()

    async def test_rejects_invalid_permission_and_account_and_foreign_household(
        self,
    ):
        await MemberAccessState.toggle_permission.fn(
            self.state, str(self.partner_id), "role"
        )
        self.assertTrue(self.state.error)
        await MemberAccessState.toggle_account.fn(
            self.state, str(self.partner_id), "bad-id"
        )
        self.assertTrue(self.state.error)
        self.account.household_id = uuid4()
        await MemberAccessState.toggle_account.fn(
            self.state, str(self.partner_id), str(self.account_id)
        )
        self.assertTrue(self.state.error)
        self.account = None
        await MemberAccessState.toggle_account.fn(
            self.state, str(self.partner_id), str(self.account_id)
        )
        self.assertTrue(self.state.error)
        self.partner = None
        await MemberAccessState.toggle_account.fn(
            self.state, str(self.partner_id), str(uuid4())
        )
        self.assertTrue(self.state.error)
        self.household.owner_user_id = uuid4()
        await MemberAccessState.toggle_account.fn(
            self.state, str(self.partner_id), str(self.account_id)
        )
        self.assertFalse(self.state.owner)
        self.db.commit.assert_not_called()

    async def test_restriction_is_added_then_removed_atomically(self):
        await MemberAccessState.toggle_account.fn(
            self.state, str(self.partner_id), str(self.account_id)
        )
        created = self.db.add.call_args.args[0]
        self.assertEqual(created.household_id, self.household_id)
        self.assertEqual(created.member_user_id, self.partner_id)
        self.assertEqual(created.account_id, self.account_id)
        self.assertEqual(self.db.commit.call_count, 1)
        self.denied = [created]
        await MemberAccessState.toggle_account.fn(
            self.state, str(self.partner_id), str(self.account_id)
        )
        self.db.delete.assert_called_once_with(created)
        self.assertEqual(self.db.commit.call_count, 2)

    def test_disclosure_permission_is_on_member_card_not_account_row(self):
        member = MemberAccessState.members[0]
        account = member["accounts"][0]
        row = str(account_switch(member, account))
        card = str(member_card(member))
        self.assertNotIn("planning.disclosure", row)
        self.assertNotIn("can_view_commitments", row)
        self.assertIn("planning.disclosure", card)

    def test_ui_panel_uses_existing_settings_controls(self):
        panel = member_access_panel()
        self.assertIsInstance(panel, rx.Component)
        representation = str(panel)
        self.assertIn(
            json.dumps("صلاحيات أفراد الأسرة", ensure_ascii=True)[1:-1],
            representation,
        )
        self.assertIn(
            json.dumps("إضافة معاملات", ensure_ascii=True)[1:-1], representation
        )
        self.assertIn(
            json.dumps("تعديل الميزانيات", ensure_ascii=True)[1:-1],
            representation,
        )
        self.assertIn(
            json.dumps("يستطيع الاطلاع", ensure_ascii=True)[1:-1],
            representation,
        )
        self.assertIn(
            json.dumps("إجمالياته وتقاريره", ensure_ascii=True)[1:-1],
            representation,
        )


if __name__ == "__main__":
    unittest.main()
