import reflex as rx

# Supplemental static labels: the editor does not permit JSON file edits.
LABELS: dict[str, tuple[str, str]] = {
    "nav.family_planning": ("تخطيط الأسرة", "Family planning"),
    "planning.title": ("تخطيط الأسرة", "Family planning"),
    "planning.subtitle": (
        "مهام مشتركة وتقاسم اختياري موثق للفواتير لكل عملة على حدة.",
        "Shared tasks and optional documented bill splits, separately per currency.",
    ),
    "planning.tasks": ("مهام الأسرة", "Household tasks"),
    "planning.new_task": ("مهمة جديدة", "New task"),
    "planning.task_form": ("تفاصيل المهمة", "Task details"),
    "planning.task_title": ("عنوان المهمة", "Task title"),
    "planning.details": (
        "التفاصيل (اختياري، حتى 4000 حرف)",
        "Details (optional, up to 4000 characters)",
    ),
    "planning.due_date": ("تاريخ الاستحقاق (اختياري)", "Due date (optional)"),
    "planning.currency": (
        "العملة · رمز ISO من ثلاثة أحرف",
        "Currency · three-letter ISO code",
    ),
    "planning.account": (
        "حساب ظاهر مرتبط (اختياري، بنفس العملة)",
        "Linked visible account (optional, same currency)",
    ),
    "planning.assignee": ("المسؤول (اختياري)", "Assignee (optional)"),
    "planning.none": ("بدون", "None"),
    "planning.all": ("الكل", "All"),
    "planning.status": ("الحالة", "Status"),
    "planning.pending": ("قيد التنفيذ", "Pending"),
    "planning.complete": ("مكتملة", "Complete"),
    "planning.complete_action": ("إكمال المهمة", "Complete task"),
    "planning.reopen": ("إعادة فتح", "Reopen"),
    "planning.filter": ("تطبيق المرشحات", "Apply filters"),
    "planning.refresh": ("تحديث التخطيط", "Refresh planning"),
    "planning.empty_tasks": (
        "لا توجد مهام ظاهرة تطابق المرشحات.",
        "No visible tasks match these filters.",
    ),
    "planning.empty_bills": (
        "لا توجد فواتير مرتبطة بحسابات ظاهرة.",
        "No bills linked to visible accounts.",
    ),
    "planning.delete_confirm": (
        "هل تريد حذف المهمة نهائيًا؟",
        "Permanently delete this task?",
    ),
    "planning.splits": ("تقاسم الفواتير الاختياري", "Optional bill splitting"),
    "planning.no_posting": (
        "تخطيط فقط: لا دفع تلقائي ولا تغيير في الأرصدة أو المعاملات أو حالة سداد الفاتورة. حدّث للاطلاع على التغييرات؛ لا مزامنة لحظية ولا جمع بين العملات.",
        "Planning only: no automatic payments or changes to balances, transactions or bill payment status. Refresh to see changes; no live synchronization or cross-currency totals.",
    ),
    "planning.equal": ("بالمناصفة", "Equal split"),
    "planning.income": ("حسب الدخل الموثق", "Documented income proportions"),
    "planning.mode": ("قاعدة التقاسم", "Split rule"),
    "planning.participant_1": ("المشارك الأول", "First participant"),
    "planning.participant_2": ("المشارك الثاني", "Second participant"),
    "planning.income_1": (
        "الدخل الموثق للأول بعملة الفاتورة",
        "First documented income in bill currency",
    ),
    "planning.income_2": (
        "الدخل الموثق للثاني بعملة الفاتورة",
        "Second documented income in bill currency",
    ),
    "planning.income_help": (
        "في وضع الدخل أدخل دخلين موجبين بنفس العملة ولنفس الفترة المتفق عليها (حتى 4 خانات عشرية). تُحفظ لقطة الدخل والنسب والحصص ولا تُستخرج من الدفتر. في المناصفة اترك الدخل فارغًا. تُقرب الحصص إلى 4 خانات وتُضاف البقية للحصة الثانية لضمان مجموع مطابق.",
        "For income mode, enter two positive incomes in the same currency and agreed period (up to 4 decimals). Income, percentage and share snapshots are saved, not derived from the ledger. Leave incomes blank for equal splits. Shares are rounded to 4 decimals; the second receives the remainder for an exact total.",
    ),
    "planning.confirm": (
        "أؤكد أن التقاسم اختياري لمشاركين نشطين، وأن الدخل الموثق بنفس العملة والفترة ومصرح بالإفصاح عنه للمشاركين المخولين.",
        "I confirm optional planning for two active participants and that documented incomes use the same currency and period and are authorized for disclosure to permitted participants.",
    ),
    "planning.save_split": (
        "حفظ / استبدال قاعدة التقاسم",
        "Save / replace split rule",
    ),
    "planning.revoke": (
        "إلغاء التقاسم والإفصاح المحفوظ",
        "Revoke split and saved disclosure",
    ),
    "planning.snapshot": (
        "لقطة موثقة، وليست دفعة",
        "Documented snapshot, not a payment",
    ),
    "planning.income_label": ("الدخل المعلن", "Declared income"),
    "planning.percentage": ("النسبة", "Percentage"),
    "planning.share": ("الحصة", "Share"),
    "planning.stale": (
        "تغيرت الفاتورة منذ حفظ اللقطة؛ الحصص ليست توزيعًا للمبلغ الجديد. على المالك إعادة حفظ القاعدة أو إلغاؤها.",
        "The bill changed after this snapshot; shares do not distribute the new amount. The owner must resave or revoke the rule.",
    ),
    "planning.no_disclosure": (
        "لا توجد تفاصيل تقاسم متاحة لك. يلزم أن تكون مشاركًا مخولًا بالإفصاح والحساب ظاهرًا.",
        "No split details available. You must be a permitted participant with visible account access.",
    ),
    "planning.disclosure": (
        "الاطلاع على الالتزامات والدخل المعلن للتقاسم",
        "View commitments and declared split incomes",
    ),
    "planning.disclosure_help": (
        "معطل افتراضيًا. المالك وحده يسمح أو يمنع الإفصاح؛ السماح يكشف للمشارك حصص التقاسم والدخل المعلن المحفوظ للمشاركين في فواتير الحسابات الظاهرة فقط. لا يمنح إدارة التقاسم أو حسابات محجوبة. يحتفظ المالك بالاطلاع دائمًا.",
        "Off by default. Only the owner enables or revokes disclosure. It reveals saved shares and participant income for bills you participate in, on visible accounts only. It grants neither split management nor hidden account access. The owner always retains access.",
    ),
    "planning.allowed": ("مسموح ✓", "Allowed ✓"),
    "planning.denied": ("غير مسموح", "Not allowed"),
    "planning.saved": (
        "حُفظ التخطيط دون تغيير السجل المالي.",
        "Planning saved without changing financial records.",
    ),
    "planning.failed": (
        "تعذر تنفيذ العملية. أعد التحديث ثم حاول مجددًا.",
        "Operation failed. Refresh and try again.",
    ),
    "planning.unavailable": (
        "البيانات غير متاحة أو تغيرت صلاحياتك. حدّث أو سجل الدخول مجددًا.",
        "Data unavailable or permissions changed. Refresh or sign in again.",
    ),
    "planning.forbidden": (
        "التعديل والحذف للمالك أو المنشئ؛ يمكن للمسؤول تحديث الحالة فقط.",
        "Only owner or creator can edit/delete; assignee can update status only.",
    ),
    "planning.owner_only": (
        "مالك الأسرة وحده يدير قواعد التقاسم.",
        "Only the owner manages split rules.",
    ),
    "planning.invalid_task": (
        "أدخل عنوانًا حتى 200 حرف وتفاصيل حتى 4000 حرف وعملة من ثلاثة أحرف وحالة صالحة.",
        "Enter a title up to 200 characters, details up to 4000, a three-letter currency and valid status.",
    ),
    "planning.invalid_date": ("أدخل تاريخًا صالحًا.", "Enter a valid date."),
    "planning.account_currency": (
        "اختر حسابًا متاحًا في الأسرة بعملة مطابقة؛ لا تحويل بين العملات.",
        "Choose an available household account with matching currency; no conversion.",
    ),
    "planning.invalid_participants": (
        "اختر مشاركين مختلفين نشطين من نفس الأسرة.",
        "Choose two distinct active household participants.",
    ),
    "planning.invalid_income": (
        "الدخل رقم موجب محدود أقل من 1000000000000000 وحتى أربع خانات عشرية.",
        "Income must be finite, positive, below 1000000000000000 and at most four decimals.",
    ),
    "planning.invalid_split": (
        "قاعدة التقاسم أو مبلغ الفاتورة غير صالح.",
        "Invalid split rule or bill amount.",
    ),
    "planning.consent_required": (
        "على المالك تمكين إذن الإفصاح لكل مشارك غير مالك قبل حفظ القاعدة.",
        "Owner must enable disclosure for each non-owner participant before saving.",
    ),
    "planning.confirm_required": (
        "يلزم تأكيد الإفصاح والتقاسم الاختياري صراحة.",
        "Explicit optional splitting and disclosure confirmation is required.",
    ),
    "planning.limit": (
        "تُعرض أول 200 مهمة وفاتورة بحسب الاستحقاق؛ استخدم مرشحات المهام لتضييق النتائج.",
        "First 200 tasks and bills shown by due date; narrow tasks using filters.",
    ),
}
