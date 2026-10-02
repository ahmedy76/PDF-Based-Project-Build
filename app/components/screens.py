import reflex as rx
import reflex_xy

from app.states.auth import AuthState
from app.components.landing import landing_content
from app.components.member_access import member_access_panel
from app.components.bills import reminder_section, reminder_card
from app.states.bills import BillState as B
from app.states.categories import CategoryState as C
from app.states.ledger import LedgerState as S
from app.states.goals import GoalRow, GoalState as G
from app.states.debts import DebtRow, InstallmentRow, PaymentRow, DebtState as D
from app.components.ui import (
    BUTTON,
    SECONDARY,
    CARD,
    brand,
    field,
    select_field,
    section_title,
    empty,
    notice,
    shell,
    public_shell,
    metric,
    edit_actions,
    transaction_row,
    budget_card,
    currency_switcher,
)


def welcome() -> rx.Component:
    return public_shell(landing_content())


def auth_page(
    registering: bool, submit_handler: rx.event.EventType
) -> rx.Component:
    return public_shell(
        rx.el.div(
            rx.el.div(
                rx.icon(
                    "notebook-pen",
                    class_name="mx-auto mb-5 h-9 w-9 text-[#62704b]",
                ),
                rx.el.h1(
                    rx.cond(
                        registering,
                        "افتح صفحة جديدة لأسرتك",
                        "أهلًا بعودتك إلى الدفتر",
                    ),
                    class_name="text-center text-3xl font-bold",
                ),
                rx.el.p(
                    rx.cond(
                        registering,
                        "تفاصيل بسيطة، وبداية مطمئنة.",
                        "سجّل دخولك لمتابعة ميزانية البيت.",
                    ),
                    class_name="mb-7 mt-3 text-center text-[#7c8178]",
                ),
                rx.cond(
                    AuthState.error != "",
                    rx.el.p(
                        AuthState.error,
                        role="alert",
                        class_name="mb-4 rounded-xl bg-red-100 p-4 text-sm text-red-600",
                    ),
                ),
                rx.el.form(
                    rx.cond(registering, field("الاسم", "name")),
                    field("البريد الإلكتروني", "email", "email"),
                    field("كلمة المرور", "password", "password"),
                    rx.cond(
                        registering,
                        rx.el.div(
                            field("تأكيد كلمة المرور", "confirm", "password"),
                            rx.el.p(
                                "8 أحرف على الأقل. لا تشارك كلمة مرورك مع أحد.",
                                class_name="mt-2 text-xs text-[#7c8178]",
                            ),
                            rx.el.label(
                                rx.el.input(
                                    type="checkbox",
                                    name="terms",
                                    required=True,
                                    class_name="h-4 w-4 accent-[#62704b]",
                                ),
                                "أوافق على شروط الاستخدام والخصوصية أدناه",
                                class_name="mt-5 flex items-center gap-2 text-sm",
                            ),
                            rx.el.details(
                                rx.el.summary(
                                    "شروط الاستخدام والخصوصية",
                                    class_name="cursor-pointer text-sm text-[#62704b]",
                                ),
                                rx.el.p(
                                    "يُستخدم هذا الدفتر لتنظيم ميزانية الأسرة، وليس لتقديم استشارات مالية. يرى أعضاء الأسرة حساباتها ومعاملاتها وميزانياتها. لا تُشارك رابط الدعوة إلا مع صاحب البريد المحدد. تُحفظ بياناتك لخدمة حسابك، ولا يرسل التطبيق بريدًا أو يربط حسابات بنكية. احرص على صحة البيانات وعلى سرية كلمة المرور.",
                                    class_name="mt-3 text-xs leading-7 text-[#7c8178]",
                                ),
                                class_name="mt-4",
                            ),
                        ),
                    ),
                    rx.el.button(
                        rx.cond(
                            registering, "إنشاء حساب ودفتر أسرة", "تسجيل الدخول"
                        ),
                        type="submit",
                        class_name=BUTTON,
                    ),
                    on_submit=submit_handler,
                    class_name="flex flex-col gap-4",
                ),
                rx.el.a(
                    rx.cond(
                        registering,
                        "لديك حساب؟ سجّل الدخول",
                        "ليس لديك حساب؟ ابدأ الآن",
                    ),
                    href=rx.cond(registering, "/login", "/register"),
                    class_name="mt-6 block text-center text-sm text-[#62704b]",
                ),
                class_name=CARD,
            ),
            class_name="mx-auto max-w-lg",
        )
    )


def invite_panel() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("heart-handshake", class_name="h-7 w-7 text-[#62704b]"),
            rx.el.h2("التخطيط أجمل معًا", class_name="text-xl font-bold"),
            class_name="mb-3 flex items-center gap-3",
        ),
        rx.el.p(
            "أنشئ دعوة خاصة ببريد شريكك، ثم شارك الرابط معه بنفسك. لا نرسل بريدًا إلكترونيًا. صلاحية الدعوة 7 أيام.",
            class_name="mb-5 text-sm leading-7 text-[#7c8178]",
        ),
        rx.cond(
            S.owner,
            rx.el.form(
                field("البريد الإلكتروني للشريك", "email", "email"),
                rx.el.button(
                    rx.icon("link", class_name="h-4 w-4"),
                    "إنشاء دعوة قابلة للمشاركة",
                    type="submit",
                    class_name=BUTTON,
                ),
                on_submit=S.invite,
                class_name="flex flex-col gap-4",
            ),
            rx.el.p(
                "يمكن لمالك الأسرة إنشاء الدعوات وإلغاؤها.",
                class_name="text-sm text-[#7c8178]",
            ),
        ),
        rx.cond(
            S.invite_link != "",
            rx.el.div(
                rx.el.p(
                    "الرابط يظهر الآن فقط؛ احتفظ به وأرسله إلى صاحب البريد.",
                    class_name="mb-3 text-xs text-[#7c8178]",
                ),
                rx.el.code(
                    S.invite_link,
                    class_name="block break-all rounded-lg bg-[#eeece3] p-3 text-xs",
                    dir="ltr",
                ),
                rx.el.button(
                    rx.icon("copy", class_name="h-4 w-4"),
                    "نسخ رابط الدعوة الكامل",
                    on_click=rx.call_script(
                        f"navigator.clipboard.writeText(window.location.origin + {S.invite_link.to_string()})"
                    ),
                    class_name=SECONDARY,
                ),
                class_name="mt-5 space-y-3",
            ),
        ),
        class_name=CARD,
    )


def onboarding() -> rx.Component:
    return shell(
        rx.el.div(
            section_title(
                "أهلًا، هذه بداية التناغم",
                "تم إنشاء أسرتك وفئات الدخل والمصروف. الآن اختر أن تبدأ بمفردك أو مع شريكك.",
            ),
            invite_panel(),
            rx.el.a(
                "تخطي الآن، والانتقال إلى دفتري",
                rx.icon("arrow-left", class_name="h-4 w-4"),
                href="/dashboard",
                class_name="mt-6 inline-flex items-center gap-2 text-sm font-bold text-[#62704b]",
            ),
            class_name="mx-auto w-full max-w-2xl",
        )
    )


def harmony_ring() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.h2("تناغم الشهر", class_name="text-xl font-bold"),
            rx.el.span(
                "الدخل · المصروف · الادخار", class_name="text-xs text-[#7c8178]"
            ),
            class_name="flex flex-wrap items-center justify-between gap-3",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.icon(
                            "sprout", class_name="mb-2 h-6 w-6 text-[#62704b]"
                        ),
                        rx.el.span(
                            "صافي التوفير", class_name="text-xs text-[#7c8178]"
                        ),
                        rx.el.strong(
                            f"{S.saving} {S.view_currency}",
                            class_name="mt-2 text-3xl font-bold tabular-nums text-[#62704b]",
                        ),
                        rx.el.span(
                            f"{S.saving_rate}% من الدخل",
                            class_name="mt-2 text-xs text-[#7c8178]",
                        ),
                        class_name="flex h-48 w-48 flex-col items-center justify-center rounded-full border-[8px] border-[#aab78f]",
                    ),
                    class_name="rounded-full border-[8px] border-[#d8bf96] p-2",
                ),
                class_name="rounded-full border-[8px] border-[#dce2d0] p-2",
            ),
            class_name="flex justify-center py-7",
        ),
        rx.el.div(
            rx.el.p(
                f"الدخل  {S.income} {S.view_currency}",
                class_name="text-[#62704b]",
            ),
            rx.el.p(
                f"المصروف  {S.expense} {S.view_currency}",
                class_name="text-[#a27456]",
            ),
            class_name="flex flex-wrap justify-between gap-3 border-t border-[#e7e2d7] pt-4 text-sm font-semibold tabular-nums",
        ),
        rx.el.p(
            "أرقام هذا الشهر حتى اليوم. تتجدد مع كل معاملة.",
            class_name="mt-4 text-xs text-[#929686]",
        ),
        class_name=CARD,
    )


