import reflex as rx

from app.components.ui import CARD
from app.locales.catalog import t
from app.states.member_access import (
    AccountAccess,
    MemberAccess,
    MemberAccessState as M,
)


def account_switch(
    member: MemberAccess, account: AccountAccess
) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("wallet", class_name="h-4 w-4 text-[#62704b]"),
            rx.el.span(
                account["name"],
                class_name="ms-2 font-medium text-[#27394a]",
            ),
            rx.el.span(
                account["currency"],
                class_name="ms-2 text-xs font-bold text-[#62704b]",
            ),
            rx.cond(
                account["archived"],
                rx.el.span("مؤرشف", class_name="ms-2 text-xs text-[#7c8178]"),
            ),
            class_name="min-w-0 break-words text-sm",
        ),
        rx.el.button(
            rx.cond(
                account["visible"], "يستطيع الاطلاع ✓", "لا يستطيع الاطلاع"
            ),
            on_click=lambda: M.toggle_account(member["id"], account["id"]),
            aria_label=f"حق الاطلاع على {account['name']} للعضو {member['name']}",
            aria_pressed=account["visible"],
            class_name=rx.cond(
                account["visible"],
                "shrink-0 rounded-full border border-[#dce0ce] bg-[#e8edde] px-3 py-2 text-xs font-bold text-[#62704b] hover:bg-[#dce5cf] focus-visible:outline-2 focus-visible:outline-[#62704b]",
                "shrink-0 rounded-full border border-[#e2ded2] bg-[#eeece5] px-3 py-2 text-xs font-bold text-[#27394a] hover:bg-[#e3dfd5] focus-visible:outline-2 focus-visible:outline-[#62704b]",
            ),
        ),
        class_name="flex flex-wrap items-center justify-between gap-2 border-b border-[#eeebe2] py-2 last:border-0",
        key=account["id"],
    )


def permission_switch(
    member: MemberAccess, label: str, permission: str, enabled: rx.Var[bool]
) -> rx.Component:
    return rx.el.div(
        rx.el.span(label, class_name="text-sm font-medium text-[#27394a]"),
        rx.el.button(
            rx.cond(enabled, t("planning.allowed"), t("planning.denied")),
            on_click=lambda: M.toggle_permission(member["id"], permission),
            aria_label=f"{label} للعضو {member['name']}",
            aria_pressed=enabled,
            class_name=rx.cond(
                enabled,
                "rounded-full border border-[#dce0ce] bg-[#e8edde] px-3 py-2 text-xs font-bold text-[#62704b] hover:bg-[#dce5cf] focus-visible:outline-2 focus-visible:outline-[#62704b]",
                "rounded-full border border-[#e2ded2] bg-[#eeece5] px-3 py-2 text-xs font-bold text-[#27394a] hover:bg-[#e3dfd5] focus-visible:outline-2 focus-visible:outline-[#62704b]",
            ),
        ),
        class_name="flex items-center justify-between gap-3 border-b border-[#eeebe2] py-2",
    )


def member_card(member: MemberAccess) -> rx.Component:
    return rx.el.div(
        rx.el.h3(
            member["name"], class_name="mb-3 text-base font-bold text-[#27394a]"
        ),
        permission_switch(
            member,
            "إضافة معاملات",
            "can_add_transactions",
            member["can_add_transactions"],
        ),
        permission_switch(
            member,
            "تعديل الميزانيات",
            "can_edit_budgets",
            member["can_edit_budgets"],
        ),
        permission_switch(
            member,
            t("planning.disclosure"),
            "can_view_commitments",
            member["can_view_commitments"],
        ),
        rx.el.p(
            t("planning.disclosure_help"),
            class_name="mt-2 text-sm leading-6 text-[#7c8178]",
        ),
        rx.el.div(
            rx.icon("wallet", class_name="h-4 w-4 text-[#62704b]"),
            rx.el.h4(
                "الاطلاع على الحسابات",
                class_name="text-sm font-bold text-[#27394a]",
            ),
            class_name="mt-5 mb-2 flex items-center gap-2",
        ),
        rx.cond(
            member["accounts"].length() > 0,
            rx.foreach(
                member["accounts"],
                lambda account: account_switch(member, account),
            ),
            rx.el.p(
                "لا توجد حسابات في هذه الأسرة بعد.",
                class_name="text-sm text-[#7c8178]",
            ),
        ),
        class_name="rounded-xl border border-[#e2ded2] bg-[#fffdf8] p-4",
        key=member["id"],
    )


def member_access_panel() -> rx.Component:
    return rx.cond(
        M.owner,
        rx.el.section(
            rx.el.div(
                rx.icon("shield-check", class_name="h-5 w-5 text-[#62704b]"),
                rx.el.h2(
                    "صلاحيات أفراد الأسرة",
                    class_name="text-xl font-bold text-[#27394a]",
                ),
                class_name="mb-2 flex items-center gap-2",
            ),
            rx.el.p(
                "المالك يتمتع دائمًا بكامل الصلاحيات. تتغير صلاحيات كل شريك فور الضغط على الخيار.",
                class_name="mb-2 text-sm leading-6 text-[#7c8178]",
            ),
            rx.el.p(
                "الحساب المحجوب عن عضو يُستبعد أيضًا من إجمالياته وتقاريره عند تطبيق ضوابط الاطلاع على البيانات.",
                class_name="mb-4 rounded-xl bg-[#f6f4ec] px-3 py-2 text-xs leading-6 text-[#62704b]",
            ),
            rx.cond(
                M.message != "",
                rx.el.p(
                    M.message,
                    role="status",
                    class_name=rx.cond(
                        M.error,
                        "mb-4 rounded-lg bg-red-100 px-3 py-2 text-sm text-red-600",
                        "mb-4 rounded-lg bg-green-100 px-3 py-2 text-sm text-green-700",
                    ),
                ),
            ),
            rx.cond(
                M.members.length() > 0,
                rx.el.div(
                    rx.foreach(M.members, member_card), class_name="space-y-4"
                ),
                rx.el.p(
                    "لا يوجد شركاء نشطون حاليًا. يمكنك دعوة شريك من بطاقة الدعوات.",
                    class_name="text-sm text-[#7c8178]",
                ),
            ),
            class_name=CARD,
        ),
    )
