import reflex as rx

from app.components.ui import BUTTON, SECONDARY, INPUT
from app.states.waitlist import WaitlistState as W, PROBLEMS


CARD = "rounded-3xl border border-[#e2ded2] bg-[#fffdf8] p-6 md:p-9"


def feature(icon: str, title: str, body: str) -> rx.Component:
    return rx.el.article(
        rx.el.div(
            rx.icon(icon, class_name="h-6 w-6"),
            class_name="mb-6 w-fit rounded-2xl bg-[#e8ecdf] p-3 text-[#62704b]",
        ),
        rx.el.h3(title, class_name="text-xl font-bold text-[#27394a]"),
        rx.el.p(body, class_name="mt-3 text-sm leading-8 text-[#697366]"),
        class_name=CARD,
    )


def problem_option(item: tuple[str, str]) -> rx.Component:
    return rx.el.button(
        rx.icon("check", class_name="h-4 w-4"),
        item[1],
        type="button",
        aria_pressed=W.selected_problems.contains(item[0]),
        on_click=lambda: W.toggle_problem(item[0]),
        class_name=rx.cond(
            W.selected_problems.contains(item[0]),
            "flex w-full items-center gap-3 rounded-xl border border-[#62704b] bg-[#edf0e5] p-4 text-right text-sm font-bold text-[#46593c] transition-colors",
            "flex w-full items-center gap-3 rounded-xl border border-[#e2ded2] bg-white p-4 text-right text-sm font-medium text-[#555f55] transition-colors hover:border-[#62704b]",
        ),
    )


def progress() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.span("01", class_name="font-mono text-xs"),
            " اهتمامك",
            class_name=rx.cond(
                W.stage == 1,
                "rounded-full bg-[#62704b] px-4 py-2 text-sm font-bold text-white",
                "rounded-full bg-[#e8ecdf] px-4 py-2 text-sm text-[#62704b]",
            ),
        ),
        rx.el.div(
            rx.el.span("02", class_name="font-mono text-xs"),
            " تحديات البيت",
            class_name=rx.cond(
                W.stage == 2,
                "rounded-full bg-[#62704b] px-4 py-2 text-sm font-bold text-white",
                "rounded-full bg-[#e8ecdf] px-4 py-2 text-sm text-[#62704b]",
            ),
        ),
        rx.el.div(
            rx.el.span("03", class_name="font-mono text-xs"),
            " اختيارك",
            class_name=rx.cond(
                W.stage >= 3,
                "rounded-full bg-[#62704b] px-4 py-2 text-sm font-bold text-white",
                "rounded-full bg-[#e8ecdf] px-4 py-2 text-sm text-[#62704b]",
            ),
        ),
        class_name="mb-9 flex flex-wrap gap-2",
    )


def contact_step() -> rx.Component:
    return rx.el.div(
        rx.el.h3(
            "ابدأ بخطوة صغيرة", class_name="text-2xl font-bold text-[#27394a]"
        ),
        rx.el.p(
            "اترك وسيلة تواصل واحدة لنخبرك عند الإطلاق. تسجيل اهتمامك يُحفظ الآن، ولا ينشئ حسابًا أو حجزًا مدفوعًا.",
            class_name="mt-3 text-sm leading-8 text-[#697366]",
        ),
        rx.el.form(
            rx.el.label(
                rx.el.span(
                    "بريد إلكتروني أو جوال دولي",
                    class_name="mb-2 block text-sm font-bold text-[#465344]",
                ),
                rx.el.input(
                    name="contact",
                    type="text",
                    required=True,
                    max_length=320,
                    placeholder="name@example.com أو +9665…",
                    class_name=INPUT,
                    dir="ltr",
                ),
                class_name="mt-7 block",
            ),
            rx.el.label(
                rx.el.input(
                    name="consent",
                    type="checkbox",
                    class_name="mt-1 h-4 w-4 shrink-0 accent-[#62704b]",
                ),
                rx.el.span(
                    "أوافق صراحةً على التواصل معي بشأن إطلاق Money Harmony عبر وسيلة التواصل التي أدخلتها.",
                    class_name="text-sm leading-7 text-[#465344]",
                ),
                class_name="mt-5 flex items-start gap-3",
            ),
            rx.el.button(
                "تابع إلى الخطوة الثانية",
                rx.icon("arrow-left", class_name="h-4 w-4"),
                type="submit",
                class_name="mt-7 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#62704b] px-5 py-3 text-sm font-bold text-white transition-colors hover:bg-[#4f5e3c] focus-visible:outline-2 focus-visible:outline-[#62704b] sm:w-auto",
            ),
            on_submit=W.register_interest,
        ),
        rx.el.p(
            "بعد تحديث الصفحة لا يمكن استعادة الخطوات غير المكتملة تلقائيًا. سيبقى تسجيل اهتمامك الأول محفوظًا، لكن لن نطلب منك إعادة إرسال بياناتك هنا.",
            class_name="mt-5 text-xs leading-6 text-[#858676]",
        ),
    )


