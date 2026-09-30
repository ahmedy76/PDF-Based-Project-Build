import reflex as rx

import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import func, select

from app import models as m
from app.states.auth import AuthState
from app.states.ledger import LedgerState


class AllocationRow(TypedDict):
    id: str
    kind: str
    amount: str
    date: str
    note: str


class GoalRow(TypedDict):
    id: str
    name: str
    description: str
    amount: str
    target: str
    target_amount: str
    remaining: str
    date: str
    status: str
    percent: str
    progress: float
    history: list[AllocationRow]


class GoalState(rx.State):
    goals: list[GoalRow] = []
    archived_goals: list[GoalRow] = []
    active_count: int = 0
    completed_count: int = 0
    message: str = ""
    error: str = ""
    editor: str = ""
    edit_id: str = ""
    allocation_kind: str = "add"
    allocation_name: str = ""
    draft: dict[str, str] = {
        "name": "",
        "description": "",
        "target_amount": "",
        "target_date": "",
    }

    def _uuid(self, value: str) -> UUID:
        try:
            return UUID(str(value))
        except (ValueError, TypeError, AttributeError) as e:
            logging.exception("Unexpected error")
            raise ValueError("الهدف غير موجود أو غير متاح لهذه الأسرة.") from e

    def _guard(self, db, hid: UUID, uid: UUID):
        household = db.scalar(
            select(m.Household)
            .where(m.Household.id == hid, m.Household.status == "active")
            .with_for_update()
        )
        member = db.scalar(
            select(m.HouseholdMembership.id).where(
                m.HouseholdMembership.household_id == hid,
                m.HouseholdMembership.user_id == uid,
                m.HouseholdMembership.status == "active",
            )
        )
        if household is None or member is None:
            raise PermissionError("لا توجد عضوية أسرة نشطة.")

    def _goal(self, db, hid: UUID, goal_id: str):
        goal = db.scalar(
            select(m.SavingsGoal)
            .where(
                m.SavingsGoal.household_id == hid,
                m.SavingsGoal.id == self._uuid(goal_id),
            )
            .with_for_update()
        )
        if goal is None:
            raise ValueError("الهدف غير موجود أو غير متاح لهذه الأسرة.")
        return goal

    def _save_goal(
        self, db, hid: UUID, uid: UUID, data: dict[str, Any], edit_id: str = ""
    ):
        self._guard(db, hid, uid)
        goal = (
            self._goal(db, hid, edit_id)
            if edit_id
            else m.SavingsGoal(
                household_id=hid,
                created_by_user_id=uid,
                target_amount=Decimal("1"),
            )
        )
        if goal.is_archived:
            raise ValueError("استعد الهدف المؤرشف قبل تعديله.")
        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()
        if not 1 <= len(name) <= 120:
            raise ValueError("اسم الهدف مطلوب ولا يتجاوز 120 حرفًا.")
        if len(description) > 500:
            raise ValueError("وصف الهدف لا يتجاوز 500 حرف.")
        amount = LedgerState._money(
            self, str(data.get("target_amount", "")).strip(), True
        )
        raw_date = str(data.get("target_date", "")).strip()
        if raw_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
            raise ValueError("أدخل تاريخ الهدف بصيغة YYYY-MM-DD.")
        try:
            deadline = date.fromisoformat(raw_date) if raw_date else None
        except ValueError as e:
            raise ValueError("أدخل تاريخ هدف صالحًا بصيغة YYYY-MM-DD.") from e
        if (
            deadline
            and deadline < date.today()
            and (not edit_id or deadline != goal.target_date)
        ):
            raise ValueError("تاريخ الهدف الجديد لا يمكن أن يكون في الماضي.")
        goal.name, goal.description, goal.target_amount, goal.target_date = (
            name,
            description or None,
            amount,
            deadline,
        )
        db.add(goal)
        db.flush()
        return goal

    def _allocate(
        self,
        db,
        hid: UUID,
        uid: UUID,
        goal_id: str,
        kind: str,
        data: dict[str, Any],
    ):
        self._guard(db, hid, uid)
        goal = self._goal(db, hid, goal_id)
        if goal.is_archived:
            raise ValueError("الهدف مؤرشف. استعده قبل إضافة أو تحرير مبلغ.")
        if kind not in ("add", "release"):
            raise ValueError("نوع التخصيص غير صالح.")
        amount = LedgerState._money(
            self, str(data.get("amount", "")).strip(), True
        )
        note = str(data.get("note", "")).strip()
        if len(note) > 500:
            raise ValueError("الملاحظة لا تتجاوز 500 حرف.")
        funded = db.scalar(
            select(
                func.coalesce(func.sum(m.SavingsGoalAllocation.amount), 0)
            ).where(
                m.SavingsGoalAllocation.household_id == hid,
                m.SavingsGoalAllocation.goal_id == goal.id,
            )
        )
        if (kind == "release") & (amount > Decimal(str(funded or 0))):
            raise ValueError("المبلغ المحرّر يتجاوز المبلغ المخصص لهذا الهدف.")
        entry = m.SavingsGoalAllocation(
            household_id=hid,
            goal_id=goal.id,
            created_by_user_id=uid,
            amount=amount if kind == "add" else -amount,
            event_date=date.today(),
            note=note or None,
        )
        db.add(entry)
        db.flush()
        return entry

    def _archive(self, db, hid: UUID, uid: UUID, goal_id: str, archived: bool):
        self._guard(db, hid, uid)
        goal = self._goal(db, hid, goal_id)
        if goal.is_archived == archived:
            raise ValueError("حالة الهدف محدّثة بالفعل.")
        goal.is_archived = archived
        db.flush()
        return goal

    def _load(self, db, hid: UUID):
        goals = db.scalars(
            select(m.SavingsGoal)
            .where(m.SavingsGoal.household_id == hid)
            .order_by(m.SavingsGoal.created_at.desc(), m.SavingsGoal.id.desc())
        ).all()
        allocations = db.scalars(
            select(m.SavingsGoalAllocation)
            .where(m.SavingsGoalAllocation.household_id == hid)
            .order_by(
                m.SavingsGoalAllocation.event_date,
                m.SavingsGoalAllocation.created_at,
                m.SavingsGoalAllocation.id,
            )
        ).all()
        histories: dict[UUID, list[AllocationRow]] = {
            goal.id: [] for goal in goals
        }
        totals: dict[UUID, Decimal] = {goal.id: Decimal("0") for goal in goals}
        for entry in allocations:
            if entry.goal_id in totals:
                value = Decimal(str(entry.amount or 0))
                totals[entry.goal_id] += value
                histories[entry.goal_id].append(
                    {
                        "id": str(entry.id),
                        "kind": "add" if value > 0 else "release",
                        "amount": f"{abs(value):,.4f}",
                        "date": entry.event_date.isoformat(),
                        "note": entry.note or "",
                    }
                )
        active: list[GoalRow] = []
        archived: list[GoalRow] = []
        completed = 0
        for goal in goals:
            target = Decimal(str(goal.target_amount))
            funded = totals[goal.id]
            remaining = max(Decimal("0"), target - funded)
            percent = funded / target * 100
            finished = funded >= target
            row: GoalRow = {
                "id": str(goal.id),
                "name": goal.name,
                "description": goal.description or "",
                "amount": f"{funded:,.4f}",
                "target": f"{target:,.4f}",
                "remaining": f"{remaining:,.4f}",
                "date": goal.target_date.isoformat()
                if goal.target_date
                else "",
                "status": "مكتمل" if finished else "قيد الادخار",
                "percent": f"{percent:.1f}",
                "progress": float(min(Decimal("100"), percent)),
                "history": histories[goal.id],
            }
            if goal.is_archived:
                archived.append(row)
            else:
                active.append(row)
                completed += int(finished)
        self.goals, self.archived_goals = active, archived
        self.active_count, self.completed_count = len(active), completed

    @rx.event
    async def load(self):
        self.goals, self.archived_goals = [], []
        self.active_count = self.completed_count = 0
        self.editor = self.edit_id = ""
        self.error = self.message = ""
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def load_sync(sync_db):
                    _, member = auth._household(sync_db)
                    self._load(sync_db, member.household_id)

                await db.run_sync(load_sync)
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر تحميل الأهداف. حاول مجددًا."

    @rx.event
    def open_goal(self, goal_id: str = ""):
        self.error = self.message = ""
        self.edit_id = ""
        self.draft = {
            "name": "",
            "description": "",
            "target_amount": "",
            "target_date": "",
        }
        if goal_id:
            row = next((g for g in self.goals if g["id"] == goal_id), None)
            if row is None:
                self.error = "الهدف غير موجود أو غير متاح لهذه الأسرة."
                return
            self.edit_id = goal_id
            self.draft = {
                "name": row["name"],
                "description": row["description"],
                "target_amount": row["target_amount"],
                "target_date": row["date"],
            }
        self.editor = "goal"

    @rx.event
    def open_allocation(self, goal_id: str, kind: str):
        self.error = self.message = ""
        row = next((g for g in self.goals if g["id"] == goal_id), None)
        if row is None or kind not in ("add", "release"):
            self.error = "الهدف غير موجود أو غير متاح لهذه الأسرة."
            return
        self.edit_id, self.allocation_kind, self.allocation_name = (
            goal_id,
            kind,
            row["name"],
        )
        self.editor = "allocation"

    @rx.event
    def close_editor(self):
        self.editor = self.edit_id = ""
        self.error = ""

    @rx.event
    async def save_goal(self, data: dict[str, Any]):
        try:
            if self.editor != "goal":
                raise ValueError("افتح نموذج الهدف أولًا.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def save_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._save_goal(
                        sync_db,
                        member.household_id,
                        user.id,
                        data,
                        self.edit_id,
                    )
                    sync_db.flush()
                    self._load(sync_db, member.household_id)

                await db.run_sync(save_sync)
                await db.commit()
            self.editor = self.edit_id = self.error = ""
            self.message = "تم حفظ الهدف بنجاح."
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر حفظ الهدف. حاول مجددًا."

    @rx.event
    async def save_allocation(self, data: dict[str, Any]):
        try:
            if self.editor != "allocation":
                raise ValueError("افتح نموذج التخصيص أولًا.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def allocate_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._allocate(
                        sync_db,
                        member.household_id,
                        user.id,
                        self.edit_id,
                        self.allocation_kind,
                        data,
                    )
                    sync_db.flush()
                    self._load(sync_db, member.household_id)

                await db.run_sync(allocate_sync)
                await db.commit()
            self.editor = self.edit_id = self.error = ""
            self.message = (
                "تم تحديث المبلغ المخصص للهدف؛ لم يتغير رصيد أي حساب."
            )
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر تحديث التخصيص. حاول مجددًا."

    @rx.event
    async def set_archived(self, goal_id: str, archived: bool):
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def archive_sync(sync_db):
                    user, member = auth._household(sync_db)
                    self._archive(
                        sync_db, member.household_id, user.id, goal_id, archived
                    )
                    sync_db.flush()
                    self._load(sync_db, member.household_id)

                await db.run_sync(archive_sync)
                await db.commit()
            self.error = ""
            self.message = (
                "تمت أرشفة الهدف مع الحفاظ على سجله."
                if archived
                else "تمت استعادة الهدف وسجل تخصيصاته."
            )
        except PermissionError:
            logging.exception("Unexpected error")
            return rx.redirect("/login")
        except ValueError as e:
            self.error = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.error = "تعذر تحديث حالة الهدف. حاول مجددًا."
