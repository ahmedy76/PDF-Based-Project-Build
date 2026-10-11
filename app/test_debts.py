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
                "account_id": str(uuid4()),
                "account": "حساب",
                "currency": "USD",
                "linked": True,
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
        account = m.FinancialAccount(
            household_id=home.id,
            created_by_user_id=user.id,
            name="حساب الديون",
            currency="USD",
        )
        db.add(account)
        db.flush()
        data = {
            "account_id": str(account.id),
            "title": "دفعة قديمة",
            "direction": "payable",
            "counterparty": "شركة",
            "principal": "10.0001",
            "first_due_date": "2020-01-31",
            "installment_count": "3",
            "note": "سجل قديم",
        }
        with self.assertRaises(ValueError):
            state._save(
                db,
                home.id,
                user.id,
                {k: v for k, v in data.items() if k != "account_id"},
            )
        debt = state._save(db, home.id, user.id, dict(data, currency="SAR"))
        self.assertEqual((debt.account_id, debt.currency), (account.id, "USD"))
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
        state._load(db, home.id, user.id)
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
        state._load(db, home.id, user.id)
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
        state._load(db, home.id, user.id)
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
        self._attribution_boundaries(
            db, state, user, home, outsider, other, account, data, debt, entry
        )
        db.commit()

    def _attribution_boundaries(
        self, db, state, user, home, outsider, other, account, data, debt, entry
    ):
        from app.states.csv_transfer import (
            HEADERS,
            SAMPLES,
            import_rows,
            transfer_rows,
            parse_csv,
        )
        from app.states.ledger import LedgerState

        partner = m.User(
            display_name="شريك",
            email=f"debt-partner-{uuid4().hex}@example.test",
            password_hash=user.password_hash,
        )
        db.add(partner)
        db.flush()
        member = m.HouseholdMembership(
            household_id=home.id, user_id=partner.id, role="partner"
        )
        euro = m.FinancialAccount(
            household_id=home.id,
            created_by_user_id=user.id,
            name="حساب يورو",
            currency="EUR",
        )
        db.add_all([member, euro])
        db.flush()
        euro_debt = state._save(
            db,
            home.id,
            user.id,
            dict(
                data, account_id=str(euro.id), title="دين يورو", principal="40"
            ),
        )
        legacy = m.Debt(
            household_id=home.id,
            created_by_user_id=user.id,
            title="قديم مجهول",
            counterparty="طرف",
            direction="payable",
            principal=Decimal("20"),
            first_due_date=date(2020, 1, 1),
            installment_count=1,
        )
        db.add(legacy)
        db.flush()
        old_installment = m.DebtInstallment(
            household_id=home.id,
            debt_id=legacy.id,
            sequence_no=1,
            due_date=date(2020, 1, 1),
            amount=Decimal("20"),
        )
        old_payment = m.DebtPayment(
            household_id=home.id,
            debt_id=legacy.id,
            created_by_user_id=user.id,
            amount=Decimal("3"),
            paid_on=date(2020, 1, 1),
            note="تاريخي",
        )
        db.add_all([old_installment, old_payment])
        db.flush()
        original = (
            old_installment.id,
            old_installment.amount,
            old_payment.id,
            old_payment.amount,
            old_payment.paid_on,
            old_payment.note,
        )
        state._load(db, home.id, user.id)
        self.assertEqual(
            {r["currency"] for r in state.currency_totals}, {"USD", "EUR"}
        )
        self.assertEqual(state.legacy_count, 1)
        self.assertIsNone(legacy.account_id)
        self.assertIsNone(legacy.currency)
        state._load(db, home.id, partner.id)
        self.assertNotIn(str(legacy.id), {r["id"] for r in state.debts})
        with self.assertRaises(ValueError):
            state._assign(
                db,
                home.id,
                partner.id,
                str(legacy.id),
                {"account_id": str(account.id), "confirm_history": True},
            )
        with self.assertRaises(ValueError):
            state._assign(
                db,
                home.id,
                user.id,
                str(legacy.id),
                {"account_id": str(account.id)},
            )
        self.assertIsNone(legacy.currency)
        with self.assertRaises(ValueError):
            state._payment(
                db,
                home.id,
                user.id,
                str(legacy.id),
                {"amount": "1", "paid_on": "2020-01-01"},
            )
        with self.assertRaises(ValueError):
            state._assign(
                db,
                other.id,
                outsider.id,
                str(legacy.id),
                {"account_id": str(account.id), "confirm_history": True},
            )
        state._assign(
            db,
            home.id,
            user.id,
            str(legacy.id),
            {
                "account_id": str(account.id),
                "currency": "EUR",
                "confirm_history": True,
            },
        )
        self.assertEqual(
            (legacy.account_id, legacy.currency), (account.id, "USD")
        )
        self.assertEqual(
            original,
            (
                old_installment.id,
                old_installment.amount,
                old_payment.id,
                old_payment.amount,
                old_payment.paid_on,
                old_payment.note,
            ),
        )
        for target in (debt, legacy):
            with self.assertRaises(ValueError):
                state._assign(
                    db,
                    home.id,
                    user.id,
                    str(target.id),
                    {"account_id": str(euro.id), "confirm_history": True},
                )
        with self.assertRaises(ValueError):
            state._save(
                db,
                home.id,
                user.id,
                dict(data, account_id=str(euro.id)),
                str(debt.id),
            )
        with self.assertRaises(ValueError):
            state._save(
                db, home.id, user.id, dict(data, currency="EUR"), str(debt.id)
            )
        db.add(
            m.HouseholdAccountRestriction(
                household_id=home.id,
                member_user_id=partner.id,
                account_id=account.id,
            )
        )
        db.flush()
        state._load(db, home.id, partner.id)
        self.assertEqual([r["id"] for r in state.debts], [str(euro_debt.id)])
        self.assertEqual(
            state.currency_totals,
            [{"currency": "EUR", "payable": "40.0000", "receivable": "0.0000"}],
        )
        for mutate in (
            lambda: state._save(db, home.id, partner.id, data, str(debt.id)),
            lambda: state._payment(
                db,
                home.id,
                partner.id,
                str(debt.id),
                {"amount": "1", "paid_on": "2020-01-01"},
            ),
            lambda: state._void(
                db, home.id, partner.id, str(debt.id), str(entry.id)
            ),
            lambda: state._archive(db, home.id, partner.id, str(debt.id), True),
            lambda: state._save(db, home.id, partner.id, data),
        ):
            with self.assertRaises(ValueError):
                mutate()
        for kind in ("debts", "debt_installments", "debt_payments"):
            rows = transfer_rows(db, member, kind)
            self.assertTrue(
                all(
                    r["account_source_id"] == str(euro.id)
                    and r["currency"] == "EUR"
                    for r in rows
                )
            )
        owner_member = state._guard(db, home.id, user.id)
        exports = transfer_rows(db, owner_member, "debts")
        hidden_row = next(r for r in exports if r["source_id"] == str(debt.id))
        with self.assertRaises(ValueError):
            import_rows(
                db,
                partner,
                member,
                "debts",
                [dict(hidden_row, _line="2")],
                LedgerState(),
            )
        for kind in ("debt_installments", "debt_payments"):
            rows = transfer_rows(db, owner_member, kind)
            target_row = next(
                r for r in rows if r["debt_source_id"] == str(legacy.id)
            )
            with self.assertRaises(ValueError):
                import_rows(
                    db,
                    partner,
                    member,
                    kind,
                    [dict(target_row, _line="2")],
                    LedgerState(),
                )
        row = dict(zip(HEADERS["debts"], SAMPLES["debts"]))
        row.update(
            account_name=euro.name,
            account_source_id=str(euro.id),
            currency="EUR",
            _line="2",
            title="CSV EUR",
        )
        member.can_add_transactions = False
        db.flush()
        with self.assertRaises(ValueError):
            state._save(
                db, home.id, partner.id, dict(data, account_id=str(euro.id))
            )
        member.can_add_transactions = True
        euro.is_archived = True
        db.flush()
        with self.assertRaises(ValueError):
            state._save(
                db, home.id, user.id, dict(data, account_id=str(euro.id))
            )
        with self.assertRaises(ValueError):
            import_rows(db, user, owner_member, "debts", [row], LedgerState())
        euro.is_archived = False
        db.flush()
        self.assertEqual(
            import_rows(db, user, owner_member, "debts", [row], LedgerState()),
            (1, 0),
        )
        self.assertEqual(
            import_rows(db, user, owner_member, "debts", [row], LedgerState()),
            (0, 1),
        )
        unassigned = m.Debt(
            household_id=home.id,
            created_by_user_id=user.id,
            title="غير مسند",
            counterparty="قديم",
            direction="receivable",
            principal=Decimal("2"),
            first_due_date=date(2020, 1, 1),
            installment_count=1,
        )
        db.add(unassigned)
        db.flush()
        owner_rows = transfer_rows(db, owner_member, "debts")
        unknown = next(
            r for r in owner_rows if r["source_id"] == str(unassigned.id)
        )
        self.assertEqual(
            (
                unknown["account_name"],
                unknown["currency"],
                unknown["account_source_id"],
            ),
            ("", "", ""),
        )
        with self.assertRaises(ValueError):
            import_rows(
                db,
                user,
                owner_member,
                "debts",
                [dict(unknown, _line="2")],
                LedgerState(),
            )
        unknown.update(
            account_name=euro.name,
            account_source_id=str(euro.id),
            currency="EUR",
            _line="2",
        )
        with self.assertRaises(ValueError):
            import_rows(
                db, user, owner_member, "debts", [unknown], LedgerState()
            )
        self.assertIsNone(unassigned.currency)
        with self.assertRaisesRegex(ValueError, "القالب"):
            parse_csv(
                "debts",
                b"title,counterparty,direction,principal,first_due_date,installment_count,note,is_archived,source_id\nold,party,payable,1,2020-01-01,1,,false,",
            )
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.Transaction)
                .where(m.Transaction.household_id == home.id)
            ),
            0,
        )

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
