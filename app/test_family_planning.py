import reflex as rx

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy import func, select
from app import models as m
from app.components.family_planning import family_planning_page
from app.locales.catalog import catalog, translation
from app.states.family_planning import (
    FamilyPlanningState,
    calculate_split,
    positive_money,
)
from app.test_bills import BillTests


class PlanningCalculationTests(unittest.TestCase):
    def test_exact_remainder_and_income_proportions(self):
        for amount in ("0.0001", "0.01", "30.1234", "99999999999999.9999"):
            for mode in ("equal", "income"):
                p1, p2, a1, a2 = calculate_split(
                    Decimal(amount), mode, [Decimal("2000"), Decimal("4000")]
                )
                self.assertEqual(p1 + p2, Decimal(100))
                self.assertEqual(a1 + a2, Decimal(amount))
                self.assertGreaterEqual(a1, 0)
                self.assertGreaterEqual(a2, 0)
        self.assertEqual(
            calculate_split(
                Decimal("90"), "income", [Decimal("1000"), Decimal("2000")]
            ),
            (
                Decimal("33.333333"),
                Decimal("66.666667"),
                Decimal("30.0000"),
                Decimal("60.0000"),
            ),
        )

    def test_positive_finite_bounded_income(self):
        for raw in (
            "",
            "NaN",
            "Infinity",
            "-Infinity",
            "-1",
            "0",
            "1000000000000000",
            "1.23456",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                positive_money(raw)
        self.assertEqual(positive_money("1234.5678"), Decimal("1234.5678"))
        for mode, values in [
            ("unknown", [Decimal(1), Decimal(1)]),
            ("income", [Decimal(0), Decimal(1)]),
            ("income", [Decimal(1)]),
        ]:
            with self.assertRaises(ValueError):
                calculate_split(Decimal(10), mode, values)

    def test_task_authorization_matrix(self):
        state = FamilyPlanningState()
        creator, assignee = uuid4(), uuid4()
        task = SimpleNamespace(
            created_by_user_id=creator, assignee_user_id=assignee
        )
        for role, uid, edit, status in [
            ("owner", uuid4(), True, True),
            ("partner", creator, True, True),
            ("partner", assignee, False, True),
            ("partner", uuid4(), False, False),
        ]:
            member = SimpleNamespace(role=role, user_id=uid)
            for status_only, allowed in [(False, edit), (True, status)]:
                if allowed:
                    state._authorize_task(member, task, status_only)
                else:
                    with self.assertRaises(ValueError):
                        state._authorize_task(member, task, status_only)

    def test_owner_only_split_before_any_lookup(self):
        state, db = FamilyPlanningState(), Mock()
        with self.assertRaises(ValueError):
            state._configure_split(db, SimpleNamespace(role="partner"), {})
        db.scalar.assert_not_called()

    def test_consent_schema_default_and_translated_page(self):
        column = m.HouseholdMembership.__table__.c.can_view_commitments
        self.assertFalse(column.default.arg)
        self.assertEqual(str(column.server_default.arg), "false")
        ar, en = catalog("ar"), catalog("en")
        self.assertEqual(ar.keys(), en.keys())
        for key in (
            "nav.family_planning",
            "planning.disclosure_help",
            "planning.confirm",
        ):
            self.assertIn(key, ar)
            self.assertNotEqual(translation(key, "ar"), translation(key, "en"))
        page = family_planning_page()
        self.assertIsInstance(page, rx.Component)
        rendered = str(page)
        for name in (
            "title",
            "details",
            "currency",
            "account_id",
            "assignee_user_id",
            "participant_1",
            "participant_2",
            "confirm",
        ):
            self.assertIn(f'name:"{name}"', rendered)
        self.assertIn("/family-planning", rendered)
        self.assertIn("alertdialog", rendered)


class PlanningDatabaseTests(unittest.TestCase):
    _seed = BillTests._seed
    _cleanup = BillTests._cleanup

    def setUp(self):
        BillTests.setUp(self)
        self.state = FamilyPlanningState()
        self.bill = m.Bill(
            household_id=self.home.id,
            account_id=self.account.id,
            created_by_user_id=self.user.id,
            title="Utilities",
            amount=Decimal("30.1234"),
            currency="USD",
            due_date=date.today(),
        )
        self.db.add(self.bill)
        self.db.flush()

    def task_data(self, **changes):
        data = {
            "title": "Arrange home repairs",
            "details": "Compare estimates before agreeing",
            "currency": "USD",
            "account_id": str(self.account.id),
            "assignee_user_id": str(self.partner.id),
            "due_date": date.today().isoformat(),
        }
        data.update(changes)
        return data

    def split_data(self, **changes):
        data = {
            "bill_id": str(self.bill.id),
            "currency": "USD",
            "mode": "income",
            "participant_1": str(self.user.id),
            "participant_2": str(self.partner.id),
            "income_1": "2500",
            "income_2": "5000",
            "confirm": "on",
        }
        data.update(changes)
        return data

    def task(self):
        return self.db.scalar(
            select(m.HouseholdTask).where(
                m.HouseholdTask.household_id == self.home.id
            )
        )

    def test_task_crud_status_and_creator_assignee_boundaries(self):
        self.state._save_task(self.db, self.member, self.task_data(), "")
        task = self.task()
        self.assertEqual(task.currency, "USD")
        with self.assertRaises(ValueError):
            self.state._save_task(
                self.db,
                self.partner_member,
                self.task_data(title="Unauthorized edit"),
                str(task.id),
            )
        with self.assertRaises(ValueError):
            self.state._change_task(
                self.db, self.partner_member, str(task.id), "delete"
            )
        self.state._change_task(
            self.db, self.partner_member, str(task.id), "complete"
        )
        self.assertEqual(task.status, "complete")
        self.state._change_task(
            self.db, self.partner_member, str(task.id), "pending"
        )
        self.state._save_task(
            self.db, self.member, self.task_data(title="Updated"), str(task.id)
        )
        self.assertEqual(task.title, "Updated")
        self.state._change_task(self.db, self.member, str(task.id), "delete")
        self.assertIsNone(self.task())
        self.state._save_task(
            self.db,
            self.partner_member,
            self.task_data(assignee_user_id=""),
            "",
        )
        self.state._save_task(
            self.db,
            self.partner_member,
            self.task_data(title="Creator update", assignee_user_id=""),
            str(self.task().id),
        )
        self.assertEqual(self.task().title, "Creator update")

    def test_task_currency_tenant_validation_and_changed_account_restrictions(
        self,
    ):
        for changes in (
            {"title": " "},
            {"currency": "US"},
            {"currency": "EUR"},
            {"details": "x" * 4001},
            {"due_date": "2025-02-30"},
            {"account_id": str(self.other_account.id)},
            {"assignee_user_id": str(self.other.id)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.state._save_task(
                    self.db, self.member, self.task_data(**changes), ""
                )
        self.state._save_task(self.db, self.member, self.task_data(), "")
        task = self.task()
        self.state._read(self.db, self.partner_member)
        self.assertEqual(len(self.state.tasks), 1)
        self.db.add(
            m.HouseholdAccountRestriction(
                household_id=self.home.id,
                member_user_id=self.partner.id,
                account_id=self.account.id,
            )
        )
        self.db.flush()
        self.state._read(self.db, self.partner_member)
        self.assertEqual(self.state.tasks, [])
        with self.assertRaises(ValueError):
            self.state._change_task(
                self.db, self.partner_member, str(task.id), "complete"
            )
        with self.assertRaises(ValueError):
            self.state._save_task(
                self.db, self.member, self.task_data(), str(task.id)
            )
        self.state._read(self.db, self.other_member)
        self.assertEqual(self.state.tasks, [])
        with self.assertRaises(ValueError):
            self.state._task(self.db, self.other_member, str(task.id))
        self.state._save_task(
            self.db,
            self.member,
            self.task_data(
                title="Unlinked",
                account_id="",
                assignee_user_id="",
                currency="EUR",
            ),
            "",
        )
        self.state.currency_filter = "EUR"
        self.state._read(self.db, self.partner_member)
        self.assertEqual([r["currency"] for r in self.state.tasks], ["EUR"])
        self.state.status_filter = "complete"
        self.state._read(self.db, self.partner_member)
        self.assertEqual(self.state.tasks, [])

    def test_split_consent_snapshot_exact_sum_no_posting_and_revoke(self):
        self.assertFalse(self.partner_member.can_view_commitments)
        with self.assertRaises(ValueError):
            self.state._configure_split(self.db, self.member, self.split_data())
        self.partner_member.can_view_commitments = True
        self.db.flush()
        self.state._configure_split(self.db, self.member, self.split_data())
        rule = self.db.scalar(
            select(m.BillSplitRule).where(
                m.BillSplitRule.bill_id == self.bill.id
            )
        )
        shares = self.db.scalars(
            select(m.BillSplitShare).where(m.BillSplitShare.rule_id == rule.id)
        ).all()
        self.assertEqual(sum(s.share_amount for s in shares), self.bill.amount)
        self.assertEqual(sum(s.percentage for s in shares), 100)
        self.assertEqual(
            {s.declared_income for s in shares},
            {Decimal("2500"), Decimal("5000")},
        )
        self.state._read(self.db, self.partner_member)
        self.assertEqual(len(self.state.bills[0]["shares"]), 2)
        self.partner_member.can_view_commitments = False
        self.db.flush()
        self.state._read(self.db, self.partner_member)
        self.assertEqual(self.state.bills[0]["shares"], [])
        self.assertEqual(self.state.bills[0]["mode"], "")
        self.state._read(self.db, self.member)
        self.assertEqual(len(self.state.bills[0]["shares"]), 2)
        self.bill.amount = Decimal("31")
        self.db.flush()
        self.state._read(self.db, self.member)
        self.assertTrue(self.state.bills[0]["stale"])
        self.assertEqual(self.bill.status, "unpaid")
        self.assertEqual(
            self.db.scalar(
                select(func.count())
                .select_from(m.Transaction)
                .where(m.Transaction.household_id == self.home.id)
            ),
            0,
        )
        self.assertEqual(self.account.opening_balance, 0)
        self.state._configure_split(
            self.db, self.member, {"bill_id": str(self.bill.id)}, True
        )
        self.assertIsNone(
            self.db.scalar(
                select(m.BillSplitRule).where(m.BillSplitRule.id == rule.id)
            )
        )
        self.assertEqual(
            self.db.scalar(
                select(func.count())
                .select_from(m.BillSplitShare)
                .where(m.BillSplitShare.rule_id == rule.id)
            ),
            0,
        )

    def test_split_validation_account_household_currency_and_owner_only(self):
        self.partner_member.can_view_commitments = True
        self.db.flush()
        for changes in (
            {"participant_2": str(self.user.id)},
            {"participant_2": str(self.other.id)},
            {"currency": "EUR"},
            {"confirm": ""},
            {"income_1": "0"},
            {"income_2": "NaN"},
            {"mode": "unsupported"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.state._configure_split(
                    self.db, self.member, self.split_data(**changes)
                )
        for member in (self.partner_member, self.other_member):
            with self.assertRaises(ValueError):
                self.state._configure_split(self.db, member, self.split_data())
        self.state._configure_split(
            self.db,
            self.member,
            self.split_data(mode="equal", income_1="", income_2=""),
        )
        rule = self.db.scalar(
            select(m.BillSplitRule).where(
                m.BillSplitRule.bill_id == self.bill.id
            )
        )
        shares = self.db.scalars(
            select(m.BillSplitShare).where(m.BillSplitShare.rule_id == rule.id)
        ).all()
        self.assertTrue(all(s.declared_income is None for s in shares))
        self.db.add(
            m.HouseholdAccountRestriction(
                household_id=self.home.id,
                member_user_id=self.partner.id,
                account_id=self.account.id,
            )
        )
        self.db.flush()
        self.state._read(self.db, self.partner_member)
        self.assertEqual(self.state.bills, [])
        with self.assertRaises(ValueError):
            self.state._configure_split(self.db, self.member, self.split_data())
        self.state._read(self.db, self.other_member)
        self.assertEqual(self.state.bills, [])


if __name__ == "__main__":
    unittest.main()
