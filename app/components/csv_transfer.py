import reflex as rx

from app.components.ui import BUTTON, SECONDARY, CARD, section_title, shell
from app.states.csv_transfer import CsvTransferState as T


UPLOAD_ID = "money_harmony_csv"


def entity_card(
    code: str, title: str, description: str, icon: str
) -> rx.Component:
    return rx.el.button(
        rx.el.div(
            rx.icon(icon, class_name="h-6 w-6 text-[#62704b]"),
            rx.el.span(title, class_name="text-lg font-bold text-[#27394a]"),
            class_name="flex items-center gap-3",
        ),
        rx.el.p(
            description,
            class_name="mt-2 text-right text-sm leading-7 text-[#7c8178]",
        ),
        on_click=lambda: T.choose(code),
        class_name=rx.cond(
            T.entity == code,
            "w-full rounded-2xl border-2 border-[#62704b] bg-[#edf0e3] p-5 text-right transition-colors",
            "w-full rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-5 text-right transition-colors hover:border-[#62704b]",
        ),
    )


def data_transfer_page() -> rx.Component:
    return shell(
        rx.el.div(
            section_title(
                "نقل بيانات الأسرة",
                "استورد وصدّر سجلات الدفتر بملفات CSV، خطوة بخطوة وبصلاحيات أسرتك الحالية.",
            ),
            rx.el.div(
                entity_card(
                    "accounts",
                    "الحسابات",
                    "الاسم والنوع والعملة والرصيد وتاريخ الافتتاح. ابدأ بها قبل المعاملات.",
                    "wallet",
                ),
                entity_card(
                    "categories",
                    "الفئات",
                    "فئات الدخل والمصروف بأسمائها ونوعها؛ استوردها قبل المعاملات والميزانيات.",
                    "tags",
                ),
                entity_card(
                    "transactions",
                    "المعاملات",
                    "تُربط بالحساب والعملة والفئة والنوع؛ تُستبعد المعاملات المحذوفة.",
                    "arrow-left-right",
                ),
                entity_card(
                    "budgets",
                    "الميزانيات",
                    "حدود الفئات الشهرية بحسب العملة، وتستلزم صلاحية تعديل الميزانيات.",
                    "chart-pie",
                ),
                entity_card(
                    "transfers",
                    "التحويلات",
                    "بين حسابين نشطين ظاهرين بالعملة نفسها؛ لا تدخل في الدخل والمصروف.",
                    "repeat-2",
                ),
                entity_card(
                    "bills",
                    "الفواتير",
                    "حالة paid أو unpaid، وتاريخ السداد والتذكير وحساب الفاتورة.",
                    "receipt-text",
                ),
                entity_card(
                    "debts",
                    "الديون",
                    "ديون الأسرة بعملتها الأساسية؛ الأقساط تُولّد تلقائيًا.",
                    "hand-coins",
                ),
                entity_card(
                    "debt_installments",
                    "جداول الأقساط",
                    "ملف مستقل للتحقق من تطابق الأقساط المولدة؛ لا ينشئ أقساطًا جديدة.",
                    "calendar-days",
                ),
                entity_card(
                    "debt_payments",
                    "دفعات الديون",
                    "دفعات فعلية أو ملغاة دون قيد مالي آلي؛ استوردها بعد الديون.",
                    "badge-check",
                ),
                class_name="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3",
            ),
            rx.el.div(
                rx.icon("info", class_name="h-5 w-5 shrink-0"),
                rx.el.p(
                    "استورد بالترتيب: الحسابات والفئات، ثم المعاملات والتحويلات والميزانيات والفواتير والديون، ثم تحقق من الأقساط، ثم استورد الدفعات. إذا كان الدين مؤرشفًا، أعد استيراد ملف الديون بعد الدفعات لاستعادة أرشفته بعد السداد الكامل. ملفات منفصلة بعناوين إنجليزية ثابتة وصف مثال يُحذف أو يُعدل؛ التاريخ YYYY-MM-DD، العملات ثلاثية، والمبالغ حتى 4 منازل. true/false للأرشفة والإلغاء؛ paid تتطلب paid_on وunpaid لا تقبله. source_id اختياري ويُحافظ على هوية السجلات عند نقلها؛ لا تعدّل معرفات الأسرة الأخرى. التصدير يقتصر على الأسرة والحسابات الظاهرة ولو أُغلقت تاريخيًا؛ إنشاء التحويل يتطلب حسابين نشطين. الأقساط والدفعات والفواتير لا تُنشئ قيود دفع؛ العملات لا تُجمع. الإيصالات ثنائية لا تدخل CSV؛ نزّلها منفردة من المعاملات. بدون معرف ثابت، العمليات اليدوية المتطابقة في التاريخ والبيانات تُعامل كمكررة.",
                    class_name="text-sm leading-7",
                ),
                class_name="mb-6 flex gap-3 rounded-xl border border-[#dce0ce] bg-[#edf0e3] p-4 text-[#62704b]",
            ),
            rx.cond(
                T.error != "",
                rx.el.p(
                    T.error,
                    role="alert",
                    class_name="mb-5 rounded-xl bg-red-100 p-4 text-sm text-red-700",
                ),
            ),
            rx.cond(
                T.message != "",
                rx.el.p(
                    T.message,
                    role="status",
                    class_name="mb-5 rounded-xl bg-[#e9eddf] p-4 text-sm text-[#62704b]",
                ),
            ),
            rx.el.div(
                rx.el.section(
                    rx.el.h2(
                        "١ · نزّل القالب أو بياناتك",
                        class_name="mb-2 text-xl font-bold text-[#27394a]",
                    ),
                    rx.el.p(
                        "ملفات UTF-8 مع BOM لتُفتح العربية في Excel. يُحمى النص من صيغ جداول البيانات عند التصدير.",
                        class_name="mb-5 text-sm leading-7 text-[#7c8178]",
                    ),
                    rx.el.div(
                        rx.el.button(
                            rx.icon("file-down", class_name="h-4 w-4"),
                            "تنزيل قالب مع مثال",
                            on_click=T.template,
                            class_name=SECONDARY,
                        ),
                        rx.el.button(
                            rx.icon("download", class_name="h-4 w-4"),
                            "تصدير بيانات الأسرة",
                            on_click=T.export_csv,
                            class_name=BUTTON,
                        ),
                        class_name="flex flex-wrap gap-3",
                    ),
                    class_name=CARD,
                ),
                rx.el.section(
                    rx.el.h2(
                        "٢ · ارفع ملفًا للمراجعة",
                        class_name="mb-2 text-xl font-bold text-[#27394a]",
                    ),
                    rx.el.p(
                        "ملف CSV واحد بحد 2 ميغابايت و2000 صف. تظهر الأخطاء بأرقام الصفوف؛ لا تُحفظ بيانات عند فشل أي صف.",
                        class_name="mb-4 text-sm leading-7 text-[#7c8178]",
                    ),
                    rx.upload.root(
                        rx.icon(
                            "upload",
                            class_name="mx-auto mb-2 h-6 w-6 text-[#62704b]",
                        ),
                        rx.el.p(
                            "اضغط لاختيار ملف CSV أو أسقطه هنا",
                            class_name="text-center text-sm font-semibold text-[#465344]",
                        ),
                        id=UPLOAD_ID,
                        multiple=False,
                        max_files=1,
                        accept={
                            "text/csv": [".csv"],
                            "application/vnd.ms-excel": [".csv"],
                        },
                        class_name="block cursor-pointer rounded-xl border border-dashed border-[#cbd3ba] bg-[#faf9f3] p-6 hover:bg-[#edf0e5]",
                    ),
                    rx.foreach(
                        rx.selected_files(UPLOAD_ID),
                        lambda filename: rx.el.p(
                            filename,
                            class_name="mt-2 break-all text-sm text-[#465344]",
                        ),
                    ),
                    rx.el.button(
                        "فحص الملف وعرض العينة",
                        on_click=T.upload_csv(
                            rx.upload_files(upload_id=UPLOAD_ID)
                        ),
                        class_name="mt-4 inline-flex items-center justify-center gap-2 rounded-xl bg-[#62704b] px-5 py-3 text-sm font-bold text-white hover:bg-[#4f5e3c]",
                    ),
                    class_name=CARD,
                ),
                class_name="grid gap-5 lg:grid-cols-2",
            ),
            rx.cond(
                T.row_count > 0,
                rx.el.section(
                    rx.el.h2(
                        f"٣ · معاينة {T.row_count} صف",
                        class_name="mb-3 text-xl font-bold text-[#27394a]",
                    ),
                    rx.el.p(
                        "أول خمسة صفوف فقط. يُعاد التحقق من الملف والصلاحيات والروابط عند التأكيد داخل معاملة واحدة؛ الصفوف المكررة تُتخطّى.",
                        class_name="mb-4 text-sm leading-7 text-[#7c8178]",
                    ),
                    rx.el.ul(
                        rx.foreach(
                            T.preview,
                            lambda line: rx.el.li(
                                line,
                                class_name="break-all border-b border-[#e2ded2] py-2 text-sm text-[#465344]",
                            ),
                        ),
                        class_name="mb-5 rounded-xl bg-[#f6f4ec] px-4",
                    ),
                    rx.el.div(
                        rx.el.button(
                            "تأكيد الاستيراد",
                            on_click=T.confirm,
                            disabled=T.busy,
                            class_name=BUTTON,
                        ),
                        rx.el.button(
                            "إلغاء",
                            on_click=[
                                T.cancel_preview,
                                rx.clear_selected_files(UPLOAD_ID),
                            ],
                            class_name=SECONDARY,
                        ),
                        class_name="flex flex-wrap gap-3",
                    ),
                    class_name="mt-5 rounded-2xl border border-[#e2ded2] bg-[#fffdf8] p-5 md:p-7",
                ),
            ),
            rx.el.a(
                rx.icon("arrow-right", class_name="h-4 w-4"),
                "العودة إلى الإعدادات",
                href="/settings",
                class_name="mt-7 inline-flex items-center gap-2 text-sm font-bold text-[#62704b] hover:underline",
            ),
            class_name="w-full",
        )
    )