def dashboard() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    f"أهلًا {AuthState.name}،",
                    "لنلقِ نظرة هادئة على أموال البيت هذا الشهر.",
                ),
                rx.cond(
                    S.can_add_transactions,
                    rx.el.button(
                        rx.icon("plus", class_name="h-4 w-4"),
                        "تسجيل معاملة",
                        on_click=lambda: S.open_editor("transaction"),
                        class_name=BUTTON,
                    ),
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.cond(
                S.pending_count > 0,
                rx.el.a(
                    rx.icon("mail", class_name="h-5 w-5"),
                    f"لديك {S.pending_count} دعوة معلقة · متابعة الدعوات",
                    href="/settings",
                    class_name="mb-6 flex items-center gap-3 rounded-xl border border-[#dfd4b9] bg-[#f4eddb] p-4 text-sm text-[#91713d]",
                ),
            ),
            currency_switcher(),
            rx.el.div(
                metric("رصيد الحسابات النشطة", S.total, "wallet"),
                metric("دخل الشهر", S.income, "arrow-down-left"),
                metric("مصروف الشهر", S.expense, "arrow-up-right"),
                metric("صافي التوفير", S.saving, "sprout"),
                class_name="mb-4 grid grid-cols-2 gap-4 xl:grid-cols-4",
            ),
            rx.cond(
                S.has_archived_balance,
                rx.el.p(
                    f"أرصدة الحسابات المغلقة المسجّلة ({S.archived_total} {S.view_currency}) مفصولة عن رصيد الحسابات النشطة؛ لم تُنقل أو تختفِ الأموال بسبب الإغلاق.",
                    class_name="mb-6 rounded-xl border border-[#e2ded2] bg-[#fffdf8] px-4 py-3 text-sm leading-7 text-[#62704b]",
                ),
            ),
            rx.el.div(
                harmony_ring(),
                rx.el.section(
                    rx.el.div(
                        rx.el.h2(
                            "آخر صفحات الدفتر", class_name="text-xl font-bold"
                        ),
                        rx.el.a(
                            "كل المعاملات ←",
                            href="/transactions",
                            class_name="text-sm text-[#62704b]",
                        ),
                        class_name="mb-4 flex justify-between gap-3",
                    ),
                    rx.cond(
                        S.transactions.length() > 0,
                        rx.foreach(S.transactions[:5], transaction_row),
                        rx.el.div(
                            empty(
                                "دفترك ينتظر أول معاملة. أضف حسابًا ماليًا، ثم سجّل دخلك أو مصروفك."
                            ),
                            rx.el.a(
                                "إضافة حساب مالي",
                                href="/accounts",
                                class_name="mt-5 inline-block text-sm font-bold text-[#62704b]",
                            ),
                        ),
                    ),
                    class_name=CARD,
                ),
                class_name="mb-7 grid gap-6 lg:grid-cols-[0.85fr_1.4fr]",
            ),
            rx.el.div(reminder_section(), class_name="mb-7"),
            rx.el.a(
                rx.icon("target", class_name="h-5 w-5 text-[#62704b]"),
                rx.el.span(
                    "أهدافكم الادخارية · خصصوا مبالغ لأحلامكم يدويًا دون تغيير أرصدة الحسابات"
                ),
                rx.icon("arrow-left", class_name="h-4 w-4"),
                href="/goals",
                class_name="mb-7 flex w-full flex-wrap items-center gap-3 rounded-2xl border border-[#dce0ce] bg-[#edf0e3] px-5 py-4 text-sm font-bold text-[#62704b] hover:bg-[#e2e9d6]",
            ),
            rx.el.div(
                rx.el.h2("خطتنا لهذا الشهر", class_name="text-xl font-bold"),
                rx.el.a(
                    "إدارة الميزانيات ←",
                    href="/budgets",
                    class_name="text-sm text-[#62704b]",
                ),
                class_name="mb-4 flex justify-between",
            ),
            rx.cond(
                S.dashboard_budgets.length() > 0,
                rx.el.div(
                    rx.foreach(S.dashboard_budgets, budget_card),
                    class_name="grid gap-4 md:grid-cols-2 xl:grid-cols-3",
                ),
                empty("ضع أول حد شهري لفئة مصروف، لتعرف أين تقف من خطتك."),
            ),
        )
    )


def active_account_card(a: dict[str, str]) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.icon("wallet", class_name="h-6 w-6 text-[#62704b]"),
            rx.el.span(
                rx.match(
                    a["account_type"],
                    ("cash", "نقدي"),
                    ("bank", "بنكي"),
                    ("savings", "ادخار"),
                    ("credit_card", "بطاقة ائتمان"),
                    "آخر",
                ),
                class_name="w-fit rounded-full bg-[#eeeee4] px-3 py-1 text-xs text-[#7c8178]",
            ),
            class_name="mb-5 flex justify-between",
        ),
        rx.el.h3(a["name"], class_name="text-xl font-bold"),
        rx.el.div(
            rx.el.strong(a["balance"], class_name="text-3xl tabular-nums"),
            rx.el.span(a["currency"], class_name="text-sm text-[#7c8178]"),
            class_name="my-5 flex items-baseline gap-2",
        ),
        rx.el.div(
            edit_actions("account", a),
            class_name="border-t border-[#e8e4d8] pt-2",
        ),
        class_name=CARD,
        key=a["id"],
    )


def archived_account_card(a: dict[str, str]) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.icon("archive", class_name="h-5 w-5 text-[#7c8178]"),
            rx.el.span(
                "مغلق · للعرض التاريخي",
                class_name="w-fit rounded-full bg-[#eeece5] px-3 py-1 text-xs text-[#52604f]",
            ),
            class_name="mb-4 flex items-center justify-between gap-3",
        ),
        rx.el.h3(a["name"], class_name="text-xl font-bold text-[#27394a]"),
        rx.el.p("الرصيد المسجّل", class_name="mt-4 text-xs text-[#7c8178]"),
        rx.el.div(
            rx.el.strong(a["balance"], class_name="text-2xl tabular-nums"),
            rx.el.span(a["currency"], class_name="text-sm text-[#7c8178]"),
            class_name="mt-1 flex items-baseline gap-2",
        ),
        class_name="rounded-2xl border border-[#e2ded2] bg-[#f1f0e9] p-5 md:p-7",
        key=a["id"],
    )


def transfer_row(row: dict[str, str]) -> rx.Component:
    return rx.el.li(
        rx.el.div(
            rx.el.div(
                rx.icon(
                    "arrow-left-right", class_name="h-5 w-5 text-[#62704b]"
                ),
                rx.el.strong(
                    f"من {row['source']} إلى {row['destination']}",
                    class_name="break-words text-sm font-bold text-[#27394a]",
                ),
                class_name="flex min-w-0 items-center gap-3",
            ),
            rx.el.p(
                f"{row['transfer_date']} · {row['amount']} {row['currency']}",
                class_name="mt-2 text-sm tabular-nums text-[#62704b]",
            ),
            rx.cond(
                row["note"] != "",
                rx.el.p(
                    row["note"],
                    class_name="mt-2 break-words text-sm text-[#7c8178]",
                ),
            ),
            class_name="border-b border-[#eeebe2] py-4 last:border-0",
        ),
        key=row["id"],
    )


