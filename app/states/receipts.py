import reflex as rx

import base64
from app.observability import report_unexpected
import re
from pathlib import PurePath
from uuid import UUID

from sqlalchemy import select

from app import models as m
from app.states.auth import AuthState, require_account, require_permission

import logging

UPLOAD_ID = "transaction_receipt"
PHOTO_UPLOAD_ID = "transaction_receipt_photo"
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def validate_receipt(filename: str, mime: str, data: bytes) -> tuple[str, str]:
    if not 0 < len(data) <= MAX_RECEIPT_BYTES:
        raise ValueError("يجب أن يكون حجم الإيصال بين 1 بايت و5 ميغابايت.")
    basename = filename.replace("\\", "/").split("/")[-1]
    suffix = PurePath(basename).suffix.lower()
    expected = ALLOWED_EXTENSIONS.get(suffix)
    if not expected or mime.lower().split(";", 1)[0].strip() != expected:
        raise ValueError(
            "اختر صورة PNG أو JPG أو WEBP أو ملف PDF بامتداد ونوع مطابقين."
        )
    valid = {
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n")
        and b"IHDR" in data[:32],
        "image/jpeg": data.startswith(b"\xff\xd8\xff")
        and data.endswith(b"\xff\xd9"),
        "image/webp": data.startswith(b"RIFF")
        and data[8:12] == b"WEBP"
        and data[12:16] in (b"VP8 ", b"VP8L", b"VP8X"),
        "application/pdf": data.startswith(b"%PDF-")
        and b"%%EOF" in data[-1024:],
    }
    if not valid[expected]:
        raise ValueError("محتوى الملف لا يطابق نوع الإيصال المحدد.")
    stem = (
        re.sub(r"[^\w\- .\u0600-\u06ff]", "_", basename[: -len(suffix)]).strip(
            " ._"
        )
        or "receipt"
    )
    return f"{stem[: 200 - len(suffix)]}{suffix}", expected


