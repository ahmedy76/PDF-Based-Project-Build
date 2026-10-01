import reflex as rx

import logging
import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import bcrypt
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app import models as m
from app.states.bills import BillState
from app.components.bills import bills_page, reminder_section


class BillTests(unittest.TestCase):
    def setUp(self):
        self.state = BillState()
        self.engine = None
        url = os.getenv("REFLEX_DEV_DB_URL")
        if not url:
            self.skipTest("Managed test database unavailable")
        self.engine = create_engine(
            url.replace("postgresql://", "postgresql+psycopg://", 1)
        )
        self.connection = self.engine.connect()
        self.outer = self.connection.begin()
        self.db = Session(
            bind=self.connection, join_transaction_mode="create_savepoint"
        )
        self.addCleanup(self._cleanup)
        self.user, self.member, self.home, self.account = self._seed("one")
        self.other, self.other_member, self.other_home, self.other_account = (
            self._seed("two")
        )
        self.partner = m.User(
            display_name="شريك",
            email=f"partner-{uuid4().hex}@example.test",
            password_hash=bcrypt.hashpw(
                b"test-password-123", bcrypt.gensalt()
            ).decode(),
        )
        self.db.add(self.partner)
        self.db.flush()
        self.partner_member = m.HouseholdMembership(
            household_id=self.home.id, user_id=self.partner.id, role="partner"
        )
        self.db.add(self.partner_member)
        self.db.flush()

    def _cleanup(self):
        try:
            self.db.close()
            self.outer.rollback()
            self.connection.close()
        except Exception as e:
            logging.exception(f"Error: {e}")
            raise
        finally:
            self.engine.dispose()

    def _seed(self, label):
        user = m.User(
            display_name=label,
            email=f"bill-{label}-{uuid4().hex}@example.test",
            password_hash=bcrypt.hashpw(
                b"test-password-123", bcrypt.gensalt()
            ).decode(),
        )
        self.db.add(user)
        self.db.flush()
        home = m.Household(name=label, owner_user_id=user.id)
        self.db.add(home)
        self.db.flush()
        member = m.HouseholdMembership(
            household_id=home.id, user_id=user.id, role="owner"
        )
        self.db.add(member)
        self.db.flush()
        account = m.FinancialAccount(
            household_id=home.id,
            created_by_user_id=user.id,
            name="الحساب",
            currency="USD",
        )
        self.db.add(account)
        self.db.flush()
        return user, member, home, account

    def _data(self, account=None, due=None, **changes):
        data = {
            "title": "فاتورة المنزل",
            "amount": "30.1234",
            "account_id": str(account.id if account else self.account.id),
            "due_date": (due or date.today() + timedelta(days=2)).isoformat(),
            "remind_days": "3",
            "notes": "دفعة الشهر",
        }
        data.update(changes)
        return data

    def test_crud_validation_currency_and_no_ledger_posting(self):
        self.state._save(
            self.db, self.member, self.user.id, self._data(currency="SAR")
        )
        bill = self.db.scalar(
            select(m.Bill).where(m.Bill.household_id == self.home.id)
        )
        self.assertEqual(
            (bill.currency, bill.amount, bill.status),
            ("USD", Decimal("30.1234"), "unpaid"),
        )
        for bad in (
            "0",
            "NaN",
            "Infinity",
            "1.23456",
            "-1",
            "1000000000000000",
        ):
            with self.subTest(amount=bad), self.assertRaises(ValueError):
                self.state._save(
                    self.db, self.member, self.user.id, self._data(amount=bad)
                )
        for changes in (
            {"due_date": "2025-02-30"},
            {"remind_days": "366"},
            {"remind_days": "-1"},
            {"title": " "},
            {"account_id": str(self.other_account.id)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.state._save(
                    self.db, self.member, self.user.id, self._data(**changes)
                )
        other_account = m.FinancialAccount(
            household_id=self.home.id,
            created_by_user_id=self.user.id,
            name="حساب آخر",
            currency="EUR",
        )
        self.db.add(other_account)
        self.db.flush()
        self.state._save(
            self.db,
            self.member,
            self.user.id,
            self._data(account=other_account, title="متجددة"),
            str(bill.id),
        )
        self.assertEqual((bill.currency, bill.title), ("EUR", "متجددة"))
        self.state._set_paid(self.db, self.member, str(bill.id), True)
        self.assertEqual(bill.status, "paid")
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual(self.state.reminders, [])
        self.state._set_paid(self.db, self.member, str(bill.id), False)
        self.assertIsNone(bill.paid_on)
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual(len(self.state.reminders), 1)
        self.state._delete(self.db, self.member, str(bill.id))
        self.assertIsNone(self.db.get(m.Bill, bill.id))
        self.assertEqual(
            self.db.scalar(
                select(func.count())
                .select_from(m.Transaction)
                .where(m.Transaction.household_id == self.home.id)
            ),
            0,
        )

    def test_reminder_windows_dedup_fifo_payment_and_opt_out(self):
        due = date.today() + timedelta(days=2)
        self.state._save(
            self.db, self.member, self.user.id, self._data(due=due)
        )
        self.state._save(
            self.db,
            self.member,
            self.user.id,
            self._data(due=date.today() + timedelta(days=5)),
        )
        debt = m.Debt(
            household_id=self.home.id,
            created_by_user_id=self.user.id,
            direction="payable",
            title="قرض الأسرة",
            counterparty="البنك",
            principal=Decimal("20"),
            first_due_date=due,
            installment_count=2,
        )
        self.db.add(debt)
        self.db.flush()
        first = m.DebtInstallment(
            household_id=self.home.id,
            debt_id=debt.id,
            sequence_no=1,
            due_date=due,
            amount=Decimal("10"),
        )
        second = m.DebtInstallment(
            household_id=self.home.id,
            debt_id=debt.id,
            sequence_no=2,
            due_date=due + timedelta(days=30),
            amount=Decimal("10"),
        )
        self.db.add_all([first, second])
        self.db.flush()
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual(len(self.state.reminders), 2)
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual(len(self.state.reminders), 2)
        self.assertEqual(
            self.db.scalar(
                select(func.count())
                .select_from(m.ReminderDelivery)
                .where(m.ReminderDelivery.household_id == self.home.id)
            ),
            2,
        )
        payment = m.DebtPayment(
            household_id=self.home.id,
            debt_id=debt.id,
            created_by_user_id=self.user.id,
            amount=Decimal("4"),
            paid_on=date.today(),
        )
        self.db.add(payment)
        self.db.flush()
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual(
            next(r for r in self.state.reminders if r["kind"] == "installment")[
                "amount"
            ],
            "6.0000",
        )
        payment.amount = Decimal("10")
        self.db.flush()
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual([r["kind"] for r in self.state.reminders], ["bill"])
        payment.voided_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        self.db.flush()
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual(len(self.state.reminders), 2)
        self.db.add(
            m.NotificationPreference(
                user_id=self.user.id,
                kind="reminder",
                channel="in_app",
                enabled=False,
            )
        )
        self.db.flush()
        self.state._load(self.db, self.member, self.user.id)
        self.assertEqual(self.state.reminders, [])

    def test_account_restriction_permission_and_tenant_isolation(self):
        self.state._save(self.db, self.member, self.user.id, self._data())
        bill = self.db.scalar(
            select(m.Bill).where(m.Bill.household_id == self.home.id)
        )
        self.state._load(self.db, self.partner_member, self.partner.id)
        self.assertEqual(len(self.state.bills), 1)
        self.db.add(
            m.HouseholdAccountRestriction(
                household_id=self.home.id,
                member_user_id=self.partner.id,
                account_id=self.account.id,
            )
        )
        self.db.flush()
        self.state._load(self.db, self.partner_member, self.partner.id)
        self.assertEqual((self.state.bills, self.state.reminders), ([], []))
        with self.assertRaises(ValueError):
            self.state._set_paid(
                self.db, self.partner_member, str(bill.id), True
            )
        self.partner_member.can_add_transactions = False
        self.db.flush()
        with self.assertRaises(ValueError):
            self.state._save(
                self.db, self.partner_member, self.partner.id, self._data()
            )
        self.state._load(self.db, self.other_member, self.other.id)
        self.assertEqual((self.state.bills, self.state.reminders), ([], []))
        with self.assertRaises(ValueError):
            self.state._delete(self.db, self.other_member, str(bill.id))

    def test_page_components(self):
        self.assertIsNotNone(bills_page())
        self.assertIsNotNone(reminder_section())


if __name__ == "__main__":
    unittest.main()