def transfer_form() -> rx.Component:
    return rx.cond(
        S.transfer_open,
        rx.el.div(
            rx.el.section(
                rx.el.div(
                    rx.el.h2(
                        "تحويل بين حسابين",
                        class_name="text-xl font-bold text-[#27394a]",
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-5 w-5"),
                        on_click=S.close_transfer,
                        aria_label="إغلاق نموذج التحويل",
                        class_name=SECONDARY,
                    ),
                    class_name="mb-5 flex items-center justify-between gap-3",
                ),
                rx.el.p(
                    "يُنقل المبلغ بين حسابين نشطين بالعملة نفسها. لا يُحسب التحويل دخلًا أو مصروفًا ولا يغيّر تقارير الميزانية.",
                    class_name="mb-5 rounded-xl bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
                ),
                rx.cond(
                    S.transfer_error != "",
                    rx.el.p(
                        S.transfer_error,
                        role="alert",
                        class_name="mb-4 rounded-xl bg-red-100 p-4 text-sm text-red-600",
                    ),
                ),
                rx.cond(
                    S.transfer_draft["source_account_id"] != "",
                    rx.el.form(
                        rx.el.label(
                            rx.el.span(
                                "من الحساب",
                                class_name="mb-2 block text-sm font-semibold text-[#465344]",
                            ),
                            rx.el.div(
                                rx.el.select(
                                    rx.foreach(
                                        S.accounts,
                                        lambda a: rx.el.option(
                                            f"{a['name']} · {a['currency']}",
                                            value=a["id"],
                                        ),
                                    ),
                                    name="source_account_id",
                                    default_value=S.transfer_draft[
                                        "source_account_id"
                                    ],
                                    on_change=S.change_transfer_source,
                                    required=True,
                                    class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pl-9 text-[#27394a] focus:outline-2 focus:outline-[#62704b]",
                                ),
                                rx.icon(
                                    "chevron-down",
                                    class_name="pointer-events-none absolute left-3 top-4 h-4 w-4 text-[#62704b]",
                                ),
                                class_name="relative",
                            ),
                            class_name="block",
                        ),
                        rx.el.label(
                            rx.el.span(
                                "إلى الحساب",
                                class_name="mb-2 block text-sm font-semibold text-[#465344]",
                            ),
                            rx.el.div(
                                rx.el.select(
                                    rx.foreach(
                                        S.transfer_destinations,
                                        lambda a: rx.el.option(
                                            f"{a['name']} · {a['currency']}",
                                            value=a["id"],
                                        ),
                                    ),
                                    name="destination_account_id",
                                    default_value=S.transfer_draft[
                                        "destination_account_id"
                                    ],
                                    key=S.transfer_draft["source_account_id"],
                                    required=True,
                                    class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pl-9 text-[#27394a] focus:outline-2 focus:outline-[#62704b]",
                                ),
                                rx.icon(
                                    "chevron-down",
                                    class_name="pointer-events-none absolute left-3 top-4 h-4 w-4 text-[#62704b]",
                                ),
                                class_name="relative",
                            ),
                            class_name="block",
                        ),
                        rx.el.p(
                            f"عملة التحويل: {S.transfer_currency}",
                            class_name="text-sm font-bold text-[#62704b]",
                        ),
                        rx.cond(
                            S.transfer_destinations.length() == 0,
                            rx.el.p(
                                "لا يوجد حساب وجهة نشط بهذه العملة؛ اختر مصدرًا آخر.",
                                class_name="text-sm text-[#a26550]",
                            ),
                        ),
                        field("المبلغ", "amount"),
                        field(
                            "تاريخ التحويل",
                            "transfer_date",
                            "date",
                            S.transfer_draft["transfer_date"],
                        ),
                        field("ملاحظة (اختياري)", "note", required=False),
                        rx.el.div(
                            rx.el.button(
                                "تأكيد التحويل",
                                type="submit",
                                disabled=S.transfer_destinations.length() == 0,
                                class_name=BUTTON,
                            ),
                            rx.el.button(
                                "إلغاء",
                                type="button",
                                on_click=S.close_transfer,
                                class_name=SECONDARY,
                            ),
                            class_name="flex flex-wrap gap-3",
                        ),
                        on_submit=S.save_transfer,
                        class_name="space-y-4",
                    ),
                    rx.el.p(
                        "تحتاج إلى حسابين نشطين ظاهرين لك بالعملة نفسها لإجراء التحويل.",
                        class_name="rounded-xl border border-[#e2ded2] bg-[#faf9f3] p-4 text-sm text-[#7c8178]",
                    ),
                ),
                role="dialog",
                aria_modal=True,
                aria_label="تحويل بين حسابين",
                class_name="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[#fffdf8] p-6",
            ),
            class_name="fixed inset-0 z-40 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )


def accounts() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "حسابات البيت",
                    "الأرصدة المسجّلة من المعاملات غير المحذوفة والتحويلات؛ إغلاق الحساب يحفظ تاريخه ويفصل رصيده عن مجموع الحسابات النشطة.",
                ),
                rx.el.div(
                    rx.cond(
                        S.can_add_transactions,
                        rx.el.button(
                            rx.icon("arrow-left-right", class_name="h-4 w-4"),
                            "تحويل بين حسابين",
                            on_click=S.open_transfer,
                            class_name=SECONDARY,
                        ),
                    ),
                    rx.el.button(
                        rx.icon("plus", class_name="h-4 w-4"),
                        "إضافة حساب",
                        on_click=lambda: S.open_editor("account"),
                        class_name=BUTTON,
                    ),
                    class_name="flex flex-wrap gap-2",
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.el.section(
                rx.el.h2(
                    "الحسابات النشطة", class_name="mb-4 text-xl font-bold"
                ),
                rx.cond(
                    S.accounts.length() > 0,
                    rx.el.div(
                        rx.foreach(S.accounts, active_account_card),
                        class_name="grid gap-5 md:grid-cols-2 xl:grid-cols-3",
                    ),
                    empty(
                        "لا توجد حسابات نشطة. أضف حسابًا لتسجيل معاملات جديدة."
                    ),
                ),
                class_name="mb-9",
            ),
            rx.el.section(
                rx.el.div(
                    rx.el.h2(
                        "الحسابات المغلقة", class_name="text-xl font-bold"
                    ),
                    rx.cond(
                        S.archived_accounts.length() > 0,
                        rx.el.span(
                            "الأرصدة المغلقة بعملاتها مبينة لكل حساب؛ لا تُجمع العملات المختلفة.",
                            class_name="text-sm text-[#7c8178]",
                        ),
                    ),
                    class_name="mb-4 flex flex-wrap items-center justify-between gap-3",
                ),
                rx.cond(
                    S.archived_accounts.length() > 0,
                    rx.el.div(
                        rx.foreach(S.archived_accounts, archived_account_card),
                        class_name="grid gap-5 md:grid-cols-2 xl:grid-cols-3",
                    ),
                    empty(
                        "لا توجد حسابات مغلقة. سيبقى تاريخ أي حساب تغلقه ظاهرًا هنا."
                    ),
                ),
            ),
            rx.el.section(
                rx.el.h2(
                    "سجل التحويلات",
                    class_name="text-xl font-bold text-[#27394a]",
                ),
                rx.el.p(
                    "حركة مستقلة عن سجل الدخل والمصروف؛ تُعرض فقط التحويلات بين حسابات يمكنك رؤيتها.",
                    class_name="mb-4 mt-1 text-sm text-[#7c8178]",
                ),
                rx.cond(
                    S.transfers.length() > 0,
                    rx.el.ul(
                        rx.foreach(S.transfers, transfer_row), class_name="px-5"
                    ),
                    empty("لا توجد تحويلات بين حساباتك الظاهرة بعد."),
                ),
                class_name="mt-9 rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-5 md:p-7",
            ),
            transfer_form(),
        )
    )


def recurring_card(row) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.el.div(
                rx.el.h3(
                    row["name"], class_name="text-lg font-bold text-[#27394a]"
                ),
                rx.el.p(
                    f"{row['category']} · {row['account']}",
                    class_name="mt-1 text-sm text-[#7c8178]",
                ),
            ),
            rx.el.span(
                row["status"],
                class_name=rx.cond(
                    row["active"] == "yes",
                    "w-fit rounded-lg bg-[#e9eddf] px-3 py-1 text-xs font-bold text-[#62704b]",
                    "w-fit rounded-lg bg-[#f1e7dd] px-3 py-1 text-xs font-bold text-[#a26550]",
                ),
            ),
            class_name="flex items-start justify-between gap-3",
        ),
        rx.el.p(
            f"{row['display_amount']} {row['currency']} · {row['frequency_label']}",
            class_name="mt-4 font-bold tabular-nums text-[#27394a]",
        ),
        rx.el.p(
            f"الاستحقاق القادم: {row['next_date']}",
            class_name="mt-1 text-sm text-[#7c8178]",
        ),
        rx.cond(
            row["end_date"] != "",
            rx.el.p(
                f"حتى {row['end_date']}",
                class_name="mt-1 text-xs text-[#7c8178]",
            ),
        ),
        rx.el.div(
            rx.cond(
                S.can_add_transactions,
                rx.el.button(
                    rx.icon("pencil", class_name="h-4 w-4"),
                    "تعديل",
                    on_click=lambda: S.open_editor("recurring", row["id"]),
                    class_name=SECONDARY,
                ),
            ),
            rx.cond(
                S.can_add_transactions,
                rx.el.button(
                    rx.cond(row["active"] == "yes", "إيقاف مؤقت", "استئناف"),
                    on_click=lambda: S.toggle_recurring(row["id"]),
                    class_name=SECONDARY,
                ),
            ),
            class_name="mt-5 flex flex-wrap gap-2 border-t border-[#eeebe2] pt-4",
        ),
        class_name=CARD,
        key=row["id"],
    )


def transactions() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "دفتر المعاملات", "التفاصيل الصغيرة تصنع الصورة الكاملة."
                ),
                rx.cond(
                    S.can_add_transactions,
                    rx.el.button(
                        rx.icon("plus", class_name="h-4 w-4"),
                        "معاملة جديدة",
                        on_click=lambda: S.open_editor("transaction"),
                        class_name=BUTTON,
                    ),
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.el.a(
                rx.icon("file-up", class_name="h-4 w-4"),
                "استيراد وتصدير CSV",
                href="/data-transfer",
                class_name="mb-5 inline-flex items-center gap-2 text-sm font-bold text-[#62704b] hover:underline",
            ),
            rx.el.details(
                rx.el.summary(
                    "تصفية الدفتر حسب النوع والحساب والفئة والفترة",
                    class_name="cursor-pointer text-sm font-bold text-[#62704b]",
                ),
                rx.el.form(
                    select_field(
                        "النوع",
                        "kind",
                        [
                            {"id": "", "name": "كل الأنواع"},
                            {"id": "income", "name": "دخل"},
                            {"id": "expense", "name": "مصروف"},
                        ],
                    ),
                    rx.el.label(
                        "الحساب",
                        rx.el.div(
                            rx.el.select(
                                rx.el.option("كل الحسابات", value=""),
                                rx.foreach(
                                    S.filter_account_options,
                                    lambda a: rx.el.option(
                                        a["name"], value=a["id"]
                                    ),
                                ),
                                name="account",
                                default_value=S.filter_account,
                                key=S.filter_account,
                                class_name="mt-2 w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3",
                            ),
                            rx.icon(
                                "chevron-down",
                                class_name="pointer-events-none absolute left-3 top-6 h-4 w-4",
                            ),
                            class_name="relative",
                        ),
                        class_name="text-sm",
                    ),
                    rx.el.label(
                        "الفئة",
                        rx.el.div(
                            rx.el.select(
                                rx.el.option("كل الفئات", value=""),
                                rx.foreach(
                                    S.filter_category_options,
                                    lambda c: rx.el.option(
                                        c["name"], value=c["id"]
                                    ),
                                ),
                                name="category",
                                class_name="mt-2 w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3",
                            ),
                            rx.icon(
                                "chevron-down",
                                class_name="pointer-events-none absolute left-3 top-6 h-4 w-4",
                            ),
                            class_name="relative",
                        ),
                        class_name="text-sm",
                    ),
                    field("من تاريخ", "start", "date", required=False),
                    field("إلى تاريخ", "end", "date", required=False),
                    rx.el.button(
                        "تطبيق الفلاتر", type="submit", class_name=BUTTON
                    ),
                    on_submit=S.apply_filters,
                    class_name="mt-5 grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-3",
                ),
                class_name="mb-5 rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-5",
            ),
            rx.el.div(
                rx.cond(
                    S.visible_transactions.length() > 0,
                    rx.foreach(S.visible_transactions, transaction_row),
                    empty("لا توجد معاملات تطابق هذه الفترة أو الفلاتر."),
                ),
                class_name=CARD,
            ),
            rx.el.section(
                rx.el.div(
                    rx.el.div(
                        rx.el.h2(
                            "المعاملات المتكررة",
                            class_name="text-xl font-bold text-[#27394a]",
                        ),
                        rx.el.p(
                            "تُسجّل المستحقات عند فتح الدفتر، لا في الخلفية",
                            class_name="mt-1 text-sm text-[#7c8178]",
                        ),
                    ),
                    rx.cond(
                        S.can_add_transactions,
                        rx.el.button(
                            rx.icon("plus", class_name="h-4 w-4"),
                            "معاملة متكررة جديدة",
                            on_click=lambda: S.open_editor("recurring"),
                            class_name=BUTTON,
                        ),
                    ),
                    class_name="mb-5 flex flex-wrap items-center justify-between gap-4",
                ),
                rx.cond(
                    S.recurring_rules.length() > 0,
                    rx.el.div(
                        rx.foreach(S.recurring_rules, recurring_card),
                        class_name="grid gap-4 md:grid-cols-2 xl:grid-cols-3",
                    ),
                    empty(
                        "لا توجد معاملات متكررة بعد. أضف قاعدة لجدولة دخلك أو مصروفك."
                    ),
                ),
                class_name="mt-8",
            ),
        )
    )