class ReceiptState(rx.State):
    transaction_id: str = ""
    household_id: str = ""
    filename: str = ""
    size_bytes: int = 0
    mime_type: str = ""
    preview_uri: str = ""
    loading: bool = False
    error: str = ""
    message: str = ""
    can_manage: bool = False

    def _clear_receipt(self) -> None:
        self.filename = ""
        self.size_bytes = 0
        self.mime_type = ""
        self.preview_uri = ""

    def _close(self) -> None:
        self.transaction_id = ""
        self.household_id = ""
        self._clear_receipt()
        self.loading = False
        self.error = ""
        self.message = ""
        self.can_manage = False

    def _authorized(
        self,
        db,
        auth,
        transaction_id: str,
        household_id: str = "",
        write: bool = False,
    ):
        user, member = auth._household(db)
        if household_id and str(member.household_id) != household_id:
            raise PermissionError("تغيرت الأسرة. افتح الإيصال مجددًا.")
        if write:
            require_permission(member, "can_add_transactions")
        try:
            tid = UUID(transaction_id)
        except (ValueError, TypeError, AttributeError) as e:
            logging.exception("Unexpected error")
            raise ValueError("المعاملة غير متاحة.")
        transaction = db.scalar(
            select(m.Transaction).where(
                m.Transaction.id == tid,
                m.Transaction.household_id == member.household_id,
                m.Transaction.deleted_at.is_(None),
            )
        )
        if transaction is None:
            raise ValueError("المعاملة غير متاحة.")
        require_account(db, member, transaction.account_id)
        return user, member, transaction

    @rx.event
    def close_receipt(self):
        self._close()
        return [
            rx.clear_selected_files(UPLOAD_ID),
            rx.clear_selected_files(PHOTO_UPLOAD_ID),
        ]

    @rx.event
    async def open_receipt(self, transaction_id: str):
        self._close()
        self.transaction_id = transaction_id
        self.loading = True
        yield rx.clear_selected_files(UPLOAD_ID)
        yield rx.clear_selected_files(PHOTO_UPLOAD_ID)
        try:
            auth = await self.get_state(AuthState)

            def load(db):
                _, member, transaction = self._authorized(
                    db, auth, transaction_id
                )
                receipt = db.scalar(
                    select(m.TransactionReceipt).where(
                        m.TransactionReceipt.household_id
                        == member.household_id,
                        m.TransactionReceipt.transaction_id == transaction.id,
                    )
                )
                return (
                    str(member.household_id),
                    receipt.filename if receipt else "",
                    receipt.mime_type if receipt else "",
                    receipt.size_bytes if receipt else 0,
                    member.role == "owner" or member.can_add_transactions,
                )

            async with rx.asession() as session:
                hid, filename, mime, size, can_manage = await session.run_sync(
                    load
                )
            self.transaction_id = transaction_id
            self.household_id = hid
            self.filename, self.mime_type, self.size_bytes = (
                filename,
                mime,
                size,
            )
            self.can_manage = can_manage
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            self._clear_receipt()
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("receipts.open", e)
            self._clear_receipt()
            self.error = "تعذر فتح الإيصال. حاول مجددًا."
        finally:
            self.loading = False

    @rx.event
    async def upload_receipt(self, files: list[rx.UploadFile]):
        self.error = self.message = ""
        if not self.transaction_id or not self.household_id:
            self.error = "افتح المعاملة أولًا."
            return
        transaction_id, household_id = self.transaction_id, self.household_id
        self.loading = True
        yield
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as session:
                await session.run_sync(
                    lambda db: self._authorized(
                        db, auth, transaction_id, household_id, True
                    )
                )
            if len(files) != 1:
                raise ValueError("اختر ملف إيصال واحدًا فقط.")
            file = files[0]
            data = await file.read(MAX_RECEIPT_BYTES + 1)
            filename, mime = validate_receipt(
                file.name or "", file.content_type or "", data
            )

            def save(db):
                user, member, transaction = self._authorized(
                    db, auth, transaction_id, household_id, True
                )
                db.scalar(
                    select(m.Transaction)
                    .where(m.Transaction.id == transaction.id)
                    .with_for_update()
                )
                receipt = db.scalar(
                    select(m.TransactionReceipt)
                    .where(
                        m.TransactionReceipt.household_id
                        == member.household_id,
                        m.TransactionReceipt.transaction_id == transaction.id,
                    )
                    .with_for_update()
                )
                if receipt is None:
                    db.add(
                        m.TransactionReceipt(
                            household_id=member.household_id,
                            transaction_id=transaction.id,
                            created_by_user_id=user.id,
                            filename=filename,
                            mime_type=mime,
                            content=data,
                            size_bytes=len(data),
                        )
                    )
                else:
                    receipt.filename, receipt.mime_type = filename, mime
                    receipt.content, receipt.size_bytes = data, len(data)
                    receipt.created_by_user_id = user.id
                db.commit()

            async with rx.asession() as session:
                await session.run_sync(save)
            if (
                self.transaction_id == transaction_id
                and self.household_id == household_id
            ):
                self._clear_receipt()
                self.filename, self.mime_type, self.size_bytes = (
                    filename,
                    mime,
                    len(data),
                )
                self.message = "تم حفظ الإيصال بأمان."
            yield rx.clear_selected_files(UPLOAD_ID)
            yield rx.clear_selected_files(PHOTO_UPLOAD_ID)
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            self._clear_receipt()
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("receipts.upload", e)
            self._clear_receipt()
            self.error = "تعذر حفظ الإيصال. حاول مجددًا."
        finally:
            self.loading = False

    @rx.event
    async def delete_receipt(self):
        self.error = self.message = ""
        transaction_id, household_id = self.transaction_id, self.household_id
        self.loading = True
        yield
        try:
            auth = await self.get_state(AuthState)

            def delete(db):
                _, member, transaction = self._authorized(
                    db, auth, transaction_id, household_id, True
                )
                db.scalar(
                    select(m.Transaction)
                    .where(m.Transaction.id == transaction.id)
                    .with_for_update()
                )
                receipt = db.scalar(
                    select(m.TransactionReceipt)
                    .where(
                        m.TransactionReceipt.household_id
                        == member.household_id,
                        m.TransactionReceipt.transaction_id == transaction.id,
                    )
                    .with_for_update()
                )
                if receipt is None:
                    raise ValueError("لا يوجد إيصال لهذه المعاملة.")
                db.delete(receipt)
                db.commit()

            async with rx.asession() as session:
                await session.run_sync(delete)
            self._clear_receipt()
            self.message = "تم حذف الإيصال."
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            self._clear_receipt()
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("receipts.delete", e)
            self._clear_receipt()
            self.error = "تعذر حذف الإيصال. حاول مجددًا."
        finally:
            self.loading = False

    async def _read(self):
        auth = await self.get_state(AuthState)
        transaction_id, household_id = self.transaction_id, self.household_id
        if not transaction_id or not household_id:
            raise ValueError("افتح المعاملة أولًا.")

        def read(db):
            _, member, transaction = self._authorized(
                db, auth, transaction_id, household_id
            )
            receipt = db.scalar(
                select(m.TransactionReceipt).where(
                    m.TransactionReceipt.household_id == member.household_id,
                    m.TransactionReceipt.transaction_id == transaction.id,
                )
            )
            if receipt is None:
                raise ValueError("لا يوجد إيصال لهذه المعاملة.")
            return receipt.filename, receipt.mime_type, receipt.content

        async with rx.asession() as session:
            return await session.run_sync(read)

    @rx.event
    async def preview_receipt(self):
        self.error = ""
        self.preview_uri = ""
        self.loading = True
        yield
        try:
            filename, mime, data = await self._read()
            validate_receipt(filename, mime, data)
            if mime == "application/pdf":
                raise ValueError(
                    "لأمان بياناتك، حمّل ملف PDF لعرضه بدلًا من فتحه داخل الصفحة."
                )
            self.preview_uri = (
                f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            )
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            self._clear_receipt()
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("receipts.preview", e)
            self._clear_receipt()
            self.error = "تعذرت معاينة الإيصال. حاول مجددًا."
        finally:
            self.loading = False

    @rx.event
    async def download_receipt(self):
        self.error = ""
        try:
            filename, mime, data = await self._read()
            filename, mime = validate_receipt(filename, mime, data)
            return rx.download(
                data=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
                filename=filename,
            )
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            self._clear_receipt()
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("receipts.download", e)
            self._clear_receipt()
            self.error = "تعذر تنزيل الإيصال. حاول مجددًا."
