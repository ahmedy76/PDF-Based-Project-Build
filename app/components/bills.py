import reflex as rx

from app.locales.catalog import t
from app.states.bills import BillRow, ReminderRow, BillState as B
from app.states.ledger import LedgerState as S
from app.components.ui import (
    BUTTON,
    SECONDARY,
    CARD,
    empty,
    field,
    section_title,
    shell,
)


def reminder_card(row: ReminderRow) -> rx.Component:
    return rx.el.a(
        rx.el.div(
            rx.icon("bell-ring", class_name="h-5 w-5 shrink-0 text-[#62704b]"),
            rx.el.div(
                rx.el.h3(row["title"], class_name="font-bold text-[#27394a]"),
                rx.el.p(
                    row["detail"], class_name="mt-1 text-sm text-[#7c8178]"
                ),
                class_name="min-w-0",
            ),
            class_name="flex items-start gap-3",
        ),
        rx.el.strong(
            f"{row['amount']} {row['currency']}",
            class_name="text-sm tabular-nums text-[#62704b]",
        ),
        href=row["path"],
        class_name="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[#dce0ce] bg-[#fffdf8] p-4 hover:bg-[#edf0e3]",
        key=row["id"],
    )


def reminder_section() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.h2(
                    t("reminders.title"),
                    class_name="text-xl font-bold text-[#27394a]",
                ),
                rx.el.p(
                    t("reminders.subtitle"),
                    class_name="mt-1 text-sm leading-7 text-[#7c8178]",
                ),
            ),
            rx.el.a(
                t("reminders.all"),
                href="/notifications",
                class_name="text-sm font-bold text-[#62704b] hover:underline",
            ),
            class_name="mb-4 flex flex-wrap items-start justify-between gap-3",
        ),
        rx.cond(
            B.reminders.length() > 0,
            rx.el.div(
                rx.foreach(B.reminders[:4], reminder_card),
                class_name="space-y-3",
            ),
            empty(
                "لا توجد فواتير أو أقساط غير مسددة تستحق قريبًا، أو أن تذكيراتك معطّلة."
            ),
        ),
        class_name=CARD,
    )


def bill_card(row: BillRow) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.el.div(
                rx.icon("receipt-text", class_name="h-5 w-5 text-[#62704b]"),
                rx.el.h3(
                    row["title"],
                    class_name="break-words text-lg font-bold text-[#27394a]",
                ),
                class_name="flex min-w-0 items-center gap-3",
            ),
            rx.el.span(
                rx.cond(
                    row["status"] == "paid", t("bills.paid"), t("bills.unpaid")
                ),
                class_name=rx.cond(
                    row["status"] == "paid",
                    "w-fit rounded-full bg-[#e9eddf] px-3 py-1 text-xs font-bold text-[#62704b]",
                    "w-fit rounded-full bg-[#f4eddb] px-3 py-1 text-xs font-bold text-[#9a7945]",
                ),
            ),
            class_name="flex flex-wrap items-start justify-between gap-3",
        ),
        rx.el.p(
            f"{row['amount']} {row['currency']}",
            class_name="mt-5 text-2xl font-bold tabular-nums text-[#27394a]",
        ),
        rx.el.p(
            f"{row['account']} · الاستحقاق {row['due_date']}",
            class_name="mt-2 text-sm text-[#7c8178]",
        ),
        rx.cond(
            row["paid_on"] != "",
            rx.el.p(
                f"سُددت في {row['paid_on']}",
                class_name="mt-1 text-sm text-[#62704b]",
            ),
        ),
        rx.el.p(
            f"التذكير قبل {row['remind_days']} يوم",
            class_name="mt-1 text-xs text-[#7c8178]",
        ),
        rx.cond(
            row["notes"] != "",
            rx.el.p(
                row["notes"],
                class_name="mt-3 break-words text-sm text-[#7c8178]",
            ),
        ),
        rx.cond(
            S.can_add_transactions,
            rx.el.div(
                rx.el.button(
                    rx.cond(
                        row["status"] == "paid",
                        t("action.mark_unpaid"),
                        t("action.mark_paid"),
                    ),
                    on_click=lambda: B.set_paid(
                        row["id"], row["status"] != "paid"
                    ),
                    class_name=BUTTON,
                ),
                rx.el.button(
                    t("action.edit"),
                    on_click=lambda: B.open_bill(row["id"]),
                    class_name=SECONDARY,
                ),
                rx.el.button(
                    t("action.delete_bill"),
                    on_click=lambda: B.delete_bill(row["id"]),
                    class_name="rounded-xl border border-[#e2ded2] px-4 py-2.5 text-sm font-semibold text-[#a26550] hover:bg-[#f5e9e3]",
                ),
                class_name="mt-5 flex flex-wrap gap-2 border-t border-[#eeebe2] pt-4",
            ),
        ),
        class_name=CARD,
        key=row["id"],
    )


