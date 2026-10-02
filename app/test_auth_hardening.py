import reflex as rx

import logging
import os
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import bcrypt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models as m
from app.states.auth import (
    AuthState,
    INVALID_CREDENTIALS,
    LOCKED_LOGIN,
    digest,
    DUMMY_PASSWORD_HASH,
    now,
    require_account,
    require_permission,
    visible_account_ids,
)


class AuthGuardTests(unittest.TestCase):
    def test_malformed_roles_never_gain_owner_privileges(self):
        db = Mock()
        for member in (
            SimpleNamespace(),
            SimpleNamespace(role="OWNER", can_add_transactions=True),
            SimpleNamespace(role=None, can_add_transactions=True),
        ):
            with self.assertRaises(ValueError):
                require_permission(member, "can_add_transactions")
            with self.assertRaises(ValueError):
                require_account(db, member, uuid4())
            with self.assertRaises(ValueError):
                visible_account_ids(db, member, [])
        db.scalars.assert_not_called()
        partner = SimpleNamespace(role="partner", can_add_transactions=True)
        require_permission(partner, "can_add_transactions")
        require_permission(SimpleNamespace(role="owner"), "can_edit_budgets")

    def test_oversize_input_never_reaches_database_or_hashing(self):
        state = AuthState()
        with (
            patch("app.states.auth.rx.session") as database,
            patch("app.states.auth.bcrypt.checkpw") as check,
        ):
            AuthState.login.fn(
                state,
                {"email": f"{'a' * 321}@example.test", "password": "wrong"},
            )
            self.assertEqual(state.error, INVALID_CREDENTIALS)
            AuthState.login.fn(
                state, {"email": "one@example.test", "password": "x" * 73}
            )
            self.assertEqual(state.error, INVALID_CREDENTIALS)
            database.assert_not_called()
            check.assert_not_called()

    def test_missing_account_runs_dummy_bcrypt_after_identifier_lock(self):
        state = AuthState()
        db = Mock()
        db.scalar.return_value = None
        with patch(
            "app.states.auth.bcrypt.checkpw", return_value=False
        ) as check:
            result = state._login_attempt(db, "nobody@example.test", b"wrong")
        self.assertEqual(result, "invalid")
        self.assertEqual(check.call_args.args, (b"wrong", DUMMY_PASSWORD_HASH))
        self.assertIn(
            "pg_advisory_xact_lock", str(db.execute.call_args.args[0])
        )
        self.assertEqual(db.mock_calls[0][0], "execute")
        attempt = db.add.call_args.args[0]
        self.assertEqual(
            attempt.identifier_digest, digest("nobody@example.test")
        )
        self.assertEqual(attempt.attempt_count, 1)
        db.commit.assert_called_once()

    def test_session_commit_failure_never_publishes_token(self):
        state = AuthState()
        db = Mock()
        user = SimpleNamespace(
            id=uuid4(),
            display_name="Test",
            email="one@example.test",
            password_hash=DUMMY_PASSWORD_HASH.decode(),
        )
        db.scalar.side_effect = [None, user, None]
        db.commit.side_effect = RuntimeError("commit failed")
        with patch("app.states.auth.bcrypt.checkpw", return_value=True):
            with self.assertRaises(RuntimeError):
                state._login_attempt(db, user.email, b"correct")
        self.assertEqual(state.token, "")
        self.assertFalse(state.authenticated)
        self.assertEqual(db.execute.call_count, 1)

    def test_database_failure_does_not_create_session_or_expose_exception(self):
        state = AuthState()
        database = Mock()
        database.execute.side_effect = RuntimeError("sensitive bind parameters")
        context = Mock()
        context.__enter__ = Mock(return_value=database)
        context.__exit__ = Mock(return_value=False)
        with (
            patch("app.states.auth.rx.session", return_value=context),
            patch("app.states.auth.logging.error") as log,
        ):
            AuthState.login.fn(
                state, {"email": "one@example.test", "password": "wrong"}
            )
        self.assertEqual(state.token, "")
        self.assertFalse(state.authenticated)
        self.assertNotIn("sensitive", state.error)
        self.assertNotIn("sensitive", str(log.call_args))
        database.scalar.assert_not_called()