def goal_history(entry: dict[str, str]) -> rx.Component:
    return rx.el.li(
        rx.el.div(
            rx.el.span(
                rx.cond(entry["kind"] == "add", "تخصيص", "تحرير"),
                class_name=rx.cond(
                    entry["kind"] == "add",
                    "w-fit rounded-full bg-[#e9eddf] px-2 py-1 text-xs font-bold text-[#62704b]",
                    "w-fit rounded-full bg-[#f1e7dd] px-2 py-1 text-xs font-bold text-[#a27456]",
                ),
            ),
            rx.el.span(entry["date"], class_name="text-xs text-[#7c8178]"),
            class_name="flex items-center gap-3",
        ),
        rx.el.span(
            f"{entry['amount']} {S.currency}",
            class_name="font-bold tabular-nums",
        ),
        rx.cond(
            entry["note"] != "",
            rx.el.p(
                entry["note"],
                class_name="w-full break-words text-sm text-[#7c8178]",
            ),
        ),
        class_name="flex flex-wrap items-center justify-between gap-2 border-b border-[#eeebe2] py-3 last:border-0",
        key=entry["id"],
    )


def goal_card(row: GoalRow, archived: bool = False) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.el.div(
                rx.icon("target", class_name="h-6 w-6 text-[#62704b]"),
                rx.el.h3(
                    row["name"],
                    class_name="break-words text-xl font-bold text-[#27394a]",
                ),
                class_name="flex min-w-0 items-center gap-3",
            ),
            rx.el.span(
                row["status"],
                class_name="w-fit shrink-0 rounded-full bg-[#e9eddf] px-3 py-1 text-xs font-bold text-[#62704b]",
            ),
            class_name="flex flex-wrap items-center justify-between gap-3",
        ),
        rx.cond(
            row["description"] != "",
            rx.el.p(
                row["description"],
                class_name="mt-3 break-words text-sm leading-7 text-[#7c8178]",
            ),
        ),
        rx.cond(
            row["date"] != "",
            rx.el.p(
                f"التاريخ المستهدف: {row['date']}",
                class_name="mt-3 text-sm text-[#7c8178]",
            ),
        ),
        rx.el.div(
            rx.el.div(
                rx.el.span("مخصص يدويًا", class_name="text-xs text-[#7c8178]"),
                rx.el.strong(
                    f"{row['amount']} {S.currency}",
                    class_name="block text-xl font-bold tabular-nums text-[#27394a]",
                ),
            ),
            rx.el.div(
                rx.el.span("المستهدف", class_name="text-xs text-[#7c8178]"),
                rx.el.strong(
                    f"{row['target']} {S.currency}",
                    class_name="block font-bold tabular-nums",
                ),
            ),
            rx.el.div(
                rx.el.span("المتبقي", class_name="text-xs text-[#7c8178]"),
                rx.el.strong(
                    f"{row['remaining']} {S.currency}",
                    class_name="block font-bold tabular-nums",
                ),
            ),
            class_name="my-5 grid gap-4 rounded-xl bg-[#f6f4ec] p-4 sm:grid-cols-3",
        ),
        rx.el.progress(
            value=row["progress"],
            max="100",
            aria_label=f"تقدم هدف {row['name']}",
            class_name="h-2 w-full accent-[#62704b]",
        ),
        rx.el.p(
            f"{row['percent']}% من المستهدف",
            class_name="mt-2 text-left text-sm tabular-nums text-[#62704b]",
        ),
        rx.el.div(
            rx.el.details(
                rx.el.summary(
                    f"سجل التخصيصات ({row['history'].length()})",
                    class_name="cursor-pointer text-sm font-bold text-[#62704b]",
                ),
                rx.cond(
                    row["history"].length() > 0,
                    rx.el.ul(
                        rx.foreach(row["history"], goal_history),
                        class_name="mt-2",
                    ),
                    rx.el.p(
                        "لم تُخصّص مبالغ بعد.",
                        class_name="mt-3 text-sm text-[#7c8178]",
                    ),
                ),
            ),
            class_name="mt-5 border-t border-[#eeebe2] pt-4",
        ),
        rx.el.div(
            rx.cond(
                archived,
                rx.el.button(
                    rx.icon("archive-restore", class_name="h-4 w-4"),
                    "استعادة",
                    on_click=lambda: G.set_archived(row["id"], False),
                    class_name=SECONDARY,
                ),
                rx.el.div(
                    rx.el.button(
                        "تخصيص مبلغ",
                        on_click=lambda: G.open_allocation(row["id"], "add"),
                        class_name=BUTTON,
                    ),
                    rx.el.button(
                        "تحرير مبلغ",
                        on_click=lambda: G.open_allocation(
                            row["id"], "release"
                        ),
                        class_name=SECONDARY,
                    ),
                    rx.el.button(
                        "تعديل",
                        on_click=lambda: G.open_goal(row["id"]),
                        class_name=SECONDARY,
                    ),
                    rx.el.button(
                        "أرشفة",
                        on_click=lambda: G.set_archived(row["id"], True),
                        class_name=SECONDARY,
                    ),
                    class_name="flex flex-wrap gap-2",
                ),
            ),
            class_name="mt-5 flex flex-wrap gap-2",
        ),
        class_name=CARD,
        key=row["id"],
    )


def goal_dialog() -> rx.Component:
    return rx.cond(
        G.editor != "",
        rx.el.div(
            rx.el.section(
                rx.el.div(
                    rx.el.h2(
                        rx.cond(
                            G.editor == "goal",
                            rx.cond(G.edit_id == "", "هدف جديد", "تعديل الهدف"),
                            rx.cond(
                                G.allocation_kind == "add",
                                "تخصيص مبلغ",
                                "تحرير مبلغ",
                            ),
                        ),
                        class_name="text-xl font-bold",
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-5 w-5"),
                        on_click=G.close_editor,
                        aria_label="إغلاق",
                        class_name=SECONDARY,
                    ),
                    class_name="mb-5 flex items-center justify-between gap-3",
                ),
                rx.cond(
                    G.error != "",
                    rx.el.p(
                        G.error,
                        role="alert",
                        class_name="mb-4 rounded-xl bg-red-100 p-3 text-sm text-red-600",
                    ),
                ),
                rx.el.p(
                    "المبالغ هنا مخصصة يدويًا فقط، وليست إيداعًا أو تحويلًا. لا تتغير أرصدة الحسابات أو التدفقات النقدية.",
                    class_name="mb-5 rounded-xl bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
                ),
                rx.cond(
                    G.editor == "goal",
                    rx.el.form(
                        field("اسم الهدف", "name", default=G.draft["name"]),
                        field(
                            "المبلغ المستهدف",
                            "target_amount",
                            default=G.draft["target_amount"],
                        ),
                        field(
                            "تاريخ مستهدف (اختياري)",
                            "target_date",
                            "date",
                            G.draft["target_date"],
                            required=False,
                        ),
                        field(
                            "وصف أو ملاحظات (اختياري)",
                            "description",
                            default=G.draft["description"],
                            required=False,
                        ),
                        rx.el.p(
                            "سمّه كما تشاء؛ مثل صندوق للطوارئ أو رحلة عائلية.",
                            class_name="text-xs text-[#7c8178]",
                        ),
                        rx.el.button(
                            "حفظ الهدف", type="submit", class_name=BUTTON
                        ),
                        on_submit=G.save_goal,
                        key=G.edit_id,
                        class_name="space-y-4",
                    ),
                    rx.el.form(
                        rx.el.p(
                            G.allocation_name,
                            class_name="font-bold text-[#27394a]",
                        ),
                        field("المبلغ", "amount"),
                        field("ملاحظة (اختياري)", "note", required=False),
                        rx.el.button(
                            rx.cond(
                                G.allocation_kind == "add",
                                "تأكيد التخصيص",
                                "تأكيد التحرير",
                            ),
                            type="submit",
                            class_name=BUTTON,
                        ),
                        on_submit=G.save_allocation,
                        key=f"{G.edit_id}-{G.allocation_kind}",
                        class_name="space-y-4",
                    ),
                ),
                role="dialog",
                aria_modal=True,
                aria_label="إدارة هدف الادخار",
                class_name="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[#fffdf8] p-6",
            ),
            class_name="fixed inset-0 z-40 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )


def goals() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "أهداف الادخار",
                    "مساحة للأحلام التي تخططون لها معًا، خطوة صغيرة في كل مرة.",
                ),
                rx.el.button(
                    rx.icon("plus", class_name="h-4 w-4"),
                    "هدف جديد",
                    on_click=lambda: G.open_goal(),
                    class_name=BUTTON,
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.el.div(
                rx.icon("info", class_name="h-5 w-5 shrink-0"),
                rx.el.p(
                    f"هذه المبالغ مقومة بعملة الأسرة الأساسية {S.currency} وتُخصّص يدويًا للمتابعة فقط، وليست إيداعات أو تحويلات؛ لا تتغير أرصدة الحسابات أو التدفقات النقدية أو أرقام الدخل والمصروف."
                ),
                class_name="mb-6 flex gap-3 rounded-xl border border-[#dce0ce] bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
            ),
            rx.cond(
                G.error != "",
                rx.el.p(
                    G.error,
                    role="alert",
                    class_name="mb-5 rounded-xl bg-red-100 p-4 text-sm text-red-600",
                ),
            ),
            rx.cond(
                G.message != "",
                rx.el.p(
                    G.message,
                    role="status",
                    class_name="mb-5 rounded-xl bg-[#e9eddf] p-4 text-sm text-[#62704b]",
                ),
            ),
            rx.el.section(
                rx.el.div(
                    rx.el.h2("الأهداف النشطة", class_name="text-xl font-bold"),
                    rx.el.span(
                        f"{G.active_count} أهداف · {G.completed_count} مكتملة",
                        class_name="text-sm text-[#7c8178]",
                    ),
                    class_name="mb-5 flex flex-wrap items-center justify-between gap-3",
                ),
                rx.cond(
                    G.goals.length() > 0,
                    rx.el.div(
                        rx.foreach(G.goals, goal_card),
                        class_name="grid gap-5 lg:grid-cols-2",
                    ),
                    empty(
                        "لم تضف هدفًا بعد. ابدأ باسم ومبلغ مستهدف، ثم تابع تخصيصاتك اليدوية."
                    ),
                ),
                class_name="mb-10",
            ),
            rx.el.section(
                rx.el.h2(
                    "الأهداف المؤرشفة", class_name="mb-2 text-xl font-bold"
                ),
                rx.el.p(
                    "تبقى تفاصيل الأهداف وسجل تخصيصاتها محفوظة، ويمكن استعادتها في أي وقت.",
                    class_name="mb-5 text-sm text-[#7c8178]",
                ),
                rx.cond(
                    G.archived_goals.length() > 0,
                    rx.el.div(
                        rx.foreach(
                            G.archived_goals, lambda row: goal_card(row, True)
                        ),
                        class_name="grid gap-5 lg:grid-cols-2",
                    ),
                    empty("لا توجد أهداف مؤرشفة."),
                ),
            ),
            goal_dialog(),
        )
    )


