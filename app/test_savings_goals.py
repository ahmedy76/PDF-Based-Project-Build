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
from app.states.goals import GoalState


class GoalDialogTests(unittest.TestCase):
    def test_open_edit_allocate_and_close(self):
        state = GoalState()
        GoalState.open_goal.fn(state, "")
        self.assertEqual(state.editor, "goal")
        self.assertEqual(state.draft["name"], "")
        state.goals = [
            {
                "id": str(uuid4()),
                "name": "رحلة",
                "description": "صيفًا",
                "amount": "0.00",
                "target": "100.00",
                "target_amount": "100.0000",
                "remaining": "100.00",
                "date": "",
                "status": "قيد الادخار",
                "percent": "0.0",
                "progress": 0.0,
                "history": [],
            }
        ]
        goal_id = state.goals[0]["id"]
        GoalState.open_goal.fn(state, goal_id)
        self.assertEqual(state.draft["name"], "رحلة")
        GoalState.open_allocation.fn(state, goal_id, "release")
        self.assertEqual(
            (state.editor, state.allocation_kind), ("allocation", "release")
        )
        GoalState.close_editor.fn(state)
        self.assertEqual((state.editor, state.edit_id), ("", ""))
        GoalState.open_allocation.fn(state, str(uuid4()), "add")
        self.assertEqual(state.editor, "")
        self.assertNotEqual(state.error, "")


