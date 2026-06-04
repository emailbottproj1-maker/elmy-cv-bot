# Elmy CV Bot — Web Edition Deployment Guide

نسخة الويب من البوت — منصة تشتغل من المتصفح على الجوال (آيفون/آيباد/أندرويد) بدون أي تثبيت.

## نظرة سريعة على المعمارية
```
[الجوال]──► Vercel (واجهة + API + بكسل) ──► Supabase (قاعدة + تخزين CV)
                       ▲
                       │ كل دقيقة
              [cron-job.org يستدعي /api/tick]
```

ميزة المعمارية: الإرسال **يكمل 24/7 بدون أي جهاز مفتوح**. الـ cron الخارجي ينبض السيرفر، كل نبضة ترسل إيميل واحد بمراعاة **حد يومي وفاصل زمني عالميين** (مشتركان عبر كل الحملات لأن الإيميل واحد).

---

## النشر — خطوة بخطوة

### ١) Supabase
1. أنشئ مشروعًا جديدًا في [supabase.com](https://supabase.com) (مجاني).
2. **SQL Editor** → الصق محتوى `db/schema.sql` → Run.
3. **Storage** → أنشئ Bucket باسم `cvs` (Private).
4. **Project Settings → API** — احفظ:
   - `Project URL` → سيستخدم كـ `SUPABASE_URL`
   - `service_role` key → سيستخدم كـ `SUPABASE_SERVICE_KEY`

### ٢) Gemini AI (مجاني)
1. روح [aistudio.google.com](https://aistudio.google.com/) → **Get API key**.
2. احفظ المفتاح → سيستخدم كـ `GEMINI_API_KEY`.

### ٣) Vercel
1. `cd web` ثم `vercel` (أول مرة يربط المشروع) → `vercel --prod`.
2. **Project Settings → Environment Variables** أضف:

| المفتاح | القيمة |
|--------|--------|
| `SUPABASE_URL` | من الخطوة ١ |
| `SUPABASE_SERVICE_KEY` | service_role من الخطوة ١ |
| `SITE_PASSWORD` | كلمة المرور التي يدخل بها العميل للموقع |
| `GMAIL_ADDRESS` | إيميل الإرسال (Gmail) |
| `GMAIL_APP_PASSWORD` | App Password (16 حرف) |
| `GEMINI_API_KEY` | من Google AI Studio |
| `CRON_TOKEN` | نص سري عشوائي (يحمي endpoint الـtick) |
| `PIXEL_BASE_URL` | رابط مشروع Vercel نفسه (أو خدمة بكسل منفصلة) |
| `PIXEL_TOKEN` | (اختياري) — توكن خدمة الإحصائيات |

ثم أعد النشر: `vercel --prod`.

### ٤) cron-job.org (نبضة الإرسال)
1. سجّل في [cron-job.org](https://cron-job.org/) مجانًا.
2. **Cronjob جديد**:
   - URL: `https://<مشروعك>.vercel.app/api/tick?token=<CRON_TOKEN>`
   - Schedule: `every 1 minute`
   - Save.

### ٥) قاعدة الشركات الأولية
شغّل محليًا لاستيراد قاعدة العينة (30 شركة) أو القائمة الحقيقية:
```bash
python tools/seed_companies.py
```
(أو من الواجهة لاحقًا عبر استيراد Excel.)

---

## الاستخدام
1. افتح الموقع من الجوال → أدخل كلمة المرور.
2. **حملة جديدة** → ارفع CV العميل + اسمه + عنوان الإيميل + نص الرسالة.
3. اضغط **ابدأ** → الإرسال يبدأ على السيرفر.
4. ادخل لتفاصيل الحملة لمتابعة الإرسال والفتحات.

> **مهم:** الحد اليومي 50 إيميل والفواصل العشوائية **عالمية** بين كل الحملات (لأن المُرسِل إيميل واحد). تشغيل 3 حملات لا يعني 150/يوم — يبقى 50 إجمالًا موزّعة.

---

## نقاط نهاية الـ API

| المسار | الوظيفة |
|--------|--------|
| `POST /api/login` | دخول بكلمة المرور (يضع cookie) |
| `DELETE /api/login` | خروج |
| `GET  /api/me` | فحص حالة الدخول |
| `GET  /api/campaigns` | قائمة الحملات + العدّادات |
| `POST /api/campaigns` | إنشاء حملة (يملأ تلقائيًا send rows لكل الشركات) |
| `PATCH /api/campaigns?id=X` | تغيير حالة الحملة (active/paused/stopped) |
| `GET  /api/companies` | قائمة الشركات الماستر |
| `POST /api/companies` | إضافة شركات للماستر |
| `POST /api/upload` | رفع CV (PDF) إلى Storage |
| `GET  /api/stats?campaign_id=X` | عدّادات + قائمة الفتحات لحملة |
| `GET  /api/tick?token=...` | معالجة إيميل واحد (يُستدعى من cron) |
| `GET  /api/pixel?id=...` | بكسل التتبع |

---

## الاختبار قبل النشر
```bash
python tests/run_all.py
```
يجب أن تطلع: **14 passed, 0 failed**.

ولاختبار الواجهة محليًا بدون Supabase:
```bash
python tests/serve_local.py 8765
# افتح http://127.0.0.1:8765 ، كلمة المرور: test
```
