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
    JSON,
    LargeBinary,
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


class WaitlistLead(Record, Base):
    __tablename__ = "mh_waitlist_leads"
    __table_args__ = (
        UniqueConstraint(
            "contact_kind", "contact_value", name="uq_mh_waitlist_lead_contact"
        ),
        CheckConstraint(
            "contact_kind IN ('email', 'phone')", name="contact_kind"
        ),
        CheckConstraint(
            "length(trim(contact_value)) > 0", name="contact_required"
        ),
        CheckConstraint(
            "(contact_kind = 'email' AND contact_value = lower(trim(contact_value)) "
            "AND position('@' in contact_value) > 1) OR "
            "(contact_kind = 'phone' AND contact_value ~ '^\\+[1-9][0-9]{1,14}$')",
            name="normalized_contact",
        ),
        CheckConstraint("consent_contact = true", name="explicit_consent"),
        CheckConstraint(
            "json_typeof(problem_codes) = 'array'", name="problem_codes_array"
        ),
        CheckConstraint(
            "length(trim(referral_code)) > 0", name="referral_code_required"
        ),
        CheckConstraint(
            "referred_by_id IS NULL OR referred_by_id <> id",
            name="not_self_referred",
        ),
        CheckConstraint(
            "founder_decision IN ('pending', 'reserved', 'free')",
            name="founder_decision",
        ),
        CheckConstraint(
            "(founder_decision = 'reserved' AND reserved_at IS NOT NULL) OR "
            "(founder_decision <> 'reserved' AND reserved_at IS NULL)",
            name="reservation_consistency",
        ),
        Index("ix_mh_waitlist_leads_decision", "founder_decision"),
        Index("ix_mh_waitlist_leads_referral", "referred_by_id"),
    )
    contact_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    contact_value: Mapped[str] = mapped_column(String(320), nullable=False)
    consent_contact: Mapped[bool] = mapped_column(Boolean, nullable=False)
    problem_codes: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default=text("'[]'::json"), nullable=False
    )
    invite_clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    referral_code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False
    )
    referred_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("mh_waitlist_leads.id", ondelete="SET NULL"),
        default=None,
        nullable=True,
    )
    founder_decision: Mapped[str] = mapped_column(
        String(12), default="pending", server_default="pending", nullable=False
    )
    reserved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
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


class AuthenticationAttempt(Record, Base):
    __tablename__ = "mh_authentication_attempts"
    __table_args__ = (
        CheckConstraint(
            "identifier_digest ~ '^[0-9a-f]{64}$'",
            name="identifier_sha256_digest",
        ),
        CheckConstraint(
            "attempt_count BETWEEN 1 AND 100",
            name="bounded_positive_attempt_count",
        ),
        Index("ix_mh_authentication_attempts_locked_until", "locked_until"),
    )
    # Digest of the normalized login identifier; never store the identifier itself.
    identifier_digest: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, deferred=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )


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
            "role <> 'owner' OR (can_add_transactions = true AND can_edit_budgets = true)",
            name="owner_full_permissions",
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
    can_add_transactions: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    can_edit_budgets: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    # Application authorization grants owners access regardless of this opt-in flag.
    can_view_commitments: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
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


