import reflex as rx

from app.locales.catalog import t
from app.states.language import LanguageState as L
from app.states.auth import AuthState
from app.states.ledger import LedgerState as S
from app.states.receipts import ReceiptState
from app.components.receipts import receipt_modal


BUTTON = "inline-flex items-center justify-center gap-2 rounded-xl bg-[#62704b] px-5 py-3 text-sm font-bold text-white hover:bg-[#4f5e3c] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#62704b] transition-colors disabled:opacity-50"
SECONDARY = "inline-flex items-center justify-center gap-2 rounded-xl border border-[#ddd9cd] bg-[#fffdf8] px-4 py-2.5 text-sm font-semibold text-[#27394a] hover:bg-[#eeece2] focus-visible:outline-2 focus-visible:outline-[#62704b]"
INPUT = "w-full rounded-xl border border-[#dcd8cb] bg-white px-3 py-3 text-base text-[#27394a] outline-hidden focus:border-[#62704b] focus:ring-2 focus:ring-[#62704b]/20"
CARD = "rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-5 md:p-7"
NAV = [
    {"label": "nav.dashboard", "path": "/dashboard", "icon": "house"},
    {"label": "nav.accounts", "path": "/accounts", "icon": "wallet"},
    {
        "label": "nav.transactions",
        "path": "/transactions",
        "icon": "arrow-left-right",
    },
    {"label": "nav.budgets", "path": "/budgets", "icon": "chart-pie"},
    {"label": "nav.goals", "path": "/goals", "icon": "target"},
    {"label": "nav.debts", "path": "/debts", "icon": "hand-coins"},
    {"label": "nav.bills", "path": "/bills", "icon": "receipt-text"},
    {
        "label": "nav.reports",
        "path": "/reports",
        "icon": "chart-no-axes-combined",
    },
]


def language_toggle() -> rx.Component:
    return rx.el.div(
        rx.el.span(
            t("language.label"),
            class_name="text-xs font-semibold text-[#52604f]",
        ),
        rx.el.div(
            rx.el.button(
                "AR",
                type="button",
                lang="ar",
                aria_label=t("language.ar"),
                aria_pressed=L.language == "ar",
                on_click=lambda: L.set_language("ar"),
                class_name=rx.cond(
                    L.language == "ar",
                    "rounded-lg bg-[#62704b] px-2 py-2 text-xs font-bold text-white focus-visible:outline-2 focus-visible:outline-[#62704b]",
                    "rounded-lg bg-[#fffdf8] px-2 py-2 text-xs font-bold text-[#52604f] hover:bg-[#eeece2] focus-visible:outline-2 focus-visible:outline-[#62704b]",
                ),
            ),
            rx.el.button(
                "EN",
                type="button",
                lang="en",
                aria_label=t("language.en"),
                aria_pressed=L.language == "en",
                on_click=lambda: L.set_language("en"),
                class_name=rx.cond(
                    L.language == "en",
                    "rounded-lg bg-[#62704b] px-2 py-2 text-xs font-bold text-white focus-visible:outline-2 focus-visible:outline-[#62704b]",
                    "rounded-lg bg-[#fffdf8] px-2 py-2 text-xs font-bold text-[#52604f] hover:bg-[#eeece2] focus-visible:outline-2 focus-visible:outline-[#62704b]",
                ),
            ),
            role="group",
            aria_label=t("language.label"),
            dir="ltr",
            class_name="flex gap-1 rounded-xl border border-[#ddd9cd] bg-[#fffdf8] p-1",
        ),
        title=t("language.partial"),
        class_name="flex shrink-0 flex-col items-center gap-1",
    )


def brand() -> rx.Component:
    return rx.el.a(
        rx.el.div(
            rx.icon("sprout", class_name="h-6 w-6"),
            class_name="rounded-xl bg-[#e7ebdc] p-2.5 text-[#62704b]",
        ),
        rx.el.div(
            rx.el.span(
                "Money Harmony",
                class_name="block text-lg font-bold tracking-tight",
            ),
            rx.el.span(
                t("brand.tagline"),
                class_name="block text-xs font-medium text-[#7c8178]",
            ),
        ),
        href="/",
        class_name="flex items-center gap-3 text-[#27394a]",
    )


def field(
    label: str, name: str, kind: str = "text", default="", required: bool = True
) -> rx.Component:
    return rx.el.label(
        rx.el.span(
            label, class_name="mb-2 block text-sm font-semibold text-[#465344]"
        ),
        rx.el.input(
            name=name,
            type=kind,
            default_value=default,
            required=required,
            class_name=INPUT,
        ),
        class_name="block min-w-0",
    )


