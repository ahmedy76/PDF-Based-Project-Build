import reflex as rx

from app.states.receipts import ReceiptState as R


UPLOAD_ID = "transaction_receipt"
BUTTON = "inline-flex items-center justify-center gap-2 rounded-xl bg-[#62704b] px-4 py-2.5 text-sm font-bold text-white hover:bg-[#4f5e3c] disabled:opacity-50"
SECONDARY = "inline-flex items-center justify-center gap-2 rounded-xl border border-[#ddd9cd] bg-[#fffdf8] px-4 py-2.5 text-sm font-semibold text-[#27394a] hover:bg-[#eeece2] disabled:opacity-50"


def receipt_modal() -> rx.Component:
    return rx.cond(
        R.transaction_id != "",
        rx.el.div(
            rx.el.section(
                rx.el.div(
                    rx.el.div(
                        rx.el.h2(
                            "إيصال المعاملة",
                            class_name="text-xl font-bold text-[#27394a]",
                        ),
                        rx.el.p(
                            "مرفق خاص بأسرتك · لا يغيّر رصيد المعاملة أو سجل تعديلاتها",
                            class_name="mt-1 text-sm leading-6 text-[#7c8178]",
                        ),
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-5 w-5"),
                        on_click=R.close_receipt,
                        aria_label="إغلاق الإيصال",
                        class_name=SECONDARY,
                    ),
                    class_name="mb-5 flex items-start justify-between gap-3",
                ),
                rx.cond(
                    R.loading,
                    rx.el.p(
                        "جارٍ معالجة الإيصال…",
                        role="status",
                        class_name="mb-4 rounded-xl bg-[#f6f4ec] p-3 text-sm text-[#62704b]",
                    ),
                ),
                rx.cond(
                    R.error != "",
                    rx.el.p(
                        R.error,
                        role="alert",
                        class_name="mb-4 rounded-xl bg-red-100 p-3 text-sm text-red-700",
                    ),
                ),
                rx.cond(
                    R.message != "",
                    rx.el.p(
                        R.message,
                        role="status",
                        class_name="mb-4 rounded-xl bg-green-100 p-3 text-sm text-green-700",
                    ),
                ),
                rx.cond(
                    R.filename != "",
                    rx.el.div(
                        rx.el.div(
                            rx.icon(
                                "file-check-2",
                                class_name="h-5 w-5 shrink-0 text-[#62704b]",
                            ),
                            rx.el.div(
                                rx.el.p(
                                    R.filename,
                                    class_name="break-all font-semibold text-[#27394a]",
                                ),
                                rx.el.p(
                                    f"{R.size_bytes} بايت · {R.mime_type}",
                                    class_name="mt-1 text-xs text-[#7c8178]",
                                ),
                                class_name="min-w-0",
                            ),
                            class_name="flex items-start gap-3",
                        ),
                        rx.el.div(
                            rx.cond(
                                R.mime_type != "application/pdf",
                                rx.el.button(
                                    rx.icon("eye", class_name="h-4 w-4"),
                                    "معاينة الصورة",
                                    on_click=R.preview_receipt,
                                    disabled=R.loading,
                                    class_name=SECONDARY,
                                ),
                            ),
                            rx.el.button(
                                rx.icon("download", class_name="h-4 w-4"),
                                "تنزيل",
                                on_click=R.download_receipt,
                                disabled=R.loading,
                                class_name=SECONDARY,
                            ),
                            rx.cond(
                                R.can_manage,
                                rx.el.button(
                                    rx.icon("trash-2", class_name="h-4 w-4"),
                                    "حذف الإيصال",
                                    on_click=R.delete_receipt,
                                    disabled=R.loading,
                                    class_name="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-[#fffdf8] px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50",
                                ),
                            ),
                            class_name="mt-4 flex flex-wrap gap-2",
                        ),
                        rx.cond(
                            R.preview_uri != "",
                            rx.el.img(
                                src=R.preview_uri,
                                alt="معاينة الإيصال",
                                class_name="mt-4 max-h-80 w-full rounded-xl border border-[#e2ded2] bg-white object-contain",
                            ),
                        ),
                        class_name="rounded-xl border border-[#e2ded2] bg-[#faf9f3] p-4",
                    ),
                    rx.cond(
                        ~R.loading & (R.error == ""),
                        rx.el.p(
                            "لا يوجد إيصال مرفق بهذه المعاملة.",
                            class_name="rounded-xl border border-dashed border-[#ddd9cd] bg-[#faf9f3] p-6 text-center text-sm text-[#7c8178]",
                        ),
                    ),
                ),
                rx.cond(
                    R.can_manage,
                    rx.el.div(
                        rx.el.p(
                            rx.cond(
                                R.filename != "",
                                "استبدال الإيصال",
                                "إرفاق إيصال",
                            ),
                            class_name="mb-3 font-bold text-[#27394a]",
                        ),
                        rx.upload.root(
                            rx.icon(
                                "upload",
                                class_name="mx-auto mb-2 h-6 w-6 text-[#62704b]",
                            ),
                            rx.el.p(
                                "اضغط لاختيار ملف أو أسقطه هنا",
                                class_name="text-sm font-semibold text-[#465344]",
                            ),
                            id=UPLOAD_ID,
                            multiple=False,
                            max_files=1,
                            accept={
                                "image/png": [".png"],
                                "image/jpeg": [".jpg", ".jpeg"],
                                "image/webp": [".webp"],
                                "application/pdf": [".pdf"],
                            },
                            class_name="block cursor-pointer rounded-xl border border-dashed border-[#cbd3ba] bg-[#faf9f3] p-5 text-center hover:bg-[#edf0e5]",
                        ),
                        rx.foreach(
                            rx.selected_files(UPLOAD_ID),
                            lambda name: rx.el.p(
                                name,
                                class_name="mt-2 break-all text-sm text-[#465344]",
                            ),
                        ),
                        rx.el.p(
                            "PNG، JPG، WEBP أو PDF · ملف واحد بحد أقصى 5 ميغابايت. ملفات PDF متاحة للتنزيل فقط.",
                            class_name="my-3 text-xs leading-6 text-[#7c8178]",
                        ),
                        rx.el.button(
                            rx.icon("upload", class_name="h-4 w-4"),
                            rx.cond(
                                R.filename != "",
                                "حفظ الإيصال البديل",
                                "رفع الإيصال",
                            ),
                            on_click=R.upload_receipt(
                                rx.upload_files(upload_id=UPLOAD_ID)
                            ),
                            disabled=R.loading | (R.household_id == ""),
                            class_name=BUTTON,
                        ),
                        class_name="mt-5 border-t border-[#e2ded2] pt-5",
                    ),
                ),
                role="dialog",
                aria_modal=True,
                aria_label="إيصال المعاملة",
                class_name="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-2xl bg-[#fffdf8] p-5 md:p-7",
            ),
            class_name="fixed inset-0 z-50 flex items-center justify-center bg-[#243747]/40 p-4",
        ),
    )
