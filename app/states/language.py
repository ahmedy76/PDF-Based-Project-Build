import reflex as rx

from app.locales.catalog import (
    Direction,
    Language,
    catalog,
    language_direction,
    validate_language,
)


class LanguageState(rx.State):
    preference: str = rx.Cookie(
        "ar", name="mh_language", path="/", same_site="lax", max_age=31536000
    )

    @rx.var
    def language(self) -> Language:
        return validate_language(self.preference)

    @rx.var
    def direction(self) -> Direction:
        return language_direction(self.preference)

    @rx.var
    def translations(self) -> dict[str, str]:
        return catalog(self.language)

    @rx.var
    def unavailable_text(self) -> str:
        return "Text unavailable" if self.language == "en" else "النص غير متاح"

    @rx.event
    def set_language(self, value: str):
        self.preference = validate_language(value)

    @rx.event
    def hydrate_language(self):
        self.preference = validate_language(self.preference)
