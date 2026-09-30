import reflex as rx

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Record:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Record, Base):
    __tablename__ = "mh_users"
    __table_args__ = (
        CheckConstraint("length(trim(display_name)) > 0", name="name_required"),
        CheckConstraint(
            "email = lower(trim(email)) AND position('@' in email) > 1",
            name="normalized_email",
        ),
        CheckConstraint(
            "password_hash LIKE '$argon2id$%' OR password_hash LIKE '$2b$%'",
            name="password_hash_format",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'deleted')", name="status"
        ),
        CheckConstraint("language IN ('ar', 'en')", name="language"),
    )
    display_name: Mapped[str] = mapped_column(
        String(120), default="", server_default=""
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, default="", server_default=""
    )
    # Only encoded password hashes belong here; hashing is a later service concern.
    password_hash: Mapped[str] = mapped_column(
        String(512), default="", deferred=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    language: Mapped[str] = mapped_column(
        String(5), default="en", server_default="en"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), default="UTC", server_default="UTC"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    memberships: Mapped[list["HouseholdMembership"]] = relationship(
        viewonly=True, lazy="raise"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        viewonly=True, lazy="raise"
    )
    notification_preferences: Mapped[list["NotificationPreference"]] = (
        relationship(viewonly=True, lazy="raise")
    )


class UserSession(Record, Base):
    __tablename__ = "mh_user_sessions"
    __table_args__ = (
        CheckConstraint(
            "access_token_hash ~ '^[0-9a-f]{64}$'", name="access_digest"
        ),
        CheckConstraint(
            "refresh_token_hash ~ '^[0-9a-f]{64}$'", name="refresh_digest"
        ),
        CheckConstraint(
            "access_token_hash <> refresh_token_hash", name="distinct_tokens"
        ),
        CheckConstraint(
            "access_expires_at > created_at AND refresh_expires_at >= access_expires_at",
            name="expiry",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="revocation_time",
        ),
        Index("ix_mh_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_mh_sessions_expiry", "refresh_expires_at"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_users.id", ondelete="CASCADE"),
        default=None,
        nullable=False,
    )
    # SHA-256 digests of high-entropy random tokens, never bearer tokens themselves.
    access_token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, default="", deferred=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, default="", deferred=True
    )
    access_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=None, nullable=False
    )
    refresh_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=None, nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    user: Mapped["User"] = relationship(viewonly=True, lazy="raise")


class Household(Record, Base):
    __tablename__ = "mh_households"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint("status IN ('active', 'archived')", name="status"),
    )
    name: Mapped[str] = mapped_column(
        String(120), default="", server_default=""
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_users.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="SAR", server_default="SAR"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    owner: Mapped["User"] = relationship(
        foreign_keys=[owner_user_id], viewonly=True, lazy="raise"
    )
    memberships: Mapped[list["HouseholdMembership"]] = relationship(
        foreign_keys="HouseholdMembership.household_id",
        viewonly=True,
        lazy="raise",
    )
    accounts: Mapped[list["FinancialAccount"]] = relationship(
        viewonly=True, lazy="raise"
    )
    categories: Mapped[list["Category"]] = relationship(
        viewonly=True, lazy="raise"
    )


class HouseholdMembership(Record, Base):
    __tablename__ = "mh_household_memberships"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "user_id", name="uq_mh_membership_household_user"
        ),
        UniqueConstraint(
            "household_id",
            "user_id",
            "role",
            name="uq_mh_membership_owner_target",
        ),
        CheckConstraint("role IN ('owner', 'partner')", name="role"),
        CheckConstraint(
            "status IN ('active', 'left', 'removed')", name="status"
        ),
        CheckConstraint(
            "role <> 'owner' OR status = 'active'", name="active_owner"
        ),
        CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR (status <> 'active' AND ended_at IS NOT NULL)",
            name="ended_status",
        ),
        Index(
            "uq_mh_membership_single_owner",
            "household_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
        Index("ix_mh_membership_user_status", "user_id", "status"),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="CASCADE"),
        default=None,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_users.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16), default="partner", server_default="partner"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    household: Mapped["Household"] = relationship(
        foreign_keys=[household_id], viewonly=True, lazy="raise"
    )
    user: Mapped["User"] = relationship(viewonly=True, lazy="raise")


