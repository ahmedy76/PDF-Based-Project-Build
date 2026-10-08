import reflex as rx

from app.components.ui import (
    BUTTON,
    SECONDARY,
    CARD,
    INPUT,
    empty,
    field,
    section_title,
    shell,
)
from app.locales.catalog import t
from app.states.family_planning import (
    FamilyPlanningState as P,
    TaskRow,
    SplitBillRow,
    ShareRow,
)


def choice(
    label, name: str, children: rx.Component, default=""
) -> rx.Component:
    return rx.el.label(
        rx.el.span(
            label, class_name="mb-2 block text-sm font-semibold text-[#465344]"
        ),
        rx.el.div(
            rx.el.select(
                children,
                name=name,
                default_value=default,
                class_name="w-full appearance-none rounded-xl border border-[#dcd8cb] bg-white p-3 pe-9 text-[#27394a] focus:outline-2 focus:outline-[#62704b]",
            ),
            rx.icon(
                "chevron-down",
                class_name="pointer-events-none absolute end-3 top-4 h-4 w-4 text-[#62704b]",
            ),
            class_name="relative",
        ),
        class_name="block min-w-0",
    )


def people_choice(label, name: str, default="") -> rx.Component:
    return choice(
        label,
        name,
        rx.fragment(
            rx.el.option(t("planning.none"), value=""),
            rx.foreach(
                P.participants,
                lambda person: rx.el.option(person["name"], value=person["id"]),
            ),
        ),
        default,
    )


def task_card(row: TaskRow) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.el.h3(
                row["title"],
                class_name="break-words text-lg font-bold text-[#27394a]",
            ),
            rx.el.span(
                rx.cond(
                    row["status"] == "complete",
                    t("planning.complete"),
                    t("planning.pending"),
                ),
                class_name="w-fit rounded-full bg-[#e8edde] px-3 py-1 text-xs font-bold text-[#62704b]",
            ),
            class_name="flex flex-wrap items-start justify-between gap-3",
        ),
        rx.el.p(
            row["details"],
            class_name="mt-3 whitespace-pre-wrap break-words text-sm leading-7 text-[#7c8178]",
        ),
        rx.el.dl(
            rx.el.div(
                rx.el.dt(t("planning.currency")),
                rx.el.dd(
                    row["currency"], class_name="font-bold text-[#62704b]"
                ),
            ),
            rx.el.div(
                rx.el.dt(t("planning.due_date")),
                rx.el.dd(
                    rx.cond(
                        row["due_date"] != "",
                        row["due_date"],
                        t("planning.none"),
                    )
                ),
            ),
            rx.el.div(
                rx.el.dt(t("planning.account")),
                rx.el.dd(
                    rx.cond(
                        row["account"] != "", row["account"], t("planning.none")
                    )
                ),
            ),
            rx.el.div(
                rx.el.dt(t("planning.assignee")),
                rx.el.dd(
                    rx.cond(
                        row["assignee"] != "",
                        row["assignee"],
                        t("planning.none"),
                    )
                ),
            ),
            class_name="mt-4 grid grid-cols-1 gap-3 text-xs text-[#7c8178] sm:grid-cols-2",
        ),
        rx.el.div(
            rx.cond(
                row["actionable"],
                rx.el.button(
                    rx.icon("check-check", class_name="h-4 w-4"),
                    rx.cond(
                        row["status"] == "complete",
                        t("planning.reopen"),
                        t("planning.complete_action"),
                    ),
                    on_click=lambda: P.set_status(
                        row["id"],
                        rx.cond(
                            row["status"] == "complete", "pending", "complete"
                        ),
                    ),
                    class_name=SECONDARY,
                ),
            ),
            rx.cond(
                row["editable"],
                rx.fragment(
                    rx.el.button(
                        t("action.edit"),
                        on_click=lambda: P.open_task(row["id"]),
                        class_name=SECONDARY,
                    ),
                    rx.el.button(
                        t("action.delete"),
                        on_click=lambda: P.ask_delete(row["id"]),
                        class_name=SECONDARY,
                    ),
                ),
            ),
            class_name="mt-4 flex flex-wrap gap-2 border-t border-[#eeebe2] pt-4",
        ),
        key=row["id"],
        class_name=CARD,
    )


