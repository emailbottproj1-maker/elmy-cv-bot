# Elmy CV Bot — منصة إرسال السير الذاتية للشركات

**النسخة الحالية:** منصة ويب متعددة الحملات (Vercel + Supabase + Gemini AI).

## كيف يعمل
محمد (تاجر الخدمة) يستقبل CV من كل عميل من عملائه، يفتح الموقع من جواله، **ينشئ حملة لذلك العميل** بـ CV + اسم + رسالة تغطية، ويضغط ابدأ. السيرفر يكمل الإرسال 24/7 (cron-job.org ينبض كل دقيقة) إلى **قائمة الشركات الكاملة** مع:
- ✉️ تخصيص باسم كل شركة (يدويًا أو بـ Gemini AI)
- 🌍 عربي/إنجليزي تلقائيًا حسب لغة الشركة
- 🛡️ حد يومي + فاصل عشوائي **عالميان** عبر كل الحملات (لأن المُرسِل إيميل واحد)
- 📊 بكسل تتبع + لوحة إحصائيات لكل حملة
- 🔁 استئناف تلقائي بعد أي توقف

## بنية المشروع
```
elmy-cv-bot/
├── bot/                   # المنطق المشترك (يُعاد استخدامه في كلا النسختين)
│   ├── excel_reader.py    # قراءة + تحقق Excel
│   ├── email_sender.py    # Gmail SMTP + MIME + مرفقات
│   ├── language_handler.py# AR/EN + استبدال placeholders
│   ├── rate_limiter.py    # فواصل عشوائية + حد يومي
│   ├── tracker.py         # بناء بكسل التتبع + جلب الإحصائيات
│   ├── ai_writer.py       # Gemini Flash + fallback للقالب
│   ├── supabase_db.py     # طبقة Supabase (REST + Storage)
│   ├── web_engine.py      # محرك tick (إيميل/طلب)
│   ├── database.py        # SQLite (نسخة الديسكتوب — مرجع)
│   ├── campaign.py        # Thread loop (نسخة الديسكتوب — مرجع)
│   ├── config.py          # حفظ الإعدادات (نسخة الديسكتوب — مرجع)
│   └── __init__.py
├── web/                   # نسخة الويب (تُنشر على Vercel)
│   ├── api/               # دوال Serverless: login, campaigns, upload, tick, stats, pixel
│   ├── public/            # الواجهة (HTML/CSS/JS) — RTL عربي + موبايل أولًا
│   ├── vercel.json
│   ├── requirements.txt
│   └── README.md          # دليل النشر الكامل
├── db/
│   └── schema.sql         # Supabase schema (companies, campaigns, sends, opens, config)
├── vercel-pixel/          # خدمة البكسل المستقلة (مرجع — استُخدمت كقاعدة)
├── tools/
│   ├── build_company_db.py    # توليد قاعدة شركات + Excel نموذجي
│   └── seed_companies.py      # رفع القائمة إلى Supabase
├── data/                  # قائمة الشركات + قوالب الرسائل
├── tests/                 # اختبارات (run_all.py)
├── docs/
│   └── PLAN.md            # الخطة الكاملة
├── client-data/           # بيانات العميل (gitignored)
├── gui/                   # واجهة الديسكتوب (Tkinter — مرجع)
├── main.py                # نقطة دخول الديسكتوب (مرجع)
├── build.bat              # بناء .exe (لنسخة الديسكتوب)
└── requirements.txt
```

## التشغيل والاختبار
```bash
# اختبار شامل (14/14 يجب أن تنجح)
python tests/run_all.py

# تجربة الواجهة محليًا بدون Supabase (مع stubs)
python tests/serve_local.py 8765
# افتح http://127.0.0.1:8765 — كلمة المرور: test
```

## النشر
شاهد `web/README.md` — دليل خطوة بخطوة لنشر Supabase + Vercel + cron-job.org + Gemini.

## التسعير المُتفق عليه
- **حزمة كاملة:** $80 دفعة واحدة (لا اشتراكات شهرية).
- **الاستضافة:** مجانية تمامًا (Vercel Hobby + Supabase Free + cron-job.org + Gemini Free).
- **التسليم:** 5–6 أيام عمل + دعم فني أسبوعين.
- **الكود ملك العميل بالكامل بعد التسليم.**