class ManagedSavingsGoalsTests(unittest.TestCase):
    def _seed(self, db: Session, suffix: str):
        user = m.User(
            display_name="مختبر الأهداف",
            email=f"goals-{suffix}@example.test",
            password_hash=bcrypt.hashpw(
                secrets.token_bytes(24), bcrypt.gensalt()
            ).decode(),
        )
        db.add(user)
        db.flush()
        household = m.Household(name="أسرة الأهداف", owner_user_id=user.id)
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
        user, household = self._seed(db, suffix)
        outsider, other = self._seed(db, f"other-{suffix}")
        state = GoalState()
        emergency = state._save_goal(
            db,
            household.id,
            user.id,
            {
                "name": "  صندوق الطوارئ  ",
                "description": "احتياط الأسرة",
                "target_amount": "100.0000",
                "target_date": "",
            },
        )
        trip = state._save_goal(
            db,
            household.id,
            user.id,
            {
                "name": "رحلة عائلية",
                "target_amount": "300",
                "target_date": date.today().isoformat(),
            },
        )
        db.flush()
        self.assertEqual(emergency.name, "صندوق الطوارئ")
        with self.assertRaisesRegex(ValueError, "اسم الهدف"):
            state._save_goal(
                db, household.id, user.id, {"name": " ", "target_amount": "1"}
            )
        for amount in ("0", "-1", "1.12345", "NaN", "1000000000000000"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                state._save_goal(
                    db,
                    household.id,
                    user.id,
                    {"name": "غير صالح", "target_amount": amount},
                )
        with self.assertRaises(ValueError):
            state._save_goal(
                db,
                household.id,
                user.id,
                {
                    "name": "قديم",
                    "target_amount": "2",
                    "target_date": "2000-01-01",
                },
            )
        with self.assertRaises(ValueError):
            state._save_goal(
                db,
                household.id,
                user.id,
                {
                    "name": "يوم",
                    "target_amount": "2",
                    "target_date": "2026-02-30",
                },
            )
        trip.target_date = date(2000, 1, 1)
        db.flush()
        state._save_goal(
            db,
            household.id,
            user.id,
            {
                "name": "رحلة عائلية",
                "target_amount": "300",
                "target_date": "2000-01-01",
            },
            str(trip.id),
        )
        with self.assertRaisesRegex(ValueError, "الماضي"):
            state._save_goal(
                db,
                household.id,
                user.id,
                {
                    "name": "رحلة عائلية",
                    "target_amount": "300",
                    "target_date": "2000-01-02",
                },
                str(trip.id),
            )
        with self.assertRaisesRegex(ValueError, "غير متاح"):
            state._save_goal(
                db,
                other.id,
                outsider.id,
                {"name": "غريب", "target_amount": "1"},
                str(emergency.id),
            )
        with self.assertRaisesRegex(PermissionError, "عضوية"):
            state._save_goal(
                db, other.id, user.id, {"name": "غريب", "target_amount": "1"}
            )
        for kind, amount in (
            ("add", "125.2500"),
            ("release", "25.25"),
            ("add", "50"),
        ):
            state._allocate(
                db,
                household.id,
                user.id,
                str(emergency.id),
                kind,
                {"amount": amount, "note": "مراجعة يدوية"},
            )
        state._allocate(
            db,
            household.id,
            user.id,
            str(trip.id),
            "add",
            {"amount": "20.0001"},
        )
        with self.assertRaisesRegex(ValueError, "يتجاوز"):
            state._allocate(
                db,
                household.id,
                user.id,
                str(emergency.id),
                "release",
                {"amount": "150.0001"},
            )
        with self.assertRaisesRegex(ValueError, "غير متاح"):
            state._allocate(
                db,
                other.id,
                outsider.id,
                str(emergency.id),
                "add",
                {"amount": "1"},
            )
        with self.assertRaisesRegex(ValueError, "غير متاح"):
            state._archive(db, other.id, outsider.id, str(emergency.id), True)
        with self.assertRaisesRegex(ValueError, "غير متاح"):
            state._archive(db, household.id, user.id, "not-a-uuid", True)
        db.flush()
        state._load(db, household.id)
        self.assertEqual((state.active_count, state.completed_count), (2, 1))
        funded = next(
            row for row in state.goals if row["id"] == str(emergency.id)
        )
        self.assertEqual(
            (funded["amount"], funded["remaining"], funded["status"]),
            ("150.0000", "0.0000", "مكتمل"),
        )
        self.assertEqual(funded["target"], "100.0000")
        self.assertEqual(funded["target_amount"], "100.0000")
        self.assertNotEqual(funded["target_amount"], funded["amount"])
        GoalState.open_goal.fn(state, str(emergency.id))
        self.assertEqual(
            (state.editor, state.edit_id), ("goal", str(emergency.id))
        )
        self.assertEqual(
            state.draft,
            {
                "name": "صندوق الطوارئ",
                "description": "احتياط الأسرة",
                "target_amount": "100.0000",
                "target_date": "",
            },
        )
        self.assertEqual(state.error, "")
        self.assertEqual(
            (funded["percent"], funded["progress"]), ("150.0", 100.0)
        )
        self.assertEqual(
            sorted(h["kind"] for h in funded["history"]),
            ["add", "add", "release"],
        )
        self.assertEqual(
            next(row for row in state.goals if row["id"] == str(trip.id))[
                "remaining"
            ],
            "279.9999",
        )
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.Transaction)
                .where(m.Transaction.household_id == household.id)
            ),
            0,
        )
        state._archive(db, household.id, user.id, str(emergency.id), True)
        db.flush()
        state._load(db, household.id)
        self.assertEqual(state.active_count, 1)
        self.assertEqual(len(state.archived_goals[0]["history"]), 3)
        with self.assertRaisesRegex(ValueError, "مؤرشف"):
            state._allocate(
                db,
                household.id,
                user.id,
                str(emergency.id),
                "add",
                {"amount": "1"},
            )
        with self.assertRaisesRegex(ValueError, "استعد"):
            state._save_goal(
                db,
                household.id,
                user.id,
                {"name": "جديد", "target_amount": "10"},
                str(emergency.id),
            )
        state._archive(db, household.id, user.id, str(emergency.id), False)
        db.flush()
        state._load(db, household.id)
        self.assertEqual(
            len(
                next(
                    row for row in state.goals if row["id"] == str(emergency.id)
                )["history"]
            ),
            3,
        )
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.Transaction)
                .where(m.Transaction.household_id == household.id)
            ),
            0,
        )
        self.assertEqual(
            db.scalar(
                select(func.count())
                .select_from(m.SavingsGoalAllocation)
                .where(m.SavingsGoalAllocation.household_id == household.id)
            ),
            4,
        )
        db.commit()

    def test_goals_on_isolated_managed_dev_postgres(self):
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
