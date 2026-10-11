import unittest

from app import models as m
from app.states.ledger import ACCOUNT_COLORS, LedgerState
from app import test_multi_currency


class AccountDetailsTests(unittest.TestCase):
    def test_color_and_notes_validation(self):
        self.assertEqual(
            LedgerState._account_details({"color": "", "notes": "  "}),
            (None, None),
        )
        self.assertEqual(
            LedgerState._account_details(
                {"color": " #62704B ", "notes": " راتب شهري "}
            ),
            ("#62704b", "راتب شهري"),
        )
        self.assertEqual(LedgerState._account_details({}), (None, None))
        for bad in ("red", "#123456", "#62704b; x"):
            with self.subTest(color=bad), self.assertRaises(ValueError):
                LedgerState._account_details({"color": bad})
        with self.assertRaises(ValueError):
            LedgerState._account_details({"notes": "س" * 501})
        self.assertEqual(
            LedgerState._account_details({"notes": "س" * 500})[1], "س" * 500
        )

    def test_palette_matches_schema_constraint(self):
        for color in ACCOUNT_COLORS:
            self.assertRegex(color, r"^#[0-9a-f]{6}$")
        names = {
            str(c.name) for c in m.FinancialAccount.__table__.constraints
        }
        self.assertTrue(any(n.endswith("color_hex") for n in names))
        self.assertTrue(any(n.endswith("notes_length") for n in names))


class AccountTotalsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_multi_currency.MultiCurrencyTests()
        self.fixture.setUp()
        self.accounts, self.load = self.fixture.accounts, self.fixture.load

    def test_active_totals_are_per_currency_and_rows_carry_details(self):
        self.accounts[0].color = "#a26550"
        self.accounts[0].notes = "مصروف البيت"
        state = LedgerState()
        state.period = "current"
        self.load(state)
        self.assertEqual(
            state.currency_totals,
            [
                {"currency": "SAR", "total": "90.00"},
                {"currency": "USD", "total": "150.00"},
            ],
        )
        self.assertEqual(state.accounts[0]["color"], "#a26550")
        self.assertEqual(state.accounts[0]["notes"], "مصروف البيت")
        self.assertEqual(state.accounts[1]["color"], "")
        self.assertEqual(state.archived_accounts[0]["notes"], "")

    def test_closed_accounts_do_not_add_to_totals(self):
        self.accounts[1].is_archived = True
        state = LedgerState()
        state.period = "current"
        self.load(state)
        self.assertEqual(
            state.currency_totals, [{"currency": "SAR", "total": "90.00"}]
        )
