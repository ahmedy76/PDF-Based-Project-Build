import reflex as rx

import logging
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import models as m
from app.states.auth import AuthState


class CategoryState(rx.State):
    income_categories: list[dict[str, str]] = []
    expense_categories: list[dict[str, str]] = []
    message: str = ""
    editing_id: str = ""
    editing_name: str = ""
    editing_kind: str = ""
    archive_id: str = ""
    archive_name: str = ""

    @staticmethod
    def _validate_name(value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("أدخل اسم الفئة.")
        if len(name) > 100:
            raise ValueError("اسم الفئة يجب ألا يتجاوز 100 حرف.")
        return name

    def _list(self, db, household_id):
        categories = db.scalars(
            select(m.Category)
            .where(
                m.Category.household_id == household_id,
                m.Category.is_archived.is_(False),
            )
            .order_by(m.Category.name)
        ).all()
        self.income_categories = [
            {"id": str(c.id), "name": c.name, "kind": c.kind}
            for c in categories
            if c.kind == "income"
        ]
        self.expense_categories = [
            {"id": str(c.id), "name": c.name, "kind": c.kind}
            for c in categories
            if c.kind == "expense"
        ]

    def _category(self, db, household_id, record_id: str):
        try:
            category_id = UUID(record_id)
        except (ValueError, TypeError):
            raise ValueError(
                "الفئة غير موجودة أو غير متاحة لهذه الأسرة."
            ) from None
        category = db.scalar(
            select(m.Category)
            .where(
                m.Category.household_id == household_id,
                m.Category.id == category_id,
            )
            .with_for_update()
        )
        if category is None or category.is_archived:
            raise ValueError("الفئة غير موجودة أو مؤرشفة.")
        return category

    def _unique(self, db, household_id, kind: str, name: str, excluded_id=None):
        query = select(m.Category.id).where(
            m.Category.household_id == household_id,
            m.Category.kind == kind,
            func.lower(m.Category.name) == name.lower(),
        )
        if excluded_id is not None:
            query = query.where(m.Category.id != excluded_id)
        if db.scalar(query.limit(1)) is not None:
            raise ValueError(
                "اسم الفئة مستخدم بالفعل لهذا النوع، حتى إن كانت الفئة مؤرشفة."
            )

    @rx.event
    async def load(self):
        self.message = ""
        self.editing_id = ""
        self.archive_id = ""
        try:
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def load_sync(sync_db):
                    _, member = auth._household(sync_db)
                    self._list(sync_db, member.household_id)

                await db.run_sync(load_sync)
        except PermissionError:
            logging.exception("Unexpected error")
            self.income_categories = []
            self.expense_categories = []
            self.message = ""
            return rx.redirect("/login")
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر تحميل الفئات. أعد المحاولة."

    @rx.event
    def open_edit(self, record_id: str):
        self.message = ""
        rows = self.income_categories + self.expense_categories
        row = next((item for item in rows if item["id"] == record_id), None)
        if row is not None:
            self.editing_id = row["id"]
            self.editing_name = row["name"]
            self.editing_kind = row["kind"]

    @rx.event
    def close_edit(self):
        self.editing_id = ""
        self.message = ""

    @rx.event
    def ask_archive(self, record_id: str):
        self.message = ""
        rows = self.income_categories + self.expense_categories
        row = next((item for item in rows if item["id"] == record_id), None)
        if row is not None:
            self.archive_id = row["id"]
            self.archive_name = row["name"]

    @rx.event
    def cancel_archive(self):
        self.archive_id = ""
        self.message = ""

    @rx.event
    async def add(self, data: dict[str, Any]):
        try:
            name = self._validate_name(str(data.get("name", "")))
            kind = str(data.get("kind", ""))
            if kind not in ("income", "expense"):
                raise ValueError("اختر نوع الفئة: دخل أو مصروف.")
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def add_sync(sync_db):
                    _, member = auth._household(sync_db)
                    hid = member.household_id
                    sync_db.scalar(
                        select(m.Household)
                        .where(m.Household.id == hid)
                        .with_for_update()
                    )
                    self._unique(sync_db, hid, kind, name)
                    sync_db.add(
                        m.Category(household_id=hid, name=name, kind=kind)
                    )
                    sync_db.commit()
                    self._list(sync_db, hid)

                await db.run_sync(add_sync)
            self.message = "تمت إضافة الفئة بنجاح."
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except IntegrityError:
            logging.exception("Unexpected error")
            self.message = (
                "اسم الفئة مستخدم بالفعل لهذا النوع، حتى إن كانت الفئة مؤرشفة."
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذرت إضافة الفئة. أعد المحاولة."

    @rx.event
    async def rename(self, data: dict[str, Any]):
        try:
            name = self._validate_name(str(data.get("name", "")))
            record_id = self.editing_id
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def rename_sync(sync_db):
                    _, member = auth._household(sync_db)
                    hid = member.household_id
                    sync_db.scalar(
                        select(m.Household)
                        .where(m.Household.id == hid)
                        .with_for_update()
                    )
                    category = self._category(sync_db, hid, record_id)
                    self._unique(sync_db, hid, category.kind, name, category.id)
                    category.name = name
                    sync_db.commit()
                    self._list(sync_db, hid)

                await db.run_sync(rename_sync)
            self.editing_id = ""
            self.message = "تم تحديث اسم الفئة. بقي نوعها كما هو لحماية المعاملات والميزانيات."
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except IntegrityError:
            logging.exception("Unexpected error")
            self.message = (
                "اسم الفئة مستخدم بالفعل لهذا النوع، حتى إن كانت الفئة مؤرشفة."
            )
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذر تحديث الفئة. أعد المحاولة."

    @rx.event
    async def confirm_archive(self):
        try:
            record_id = self.archive_id
            auth = await self.get_state(AuthState)
            async with rx.asession() as db:

                def archive_sync(sync_db):
                    _, member = auth._household(sync_db)
                    hid = member.household_id
                    sync_db.scalar(
                        select(m.Household)
                        .where(m.Household.id == hid)
                        .with_for_update()
                    )
                    category = self._category(sync_db, hid, record_id)
                    today = date.today()
                    ongoing_budget = sync_db.scalar(
                        select(m.MonthlyCategoryBudget.id)
                        .where(
                            m.MonthlyCategoryBudget.household_id == hid,
                            m.MonthlyCategoryBudget.category_id == category.id,
                            (m.MonthlyCategoryBudget.year > today.year)
                            | (
                                (m.MonthlyCategoryBudget.year == today.year)
                                & (m.MonthlyCategoryBudget.month >= today.month)
                            ),
                        )
                        .limit(1)
                    )
                    if ongoing_budget is not None:
                        raise ValueError(
                            "لا يمكن أرشفة فئة مرتبطة بميزانية للشهر الجاري أو لشهر قادم. أزل هذه الميزانيات أولًا."
                        )
                    category.is_archived = True
                    sync_db.commit()
                    self._list(sync_db, hid)

                await db.run_sync(archive_sync)
            self.archive_id = ""
            self.message = (
                "تمت أرشفة الفئة. ستبقى ظاهرة في المعاملات والميزانيات السابقة."
            )
        except PermissionError:
            logging.exception("Unexpected error")
            self.message = ""
            return rx.redirect("/login")
        except ValueError as e:
            self.message = str(e)
        except Exception as e:
            logging.exception(f"Error: {e}")
            self.message = "تعذرت أرشفة الفئة. أعد المحاولة."