def problems_step() -> rx.Component:
    return rx.el.div(
        rx.el.h3(
            "ما الذي يشغل بال بيتكم؟",
            class_name="text-2xl font-bold text-[#27394a]",
        ),
        rx.el.p(
            "اختر تحديًا واحدًا على الأقل؛ يمكنك اختيار أكثر من واحد.",
            class_name="mt-3 text-sm leading-7 text-[#697366]",
        ),
        rx.el.div(
            rx.foreach(PROBLEMS, problem_option),
            class_name="mt-6 grid gap-3 sm:grid-cols-2",
        ),
        rx.el.div(
            rx.el.h4(
                "هل تريد دعوة شريكك الآن؟",
                class_name="text-lg font-bold text-[#27394a]",
            ),
            rx.el.p(
                "افتح واتساب برسالة جاهزة ورابط إحالة إلى هذه الصفحة. أنت من يختار المستلم ويرسل الرسالة؛ نقرة المشاركة ليست دعوة مرسلة.",
                class_name="mt-2 text-sm leading-7 text-[#697366]",
            ),
            rx.el.div(
                rx.el.button(
                    rx.icon("send", class_name="h-4 w-4"),
                    "مشاركة عبر واتساب",
                    type="button",
                    on_click=[
                        rx.call_script(
                            f"window.open('https://api.whatsapp.com/send?text=' + encodeURIComponent('خلّينا نرتّب ميزانية بيتنا معًا في Money Harmony: ' + window.location.origin + '/?ref=' + encodeURIComponent({W.referral_code})), '_blank', 'noopener,noreferrer')"
                        ),
                        W.mark_invite_click,
                    ],
                    class_name=SECONDARY,
                ),
                rx.el.button(
                    "ليس الآن · تابع",
                    on_click=W.save_problems,
                    class_name=BUTTON,
                ),
                class_name="mt-5 flex flex-wrap gap-3",
            ),
            rx.el.p(
                "يمكنك مشاركة الرابط أو التخطي؛ سيُحفظ اختيار التحديات عند المتابعة.",
                class_name="mt-3 text-xs text-[#858676]",
            ),
            class_name="mt-8 rounded-2xl border border-[#e6dfcf] bg-[#faf8f1] p-5",
        ),
    )


def choice_step() -> rx.Component:
    return rx.el.div(
        rx.el.span(
            "قرارك لك، دون دفع الآن",
            class_name="text-sm font-bold text-[#62704b]",
        ),
        rx.el.h3(
            "عضوية المؤسسين: أول 500 أسرة فقط",
            class_name="mt-3 text-2xl font-bold leading-relaxed text-[#27394a]",
        ),
        rx.el.p(
            "السنة الأولى بـ 99 ريالاً بدل 228",
            class_name="mt-4 text-xl font-bold text-[#865f40]",
        ),
        rx.el.p(
            "لن نأخذ منك أي مبلغ الآن. سنراسلك عند الإطلاق لتأكيد الحجز.",
            class_name="mt-4 text-base leading-8 text-[#53634b]",
        ),
        rx.el.p(
            "اختيارك الآن يحجز مكانًا ضمن العدد المحدود، وليس عملية شراء. لا توجد وسيلة دفع مطلوبة.",
            class_name="mt-2 text-sm leading-7 text-[#697366]",
        ),
        rx.cond(
            W.full,
            rx.el.p(
                "اكتملت أماكن المؤسسين. النسخة المجانية ما زالت خيارًا متاحًا.",
                role="status",
                class_name="mt-5 rounded-xl bg-[#f6f0df] p-4 text-sm text-[#786036]",
            ),
        ),
        rx.el.div(
            rx.cond(
                W.full,
                rx.el.span(),
                rx.el.button(
                    "احجز مكاني",
                    on_click=lambda: W.choose_founder("reserved"),
                    class_name=BUTTON,
                ),
            ),
            rx.el.button(
                "لا، أفضّل النسخة المجانية",
                on_click=lambda: W.choose_founder("free"),
                class_name=SECONDARY,
            ),
            class_name="mt-7 flex flex-wrap gap-3",
        ),
    )