class FinancialAccount(Record, Base):
    __tablename__ = "mh_financial_accounts"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_mh_account_tenant_id"),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
        CheckConstraint(
            "account_type IN ('cash', 'bank', 'credit_card', 'savings', 'other')",
            name="type",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint(
            "opening_balance <> 'NaN'::numeric", name="finite_balance"
        ),
        Index(
            "ix_mh_accounts_household_archived", "household_id", "is_archived"
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(120), default="", server_default=""
    )
    account_type: Mapped[str] = mapped_column(
        String(20), default="cash", server_default="cash"
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="SAR", server_default="SAR"
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), default=Decimal("0"), server_default="0"
    )
    opening_date: Mapped[date] = mapped_column(
        Date, server_default=func.current_date()
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class Category(Record, Base):
    __tablename__ = "mh_categories"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", "kind", name="uq_mh_category_tenant_kind"
        ),
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
        UniqueConstraint(
            "household_id", "kind", "name", name="uq_mh_category_name"
        ),
        Index(
            "ix_mh_category_household_archived", "household_id", "is_archived"
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100), default="", server_default=""
    )
    kind: Mapped[str] = mapped_column(
        String(10), default="expense", server_default="expense"
    )
    icon: Mapped[str] = mapped_column(
        String(64), default="tag", server_default="tag"
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")


class RecurringTransactionRule(Record, Base):
    __tablename__ = "mh_recurring_transaction_rules"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", name="uq_mh_recurring_rule_tenant_id"
        ),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "account_id"],
            ["mh_financial_accounts.household_id", "mh_financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "category_id", "kind"],
            [
                "mh_categories.household_id",
                "mh_categories.id",
                "mh_categories.kind",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        CheckConstraint(
            "amount > 0 AND amount <> 'NaN'::numeric", name="positive_amount"
        ),
        CheckConstraint(
            "frequency IN ('daily', 'weekly', 'monthly')", name="frequency"
        ),
        CheckConstraint(
            "next_date >= start_date", name="next_date_after_start"
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="end_date_after_start",
        ),
        Index(
            "ix_mh_recurring_rules_tenant_active_next",
            "household_id",
            "is_active",
            "next_date",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(Uuid, default=None, nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(10), default="expense", server_default="expense"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), default=Decimal("0"), server_default="0"
    )
    description: Mapped[str] = mapped_column(
        Text, default="", server_default=""
    )
    frequency: Mapped[str] = mapped_column(
        String(10), default="monthly", server_default="monthly"
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )
    account: Mapped["FinancialAccount"] = relationship(
        viewonly=True, lazy="raise"
    )
    category: Mapped["Category"] = relationship(viewonly=True, lazy="raise")


class Transaction(Record, Base):
    __tablename__ = "mh_transactions"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", name="uq_mh_transaction_tenant_id"
        ),
        ForeignKeyConstraint(
            ["household_id", "account_id"],
            ["mh_financial_accounts.household_id", "mh_financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "category_id", "kind"],
            [
                "mh_categories.household_id",
                "mh_categories.id",
                "mh_categories.kind",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "recurring_rule_id"],
            [
                "mh_recurring_transaction_rules.household_id",
                "mh_recurring_transaction_rules.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "household_id",
            "recurring_rule_id",
            "scheduled_for",
            name="uq_mh_transaction_recurring_occurrence",
        ),
        CheckConstraint(
            "(recurring_rule_id IS NULL AND scheduled_for IS NULL) OR "
            "(recurring_rule_id IS NOT NULL AND scheduled_for IS NOT NULL)",
            name="recurring_fields_together",
        ),
        CheckConstraint("kind IN ('income', 'expense')", name="kind"),
        CheckConstraint(
            "amount > 0 AND amount <> 'NaN'::numeric", name="positive_amount"
        ),
        Index(
            "ix_mh_transactions_tenant_date",
            "household_id",
            "transaction_date",
            "id",
        ),
        Index(
            "ix_mh_transactions_account_date",
            "household_id",
            "account_id",
            "transaction_date",
        ),
        Index(
            "ix_mh_transactions_category_date",
            "household_id",
            "category_id",
            "kind",
            "transaction_date",
        ),
        Index(
            "ix_mh_transactions_creator", "household_id", "created_by_user_id"
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(Uuid, default=None, nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    kind: Mapped[str] = mapped_column(
        String(10), default="expense", server_default="expense"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), default=Decimal("0"), server_default="0"
    )
    transaction_date: Mapped[date] = mapped_column(
        Date, server_default=func.current_date()
    )
    description: Mapped[str] = mapped_column(
        Text, default="", server_default=""
    )
    recurring_rule_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    scheduled_for: Mapped[date | None] = mapped_column(Date, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    account: Mapped["FinancialAccount"] = relationship(
        viewonly=True, lazy="raise"
    )
    category: Mapped["Category"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )
    recurring_rule: Mapped["RecurringTransactionRule | None"] = relationship(
        viewonly=True, lazy="raise"
    )


class SavingsGoal(Record, Base):
    __tablename__ = "mh_savings_goals"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", name="uq_mh_savings_goal_tenant_id"
        ),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_required"),
        CheckConstraint(
            "target_amount > 0 AND target_amount < 'Infinity'::numeric",
            name="positive_finite_target",
        ),
        Index(
            "ix_mh_savings_goals_household_archived",
            "household_id",
            "is_archived",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(120), default="", server_default=""
    )
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    target_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False
    )
    target_date: Mapped[date | None] = mapped_column(Date, default=None)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class SavingsGoalAllocation(Record, Base):
    __tablename__ = "mh_savings_goal_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "goal_id"],
            ["mh_savings_goals.household_id", "mh_savings_goals.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "amount <> 0 AND amount > '-Infinity'::numeric "
            "AND amount < 'Infinity'::numeric",
            name="nonzero_finite_amount",
        ),
        Index(
            "ix_mh_savings_allocations_household_goal_date",
            "household_id",
            "goal_id",
            "event_date",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    goal_id: Mapped[UUID] = mapped_column(Uuid, default=None, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    event_date: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    goal: Mapped["SavingsGoal"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class Debt(Record, Base):
    __tablename__ = "mh_debts"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_mh_debt_tenant_id"),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "direction IN ('payable', 'receivable')", name="direction"
        ),
        CheckConstraint("length(trim(title)) > 0", name="title_required"),
        CheckConstraint(
            "length(trim(counterparty)) > 0", name="counterparty_required"
        ),
        CheckConstraint(
            "principal > 0 AND principal < 1000000000000000 "
            "AND principal <> 'NaN'::numeric",
            name="positive_finite_principal",
        ),
        CheckConstraint(
            "installment_count BETWEEN 1 AND 120", name="installment_count"
        ),
        Index("ix_mh_debts_household_archived", "household_id", "is_archived"),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(120), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    principal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class DebtInstallment(Record, Base):
    __tablename__ = "mh_debt_installments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "debt_id"],
            ["mh_debts.household_id", "mh_debts.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "household_id",
            "debt_id",
            "sequence_no",
            name="uq_mh_debt_installment_sequence",
        ),
        CheckConstraint("sequence_no > 0", name="positive_sequence"),
        CheckConstraint(
            "amount > 0 AND amount < 'Infinity'::numeric "
            "AND amount <> 'NaN'::numeric",
            name="positive_finite_amount",
        ),
        Index(
            "ix_mh_debt_installments_household_due", "household_id", "due_date"
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    debt_id: Mapped[UUID] = mapped_column(Uuid, default=None, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    debt: Mapped["Debt"] = relationship(viewonly=True, lazy="raise")


class DebtPayment(Record, Base):
    __tablename__ = "mh_debt_payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "debt_id"],
            ["mh_debts.household_id", "mh_debts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "amount > 0 AND amount < 'Infinity'::numeric "
            "AND amount <> 'NaN'::numeric",
            name="positive_finite_amount",
        ),
        Index(
            "ix_mh_debt_payments_household_debt_paid",
            "household_id",
            "debt_id",
            "paid_on",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    debt_id: Mapped[UUID] = mapped_column(Uuid, default=None, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    debt: Mapped["Debt"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class MonthlyCategoryBudget(Record, Base):
    __tablename__ = "mh_monthly_category_budgets"
    __table_args__ = (
        UniqueConstraint(
            "household_id",
            "category_id",
            "year",
            "month",
            name="uq_mh_budget_category_month",
        ),
        UniqueConstraint("household_id", "id", name="uq_mh_budget_tenant_id"),
        ForeignKeyConstraint(
            ["household_id", "category_id", "category_kind"],
            [
                "mh_categories.household_id",
                "mh_categories.id",
                "mh_categories.kind",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("category_kind = 'expense'", name="expense_only"),
        CheckConstraint(
            "month BETWEEN 1 AND 12 AND year BETWEEN 1900 AND 9999",
            name="period",
        ),
        CheckConstraint(
            "amount >= 0 AND amount <> 'NaN'::numeric",
            name="nonnegative_amount",
        ),
        CheckConstraint(
            "alert_threshold_percent BETWEEN 1 AND 100", name="threshold"
        ),
        Index("ix_mh_budgets_tenant_period", "household_id", "year", "month"),
        Index("ix_mh_budgets_creator", "household_id", "created_by_user_id"),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    category_kind: Mapped[str] = mapped_column(
        String(10), default="expense", server_default="expense"
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    year: Mapped[int] = mapped_column(
        Integer, server_default=text("EXTRACT(YEAR FROM CURRENT_DATE)::integer")
    )
    month: Mapped[int] = mapped_column(
        Integer,
        server_default=text("EXTRACT(MONTH FROM CURRENT_DATE)::integer"),
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), default=Decimal("0"), server_default="0"
    )
    alert_threshold_percent: Mapped[int] = mapped_column(
        Integer, default=80, server_default="80"
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    category: Mapped["Category"] = relationship(viewonly=True, lazy="raise")
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class PartnerInvitation(Record, Base):
    __tablename__ = "mh_partner_invitations"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", name="uq_mh_invitation_tenant_id"
        ),
        ForeignKeyConstraint(
            ["household_id", "invited_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            name="fk_mh_invitation_inviter_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "accepted_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            name="fk_mh_invitation_acceptor_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "email = lower(trim(email)) AND position('@' in email) > 1",
            name="normalized_email",
        ),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_digest"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'expired', 'revoked')",
            name="status",
        ),
        CheckConstraint("expires_at > created_at", name="expiry"),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR (status <> 'pending' AND resolved_at IS NOT NULL)",
            name="resolution",
        ),
        CheckConstraint(
            "(status = 'accepted' AND accepted_by_user_id IS NOT NULL AND resolved_at < expires_at) OR (status <> 'accepted' AND accepted_by_user_id IS NULL)",
            name="acceptance",
        ),
        CheckConstraint(
            "accepted_by_user_id IS NULL OR accepted_by_user_id <> invited_by_user_id",
            name="not_self",
        ),
        Index(
            "uq_mh_invitation_pending",
            "household_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_mh_invitation_email_status", "email", "status"),
        Index("ix_mh_invitation_expiry", "status", "expires_at"),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    invited_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, default=None, nullable=False
    )
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    email: Mapped[str] = mapped_column(
        String(320), default="", server_default=""
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, default="", deferred=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP + INTERVAL '7 days'"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    inviter: Mapped["HouseholdMembership"] = relationship(
        foreign_keys=[household_id, invited_by_user_id],
        viewonly=True,
        lazy="raise",
    )
    accepted_membership: Mapped["HouseholdMembership | None"] = relationship(
        foreign_keys=[household_id, accepted_by_user_id],
        viewonly=True,
        lazy="raise",
    )


class Notification(Record, Base):
    __tablename__ = "mh_notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "transaction_id"],
            ["mh_transactions.household_id", "mh_transactions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "budget_id"],
            [
                "mh_monthly_category_budgets.household_id",
                "mh_monthly_category_budgets.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "invitation_id"],
            [
                "mh_partner_invitations.household_id",
                "mh_partner_invitations.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "member_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "kind IN ('partner_invitation', 'invitation_accepted', 'partner_transaction', 'budget_warning', 'budget_exceeded', 'monthly_summary', 'reminder', 'system')",
            name="kind",
        ),
        CheckConstraint(
            "channel IN ('in_app', 'email', 'push')", name="channel"
        ),
        CheckConstraint(
            "delivery_status IN ('pending', 'sent', 'failed', 'suppressed')",
            name="delivery_status",
        ),
        CheckConstraint("length(trim(title)) > 0", name="title_required"),
        CheckConstraint(
            "member_user_id IS NULL OR member_user_id = recipient_user_id",
            name="recipient_member",
        ),
        CheckConstraint(
            "(kind = 'partner_invitation' AND invitation_id IS NOT NULL AND transaction_id IS NULL AND budget_id IS NULL) OR (kind <> 'partner_invitation' AND member_user_id IS NOT NULL)",
            name="recipient_scope",
        ),
        CheckConstraint(
            "read_at IS NULL OR read_at >= created_at", name="read_time"
        ),
        Index(
            "ix_mh_notification_inbox",
            "recipient_user_id",
            "household_id",
            "read_at",
            "created_at",
        ),
        Index("ix_mh_notification_delivery", "delivery_status", "scheduled_at"),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    recipient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_users.id", ondelete="CASCADE"),
        default=None,
        nullable=False,
    )
    # Invitations may reach registered users before they become household members.
    member_user_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    transaction_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    budget_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    invitation_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    kind: Mapped[str] = mapped_column(
        String(32), default="system", server_default="system"
    )
    channel: Mapped[str] = mapped_column(
        String(10), default="in_app", server_default="in_app"
    )
    title: Mapped[str] = mapped_column(
        String(200), default="", server_default=""
    )
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    delivery_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    recipient: Mapped["User"] = relationship(viewonly=True, lazy="raise")
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    transaction: Mapped["Transaction | None"] = relationship(
        viewonly=True, lazy="raise"
    )
    budget: Mapped["MonthlyCategoryBudget | None"] = relationship(
        viewonly=True, lazy="raise"
    )
    invitation: Mapped["PartnerInvitation | None"] = relationship(
        viewonly=True, lazy="raise"
    )


class NotificationPreference(Record, Base):
    __tablename__ = "mh_notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "kind",
            "channel",
            name="uq_mh_preference_user_kind_channel",
        ),
        CheckConstraint(
            "kind IN ('partner_invitation', 'invitation_accepted', 'partner_transaction', 'budget_warning', 'budget_exceeded', 'monthly_summary', 'reminder', 'system')",
            name="kind",
        ),
        CheckConstraint(
            "channel IN ('in_app', 'email', 'push')", name="channel"
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_users.id", ondelete="CASCADE"),
        default=None,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(32), default="system", server_default="system"
    )
    channel: Mapped[str] = mapped_column(
        String(10), default="in_app", server_default="in_app"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    user: Mapped["User"] = relationship(viewonly=True, lazy="raise")