def debt_installment(item: InstallmentRow) -> rx.Component:
    return rx.el.li(
        rx.el.div(
            rx.el.span(
                f"قسط {item['sequence']} · {item['due']}",
                class_name="font-semibold text-[#27394a]",
            ),
            rx.el.span(
                item["status"],
                class_name=rx.cond(
                    item["status"] == "متأخر",
                    "w-fit rounded-full bg-[#f1e7dd] px-2 py-1 text-xs font-bold text-[#a26550]",
                    rx.cond(
                        item["status"] == "مدفوع",
                        "w-fit rounded-full bg-[#e9eddf] px-2 py-1 text-xs font-bold text-[#62704b]",
                        "w-fit rounded-full bg-[#f4eddb] px-2 py-1 text-xs font-bold text-[#b48861]",
                    ),
                ),
            ),
            class_name="flex flex-wrap items-center justify-between gap-2",
        ),
        rx.el.p(
            f"القسط {item['amount']} · المدفوع {item['paid']} · المتبقي {item['remaining']} {S.currency}",
            class_name="mt-2 text-sm tabular-nums text-[#7c8178]",
        ),
        class_name="border-b border-[#eeebe2] py-3 last:border-0",
    )


def debt_payment(
    item: PaymentRow, debt_id: str, archived: bool
) -> rx.Component:
    return rx.el.li(
        rx.el.div(
            rx.el.span(
                f"{item['date']} · {item['amount']} {S.currency}",
                class_name="font-semibold tabular-nums",
            ),
            rx.cond(
                item["voided"],
                rx.el.span(
                    "ملغاة",
                    class_name="w-fit rounded-full bg-[#f1e7dd] px-2 py-1 text-xs text-[#a26550]",
                ),
                rx.cond(
                    archived,
                    rx.el.span("مسجلة", class_name="text-xs text-[#62704b]"),
                    rx.el.button(
                        "إلغاء الدفعة",
                        on_click=lambda: D.ask_void(debt_id, item["id"]),
                        class_name="text-xs font-bold text-[#a26550] hover:underline",
                    ),
                ),
            ),
            class_name="flex flex-wrap items-center justify-between gap-2",
        ),
        rx.cond(
            item["note"] != "",
            rx.el.p(
                item["note"],
                class_name="mt-1 break-words text-sm text-[#7c8178]",
            ),
        ),
        class_name="border-b border-[#eeebe2] py-3 last:border-0",
    )


def debt_card(row: DebtRow, archived: bool = False) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.el.div(
                rx.icon("hand-coins", class_name="h-6 w-6 text-[#62704b]"),
                rx.el.h3(
                    row["title"],
                    class_name="break-words text-xl font-bold text-[#27394a]",
                ),
                class_name="flex min-w-0 items-center gap-3",
            ),
            rx.el.div(
                rx.el.span(
                    rx.cond(row["direction"] == "payable", "علينا", "لنا"),
                    class_name="w-fit rounded-full bg-[#e9eddf] px-3 py-1 text-xs font-bold text-[#62704b]",
                ),
                rx.el.span(
                    row["status"],
                    class_name=rx.cond(
                        row["status"] == "متأخر",
                        "w-fit rounded-full bg-[#f1e7dd] px-3 py-1 text-xs font-bold text-[#a26550]",
                        rx.cond(
                            row["status"] == "مدفوع",
                            "w-fit rounded-full bg-[#e9eddf] px-3 py-1 text-xs font-bold text-[#62704b]",
                            "w-fit rounded-full bg-[#f4eddb] px-3 py-1 text-xs font-bold text-[#9a7945]",
                        ),
                    ),
                ),
                class_name="flex flex-wrap gap-2",
            ),
            class_name="flex flex-wrap items-start justify-between gap-3",
        ),
        rx.el.p(
            f"الطرف الآخر: {row['counterparty']}",
            class_name="mt-4 break-words text-sm text-[#7c8178]",
        ),
        rx.cond(
            row["note"] != "",
            rx.el.p(
                row["note"],
                class_name="mt-2 break-words text-sm text-[#7c8178]",
            ),
        ),
        rx.el.div(
            rx.el.div(
                rx.el.span("أصل الدين", class_name="text-xs text-[#7c8178]"),
                rx.el.strong(
                    row["principal"], class_name="block font-bold tabular-nums"
                ),
            ),
            rx.el.div(
                rx.el.span("المدفوع", class_name="text-xs text-[#7c8178]"),
                rx.el.strong(
                    row["paid"],
                    class_name="block font-bold tabular-nums text-[#62704b]",
                ),
            ),
            rx.el.div(
                rx.el.span("المتبقي", class_name="text-xs text-[#7c8178]"),
                rx.el.strong(
                    row["remaining"], class_name="block font-bold tabular-nums"
                ),
            ),
            class_name="my-5 grid grid-cols-3 gap-3 rounded-xl bg-[#f6f4ec] p-4 text-sm",
        ),
        rx.el.p(
            f"المتأخر: {row['overdue']} {S.currency}",
            class_name="text-sm font-semibold tabular-nums text-[#a26550]",
        ),
        rx.cond(
            row["next_due"] != "",
            rx.el.p(
                f"أول قسط غير مسدد: {row['next_due']}",
                class_name="mt-1 text-sm text-[#b48861]",
            ),
        ),
        rx.el.details(
            rx.el.summary(
                f"جدول الأقساط ({row['installments'].length()})",
                class_name="cursor-pointer text-sm font-bold text-[#62704b]",
            ),
            rx.el.ol(
                rx.foreach(row["installments"], debt_installment),
                class_name="mt-2",
            ),
            class_name="mt-5 border-t border-[#eeebe2] pt-4",
        ),
        rx.el.details(
            rx.el.summary(
                f"سجل الدفعات ({row['history'].length()})",
                class_name="cursor-pointer text-sm font-bold text-[#62704b]",
            ),
            rx.cond(
                row["history"].length() > 0,
                rx.el.ul(
                    rx.foreach(
                        row["history"],
                        lambda item: debt_payment(item, row["id"], archived),
                    ),
                    class_name="mt-2",
                ),
                rx.el.p(
                    "لا دفعات مسجلة.", class_name="mt-3 text-sm text-[#7c8178]"
                ),
            ),
            class_name="mt-4 border-t border-[#eeebe2] pt-4",
        ),
        rx.el.div(
            rx.cond(
                archived,
                rx.el.button(
                    rx.icon("archive-restore", class_name="h-4 w-4"),
                    "استعادة",
                    on_click=lambda: D.set_archived(row["id"], False),
                    class_name=SECONDARY,
                ),
                rx.el.div(
                    rx.cond(
                        row["remaining"] != "0.0000",
                        rx.el.button(
                            "تسجيل دفعة",
                            on_click=lambda: D.open_payment(row["id"]),
                            class_name=BUTTON,
                        ),
                    ),
                    rx.el.button(
                        "تعديل",
                        on_click=lambda: D.open_debt(row["id"]),
                        class_name=SECONDARY,
                    ),
                    rx.el.button(
                        "أرشفة",
                        on_click=lambda: D.set_archived(row["id"], True),
                        class_name=SECONDARY,
                    ),
                    class_name="flex flex-wrap gap-2",
                ),
            ),
            class_name="mt-5 border-t border-[#eeebe2] pt-4",
        ),
        class_name=CARD,
        key=row["id"],
    )