def select_field(label: str, name: str, options, default="") -> rx.Component:
    return rx.el.label(
        rx.el.span(
            label, class_name="mb-2 block text-sm font-semibold text-[#465344]"
        ),
        rx.el.div(
            rx.el.select(
                rx.foreach(
                    options, lambda o: rx.el.option(o["name"], value=o["id"])
                ),
                name=name,
                default_value=default,
                class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white px-3 py-3 pl-9 text-base text-[#27394a] focus:outline-2 focus:outline-[#62704b]",
            ),
            rx.icon(
                "chevron-down",
                class_name="pointer-events-none absolute left-3 top-4 h-4 w-4 text-[#7c8178]",
            ),
            class_name="relative",
        ),
        class_name="block min-w-0",
    )


def section_title(title: str, subtitle: str) -> rx.Component:
    return rx.el.div(
        rx.el.h1(
            title,
            class_name="text-3xl font-bold leading-relaxed text-[#243747]",
        ),
        rx.el.p(subtitle, class_name="mt-1 text-base leading-7 text-[#7a8179]"),
        class_name="mb-7",
    )


def empty(text: str) -> rx.Component:
    return rx.el.div(
        rx.icon(
            "notebook-pen", class_name="mx-auto mb-3 h-8 w-8 text-[#a6ad96]"
        ),
        rx.el.p(text, class_name="text-sm leading-7 text-[#7a8179]"),
        class_name="rounded-xl border border-dashed border-[#ddd9cd] bg-[#faf9f3] p-9 text-center",
    )


def notice() -> rx.Component:
    return rx.cond(
        S.message != "",
        rx.el.div(
            rx.icon("info", class_name="h-5 w-5 shrink-0"),
            rx.el.p(S.message),
            role="status",
            class_name="mb-5 flex items-center gap-3 rounded-xl border border-[#e0d7bc] bg-[#f6f0df] p-4 text-sm leading-7 text-[#786036]",
        ),
    )


def nav_item(item: dict[str, str]) -> rx.Component:
    return rx.el.a(
        rx.icon(item["icon"], class_name="h-5 w-5"),
        rx.el.span(t(item["label"])),
        aria_label=t(item["label"]),
        href=item["path"],
        class_name="flex min-w-[70px] shrink-0 flex-col items-center justify-center gap-1 rounded-xl px-2 py-3 text-xs font-semibold text-[#52604f] hover:bg-[#e9ecdf] lg:min-w-0 lg:flex-row lg:gap-1 lg:px-1.5 xl:gap-2 xl:px-2 xl:text-sm",
    )


def header() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            brand(),
            rx.el.nav(
                rx.foreach(NAV, nav_item),
                aria_label=t("nav.main"),
                class_name="hidden items-center gap-1 lg:flex",
            ),
            rx.el.div(
                rx.el.a(
                    rx.icon("bell", class_name="h-5 w-5"),
                    href="/notifications",
                    aria_label=t("nav.notifications"),
                    class_name=SECONDARY,
                ),
                rx.el.a(
                    rx.icon("settings-2", class_name="h-5 w-5"),
                    href="/settings",
                    aria_label=t("nav.settings"),
                    class_name=SECONDARY,
                ),
                language_toggle(),
                class_name="flex gap-2",
            ),
            class_name="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-5 py-4 md:px-10",
        ),
        class_name="shrink-0 border-b border-[#e3dfd3] bg-[#fffdf8]",
    )


def shell(content: rx.Component) -> rx.Component:
    return rx.el.div(
        header(),
        rx.el.main(
            rx.cond(
                AuthState.authenticated & S.ready,
                rx.el.div(
                    rx.el.div(
                        rx.el.span(S.household_name),
                        rx.el.button(
                            rx.icon("refresh-cw", class_name="h-3.5 w-3.5"),
                            t("action.refresh"),
                            on_click=S.load,
                            class_name="flex items-center gap-2 hover:text-[#62704b]",
                        ),
                        class_name="mb-5 flex justify-between border-b border-[#e4e0d4] pb-4 text-xs text-[#7d8277]",
                    ),
                    notice(),
                    rx.cond(
                        L.language == "en",
                        rx.el.p(
                            t("language.partial"),
                            class_name="mb-4 text-xs text-[#7d8277]",
                        ),
                    ),
                    content,
                    editor(),
                    delete_confirmation(),
                    transaction_history(),
                    receipt_modal(),
                    class_name="mx-auto w-full max-w-[1320px]",
                ),
                rx.el.div(
                    notice(),
                    rx.el.p(
                        t("shell.loading"),
                        class_name="py-20 text-center text-[#7c8178]",
                    ),
                    rx.el.button(
                        t("action.retry"), on_click=S.load, class_name=SECONDARY
                    ),
                ),
            ),
            class_name="w-full min-w-0 flex-1 overflow-y-auto px-5 py-6 pb-28 md:px-10 md:py-8",
        ),
        rx.el.nav(
            rx.foreach(NAV, nav_item),
            aria_label=t("nav.main"),
            class_name="fixed inset-x-0 bottom-0 z-20 flex justify-start gap-1 overflow-x-auto border-t border-[#dedacd] bg-[#fffdf8] px-2 pb-2 lg:hidden",
        ),
        dir=L.direction,
        lang=L.language,
        on_mount=L.hydrate_language,
        class_name=rx.cond(
            L.language == "ar",
            "flex h-dvh flex-col overflow-hidden bg-[#f6f4ec] font-['Tajawal'] text-[#27394a]",
            "flex h-dvh flex-col overflow-hidden bg-[#f6f4ec] font-sans text-[#27394a]",
        ),
    )


