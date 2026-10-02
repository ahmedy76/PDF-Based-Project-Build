import reflex as rx

import bcrypt
import logging
import os
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4, uuid5

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import models as m
from app.states.csv_transfer import import_rows, transfer_rows
from app.states.ledger import LedgerState


class CsvIntegrityDatabaseTests(unittest.TestCase):
    def test_cross_household_import_and_rollback(self):
        url = os.getenv("REFLEX_DEV_DB_URL")
        if not url:
            self.skipTest("Isolated development database unavailable")
        engine = create_engine(
            url.replace("postgresql://", "postgresql+psycopg://", 1)
        )
        try:
            with engine.connect() as connection:
                outer = connection.begin()
                try:
                    with Session(
                        bind=connection,
                        join_transaction_mode="create_savepoint",
                    ) as db:
                        target_id = self.exercise(db)
                finally:
                    outer.rollback()
            with Session(engine) as check:
                self.assertEqual(
                    check.scalar(
                        select(func.count())
                        .select_from(m.Household)
                        .where(m.Household.id == target_id)
                    ),
                    0,
                )
        except Exception as e:
            logging.exception(f"Error: {e}")
            raise
        finally:
            engine.dispose()

    def exercise(self, db: Session):
        suffix = uuid4().hex
        user = m.User(
            display_name="CSV integration",
            email=f"csv-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                b"csv-integrity-test-only", bcrypt.gensalt()
            ).decode(),
        )
        partner = m.User(
            display_name="CSV partner",
            email=f"csv-partner-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                b"csv-partner-test-only", bcrypt.gensalt()
            ).decode(),
        )
        db.add_all([user, partner])
        db.flush()
        source = m.Household(name="source", owner_user_id=user.id)
        target = m.Household(name="target", owner_user_id=user.id)
        db.add_all([source, target])
        db.flush()
        for household in (source, target):
            db.add(
                m.HouseholdMembership(
                    household_id=household.id, user_id=user.id, role="owner"
                )
            )
        db.add(
            m.HouseholdMembership(
                household_id=target.id, user_id=partner.id, role="partner"
            )
        )
        db.flush()
        original_account = m.FinancialAccount(
            household_id=source.id,
            created_by_user_id=user.id,
            name="wallet",
            currency="SAR",
            opening_balance=Decimal("10"),
            opening_date=date(2025, 1, 1),
        )
        original_category = m.Category(
            household_id=source.id, name="food", kind="expense"
        )
        original_debt = m.Debt(
            household_id=source.id,
            created_by_user_id=user.id,
            title="loan",
            counterparty="bank",
            direction="payable",
            principal=Decimal("100"),
            first_due_date=date(2025, 1, 10),
            installment_count=2,
        )
        db.add_all([original_account, original_category, original_debt])
        db.flush()
        original_tx = m.Transaction(
            household_id=source.id,
            created_by_user_id=user.id,
            account_id=original_account.id,
            category_id=original_category.id,
            kind="expense",
            amount=Decimal("3"),
            transaction_date=date(2025, 1, 2),
            description="food",
        )
        original_bill = m.Bill(
            household_id=source.id,
            created_by_user_id=user.id,
            account_id=original_account.id,
            title="power",
            amount=Decimal("4"),
            currency="SAR",
            due_date=date(2025, 1, 10),
            status="unpaid",
            remind_days=3,
        )
        original_payment = m.DebtPayment(
            household_id=source.id,
            debt_id=original_debt.id,
            created_by_user_id=user.id,
            amount=Decimal("25"),
            paid_on=date(2025, 1, 11),
        )
        db.add_all([original_tx, original_bill, original_payment])
        db.flush()
        source_member = SimpleNamespace(
            household_id=source.id, user_id=user.id, role="owner"
        )
        target_member = SimpleNamespace(
            household_id=target.id, user_id=user.id, role="owner"
        )
        ledger = LedgerState()
        for kind in (
            "accounts",
            "categories",
            "transactions",
            "bills",
            "debts",
            "debt_payments",
        ):
            exported = transfer_rows(db, source_member, kind)
            rows = [
                dict(row, _line=str(index + 2))
                for index, row in enumerate(exported)
            ]
            self.assertEqual(
                import_rows(db, user, target_member, kind, rows, ledger),
                (len(rows), 0),
                kind,
            )
            self.assertEqual(
                import_rows(db, user, target_member, kind, rows, ledger),
                (0, len(rows)),
                kind,
            )
        for model, original in (
            (m.FinancialAccount, original_account),
            (m.Category, original_category),
            (m.Transaction, original_tx),
            (m.Bill, original_bill),
            (m.Debt, original_debt),
            (m.DebtPayment, original_payment),
        ):
            mapped = db.scalar(
                select(model).where(model.household_id == target.id)
            )
            self.assertEqual(mapped.id, uuid5(target.id, original.id.hex))
            self.assertNotEqual(mapped.id, original.id)
            self.assertEqual(original.household_id, source.id)
        mapped_account = db.scalar(
            select(m.FinancialAccount).where(
                m.FinancialAccount.household_id == target.id
            )
        )
        mapped_tx = db.scalar(
            select(m.Transaction).where(m.Transaction.household_id == target.id)
        )
        mapped_bill = db.scalar(
            select(m.Bill).where(m.Bill.household_id == target.id)
        )
        mapped_payment = db.scalar(
            select(m.DebtPayment).where(m.DebtPayment.household_id == target.id)
        )
        self.assertEqual(mapped_tx.account_id, mapped_bill.account_id)
        self.assertEqual(
            mapped_payment.debt_id, uuid5(target.id, original_debt.id.hex)
        )
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.TransactionAuditEvent)
                .where(m.TransactionAuditEvent.household_id == target.id)
            ),
            1,
        )
        db.add(
            m.HouseholdAccountRestriction(
                household_id=target.id,
                member_user_id=partner.id,
                account_id=mapped_account.id,
            )
        )
        db.flush()
        partner_member = SimpleNamespace(
            household_id=target.id,
            user_id=partner.id,
            role="partner",
            can_add_transactions=True,
        )
        hidden = dict(
            transfer_rows(db, source_member, "accounts")[0],
            _line="2",
            source_id="",
        )
        with self.assertRaises(ValueError) as error:
            import_rows(
                db, partner, partner_member, "accounts", [hidden], ledger
            )
        self.assertNotIn("محجوب", str(error.exception))
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.FinancialAccount)
                .where(m.FinancialAccount.household_id == target.id)
            ),
            1,
        )
        tx_row = dict(
            transfer_rows(db, source_member, "transactions")[0], _line="2"
        )
        forged = dict(tx_row, source_id=str(mapped_tx.id), amount="5")
        with self.assertRaisesRegex(ValueError, "الصف 2"):
            import_rows(
                db, user, target_member, "transactions", [forged], ledger
            )
        distinct = dict(tx_row, source_id=str(uuid4()), _line="2")
        invalid = dict(tx_row, source_id=str(uuid4()), amount="-4", _line="3")
        with self.assertRaisesRegex(ValueError, "الصف 3"):
            import_rows(
                db,
                user,
                target_member,
                "transactions",
                [distinct, invalid],
                ledger,
            )
        db.rollback()
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.Transaction)
                .where(m.Transaction.household_id == target.id)
            ),
            1,
        )
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.TransactionAuditEvent)
                .where(m.TransactionAuditEvent.household_id == target.id)
            ),
            1,
        )
        return target.id


if __name__ == "__main__":
    unittest.main()