def debt_dialog() -> rx.Component:
    return rx.cond(
        D.editor != "",
        rx.el.div(
            rx.el.section(
                rx.el.div(
                    rx.el.h2(
                        rx.match(
                            D.editor,
                            (
                                "debt",
                                rx.cond(
                                    D.edit_id == "", "دين جديد", "تعديل الدين"
                                ),
                            ),
                            ("payment", "تسجيل دفعة"),
                            "تأكيد إلغاء الدفعة",
                        ),
                        class_name="text-xl font-bold",
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-5 w-5"),
                        on_click=D.close_editor,
                        aria_label="إغلاق",
                        class_name=SECONDARY,
                    ),
                    class_name="mb-5 flex items-center justify-between gap-3",
                ),
                rx.cond(
                    D.error != "",
                    rx.el.p(
                        D.error,
                        role="alert",
                        class_name="mb-4 rounded-xl bg-red-100 p-3 text-sm text-red-600",
                    ),
                ),
                rx.el.p(
                    "الدفعات هنا سجل يدوي للمتابعة؛ لا تُنشئ معاملات ولا تغيّر أرصدة الحسابات. سجّل التحويل الفعلي منفصلًا في دفتر المعاملات عند الحاجة لتجنب العد المزدوج.",
                    class_name="mb-5 rounded-xl bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
                ),
                rx.match(
                    D.editor,
                    (
                        "debt",
                        rx.el.form(
                            field(
                                "عنوان الدين", "title", default=D.draft["title"]
                            ),
                            select_field(
                                "الاتجاه",
                                "direction",
                                [
                                    {"id": "payable", "name": "علينا"},
                                    {"id": "receivable", "name": "لنا"},
                                ],
                                D.draft["direction"],
                            ),
                            field(
                                "الطرف الآخر",
                                "counterparty",
                                default=D.draft["counterparty"],
                            ),
                            field(
                                "أصل الدين",
                                "principal",
                                default=D.draft["principal"],
                            ),
                            field(
                                "موعد أول قسط",
                                "first_due_date",
                                "date",
                                D.draft["first_due_date"],
                            ),
                            field(
                                "عدد الأقساط (1–120)",
                                "installment_count",
                                "number",
                                D.draft["installment_count"],
                            ),
                            field(
                                "ملاحظة (اختياري)",
                                "note",
                                default=D.draft["note"],
                                required=False,
                            ),
                            rx.cond(
                                D.edit_id != "",
                                rx.el.p(
                                    "بعد تسجيل أي دفعة، حتى الملغاة، يمكن تعديل العنوان والطرف والملاحظة فقط.",
                                    class_name="text-xs leading-6 text-[#7c8178]",
                                ),
                            ),
                            rx.el.button(
                                "حفظ الدين", type="submit", class_name=BUTTON
                            ),
                            on_submit=D.save_debt,
                            key=D.edit_id,
                            class_name="space-y-4",
                        ),
                    ),
                    (
                        "payment",
                        rx.el.form(
                            field("المبلغ", "amount"),
                            field("تاريخ الدفعة", "paid_on", "date", D.today),
                            field("ملاحظة (اختياري)", "note", required=False),
                            rx.el.button(
                                "تأكيد تسجيل الدفعة",
                                type="submit",
                                class_name=BUTTON,
                            ),
                            on_submit=D.save_payment,
                            key=D.edit_id,
                            class_name="space-y-4",
                        ),
                    ),
                    rx.el.div(
                        rx.el.p(
                            "هل تريد إلغاء هذه الدفعة؟ ستبقى في السجل بوسم ملغاة، وتُعاد حسابات الأقساط والمستحقات دونها.",
                            class_name="mb-5 text-sm leading-7 text-[#7c8178]",
                        ),
                        rx.el.div(
                            rx.el.button(
                                "نعم، إلغاء الدفعة",
                                on_click=D.confirm_void,
                                class_name=BUTTON,
                            ),
                            rx.el.button(
                                "الاحتفاظ بالدفعة",
                                on_click=D.close_editor,
                                class_name=SECONDARY,
                            ),
                            class_name="flex flex-wrap gap-3",
                        ),
                    ),
                ),
                role=rx.cond(D.editor == "void", "alertdialog", "dialog"),
                aria_modal=True,
                aria_label="إدارة الديون والدفعات",
                class_name="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[#fffdf8] p-6",
            ),
            class_name="fixed inset-0 z-50 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )


def debts() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "الديون والأقساط",
                    "سجّل ما علينا وما لنا، وتابع الأقساط والدفعات معًا.",
                ),
                rx.el.button(
                    rx.icon("plus", class_name="h-4 w-4"),
                    "دين جديد",
                    on_click=lambda: D.open_debt(),
                    class_name=BUTTON,
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.el.div(
                rx.icon("info", class_name="h-5 w-5 shrink-0"),
                rx.el.p(
                    f"الديون والأقساط مقومة بعملة الأسرة الأساسية {S.currency} فقط. هذا سجل يدوي: لا ننشئ معاملات أو نغيّر الأرصدة والتدفقات. سجّل الدفع أو القبض الفعلي منفصلًا في دفتر المعاملات دون تكرار."
                ),
                class_name="mb-6 flex gap-3 rounded-xl border border-[#dce0ce] bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
            ),
            rx.cond(
                D.error != "",
                rx.el.p(
                    D.error,
                    role="alert",
                    class_name="mb-5 rounded-xl bg-red-100 p-4 text-sm text-red-600",
                ),
            ),
            rx.cond(
                D.message != "",
                rx.el.p(
                    D.message,
                    role="status",
                    class_name="mb-5 rounded-xl bg-[#e9eddf] p-4 text-sm text-[#62704b]",
                ),
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.span(
                        "المتبقي علينا", class_name="text-sm text-[#7c8178]"
                    ),
                    rx.el.strong(
                        f"{D.payable_total} {S.currency}",
                        class_name="mt-3 block text-xl font-bold tabular-nums",
                    ),
                    rx.el.p(
                        f"{D.payable_overdue_count} ديون متأخرة",
                        class_name="mt-2 text-sm text-[#a26550]",
                    ),
                    class_name=CARD,
                ),
                rx.el.div(
                    rx.el.span(
                        "المتبقي لنا", class_name="text-sm text-[#7c8178]"
                    ),
                    rx.el.strong(
                        f"{D.receivable_total} {S.currency}",
                        class_name="mt-3 block text-xl font-bold tabular-nums",
                    ),
                    rx.el.p(
                        f"{D.receivable_overdue_count} ديون متأخرة",
                        class_name="mt-2 text-sm text-[#a26550]",
                    ),
                    class_name=CARD,
                ),
                rx.el.div(
                    rx.el.span(
                        "إجمالي الديون المتأخرة",
                        class_name="text-sm text-[#7c8178]",
                    ),
                    rx.el.strong(
                        D.overdue_count,
                        class_name="mt-4 block text-3xl font-bold text-[#a26550]",
                    ),
                    class_name=CARD,
                ),
                class_name="mb-7 grid gap-4 sm:grid-cols-3",
            ),
            rx.el.div(
                rx.el.button(
                    "الكل",
                    on_click=lambda: D.set_filter("all"),
                    class_name=rx.cond(
                        D.filter_direction == "all", BUTTON, SECONDARY
                    ),
                ),
                rx.el.button(
                    "علينا",
                    on_click=lambda: D.set_filter("payable"),
                    class_name=rx.cond(
                        D.filter_direction == "payable", BUTTON, SECONDARY
                    ),
                ),
                rx.el.button(
                    "لنا",
                    on_click=lambda: D.set_filter("receivable"),
                    class_name=rx.cond(
                        D.filter_direction == "receivable", BUTTON, SECONDARY
                    ),
                ),
                class_name="mb-5 flex flex-wrap gap-2",
            ),
            rx.el.section(
                rx.el.h2("الديون النشطة", class_name="mb-4 text-xl font-bold"),
                rx.cond(
                    D.visible_debts.length() > 0,
                    rx.el.div(
                        rx.foreach(D.visible_debts, lambda row: debt_card(row)),
                        class_name="grid items-start gap-5 lg:grid-cols-2",
                    ),
                    empty(
                        "لا توجد ديون في هذا التصنيف. أضف دينًا لتبدأ المتابعة."
                    ),
                ),
                class_name="mb-10",
            ),
            rx.el.section(
                rx.el.h2(
                    "الديون المؤرشفة", class_name="mb-2 text-xl font-bold"
                ),
                rx.el.p(
                    "تبقى الأقساط وسجلات الدفعات محفوظة ويمكن استعادة الدين.",
                    class_name="mb-5 text-sm text-[#7c8178]",
                ),
                rx.cond(
                    D.archived_debts.length() > 0,
                    rx.el.div(
                        rx.foreach(
                            D.archived_debts, lambda row: debt_card(row, True)
                        ),
                        class_name="grid items-start gap-5 lg:grid-cols-2",
                    ),
                    empty("لا توجد ديون مؤرشفة."),
                ),
            ),
            rx.el.div(reminder_section(), class_name="mt-8"),
            debt_dialog(),
        )
    )


def budgets() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "مساحة لكل احتياج",
                    "ميزانيات شهرية مرنة، وخطوات أقرب إلى التوازن.",
                ),
                rx.cond(
                    S.can_edit_budgets,
                    rx.el.button(
                        rx.icon("plus", class_name="h-4 w-4"),
                        "ميزانية جديدة",
                        on_click=lambda: S.open_editor("budget"),
                        class_name=BUTTON,
                    ),
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            currency_switcher(),
            rx.el.p(
                f"الميزانيات المعروضة بعملة {S.view_currency} فقط؛ يُحتسب إنفاق الحسابات بهذه العملة دون تحويل.",
                class_name="mb-4 text-sm text-[#62704b]",
            ),
            rx.el.form(
                field("شهر الميزانية", "month", "month", S.budget_month),
                rx.el.button("عرض الشهر", type="submit", class_name=SECONDARY),
                on_submit=S.change_month,
                class_name="mb-6 flex flex-wrap items-end gap-3",
            ),
            rx.cond(
                S.budgets.length() > 0,
                rx.el.div(
                    rx.foreach(S.budgets, budget_card),
                    class_name="grid gap-5 md:grid-cols-2 xl:grid-cols-3",
                ),
                empty(
                    "لم تضع حدودًا لهذا الشهر بعد. اختر فئة مصروف وحدّد المبلغ المناسب لأسرتك."
                ),
            ),
        )
    )


