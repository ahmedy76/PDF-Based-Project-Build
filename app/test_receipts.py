import reflex as rx

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app import models as m
from app.states.receipts import (
    MAX_RECEIPT_BYTES,
    PHOTO_UPLOAD_ID,
    UPLOAD_ID,
    ReceiptState,
    validate_receipt,
)


PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 20
JPEG = b"\xff\xd8\xff" + b"\x00" * 10 + b"\xff\xd9"
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBPVP8 " + b"\x00" * 10
PDF = b"%PDF-1.7\nbody\n%%EOF"


class ReceiptValidationTests(unittest.TestCase):
    def test_valid_signatures_and_clean_names(self):
        for name, mime, data in (
            ("receipt.png", "image/png", PNG),
            ("photo.jpeg", "image/jpeg", JPEG),
            ("scan.webp", "image/webp", WEBP),
            ("invoice.pdf", "application/pdf", PDF),
        ):
            self.assertEqual(validate_receipt(name, mime, data), (name, mime))
        self.assertEqual(
            validate_receipt("../private\\invoice.pdf", "application/pdf", PDF)[
                0
            ],
            "invoice.pdf",
        )
        self.assertEqual(
            validate_receipt("bad\nname.png", "image/png", PNG)[0],
            "bad_name.png",
        )

    def test_rejects_empty_oversize_and_mismatched_magic_mime_or_extension(
        self,
    ):
        for name, mime, data in (
            ("x.png", "image/png", b""),
            ("x.png", "image/png", PNG + b"0" * MAX_RECEIPT_BYTES),
            ("x.pdf", "application/pdf", PNG),
            ("x.jpg", "image/png", PNG),
            ("x.svg", "image/svg+xml", b"<svg></svg>"),
            ("x.pdf", "application/pdf", b"%PDF-1.7 fake"),
            ("x.webp", "image/webp", b"RIFF" + b"0" * 20),
        ):
            with self.subTest(name=name, mime=mime):
                with self.assertRaises(ValueError):
                    validate_receipt(name, mime, data)


class ReceiptAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.state = ReceiptState()
        self.hid, self.uid, self.aid, self.tid = (uuid4() for _ in range(4))
        self.member = SimpleNamespace(
            household_id=self.hid,
            user_id=self.uid,
            role="partner",
            can_add_transactions=False,
        )
        self.transaction = SimpleNamespace(id=self.tid, account_id=self.aid)
        self.auth = Mock()
        self.auth._household.return_value = (
            SimpleNamespace(id=self.uid),
            self.member,
        )
        self.db = Mock()
        self.db.scalar.return_value = self.transaction
        self.db.scalars.return_value.all.return_value = []

    def test_readable_for_partner_but_not_writable(self):
        self.assertEqual(
            self.state._authorized(self.db, self.auth, str(self.tid))[2],
            self.transaction,
        )
        with self.assertRaisesRegex(ValueError, "صلاحية"):
            self.state._authorized(
                self.db, self.auth, str(self.tid), write=True
            )
        self.db.commit.assert_not_called()

    def test_household_mismatch_invalid_uuid_missing_and_hidden_account(self):
        for tid, hid in ((str(self.tid), str(uuid4())), ("not-uuid", "")):
            with self.assertRaises((ValueError, PermissionError)):
                self.state._authorized(self.db, self.auth, tid, hid)
        self.db.scalar.return_value = None
        with self.assertRaisesRegex(ValueError, "غير متاحة"):
            self.state._authorized(self.db, self.auth, str(self.tid))
        self.db.scalar.return_value = self.transaction
        self.db.scalars.return_value.all.return_value = [self.aid]
        with self.assertRaisesRegex(ValueError, "غير متاح"):
            self.state._authorized(self.db, self.auth, str(self.tid))
        sql = str(self.db.scalar.call_args.args[0])
        self.assertIn("mh_transactions.household_id", sql)
        self.assertIn("mh_transactions.deleted_at IS NULL", sql)
        self.db.commit.assert_not_called()


class ReceiptEventTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = ReceiptState()
        self.hid, self.uid, self.aid, self.tid = (uuid4() for _ in range(4))
        self.member = SimpleNamespace(
            household_id=self.hid,
            user_id=self.uid,
            role="owner",
            can_add_transactions=True,
        )
        self.auth = Mock()
        self.auth._household.return_value = (
            SimpleNamespace(id=self.uid),
            self.member,
        )
        self.transaction = SimpleNamespace(id=self.tid, account_id=self.aid)
        self.db = Mock()
        self.db.scalar.side_effect = self.scalar
        self.receipt = None
        self.session = Mock()

        async def run_sync(fn):
            return fn(self.db)

        self.session.run_sync = AsyncMock(side_effect=run_sync)
        self.context = AsyncMock()
        self.context.__aenter__.return_value = self.session
        self.state.transaction_id = str(self.tid)
        self.state.household_id = str(self.hid)

    def scalar(self, query):
        sql = str(query)
        if "mh_transaction_receipts" in sql:
            return self.receipt
        return self.transaction

    async def run_event(self, event, *args):
        async for _ in event.fn(self.state, *args):
            pass

    async def test_create_replace_delete_without_touching_ledger(self):
        file = SimpleNamespace(
            name="invoice.pdf",
            content_type="application/pdf",
            read=AsyncMock(return_value=PDF),
        )
        with (
            patch.object(
                ReceiptState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch("app.states.receipts.rx.asession", return_value=self.context),
        ):
            await self.run_event(ReceiptState.upload_receipt, [file])
            self.assertEqual(self.state.filename, "invoice.pdf")
            self.assertEqual(file.read.call_args.args, (MAX_RECEIPT_BYTES + 1,))
            created = self.db.add.call_args.args[0]
            self.assertIsInstance(created, m.TransactionReceipt)
            self.assertEqual(
                (created.household_id, created.transaction_id, created.content),
                (self.hid, self.tid, PDF),
            )
            self.assertEqual(self.db.commit.call_count, 1)
            self.assertNotIn(
                "mh_transaction_audit_events", str(self.db.scalar.call_args)
            )
            self.receipt = created
            second = SimpleNamespace(
                name="new.jpg",
                content_type="image/jpeg",
                read=AsyncMock(return_value=JPEG),
            )
            await self.run_event(ReceiptState.upload_receipt, [second])
            self.assertEqual(self.db.add.call_count, 1)
            self.assertEqual(self.receipt.content, JPEG)
            self.assertEqual(self.receipt.filename, "new.jpg")
            self.assertEqual(self.db.commit.call_count, 2)
            await self.run_event(ReceiptState.delete_receipt)
            self.db.delete.assert_called_once_with(self.receipt)
            self.assertEqual(self.db.commit.call_count, 3)
            self.assertEqual(self.state.filename, "")

    async def test_screenshot_png_upload_and_replacement_clear_both_pickers(
        self,
    ):
        screenshot = SimpleNamespace(
            name="لقطة شاشة.png",
            content_type="image/png",
            read=AsyncMock(return_value=PNG),
        )
        replacement_data = PNG + b"replacement"
        replacement = SimpleNamespace(
            name="لقطة جديدة.png",
            content_type="image/png",
            read=AsyncMock(return_value=replacement_data),
        )
        with (
            patch.object(
                ReceiptState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch("app.states.receipts.rx.asession", return_value=self.context),
            patch("app.states.receipts.rx.clear_selected_files") as clear,
        ):
            await self.run_event(ReceiptState.upload_receipt, [screenshot])
            self.receipt = self.db.add.call_args.args[0]
            self.assertEqual(self.receipt.content, PNG)
            self.assertEqual(self.receipt.mime_type, "image/png")
            self.assertEqual(self.state.filename, "لقطة شاشة.png")
            self.assertEqual(
                [call.args[0] for call in clear.call_args_list],
                [UPLOAD_ID, PHOTO_UPLOAD_ID],
            )
            clear.reset_mock()
            self.state.preview_uri = "previous-preview"
            await self.run_event(ReceiptState.upload_receipt, [replacement])
            self.assertEqual(self.db.add.call_count, 1)
            self.assertEqual(self.db.commit.call_count, 2)
            self.assertEqual(self.receipt.content, replacement_data)
            self.assertEqual(self.receipt.filename, "لقطة جديدة.png")
            self.assertEqual(self.receipt.size_bytes, len(replacement_data))
            self.assertEqual(self.state.preview_uri, "")
            self.assertEqual(self.state.mime_type, "image/png")
            self.assertEqual(
                [call.args[0] for call in clear.call_args_list],
                [UPLOAD_ID, PHOTO_UPLOAD_ID],
            )
            screenshot.read.assert_awaited_once_with(MAX_RECEIPT_BYTES + 1)
            replacement.read.assert_awaited_once_with(MAX_RECEIPT_BYTES + 1)

    async def test_modal_open_and_close_clear_both_pickers(self):
        self.assertNotEqual(UPLOAD_ID, PHOTO_UPLOAD_ID)
        with (
            patch.object(
                ReceiptState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch("app.states.receipts.rx.asession", return_value=self.context),
            patch("app.states.receipts.rx.clear_selected_files") as clear,
        ):
            await self.run_event(ReceiptState.open_receipt, str(self.tid))
            self.assertEqual(
                [call.args[0] for call in clear.call_args_list],
                [UPLOAD_ID, PHOTO_UPLOAD_ID],
            )
            clear.reset_mock()
            events = ReceiptState.close_receipt.fn(self.state)
            self.assertEqual(len(events), 2)
            self.assertEqual(
                [call.args[0] for call in clear.call_args_list],
                [UPLOAD_ID, PHOTO_UPLOAD_ID],
            )
            self.assertEqual(self.state.transaction_id, "")
            self.assertEqual(self.state.household_id, "")
            self.assertFalse(self.state.can_manage)

    async def test_screenshot_denied_before_read_for_permission_account_or_household(
        self,
    ):
        for restriction in ("permission", "account", "household"):
            with self.subTest(restriction=restriction):
                self.db.add.reset_mock()
                self.db.commit.reset_mock()
                self.member.role = (
                    "owner" if restriction == "household" else "partner"
                )
                self.member.can_add_transactions = restriction != "permission"
                self.member.household_id = (
                    uuid4() if restriction == "household" else self.hid
                )
                self.db.scalars.return_value.all.return_value = (
                    [self.aid] if restriction == "account" else []
                )
                file = SimpleNamespace(
                    name="screenshot.png",
                    content_type="image/png",
                    read=AsyncMock(return_value=PNG),
                )
                with (
                    patch.object(
                        ReceiptState,
                        "get_state",
                        new_callable=AsyncMock,
                        return_value=self.auth,
                    ),
                    patch(
                        "app.states.receipts.rx.asession",
                        return_value=self.context,
                    ),
                    patch(
                        "app.states.receipts.rx.clear_selected_files"
                    ) as clear,
                ):
                    await self.run_event(ReceiptState.upload_receipt, [file])
                self.assertNotEqual(self.state.error, "")
                self.assertFalse(self.state.loading)
                file.read.assert_not_awaited()
                self.db.add.assert_not_called()
                self.db.commit.assert_not_called()
                clear.assert_not_called()

    async def test_empty_selection_does_not_save_or_clear_pickers(self):
        with (
            patch.object(
                ReceiptState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch("app.states.receipts.rx.asession", return_value=self.context),
            patch("app.states.receipts.rx.clear_selected_files") as clear,
        ):
            await self.run_event(ReceiptState.upload_receipt, [])
        self.assertIn("واحدًا", self.state.error)
        self.assertFalse(self.state.loading)
        self.db.commit.assert_not_called()
        clear.assert_not_called()

    async def test_invalid_upload_keeps_database_unchanged(self):
        file = SimpleNamespace(
            name="forged.pdf",
            content_type="application/pdf",
            read=AsyncMock(return_value=PNG),
        )
        with (
            patch.object(
                ReceiptState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch("app.states.receipts.rx.asession", return_value=self.context),
        ):
            await self.run_event(ReceiptState.upload_receipt, [file])
        self.assertIn("لا يطابق", self.state.error)
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    async def test_switch_or_restriction_clears_previous_preview_and_prevents_read(
        self,
    ):
        self.receipt = SimpleNamespace(
            filename="invoice.pdf",
            mime_type="application/pdf",
            content=PDF,
            size_bytes=len(PDF),
        )
        self.state.preview_uri = "old-secret"
        self.state.filename = "invoice.pdf"
        self.auth._household.return_value = (
            SimpleNamespace(id=self.uid),
            SimpleNamespace(household_id=uuid4(), role="owner"),
        )
        with (
            patch.object(
                ReceiptState,
                "get_state",
                new_callable=AsyncMock,
                return_value=self.auth,
            ),
            patch("app.states.receipts.rx.asession", return_value=self.context),
        ):
            await self.run_event(ReceiptState.preview_receipt)
            self.assertEqual(self.state.preview_uri, "")
            self.assertEqual(self.state.filename, "")
            self.assertIn("تغيرت الأسرة", self.state.error)
            self.db.commit.assert_not_called()
            self.auth._household.return_value = (
                SimpleNamespace(id=self.uid),
                self.member,
            )
            self.state.preview_uri = "old-secret"
            await self.run_event(ReceiptState.open_receipt, str(uuid4()))
            self.assertEqual(self.state.preview_uri, "")
            self.assertEqual(self.state.filename, "invoice.pdf")
            ReceiptState.close_receipt.fn(self.state)
            self.assertEqual(self.state.transaction_id, "")
            self.assertEqual(self.state.preview_uri, "")