def bill_dialog() -> rx.Component:
    return rx.cond(
        B.editor == "bill",
        rx.el.div(
            rx.el.section(
                rx.el.div(
                    rx.el.h2(
                        rx.cond(
                            B.edit_id == "", "فاتورة جديدة", "تعديل الفاتورة"
                        ),
                        class_name="text-xl font-bold text-[#27394a]",
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-4 w-4"),
                        on_click=B.close_bill,
                        aria_label=t("action.close"),
                        class_name=SECONDARY,
                    ),
                    class_name="mb-5 flex items-center justify-between gap-3",
                ),
                rx.cond(
                    B.error != "",
                    rx.el.p(
                        B.error,
                        role="alert",
                        class_name="mb-4 rounded-xl bg-red-100 p-3 text-sm text-red-600",
                    ),
                ),
                rx.el.p(
                    "هذا سجل استحقاق مستقل. تحديد السداد لا يخصم من الحساب ولا ينشئ معاملة؛ سجّل الدفع الفعلي في دفتر المعاملات منفصلًا.",
                    class_name="mb-5 rounded-xl bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
                ),
                rx.el.form(
                    field("عنوان الفاتورة", "title", default=B.draft["title"]),
                    field(
                        "المبلغ (حتى 4 خانات عشرية)",
                        "amount",
                        default=B.draft["amount"],
                    ),
                    rx.el.label(
                        rx.el.span(
                            "الحساب المرتبط · تُحدد العملة منه تلقائيًا",
                            class_name="mb-2 block text-sm font-semibold text-[#465344]",
                        ),
                        rx.el.div(
                            rx.el.select(
                                rx.foreach(
                                    B.accounts,
                                    lambda a: rx.el.option(
                                        a["name"], value=a["id"]
                                    ),
                                ),
                                name="account_id",
                                default_value=B.draft["account_id"],
                                required=True,
                                class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white px-3 py-3 pl-9 text-[#27394a]",
                            ),
                            rx.icon(
                                "chevron-down",
                                class_name="pointer-events-none absolute left-3 top-4 h-4 w-4 text-[#62704b]",
                            ),
                            class_name="relative",
                        ),
                        class_name="block",
                    ),
                    field(
                        "تاريخ الاستحقاق",
                        "due_date",
                        "date",
                        B.draft["due_date"],
                    ),
                    field(
                        "التذكير قبل الموعد بالأيام (0–365)",
                        "remind_days",
                        "number",
                        B.draft["remind_days"],
                    ),
                    field(
                        "ملاحظة (اختياري)",
                        "notes",
                        default=B.draft["notes"],
                        required=False,
                    ),
                    rx.el.div(
                        rx.el.button(
                            t("action.save_bill"),
                            type="submit",
                            class_name=BUTTON,
                        ),
                        rx.el.button(
                            t("action.cancel"),
                            type="button",
                            on_click=B.close_bill,
                            class_name=SECONDARY,
                        ),
                        class_name="flex flex-wrap gap-3",
                    ),
                    on_submit=B.save_bill,
                    key=B.edit_id,
                    class_name="space-y-4",
                ),
                role="dialog",
                aria_modal=True,
                aria_label="بيانات الفاتورة",
                class_name="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[#fffdf8] p-6",
            ),
            class_name="fixed inset-0 z-50 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )


def bills_page() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(
                    t("bills.title"),
                    t("bills.subtitle"),
                ),
                rx.cond(
                    S.can_add_transactions,
                    rx.el.button(
                        rx.icon("plus", class_name="h-4 w-4"),
                        t("action.new_bill"),
                        on_click=lambda: B.open_bill(),
                        disabled=B.accounts.length() == 0,
                        class_name=BUTTON,
                    ),
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.cond(
                B.error != "",
                rx.el.p(
                    B.error,
                    role="alert",
                    class_name="mb-5 rounded-xl bg-red-100 p-4 text-sm text-red-600",
                ),
            ),
            rx.cond(
                B.message != "",
                rx.el.p(
                    B.message,
                    role="status",
                    class_name="mb-5 rounded-xl bg-[#e9eddf] p-4 text-sm text-[#62704b]",
                ),
            ),
            rx.el.p(
                "الفواتير مرتبطة بحساباتك النشطة الظاهرة لك، وعملتها من الحساب. يُحدّث التذكير عند زيارة الصفحات لا تلقائيًا في الخلفية.",
                class_name="mb-6 rounded-xl border border-[#dce0ce] bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
            ),
            rx.cond(
                B.accounts.length() == 0,
                empty("أضف حسابًا نشطًا ظاهرًا لك أولًا لتسجيل فاتورة."),
            ),
            rx.el.div(
                rx.el.h2(
                    t("bills.register"),
                    class_name="mb-4 text-xl font-bold text-[#27394a]",
                ),
                rx.cond(
                    B.bills.length() > 0,
                    rx.el.div(
                        rx.foreach(B.bills, bill_card),
                        class_name="grid items-start gap-5 md:grid-cols-2 xl:grid-cols-3",
                    ),
                    empty(
                        "لا توجد فواتير مرتبطة بحساباتك الظاهرة. أضف أول فاتورة لتبدأ المتابعة."
                    ),
                ),
                class_name="mb-8",
            ),
            reminder_section(),
            bill_dialog(),
        )
    )