class ManagedAuthTests(unittest.TestCase):
    def test_database_backed_login_isolation_and_recovery(self):
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
                    self.exercise(connection)
                finally:
                    outer.rollback()
        except Exception as e:
            logging.exception("Unexpected error")
            logging.error("Auth regression failed (%s)", type(e).__name__)
            raise
        finally:
            engine.dispose()

    def exercise(self, connection):
        def session():
            return Session(
                bind=connection, join_transaction_mode="create_savepoint"
            )

        suffix = uuid4().hex
        email = f"auth-{suffix}@example.test"
        other_email = f"other-{suffix}@example.test"
        unknown_email = f"unknown-{suffix}@example.test"
        secret = "Correct-password-123"
        with session() as db:
            user = m.User(
                display_name="اختبار",
                email=email,
                password_hash=bcrypt.hashpw(
                    secret.encode(), bcrypt.gensalt()
                ).decode(),
            )
            other = m.User(
                display_name="شخص آخر",
                email=other_email,
                password_hash=bcrypt.hashpw(
                    secret.encode(), bcrypt.gensalt()
                ).decode(),
            )
            db.add_all([user, other])
            db.flush()
            household = m.Household(name="الأسرة الأولى", owner_user_id=user.id)
            foreign = m.Household(name="الأسرة الأخرى", owner_user_id=other.id)
            db.add_all([household, foreign])
            db.flush()
            db.add_all(
                [
                    m.HouseholdMembership(
                        household_id=household.id, user_id=user.id, role="owner"
                    ),
                    m.HouseholdMembership(
                        household_id=foreign.id, user_id=other.id, role="owner"
                    ),
                    m.HouseholdMembership(
                        household_id=foreign.id,
                        user_id=user.id,
                        role="partner",
                        can_add_transactions=False,
                        can_edit_budgets=False,
                    ),
                ]
            )
            db.flush()
            account = m.FinancialAccount(
                household_id=foreign.id,
                created_by_user_id=other.id,
                name="محجوب",
                currency="SAR",
            )
            db.add(account)
            db.flush()
            db.add(
                m.HouseholdAccountRestriction(
                    household_id=foreign.id,
                    member_user_id=user.id,
                    account_id=account.id,
                )
            )
            db.commit()
            user_id, household_id, foreign_id, account_id = (
                user.id,
                household.id,
                foreign.id,
                account.id,
            )

        def sign_in(state, identifier, password):
            return AuthState.login.fn(
                state,
                {"email": f"  {identifier.upper()}  ", "password": password},
            )

        with patch("app.states.auth.rx.session", side_effect=session):
            fresh = AuthState()
            sign_in(fresh, email, "wrong")
            self.assertEqual(fresh.error, INVALID_CREDENTIALS)
            unknown = AuthState()
            sign_in(unknown, unknown_email, "wrong")
            self.assertEqual(unknown.error, fresh.error)
            with session() as db:
                attempt = db.scalar(
                    select(m.AuthenticationAttempt).where(
                        m.AuthenticationAttempt.identifier_digest
                        == digest(email)
                    )
                )
                self.assertEqual(attempt.attempt_count, 1)
                self.assertEqual(attempt.identifier_digest, digest(email))
                self.assertNotEqual(attempt.identifier_digest, email)
            for _ in range(4):
                sign_in(AuthState(), email, "wrong")
            with session() as db:
                attempt = db.scalar(
                    select(m.AuthenticationAttempt).where(
                        m.AuthenticationAttempt.identifier_digest
                        == digest(email)
                    )
                )
                self.assertEqual(attempt.attempt_count, 5)
                locked_until = attempt.locked_until
                self.assertIsNotNone(locked_until)
            locked = AuthState()
            sign_in(locked, email, secret)
            self.assertEqual(locked.error, LOCKED_LOGIN)
            self.assertFalse(locked.authenticated)
            with session() as db:
                attempt = db.scalar(
                    select(m.AuthenticationAttempt).where(
                        m.AuthenticationAttempt.identifier_digest
                        == digest(email)
                    )
                )
                self.assertEqual(attempt.locked_until, locked_until)
                self.assertEqual(attempt.attempt_count, 5)
            other_state = AuthState()
            sign_in(other_state, other_email, secret)
            self.assertTrue(other_state.authenticated)
            future = now() + timedelta(minutes=16)
            with patch("app.states.auth.now", return_value=future):
                sign_in(AuthState(), email, "wrong")
                with session() as db:
                    attempt = db.scalar(
                        select(m.AuthenticationAttempt).where(
                            m.AuthenticationAttempt.identifier_digest
                            == digest(email)
                        )
                    )
                    self.assertEqual(attempt.attempt_count, 1)
                    self.assertIsNone(attempt.locked_until)
                recovered = AuthState()
                recovered.pending_invite = "invitation-in-progress"
                sign_in(recovered, email, secret)
                self.assertTrue(recovered.authenticated)
                self.assertNotEqual(recovered.token, "")
                self.assertEqual(recovered.error, "")
                with session() as db:
                    self.assertIsNone(
                        db.scalar(
                            select(m.AuthenticationAttempt).where(
                                m.AuthenticationAttempt.identifier_digest
                                == digest(email)
                            )
                        )
                    )
                    self.assertEqual(recovered._identity(db).id, user_id)
                    recovered.selected_household = str(uuid4())
                    _, member = recovered._household(db)
                    self.assertIn(
                        member.household_id, {household_id, foreign_id}
                    )
                    self.assertEqual(member.user_id, user_id)
                    recovered.selected_household = str(foreign_id)
                    _, member = recovered._household(db)
                    self.assertEqual(member.role, "partner")
                    self.assertEqual(member.household_id, foreign_id)
                    with self.assertRaises(ValueError):
                        require_permission(member, "can_add_transactions")
                    with self.assertRaises(ValueError):
                        require_account(db, member, account_id)
                    self.assertNotIn(
                        account_id,
                        visible_account_ids(
                            db, member, [SimpleNamespace(id=account_id)]
                        ),
                    )
                old_token = recovered.token
                sign_in(recovered, email, secret)
                rotated_token = recovered.token
                self.assertTrue(recovered.authenticated)
                self.assertNotEqual(rotated_token, "")
                self.assertNotEqual(rotated_token, old_token)
                stale = AuthState()
                stale.token = old_token
                with session() as db:
                    with self.assertRaises(PermissionError):
                        stale._identity(db)
                    self.assertFalse(stale.authenticated)
                verifier = AuthState()
                verifier.token = rotated_token
                with session() as db:
                    self.assertEqual(verifier._identity(db).id, user_id)
                AuthState.logout.fn(verifier)
                logged_out = AuthState()
                logged_out.token = rotated_token
                with session() as db:
                    with self.assertRaises(PermissionError):
                        logged_out._identity(db)
                    self.assertFalse(logged_out.authenticated)
