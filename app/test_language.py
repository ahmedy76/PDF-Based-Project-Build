import reflex as rx

import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.locales.catalog import (
    _read_catalog,
    catalog,
    language_direction,
    translation,
    validate_language,
)
from app.states.language import LanguageState
from app.components.ui import NAV, header, public_shell, shell, language_toggle
from app.components.screens import auth_page
from app.states.auth import AuthState


class LocaleTests(unittest.TestCase):
    def test_utf8_json_matching_keys_and_nonempty_values(self):
        folder = Path(__file__).parent / "locales"
        ar = json.loads((folder / "ar.json").read_text(encoding="utf-8"))
        en = json.loads((folder / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(ar.keys(), en.keys())
        self.assertGreater(len(ar), 80)
        for key in ar:
            self.assertIsInstance(ar[key], str)
            self.assertIsInstance(en[key], str)
            self.assertTrue(ar[key].strip())
            self.assertTrue(en[key].strip())
            self.assertNotEqual(ar[key], key)
            self.assertNotEqual(en[key], key)
        self.assertEqual(ar["nav.accounts"], "الحسابات")
        self.assertEqual(en["nav.accounts"], "Accounts")

    def test_catalog_reads_only_existing_json_without_writes(self):
        _read_catalog.cache_clear()
        try:
            with (
                patch.object(
                    Path, "read_text", return_value='{"key": "value"}'
                ) as read,
                patch.object(Path, "open") as opened,
            ):
                self.assertEqual(_read_catalog("en"), {"key": "value"})
                read.assert_called_once_with(encoding="utf-8")
                opened.assert_not_called()
            _read_catalog.cache_clear()
            with (
                patch.object(
                    Path, "read_text", side_effect=FileNotFoundError
                ) as read,
                patch.object(Path, "open") as opened,
                self.assertLogs(level="ERROR"),
            ):
                self.assertEqual(_read_catalog("en"), {})
                read.assert_called_once_with(encoding="utf-8")
                opened.assert_not_called()
            tree = ast.parse(
                (Path(__file__).parent / "locales/catalog.py").read_text(
                    encoding="utf-8"
                )
            )
            literals = {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            }
            self.assertIn(".json", literals)
            self.assertNotIn(".txt", literals)
        finally:
            _read_catalog.cache_clear()

    def test_all_literal_ui_keys_exist(self):
        folder = Path(__file__).parent / "components"
        for filename in ("ui.py", "screens.py", "bills.py"):
            tree = ast.parse((folder / filename).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "t"
                ):
                    if isinstance(node.args[0], ast.Constant):
                        self.assertIn(node.args[0].value, catalog("ar"))
                        self.assertIn(node.args[0].value, catalog("en"))

    def test_fallback_does_not_render_missing_key(self):
        self.assertEqual(translation("unknown.key", "en"), "Text unavailable")
        self.assertEqual(translation("unknown.key", "ar"), "النص غير متاح")
        self.assertEqual(translation("nav.accounts", "invalid"), "الحسابات")
        with patch(
            "app.locales.catalog._read_catalog",
            side_effect=lambda lang: {"key": "بديل"} if lang == "ar" else {},
        ):
            self.assertEqual(translation("key", "en"), "بديل")

    def test_validation_and_direction(self):
        for value in ("", "AR", "EN", "fr", "../en", "en;alert(1)", " en "):
            self.assertEqual(validate_language(value), "ar")
            self.assertEqual(language_direction(value), "rtl")
        self.assertEqual(validate_language("ar"), "ar")
        self.assertEqual(validate_language("en"), "en")
        self.assertEqual(language_direction("en"), "ltr")

    def test_events_validate_cookie_choice(self):
        state = SimpleNamespace(preference="ar")
        LanguageState.set_language.fn(state, "en")
        self.assertEqual(state.preference, "en")
        LanguageState.hydrate_language.fn(state)
        self.assertEqual(state.preference, "en")
        LanguageState.set_language.fn(state, "invalid")
        self.assertEqual(state.preference, "ar")
        state.preference = "fr"
        LanguageState.hydrate_language.fn(state)
        self.assertEqual(state.preference, "ar")

    def test_cookie_is_persistent_and_shared_across_routes(self):
        tree = ast.parse(
            (Path(__file__).parent / "states/language.py").read_text(
                encoding="utf-8"
            )
        )
        cookie = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Cookie"
        )
        options = {
            item.arg: ast.literal_eval(item.value) for item in cookie.keywords
        }
        self.assertEqual(ast.literal_eval(cookie.args[0]), "ar")
        self.assertEqual(options["path"], "/")
        self.assertEqual(options["name"], "mh_language")
        self.assertGreaterEqual(options["max_age"], 31536000)


class BilingualShellTests(unittest.TestCase):
    def test_navigation_routes_and_bilingual_labels(self):
        self.assertEqual(
            [item["path"] for item in NAV],
            [
                "/dashboard",
                "/accounts",
                "/transactions",
                "/budgets",
                "/goals",
                "/debts",
                "/bills",
                "/reports",
            ],
        )
        for item in NAV:
            for lang in ("ar", "en"):
                self.assertIn(item["label"], catalog(lang))
                self.assertTrue(translation(item["label"], lang))
        rendered = str(header())
        self.assertIn("nav.main", rendered)
        self.assertIn("nav.notifications", rendered)
        self.assertIn("nav.settings", rendered)
        self.assertIn("lg:flex", rendered)

    def test_both_shells_have_dynamic_direction_font_and_toggle(self):
        for component in (
            public_shell(rx.el.p("Test")),
            shell(rx.el.p("Test")),
        ):
            rendered = str(component)
            self.assertIn("direction", rendered)
            self.assertIn("language", rendered)
            self.assertIn("font-sans", rendered)
            self.assertIn("Tajawal", rendered)
            self.assertIn("#f6f4ec", rendered)
            self.assertIn("on_mount", component.event_triggers)
            mounted_events = component.event_triggers["on_mount"].events
            hydration_events = [
                event
                for event in mounted_events
                if event.handler.fn is LanguageState.hydrate_language.fn
            ]
            self.assertTrue(
                hydration_events, "Root mount must validate the language cookie"
            )
            for preference, expected in (
                ("en", "en"),
                ("ar", "ar"),
                ("fr", "ar"),
            ):
                state = SimpleNamespace(preference=preference)
                for event in hydration_events:
                    self.assertEqual(event.args, ())
                    event.handler.fn(state)
                self.assertEqual(state.preference, expected)
            self.assertIn("language.ar", rendered)
            self.assertIn("language.en", rendered)
        self.assertIn("bottom-0", str(shell(rx.el.p("Test"))))
        self.assertIn("lg:hidden", str(shell(rx.el.p("Test"))))
        toggle = str(language_toggle())
        self.assertIn("aria-pressed", toggle)
        self.assertIn("language.label", toggle)
        self.assertIn("set_language", toggle)

    def test_auth_forms_preserve_names_and_translate_primary_surface(self):
        for registering, handler in (
            (True, AuthState.register),
            (False, AuthState.login),
        ):
            rendered = str(auth_page(registering, handler))
            for name in ("email", "password"):
                self.assertIn(f'name:"{name}"', rendered)
            self.assertIn("auth.email", rendered)
            self.assertIn("auth.password", rendered)
            self.assertIn("auth.register_title", rendered)
            self.assertIn("auth.login_title", rendered)
            if registering:
                for name in ("name", "confirm", "terms"):
                    self.assertIn(f'name:"{name}"', rendered)


if __name__ == "__main__":
    unittest.main()