def finished_step() -> rx.Component:
    return rx.el.div(
        rx.icon("circle-check", class_name="h-10 w-10 text-[#62704b]"),
        rx.el.h3(
            rx.cond(
                W.completed_choice == "reserved",
                "حُفظ مكانك ضمن عضوية المؤسسين",
                "سُجّل اختيارك للنسخة المجانية",
            ),
            class_name="mt-5 text-2xl font-bold text-[#27394a]",
        ),
        rx.el.p(
            "شكرًا لاهتمامك. لن نحصّل أي مبلغ الآن. التواصل عند الإطلاق يتطلب تجهيز قناة مراسلة لاحقًا؛ لم نرسل إليك رسالة الآن.",
            class_name="mt-4 text-sm leading-8 text-[#697366]",
        ),
    )


def join_panel() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.span(
                "قائمة الإطلاق", class_name="text-sm font-bold text-[#62704b]"
            ),
            rx.el.h2(
                "كن جزءًا من بداية أكثر هدوءًا",
                class_name="mt-3 text-3xl font-bold leading-relaxed text-[#27394a] md:text-4xl",
            ),
            rx.el.p(
                "ثلاث خطوات قصيرة: اهتمامك، ما تحتاجه أسرتك، ثم اختيارك. لا نطلب بيانات بنكية ولا نفتح حسابًا باسمك.",
                class_name="mt-4 max-w-2xl text-base leading-9 text-[#697366]",
            ),
            class_name="mb-9",
        ),
        rx.el.div(
            progress(),
            rx.cond(
                W.error != "",
                rx.el.p(
                    W.error,
                    role="alert",
                    class_name="mb-6 rounded-xl border border-red-200 bg-red-100 p-4 text-sm text-red-700",
                ),
            ),
            rx.match(
                W.stage,
                (1, contact_step()),
                (2, problems_step()),
                (3, choice_step()),
                finished_step(),
            ),
            class_name=CARD,
        ),
        id="join",
        class_name="scroll-mt-8 py-16 md:py-24",
    )