class HouseholdAccountRestriction(Record, Base):
    __tablename__ = "mh_household_account_restrictions"
    __table_args__ = (
        UniqueConstraint(
            "household_id",
            "member_user_id",
            "account_id",
            name="uq_mh_account_restriction_member_account",
        ),
        ForeignKeyConstraint(
            ["household_id", "member_user_id"],
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
        Index(
            "ix_mh_account_restrictions_household_member",
            "household_id",
            "member_user_id",
        ),
        Index(
            "ix_mh_account_restrictions_household_account",
            "household_id",
            "account_id",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    member_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class FinancialAccount(Record, Base):
    __tablename__ = "mh_financial_accounts"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_mh_account_tenant_id"),
        CheckConstraint(
            "scope IS NULL OR scope IN ('personal', 'shared')", name="scope"
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
    scope: Mapped[str | None] = mapped_column(
        String(10), default=None, nullable=True
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


class AccountTransfer(Record, Base):
    __tablename__ = "mh_account_transfers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "source_account_id"],
            ["mh_financial_accounts.household_id", "mh_financial_accounts.id"],
            name="fk_mh_account_transfers_source_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "destination_account_id"],
            ["mh_financial_accounts.household_id", "mh_financial_accounts.id"],
            name="fk_mh_account_transfers_destination_account",
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
            "source_account_id <> destination_account_id",
            name="distinct_accounts",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint(
            "amount > 0 AND amount < 'Infinity'::numeric "
            "AND amount <> 'NaN'::numeric",
            name="positive_finite_amount",
        ),
        Index(
            "ix_mh_account_transfers_source_date",
            "household_id",
            "source_account_id",
            "transfer_date",
        ),
        Index(
            "ix_mh_account_transfers_destination_date",
            "household_id",
            "destination_account_id",
            "transfer_date",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    source_account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    destination_account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    source_account: Mapped["FinancialAccount"] = relationship(
        foreign_keys=[household_id, source_account_id],
        viewonly=True,
        lazy="raise",
    )
    destination_account: Mapped["FinancialAccount"] = relationship(
        foreign_keys=[household_id, destination_account_id],
        viewonly=True,
        lazy="raise",
    )
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class Transaction(Record, Base):
    __tablename__ = "mh_transactions"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", name="uq_mh_transaction_tenant_id"
        ),
        ForeignKeyConstraint(
            ["household_id", "paid_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            name="fk_mh_transactions_payer_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "scope IS NULL OR scope IN ('personal', 'shared')", name="scope"
        ),
        Index("ix_mh_transactions_payer", "household_id", "paid_by_user_id"),
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
    scope: Mapped[str | None] = mapped_column(
        String(10), default=None, nullable=True
    )
    # Explicitly documented payer only; never derived from the record creator.
    paid_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, default=None, nullable=True
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
        foreign_keys=[household_id, created_by_user_id],
        viewonly=True,
        lazy="raise",
    )
    recurring_rule: Mapped["RecurringTransactionRule | None"] = relationship(
        viewonly=True, lazy="raise"
    )


class TransactionReceipt(Record, Base):
    __tablename__ = "mh_transaction_receipts"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "transaction_id", name="uq_mh_receipt_transaction"
        ),
        ForeignKeyConstraint(
            ["household_id", "transaction_id"],
            ["mh_transactions.household_id", "mh_transactions.id"],
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
        CheckConstraint("length(trim(filename)) > 0", name="filename_required"),
        CheckConstraint(
            "mime_type IN ('image/png', 'image/jpeg', 'application/pdf', 'image/webp')",
            name="allowed_mime_type",
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 5242880", name="size_bytes_range"
        ),
        CheckConstraint(
            "octet_length(content) = size_bytes", name="content_size_matches"
        ),
        Index(
            "ix_mh_transaction_receipts_household_created",
            "household_id",
            "created_at",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        nullable=False,
    )
    transaction_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, deferred=True
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    transaction: Mapped["Transaction"] = relationship(
        viewonly=True, lazy="raise"
    )
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


class TransactionAuditEvent(Record, Base):
    __tablename__ = "mh_transaction_audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "transaction_id"],
            ["mh_transactions.household_id", "mh_transactions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "actor_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "action IN ('created', 'updated', 'deleted', 'auto_created')",
            name="action",
        ),
        CheckConstraint(
            "(action = 'auto_created' AND actor_user_id IS NULL) OR "
            "(action <> 'auto_created' AND actor_user_id IS NOT NULL)",
            name="actor_for_action",
        ),
        CheckConstraint(
            "json_typeof(before_data) = 'object' AND "
            "json_typeof(after_data) = 'object'",
            name="snapshot_objects",
        ),
        CheckConstraint(
            "(before_data::jsonb - ARRAY['account_id', 'category_id', 'kind', "
            "'amount', 'transaction_date', 'description']) = '{}'::jsonb AND "
            "(after_data::jsonb - ARRAY['account_id', 'category_id', 'kind', "
            "'amount', 'transaction_date', 'description']) = '{}'::jsonb",
            name="snapshot_fields",
        ),
        CheckConstraint(
            "json_typeof(changed_fields) = 'array' AND "
            'changed_fields::jsonb <@ \'["account_id", "category_id", '
            '"kind", "amount", "transaction_date", '
            '"description"]\'::jsonb',
            name="changed_fields_allowed",
        ),
        Index(
            "ix_mh_transaction_audit_events_history",
            "household_id",
            "transaction_id",
            "created_at",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    before_data: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'::json"), nullable=False
    )
    after_data: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'::json"), nullable=False
    )
    changed_fields: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default=text("'[]'::json"), nullable=False
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


class Bill(Record, Base):
    __tablename__ = "mh_bills"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_mh_bill_tenant_id"),
        ForeignKeyConstraint(
            ["household_id", "account_id"],
            ["mh_financial_accounts.household_id", "mh_financial_accounts.id"],
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
        CheckConstraint("length(trim(title)) > 0", name="title_required"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint(
            "amount > 0 AND amount < 'Infinity'::numeric "
            "AND amount <> 'NaN'::numeric",
            name="positive_finite_amount",
        ),
        CheckConstraint("status IN ('unpaid', 'paid')", name="status"),
        CheckConstraint(
            "(status = 'paid' AND paid_on IS NOT NULL) OR "
            "(status = 'unpaid' AND paid_on IS NULL)",
            name="paid_date_consistency",
        ),
        CheckConstraint(
            "remind_days BETWEEN 0 AND 365", name="remind_days_range"
        ),
        Index("ix_mh_bills_household_due", "household_id", "due_date"),
        Index(
            "ix_mh_bills_household_account_due",
            "household_id",
            "account_id",
            "due_date",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    # An account is required so account restrictions and currency are unambiguous.
    account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), default="unpaid", server_default="unpaid", nullable=False
    )
    paid_on: Mapped[date | None] = mapped_column(Date, default=None)
    remind_days: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    account: Mapped["FinancialAccount"] = relationship(
        viewonly=True, lazy="raise"
    )
    creator_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )


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
            "currency",
            name="uq_mh_budget_category_month_currency",
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
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
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
    currency: Mapped[str] = mapped_column(
        String(3), default="SAR", server_default="SAR", nullable=False
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


class ReminderDelivery(Record, Base):
    __tablename__ = "mh_reminder_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "recipient_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "bill_id"],
            ["mh_bills.household_id", "mh_bills.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["installment_id"],
            ["mh_debt_installments.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "household_id",
            "recipient_user_id",
            "channel",
            "source_kind",
            "source_id",
            "due_date",
            name="uq_mh_reminder_delivery_occurrence",
        ),
        CheckConstraint("channel IN ('in_app', 'email')", name="channel"),
        CheckConstraint(
            "source_kind IN ('bill', 'installment')", name="source_kind"
        ),
        CheckConstraint(
            "(source_kind = 'bill' AND bill_id IS NOT NULL "
            "AND bill_id = source_id AND installment_id IS NULL) OR "
            "(source_kind = 'installment' AND installment_id IS NOT NULL "
            "AND installment_id = source_id AND bill_id IS NULL)",
            name="source_reference",
        ),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'suppressed')",
            name="status",
        ),
        CheckConstraint(
            "(status = 'sent' AND delivered_at IS NOT NULL) OR "
            "(status <> 'sent' AND delivered_at IS NULL)",
            name="delivery_time",
        ),
        Index(
            "ix_mh_reminder_deliveries_pending",
            "household_id",
            "channel",
            "status",
            "scheduled_at",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"),
        default=None,
        nullable=False,
    )
    recipient_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    channel: Mapped[str] = mapped_column(
        String(10), default="in_app", server_default="in_app", nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    bill_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    installment_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    household: Mapped["Household"] = relationship(viewonly=True, lazy="raise")
    recipient_membership: Mapped["HouseholdMembership"] = relationship(
        viewonly=True, lazy="raise"
    )
    bill: Mapped["Bill | None"] = relationship(viewonly=True, lazy="raise")
    installment: Mapped["DebtInstallment | None"] = relationship(
        viewonly=True, lazy="raise"
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


class HouseholdTask(Record, Base):
    __tablename__ = "mh_household_tasks"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_mh_task_tenant_id"),
        ForeignKeyConstraint(
            ["household_id", "account_id"],
            ["mh_financial_accounts.household_id", "mh_financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            name="fk_mh_tasks_creator_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "assignee_user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            name="fk_mh_tasks_assignee_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint("length(trim(title)) > 0", name="title_required"),
        CheckConstraint("status IN ('pending', 'complete')", name="status"),
        Index(
            "ix_mh_tasks_tenant_status_due",
            "household_id",
            "status",
            "due_date",
        ),
        Index("ix_mh_tasks_tenant_account", "household_id", "account_id"),
        Index(
            "ix_mh_tasks_tenant_creator", "household_id", "created_by_user_id"
        ),
        Index(
            "ix_mh_tasks_tenant_assignee", "household_id", "assignee_user_id"
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Linked tasks must inherit account visibility in application authorization.
    account_id: Mapped[UUID | None] = mapped_column(
        Uuid, default=None, nullable=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, default=None, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(
        Date, default=None, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(10), default="pending", server_default="pending", nullable=False
    )


class BillSplitRule(Record, Base):
    __tablename__ = "mh_bill_split_rules"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", name="uq_mh_bill_split_rule_tenant_id"
        ),
        UniqueConstraint(
            "household_id", "bill_id", name="uq_mh_bill_split_rule_bill"
        ),
        ForeignKeyConstraint(
            ["household_id", "bill_id"],
            ["mh_bills.household_id", "mh_bills.id"],
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
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint("mode IN ('equal', 'income')", name="mode"),
        Index(
            "ix_mh_bill_split_rules_creator",
            "household_id",
            "created_by_user_id",
        ),
        Index("ix_mh_bill_split_rules_currency", "household_id", "currency"),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"), nullable=False
    )
    bill_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    mode: Mapped[str] = mapped_column(
        String(10), default="equal", server_default="equal", nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class BillSplitShare(Record, Base):
    __tablename__ = "mh_bill_split_shares"
    __table_args__ = (
        UniqueConstraint(
            "household_id",
            "rule_id",
            "member_user_id",
            name="uq_mh_bill_split_share_member",
        ),
        ForeignKeyConstraint(
            ["household_id", "rule_id"],
            ["mh_bill_split_rules.household_id", "mh_bill_split_rules.id"],
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
            "percentage BETWEEN 0 AND 100 AND percentage <> 'NaN'::numeric",
            name="percentage_range",
        ),
        CheckConstraint(
            "declared_income IS NULL OR (declared_income >= 0 "
            "AND declared_income < 'Infinity'::numeric AND declared_income <> 'NaN'::numeric)",
            name="nonnegative_finite_income",
        ),
        CheckConstraint(
            "share_amount >= 0 AND share_amount < 'Infinity'::numeric "
            "AND share_amount <> 'NaN'::numeric",
            name="nonnegative_finite_share",
        ),
        Index(
            "ix_mh_bill_split_shares_member", "household_id", "member_user_id"
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"), nullable=False
    )
    rule_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    member_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    # Preserve the declared income snapshot, not a live link to financial totals.
    declared_income: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), default=None, nullable=True
    )
    # Persist the explicitly calculated snapshot; this does not record a payment.
    share_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False
    )


class SafeBalanceSetting(Record, Base):
    __tablename__ = "mh_safe_balance_settings"
    __table_args__ = (
        UniqueConstraint(
            "household_id",
            "user_id",
            "currency",
            name="uq_mh_safe_balance_person_currency",
        ),
        ForeignKeyConstraint(
            ["household_id", "user_id"],
            [
                "mh_household_memberships.household_id",
                "mh_household_memberships.user_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint("payday_day BETWEEN 1 AND 31", name="payday_day_range"),
        CheckConstraint(
            "monthly_essentials >= 0 AND monthly_essentials < 'Infinity'::numeric "
            "AND monthly_essentials <> 'NaN'::numeric",
            name="nonnegative_finite_essentials",
        ),
        CheckConstraint(
            "additional_due_allocation IS NULL OR (additional_due_allocation >= 0 "
            "AND additional_due_allocation < 'Infinity'::numeric "
            "AND additional_due_allocation <> 'NaN'::numeric)",
            name="nonnegative_finite_allocation",
        ),
        Index("ix_mh_safe_balance_settings_user", "user_id", "household_id"),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    payday_day: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_essentials: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), default=Decimal("0"), server_default="0", nullable=False
    )
    additional_due_allocation: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), default=None, nullable=True
    )


class SeasonalFund(Record, Base):
    __tablename__ = "mh_seasonal_funds"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "id", name="uq_mh_seasonal_fund_tenant_id"
        ),
        ForeignKeyConstraint(
            ["household_id", "account_id"],
            ["mh_financial_accounts.household_id", "mh_financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "paid_transaction_id"],
            ["mh_transactions.household_id", "mh_transactions.id"],
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
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint("length(trim(title)) > 0", name="title_required"),
        CheckConstraint(
            "target_amount > 0 AND target_amount < 'Infinity'::numeric "
            "AND target_amount <> 'NaN'::numeric",
            name="positive_finite_target",
        ),
        CheckConstraint(
            "contribution_amount > 0 AND contribution_amount < 'Infinity'::numeric "
            "AND contribution_amount <> 'NaN'::numeric",
            name="positive_finite_contribution",
        ),
        CheckConstraint(
            "target_date >= reserve_start_date", name="target_after_start"
        ),
        CheckConstraint("frequency IN ('monthly', 'weekly')", name="frequency"),
        CheckConstraint(
            "status IN ('active', 'paid', 'archived')", name="status"
        ),
        CheckConstraint(
            "paid_transaction_id IS NULL OR status IN ('paid', 'archived')",
            name="paid_reference_status",
        ),
        Index(
            "ix_mh_seasonal_funds_currency_status_target",
            "household_id",
            "currency",
            "status",
            "target_date",
        ),
        Index("ix_mh_seasonal_funds_account", "household_id", "account_id"),
        Index(
            "ix_mh_seasonal_funds_payment",
            "household_id",
            "paid_transaction_id",
        ),
        Index(
            "ix_mh_seasonal_funds_creator", "household_id", "created_by_user_id"
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    account_id: Mapped[UUID | None] = mapped_column(
        Uuid, default=None, nullable=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Reservations are derived for display only, never posted as transactions.
    contribution_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False
    )
    reserve_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    frequency: Mapped[str] = mapped_column(
        String(10), default="monthly", server_default="monthly", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(10), default="active", server_default="active", nullable=False
    )
    paid_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, default=None, nullable=True
    )


class TransactionSplitShare(Record, Base):
    __tablename__ = "mh_transaction_split_shares"
    __table_args__ = (
        UniqueConstraint(
            "household_id",
            "transaction_id",
            "member_user_id",
            name="uq_mh_transaction_split_share_member",
        ),
        ForeignKeyConstraint(
            ["household_id", "transaction_id"],
            ["mh_transactions.household_id", "mh_transactions.id"],
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
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_code"),
        CheckConstraint(
            "owed_amount >= 0 AND owed_amount < 'Infinity'::numeric "
            "AND owed_amount <> 'NaN'::numeric",
            name="nonnegative_finite_owed",
        ),
        CheckConstraint(
            "percentage BETWEEN 0 AND 100 AND percentage <> 'NaN'::numeric",
            name="percentage_range",
        ),
        Index(
            "ix_mh_transaction_split_shares_member_currency",
            "household_id",
            "member_user_id",
            "currency",
        ),
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("mh_households.id", ondelete="RESTRICT"), nullable=False
    )
    transaction_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    member_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Documented shares only; no creator-based inference or automatic settlement.
    owed_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)


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
