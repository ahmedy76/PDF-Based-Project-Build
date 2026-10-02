import reflex as rx

from app.observability import report_unexpected
from typing import TypedDict
from uuid import UUID

from sqlalchemy import select

from app import models as m
from app.states.auth import AuthState

import logging


class AccountAccess(TypedDict):
    id: str
    name: str
    currency: str
    archived: bool
    visible: bool


class MemberAccess(TypedDict):
    id: str
    name: str
    can_add_transactions: bool
    can_edit_budgets: bool
    accounts: list[AccountAccess]


class MemberAccessState(rx.State):
    members: list[MemberAccess] = []
    owner: bool = False
    message: str = ""
    error: bool = False

    def _owner_household(self, db, auth):
        user, membership = auth._household(db)
        if membership.role != "owner" or membership.user_id != user.id:
            raise PermissionError("هذه الإعدادات متاحة لمالك الأسرة فقط.")
        household = db.scalar(
            select(m.Household)
            .where(
                m.Household.id == membership.household_id,
                m.Household.status == "active",
            )
            .with_for_update()
        )
        if household is None or household.owner_user_id != user.id:
            raise PermissionError("هذه الإعدادات متاحة لمالك الأسرة فقط.")
        return user, household

    def _target(self, db, household, user, target_id: str):
        try:
            target_uuid = UUID(target_id)
        except (ValueError, TypeError, AttributeError) as e:
            logging.exception("Unexpected error")
            raise ValueError("العضو غير متاح لهذه الأسرة.")
        target = db.scalar(
            select(m.HouseholdMembership)
            .where(
                m.HouseholdMembership.household_id == household.id,
                m.HouseholdMembership.user_id == target_uuid,
                m.HouseholdMembership.status == "active",
                m.HouseholdMembership.role == "partner",
                m.HouseholdMembership.user_id != user.id,
                m.HouseholdMembership.user_id != household.owner_user_id,
            )
            .with_for_update()
        )
        if target is None:
            raise ValueError("العضو غير متاح لهذه الأسرة.")
        return target

    def _rows(self, db, household_id: UUID) -> list[MemberAccess]:
        partners = db.execute(
            select(m.HouseholdMembership, m.User.display_name)
            .join(m.User, m.User.id == m.HouseholdMembership.user_id)
            .where(
                m.HouseholdMembership.household_id == household_id,
                m.HouseholdMembership.role == "partner",
                m.HouseholdMembership.status == "active",
                m.User.status == "active",
            )
            .order_by(m.User.display_name, m.HouseholdMembership.user_id)
        ).all()
        if not partners:
            return []
        accounts = db.scalars(
            select(m.FinancialAccount)
            .where(m.FinancialAccount.household_id == household_id)
            .order_by(
                m.FinancialAccount.is_archived,
                m.FinancialAccount.name,
                m.FinancialAccount.id,
            )
        ).all()
        denied = {
            (r.member_user_id, r.account_id)
            for r in db.scalars(
                select(m.HouseholdAccountRestriction).where(
                    m.HouseholdAccountRestriction.household_id == household_id
                )
            ).all()
        }
        return [
            {
                "id": str(member.user_id),
                "name": name,
                "can_add_transactions": member.can_add_transactions,
                "can_edit_budgets": member.can_edit_budgets,
                "accounts": [
                    {
                        "id": str(account.id),
                        "name": account.name,
                        "currency": account.currency,
                        "archived": account.is_archived,
                        "visible": (member.user_id, account.id) not in denied,
                    }
                    for account in accounts
                ],
            }
            for member, name in partners
        ]

    @rx.event
    async def load(self):
        self.members = []
        self.owner = False
        self.message = ""
        self.error = False
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as session:

                def read(db):
                    user, member = auth._household(db)
                    if member.role != "owner" or member.user_id != user.id:
                        return False, []
                    household = db.get(m.Household, member.household_id)
                    if household is None or household.owner_user_id != user.id:
                        return False, []
                    return True, self._rows(db, household.id)

                owner, rows = await session.run_sync(read)
            self.owner = owner
            self.members = rows
        except PermissionError:
            logging.exception("Unexpected error")
            self.members = []
            self.owner = False
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("member_access.load", e)
            self.members = []
            self.owner = False
            self.message = "تعذر تحميل صلاحيات الأعضاء. أعد المحاولة."
            self.error = True

    @rx.event
    async def toggle_permission(self, target_id: str, permission: str):
        try:
            if permission not in ("can_add_transactions", "can_edit_budgets"):
                raise ValueError("صلاحية غير مدعومة.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as session:

                def update(db):
                    user, household = self._owner_household(db, auth)
                    target = self._target(db, household, user, target_id)
                    setattr(target, permission, not getattr(target, permission))
                    db.commit()
                    return self._rows(db, household.id)

                rows = await session.run_sync(update)
            self.members = rows
            self.owner = True
            self.message = "حُفظت صلاحية العضو بنجاح."
            self.error = False
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            if isinstance(e, PermissionError):
                self.members = []
                self.owner = False
            self.message = str(e)
            self.error = True
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("member_access.toggle_permission", e)
            self.message = "تعذر حفظ صلاحية العضو. أعد المحاولة."
            self.error = True

    @rx.event
    async def toggle_account(self, target_id: str, account_id: str):
        try:
            try:
                account_uuid = UUID(account_id)
            except (ValueError, TypeError, AttributeError) as e:
                logging.exception("Unexpected error")
                raise ValueError("الحساب غير متاح لهذه الأسرة.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as session:

                def update(db):
                    user, household = self._owner_household(db, auth)
                    target = self._target(db, household, user, target_id)
                    account = db.scalar(
                        select(m.FinancialAccount)
                        .where(
                            m.FinancialAccount.id == account_uuid,
                            m.FinancialAccount.household_id == household.id,
                        )
                        .with_for_update()
                    )
                    if account is None:
                        raise ValueError("الحساب غير متاح لهذه الأسرة.")
                    restriction = db.scalar(
                        select(m.HouseholdAccountRestriction)
                        .where(
                            m.HouseholdAccountRestriction.household_id
                            == household.id,
                            m.HouseholdAccountRestriction.member_user_id
                            == target.user_id,
                            m.HouseholdAccountRestriction.account_id
                            == account.id,
                        )
                        .with_for_update()
                    )
                    if restriction is None:
                        db.add(
                            m.HouseholdAccountRestriction(
                                household_id=household.id,
                                member_user_id=target.user_id,
                                account_id=account.id,
                            )
                        )
                    else:
                        db.delete(restriction)
                    db.commit()
                    return self._rows(db, household.id)

                rows = await session.run_sync(update)
            self.members = rows
            self.owner = True
            self.message = "حُفظ حق الاطلاع على الحساب بنجاح."
            self.error = False
        except (ValueError, PermissionError) as e:
            logging.exception("Unexpected error")
            self.message = str(e)
            self.error = True
        except Exception as e:
            logging.exception("Unexpected error")
            report_unexpected("member_access.toggle_account", e)
            self.message = "تعذر حفظ حق الاطلاع. أعد المحاولة."
            self.error = True
