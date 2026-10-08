import reflex as rx

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

Language = Literal["ar", "en"]
Direction = Literal["rtl", "ltr"]


def validate_language(value: str) -> Language:
    return "en" if value == "en" else "ar"


def language_direction(value: str) -> Direction:
    return "ltr" if validate_language(value) == "en" else "rtl"


@lru_cache(maxsize=2)
def _read_catalog(language: Language) -> dict[str, str]:
    try:
        path = Path(__file__).with_name(f"{language}.json")
        source = path if path.exists() else path.with_suffix(".txt")
        raw = source.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not path.exists():
            try:
                with path.open("x", encoding="utf-8") as output:
                    output.write(raw)
            except FileExistsError:
                logging.exception("Unexpected error")
            except OSError as e:
                logging.exception(f"Error: {e}")
        if not isinstance(payload, dict):
            raise ValueError("Invalid translation catalog")
        return {
            key: value
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        }
    except (OSError, ValueError) as e:
        logging.exception(f"Error: {e}")
        return {}


def translation(key: str, language: str = "ar") -> str:
    selected = validate_language(language)
    fallback = "Text unavailable" if selected == "en" else "النص غير متاح"
    return (
        _read_catalog(selected).get(key)
        or _read_catalog("ar").get(key)
        or fallback
    )


def catalog(language: str) -> dict[str, str]:
    selected = validate_language(language)
    keys = _read_catalog("ar").keys() | _read_catalog("en").keys()
    return {key: translation(key, selected) for key in keys}


def t(key: str | rx.Var[str]) -> rx.Var[str]:
    from app.states.language import LanguageState

    return LanguageState.translations.get(key, LanguageState.unavailable_text)
