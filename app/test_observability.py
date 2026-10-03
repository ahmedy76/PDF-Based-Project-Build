import reflex as rx

import asyncio
import importlib
import io
import logging
import unittest
from unittest.mock import Mock, patch

import app.observability as observability
from app.observability import report_unexpected
from app.states.auth import AuthState, INVALID_CREDENTIALS
from app.states.csv_transfer import CsvTransferState, parse_csv
from app.states.receipts import ReceiptState


class SafeLoggingTests(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.root_stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.root_handler = logging.StreamHandler(self.root_stream)
        formatter = logging.Formatter("%(message)s")
        self.handler.setFormatter(formatter)
        self.root_handler.setFormatter(formatter)
        self.logger = logging.getLogger("app.observability")
        self.root_logger = logging.getLogger()
        self.previous_level = self.logger.level
        self.previous_root_level = self.root_logger.level
        self.previous_propagate = self.logger.propagate
        self.logger.setLevel(logging.ERROR)
        self.root_logger.setLevel(logging.ERROR)
        self.logger.propagate = False
        self.logger.addHandler(self.handler)
        self.root_logger.addHandler(self.root_handler)

    def tearDown(self):
        self.root_logger.removeHandler(self.root_handler)
        self.logger.removeHandler(self.handler)
        self.logger.propagate = self.previous_propagate
        self.logger.setLevel(self.previous_level)
        self.root_logger.setLevel(self.previous_root_level)
        self.handler.close()
        self.root_handler.close()

    def assert_redacted(self, secret: str):
        output = f"{self.stream.getvalue()}\n{self.root_stream.getvalue()}"
        self.assertNotIn(secret, output)
        self.assertNotIn("Traceback", output)
        self.assertTrue(
            all(
                line == "application_state_event"
                for line in self.root_stream.getvalue().splitlines()
            )
        )

    def test_only_static_operation_class_and_random_reference_are_reported(
        self,
    ):
        secret = (
            "private@example.test token=opaque amount=987654.32 receipt-bytes"
        )
        error = RuntimeError(secret)
        first = report_unexpected("auth.login", error)
        second = report_unexpected("auth.login", error)
        text = self.stream.getvalue()
        self.assert_redacted(secret)
        self.assertNotIn("private@example.test", text)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{16}$")
        self.assertEqual(
            text.splitlines(),
            [
                f"application_failure operation=auth.login exception_class=RuntimeError incident={first}",
                f"application_failure operation=auth.login exception_class=RuntimeError incident={second}",
            ],
        )

    def test_login_failure_has_generic_response_and_no_exception_payload(self):
        secret = "bind private@example.test password=do-not-log"
        db = Mock()
        db.execute.side_effect = RuntimeError(secret)
        context = Mock()
        context.__enter__ = Mock(return_value=db)
        context.__exit__ = Mock(return_value=False)
        state = AuthState()
        with patch("app.states.auth.rx.session", return_value=context):
            AuthState.login.fn(
                state, {"email": "private@example.test", "password": "wrong"}
            )
        self.assertEqual(state.error, "تعذر تسجيل الدخول. حاول مجددًا.")
        self.assertFalse(state.authenticated)
        self.assertEqual(state.token, "")
        self.assert_redacted(secret)
        self.assertEqual(
            self.root_stream.getvalue().splitlines(),
            ["application_state_event"],
        )
        self.assertIn(
            "operation=auth.login exception_class=RuntimeError incident=",
            self.stream.getvalue(),
        )

    def test_expected_login_and_csv_validation_do_not_log_payloads(self):
        state = AuthState()
        AuthState.login.fn(state, {"email": "invalid", "password": "wrong"})
        self.assertEqual(state.error, INVALID_CREDENTIALS)
        with self.assertRaises(ValueError):
            parse_csv("accounts", b"\xffprivate@example.test")
        self.assertEqual(self.stream.getvalue(), "")
        self.assert_redacted("private@example.test")

    def test_csv_unexpected_failure_does_not_expose_payload(self):
        secret = "synthetic CSV private@example.test token=do-not-log"
        state = CsvTransferState()

        async def fail(_state, auth_class):
            self.assertIs(auth_class, AuthState)
            raise RuntimeError(secret)

        async def exercise():
            with patch.object(CsvTransferState, "get_state", fail):
                await CsvTransferState.export_csv.fn(state)

        asyncio.run(exercise())
        self.assertEqual(state.error, "تعذر تصدير البيانات. حاول ثانية.")
        self.assert_redacted(secret)
        self.assertEqual(
            self.root_stream.getvalue().splitlines(),
            ["application_state_event"],
        )
        self.assertIn(
            "operation=csv_transfer.export_csv exception_class=RuntimeError incident=",
            self.stream.getvalue(),
        )

    def test_receipt_failure_does_not_expose_payload(self):
        secret = "receipt bytes and private@example.test"
        state = ReceiptState()

        async def fail(_state, auth_class):
            self.assertIs(auth_class, AuthState)
            raise RuntimeError(secret)

        async def exercise():
            with patch.object(ReceiptState, "get_state", fail):
                async for _ in ReceiptState.open_receipt.fn(state, "invalid"):
                    pass

        asyncio.run(exercise())
        self.assertEqual(state.error, "تعذر فتح الإيصال. حاول مجددًا.")
        self.assertEqual(state.preview_uri, "")
        self.assert_redacted(secret)
        self.assertEqual(
            self.root_stream.getvalue().splitlines(),
            ["application_state_event"],
        )
        self.assertIn(
            "operation=receipts.open exception_class=RuntimeError",
            self.stream.getvalue(),
        )

    def test_state_factory_redacts_payload_before_handlers_and_is_idempotent(
        self,
    ):
        factory = logging.getLogRecordFactory()
        importlib.reload(observability)
        self.assertIs(logging.getLogRecordFactory(), factory)

        record = factory(
            "root",
            logging.ERROR,
            "C:\\project\\app\\states\\auth.py",
            42,
            "sensitive %s",
            ("private@example.test",),
            (RuntimeError, RuntimeError("private@example.test"), None),
            sinfo="sensitive stack",
        )
        self.assertEqual(record.msg, "application_state_event")
        self.assertEqual(record.args, ())
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.exc_text)
        self.assertIsNone(record.stack_info)

        other = factory(
            "third.party",
            logging.ERROR,
            "/project/vendor/module.py",
            42,
            "third-party message",
            (),
            None,
            None,
        )
        self.assertEqual(other.msg, "third-party message")
        self.assertEqual(other.pathname, "/project/vendor/module.py")
        self.assertEqual(self.root_stream.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