def public_shell(content: rx.Component) -> rx.Component:
    return rx.el.div(
        rx.el.header(
            brand(),
            rx.el.div(
                rx.el.a(
                    t("action.open_ledger"), href="/login", class_name=SECONDARY
                ),
                language_toggle(),
                class_name="flex items-center gap-2",
            ),
            class_name="mx-auto flex max-w-6xl items-center justify-between px-5 py-6",
        ),
        rx.el.main(
            content, class_name="mx-auto w-full max-w-6xl px-5 py-10 md:py-16"
        ),
        rx.el.footer(
            rx.el.p(t("brand.footer")),
            rx.cond(
                L.language == "en",
                rx.el.p(
                    t("language.partial"),
                    class_name="mt-2 text-xs text-[#7d8277]",
                ),
            ),
            class_name="px-5 py-8 text-center text-sm text-[#7d8277]",
        ),
        dir=L.direction,
        lang=L.language,
        on_mount=L.hydrate_language,
        class_name=rx.cond(
            L.language == "ar",
            "min-h-dvh bg-[#f6f4ec] font-['Tajawal'] text-[#27394a]",
            "min-h-dvh bg-[#f6f4ec] font-sans text-[#27394a]",
        ),
    )


def currency_switcher() -> rx.Component:
    return rx.el.label(
        rx.el.span(
            t("currency.label"),
            class_name="mb-2 block text-sm font-semibold text-[#465344]",
        ),
        rx.el.div(
            rx.el.select(
                rx.foreach(
                    S.view_currencies,
                    lambda code: rx.el.option(code, value=code),
                ),
                value=S.view_currency,
                on_change=S.set_view_currency,
                aria_label=t("currency.accessible"),
                class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-[#fffdf8] px-4 py-3 pl-10 text-sm font-bold text-[#27394a] focus:outline-2 focus:outline-[#62704b]",
            ),
            rx.icon(
                "chevron-down",
                class_name="pointer-events-none absolute left-3 top-4 h-4 w-4 text-[#62704b]",
            ),
            class_name="relative",
        ),
        class_name="mb-6 block w-full sm:w-72",
    )


def metric(label: str, value, icon: str) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.span(label),
            rx.icon(icon, class_name="h-5 w-5 text-[#8c9778]"),
            class_name="flex items-center justify-between text-sm text-[#75806d]",
        ),
        rx.el.div(
            rx.el.strong(
                value, class_name="text-2xl font-bold tabular-nums md:text-3xl"
            ),
            rx.el.span(S.view_currency, class_name="text-xs text-[#88907e]"),
            class_name="mt-4 flex flex-wrap items-baseline gap-2",
        ),
        class_name=CARD,
    )


def edit_actions(kind: str, row) -> rx.Component:
    return rx.cond(
        rx.cond(
            kind == "budget",
            S.can_edit_budgets,
            rx.cond(kind == "transaction", S.can_add_transactions, True),
        ),
        rx.el.div(
            rx.el.button(
                rx.icon("pencil", class_name="h-4 w-4"),
                t("action.edit"),
                on_click=lambda: S.open_editor(kind, row["id"]),
                class_name="flex items-center gap-1 rounded-lg px-3 py-2 text-xs text-[#62704b] hover:bg-[#edf0e5]",
            ),
            rx.el.button(
                rx.cond(
                    kind == "account",
                    rx.icon("archive", class_name="h-4 w-4"),
                    rx.icon("trash-2", class_name="h-4 w-4"),
                ),
                rx.cond(
                    kind == "account",
                    t("action.close_account"),
                    t("action.delete"),
                ),
                on_click=lambda: S.ask_delete(kind, row["id"]),
                class_name=rx.cond(
                    kind == "account",
                    "flex items-center gap-1 rounded-lg px-3 py-2 text-xs text-[#62704b] hover:bg-[#edf0e5]",
                    "flex items-center gap-1 rounded-lg px-3 py-2 text-xs text-[#a26550] hover:bg-[#f5e9e3]",
                ),
            ),
            class_name="flex gap-1",
        ),
    )


