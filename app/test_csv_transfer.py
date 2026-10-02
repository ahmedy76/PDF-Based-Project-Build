import reflex as rx

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4, uuid5

from app.states.csv_transfer import (
    HEADERS,
    SAMPLES,
    import_financial_rows,
    csv_bytes,
    import_rows,
    money,
    parse_csv,
    safe_cell,
    tenant_id,
    transfer_rows,
    validate_row,
)


class CsvTransferTests(unittest.TestCase):
    def test_templates_match_each_entity(self):
        self.assertEqual(set(HEADERS), set(SAMPLES))
        for kind in HEADERS:
            self.assertEqual(len(HEADERS[kind]), len(SAMPLES[kind]))
            row = dict(zip(HEADERS[kind], SAMPLES[kind]))
            validate_row(kind, row)

    def test_budget_zero_and_bill_status(self):
        row = dict(zip(HEADERS["budgets"], SAMPLES["budgets"]))
        row["amount"] = "0"
        validate_row("budgets", row)
        bill = dict(zip(HEADERS["bills"], SAMPLES["bills"]))
        bill["status"] = "paid"
        with self.assertRaises(ValueError):
            validate_row("bills", bill)
        bill["paid_on"] = "2025-01-10"
        validate_row("bills", bill)
        bill["remind_days"] = "366"
        with self.assertRaises(ValueError):
            validate_row("bills", bill)

    def test_headers_roundtrip_and_bom(self):
        for kind, header in HEADERS.items():
            row = {key: "نص عربي" for key in header}
            data = csv_bytes(kind, [row])
            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(
                tuple(parse_csv(kind, data)[0][key] for key in header),
                tuple(row.values()),
            )
        with self.assertRaisesRegex(ValueError, "عناوين"):
            parse_csv("categories", b"name,kind\nfoo,expense")

    def test_row_diagnostics_and_validation(self):
        with self.assertRaisesRegex(ValueError, "الصف 2"):
            parse_csv(
                "categories",
                (",".join(HEADERS["categories"]) + "\nexpense").encode(),
            )
        for value in ("NaN", "Infinity", "0", "-1", "1.00001"):
            with self.assertRaises(ValueError):
                money(value)
        with self.assertRaises(ValueError):
            validate_row(
                "transactions",
                {
                    "account_name": "X",
                    "category_name": "Y",
                    "kind": "other",
                    "description": "",
                    "currency": "SAR",
                    "amount": "1",
                    "transaction_date": "2020-01-01",
                },
            )

    def test_injection_safe_roundtrip(self):
        for payload in ("=SUM(1,2)", " +cmd", "@foo", "-cmd", "\t=cmd"):
            self.assertTrue(safe_cell(payload).startswith("'"))
            data = csv_bytes(
                "categories", [{"kind": "expense", "name": payload}]
            )
            self.assertEqual(
                parse_csv("categories", data)[0]["name"], payload.strip()
            )

    def test_source_references_are_tenant_local_and_repeatable(self):
        first, second, source = uuid4(), uuid4(), uuid4()
        self.assertEqual(tenant_id(source, first, {}), uuid5(first, source.hex))
        self.assertNotEqual(tenant_id(source, first, {}), source)
        self.assertNotEqual(
            tenant_id(source, first, {}), tenant_id(source, second, {})
        )
        self.assertEqual(tenant_id(source, first, {source: object()}), source)

    def test_hidden_account_import_is_generic_and_cannot_duplicate(self):
        hid, uid = uuid4(), uuid4()
        hidden = SimpleNamespace(id=uuid4(), name="خاص", currency="SAR")
        row = dict(zip(HEADERS["accounts"], SAMPLES["accounts"]))
        row.update(_line="2", name="خاص", source_id="")
        db = Mock()
        db.scalars.return_value.all.side_effect = [[hidden], []]
        with patch(
            "app.states.csv_transfer.visible_account_ids", return_value=set()
        ):
            with self.assertRaises(ValueError) as error:
                import_rows(
                    db,
                    SimpleNamespace(id=uid),
                    SimpleNamespace(
                        household_id=hid, user_id=uid, role="partner"
                    ),
                    "accounts",
                    [row],
                    Mock(),
                )
        self.assertNotIn("محجوب", str(error.exception))
        absent_db = Mock()
        absent_db.scalars.return_value.all.side_effect = [[], []]
        with patch(
            "app.states.csv_transfer.visible_account_ids", return_value=set()
        ):
            with self.assertRaises(ValueError) as absent_error:
                import_rows(
                    absent_db,
                    SimpleNamespace(id=uid),
                    SimpleNamespace(
                        household_id=hid, user_id=uid, role="partner"
                    ),
                    "accounts",
                    [row],
                    Mock(),
                )
        self.assertEqual(str(error.exception), str(absent_error.exception))
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_reimport_category_skips_duplicate(self):
        hid, uid = uuid4(), uuid4()
        member = SimpleNamespace(household_id=hid, role="owner", user_id=uid)
        user = SimpleNamespace(id=uid)
        db = Mock()
        db.scalars.return_value.all.return_value = []
        rows = [
            {"_line": "2", "kind": "expense", "name": "طعام"},
            {"_line": "3", "kind": "expense", "name": "طعام"},
        ]
        self.assertEqual(
            import_rows(db, user, member, "categories", rows, Mock()), (1, 1)
        )
        self.assertEqual(db.add.call_count, 1)
        db.commit.assert_called_once()

    def test_import_transaction_writes_audit_and_deduplicates(self):
        hid, uid = uuid4(), uuid4()
        account = SimpleNamespace(
            id=uuid4(),
            name="محفظة",
            currency="SAR",
            is_archived=False,
            opening_date=date(2020, 1, 1),
        )
        category = SimpleNamespace(
            id=uuid4(), kind="expense", name="طعام", is_archived=False
        )
        member = SimpleNamespace(household_id=hid, user_id=uid, role="owner")
        db = Mock()
        db.scalars.return_value.all.side_effect = [
            [account],
            [category],
            [],
            [],
        ]
        ledger = Mock()
        row = {
            "_line": "2",
            "account_name": "محفظة",
            "currency": "SAR",
            "category_name": "طعام",
            "kind": "expense",
            "amount": "12.5000",
            "transaction_date": "2020-01-02",
            "description": "شراء",
        }
        with patch(
            "app.states.csv_transfer.visible_account_ids",
            return_value={account.id},
        ):
            self.assertEqual(
                import_rows(
                    db,
                    SimpleNamespace(id=uid),
                    member,
                    "transactions",
                    [row, row],
                    ledger,
                ),
                (1, 1),
            )
        ledger._append_transaction_event.assert_called_once()
        ledger._budget_alerts.assert_called_once()
        db.commit.assert_called_once()

    def test_distinct_source_ids_keep_identical_transactions_distinct(self):
        hid, uid = uuid4(), uuid4()
        account = SimpleNamespace(
            id=uuid4(),
            name="محفظة",
            currency="SAR",
            opening_date=date(2020, 1, 1),
        )
        category = SimpleNamespace(id=uuid4(), kind="expense", name="طعام")
        db = Mock()
        db.scalars.return_value.all.side_effect = [
            [account],
            [category],
            [],
            [],
        ]
        ledger = Mock()
        row = dict(zip(HEADERS["transactions"], SAMPLES["transactions"]))
        row.update(
            _line="2",
            account_name="محفظة",
            category_name="طعام",
            transaction_date="2020-01-02",
            source_id=str(uuid4()),
        )
        with patch(
            "app.states.csv_transfer.visible_account_ids",
            return_value={account.id},
        ):
            self.assertEqual(
                import_rows(
                    db,
                    SimpleNamespace(id=uid),
                    SimpleNamespace(
                        household_id=hid, user_id=uid, role="owner"
                    ),
                    "transactions",
                    [row, dict(row, source_id=str(uuid4()))],
                    ledger,
                ),
                (2, 0),
            )
        self.assertEqual(ledger._append_transaction_event.call_count, 2)
        self.assertNotEqual(
            db.add.call_args_list[0].args[0].id,
            db.add.call_args_list[1].args[0].id,
        )

    def test_missing_account_rolls_back_before_commit(self):
        hid, uid = uuid4(), uuid4()
        member = SimpleNamespace(household_id=hid, role="owner", user_id=uid)
        db = Mock()
        db.scalars.return_value.all.return_value = []
        row = {
            "_line": "2",
            "account_name": "مفقود",
            "currency": "SAR",
            "category_name": "طعام",
            "kind": "expense",
            "amount": "1",
            "transaction_date": "2020-01-01",
            "description": "",
        }
        with self.assertRaisesRegex(ValueError, "الصف 2.*استورد الحسابات"):
            import_rows(
                db,
                SimpleNamespace(id=uid),
                member,
                "transactions",
                [row],
                Mock(),
            )
        db.commit.assert_not_called()

    def test_failure_after_first_row_does_not_commit(self):
        hid, uid = uuid4(), uuid4()
        db = Mock()
        db.scalars.return_value.all.return_value = []
        rows = [
            {"_line": "2", "kind": "expense", "name": "طعام"},
            {"_line": "3", "kind": "wrong", "name": "غير صالح"},
        ]
        with self.assertRaisesRegex(ValueError, "الصف 3"):
            import_rows(
                db,
                SimpleNamespace(id=uid),
                SimpleNamespace(household_id=hid, role="owner", user_id=uid),
                "categories",
                rows,
                Mock(),
            )
        db.add.assert_called_once()
        db.commit.assert_not_called()

    def test_permission_before_import(self):
        uid, hid = uuid4(), uuid4()
        member = SimpleNamespace(
            household_id=hid,
            user_id=uid,
            role="partner",
            can_add_transactions=False,
        )
        with self.assertRaises(ValueError):
            import_rows(
                Mock(),
                SimpleNamespace(id=uid),
                member,
                "transactions",
                [],
                Mock(),
            )

    def financial_db(self, accounts=(), debts=(), records=()):
        db = Mock()
        db.scalars.return_value.all.side_effect = [
            list(accounts),
            list(debts),
            list(records),
        ]
        return db

    def test_source_account_reference_never_falls_back_by_name(self):
        hid, uid = uuid4(), uuid4()
        account = SimpleNamespace(
            id=uuid4(),
            name="بيت",
            currency="SAR",
            opening_date=date(2020, 1, 1),
            is_archived=False,
        )
        row = dict(zip(HEADERS["bills"], SAMPLES["bills"]))
        row.update(
            _line="2", account_name="بيت", account_source_id=str(uuid4())
        )
        db = self.financial_db([account], [], [])
        with patch(
            "app.states.csv_transfer.visible_account_ids",
            return_value={account.id},
        ):
            with self.assertRaisesRegex(ValueError, "الصف 2"):
                import_rows(
                    db,
                    SimpleNamespace(id=uid),
                    SimpleNamespace(
                        household_id=hid, user_id=uid, role="owner"
                    ),
                    "bills",
                    [row],
                    Mock(),
                )
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_bill_import_and_visibility(self):
        hid, uid = uuid4(), uuid4()
        account = SimpleNamespace(
            id=uuid4(),
            name="بيت",
            currency="SAR",
            is_archived=False,
            opening_date=date(2020, 1, 1),
        )
        member = SimpleNamespace(household_id=hid, user_id=uid, role="owner")
        row = dict(zip(HEADERS["bills"], SAMPLES["bills"]))
        row.update(_line="2", account_name="بيت", title="إنترنت", source_id="")
        db = self.financial_db([account], [], [])
        with patch(
            "app.states.csv_transfer.visible_account_ids",
            return_value={account.id},
        ):
            self.assertEqual(
                import_rows(
                    db,
                    SimpleNamespace(id=uid),
                    member,
                    "bills",
                    [row, row],
                    Mock(),
                ),
                (1, 1),
            )
        db.commit.assert_called_once()
        self.assertEqual(db.add.call_args.args[0].currency, "SAR")
        row["currency"] = "USD"
        db = self.financial_db([account], [], [])
        with (
            patch(
                "app.states.csv_transfer.visible_account_ids",
                return_value={account.id},
            ),
            self.assertRaisesRegex(ValueError, "الصف 2"),
        ):
            import_rows(
                db, SimpleNamespace(id=uid), member, "bills", [row], Mock()
            )
        db.commit.assert_not_called()

    def test_distinct_sourced_bills_are_not_collapsed(self):
        hid, uid = uuid4(), uuid4()
        account = SimpleNamespace(
            id=uuid4(),
            name="بيت",
            currency="SAR",
            opening_date=date(2020, 1, 1),
            is_archived=False,
        )
        row = dict(zip(HEADERS["bills"], SAMPLES["bills"]))
        row.update(_line="2", account_name="بيت", source_id=str(uuid4()))
        db = self.financial_db([account], [], [])
        with patch(
            "app.states.csv_transfer.visible_account_ids",
            return_value={account.id},
        ):
            self.assertEqual(
                import_rows(
                    db,
                    SimpleNamespace(id=uid),
                    SimpleNamespace(
                        household_id=hid, user_id=uid, role="owner"
                    ),
                    "bills",
                    [row, dict(row, source_id=str(uuid4()))],
                    Mock(),
                ),
                (2, 0),
            )
        self.assertEqual(db.add.call_count, 2)

    def test_schedule_verification_and_payment_limits(self):
        hid, uid = uuid4(), uuid4()
        member = SimpleNamespace(household_id=hid, user_id=uid, role="owner")
        debt = SimpleNamespace(
            id=uuid4(),
            title="قرض المنزل",
            counterparty="شركة التمويل",
            direction="payable",
            principal=Decimal("1200"),
            first_due_date=date(2025, 1, 10),
            installment_count=12,
            is_archived=False,
        )
        installment = SimpleNamespace(
            id=uuid4(),
            debt_id=debt.id,
            sequence_no=1,
            due_date=date(2025, 1, 10),
            amount=Decimal("100"),
        )
        row = dict(
            zip(HEADERS["debt_installments"], SAMPLES["debt_installments"])
        )
        row.update(_line="2", debt_source_id=str(debt.id))
        db = self.financial_db([], [debt], [installment])
        self.assertEqual(
            import_rows(
                db,
                SimpleNamespace(id=uid),
                member,
                "debt_installments",
                [row],
                Mock(),
            ),
            (0, 1),
        )
        row["amount"] = "99"
        db = self.financial_db([], [debt], [installment])
        with self.assertRaisesRegex(ValueError, "الصف 2"):
            import_rows(
                db,
                SimpleNamespace(id=uid),
                member,
                "debt_installments",
                [row],
                Mock(),
            )
        db.commit.assert_not_called()
        payment = dict(zip(HEADERS["debt_payments"], SAMPLES["debt_payments"]))
        payment.update(_line="3", debt_source_id=str(debt.id), amount="1201")
        db = self.financial_db([], [debt], [])
        with self.assertRaisesRegex(ValueError, "الصف 3"):
            import_rows(
                db,
                SimpleNamespace(id=uid),
                member,
                "debt_payments",
                [payment],
                Mock(),
            )
        db.commit.assert_not_called()
        payment.update(amount="1200", voided="true")
        db = self.financial_db([], [debt], [])
        self.assertEqual(
            import_rows(
                db,
                SimpleNamespace(id=uid),
                member,
                "debt_payments",
                [payment],
                Mock(),
            ),
            (1, 0),
        )
        self.assertIsNotNone(db.add.call_args.args[0].voided_at)

    def test_debt_import_generates_schedule_and_defers_archive(self):
        hid, uid = uuid4(), uuid4()
        member = SimpleNamespace(household_id=hid, user_id=uid, role="owner")
        row = dict(zip(HEADERS["debts"], SAMPLES["debts"]))
        row.update(_line="2", source_id=str(uuid4()), is_archived="true")
        db = Mock()
        db.scalars.return_value.all.side_effect = [[], [], []]
        result = import_rows(
            db, SimpleNamespace(id=uid), member, "debts", [row], Mock()
        )
        self.assertEqual(result, (1, 0))
        self.assertEqual(db.add.call_count, 13)
        self.assertFalse(db.add.call_args_list[0].args[0].is_archived)
        self.assertEqual(
            sum(
                (call.args[0].amount for call in db.add.call_args_list[1:]),
                Decimal(0),
            ),
            Decimal("1200"),
        )
        db.commit.assert_called_once()

    def test_export_bill_only_visible_including_closed(self):
        hid = uuid4()
        a = SimpleNamespace(
            id=uuid4(), name="تاريخي", currency="SAR", is_archived=True
        )
        b = SimpleNamespace(
            id=uuid4(), name="سري", currency="SAR", is_archived=False
        )
        bill = SimpleNamespace(
            id=uuid4(),
            account_id=a.id,
            title="فاتورة",
            currency="SAR",
            amount=Decimal("4"),
            due_date=date(2025, 1, 1),
            status="paid",
            paid_on=date(2025, 1, 2),
            remind_days=3,
            notes=None,
        )
        db = Mock()
        db.scalars.return_value.all.side_effect = [[a, b], [], [bill]]
        with patch(
            "app.states.csv_transfer.visible_account_ids", return_value={a.id}
        ):
            rows = transfer_rows(db, SimpleNamespace(household_id=hid), "bills")
        self.assertEqual(rows[0]["account_name"], "تاريخي")
        self.assertEqual(rows[0]["source_id"], str(bill.id))

    def test_payment_reimport_idempotent_and_conflict_rolls_back(self):
        hid, uid = uuid4(), uuid4()
        member = SimpleNamespace(household_id=hid, user_id=uid, role="owner")
        debt = SimpleNamespace(
            id=uuid4(),
            title="قرض المنزل",
            counterparty="شركة التمويل",
            direction="payable",
            first_due_date=date(2025, 1, 10),
            principal=Decimal("1200"),
        )
        existing = SimpleNamespace(
            id=uuid4(),
            debt_id=debt.id,
            amount=Decimal("100"),
            paid_on=date(2025, 1, 10),
            note=None,
            voided_at=None,
        )
        row = dict(zip(HEADERS["debt_payments"], SAMPLES["debt_payments"]))
        row.update(
            _line="2", debt_source_id=str(debt.id), source_id=str(existing.id)
        )
        db = self.financial_db([], [debt], [existing])
        self.assertEqual(
            import_rows(
                db,
                SimpleNamespace(id=uid),
                member,
                "debt_payments",
                [row],
                Mock(),
            ),
            (0, 1),
        )
        db.add.assert_not_called()
        row["amount"] = "101"
        db = self.financial_db([], [debt], [existing])
        with self.assertRaisesRegex(ValueError, "الصف 2"):
            import_rows(
                db,
                SimpleNamespace(id=uid),
                member,
                "debt_payments",
                [row],
                Mock(),
            )
        db.commit.assert_not_called()

    def test_transfer_rejects_hidden_and_self(self):
        hid, uid = uuid4(), uuid4()
        member = SimpleNamespace(household_id=hid, user_id=uid, role="owner")
        a = SimpleNamespace(
            id=uuid4(),
            name="بيت",
            currency="SAR",
            opening_date=date(2020, 1, 1),
            is_archived=False,
        )
        b = SimpleNamespace(
            id=uuid4(),
            name="ادخار",
            currency="SAR",
            opening_date=date(2020, 1, 1),
            is_archived=False,
        )
        row = dict(zip(HEADERS["transfers"], SAMPLES["transfers"]))
        row.update(
            _line="2",
            source_account_name="بيت",
            destination_account_name="ادخار",
        )
        db = self.financial_db([a, b], [], [])
        with (
            patch(
                "app.states.csv_transfer.visible_account_ids",
                return_value={a.id},
            ),
            self.assertRaisesRegex(ValueError, "الصف 2"),
        ):
            import_rows(
                db, SimpleNamespace(id=uid), member, "transfers", [row], Mock()
            )
        row["destination_account_name"] = "بيت"
        db = self.financial_db([a, b], [], [])
        with (
            patch(
                "app.states.csv_transfer.visible_account_ids",
                return_value={a.id, b.id},
            ),
            self.assertRaisesRegex(ValueError, "الصف 2"),
        ):
            import_rows(
                db, SimpleNamespace(id=uid), member, "transfers", [row], Mock()
            )
        db.commit.assert_not_called()

    def test_visibility_export_accounts(self):
        uid, hid = uuid4(), uuid4()
        visible = SimpleNamespace(
            id=uuid4(),
            name="ظاهر",
            account_type="cash",
            currency="SAR",
            opening_balance=Decimal("1"),
            opening_date=date(2020, 1, 1),
            is_archived=False,
        )
        hidden = SimpleNamespace(
            id=uuid4(),
            name="محجوب",
            account_type="cash",
            currency="USD",
            opening_balance=Decimal("500"),
            opening_date=date(2020, 1, 1),
            is_archived=False,
        )
        db = Mock()
        db.scalars.return_value.all.side_effect = [[visible, hidden], []]
        with patch(
            "app.states.csv_transfer.visible_account_ids",
            return_value={visible.id},
        ):
            self.assertEqual(
                [
                    r["name"]
                    for r in transfer_rows(
                        db, SimpleNamespace(household_id=hid), "accounts"
                    )
                ],
                ["ظاهر"],
            )


if __name__ == "__main__":
    unittest.main()