def landing_content() -> rx.Component:
    return rx.el.div(
        rx.el.section(
            rx.el.div(
                rx.el.span(
                    "دفتر عربي لحياة البيت",
                    class_name="inline-flex w-fit rounded-full border border-[#dce0ce] bg-[#edf0e3] px-4 py-2 text-sm font-bold text-[#62704b]",
                ),
                rx.el.h1(
                    "رتّبوا أموال البيت،",
                    rx.el.br(),
                    rx.el.span(
                        "واتركوا مساحة للطمأنينة.", class_name="text-[#62704b]"
                    ),
                    class_name="mt-7 text-4xl font-bold leading-[1.45] tracking-tight text-[#27394a] md:text-6xl",
                ),
                rx.el.p(
                    "بين مصروف اليوم، ميزانية الشهر وخطط الغد، يستحق بيتكم دفترًا واضحًا يجمعكم على الصورة نفسها. ابدأوا يدويًا وبالخطوات التي تناسبكم.",
                    class_name="mt-6 max-w-xl text-lg leading-9 text-[#657063]",
                ),
                rx.el.div(
                    rx.el.a(
                        "انضم إلى قائمة الإطلاق",
                        rx.icon("arrow-left", class_name="h-4 w-4"),
                        href="#join",
                        class_name=BUTTON,
                    ),
                    rx.el.a(
                        "لديّ حساب بالفعل", href="/login", class_name=SECONDARY
                    ),
                    class_name="mt-8 flex flex-wrap gap-3",
                ),
                rx.el.p(
                    "لا ربط بنكي · لا رسوم اليوم · القرار بيدك",
                    class_name="mt-7 text-sm text-[#858676]",
                ),
            ),
            rx.el.div(
                rx.el.div(
                    rx.icon(
                        "notebook-pen", class_name="h-7 w-7 text-[#62704b]"
                    ),
                    rx.el.span(
                        "صفحة من دفتر البيت",
                        class_name="text-sm font-bold text-[#62704b]",
                    ),
                    class_name="flex items-center gap-3 border-b border-[#e3dfd3] pb-5",
                ),
                rx.el.p(
                    "من التفاصيل الصغيرة تتضح الصورة الكبيرة.",
                    class_name="py-10 text-3xl font-bold leading-relaxed text-[#27394a]",
                ),
                rx.el.div(
                    rx.el.span("01", class_name="font-mono text-[#b48861]"),
                    "دوّنوا الدخل والمصروف حسب الفئة",
                    class_name="flex gap-4 border-t border-[#e3dfd3] py-4 text-sm font-semibold text-[#53634b]",
                ),
                rx.el.div(
                    rx.el.span("02", class_name="font-mono text-[#b48861]"),
                    "راجعوا ميزانية الشهر معًا",
                    class_name="flex gap-4 border-t border-[#e3dfd3] py-4 text-sm font-semibold text-[#53634b]",
                ),
                rx.el.div(
                    rx.el.span("03", class_name="font-mono text-[#b48861]"),
                    "خططوا لهدف ادخار واضح",
                    class_name="flex gap-4 border-t border-[#e3dfd3] py-4 text-sm font-semibold text-[#53634b]",
                ),
                class_name="rounded-3xl border border-[#dedacd] bg-[#fffdf8] p-7 md:p-10",
            ),
            class_name="grid items-center gap-12 py-8 lg:grid-cols-2 lg:gap-20",
        ),
        rx.el.section(
            rx.el.span(
                "المشكلة ← طريقة أبسط",
                class_name="text-sm font-bold text-[#a57954]",
            ),
            rx.el.h2(
                "ليس المطلوب أن تتذكروا كل شيء",
                class_name="mt-3 text-3xl font-bold leading-relaxed text-[#27394a]",
            ),
            rx.el.p(
                "حين تتبعثر المعاملات بين الرسائل والذاكرة، يصعب معرفة أين ذهب الدخل أو كم بقي للخطة. دفتر واحد للأسرة يجعل المراجعة عادة بسيطة، لا نقاشًا مؤجلًا.",
                class_name="mt-4 max-w-3xl text-base leading-9 text-[#697366]",
            ),
            rx.el.div(
                feature(
                    "notebook-tabs",
                    "دفتر مشترك بالعربية",
                    "سجّلوا الدخل والمصروف يدويًا ضمن فئات واضحة، وراجعوا معاملات الأسرة في مكان واحد.",
                ),
                feature(
                    "chart-pie",
                    "ميزانية يمكن متابعتها",
                    "حدود شهرية لفئات المصروف، مع عرض ما أُنفق وما تبقّى داخل التطبيق.",
                ),
                feature(
                    "target",
                    "أهداف تستحق التدرّج",
                    "تابعوا أهداف الادخار وتخصيص مبالغ لها يدويًا، دون تحويلات مالية تلقائية.",
                ),
                feature(
                    "calendar-days",
                    "الأقساط في موعدها على الورق",
                    "جدول ديون وأقساط ودفعات يدوية يوضح المستحق والمتبقي دون إرسال تذكيرات تلقائية.",
                ),
                feature(
                    "chart-no-axes-combined",
                    "صورة أوضح بالتقارير",
                    "راجعوا الدخل والمصروف في فترة تختارونها لتفهموا عادات البيت.",
                ),
                feature(
                    "heart-handshake",
                    "الشريك في الصورة",
                    "دعوة قابلة للمشاركة يدويًا تتيح للشريك الانضمام إلى دفتر الأسرة بحسابه.",
                ),
                class_name="mt-9 grid gap-4 md:grid-cols-2 lg:grid-cols-3",
            ),
            class_name="py-16 md:py-24",
        ),
        join_panel(),
        rx.el.section(
            rx.el.span(
                "بوضوح من البداية",
                class_name="text-sm font-bold text-[#a57954]",
            ),
            rx.el.h2(
                "أسئلة تستحق إجابة صريحة",
                class_name="mt-3 text-3xl font-bold text-[#27394a]",
            ),
            rx.el.div(
                feature(
                    "landmark",
                    "هل يرتبط بحسابي البنكي؟",
                    "لا. إدخال المعاملات والدفعات يدوي، ولا يوجد ربط بالبنوك أو استيراد تلقائي.",
                ),
                feature(
                    "bell-off",
                    "هل تصل تنبيهات أو رسائل الآن؟",
                    "لا تُرسل تنبيهات تلقائية أو بريد أو رسائل SMS عند الانضمام للقائمة. التواصل عند الإطلاق يحتاج إعداد قناة مراسلة لاحقًا.",
                ),
                feature(
                    "credit-card",
                    "هل أدفع عند الحجز؟",
                    "لا. لا نطلب بيانات دفع ولا نحصّل رسومًا الآن. اختيار عضوية المؤسسين يحفظ مكانًا ضمن أول 500 أسرة إن كان متاحًا.",
                ),
                class_name="mt-8 grid gap-4 md:grid-cols-3",
            ),
            class_name="pb-16 md:pb-24",
        ),
    )