def transaction_row(row) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.cond(
                    row["kind"] == "income",
                    rx.icon("arrow-down-left", class_name="h-5 w-5"),
                    rx.icon("arrow-up-right", class_name="h-5 w-5"),
                ),
                class_name=rx.cond(
                    row["kind"] == "income",
                    "rounded-xl bg-[#e9eddf] p-3 text-[#62704b]",
                    "rounded-xl bg-[#f1e7dd] p-3 text-[#a27456]",
                ),
            ),
            rx.el.div(
                rx.el.p(row["name"], class_name="font-semibold"),
                rx.cond(
                    row["recurring_rule_id"] != "",
                    rx.el.span(
                        f"متكررة · استحقاق {row['scheduled_for']}",
                        class_name="inline-block w-fit rounded-lg bg-[#e9eddf] px-2 py-0.5 text-xs font-bold text-[#62704b]",
                    ),
                ),
                rx.el.p(
                    f"{row['category']} · {row['account']} · {row['transaction_date']}",
                    class_name="mt-1 text-xs text-[#828679]",
                ),
                rx.el.p(
                    row["metadata"], class_name="mt-1 text-xs text-[#7c8178]"
                ),
                rx.cond(
                    row["editor_metadata"] != "",
                    rx.el.p(
                        row["editor_metadata"],
                        class_name="text-xs text-[#7c8178]",
                    ),
                ),
                rx.cond(
                    row["legacy_metadata"] != "",
                    rx.el.p(
                        row["legacy_metadata"],
                        class_name="text-xs text-[#9a917f]",
                    ),
                ),
            ),
            class_name="flex min-w-0 items-center gap-3",
        ),
        rx.el.div(
            rx.el.p(
                rx.cond(row["kind"] == "income", "+ ", "− "),
                row["display_amount"],
                rx.el.span(f" {row['currency']}", class_name="text-xs"),
                class_name=rx.cond(
                    row["kind"] == "income",
                    "text-left font-bold tabular-nums text-[#62704b]",
                    "text-left font-bold tabular-nums text-[#a26550]",
                ),
            ),
            rx.el.div(
                rx.el.button(
                    rx.icon("paperclip", class_name="h-4 w-4"),
                    "الإيصال",
                    on_click=lambda: ReceiptState.open_receipt(row["id"]),
                    class_name="flex items-center gap-1 rounded-lg px-3 py-2 text-xs text-[#62704b] hover:bg-[#edf0e5]",
                ),
                rx.el.button(
                    rx.icon("history", class_name="h-4 w-4"),
                    "سجل التعديلات",
                    on_click=lambda: S.show_transaction_history(row["id"]),
                    class_name="flex items-center gap-1 rounded-lg px-3 py-2 text-xs text-[#62704b] hover:bg-[#edf0e5]",
                ),
                rx.cond(
                    S.can_add_transactions,
                    rx.el.button(
                        rx.icon("copy", class_name="h-4 w-4"),
                        "إعادة استخدام البيانات",
                        on_click=lambda: S.reuse_transaction(row["id"]),
                        class_name="flex items-center gap-1 rounded-lg px-3 py-2 text-xs text-[#62704b] hover:bg-[#edf0e5]",
                    ),
                ),
                edit_actions("transaction", row),
                class_name="flex flex-wrap justify-end gap-1",
            ),
            class_name="min-w-0 sm:shrink-0",
        ),
        class_name="flex flex-wrap items-center justify-between gap-3 border-b border-[#eeebe2] py-4 last:border-0",
        key=row["id"],
    )


def budget_card(row) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.el.h3(row["name"], class_name="text-lg font-bold"),
            rx.el.span(row["month"], class_name="text-xs text-[#7c8178]"),
            class_name="flex items-center justify-between",
        ),
        rx.el.div(
            rx.el.strong(row["spent"], class_name="text-2xl tabular-nums"),
            rx.el.span(
                f"من {row['limit']} {row['currency']}",
                class_name="text-sm text-[#7c8178]",
            ),
            class_name="my-5 flex flex-wrap items-baseline gap-2",
        ),
        rx.el.progress(
            value=row["progress"],
            max="100",
            aria_label=row["name"],
            class_name=rx.cond(
                row["status"] == "ضمن الميزانية",
                "h-2 w-full overflow-hidden rounded-full accent-[#62704b]",
                "h-2 w-full overflow-hidden rounded-full accent-[#b28b49]",
            ),
        ),
        rx.el.div(
            rx.el.span(
                row["status"],
                class_name=rx.cond(
                    row["status"] == "ضمن الميزانية",
                    "text-sm text-[#62704b]",
                    "text-sm text-[#a27456]",
                ),
            ),
            rx.el.span(f"{row['percent']}%", class_name="text-sm tabular-nums"),
            class_name="mt-3 flex justify-between",
        ),
        rx.el.div(
            edit_actions("budget", row),
            class_name="mt-4 border-t border-[#ece8dd] pt-2",
        ),
        class_name=CARD,
        key=row["id"],
    )


