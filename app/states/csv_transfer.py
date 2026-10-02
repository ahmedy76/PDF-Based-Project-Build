import reflex as rx

import csv
import io
from app.observability import report_unexpected
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid5

from sqlalchemy import select

from app import models as m
from app.states.auth import (
    AuthState,
    blocked_budget_currencies,
    require_permission,
    visible_account_ids,
)
from app.states.ledger import LedgerState

import logging

HEADERS: dict[str, tuple[str, ...]] = {
    "accounts": (
        "name",
        "account_type",
        "currency",
        "opening_balance",
        "opening_date",
        "is_archived",
        "source_id",
    ),
    "categories": ("kind", "name", "is_archived", "source_id"),
    "transactions": (
        "account_name",
        "account_source_id",
        "currency",
        "category_name",
        "kind",
        "amount",
        "transaction_date",
        "description",
        "source_id",
    ),
    "budgets": (
        "category_name",
        "year",
        "month",
        "currency",
        "amount",
        "alert_threshold_percent",
    ),
    "transfers": (
        "source_account_name",
        "source_account_id",
        "destination_account_name",
        "destination_account_id",
        "currency",
        "amount",
        "transfer_date",
        "note",
        "source_id",
    ),
    "bills": (
        "account_name",
        "account_source_id",
        "currency",
        "title",
        "amount",
        "due_date",
        "status",
        "paid_on",
        "remind_days",
        "notes",
        "source_id",
    ),
    "debts": (
        "title",
        "counterparty",
        "direction",
        "principal",
        "first_due_date",
        "installment_count",
        "note",
        "is_archived",
        "source_id",
    ),
    "debt_installments": (
        "debt_title",
        "counterparty",
        "direction",
        "first_due_date",
        "debt_source_id",
        "sequence_no",
        "due_date",
        "amount",
    ),
    "debt_payments": (
        "debt_title",
        "counterparty",
        "direction",
        "first_due_date",
        "debt_source_id",
        "amount",
        "paid_on",
        "note",
        "voided",
        "source_id",
    ),
}
SAMPLES: dict[str, tuple[str, ...]] = {
    "accounts": (
        "محفظة البيت",
        "cash",
        "SAR",
        "150.0000",
        "2025-01-01",
        "false",
        "",
    ),
    "categories": ("expense", "مستلزمات البيت", "false", ""),
    "transactions": (
        "محفظة البيت",
        "",
        "SAR",
        "مستلزمات البيت",
        "expense",
        "25.5000",
        "2025-01-02",
        "مشتريات أسبوعية",
        "",
    ),
    "budgets": ("مستلزمات البيت", "2025", "1", "SAR", "500.0000", "80"),
    "transfers": (
        "محفظة البيت",
        "",
        "حساب الادخار",
        "",
        "SAR",
        "20.0000",
        "2025-01-02",
        "نقل رصيد",
        "",
    ),
    "bills": (
        "محفظة البيت",
        "",
        "SAR",
        "الكهرباء",
        "100.0000",
        "2025-01-10",
        "unpaid",
        "",
        "3",
        "",
        "",
    ),
    "debts": (
        "قرض المنزل",
        "شركة التمويل",
        "payable",
        "1200.0000",
        "2025-01-10",
        "12",
        "",
        "false",
        "",
    ),
    "debt_installments": (
        "قرض المنزل",
        "شركة التمويل",
        "payable",
        "2025-01-10",
        "",
        "1",
        "2025-01-10",
        "100.0000",
    ),
    "debt_payments": (
        "قرض المنزل",
        "شركة التمويل",
        "payable",
        "2025-01-10",
        "",
        "100.0000",
        "2025-01-10",
        "",
        "false",
        "",
    ),
}
LIMIT_BYTES = 2 * 1024 * 1024
LIMIT_ROWS = 2000


def safe_cell(value: object) -> str:
    text = str(value if value is not None else "")
    if text.lstrip().startswith(
        ("=", "+", "-", "@", "\t", "\r", "\n")
    ) or text.startswith(("\t", "\r", "\n")):
        return f"'{text}"
    return text


def csv_bytes(kind: str, rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(HEADERS[kind])
    writer.writerows(
        [safe_cell(row.get(key, "")) for key in HEADERS[kind]] for row in rows
    )
    return output.getvalue().encode("utf-8-sig")


def parse_csv(kind: str, data: bytes) -> list[dict[str, str]]:
    if kind not in HEADERS:
        raise ValueError("اختر نوع البيانات أولًا.")
    if not data or len(data) > LIMIT_BYTES:
        raise ValueError("الملف فارغ أو يتجاوز 2 ميغابايت.")
    try:
        stream = io.StringIO(data.decode("utf-8-sig"), newline="")
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != list(HEADERS[kind]):
            raise ValueError(
                f"عناوين الأعمدة غير مطابقة. استخدم القالب: {', '.join(HEADERS[kind])}"
            )
        rows = []
        for row in reader:
            if len(rows) >= LIMIT_ROWS:
                raise ValueError("الحد الأقصى 2000 صف بيانات.")
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"الصف {reader.line_num}: عدد الأعمدة غير مطابق للقالب."
                )
            cleaned = {}
            for key, value in row.items():
                text = value.strip()
                if text.startswith("'") and text[1:].lstrip().startswith(
                    ("=", "+", "-", "@")
                ):
                    text = text[1:].strip()
                cleaned[key] = text
            if any(cleaned.values()):
                cleaned["_line"] = str(reader.line_num)
                rows.append(cleaned)
        if not rows:
            raise ValueError("لا توجد صفوف بيانات في الملف.")
        return rows
    except UnicodeError as e:
        logging.exception("Unexpected error")
        raise ValueError("احفظ الملف بترميز UTF-8 ثم حاول ثانية.")
    except csv.Error as e:
        logging.exception("Unexpected error")
        raise ValueError(
            f"تنسيق CSV غير صحيح قرب الصف {reader.line_num}."
        ) from e