def reports() -> rx.Component:
    return shell(
        rx.el.div(
            section_title(
                "الصورة الأوضح",
                "تأمل عادات البيت المالية، وخطط للشهر القادم بثقة.",
            ),
            currency_switcher(),
            rx.el.div(
                rx.el.button(
                    "الشهر الحالي",
                    on_click=lambda: S.set_period("current"),
                    class_name=rx.cond(
                        S.period == "current", BUTTON, SECONDARY
                    ),
                ),
                rx.el.button(
                    "الشهر السابق",
                    on_click=lambda: S.set_period("previous"),
                    class_name=rx.cond(
                        S.period == "previous", BUTTON, SECONDARY
                    ),
                ),
                rx.el.button(
                    "آخر 3 أشهر",
                    on_click=lambda: S.set_period("three"),
                    class_name=rx.cond(S.period == "three", BUTTON, SECONDARY),
                ),
                class_name="mb-5 flex flex-wrap gap-2",
            ),
            rx.el.form(
                field("من", "start", "date", S.report_start, required=False),
                field("إلى", "end", "date", S.report_end, required=False),
                rx.el.button(
                    rx.icon("calendar-range", class_name="h-4 w-4"),
                    "عرض الفترة",
                    type="submit",
                    class_name=rx.cond(S.period == "custom", BUTTON, SECONDARY),
                ),
                rx.el.p(
                    "يمكن عرض فترة مخصصة بحد أقصى 366 يومًا شاملة يومَي البداية والنهاية، وحتى اليوم فقط.",
                    class_name="w-full text-xs leading-6 text-[#7c8178]",
                ),
                on_submit=S.set_custom_period,
                key=f"{S.report_start}-{S.report_end}",
                class_name="mb-5 flex flex-wrap items-end gap-3 rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-5 [&>label]:w-full sm:[&>label]:w-auto sm:[&>label]:min-w-44",
            ),
            rx.el.div(
                rx.icon("calendar-days", class_name="h-5 w-5 text-[#62704b]"),
                rx.el.p(
                    "الفترة المعروضة في النتائج:",
                    rx.el.strong(
                        S.report_range_label,
                        class_name="mr-2 font-bold tabular-nums text-[#27394a]",
                    ),
                    class_name="text-sm text-[#465344]",
                ),
                class_name="mb-6 flex flex-wrap items-center gap-2 rounded-xl border border-[#dce0ce] bg-[#edf0e3] px-4 py-3",
            ),
            rx.el.div(
                metric("إجمالي الدخل", S.report_income, "arrow-down-left"),
                metric("إجمالي المصروف", S.report_expense, "arrow-up-right"),
                metric("صافي التوفير", S.report_saving, "sprout"),
                class_name="mb-6 grid gap-4 sm:grid-cols-3",
            ),
            rx.el.div(
                rx.el.section(
                    rx.el.h2(
                        "أين ذهب الإنفاق؟", class_name="mb-5 text-xl font-bold"
                    ),
                    reflex_xy.chart(
                        reflex_xy.bar("category", "amount", color="#a8b28f"),
                        reflex_xy.x_axis(label="فئة المصروف"),
                        reflex_xy.y_axis(label="المبلغ"),
                        reflex_xy.modebar(False),
                        reflex_xy.interaction_config(navigation=False),
                        data=S.spending_data,
                        height="340px",
                        class_name="w-full min-w-[280px]",
                    ),
                    class_name=CARD,
                ),
                rx.el.section(
                    rx.el.h2(
                        "إيقاع الدخل والمصروف",
                        class_name="mb-5 text-xl font-bold",
                    ),
                    reflex_xy.chart(
                        reflex_xy.line(
                            "day",
                            "income",
                            name="الدخل",
                            color="#62704b",
                            width=2.5,
                        ),
                        reflex_xy.line(
                            "day",
                            "expense",
                            name="المصروف",
                            color="#b48861",
                            width=2.5,
                        ),
                        reflex_xy.x_axis(label="التاريخ"),
                        reflex_xy.y_axis(label="المبلغ"),
                        reflex_xy.legend(),
                        reflex_xy.modebar(False),
                        reflex_xy.interaction_config(navigation=False),
                        data=S.trend_data,
                        height="340px",
                        class_name="w-full min-w-[280px]",
                    ),
                    class_name=CARD,
                ),
                class_name="grid w-full min-w-0 gap-6 xl:grid-cols-2",
            ),
            rx.el.p(
                f"البيانات من المعاملات المسجلة بعملة {S.view_currency} فقط دون تحويل عملات. الفترة الحالية تمتد حتى اليوم؛ الأصفار تعني عدم وجود حركة.",
                class_name="mt-5 text-sm leading-7 text-[#7c8178]",
            ),
        )
    )


def notifications() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "رسائل من الدفتر",
                    "مستجدات الأسرة وتنبيهات تساعدك على البقاء ضمن الخطة.",
                ),
                rx.el.button(
                    "تحديد الكل كمقروء",
                    on_click=lambda: S.mark_read(""),
                    class_name=SECONDARY,
                ),
                class_name="flex flex-wrap items-start justify-between gap-3",
            ),
            rx.el.section(
                rx.el.h2(
                    "تذكيرات الاستحقاق داخل التطبيق",
                    class_name="mb-2 text-xl font-bold text-[#27394a]",
                ),
                rx.el.p(
                    "تُحدّث عند زيارة الدفتر والإشعارات والديون والفواتير فقط، ولا نرسل بريدًا أو نعمل في الخلفية.",
                    class_name="mb-4 text-sm text-[#7c8178]",
                ),
                rx.cond(
                    B.reminders.length() > 0,
                    rx.el.div(
                        rx.foreach(B.reminders, reminder_card),
                        class_name="space-y-3",
                    ),
                    empty(
                        "لا توجد استحقاقات قريبة غير مسددة، أو أن تذكيراتك معطّلة."
                    ),
                ),
                class_name="mb-7",
            ),
            rx.cond(
                S.budget_alert_note != "",
                rx.el.p(
                    S.budget_alert_note,
                    class_name="my-3 text-sm text-[#62704b]",
                ),
            ),
            rx.cond(
                S.notifications.length() > 0,
                rx.el.div(
                    rx.foreach(
                        S.notifications,
                        lambda n: rx.el.article(
                            rx.el.div(
                                rx.icon(
                                    "bell", class_name="h-5 w-5 text-[#9a825b]"
                                ),
                                rx.el.div(
                                    rx.el.h2(
                                        n["title"], class_name="font-bold"
                                    ),
                                    rx.el.p(
                                        n["body"],
                                        class_name="mt-2 text-sm text-[#7c8178]",
                                    ),
                                    rx.el.p(
                                        n["date"],
                                        class_name="mt-2 text-xs text-[#929686]",
                                    ),
                                ),
                                class_name="flex items-start gap-4",
                            ),
                            rx.cond(
                                n["read"] == "no",
                                rx.el.button(
                                    "تحديد كمقروء",
                                    on_click=lambda: S.mark_read(n["id"]),
                                    class_name=SECONDARY,
                                ),
                                rx.el.span(
                                    "مقروء", class_name="text-xs text-[#7c8178]"
                                ),
                            ),
                            class_name=rx.cond(
                                n["read"] == "no",
                                "flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[#dadfc8] bg-[#f0f2e8] p-5",
                                "flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-5",
                            ),
                            key=n["id"],
                        ),
                    ),
                    class_name="space-y-3",
                ),
                empty(
                    "كل شيء هادئ هنا. ستظهر تنبيهات الميزانية ومعاملات الشريك عند حدوثها."
                ),
            ),
        )
    )


def category_row(row: dict[str, str]) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("tag", class_name="h-4 w-4 text-[#62704b]"),
            rx.el.span(row["name"], class_name="font-semibold text-[#27394a]"),
            class_name="flex min-w-0 items-center gap-3 break-words",
        ),
        rx.el.div(
            rx.el.button(
                rx.icon("pencil", class_name="h-4 w-4"),
                "تعديل الاسم",
                on_click=lambda: C.open_edit(row["id"]),
                class_name="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-bold text-[#62704b] hover:bg-[#edf0e5]",
            ),
            rx.el.button(
                rx.icon("archive", class_name="h-4 w-4"),
                "أرشفة",
                on_click=lambda: C.ask_archive(row["id"]),
                class_name="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-bold text-[#a26550] hover:bg-[#f5e9e3]",
            ),
            class_name="flex flex-wrap gap-1",
        ),
        class_name="flex flex-wrap items-center justify-between gap-3 border-b border-[#eeebe2] py-4 last:border-0",
        key=row["id"],
    )