def editor() -> rx.Component:
    return rx.cond(
        S.editor != "",
        rx.el.div(
            rx.el.section(
                rx.el.div(
                    rx.el.h2(
                        rx.match(
                            S.editor,
                            ("account", "بيانات الحساب المالي"),
                            ("transaction", "تفاصيل المعاملة"),
                            ("recurring", "تفاصيل المعاملة المتكررة"),
                            "الميزانية الشهرية",
                        ),
                        class_name="text-xl font-bold",
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-5 w-5"),
                        on_click=S.close_editor,
                        aria_label=t("action.close"),
                        class_name=SECONDARY,
                    ),
                    class_name="mb-5 flex items-center justify-between",
                ),
                notice(),
                rx.el.form(
                    rx.match(
                        S.editor,
                        (
                            "account",
                            rx.el.div(
                                field(
                                    "اسم الحساب",
                                    "name",
                                    default=S.draft["name"],
                                ),
                                select_field(
                                    "نوع الحساب",
                                    "account_type",
                                    [
                                        {"id": "cash", "name": "نقدي"},
                                        {"id": "bank", "name": "بنكي"},
                                        {"id": "savings", "name": "ادخار"},
                                        {
                                            "id": "credit_card",
                                            "name": "بطاقة ائتمان",
                                        },
                                        {"id": "other", "name": "آخر"},
                                    ],
                                    S.draft["account_type"],
                                ),
                                rx.cond(
                                    S.edit_id == "",
                                    rx.el.div(
                                        select_field(
                                            "عملة الحساب",
                                            "currency",
                                            [
                                                {
                                                    "id": "SAR",
                                                    "name": "SAR · ريال سعودي",
                                                },
                                                {
                                                    "id": "USD",
                                                    "name": "USD · دولار أمريكي",
                                                },
                                                {
                                                    "id": "EUR",
                                                    "name": "EUR · يورو",
                                                },
                                                {
                                                    "id": "AED",
                                                    "name": "AED · درهم إماراتي",
                                                },
                                                {
                                                    "id": "GBP",
                                                    "name": "GBP · جنيه إسترليني",
                                                },
                                                {
                                                    "id": "KWD",
                                                    "name": "KWD · دينار كويتي",
                                                },
                                                {
                                                    "id": "BHD",
                                                    "name": "BHD · دينار بحريني",
                                                },
                                                {
                                                    "id": "OMR",
                                                    "name": "OMR · ريال عماني",
                                                },
                                                {
                                                    "id": "QAR",
                                                    "name": "QAR · ريال قطري",
                                                },
                                                {
                                                    "id": "EGP",
                                                    "name": "EGP · جنيه مصري",
                                                },
                                            ],
                                            S.draft["currency"],
                                        ),
                                        field(
                                            "رمز ISO آخر (اختياري، ثلاثة أحرف إنجليزية)",
                                            "currency_custom",
                                            required=False,
                                        ),
                                        class_name="space-y-3",
                                    ),
                                    rx.el.div(
                                        rx.el.p(
                                            f"عملة الحساب: {S.draft['currency']} · ثابتة بعد الإنشاء",
                                            class_name="text-sm font-bold text-[#62704b]",
                                        ),
                                        rx.el.input(
                                            type="hidden",
                                            name="currency",
                                            default_value=S.draft["currency"],
                                        ),
                                    ),
                                ),
                                field(
                                    "الرصيد الافتتاحي",
                                    "opening_balance",
                                    default=S.draft["opening_balance"],
                                ),
                                field(
                                    "تاريخ الافتتاح",
                                    "opening_date",
                                    "date",
                                    S.draft["opening_date"],
                                ),
                                rx.el.p(
                                    "اختر العملة بعناية؛ لا يمكن تغييرها بعد إنشاء الحساب. الرصيد الحالي = الافتتاحي + الدخل − المصروف − التحويلات الصادرة + التحويلات الواردة بنفس العملة.",
                                    class_name="text-xs leading-6 text-[#7c8178]",
                                ),
                                class_name="space-y-4",
                            ),
                        ),
                        (
                            "transaction",
                            rx.el.div(
                                rx.el.label(
                                    rx.el.span(
                                        "نوع المعاملة",
                                        class_name="mb-2 block text-sm font-semibold text-[#465344]",
                                    ),
                                    rx.el.div(
                                        rx.el.select(
                                            rx.el.option(
                                                "مصروف", value="expense"
                                            ),
                                            rx.el.option("دخل", value="income"),
                                            name="kind",
                                            default_value=S.draft["kind"],
                                            on_change=S.change_transaction_kind,
                                            class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white px-3 py-3 pl-9 text-base text-[#27394a]",
                                        ),
                                        rx.icon(
                                            "chevron-down",
                                            class_name="pointer-events-none absolute left-3 top-4 h-4 w-4 text-[#7c8178]",
                                        ),
                                        class_name="relative",
                                    ),
                                ),
                                rx.cond(
                                    S.transaction_account_options.length() == 0,
                                    rx.el.p(
                                        "لا توجد حسابات نشطة. أضف حسابًا من صفحة الحسابات قبل تسجيل معاملة جديدة.",
                                        class_name="text-sm text-[#a26550]",
                                    ),
                                ),
                                rx.el.label(
                                    "الحساب",
                                    rx.el.div(
                                        rx.el.select(
                                            rx.foreach(
                                                S.transaction_account_options,
                                                lambda a: rx.el.option(
                                                    f"{a['name']} · {a['currency']}",
                                                    value=a["id"],
                                                ),
                                            ),
                                            name="account_id",
                                            default_value=S.draft["account_id"],
                                            on_change=S.change_editor_account,
                                            class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pl-9 text-[#27394a]",
                                        ),
                                        rx.icon(
                                            "chevron-down",
                                            class_name="pointer-events-none absolute left-3 top-4 h-4 w-4",
                                        ),
                                        class_name="relative mt-2",
                                    ),
                                    class_name="block text-sm font-semibold text-[#465344]",
                                ),
                                rx.el.p(
                                    f"عملة المعاملة: {S.transaction_currency}",
                                    class_name="text-sm font-bold text-[#62704b]",
                                ),
                                rx.el.label(
                                    rx.el.span(
                                        "الفئة (اختر فئة تطابق نوع المعاملة)",
                                        class_name="mb-2 block text-sm font-semibold",
                                    ),
                                    rx.el.div(
                                        rx.el.select(
                                            rx.foreach(
                                                S.transaction_category_options,
                                                lambda c: rx.el.option(
                                                    f"{c['name']} — {rx.cond(c['kind'] == 'income', 'دخل', 'مصروف')}",
                                                    value=c["id"],
                                                ),
                                            ),
                                            name="category_id",
                                            default_value=S.draft[
                                                "category_id"
                                            ],
                                            key=S.draft["kind"],
                                            on_change=S.change_transaction_category,
                                            class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pl-9 text-[#27394a]",
                                        ),
                                        rx.icon(
                                            "chevron-down",
                                            class_name="pointer-events-none absolute left-3 top-4 h-4 w-4",
                                        ),
                                        class_name="relative",
                                    ),
                                ),
                                rx.cond(
                                    S.transaction_category_options.length()
                                    == 0,
                                    rx.el.p(
                                        "لا توجد فئة نشطة لهذا النوع. أضف فئة مناسبة من صفحة فئات الأسرة.",
                                        class_name="text-sm text-[#a26550]",
                                    ),
                                ),
                                rx.cond(
                                    S.editing_archived_category,
                                    rx.el.p(
                                        "يمكن الاحتفاظ بالفئة المؤرشفة لهذه المعاملة فقط عند تعديلها.",
                                        class_name="text-xs leading-6 text-[#7c8178]",
                                    ),
                                ),
                                rx.el.a(
                                    rx.icon("tags", class_name="h-4 w-4"),
                                    "إدارة فئات الدخل والمصروف",
                                    href="/categories",
                                    class_name="inline-flex items-center gap-2 text-sm font-bold text-[#62704b] hover:underline",
                                ),
                                rx.cond(
                                    S.edit_id == "",
                                    rx.el.p(
                                        "تعبئة البيانات لا تُسجّل معاملة تلقائيًا. أدخل المبلغ وراجع التفاصيل ثم اضغط حفظ.",
                                        class_name="text-xs leading-6 text-[#7c8178]",
                                    ),
                                ),
                                field(
                                    "المبلغ",
                                    "amount",
                                    default=S.draft["amount"],
                                ),
                                field(
                                    "التاريخ",
                                    "transaction_date",
                                    "date",
                                    S.draft["transaction_date"],
                                ),
                                field(
                                    "الوصف (اختياري)",
                                    "description",
                                    default=S.draft["description"],
                                    required=False,
                                ),
                                class_name="space-y-4",
                            ),
                        ),
                        (
                            "recurring",
                            rx.el.div(
                                select_field(
                                    "نوع المعاملة",
                                    "kind",
                                    [
                                        {"id": "expense", "name": "مصروف"},
                                        {"id": "income", "name": "دخل"},
                                    ],
                                    S.draft["kind"],
                                ),
                                rx.el.label(
                                    "الحساب",
                                    rx.el.div(
                                        rx.el.select(
                                            rx.foreach(
                                                S.accounts,
                                                lambda a: rx.el.option(
                                                    f"{a['name']} · {a['currency']}",
                                                    value=a["id"],
                                                ),
                                            ),
                                            name="account_id",
                                            default_value=S.draft["account_id"],
                                            on_change=S.change_editor_account,
                                            class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pl-9 text-[#27394a]",
                                        ),
                                        rx.icon(
                                            "chevron-down",
                                            class_name="pointer-events-none absolute left-3 top-4 h-4 w-4",
                                        ),
                                        class_name="relative mt-2",
                                    ),
                                    class_name="block text-sm font-semibold text-[#465344]",
                                ),
                                rx.el.p(
                                    f"عملة التكرار: {S.transaction_currency}",
                                    class_name="text-sm font-bold text-[#62704b]",
                                ),
                                rx.el.label(
                                    rx.el.span(
                                        "الفئة (اختر فئة تطابق نوع المعاملة)",
                                        class_name="mb-2 block text-sm font-semibold text-[#465344]",
                                    ),
                                    rx.el.div(
                                        rx.el.select(
                                            rx.foreach(
                                                S.categories,
                                                lambda c: rx.el.option(
                                                    f"{c['name']} — {rx.cond(c['kind'] == 'income', 'دخل', 'مصروف')}",
                                                    value=c["id"],
                                                ),
                                            ),
                                            name="category_id",
                                            default_value=S.draft[
                                                "category_id"
                                            ],
                                            class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pl-9 text-[#27394a]",
                                        ),
                                        rx.icon(
                                            "chevron-down",
                                            class_name="pointer-events-none absolute left-3 top-4 h-4 w-4",
                                        ),
                                        class_name="relative",
                                    ),
                                ),
                                field(
                                    "المبلغ",
                                    "amount",
                                    default=S.draft["amount"],
                                ),
                                field(
                                    "الوصف (اختياري)",
                                    "description",
                                    default=S.draft["description"],
                                    required=False,
                                ),
                                select_field(
                                    "التكرار",
                                    "frequency",
                                    [
                                        {"id": "daily", "name": "يوميًا"},
                                        {"id": "weekly", "name": "أسبوعيًا"},
                                        {"id": "monthly", "name": "شهريًا"},
                                    ],
                                    S.draft["frequency"],
                                ),
                                field(
                                    "تاريخ البداية",
                                    "start_date",
                                    "date",
                                    S.draft["start_date"],
                                ),
                                field(
                                    "تاريخ النهاية (اختياري)",
                                    "end_date",
                                    "date",
                                    S.draft["end_date"],
                                    required=False,
                                ),
                                rx.el.p(
                                    "تعديل القاعدة يغيّر المواعيد القادمة فقط؛ لا يغيّر المعاملات المسجلة سابقًا.",
                                    class_name="text-xs leading-6 text-[#7c8178]",
                                ),
                                class_name="space-y-4",
                            ),
                        ),
                        rx.el.div(
                            rx.el.label(
                                rx.el.span(
                                    "فئة المصروف",
                                    class_name="mb-2 block text-sm font-semibold",
                                ),
                                rx.el.div(
                                    rx.el.select(
                                        rx.foreach(
                                            S.categories,
                                            lambda c: rx.cond(
                                                c["kind"] == "expense",
                                                rx.el.option(
                                                    c["name"], value=c["id"]
                                                ),
                                            ),
                                        ),
                                        name="category_id",
                                        default_value=S.draft["category_id"],
                                        class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pl-9 text-[#27394a]",
                                    ),
                                    rx.icon(
                                        "chevron-down",
                                        class_name="pointer-events-none absolute left-3 top-4 h-4 w-4",
                                    ),
                                    class_name="relative",
                                ),
                            ),
                            rx.el.a(
                                rx.icon("tags", class_name="h-4 w-4"),
                                "إدارة فئات المصروف",
                                href="/categories",
                                class_name="inline-flex items-center gap-2 text-sm font-bold text-[#62704b] hover:underline",
                            ),
                            select_field(
                                "عملة الميزانية (حساب نشط)",
                                "currency",
                                S.active_currencies,
                                S.draft["currency"],
                            ),
                            field("الشهر", "month", "month", S.draft["month"]),
                            field(
                                "حد الإنفاق",
                                "amount",
                                default=S.draft["amount"],
                            ),
                            field(
                                "التنبيه عند النسبة % (1–100)",
                                "threshold",
                                "number",
                                S.draft["threshold"],
                            ),
                            class_name="space-y-4",
                        ),
                    ),
                    rx.el.div(
                        rx.el.button(
                            t("action.save"), type="submit", class_name=BUTTON
                        ),
                        rx.el.button(
                            t("action.cancel"),
                            type="button",
                            on_click=S.close_editor,
                            class_name=SECONDARY,
                        ),
                        class_name="mt-7 flex gap-3",
                    ),
                    on_submit=S.save,
                    key=f"{S.editor}-{S.edit_id}",
                ),
                role="dialog",
                aria_modal=True,
                aria_label="تحرير بيانات الدفتر",
                class_name="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[#fffdf8] p-6",
            ),
            class_name="fixed inset-0 z-40 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )


def history_change(change) -> rx.Component:
    return rx.el.li(
        rx.el.span(
            f"{change['field']}: ", class_name="font-bold text-[#27394a]"
        ),
        rx.el.span(change["before"]),
        rx.icon(
            "arrow-left", class_name="inline-block h-3 w-3 mx-2 text-[#62704b]"
        ),
        rx.el.span(change["after"]),
        class_name="break-words text-sm leading-7 text-[#596456]",
    )


def history_event(event) -> rx.Component:
    return rx.el.li(
        rx.el.div(
            rx.el.strong(event["action"], class_name="text-[#27394a]"),
            rx.el.span(
                event["date"], class_name="text-xs tabular-nums text-[#7c8178]"
            ),
            class_name="flex flex-wrap justify-between gap-2",
        ),
        rx.el.p(event["actor"], class_name="mt-1 text-xs text-[#62704b]"),
        rx.el.ul(
            rx.foreach(event["changes"], history_change),
            class_name="mt-2 space-y-1",
        ),
        class_name="rounded-xl border border-[#e2ded2] bg-[#faf9f3] p-4",
        key=event["id"],
    )


def transaction_history() -> rx.Component:
    return rx.cond(
        S.history_id != "",
        rx.el.div(
            rx.el.section(
                rx.el.div(
                    rx.el.div(
                        rx.el.h2(
                            "سجل التعديلات",
                            class_name="text-xl font-bold text-[#27394a]",
                        ),
                        rx.el.p(
                            S.history_title, class_name="text-sm text-[#7c8178]"
                        ),
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-5 w-5"),
                        on_click=S.close_transaction_history,
                        aria_label="إغلاق سجل التعديلات",
                        class_name=SECONDARY,
                    ),
                    class_name="mb-5 flex items-start justify-between gap-3",
                ),
                rx.cond(
                    S.history_legacy != "",
                    rx.el.p(
                        S.history_legacy,
                        class_name="mb-4 rounded-xl bg-[#f6f4ec] p-3 text-sm leading-7 text-[#596456]",
                    ),
                ),
                rx.cond(
                    S.history_events.length() > 0,
                    rx.el.ol(
                        rx.foreach(S.history_events, history_event),
                        class_name="space-y-3",
                    ),
                    rx.el.p(
                        "لا توجد أحداث محفوظة لهذه المعاملة القديمة. التعديلات السابقة غير متاحة.",
                        class_name="text-sm leading-7 text-[#7c8178]",
                    ),
                ),
                role="dialog",
                aria_modal=True,
                aria_label="سجل تعديلات المعاملة",
                class_name="max-h-[90dvh] w-full max-w-xl overflow-y-auto rounded-2xl bg-[#fffdf8] p-5 md:p-7",
            ),
            class_name="fixed inset-0 z-50 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )


def delete_confirmation() -> rx.Component:
    return rx.cond(
        S.delete_id != "",
        rx.el.div(
            rx.el.section(
                rx.el.h2(
                    rx.cond(
                        S.delete_kind == "account",
                        "تأكيد إغلاق الحساب",
                        "هل تريد حذف هذا العنصر؟",
                    ),
                    class_name="text-xl font-bold",
                ),
                rx.cond(
                    S.delete_kind == "account",
                    rx.el.div(
                        rx.el.p(
                            f"إغلاق «{S.closing_name}» برصيد مسجّل {S.closing_balance} {S.closing_currency}؟",
                            class_name="font-bold text-[#27394a]",
                        ),
                        rx.el.p(
                            "ستبقى المعاملات السابقة واسم الحساب وتقاريره محفوظة، ولن تُسجّل معاملات جديدة عليه. إن كان رصيده غير صفري، سيُستبعد من مجموع الحسابات النشطة ويُعرض ضمن أرصدة المغلقة؛ هذا ليس تحويلًا فعليًا ولا يعني اختفاء الأموال.",
                            class_name="mt-3 text-sm leading-7 text-[#7c8178]",
                        ),
                        class_name="my-4",
                    ),
                    rx.el.p(
                        "سيتم تحديث دفتر الأسرة والأرصدة. لا يمكن التراجع عن الحذف.",
                        class_name="my-4 text-sm leading-7 text-[#7c8178]",
                    ),
                ),
                notice(),
                rx.el.div(
                    rx.el.button(
                        rx.cond(
                            S.delete_kind == "account",
                            "إغلاق الحساب",
                            "تأكيد الحذف",
                        ),
                        on_click=S.confirm_delete,
                        class_name=rx.cond(
                            S.delete_kind == "account",
                            "rounded-xl bg-[#62704b] px-5 py-3 text-white hover:bg-[#4f5e3c]",
                            "rounded-xl bg-[#a26550] px-5 py-3 text-white hover:bg-[#89513e]",
                        ),
                    ),
                    rx.el.button(
                        rx.cond(
                            S.delete_kind == "account",
                            "إبقاء الحساب نشطًا",
                            "احتفاظ بالعنصر",
                        ),
                        on_click=S.close_editor,
                        class_name=SECONDARY,
                    ),
                    class_name="flex gap-3",
                ),
                role="alertdialog",
                aria_modal=True,
                aria_label=rx.cond(
                    S.delete_kind == "account",
                    "تأكيد إغلاق الحساب",
                    "تأكيد الحذف",
                ),
                class_name="w-full max-w-md rounded-2xl bg-[#fffdf8] p-6",
            ),
            class_name="fixed inset-0 z-50 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )
