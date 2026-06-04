# Tracking Pixel Service (Vercel)

خدمة بكسل التتبع — تُنشر على Vercel وتخزّن فتحات الإيميل في Supabase.

## النشر خطوة بخطوة

### 1. جهّز Supabase
1. افتح مشروعك على [supabase.com](https://supabase.com)
2. روح **SQL Editor** → الصق محتوى `supabase_schema.sql` → **Run**
3. خذ من **Project Settings → API**:
   - `Project URL` → سيكون `SUPABASE_URL`
   - `service_role` key (السري) → سيكون `SUPABASE_SERVICE_KEY`

### 2. انشر على Vercel
```bash
cd vercel-pixel
vercel          # أول مرة: يربط المشروع
vercel --prod   # نشر للإنتاج
```

### 3. أضف Environment Variables في Vercel
من **Project → Settings → Environment Variables** أضف:

| المفتاح | القيمة |
|--------|--------|
| `SUPABASE_URL` | https://xxxx.supabase.co |
| `SUPABASE_SERVICE_KEY` | (service_role key) |
| `STATS_TOKEN` | أي نص سري عشوائي (نفسه يوضع في البرنامج) |

ثم أعد النشر: `vercel --prod`

### 4. اربط البرنامج
في لوحة التحكم بالبرنامج، حقل **رابط البكسل** = رابط مشروع Vercel
(مثل `https://elmy-pixel.vercel.app`) و **Stats Token** = نفس `STATS_TOKEN`.

## نقاط النهاية (Endpoints)
- `GET /api/pixel?id=<uuid>` — يسجّل الفتح ويرجع صورة 1×1
- `GET /api/stats?token=<STATS_TOKEN>` — يرجّع إحصائيات الفتح (JSON)

## ملاحظة دقّة التتبع
بعض عملاء البريد (Gmail/Outlook) يحجبون الصور افتراضيًا أو يحمّلونها عبر بروكسي،
لذلك أرقام الفتح **تقريبية** وليست 100%. هذا سلوك معروف لكل أنظمة تتبع البريد.
