import reflex as rx

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal
from app.locales.family_planning import LABELS

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
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
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
        or LABELS.get(key, (fallback, fallback))[selected == "en"]
        or fallback
    )


def catalog(language: str) -> dict[str, str]:
    selected = validate_language(language)
    keys = (
        _read_catalog("ar").keys() | _read_catalog("en").keys() | LABELS.keys()
    )
    return {key: translation(key, selected) for key in keys}


def t(key: str | rx.Var[str]) -> rx.Var[str]:
    from app.states.language import LanguageState

    return LanguageState.translations.get(key, LanguageState.unavailable_text)
