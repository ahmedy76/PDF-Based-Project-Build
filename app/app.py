import reflex as rx

from app.locales.catalog import catalog
from app.components import screens
from app.components.bills import bills_page
from app.components.csv_transfer import data_transfer_page
from app.states.csv_transfer import CsvTransferState
from app.states.bills import BillState
from app.states.auth import AuthState
from app.states.categories import CategoryState
from app.states.ledger import LedgerState
from app.states.goals import GoalState
from app.states.debts import DebtState
from app.states.member_access import MemberAccessState


def index() -> rx.Component:
    return screens.welcome()


def register() -> rx.Component:
    return screens.auth_page(True, AuthState.register)


def login() -> rx.Component:
    return screens.auth_page(False, AuthState.login)


catalog("ar")
catalog("en")

app = rx.App(
    theme=rx.theme(appearance="light"),
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(
            rel="preconnect",
            href="https://fonts.gstatic.com",
            cross_origin="",
        ),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap",
            rel="stylesheet",
        ),
    ],
)
app.add_page(
    index,
    route="/",
    title="Money Harmony | دفتر البيت وراحة البال",
    description="نظّم ميزانية أسرتك، تابع الدخل والمصروف وادخر مع شريكك في دفتر عربي واحد.",
)
app.add_page(
    register,
    route="/register",
    title="إنشاء حساب | Money Harmony",
    on_load=AuthState.clear_error,
)
app.add_page(
    login,
    route="/login",
    title="تسجيل الدخول | Money Harmony",
    on_load=AuthState.clear_error,
)
app.add_page(
    screens.onboarding,
    route="/onboarding",
    title="بداية التناغم | Money Harmony",
    on_load=LedgerState.load,
)
app.add_page(
    screens.dashboard,
    route="/dashboard",
    title="دفتر الأسرة | Money Harmony",
    on_load=[LedgerState.load, BillState.load],
)
app.add_page(
    screens.accounts,
    route="/accounts",
    title="الحسابات | Money Harmony",
    on_load=LedgerState.load,
)
app.add_page(
    screens.transactions,
    route="/transactions",
    title="المعاملات | Money Harmony",
    on_load=LedgerState.load,
)
app.add_page(
    screens.budgets,
    route="/budgets",
    title="الميزانيات | Money Harmony",
    on_load=LedgerState.load,
)
app.add_page(
    screens.goals,
    route="/goals",
    title="أهداف الادخار | Money Harmony",
    on_load=[LedgerState.load, GoalState.load],
)
app.add_page(
    screens.debts,
    route="/debts",
    title="الديون والأقساط | Money Harmony",
    on_load=[LedgerState.load, DebtState.load, BillState.load],
)
app.add_page(
    bills_page,
    route="/bills",
    title="الفواتير | Money Harmony",
    on_load=[LedgerState.load, BillState.load],
)
app.add_page(
    screens.reports,
    route="/reports",
    title="التقارير | Money Harmony",
    on_load=LedgerState.load,
)
app.add_page(
    screens.notifications,
    route="/notifications",
    title="الإشعارات | Money Harmony",
    on_load=[LedgerState.load, BillState.load],
)
app.add_page(
    screens.settings,
    route="/settings",
    title="الإعدادات | Money Harmony",
    on_load=[LedgerState.load, MemberAccessState.load],
)
app.add_page(
    screens.categories,
    route="/categories",
    title="فئات الأسرة | Money Harmony",
    on_load=[LedgerState.load, CategoryState.load],
)
app.add_page(
    data_transfer_page,
    route="/data-transfer",
    title="استيراد وتصدير CSV | Money Harmony",
    on_load=[LedgerState.load, CsvTransferState.load],
)
app.add_page(
    screens.accept_invitation,
    route="/accept-invitation",
    title="قبول دعوة الأسرة | Money Harmony",
    on_load=AuthState.prepare_invitation,
)