def categories() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "فئات الأسرة",
                    "رتّب فئات الدخل والمصروف معًا. الأرشفة تُخفي الفئة من الخيارات الجديدة دون مسح تاريخها.",
                ),
                rx.el.a(
                    rx.icon("arrow-right", class_name="h-4 w-4"),
                    "العودة إلى الإعدادات",
                    href="/settings",
                    class_name=SECONDARY,
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.cond(
                C.message != "",
                rx.el.div(
                    rx.icon("info", class_name="h-5 w-5 shrink-0"),
                    rx.el.p(C.message),
                    role="status",
                    class_name="mb-5 flex items-center gap-3 rounded-xl border border-[#e0d7bc] bg-[#f6f0df] p-4 text-sm leading-7 text-[#786036]",
                ),
            ),
            rx.el.div(
                rx.el.section(
                    rx.el.h2(
                        "إضافة فئة جديدة", class_name="mb-2 text-xl font-bold"
                    ),
                    rx.el.p(
                        "لكل فئة اسم ونوع ثابت. يمكنك تعديل الاسم لاحقًا، لكن لا يمكن تغيير النوع.",
                        class_name="mb-5 text-sm leading-7 text-[#7c8178]",
                    ),
                    rx.el.form(
                        field("اسم الفئة", "name"),
                        select_field(
                            "نوع الفئة",
                            "kind",
                            [
                                {"id": "expense", "name": "مصروف"},
                                {"id": "income", "name": "دخل"},
                            ],
                        ),
                        rx.el.button(
                            rx.icon("plus", class_name="h-4 w-4"),
                            "إضافة الفئة",
                            type="submit",
                            class_name=BUTTON,
                        ),
                        on_submit=C.add,
                        class_name="flex flex-col gap-4",
                    ),
                    class_name=CARD,
                ),
                rx.el.div(
                    rx.el.section(
                        rx.el.div(
                            rx.icon(
                                "arrow-down-left",
                                class_name="h-5 w-5 text-[#62704b]",
                            ),
                            rx.el.h2(
                                "فئات الدخل", class_name="text-xl font-bold"
                            ),
                            class_name="mb-3 flex items-center gap-3",
                        ),
                        rx.cond(
                            C.income_categories.length() > 0,
                            rx.foreach(C.income_categories, category_row),
                            empty(
                                "لا توجد فئات دخل نشطة. أضف فئة لتصنيف الدخل القادم."
                            ),
                        ),
                        class_name=CARD,
                    ),
                    rx.el.section(
                        rx.el.div(
                            rx.icon(
                                "arrow-up-right",
                                class_name="h-5 w-5 text-[#a27456]",
                            ),
                            rx.el.h2(
                                "فئات المصروف", class_name="text-xl font-bold"
                            ),
                            class_name="mb-3 flex items-center gap-3",
                        ),
                        rx.cond(
                            C.expense_categories.length() > 0,
                            rx.foreach(C.expense_categories, category_row),
                            empty(
                                "لا توجد فئات مصروف نشطة. أضف فئة لتصنيف المصروفات والميزانيات."
                            ),
                        ),
                        class_name=CARD,
                    ),
                    class_name="space-y-5",
                ),
                class_name="grid items-start gap-6 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.4fr)]",
            ),
            rx.cond(
                C.editing_id != "",
                rx.el.div(
                    rx.el.section(
                        rx.el.div(
                            rx.el.h2(
                                "تعديل اسم الفئة",
                                class_name="text-xl font-bold",
                            ),
                            rx.el.button(
                                rx.icon("x", class_name="h-4 w-4"),
                                on_click=C.close_edit,
                                aria_label="إغلاق",
                                class_name=SECONDARY,
                            ),
                            class_name="mb-5 flex items-center justify-between",
                        ),
                        rx.el.p(
                            rx.cond(
                                C.editing_kind == "income",
                                "فئة دخل",
                                "فئة مصروف",
                            ),
                            class_name="mb-4 text-sm text-[#7c8178]",
                        ),
                        rx.el.form(
                            field(
                                "الاسم الجديد", "name", default=C.editing_name
                            ),
                            rx.el.p(
                                "يبقى نوع الفئة ثابتًا لحماية معاملات الأسرة وميزانياتها.",
                                class_name="text-xs leading-6 text-[#7c8178]",
                            ),
                            rx.el.div(
                                rx.el.button(
                                    "حفظ الاسم",
                                    type="submit",
                                    class_name=BUTTON,
                                ),
                                rx.el.button(
                                    "إلغاء",
                                    type="button",
                                    on_click=C.close_edit,
                                    class_name=SECONDARY,
                                ),
                                class_name="flex flex-wrap gap-3",
                            ),
                            on_submit=C.rename,
                            key=C.editing_id,
                            class_name="space-y-5",
                        ),
                        role="dialog",
                        aria_modal=True,
                        aria_label="تعديل اسم الفئة",
                        class_name="w-full max-w-md rounded-2xl bg-[#fffdf8] p-6",
                    ),
                    class_name="fixed inset-0 z-40 flex items-center justify-center bg-[#243747]/40 p-4",
                ),
            ),
            rx.cond(
                C.archive_id != "",
                rx.el.div(
                    rx.el.section(
                        rx.el.h2(
                            "تأكيد أرشفة الفئة", class_name="text-xl font-bold"
                        ),
                        rx.el.p(
                            f"هل تريد أرشفة «{C.archive_name}»؟ لن تظهر في المعاملات أو الميزانيات الجديدة، لكن سيبقى اسمها في السجلات السابقة.",
                            class_name="my-4 text-sm leading-7 text-[#7c8178]",
                        ),
                        rx.cond(
                            C.message != "",
                            rx.el.p(
                                C.message,
                                role="alert",
                                class_name="mb-4 rounded-xl bg-[#f6f0df] p-3 text-sm text-[#786036]",
                            ),
                        ),
                        rx.el.div(
                            rx.el.button(
                                "تأكيد الأرشفة",
                                on_click=C.confirm_archive,
                                class_name="rounded-xl bg-[#a26550] px-5 py-3 text-sm font-bold text-white hover:bg-[#89513e]",
                            ),
                            rx.el.button(
                                "احتفاظ بالفئة",
                                on_click=C.cancel_archive,
                                class_name=SECONDARY,
                            ),
                            class_name="flex flex-wrap gap-3",
                        ),
                        role="alertdialog",
                        aria_modal=True,
                        aria_label="تأكيد الأرشفة",
                        class_name="w-full max-w-md rounded-2xl bg-[#fffdf8] p-6",
                    ),
                    class_name="fixed inset-0 z-50 flex items-center justify-center bg-[#243747]/40 p-4",
                ),
            ),
        )
    )


def settings() -> rx.Component:
    return shell(
        rx.el.div(
            section_title(
                "إعدادات البيت",
                "أفراد الأسرة، دعوات المشاركة، وما تود أن يصلك من تنبيهات.",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.section(
                        rx.el.h2(
                            "حسابك وأسرتك", class_name="mb-4 text-xl font-bold"
                        ),
                        rx.el.p(AuthState.name, class_name="font-bold"),
                        rx.el.p(
                            AuthState.email,
                            class_name="mt-1 text-sm text-[#7c8178]",
                        ),
                        rx.el.form(
                            select_field(
                                "الأسرة النشطة",
                                "household",
                                S.households,
                                AuthState.selected_household,
                            ),
                            rx.el.button(
                                "الانتقال إلى الأسرة",
                                type="submit",
                                class_name=SECONDARY,
                            ),
                            on_submit=S.switch_household,
                            class_name="mt-5 flex flex-col gap-3",
                        ),
                        rx.el.a(
                            rx.icon("tags", class_name="h-5 w-5"),
                            "إدارة فئات الدخل والمصروف",
                            href="/categories",
                            class_name="mt-5 inline-flex items-center gap-2 rounded-xl border border-[#dce0ce] bg-[#edf0e3] px-4 py-3 text-sm font-bold text-[#62704b] hover:bg-[#e2e9d6]",
                        ),
                        rx.el.a(
                            rx.icon("file-up", class_name="h-5 w-5"),
                            "استيراد وتصدير بيانات CSV",
                            href="/data-transfer",
                            class_name="mt-3 inline-flex items-center gap-2 rounded-xl border border-[#dce0ce] bg-[#edf0e3] px-4 py-3 text-sm font-bold text-[#62704b] hover:bg-[#e2e9d6]",
                        ),
                        rx.el.a(
                            "قبول دعوة إلى أسرة",
                            href="/accept-invitation",
                            class_name="mt-5 block text-sm font-bold text-[#62704b]",
                        ),
                        rx.el.button(
                            rx.icon("log-out", class_name="h-4 w-4"),
                            "تسجيل الخروج",
                            on_click=AuthState.logout,
                            class_name="mt-6 flex items-center gap-2 text-sm text-[#a26550]",
                        ),
                        class_name=CARD,
                    ),
                    member_access_panel(),
                    rx.el.section(
                        rx.el.h2(
                            "إشعارات داخل التطبيق",
                            class_name="mb-2 text-xl font-bold",
                        ),
                        rx.el.p(
                            "هذه التفضيلات لا تُفعّل بريدًا أو إشعارات خارجية.",
                            class_name="mb-4 text-xs text-[#7c8178]",
                        ),
                        rx.foreach(
                            S.preferences,
                            lambda p: rx.el.div(
                                rx.el.span(p["name"], class_name="text-sm"),
                                rx.el.button(
                                    rx.cond(
                                        p["enabled"] == "yes", "مفعّل ✓", "متوقف"
                                    ),
                                    on_click=lambda: S.toggle_preference(
                                        p["kind"]
                                    ),
                                    aria_label=p["name"],
                                    class_name=rx.cond(
                                        p["enabled"] == "yes",
                                        "rounded-full bg-[#e8edde] px-4 py-2 text-xs font-bold text-[#62704b]",
                                        "rounded-full bg-[#eeece5] px-4 py-2 text-xs text-[#7c8178]",
                                    ),
                                ),
                                class_name="flex items-center justify-between gap-3 border-b border-[#eeebe2] py-3 last:border-0",
                            ),
                        ),
                        class_name=CARD,
                    ),
                    class_name="space-y-5",
                ),
                rx.el.div(
                    invite_panel(),
                    rx.el.section(
                        rx.el.h2(
                            "سجل الدعوات", class_name="mb-5 text-xl font-bold"
                        ),
                        rx.cond(
                            S.invitations.length() > 0,
                            rx.foreach(
                                S.invitations,
                                lambda i: rx.el.div(
                                    rx.el.p(
                                        i["email"],
                                        class_name="break-all font-semibold",
                                    ),
                                    rx.el.div(
                                        rx.el.span(
                                            rx.match(
                                                i["status"],
                                                ("pending", "معلقة"),
                                                ("accepted", "مقبولة"),
                                                ("revoked", "ملغاة"),
                                                ("expired", "منتهية الصلاحية"),
                                                "مرفوضة",
                                            ),
                                            class_name="rounded-full bg-[#f0ebdc] px-3 py-1 text-xs text-[#957a46]",
                                        ),
                                        rx.el.span(
                                            f"تنتهي: {i['expires']}",
                                            class_name="text-xs text-[#7c8178]",
                                        ),
                                        rx.cond(
                                            (i["status"] == "pending")
                                            & S.owner,
                                            rx.el.button(
                                                "إلغاء الدعوة",
                                                on_click=lambda: S.revoke(
                                                    i["id"]
                                                ),
                                                class_name="text-xs text-[#a26550]",
                                            ),
                                        ),
                                        class_name="mt-2 flex flex-wrap items-center gap-3",
                                    ),
                                    class_name="border-b border-[#eeebe2] py-4 last:border-0",
                                    key=i["id"],
                                ),
                            ),
                            empty("لا توجد دعوات بعد."),
                        ),
                        class_name=CARD,
                    ),
                    class_name="space-y-5",
                ),
                class_name="grid gap-6 lg:grid-cols-2",
            ),
        )
    )


def accept_invitation() -> rx.Component:
    return public_shell(
        rx.el.section(
            rx.icon(
                "heart-handshake", class_name="mb-5 h-10 w-10 text-[#62704b]"
            ),
            section_title(
                "أهلًا بك في دفتر الأسرة",
                "سجّل الدخول بالبريد الذي خُصصت له الدعوة. نقارن بريد حسابك ببريد الدعوة؛ لا ندّعي التحقق من ملكية البريد خارجيًا.",
            ),
            notice(),
            rx.el.p(AuthState.email, class_name="mb-4 text-sm text-[#7c8178]"),
            rx.el.form(
                field(
                    "رمز أو رابط الدعوة",
                    "token",
                    default=AuthState.pending_invite,
                ),
                rx.el.p(
                    "بقبول الدعوة تنضم إلى الأسرة وتستطيع إدارة حساباتها ومعاملاتها وميزانياتها. يمكنك التنقل بين أسرك من الإعدادات.",
                    class_name="text-sm leading-7 text-[#7c8178]",
                ),
                rx.el.button(
                    "قبول الدعوة والانضمام", type="submit", class_name=BUTTON
                ),
                on_submit=S.accept_invitation,
                class_name="space-y-5",
            ),
            rx.el.a(
                "العودة إلى دفتري",
                href="/dashboard",
                class_name="mt-5 block text-sm text-[#62704b]",
            ),
            class_name="mx-auto max-w-xl rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-7",
        )
    )
