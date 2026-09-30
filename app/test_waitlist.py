import reflex as rx

import logging
import os
import unittest
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import Transaction, User, WaitlistLead
from app.states.waitlist import WaitlistState, normalize_contact
from app.components.screens import welcome


class WaitlistUnitTests(unittest.TestCase):
    def test_contact_validation(self):
        self.assertEqual(
            normalize_contact("  Hello@Example.COM  "),
            ("email", "hello@example.com"),
        )
        self.assertEqual(
            normalize_contact(" +966 55-123-4567 "), ("phone", "+966551234567")
        )
        for value in (
            "",
            "test@",
            "hello @example.com",
            "0551234567",
            "+0123",
            "+1 (555) 123",
            "+" + "1" * 16,
            "abc\n@example.com",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_contact(value)

    def test_local_selection_and_render(self):
        state = WaitlistState()
        state.stage = 2
        WaitlistState.toggle_problem.fn(state, "budget")
        self.assertEqual(state.selected_problems, ["budget"])
        WaitlistState.toggle_problem.fn(state, "budget")
        self.assertEqual(state.selected_problems, [])
        WaitlistState.toggle_problem.fn(state, "unknown")
        self.assertEqual(state.selected_problems, [])
        self.assertIsNotNone(welcome())


class ManagedWaitlistTests(unittest.TestCase):
    def _exercise(self, db: Session):
        suffix = uuid4().hex
        before_users = db.scalar(select(func.count()).select_from(User))
        before_transactions = db.scalar(
            select(func.count()).select_from(Transaction)
        )
        existing_reservations = db.scalar(
            select(func.count())
            .select_from(WaitlistLead)
            .where(WaitlistLead.founder_decision == "reserved")
        )
        test_limit = existing_reservations + 1
        state = WaitlistState()
        first_id, first_code = state._create(
            db, f" REF-{suffix}@Example.Test ", True
        )
        state.lead_id = first_id
        db.flush()
        self.assertEqual(
            db.get(WaitlistLead, state._lead(db).id).contact_value,
            f"ref-{suffix}@example.test",
        )
        with self.assertRaises(ValueError):
            state._create(db, f"ref-{suffix}@example.test", True)
        with self.assertRaises(ValueError):
            state._create(db, f"other-{suffix}@example.test", False)
        with self.assertRaises(ValueError):
            state._create(db, f"ref-{suffix}@example.test", True, first_code)
        phone = f"+9665{int(suffix[:10], 16) % 100000000:08d}"
        referred_id, _ = state._create(db, phone, True, first_code)
        self.assertNotEqual(referred_id, first_id)
        state.lead_id = referred_id
        self.assertEqual(str(state._lead(db).referred_by_id), first_id)
        state.lead_id = referred_id
        self.assertEqual(state._lead(db).referred_by_id, UUID(first_id))
        unrelated_id, _ = state._create(
            db, f"other-{suffix}@example.test", True, "not-a-real-referral"
        )
        self.assertNotIn(unrelated_id, (first_id, referred_id))
        state.lead_id = unrelated_id
        self.assertIsNone(state._lead(db).referred_by_id)
        state.lead_id = first_id
        with self.assertRaises(ValueError):
            state._save_answers(db, [])
        state.lead_id = first_id
        with self.assertRaises(ValueError):
            state._save_answers(db, ["unknown"])
        state.lead_id = first_id
        state._save_answers(db, ["budget", "saving"])
        state.lead_id = first_id
        self.assertEqual(state._lead(db).problem_codes, ["budget", "saving"])
        state.lead_id = first_id
        state._mark_invite(db)
        state.lead_id = first_id
        clicked = state._lead(db).invite_clicked_at
        state.lead_id = first_id
        state._mark_invite(db)
        state.lead_id = first_id
        self.assertEqual(state._lead(db).invite_clicked_at, clicked)
        state.lead_id = first_id
        self.assertEqual(
            state._decide(db, "reserved", limit=test_limit), "reserved"
        )
        state.lead_id = first_id
        self.assertEqual(
            state._decide(db, "reserved", limit=test_limit), "reserved"
        )
        state.lead_id = first_id
        self.assertEqual(
            state._decide(db, "free", limit=test_limit), "reserved"
        )
        state.lead_id = first_id
        self.assertIsNotNone(state._lead(db).reserved_at)
        state.lead_id = referred_id
        state._save_answers(db, ["partner"])
        state.lead_id = referred_id
        self.assertEqual(
            state._decide(db, "reserved", limit=test_limit), "full"
        )
        state.lead_id = referred_id
        self.assertEqual(state._lead(db).founder_decision, "pending")
        state.lead_id = referred_id
        self.assertEqual(state._decide(db, "free", limit=test_limit), "free")
        state.lead_id = referred_id
        self.assertIsNone(state._lead(db).reserved_at)
        state.lead_id = referred_id
        self.assertEqual(
            state._decide(db, "reserved", limit=test_limit), "free"
        )
        self.assertEqual(
            db.scalar(select(func.count()).select_from(User)), before_users
        )
        self.assertEqual(
            db.scalar(select(func.count()).select_from(Transaction)),
            before_transactions,
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
            logging.exception("Unexpected error")
            logging.error("Waitlist test failed (%s)", type(e).__name__)
            raise
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
