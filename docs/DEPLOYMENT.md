# Deployment Runbook — Elmy CV Bot (Web)

دليل النشر الفعلي خطوة بخطوة. اتبع الترتيب ولا تخطّ أي خطوة.

> **قبل البدء:** كل الخدمات في هذا الدليل مجانية. التكلفة الوحيدة المحتملة هي **دومين خاص** (~$12/سنة، اختياري).

---

## 0. Prerequisites — ما تحتاجه على جهازك

```bash
# Node.js (لـ Vercel CLI)
node --version    # تأكد إنه مثبت

# Vercel CLI
npm install -g vercel

# Python 3.10+ (مثبت أصلاً)
python --version
```

---

## 1. Supabase — قاعدة البيانات + التخزين

### 1.1 إنشاء المشروع
1. روح [supabase.com](https://supabase.com) → **New Project**
2. اختر منطقة قريبة (Frankfurt للشرق الأوسط أسرع)
3. **انسخ بعد الإنشاء:**
   - Project URL → `SUPABASE_URL`
   - Service Role Key (من **Settings → API → secret**) → `SUPABASE_SERVICE_KEY`

### 1.2 تنفيذ الـ Schema
- افتح **SQL Editor**
- الصق محتوى `db/schema.sql`
- اضغط **Run**
- يجب أن ترى الجداول: `companies`, `campaigns`, `campaign_sends`, `email_opens`, `app_config`

### 1.3 Storage bucket للـ CV
- **Storage** → **New bucket**
- Name: `cvs`
- Public: **OFF** (private — لن نشاركه)
- Save

### 1.4 (اختياري) استيراد قائمة الشركات
لو الملف عند العميل جاهز:
```bash
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_KEY=eyJ...
python tools/preview_import.py path/to/companies.xlsx
python tools/import_companies.py path/to/companies.xlsx
```

---

## 2. Gemini AI — مفتاح مجاني

1. روح [aistudio.google.com](https://aistudio.google.com/)
2. **Get API key** → Create
3. انسخ المفتاح → `GEMINI_API_KEY`

---

## 3. Vercel — الواجهة + API

### 3.1 أول نشر
```bash
cd web
vercel              # يربط المشروع — اختر "Yes" للإعدادات الافتراضية
```

### 3.2 إعداد Environment Variables
من **Vercel Dashboard → Project → Settings → Environment Variables**:

| المفتاح | القيمة | البيئات |
|--------|--------|---------|
| `SUPABASE_URL` | من الخطوة 1.1 | Production, Preview, Development |
| `SUPABASE_SERVICE_KEY` | service_role من الخطوة 1.1 | Production, Preview |
| `SITE_PASSWORD` | `Mm123456@@` (أو اللي يختاره) | Production, Preview |
| `GMAIL_ADDRESS` | `mddx90@gmail.com` | Production, Preview |
| `GMAIL_APP_PASSWORD` | `fzta jjko asva jetz` (المسافات تُحذف تلقائياً) | Production, Preview |
| `GEMINI_API_KEY` | من الخطوة 2 | Production, Preview |
| `CRON_TOKEN` | نص سري عشوائي (مثل `openssl rand -hex 24`) | Production, Preview |
| `PIXEL_BASE_URL` | رابط مشروع Vercel نفسه (بعد النشر) | Production, Preview |

### 3.3 إعادة النشر بعد الـ env vars
```bash
vercel --prod
```

### 3.4 (اختياري) ربط دومين خاص
- **Settings → Domains** → Add → اتبع تعليمات DNS
- بعد التفعيل، حدّث `PIXEL_BASE_URL` ليُشير للدومين الجديد

---

## 4. cron-job.org — نبض الإرسال

1. سجّل في [cron-job.org](https://cron-job.org/) (مجاني)
2. **Create cronjob:**
   - Title: `Elmy CV Bot — tick`
   - URL: `https://<your-vercel-domain>/api/tick?token=<CRON_TOKEN>`
   - Schedule: **Every 1 minute**
   - Notification: تنبيهك لو فشل (اختياري)
3. **Save & enable**

> ملاحظة: حد cron-job.org المجاني هو 50 وظيفة و60 ثانية كحد أدنى — كافي لنا.

---

## 5. التحقق قبل الإطلاق

شغّل المُتحقق:
```bash
export $(cat .env | xargs)   # تحميل env vars محلياً
python tools/check_env.py
```

النتيجة المطلوبة: **ALL CHECKS PASSED**.

---

## 6. الاختبار الأول الحقيقي

1. افتح الموقع: `https://<your-domain>/`
2. أدخل كلمة المرور
3. أنشئ **حملة اختبار** بـ:
   - CV تجريبي (PDF صغير)
   - اسم وعنوان تجريبيين
   - Package size: 20 (صغير)
   - Sector: أي تخصص فيه شركات
4. ابدأ الحملة
5. بعد 1-2 دقيقة، تحقق من Vercel logs أن `/api/tick` يستجيب
6. تحقق من Supabase: `campaign_sends` فيه صفوف status='sent'
7. افتح الإيميل التجريبي → تحقق أن البكسل سجّل الفتح في `email_opens`

---

## 7. التشغيل اليومي

النظام يدير نفسه:
- cron ينبض كل دقيقة → `/api/tick` يرسل إيميل واحد (إذا حد يومي + التباعد مسموحان)
- الحد العالمي يمنع الإفراط
- العميل يفتح الموقع من جواله → ينشئ حملات جديدة → ينتظر النتائج

---

## 8. الصيانة الدورية

- **مراقبة Vercel Logs أسبوعياً:** ابحث عن أخطاء 5xx
- **مراقبة Supabase usage:** خطة Free تكفي عملياً لكل هذا الحجم
- **توسيع قائمة الشركات:** استخدم `tools/import_companies.py` بأي وقت
- **رفع الحد اليومي تدريجياً:** إذا الحساب نظيف، عدّل `daily_cap` في `app_config`:
  ```sql
  update app_config set value = '80'::jsonb where key = 'daily_cap';
  ```

---

## 9. Troubleshooting

| المشكلة | الحل |
|---------|------|
| `/api/tick` يرجع 403 | تحقق `CRON_TOKEN` يطابق ما في cron-job.org |
| Gmail يرفض الإرسال | `App Password` خطأ. أنشئ واحد جديد + ضع في Vercel env |
| لا تظهر الفتحات | بعض عملاء الإيميل (خصوصاً Gmail) يحجبون البكسل افتراضياً. هذا متوقع. |
| Vercel logs فارغة | اذهب لـ `Functions` tab، اختر آخر deploy |
| Supabase 401 | service_role key منتهي/متغير. جدّده من Settings → API |

---

## 10. الإيقاف الطارئ

لو احتجت إيقاف كل الإرسال فوراً:
- **خيار 1 (آمن):** عطّل cronjob في cron-job.org
- **خيار 2 (فوري):** SQL في Supabase:
  ```sql
  update campaigns set status = 'paused';
  ```
- **خيار 3 (نهائي):** احذف `CRON_TOKEN` من Vercel env → كل tick راح يرجع 403