def task_form() -> rx.Component:
    return rx.cond(
        P.editor,
        rx.el.section(
            rx.el.h2(
                t("planning.task_form"),
                class_name="mb-5 text-xl font-bold text-[#27394a]",
            ),
            rx.el.form(
                field(
                    t("planning.task_title"), "title", default=P.draft["title"]
                ),
                rx.el.label(
                    rx.el.span(
                        t("planning.details"),
                        class_name="mb-2 block text-sm font-semibold text-[#465344]",
                    ),
                    rx.el.textarea(
                        name="details",
                        default_value=P.draft["details"],
                        max_length=4000,
                        rows=3,
                        class_name=INPUT,
                    ),
                ),
                rx.el.div(
                    field(
                        t("planning.due_date"),
                        "due_date",
                        "date",
                        P.draft["due_date"],
                        False,
                    ),
                    field(
                        t("planning.currency"),
                        "currency",
                        default=P.draft["currency"],
                    ),
                    choice(
                        t("planning.account"),
                        "account_id",
                        rx.fragment(
                            rx.el.option(t("planning.none"), value=""),
                            rx.foreach(
                                P.accounts,
                                lambda account: rx.el.option(
                                    account["name"], value=account["id"]
                                ),
                            ),
                        ),
                        P.draft["account_id"],
                    ),
                    people_choice(
                        t("planning.assignee"),
                        "assignee_user_id",
                        P.draft["assignee_user_id"],
                    ),
                    class_name="grid gap-4 md:grid-cols-2",
                ),
                rx.el.div(
                    rx.el.button(
                        t("action.save"), type="submit", class_name=BUTTON
                    ),
                    rx.el.button(
                        t("action.cancel"),
                        type="button",
                        on_click=P.close_task,
                        class_name=SECONDARY,
                    ),
                    class_name="flex flex-wrap gap-3",
                ),
                on_submit=P.save_task,
                key=P.form_key,
                class_name="space-y-4",
            ),
            class_name=CARD,
        ),
    )


def share_card(share: ShareRow, currency) -> rx.Component:
    return rx.el.div(
        rx.el.p(share["name"], class_name="font-bold text-[#27394a]"),
        rx.el.p(
            t("planning.percentage"),
            f": {share['percentage']}%",
            class_name="mt-1 text-sm text-[#62704b]",
        ),
        rx.el.p(
            t("planning.share"),
            f": {share['amount']} {currency}",
            class_name="text-sm text-[#62704b]",
        ),
        rx.cond(
            share["income"] != "",
            rx.el.p(
                t("planning.income_label"),
                f": {share['income']} {currency}",
                class_name="mt-1 text-sm text-[#7c8178]",
            ),
        ),
        class_name="rounded-xl border border-[#e2ded2] bg-[#f6f4ec] p-4",
    )


def split_form(bill: SplitBillRow) -> rx.Component:
    return rx.el.form(
        rx.el.input(type="hidden", name="bill_id", default_value=bill["id"]),
        rx.el.input(
            type="hidden", name="currency", default_value=bill["currency"]
        ),
        choice(
            t("planning.mode"),
            "mode",
            rx.fragment(
                rx.el.option(t("planning.equal"), value="equal"),
                rx.el.option(t("planning.income"), value="income"),
            ),
        ),
        rx.el.div(
            people_choice(t("planning.participant_1"), "participant_1"),
            people_choice(t("planning.participant_2"), "participant_2"),
            field(t("planning.income_1"), "income_1", required=False),
            field(t("planning.income_2"), "income_2", required=False),
            class_name="grid gap-4 sm:grid-cols-2",
        ),
        rx.el.p(
            t("planning.income_help"),
            class_name="text-sm leading-7 text-[#7c8178]",
        ),
        rx.el.label(
            rx.el.input(
                type="checkbox",
                name="confirm",
                required=True,
                class_name="mt-1 h-4 w-4 shrink-0 accent-[#62704b]",
            ),
            rx.el.span(t("planning.confirm")),
            class_name="flex items-start gap-3 text-sm leading-7 text-[#465344]",
        ),
        rx.el.div(
            rx.el.button(
                t("planning.save_split"), type="submit", class_name=BUTTON
            ),
            rx.cond(
                bill["mode"] != "",
                rx.el.button(
                    t("planning.revoke"),
                    type="button",
                    on_click=lambda: P.revoke_split(bill["id"]),
                    class_name=SECONDARY,
                ),
            ),
            class_name="flex flex-wrap gap-2",
        ),
        on_submit=P.save_split,
        key=f"{bill['id']}-{P.form_key}",
        class_name="mt-5 space-y-4 border-t border-[#eeebe2] pt-5",
    )


def split_bill_card(bill: SplitBillRow) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.icon("receipt-text", class_name="h-5 w-5 text-[#62704b]"),
            rx.el.h3(
                bill["title"],
                class_name="break-words text-lg font-bold text-[#27394a]",
            ),
            class_name="flex items-center gap-3",
        ),
        rx.el.p(
            f"{bill['amount']} {bill['currency']}",
            class_name="mt-3 text-xl font-bold tabular-nums text-[#27394a]",
        ),
        rx.el.p(
            f"{bill['account']} · {bill['due_date']}",
            class_name="mt-1 text-sm text-[#7c8178]",
        ),
        rx.cond(
            bill["stale"],
            rx.el.p(
                t("planning.stale"),
                role="status",
                class_name="mt-4 rounded-xl bg-yellow-100 p-3 text-sm text-yellow-800",
            ),
        ),
        rx.cond(
            bill["shares"].length() > 0,
            rx.el.div(
                rx.el.p(
                    t("planning.snapshot"),
                    class_name="mb-3 text-sm font-semibold text-[#62704b]",
                ),
                rx.el.p(
                    rx.cond(
                        bill["mode"] == "income",
                        t("planning.income"),
                        t("planning.equal"),
                    ),
                    class_name="mb-3 text-sm text-[#62704b]",
                ),
                rx.el.div(
                    rx.foreach(
                        bill["shares"],
                        lambda share: share_card(share, bill["currency"]),
                    ),
                    class_name="grid gap-3 sm:grid-cols-2",
                ),
                class_name="mt-4",
            ),
            rx.el.p(
                t("planning.no_disclosure"),
                class_name="mt-4 text-sm leading-7 text-[#7c8178]",
            ),
        ),
        rx.cond(P.owner, split_form(bill)),
        key=bill["id"],
        class_name=CARD,
    )


