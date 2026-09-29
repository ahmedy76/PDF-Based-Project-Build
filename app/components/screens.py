import reflex as rx
import reflex_xy

from app.states.auth import AuthState
from app.states.categories import CategoryState as C
from app.states.ledger import LedgerState as S
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
)


def welcome() -> rx.Component:
    return public_shell(
        rx.el.div(
            rx.el.div(
                rx.el.span(
                    "مساحة مشتركة لحياة أكثر اتزانًا",
                    class_name="inline-block rounded-full border border-[#dce0ce] bg-[#edf0e3] px-4 py-2 text-sm text-[#62704b]",
                ),
                rx.el.h1(
                    "أموالكم في تناغم،",
                    rx.el.br(),
                    "وبيتكم في طمأنينة.",
                    class_name="mt-7 text-4xl font-bold leading-[1.5] tracking-tight text-[#243747] md:text-6xl",
                ),
                rx.el.p(
                    "دخل، مصروف، وأحلام صغيرة تكبر معًا. اجمع تفاصيل ميزانية البيت في دفتر واحد واضح، وشارك الرحلة مع شريكك.",
                    class_name="mt-6 max-w-lg text-lg leading-9 text-[#7b8274]",
                ),
                rx.el.div(
                    rx.el.a(
                        "ابدأ دفتر أسرتك",
                        rx.icon("arrow-left", class_name="h-4 w-4"),
                        href="/register",
                        class_name=BUTTON,
                    ),
                    rx.el.a(
                        "لديّ حساب بالفعل", href="/login", class_name=SECONDARY
                    ),
                    class_name="mt-8 flex flex-wrap gap-3",
                ),
                rx.el.div(
                    rx.icon("lock-keyhole", class_name="h-4 w-4"),
                    "بيانات أسرتك خاصة · إدخال يدوي بلا ربط بنكي",
                    class_name="mt-7 flex items-center gap-2 text-xs text-[#828875]",
                ),
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.span("دفتر البيت", class_name="text-lg font-bold"),
                    rx.icon(
                        "notebook-pen", class_name="h-6 w-6 text-[#62704b]"
                    ),
                    class_name="mb-8 flex justify-between border-b border-[#dedacd] pb-5",
                ),
                rx.el.div(
                    rx.el.div(
                        rx.icon(
                            "sprout", class_name="mb-3 h-9 w-9 text-[#62704b]"
                        ),
                        rx.el.h2(
                            "كل خطوة تُحدث فرقًا", class_name="text-xl font-bold"
                        ),
                        rx.el.p(
                            "نخطط اليوم، لنطمئن غدًا",
                            class_name="mt-2 text-sm text-[#7c8178]",
                        ),
                        class_name="flex h-64 w-64 flex-col items-center justify-center rounded-full border-[14px] border-[#dfe5cf] outline-8 outline-offset-8 outline-[#ece8dc]",
                    ),
                    class_name="flex justify-center py-9",
                ),
                rx.el.div(
                    rx.el.div(
                        rx.icon("wallet", class_name="h-5 w-5"), "نعرف ما نملك"
                    ),
                    rx.el.div(
                        rx.icon("notebook-tabs", class_name="h-5 w-5"),
                        "نرتب ما ننفق",
                    ),
                    rx.el.div(
                        rx.icon("heart-handshake", class_name="h-5 w-5"),
                        "ندخر معًا",
                    ),
                    class_name="mt-8 grid grid-cols-3 gap-3 border-t border-[#dedacd] pt-6 text-center text-sm leading-8 text-[#62704b] [&>div]:flex [&>div]:flex-col [&>div]:items-center",
                ),
                class_name="rounded-3xl border border-[#dedacd] bg-[#fffdf8] p-7 md:rotate-[-2deg] md:p-10",
            ),
            class_name="grid items-center gap-12 lg:grid-cols-2",
        )
    )


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
                            S.saving,
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
            rx.el.p(f"الدخل  {S.income}", class_name="text-[#62704b]"),
            rx.el.p(f"المصروف  {S.expense}", class_name="text-[#a27456]"),
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
                rx.el.button(
                    rx.icon("plus", class_name="h-4 w-4"),
                    "تسجيل معاملة",
                    on_click=lambda: S.open_editor("transaction"),
                    class_name=BUTTON,
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
                    f"أرصدة الحسابات المغلقة المسجّلة ({S.archived_total} {S.currency}) مفصولة عن رصيد الحسابات النشطة؛ لم تُنقل أو تختفِ الأموال بسبب الإغلاق.",
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
            rx.el.span(S.currency, class_name="text-sm text-[#7c8178]"),
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
            rx.el.span(S.currency, class_name="text-sm text-[#7c8178]"),
            class_name="mt-1 flex items-baseline gap-2",
        ),
        class_name="rounded-2xl border border-[#e2ded2] bg-[#f1f0e9] p-5 md:p-7",
        key=a["id"],
    )


def accounts() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "حسابات البيت",
                    "الأرصدة المسجّلة من المعاملات غير المحذوفة؛ إغلاق الحساب يحفظ تاريخه ويفصل رصيده عن مجموع الحسابات النشطة.",
                ),
                rx.el.button(
                    rx.icon("plus", class_name="h-4 w-4"),
                    "إضافة حساب",
                    on_click=lambda: S.open_editor("account"),
                    class_name=BUTTON,
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
                            f"مجموع الأرصدة المسجّلة: {S.archived_total} {S.currency}",
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
            f"{row['display_amount']} {S.currency} · {row['frequency_label']}",
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
            rx.el.button(
                rx.icon("pencil", class_name="h-4 w-4"),
                "تعديل",
                on_click=lambda: S.open_editor("recurring", row["id"]),
                class_name=SECONDARY,
            ),
            rx.el.button(
                rx.cond(row["active"] == "yes", "إيقاف مؤقت", "استئناف"),
                on_click=lambda: S.toggle_recurring(row["id"]),
                class_name=SECONDARY,
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
                rx.el.button(
                    rx.icon("plus", class_name="h-4 w-4"),
                    "معاملة جديدة",
                    on_click=lambda: S.open_editor("transaction"),
                    class_name=BUTTON,
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
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
                    rx.el.button(
                        rx.icon("plus", class_name="h-4 w-4"),
                        "معاملة متكررة جديدة",
                        on_click=lambda: S.open_editor("recurring"),
                        class_name=BUTTON,
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


def budgets() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    "مساحة لكل احتياج",
                    "ميزانيات شهرية مرنة، وخطوات أقرب إلى التوازن.",
                ),
                rx.el.button(
                    rx.icon("plus", class_name="h-4 w-4"),
                    "ميزانية جديدة",
                    on_click=lambda: S.open_editor("budget"),
                    class_name=BUTTON,
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
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
                "البيانات من المعاملات المسجلة فقط، بالعملة الموحدة للأسرة. الفترة الحالية تمتد حتى اليوم؛ الأصفار تعني عدم وجود حركة.",
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