def money(value: str, positive: bool = True) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as e:
        logging.exception("Unexpected error")
        raise ValueError("المبلغ غير صالح.")
    if (
        not result.is_finite()
        or result.as_tuple().exponent < -4
        or abs(result) >= Decimal("1000000000000000")
        or (positive and result <= 0)
    ):
        raise ValueError(
            "المبلغ يجب أن يكون موجبًا، محدودًا وبحد أقصى 4 خانات عشرية."
        )
    return result


def currency(value: str) -> str:
    if not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError(
            "العملة يجب أن تكون رمز ISO من ثلاثة أحرف كبيرة مثل SAR."
        )
    return value


def day(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if (
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
            or parsed > date.today()
        ):
            raise ValueError()
        return parsed
    except ValueError as e:
        raise ValueError(
            "التاريخ يجب أن يكون YYYY-MM-DD وألا يكون في المستقبل."
        ) from e


def flag(value: str) -> bool:
    if value not in ("true", "false"):
        raise ValueError("استخدم true أو false للحالة.")
    return value == "true"


def source_id(row: dict[str, str], key: str = "source_id") -> UUID | None:
    raw = row.get(key, "")
    try:
        return UUID(raw) if raw else None
    except ValueError as e:
        raise ValueError("معرّف المصدر يجب أن يكون UUID صالحًا أو فارغًا.") from e


def tenant_id(
    source: UUID | None, household: UUID, existing: dict[UUID, object]
) -> UUID | None:
    if source is None:
        return None
    return source if source in existing else uuid5(household, source.hex)


def debt_identity(
    row: dict[str, str], prefix: str = ""
) -> tuple[str, str, str, date]:
    return (
        row[f"{prefix}title"].casefold(),
        row["counterparty"].casefold(),
        row["direction"],
        date.fromisoformat(row["first_due_date"]),
    )


def validate_row(kind: str, row: dict[str, str]) -> None:
    if kind == "accounts":
        if (
            not row["name"]
            or len(row["name"]) > 120
            or row["account_type"]
            not in ("cash", "bank", "savings", "credit_card", "other")
        ):
            raise ValueError(
                "اسم الحساب (حتى 120 حرفًا) ونوعه cash/bank/savings/credit_card/other مطلوبان."
            )
        currency(row["currency"])
        money(row["opening_balance"], False)
        day(row["opening_date"])
        flag(row.get("is_archived", "false"))
        source_id(row)
    elif kind == "categories":
        if (
            row["kind"] not in ("income", "expense")
            or not row["name"]
            or len(row["name"]) > 100
        ):
            raise ValueError(
                "الفئة تحتاج نوع income أو expense واسمًا لا يزيد على 100 حرف."
            )
        flag(row.get("is_archived", "false"))
        source_id(row)
    elif kind == "transactions":
        if (
            not row["account_name"]
            or not row["category_name"]
            or row["kind"] not in ("income", "expense")
            or len(row["description"]) > 2000
        ):
            raise ValueError(
                "الحساب والفئة والنوع income/expense مطلوبون؛ الوصف حتى 2000 حرف."
            )
        currency(row["currency"])
        money(row["amount"])
        day(row["transaction_date"])
        source_id(row)
        source_id(row, "account_source_id")
    elif kind == "transfers":
        if (
            not row["source_account_name"]
            or not row["destination_account_name"]
            or len(row["note"]) > 500
        ):
            raise ValueError("حسابا التحويل مطلوبان والملاحظة حتى 500 حرف.")
        currency(row["currency"])
        money(row["amount"])
        day(row["transfer_date"])
        source_id(row, "source_account_id")
        source_id(row, "destination_account_id")
        source_id(row)
    elif kind == "bills":
        if (
            not row["account_name"]
            or not 1 <= len(row["title"]) <= 200
            or len(row["notes"]) > 2000
        ):
            raise ValueError(
                "الحساب والعنوان (حتى 200 حرف) مطلوبان؛ الملاحظة حتى 2000 حرف."
            )
        currency(row["currency"])
        money(row["amount"])
        from app.states.debts import parse_date

        parse_date(row["due_date"])
        if row["status"] not in ("paid", "unpaid") or (
            row["status"] == "paid"
        ) != bool(row["paid_on"]):
            raise ValueError(
                "الحالة paid تتطلب paid_on، والحالة unpaid لا تقبل تاريخ سداد."
            )
        if row["paid_on"]:
            day(row["paid_on"])
        if (
            not re.fullmatch(r"\d{1,3}", row["remind_days"])
            or int(row["remind_days"]) > 365
        ):
            raise ValueError("أيام التذكير بين 0 و365.")
        source_id(row)
        source_id(row, "account_source_id")
    elif kind in ("debts", "debt_installments", "debt_payments"):
        prefix = "" if kind == "debts" else "debt_"
        if (
            not 1 <= len(row[f"{prefix}title"]) <= 120
            or not 1 <= len(row["counterparty"]) <= 120
            or row["direction"] not in ("payable", "receivable")
        ):
            raise ValueError(
                "العنوان والطرف (حتى 120 حرفًا) والنوع payable/receivable مطلوبون."
            )
        from app.states.debts import parse_date, schedule

        parse_date(row["first_due_date"])
        if kind == "debts":
            if len(row["note"]) > 500 or not re.fullmatch(
                r"[1-9]\d{0,2}", row["installment_count"]
            ):
                raise ValueError(
                    "الملاحظة حتى 500 حرف، وعدد الأقساط من 1 إلى 120."
                )
            schedule(
                money(row["principal"]),
                date.fromisoformat(row["first_due_date"]),
                int(row["installment_count"]),
            )
            flag(row["is_archived"])
            source_id(row)
        elif kind == "debt_installments":
            source_id(row, "debt_source_id")
            if (
                not re.fullmatch(r"[1-9]\d{0,2}", row["sequence_no"])
                or int(row["sequence_no"]) > 120
            ):
                raise ValueError("تسلسل القسط بين 1 و120.")
            parse_date(row["due_date"])
            money(row["amount"])
        else:
            source_id(row, "debt_source_id")
            source_id(row)
            money(row["amount"])
            day(row["paid_on"])
            if len(row["note"]) > 500:
                raise ValueError("الملاحظة حتى 500 حرف.")
            flag(row["voided"])
    elif kind == "budgets":
        if not row["category_name"]:
            raise ValueError("اسم فئة المصروف مطلوب.")
        try:
            year, month, threshold = (
                int(row["year"]),
                int(row["month"]),
                int(row["alert_threshold_percent"]),
            )
        except ValueError as e:
            raise ValueError(
                "السنة والشهر ونسبة التنبيه يجب أن تكون أعدادًا صحيحة."
            ) from e
        if (
            not 1900 <= year <= 9999
            or not 1 <= month <= 12
            or not 1 <= threshold <= 100
        ):
            raise ValueError(
                "السنة 1900–9999، الشهر 1–12، ونسبة التنبيه 1–100."
            )
        currency(row["currency"])
        money(row["amount"], False)
        if money(row["amount"], False) < 0:
            raise ValueError("حد الميزانية لا يمكن أن يكون سالبًا.")
    else:
        raise ValueError("نوع CSV غير معروف.")


def transaction_key(
    account_id: UUID,
    category_id: UUID,
    row_kind: str,
    amount: Decimal,
    transaction_date: date,
    description: str,
) -> tuple[UUID, UUID, str, Decimal, date, str]:
    return (
        account_id,
        category_id,
        row_kind,
        amount,
        transaction_date,
        description,
    )


def transfer_rows(db, member, kind: str) -> list[dict[str, str]]:
    hid = member.household_id
    accounts = db.scalars(
        select(m.FinancialAccount).where(m.FinancialAccount.household_id == hid)
    ).all()
    allowed = visible_account_ids(db, member, accounts)
    names = {a.id: a.name for a in accounts if a.id in allowed}
    codes = {a.id: a.currency for a in accounts if a.id in allowed}
    categories = db.scalars(
        select(m.Category).where(m.Category.household_id == hid)
    ).all()
    category_names = {c.id: c.name for c in categories}
    if kind == "accounts":
        return [
            {
                "name": a.name,
                "account_type": a.account_type,
                "currency": a.currency,
                "opening_balance": str(a.opening_balance),
                "opening_date": a.opening_date.isoformat(),
                "is_archived": str(a.is_archived).lower(),
                "source_id": str(a.id),
            }
            for a in accounts
            if a.id in allowed
        ]
    if kind == "categories":
        return [
            {
                "kind": c.kind,
                "name": c.name,
                "is_archived": str(c.is_archived).lower(),
                "source_id": str(c.id),
            }
            for c in categories
        ]
    if kind == "transactions":
        if not allowed:
            return []
        records = db.scalars(
            select(m.Transaction)
            .where(
                m.Transaction.household_id == hid,
                m.Transaction.account_id.in_(allowed),
                m.Transaction.deleted_at.is_(None),
            )
            .order_by(m.Transaction.transaction_date, m.Transaction.id)
        ).all()
        return [
            {
                "account_name": names[t.account_id],
                "account_source_id": str(t.account_id),
                "currency": codes[t.account_id],
                "category_name": category_names[t.category_id],
                "kind": t.kind,
                "amount": str(t.amount),
                "transaction_date": t.transaction_date.isoformat(),
                "description": t.description,
                "source_id": str(t.id),
            }
            for t in records
        ]
    if kind == "transfers":
        if not allowed:
            return []
        records = db.scalars(
            select(m.AccountTransfer)
            .where(
                m.AccountTransfer.household_id == hid,
                m.AccountTransfer.source_account_id.in_(allowed),
                m.AccountTransfer.destination_account_id.in_(allowed),
            )
            .order_by(m.AccountTransfer.transfer_date, m.AccountTransfer.id)
        ).all()
        return [
            {
                "source_account_name": names[t.source_account_id],
                "source_account_id": str(t.source_account_id),
                "destination_account_name": names[t.destination_account_id],
                "destination_account_id": str(t.destination_account_id),
                "currency": t.currency,
                "amount": str(t.amount),
                "transfer_date": t.transfer_date.isoformat(),
                "note": t.note or "",
                "source_id": str(t.id),
            }
            for t in records
        ]
    if kind == "bills":
        if not allowed:
            return []
        records = db.scalars(
            select(m.Bill)
            .where(m.Bill.household_id == hid, m.Bill.account_id.in_(allowed))
            .order_by(m.Bill.due_date, m.Bill.id)
        ).all()
        return [
            {
                "account_name": names[b.account_id],
                "account_source_id": str(b.account_id),
                "currency": b.currency,
                "title": b.title,
                "amount": str(b.amount),
                "due_date": b.due_date.isoformat(),
                "status": b.status,
                "paid_on": b.paid_on.isoformat() if b.paid_on else "",
                "remind_days": str(b.remind_days),
                "notes": b.notes or "",
                "source_id": str(b.id),
            }
            for b in records
        ]
    if kind in ("debts", "debt_installments", "debt_payments"):
        debts = db.scalars(
            select(m.Debt)
            .where(m.Debt.household_id == hid)
            .order_by(m.Debt.first_due_date, m.Debt.id)
        ).all()
        if kind == "debts":
            return [
                {
                    "title": d.title,
                    "counterparty": d.counterparty,
                    "direction": d.direction,
                    "principal": str(d.principal),
                    "first_due_date": d.first_due_date.isoformat(),
                    "installment_count": str(d.installment_count),
                    "note": d.note or "",
                    "is_archived": str(d.is_archived).lower(),
                    "source_id": str(d.id),
                }
                for d in debts
            ]
        by_id = {d.id: d for d in debts}
        if not by_id:
            return []
        if kind == "debt_installments":
            items = db.scalars(
                select(m.DebtInstallment)
                .where(
                    m.DebtInstallment.household_id == hid,
                    m.DebtInstallment.debt_id.in_(by_id),
                )
                .order_by(
                    m.DebtInstallment.debt_id, m.DebtInstallment.sequence_no
                )
            ).all()
            return [
                {
                    "debt_title": by_id[i.debt_id].title,
                    "counterparty": by_id[i.debt_id].counterparty,
                    "direction": by_id[i.debt_id].direction,
                    "first_due_date": by_id[
                        i.debt_id
                    ].first_due_date.isoformat(),
                    "debt_source_id": str(i.debt_id),
                    "sequence_no": str(i.sequence_no),
                    "due_date": i.due_date.isoformat(),
                    "amount": str(i.amount),
                }
                for i in items
            ]
        items = db.scalars(
            select(m.DebtPayment)
            .where(
                m.DebtPayment.household_id == hid,
                m.DebtPayment.debt_id.in_(by_id),
            )
            .order_by(
                m.DebtPayment.debt_id, m.DebtPayment.paid_on, m.DebtPayment.id
            )
        ).all()
        return [
            {
                "debt_title": by_id[p.debt_id].title,
                "counterparty": by_id[p.debt_id].counterparty,
                "direction": by_id[p.debt_id].direction,
                "first_due_date": by_id[p.debt_id].first_due_date.isoformat(),
                "debt_source_id": str(p.debt_id),
                "amount": str(p.amount),
                "paid_on": p.paid_on.isoformat(),
                "note": p.note or "",
                "voided": str(p.voided_at is not None).lower(),
                "source_id": str(p.id),
            }
            for p in items
        ]
    if kind != "budgets":
        raise ValueError("نوع CSV غير معروف.")
    blocked = blocked_budget_currencies(db, member)
    active_codes = {
        a.currency for a in accounts if a.id in allowed and not a.is_archived
    }
    budgets = db.scalars(
        select(m.MonthlyCategoryBudget)
        .where(m.MonthlyCategoryBudget.household_id == hid)
        .order_by(m.MonthlyCategoryBudget.year, m.MonthlyCategoryBudget.month)
    ).all()
    return [
        {
            "category_name": category_names[b.category_id],
            "year": str(b.year),
            "month": str(b.month),
            "currency": b.currency,
            "amount": str(b.amount),
            "alert_threshold_percent": str(b.alert_threshold_percent),
        }
        for b in budgets
        if b.currency in active_codes and b.currency not in blocked
    ]


def import_rows(
    db, user, member, kind: str, rows: list[dict[str, str]], ledger: LedgerState
) -> tuple[int, int]:
    hid = member.household_id
    db.scalar(
        select(m.Household).where(m.Household.id == hid).with_for_update()
    )
    if kind in (
        "transactions",
        "transfers",
        "bills",
        "debts",
        "debt_installments",
        "debt_payments",
    ):
        require_permission(member, "can_add_transactions")
    if kind in (
        "transfers",
        "bills",
        "debts",
        "debt_installments",
        "debt_payments",
    ):
        return import_financial_rows(db, user, member, kind, rows)
    if kind == "budgets":
        require_permission(member, "can_edit_budgets")
    accounts = db.scalars(
        select(m.FinancialAccount).where(m.FinancialAccount.household_id == hid)
    ).all()
    visible = visible_account_ids(db, member, accounts)
    account_map = {
        (a.name.casefold(), a.currency): a for a in accounts if a.id in visible
    }
    all_account_ids = {a.id: a for a in accounts}
    categories = db.scalars(
        select(m.Category).where(m.Category.household_id == hid)
    ).all()
    category_map = {(c.kind, c.name.casefold()): c for c in categories}
    category_ids = {c.id: c for c in categories}
    category_keys = {(c.kind, c.name.casefold()) for c in categories}
    hidden_keys = {
        (a.name.casefold(), a.currency) for a in accounts if a.id not in visible
    }
    budgets = (
        db.scalars(
            select(m.MonthlyCategoryBudget).where(
                m.MonthlyCategoryBudget.household_id == hid
            )
        ).all()
        if kind == "budgets"
        else []
    )
    budget_keys = {
        (b.category_id, b.year, b.month, b.currency) for b in budgets
    }
    blocked = (
        blocked_budget_currencies(db, member) if kind == "budgets" else set()
    )
    transactions = (
        db.scalars(
            select(m.Transaction).where(
                m.Transaction.household_id == hid,
                m.Transaction.account_id.in_(visible),
                m.Transaction.deleted_at.is_(None),
            )
        ).all()
        if kind == "transactions" and visible
        else []
    )
    transaction_ids = {t.id: t for t in transactions}
    all_transaction_ids = (
        {
            t.id: t
            for t in db.scalars(
                select(m.Transaction).where(m.Transaction.household_id == hid)
            ).all()
        }
        if kind == "transactions" and visible
        else {}
    )
    fingerprints = {
        transaction_key(
            t.account_id,
            t.category_id,
            t.kind,
            t.amount,
            t.transaction_date,
            t.description,
        )
        for t in transactions
    }
    added = skipped = 0
    for row in rows:
        try:
            validate_row(kind, row)
            if kind == "accounts":
                key = (row["name"].casefold(), row["currency"])
                sid = source_id(row)
                target = tenant_id(sid, hid, all_account_ids)
                identified = all_account_ids.get(target)
                matching = [
                    a
                    for a in accounts
                    if (a.name.casefold(), a.currency) == key
                ]
                if key in hidden_keys or (
                    identified and identified.id not in visible
                ):
                    raise ValueError(
                        "تعذر استيراد الحساب؛ راجع بيانات الحسابات المتاحة."
                    )
                if identified:
                    if (
                        identified.name.casefold(),
                        identified.currency,
                    ) != key or (
                        identified.account_type != row["account_type"]
                        or identified.opening_balance
                        != money(row["opening_balance"], False)
                        or identified.opening_date != day(row["opening_date"])
                        or identified.is_archived != flag(row["is_archived"])
                    ):
                        raise ValueError(
                            "تعذر استيراد الحساب؛ راجع بيانات الحسابات المتاحة."
                        )
                    skipped += 1
                    continue
                if matching:
                    if sid or len(matching) != 1:
                        raise ValueError(
                            "تعذر استيراد الحساب؛ راجع بيانات الحسابات المتاحة."
                        )
                    skipped += 1
                    continue
                if member.role != "owner":
                    raise ValueError(
                        "تعذر استيراد الحساب؛ راجع بيانات الحسابات المتاحة."
                    )
                new_account = m.FinancialAccount(
                    household_id=hid,
                    created_by_user_id=user.id,
                    name=row["name"],
                    account_type=row["account_type"],
                    currency=row["currency"],
                    opening_balance=money(row["opening_balance"], False),
                    opening_date=day(row["opening_date"]),
                    is_archived=flag(row.get("is_archived", "false")),
                    **({"id": target} if target else {}),
                )
                db.add(new_account)
                accounts.append(new_account)
                if target:
                    all_account_ids[target] = new_account
            elif kind == "categories":
                key = (row["kind"], row["name"].casefold())
                sid = source_id(row)
                target = tenant_id(sid, hid, category_ids)
                identified = category_ids.get(target)
                if identified:
                    if (
                        identified.kind,
                        identified.name.casefold(),
                    ) != key or identified.is_archived != flag(
                        row["is_archived"]
                    ):
                        raise ValueError("معرّف المصدر لا يطابق بيانات الفئة.")
                    skipped += 1
                    continue
                if key in category_keys:
                    if sid:
                        raise ValueError("معرّف المصدر لا يطابق فئة موجودة.")
                    skipped += 1
                    continue
                category = m.Category(
                    household_id=hid,
                    kind=row["kind"],
                    name=row["name"],
                    is_archived=flag(row.get("is_archived", "false")),
                    **({"id": target} if target else {}),
                )
                db.add(category)
                if target:
                    category_ids[target] = category
                category_keys.add(key)
            elif kind == "transactions":
                account = resolve_account(
                    accounts,
                    visible,
                    row["account_name"],
                    row["currency"],
                    sid=source_id(row, "account_source_id"),
                    household=hid,
                )
                category = category_map.get(
                    (row["kind"], row["category_name"].casefold())
                )
                if category is None:
                    raise ValueError(
                        "الفئة غير موجودة؛ استورد الفئات أولًا وتحقق من الاسم والنوع."
                    )
                when = day(row["transaction_date"])
                if when < account.opening_date:
                    raise ValueError("تاريخ المعاملة يسبق افتتاح الحساب.")
                key = transaction_key(
                    account.id,
                    category.id,
                    row["kind"],
                    money(row["amount"]),
                    when,
                    row["description"],
                )
                sid = source_id(row)
                target = tenant_id(sid, hid, all_transaction_ids)
                if (
                    target in all_transaction_ids
                    and target not in transaction_ids
                ):
                    raise ValueError(
                        "المعاملة غير متاحة أو معرّف المصدر غير مطابق."
                    )
                if target in transaction_ids:
                    existing = transaction_ids[target]
                    if (
                        transaction_key(
                            existing.account_id,
                            existing.category_id,
                            existing.kind,
                            existing.amount,
                            existing.transaction_date,
                            existing.description,
                        )
                        != key
                    ):
                        raise ValueError(
                            "معرّف المعاملة موجود ببيانات مختلفة؛ لن نعدل السجل التاريخي."
                        )
                    skipped += 1
                    continue
                if not sid and key in fingerprints:
                    skipped += 1
                    continue
                tx = m.Transaction(
                    household_id=hid,
                    created_by_user_id=user.id,
                    account_id=account.id,
                    category_id=category.id,
                    kind=row["kind"],
                    amount=key[3],
                    transaction_date=when,
                    description=row["description"],
                    **({"id": target} if target else {}),
                )
                db.add(tx)
                db.flush()
                ledger._append_transaction_event(db, tx, "created", user.id)
                fingerprints.add(key)
                if target:
                    transaction_ids[target] = tx
                    all_transaction_ids[target] = tx
            else:
                category = category_map.get(
                    ("expense", row["category_name"].casefold())
                )
                if category is None:
                    raise ValueError(
                        "فئة المصروف غير موجودة أو مؤرشفة؛ استورد الفئات أولًا."
                    )
                code = row["currency"]
                key = (category.id, int(row["year"]), int(row["month"]), code)
                if key in budget_keys:
                    skipped += 1
                    continue
                if category.is_archived:
                    raise ValueError("لا يمكن إنشاء ميزانية جديدة لفئة مؤرشفة.")
                if code in blocked or code not in {
                    a.currency
                    for a in account_map.values()
                    if not a.is_archived
                }:
                    raise ValueError(
                        "عملة الميزانية غير متاحة؛ راجع الحسابات النشطة المتاحة بهذه العملة."
                    )
                db.add(
                    m.MonthlyCategoryBudget(
                        household_id=hid,
                        created_by_user_id=user.id,
                        category_id=category.id,
                        category_kind="expense",
                        year=key[1],
                        month=key[2],
                        currency=code,
                        amount=money(row["amount"], False),
                        alert_threshold_percent=int(
                            row["alert_threshold_percent"]
                        ),
                    )
                )
                budget_keys.add(key)
            added += 1
        except ValueError as e:
            raise ValueError(f"الصف {row['_line']}: {e}") from e
    if added and kind in ("transactions", "budgets"):
        db.flush()
        ledger._budget_alerts(db, hid)
    db.commit()
    return added, skipped


def resolve_account(
    accounts,
    visible,
    name: str,
    code: str,
    *,
    active: bool = False,
    sid: UUID | None = None,
    household: UUID | None = None,
):
    ids = {a.id: a for a in accounts}
    target = tenant_id(sid, household, ids) if sid and household else sid
    matches = [
        a
        for a in accounts
        if a.id in visible
        and a.name.casefold() == name.casefold()
        and a.currency == code
        and (not active or not a.is_archived)
        and (target is None or a.id == target)
    ]
    if len(matches) != 1:
        raise ValueError(
            "الحساب غير متاح أو الاسم والعملة غير فريدين؛ استورد الحسابات أولًا وراجع الحسابات المتاحة."
        )
    return matches[0]


def resolve_debt(debts, row: dict[str, str], household: UUID | None = None):
    sid = source_id(row, "debt_source_id")
    key = debt_identity(row, "debt_")
    ids = {d.id: d for d in debts}
    target = tenant_id(sid, household, ids) if sid and household else sid
    by_id = [ids[target]] if target in ids else []
    if by_id:
        if (
            debt_identity(
                {
                    "title": by_id[0].title,
                    "counterparty": by_id[0].counterparty,
                    "direction": by_id[0].direction,
                    "first_due_date": by_id[0].first_due_date.isoformat(),
                }
            )
            != key
        ):
            raise ValueError("معرّف الدين لا يطابق بياناته؛ لن نربطه بسجل آخر.")
        return by_id[0]
    if sid:
        raise ValueError(
            "معرّف الدين غير موجود أو لا يطابق بياناته؛ استورد الديون أولًا."
        )
    matches = [
        d
        for d in debts
        if (
            d.title.casefold(),
            d.counterparty.casefold(),
            d.direction,
            d.first_due_date,
        )
        == key
    ]
    if len(matches) != 1:
        raise ValueError(
            "الدين غير موجود أو مطابق لأكثر من سجل؛ استورد الديون أولًا واستخدم معرّف المصدر لتمييزها."
        )
    return matches[0]


def import_financial_rows(
    db, user, member, kind: str, rows: list[dict[str, str]]
) -> tuple[int, int]:
    from app.states.debts import schedule

    hid = member.household_id
    accounts = db.scalars(
        select(m.FinancialAccount).where(m.FinancialAccount.household_id == hid)
    ).all()
    visible = visible_account_ids(db, member, accounts)
    debts = (
        db.scalars(select(m.Debt).where(m.Debt.household_id == hid)).all()
        if kind in ("debts", "debt_installments", "debt_payments")
        else []
    )
    model = {
        "transfers": m.AccountTransfer,
        "bills": m.Bill,
        "debt_installments": m.DebtInstallment,
        "debt_payments": m.DebtPayment,
    }.get(kind)
    records = (
        db.scalars(select(model).where(model.household_id == hid)).all()
        if model
        else []
    )
    by_id = {r.id: r for r in (debts if kind == "debts" else records)}
    seen = set()
    paid = {}
    if kind in ("debts", "debt_payments"):
        payments = (
            records
            if kind == "debt_payments"
            else db.scalars(
                select(m.DebtPayment).where(m.DebtPayment.household_id == hid)
            ).all()
        )
        for p in payments:
            if p.voided_at is None:
                paid[p.debt_id] = paid.get(p.debt_id, Decimal(0)) + p.amount
    added = skipped = 0
    for row in rows:
        try:
            validate_row(kind, row)
            sid = source_id(row) if kind != "debt_installments" else None
            target = tenant_id(sid, hid, by_id)
            if kind == "transfers":
                src = resolve_account(
                    accounts,
                    visible,
                    row["source_account_name"],
                    row["currency"],
                    active=True,
                    sid=source_id(row, "source_account_id"),
                    household=hid,
                )
                dst = resolve_account(
                    accounts,
                    visible,
                    row["destination_account_name"],
                    row["currency"],
                    active=True,
                    sid=source_id(row, "destination_account_id"),
                    household=hid,
                )
                when = day(row["transfer_date"])
                if src.id == dst.id or when < max(
                    src.opening_date, dst.opening_date
                ):
                    raise ValueError(
                        "حسابا التحويل يجب أن يختلفا وأن يقع التاريخ بعد افتتاح كليهما."
                    )
                key = (
                    src.id,
                    dst.id,
                    row["currency"],
                    money(row["amount"]),
                    when,
                    row["note"],
                )
                fingerprint = lambda t: (
                    t.source_account_id,
                    t.destination_account_id,
                    t.currency,
                    t.amount,
                    t.transfer_date,
                    t.note or "",
                )
                if target in by_id:
                    if fingerprint(by_id[target]) != key:
                        raise ValueError("التحويل الموجود بهذا المعرّف مختلف.")
                    skipped += 1
                    continue
                if not sid and (
                    key in seen or any(fingerprint(t) == key for t in records)
                ):
                    skipped += 1
                    continue
                obj = m.AccountTransfer(
                    household_id=hid,
                    created_by_user_id=user.id,
                    source_account_id=src.id,
                    destination_account_id=dst.id,
                    currency=row["currency"],
                    amount=key[3],
                    transfer_date=when,
                    note=row["note"] or None,
                    **({"id": target} if target else {}),
                )
            elif kind == "bills":
                account = resolve_account(
                    accounts,
                    visible,
                    row["account_name"],
                    row["currency"],
                    sid=source_id(row, "account_source_id"),
                    household=hid,
                )
                key = (
                    account.id,
                    row["title"],
                    money(row["amount"]),
                    date.fromisoformat(row["due_date"]),
                    row["status"],
                    date.fromisoformat(row["paid_on"])
                    if row["paid_on"]
                    else None,
                    int(row["remind_days"]),
                    row["notes"],
                )
                fingerprint = lambda b: (
                    b.account_id,
                    b.title,
                    b.amount,
                    b.due_date,
                    b.status,
                    b.paid_on,
                    b.remind_days,
                    b.notes or "",
                )
                if target in by_id:
                    if fingerprint(by_id[target]) != key:
                        raise ValueError(
                            "الفاتورة بهذا المعرّف مختلفة؛ لا تُعدّل الفواتير عند الاستيراد."
                        )
                    skipped += 1
                    continue
                if not sid and (
                    key in seen or any(fingerprint(b) == key for b in records)
                ):
                    skipped += 1
                    continue
                obj = m.Bill(
                    household_id=hid,
                    created_by_user_id=user.id,
                    account_id=account.id,
                    title=row["title"],
                    amount=key[2],
                    currency=account.currency,
                    due_date=key[3],
                    status=row["status"],
                    paid_on=key[5],
                    remind_days=key[6],
                    notes=row["notes"] or None,
                    **({"id": target} if target else {}),
                )
            elif kind == "debts":
                key = debt_identity(row)
                candidates = [
                    d
                    for d in debts
                    if (
                        d.title.casefold(),
                        d.counterparty.casefold(),
                        d.direction,
                        d.first_due_date,
                    )
                    == key
                ]
                debt = by_id.get(target) if target else None
                if sid and debt is None and candidates:
                    raise ValueError("معرّف المصدر لا يطابق دينًا موجودًا.")
                if debt is None and len(candidates) > 1 and not sid:
                    raise ValueError(
                        "عدة ديون تحمل التعريف نفسه؛ استخدم معرّف المصدر دون تخمين."
                    )
                if debt is None and candidates and not sid:
                    debt = candidates[0]
                if debt is not None:
                    if (
                        debt_identity(
                            {
                                "title": debt.title,
                                "counterparty": debt.counterparty,
                                "direction": debt.direction,
                                "first_due_date": debt.first_due_date.isoformat(),
                            }
                        )
                        != key
                        or debt.principal != money(row["principal"])
                        or debt.installment_count
                        != int(row["installment_count"])
                        or (debt.note or "") != row["note"]
                    ):
                        raise ValueError(
                            "الدين الموجود مختلف؛ لا يمكن تعديل الشروط المالية أو التاريخ بالاستيراد."
                        )
                    if flag(row["is_archived"]) and not debt.is_archived:
                        if paid.get(debt.id, Decimal(0)) != debt.principal:
                            skipped += 1
                            continue
                        debt.is_archived = True
                        added += 1
                    else:
                        skipped += 1
                    continue
                obj = m.Debt(
                    household_id=hid,
                    created_by_user_id=user.id,
                    title=row["title"],
                    counterparty=row["counterparty"],
                    direction=row["direction"],
                    principal=money(row["principal"]),
                    first_due_date=date.fromisoformat(row["first_due_date"]),
                    installment_count=int(row["installment_count"]),
                    note=row["note"] or None,
                    is_archived=False,
                    **({"id": target} if target else {}),
                )
                db.add(obj)
                db.flush()
                for index, (due, amount) in enumerate(
                    schedule(
                        obj.principal, obj.first_due_date, obj.installment_count
                    ),
                    1,
                ):
                    db.add(
                        m.DebtInstallment(
                            household_id=hid,
                            debt_id=obj.id,
                            sequence_no=index,
                            due_date=due,
                            amount=amount,
                        )
                    )
                debts.append(obj)
                by_id[obj.id] = obj
                added += 1
                continue
            elif kind == "debt_installments":
                debt = resolve_debt(debts, row, hid)
                entries = schedule(
                    debt.principal, debt.first_due_date, debt.installment_count
                )
                seq = int(row["sequence_no"])
                if seq > len(entries) or entries[seq - 1] != (
                    date.fromisoformat(row["due_date"]),
                    money(row["amount"]),
                ):
                    raise ValueError(
                        "القسط لا يطابق الجدول المولّد من أصل الدين."
                    )
                if not any(
                    i.debt_id == debt.id
                    and i.sequence_no == seq
                    and i.due_date == entries[seq - 1][0]
                    and i.amount == entries[seq - 1][1]
                    for i in records
                ):
                    raise ValueError(
                        "القسط المولّد غير موجود أو تغير؛ راجع الدين أولًا."
                    )
                skipped += 1
                continue
            else:
                debt = resolve_debt(debts, row, hid)
                key = (
                    debt.id,
                    money(row["amount"]),
                    day(row["paid_on"]),
                    row["note"],
                    flag(row["voided"]),
                )
                fingerprint = lambda p: (
                    p.debt_id,
                    p.amount,
                    p.paid_on,
                    p.note or "",
                    p.voided_at is not None,
                )
                if target in by_id:
                    if fingerprint(by_id[target]) != key:
                        raise ValueError(
                            "الدفعة بهذا المعرّف مختلفة؛ لا يمكن استبدال سجل الدفعات."
                        )
                    skipped += 1
                    continue
                if not sid and (
                    key in seen or any(fingerprint(p) == key for p in records)
                ):
                    skipped += 1
                    continue
                if (
                    not key[4]
                    and paid.get(debt.id, Decimal(0)) + key[1] > debt.principal
                ):
                    raise ValueError(
                        "مجموع الدفعات غير الملغاة يتجاوز أصل الدين."
                    )
                obj = m.DebtPayment(
                    household_id=hid,
                    debt_id=debt.id,
                    created_by_user_id=user.id,
                    amount=key[1],
                    paid_on=key[2],
                    note=row["note"] or None,
                    voided_at=datetime.now(timezone.utc) if key[4] else None,
                    **({"id": target} if target else {}),
                )
                if not key[4]:
                    paid[debt.id] = paid.get(debt.id, Decimal(0)) + key[1]
            db.add(obj)
            if target:
                by_id[target] = obj
            seen.add(key)
            added += 1
        except ValueError as e:
            raise ValueError(f"الصف {row['_line']}: {e}") from e
    db.commit()
    return added, skipped


class CsvTransferState(rx.State):
    entity: str = "accounts"
    pending_csv: str = ""
    pending_household: str = ""
    preview: list[str] = []
    row_count: int = 0
    error: str = ""
    message: str = ""
    busy: bool = False

    def _clear(self):
        self.pending_csv = ""
        self.pending_household = ""
        self.preview = []
        self.row_count = 0
        self.error = ""
        self.message = ""

    @rx.event
    def load(self):
        self._clear()

    @rx.event
    def choose(self, value: str):
        if value in HEADERS:
            self.entity = value
            self._clear()

    def _cancel(self):
        self.pending_csv = ""
        self.pending_household = ""
        self.preview = []
        self.row_count = 0
        self.error = ""

    @rx.event
    def cancel_preview(self):
        self._cancel()

    @rx.event
    def template(self):
        return rx.download(
            data=csv_bytes(
                self.entity,
                [dict(zip(HEADERS[self.entity], SAMPLES[self.entity]))],
            ),
            filename=f"money-harmony-{self.entity}-template.csv",
        )

    @rx.event
    async def export_csv(self):
        try:
            auth = await self.get_state(AuthState)
            kind = self.entity
            async with rx.asession() as db:

                def export_sync(sync_db):
                    _, member = auth._household(sync_db)
                    if kind == "budgets":
                        require_permission(member, "can_edit_budgets")
                    return csv_bytes(kind, transfer_rows(sync_db, member, kind))

                output = await db.run_sync(export_sync)
            return rx.download(
                data=output, filename=f"money-harmony-{kind}.csv"
            )
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("csv_transfer.export_csv", e)
            self.error = "تعذر تصدير البيانات. حاول ثانية."

    @rx.event
    async def upload_csv(self, files: list[rx.UploadFile]):
        self._cancel()
        self.message = ""
        try:
            if len(files) != 1 or not files[0].name.lower().endswith(".csv"):
                raise ValueError("اختر ملف CSV واحدًا فقط.")
            data = await files[0].read(LIMIT_BYTES + 1)
            kind = self.entity
            rows = parse_csv(kind, data)
            for row in rows:
                try:
                    validate_row(kind, row)
                except ValueError as e:
                    raise ValueError(f"الصف {row['_line']}: {e}") from e
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def check(sync_db):
                    _, member = auth._household(sync_db)
                    if kind in (
                        "transactions",
                        "transfers",
                        "bills",
                        "debts",
                        "debt_installments",
                        "debt_payments",
                    ):
                        require_permission(member, "can_add_transactions")
                    if kind == "budgets":
                        require_permission(member, "can_edit_budgets")
                    return str(member.household_id)

                hid = await db.run_sync(check)
            self.pending_household = hid
            self.pending_csv = data.decode("utf-8-sig")
            self.preview = [
                f"الصف {r['_line']}: {' · '.join(r[k][:120] for k in HEADERS[kind])}"
                for r in rows[:5]
            ]
            self.row_count = len(rows)
            self.message = "راجع العينة ثم أكّد؛ لن يُحفظ أي صف قبل التأكيد."
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("csv_transfer.upload_csv", e)
            self.error = "تعذرت قراءة الملف. تأكد من ترميز UTF-8 وصيغة CSV."

    @rx.event
    async def confirm(self):
        if not self.pending_csv or self.busy:
            return
        self.busy = True
        try:
            kind = self.entity
            rows = parse_csv(kind, self.pending_csv.encode("utf-8"))
            auth = await self.get_state(AuthState)
            ledger = await self.get_state(LedgerState)
            async with rx.asession() as db:

                def save_sync(sync_db):
                    user, member = auth._household(sync_db)
                    if str(member.household_id) != self.pending_household:
                        raise ValueError(
                            "تغيرت الأسرة النشطة؛ أعد رفع الملف للأسرة الحالية."
                        )
                    return import_rows(
                        sync_db, user, member, kind, rows, ledger
                    )

                added, skipped = await db.run_sync(save_sync)
            self._cancel()
            self.message = f"اكتمل الاستيراد: أُضيف {added}، وتُخطي {skipped} مكرر أو قسط مطابق/أرشفة مؤجلة."
            yield LedgerState.load
        except PermissionError:
            logging.exception("Unexpected error")
            yield rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("csv_transfer.confirm", e)
            self.error = "لم يُحفظ أي صف. راجع الملف وحاول ثانية."
        finally:
            self.busy = False