def task_filters() -> rx.Component:
    return rx.el.form(
        field(
            t("planning.currency"),
            "currency",
            default=P.currency_filter,
            required=False,
        ),
        choice(
            t("planning.status"),
            "status",
            rx.fragment(
                rx.el.option(t("planning.all"), value=""),
                rx.el.option(t("planning.pending"), value="pending"),
                rx.el.option(t("planning.complete"), value="complete"),
            ),
            P.status_filter,
        ),
        rx.el.button(t("planning.filter"), type="submit", class_name=SECONDARY),
        on_submit=P.apply_filters,
        class_name="mb-5 grid items-end gap-4 sm:grid-cols-3",
    )


def family_planning_page() -> rx.Component:
    return shell(
        rx.el.div(
            rx.el.div(
                section_title(t("planning.title"), t("planning.subtitle")),
                rx.el.div(
                    rx.el.button(
                        rx.icon("refresh-cw", class_name="h-4 w-4"),
                        t("planning.refresh"),
                        on_click=P.load,
                        disabled=P.loading,
                        class_name=SECONDARY,
                    ),
                    rx.el.button(
                        rx.icon("plus", class_name="h-4 w-4"),
                        t("planning.new_task"),
                        on_click=lambda: P.open_task(),
                        disabled=P.loading,
                        class_name=BUTTON,
                    ),
                    class_name="flex flex-wrap gap-2",
                ),
                class_name="flex flex-wrap items-start justify-between gap-4",
            ),
            rx.cond(
                P.error != "",
                rx.el.p(
                    t(P.error),
                    role="alert",
                    class_name="my-4 rounded-xl bg-red-100 p-4 text-sm text-red-700",
                ),
            ),
            rx.cond(
                P.message != "",
                rx.el.p(
                    t(P.message),
                    role="status",
                    class_name="my-4 rounded-xl bg-green-100 p-4 text-sm text-green-700",
                ),
            ),
            rx.el.p(
                t("planning.no_posting"),
                class_name="my-5 rounded-xl border border-[#dce0ce] bg-[#edf0e3] p-4 text-sm leading-7 text-[#62704b]",
            ),
            rx.cond(
                P.loading,
                rx.el.div(
                    rx.el.p(t("shell.loading"), role="status"),
                    class_name="animate-pulse rounded-xl bg-[#e8edde] p-10 text-center text-[#62704b]",
                ),
                rx.el.div(
                    task_form(),
                    rx.el.section(
                        rx.el.h2(
                            t("planning.tasks"),
                            class_name="mb-4 text-xl font-bold text-[#27394a]",
                        ),
                        task_filters(),
                        rx.cond(
                            P.tasks.length() > 0,
                            rx.el.div(
                                rx.foreach(P.tasks, task_card),
                                class_name="grid items-start gap-5 md:grid-cols-2",
                            ),
                            empty(t("planning.empty_tasks")),
                        ),
                        class_name="mt-7",
                    ),
                    rx.el.section(
                        rx.el.h2(
                            t("planning.splits"),
                            class_name="mb-4 text-xl font-bold text-[#27394a]",
                        ),
                        rx.cond(
                            P.bills.length() > 0,
                            rx.el.div(
                                rx.foreach(P.bills, split_bill_card),
                                class_name="grid items-start gap-5 xl:grid-cols-2",
                            ),
                            empty(t("planning.empty_bills")),
                        ),
                        class_name="mt-8",
                    ),
                    rx.el.p(
                        t("planning.limit"),
                        class_name="mt-5 text-xs text-[#7c8178]",
                    ),
                ),
            ),
            rx.cond(
                P.delete_id != "",
                rx.el.div(
                    rx.el.section(
                        rx.el.h2(
                            t("planning.delete_confirm"),
                            class_name="mb-5 text-xl font-bold text-[#27394a]",
                        ),
                        rx.el.div(
                            rx.el.button(
                                t("action.delete"),
                                on_click=P.delete_task,
                                class_name=BUTTON,
                            ),
                            rx.el.button(
                                t("action.cancel"),
                                on_click=P.cancel_delete,
                                class_name=SECONDARY,
                            ),
                            class_name="flex gap-3",
                        ),
                        role="alertdialog",
                        aria_modal=True,
                        aria_label=t("planning.delete_confirm"),
                        class_name="w-full max-w-lg rounded-2xl bg-[#fffdf8] p-6",
                    ),
                    class_name="fixed inset-0 z-50 flex items-center justify-center bg-[#243747]/40 p-4",
                ),
            ),
            class_name="w-full min-w-0",
        )
    )
