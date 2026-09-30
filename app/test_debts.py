import reflex as rx

import logging
import os
import secrets
import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

import bcrypt
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import models as m
from app.components.screens import debt_dialog, debts
from app.states.debts import DebtState, money, parse_date, schedule


class DebtValidationTests(unittest.TestCase):
    def test_month_end_leap_year_and_exact_units(self):
        self.assertEqual(
            [
                d.isoformat()
                for d, _ in schedule(Decimal("1.0000"), date(2024, 1, 31), 4)
            ],
            ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"],
        )
        self.assertEqual(
            [
                d.isoformat()
                for d, _ in schedule(Decimal("1"), date(2023, 12, 31), 3)
            ],
            ["2023-12-31", "2024-01-31", "2024-02-29"],
        )
        amounts = [
            amount
            for _, amount in schedule(money("0.0007"), date(2000, 1, 1), 3)
        ]
        self.assertEqual(
            amounts, [Decimal("0.0003"), Decimal("0.0002"), Decimal("0.0002")]
        )
        self.assertEqual(sum(amounts), Decimal("0.0007"))
        self.assertEqual(
            schedule(money("1.0000"), date(9999, 12, 31), 1),
            [(date(9999, 12, 31), Decimal("1"))],
        )
        for amount in (
            "0",
            "-1",
            "NaN",
            "1.12345",
            "1000000000000000",
            "Infinity",
        ):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                money(amount)
        for first, count, amount in (
            (date(9999, 12, 31), 2, Decimal("1")),
            (date(2024, 1, 1), 2, Decimal("0.0001")),
        ):
            with self.assertRaises(ValueError):
                schedule(amount, first, count)
        with self.assertRaises(ValueError):
            parse_date("2024-02-30")
        with self.assertRaises(ValueError):
            parse_date("9999-12-31", past_allowed=False)

    def test_dialog_events_and_rendering(self):
        state = DebtState()
        DebtState.open_debt.fn(state, "")
        self.assertEqual(state.editor, "debt")
        state.debts = [
            {
                "id": str(uuid4()),
                "title": "قرض",
                "direction": "payable",
                "counterparty": "طرف",
                "note": "",
                "principal": "10.0000",
                "principal_raw": "10.0000",
                "first_due_date": "2024-01-01",
                "installment_count": "2",
                "paid": "0.0000",
                "remaining": "10.0000",
                "overdue": "0.0000",
                "next_due": "2024-01-01",
                "status": "قادم",
                "has_payments": True,
                "installments": [],
                "history": [
                    {
                        "id": str(uuid4()),
                        "amount": "1.0000",
                        "date": "2024-01-01",
                        "note": "",
                        "voided": False,
                    }
                ],
            }
        ]
        row = state.debts[0]
        DebtState.open_debt.fn(state, row["id"])
        self.assertEqual(state.draft["title"], "قرض")
        DebtState.open_payment.fn(state, row["id"])
        self.assertEqual(state.editor, "payment")
        DebtState.ask_void.fn(state, row["id"], row["history"][0]["id"])
        self.assertEqual(
            (state.editor, state.void_id), ("void", row["history"][0]["id"])
        )
        DebtState.close_editor.fn(state)
        self.assertEqual((state.editor, state.void_id), ("", ""))
        DebtState.ask_void.fn(state, row["id"], str(uuid4()))
        self.assertNotEqual(state.error, "")
        self.assertIsNotNone(debt_dialog())
        self.assertIsNotNone(debts())


class ManagedDebtTests(unittest.TestCase):
    def _seed(self, db: Session, suffix: str):
        user = m.User(
            display_name="مختبر الديون",
            email=f"debts-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                secrets.token_bytes(24), bcrypt.gensalt()
            ).decode(),
        )
        db.add(user)
        db.flush()
        household = m.Household(name="أسرة الديون", owner_user_id=user.id)
        db.add(household)
        db.flush()
        db.add(
            m.HouseholdMembership(
                household_id=household.id, user_id=user.id, role="owner"
            )
        )
        db.flush()
        return user, household

    def _exercise(self, db: Session):
        suffix = uuid4().hex
        user, home = self._seed(db, suffix)
        outsider, other = self._seed(db, f"other-{suffix}")
        state = DebtState()
        data = {
            "title": "دفعة قديمة",
            "direction": "payable",
            "counterparty": "شركة",
            "principal": "10.0001",
            "first_due_date": "2020-01-31",
            "installment_count": "3",
            "note": "سجل قديم",
        }
        debt = state._save(db, home.id, user.id, data)
        db.flush()
        self.assertEqual(
            [
                i.due_date.isoformat()
                for i in db.scalars(
                    select(m.DebtInstallment)
                    .where(m.DebtInstallment.debt_id == debt.id)
                    .order_by(m.DebtInstallment.sequence_no)
                )
            ],
            ["2020-01-31", "2020-02-29", "2020-03-31"],
        )
        self.assertEqual(
            db.scalar(
                select(func.sum(m.DebtInstallment.amount)).where(
                    m.DebtInstallment.debt_id == debt.id
                )
            ),
            Decimal("10.0001"),
        )
        with self.assertRaisesRegex(ValueError, "أرشفة"):
            state._archive(db, home.id, user.id, str(debt.id), True)
        with self.assertRaisesRegex(PermissionError, "عضوية"):
            state._payment(
                db,
                other.id,
                user.id,
                str(debt.id),
                {"amount": "1", "paid_on": "2020-01-01"},
            )
        with self.assertRaisesRegex(ValueError, "غير متاح"):
            state._payment(
                db,
                other.id,
                outsider.id,
                str(debt.id),
                {"amount": "1", "paid_on": "2020-01-01"},
            )
        entry = state._payment(
            db,
            home.id,
            user.id,
            str(debt.id),
            {"amount": "5.0000", "paid_on": "2020-01-01"},
        )
        state._load(db, home.id)
        row = state.debts[0]
        self.assertEqual(
            (row["paid"], row["remaining"], row["overdue"]),
            ("5.0000", "5.0001", "5.0001"),
        )
        self.assertEqual(
            [line["paid"] for line in row["installments"]],
            ["3.3334", "1.6666", "0.0000"],
        )
        self.assertEqual(row["installments"][1]["status"], "متأخر")
        with self.assertRaisesRegex(ValueError, "تتجاوز"):
            state._payment(
                db,
                home.id,
                user.id,
                str(debt.id),
                {"amount": "5.0002", "paid_on": date.today().isoformat()},
            )
        with self.assertRaisesRegex(ValueError, "إعادة تخطيط"):
            state._save(
                db, home.id, user.id, dict(data, principal="11"), str(debt.id)
            )
        state._save(
            db,
            home.id,
            user.id,
            dict(data, title="اسم جديد", note="جديد"),
            str(debt.id),
        )
        self.assertEqual(debt.title, "اسم جديد")
        with self.assertRaisesRegex(ValueError, "غير متاح"):
            state._void(db, other.id, outsider.id, str(debt.id), str(entry.id))
        state._void(db, home.id, user.id, str(debt.id), str(entry.id))
        with self.assertRaisesRegex(ValueError, "ملغاة"):
            state._void(db, home.id, user.id, str(debt.id), str(entry.id))
        state._load(db, home.id)
        self.assertEqual(
            (state.debts[0]["paid"], state.debts[0]["remaining"]),
            ("0.0000", "10.0001"),
        )
        self.assertTrue(state.debts[0]["history"][0]["voided"])
        with self.assertRaisesRegex(ValueError, "أي دفعة"):
            state._save(
                db,
                home.id,
                user.id,
                dict(data, installment_count="2"),
                str(debt.id),
            )
        state._payment(
            db,
            home.id,
            user.id,
            str(debt.id),
            {"amount": "10.0001", "paid_on": date.today().isoformat()},
        )
        state._archive(db, home.id, user.id, str(debt.id), True)
        state._load(db, home.id)
        self.assertEqual(len(state.archived_debts[0]["history"]), 2)
        with self.assertRaisesRegex(ValueError, "استعد"):
            state._payment(
                db,
                home.id,
                user.id,
                str(debt.id),
                {"amount": "1", "paid_on": date.today().isoformat()},
            )
        state._archive(db, home.id, user.id, str(debt.id), False)
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.Transaction)
                .where(m.Transaction.household_id == home.id)
            ),
            0,
        )
        db.commit()

    def test_rollback_only_managed_postgres(self):
        dev_url = os.getenv("REFLEX_DEV_DB_URL")
        if not dev_url:
            self.skipTest("REFLEX_DEV_DB_URL is unavailable")
        engine = create_engine(
            dev_url.replace("postgresql://", "postgresql+psycopg://", 1)
        )
        try:
            with engine.connect() as connection:
                outer = connection.begin()
                try:
                    with Session(
                        bind=connection,
                        join_transaction_mode="create_savepoint",
                    ) as db:
                        self._exercise(db)
                finally:
                    outer.rollback()
        except Exception as e:
            logging.exception(f"Error: {e}")
            raise
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
