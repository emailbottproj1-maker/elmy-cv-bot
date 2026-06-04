# 🎯 الخطوات التالية — Action Plan

> آخر تحديث: بعد جلسة 2026-06-01. النظام مبني ومُختبر (16/16 ✅).

---

## ⚡ ما يحدث الآن

النظام جاهز للنشر. ينتظر:
1. حسابات الخدمات (تنشئها بالإيميل الجديد)
2. ملف العميل (لم يصل بعد)

أثناء انتظار الملف، أنجز خطوات 1-7 أدناه. لما يصل الملف، خطوة 8 + 9.

---

## 1️⃣ أنشئ إيميل Gmail جديد للبوت

- اسم مقترح: `elmycvbot.deliveries@gmail.com` أو ما يلائم
- مهم: استخدم اسم احترافي يصلح للإرسال للشركات
- بعد الإنشاء: **فعّل 2-Step Verification** (إجباري للخطوة 2)

## 2️⃣ أنشئ App Password

- روح: https://myaccount.google.com/apppasswords
- App name: `Elmy CV Bot`
- انسخ الـ16 حرف (مرة واحدة فقط — احفظه)
- ضعه في `client-data/CREDENTIALS_CHECKLIST.md`

## 3️⃣ افتح GitHub repo

- روح github.com → **New Repository**
- Name: `elmy-cv-bot` (أو ما يلائم)
- Visibility: **Private** (هذا مهم — الكود سيحوي مفاتيح env vars)
- Don't initialize with README (الريبو عندك جاهز)
- بعد الإنشاء، خذ الـ URL

## 4️⃣ ارفع الكود للريبو

من مجلد المشروع، شغّل:

```bash
cd "D:/Work/Portifolio & Projects/elmy-cv-bot"
git init
git add -A
git status            # تأكد إن .env و client-data/ مش ضمن المرفوع
git commit -m "Initial commit: Elmy CV Bot — web edition"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/elmy-cv-bot.git
git push -u origin main
```

## 5️⃣ Supabase

1. supabase.com → **New Project** (Free tier)
2. Region: `Central EU (Frankfurt)` (أقرب للشرق الأوسط)
3. بعد الإنشاء:
   - **SQL Editor** → الصق محتوى `db/schema.sql` → Run
   - **Storage** → New bucket: `cvs` (Private)
   - **Settings → API** → انسخ:
     - Project URL → `SUPABASE_URL`
     - service_role secret → `SUPABASE_SERVICE_KEY`
4. سجّلهم في `CREDENTIALS_CHECKLIST.md`

## 6️⃣ Google AI Studio (Gemini)

1. aistudio.google.com → **Get API key**
2. سجّل المفتاح في الـ checklist

## 7️⃣ Vercel

1. vercel.com → Sign up with GitHub (يربط ريبواتك تلقائياً)
2. **Import Project** → اختر `elmy-cv-bot`
3. **Root Directory:** `web/`  (مهم!)
4. **Environment Variables** أضف:
   ```
   SUPABASE_URL              = https://xxxx.supabase.co
   SUPABASE_SERVICE_KEY      = eyJ...
   SITE_PASSWORD             = Mm123456@@
   GMAIL_ADDRESS             = elmycvbot@gmail.com
   GMAIL_APP_PASSWORD        = xxxx xxxx xxxx xxxx
   GEMINI_API_KEY            = AIza...
   CRON_TOKEN                = 6c11e070b66cb4909498b12afdaf3b05239ead9d783ce2bd
   PIXEL_BASE_URL            = (اتركه فارغ لحد ما نعرف رابط Vercel)
   ```
5. Deploy
6. بعد النشر، انسخ الـ Production URL → عدّله ضمن `PIXEL_BASE_URL` → Redeploy

## 8️⃣ cron-job.org

1. cron-job.org → Sign up
2. **Create cronjob:**
   - URL: `https://YOUR_VERCEL_URL/api/tick?token=6c11e070b66cb4909498b12afdaf3b05239ead9d783ce2bd`
   - Schedule: Every 1 minute
3. Enable

## 9️⃣ التحقق قبل أي حملة حقيقية

افتح Terminal محلي وشغّل (بعد تعبئة env vars):

```bash
export SUPABASE_URL=...
export SUPABASE_SERVICE_KEY=...
export GMAIL_ADDRESS=...
export GMAIL_APP_PASSWORD=...
export GEMINI_API_KEY=...
export SITE_PASSWORD=Mm123456@@
export CRON_TOKEN=6c11e070b66cb4909498b12afdaf3b05239ead9d783ce2bd

python tools/check_env.py
```

**النتيجة المطلوبة:** `ALL CHECKS PASSED — safe to deploy.`

ثم زر الموقع من جوال → سجّل دخول → أنشئ حملة اختبار صغيرة بـ 5 شركات وهمية → راقب.

## 🔟 لما يصل ملف العميل

```bash
# 1. فحص هيكل الملف
python tools/preview_import.py path/to/client-file.xlsx

# 2. لو نظيف، استيراد فعلي
python tools/import_companies.py path/to/client-file.xlsx

# 3. لو فيه تخصصات غير معروفة في التقرير،
#    إما إضافتها في bot/sector_aliases.py
#    أو استخدام --keep-unknown لاستيرادها كما هي
```

---

## 🚨 تحذيرات أمان

- **لا ترفع `.env` على GitHub.** ملف `.gitignore` يستثنيه، لكن تأكد دائماً.
- **service_role key قوية جداً** — تعطي صلاحيات كاملة. احفظها في Vercel فقط.
- **App Password قابل للإلغاء** — إذا تسرّبت، روح Google → Apps → Revoke.
- **لا تشارك ريبوك public** قبل ما تتأكد إن `.env` و `client-data/` مستثناة.

---

## 📞 جلسة النشر الكاملة

لما تكون عندك:
- ✅ Gmail جديد + App Password
- ✅ GitHub repo فاضي
- ✅ حسابات Supabase / Vercel / cron-job / AI Studio
- ✅ نسخة من الـ CRON_TOKEN

اطلب جلسة معي، ونمشي خطوة بخطوة حية على كل خدمة.
