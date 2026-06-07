# 🤝 HANDOFF — Elmy CV Bot
> **Purpose:** Open this file at the start of every new Claude chat so the assistant has full context without re-reading the whole conversation history.

**Last updated:** 2026-06 (session 2)
**Status:** Code complete (16/16 tests passing). Awaiting client file + deployment.

---

## 1. Project Context (90-sec version)

**Client:** محمد (مستقل / mostaql). Runs a CV-blast service: his customers send him their CVs, he blasts them to companies via this platform.

**Final agreed scope ($80, web edition):**
- Web platform usable from iPhone/iPad (he has no laptop)
- Multi-tenant campaigns: one per his customer (different CV + sender + cover letter each time)
- Master company DB across 11 sectors (Healthcare, Marketing, Technology, Finance, Engineering, Legal, Retail, Education, HR, Hospitality, Logistics)
- Per-campaign sector filter + random non-overlap package selection (20/40/80 sizes)
- Gmail SMTP with **global** daily cap + spacing (single shared account)
- Gemini Flash AI generates personalised cover letters (with template fallback)
- Tracking pixel + per-campaign open stats
- Free hosting: Vercel + Supabase + cron-job.org + Gemini free tier
- Code ownership transfers to client. 2 weeks support.
- Estimated delivery: 5–6 days after file + start confirmation.

**Locked decisions** (don't re-debate):
- Gmail address: `mddx90@gmail.com`. App password: `fzta jjko asva jetz` (already provided)
- Site password: `Mm123456@@`
- Daily cap starts at 50 (can scale to 80–100 after monitoring)
- File: client will provide ~20,000 companies (hasn't arrived yet)
- Package sizes: 20/40/80 (final, replaces earlier 50/100/200)
- AI sector classifier deferred — only build if client's file lacks sector column

---

## 2. Repo Structure (what lives where)

```
elmy-cv-bot/
├── bot/                    Shared logic (used by both desktop archive AND web)
│   ├── excel_reader.py     Excel/CSV reading + email validation
│   ├── email_sender.py     Gmail SMTP + MIME + CV attachment
│   ├── language_handler.py AR/EN template rendering + {placeholders}
│   ├── rate_limiter.py     Random jitter + daily cap math
│   ├── tracker.py          Pixel URL builder + stats fetcher
│   ├── ai_writer.py        Gemini Flash + safe template fallback
│   ├── sector_aliases.py   Normalises any sector label → 11 canonical codes
│   ├── supabase_db.py      Supabase REST + Storage layer (web edition)
│   ├── web_engine.py       Stateless tick loop (one tick = one email)
│   ├── database.py         SQLite (DESKTOP archive — reference only)
│   ├── campaign.py         Threaded loop (DESKTOP archive)
│   └── config.py           JSON settings (DESKTOP archive)
├── web/                    Vercel deployment target
│   ├── api/                8 serverless endpoints (login, me, campaigns, companies, sectors, upload, stats, tick, pixel)
│   ├── public/             SPA frontend (index.html, app.js, style.css) — RTL Arabic, mobile-first
│   ├── vercel.json
│   └── requirements.txt
├── db/
│   └── schema.sql          ALL Supabase tables + views + RLS (run once)
├── tools/
│   ├── preview_import.py   Dry-run any Excel/CSV — shows valid/invalid/sector dist
│   ├── import_companies.py Bulk push to Supabase (with alias mapping)
│   ├── build_company_db.py Generates the 30-row sample
│   ├── seed_companies.py   Seeds master list into Supabase
│   └── check_env.py        Pre-deploy verifier (all env vars + connectivity)
├── tests/
│   ├── run_all.py          Runs all 16 tests → expect "16 passed, 0 failed"
│   ├── serve_local.py      Stub server for frontend dev without Supabase
│   └── test_*.py           Per-module tests
├── docs/
│   ├── PLAN.md             Full plan (clean version)
│   ├── DEPLOYMENT.md       Step-by-step runbook for going live
│   ├── NEXT_STEPS.md       10-step action plan for Youssef
│   └── HANDOFF.md          ← This file
├── client-data/            gitignored — credentials & client files
│   ├── REQUIRED_FROM_CLIENT.md
│   └── CREDENTIALS_CHECKLIST.md
├── gui/, main.py, build.bat   DESKTOP archive (Tkinter) — kept for reference
├── data/                   Sample data + cover letter templates
├── vercel-pixel/           Standalone pixel service (predecessor to web/api/pixel.py)
└── .env.example, .gitignore, README.md, requirements.txt
```

**Tests:** `python tests/run_all.py` → **16/16 passing** (config, excel, db, language, tracker, email, rate, campaign-desktop, pixel-http, gui-smoke, ai-fallback, supabase-guard, web-engine, package-selection, api-imports, sector-aliases).

---

## 3. What's Done — Feature Inventory

| Area | Feature | Status |
|------|---------|--------|
| **Platform** | Web UI (RTL, mobile-first), password-protected | ✅ built + previewed |
| **Auth** | Cookie-based with HMAC-signed token | ✅ |
| **Campaigns** | CRUD via /api/campaigns | ✅ |
| **CV upload** | Direct PDF upload to Supabase Storage | ✅ |
| **Targeting** | Sector filter + random non-overlap + recycle fallback | ✅ + tested with disjoint-set proof |
| **AI** | Gemini Flash cover-letter generation + safe template fallback | ✅ |
| **Sending** | Gmail SMTP via cron-tick, global cap/spacing | ✅ + global-cap test proves 3 campaigns ≠ 3× cap |
| **i18n** | AR/EN templates auto-selected per recipient | ✅ |
| **Tracking** | 1×1 pixel + Supabase persistence + dashboard | ✅ |
| **Master DB** | 11-sector company table + Arabic header detection | ✅ |
| **Sector aliases** | 100+ Arabic/English variants → 11 canonical codes | ✅ |
| **Import tooling** | preview + bulk importer with --dry-run + alias mapping | ✅ |
| **Env checker** | Pre-deploy verifier for all secrets + connectivity | ✅ |
| **Docs** | PLAN, DEPLOYMENT, NEXT_STEPS | ✅ |

---

## 4. What's Missing (Honest Inventory)

### 4.1 ⚠️ Production gaps surfaced by 2026 research

These are real risks for any cold-email system in 2026. **None block delivery of the agreed $80 scope**, but they affect long-term success.

| Gap | Why it matters in 2026 | Recommendation |
|-----|----------------------|----------------|
| **No sender warm-up curve** | Google's 2026 guidance: new accounts should start at **10–30/day** and ramp over 2–4 weeks. We start at 50 → moderately risky for a fresh Gmail. | Add a 14-day ramp: 10 → 15 → 20 → 30 → 50. Soft addition: change one config table row. |
| **No unsubscribe footer** | Google 2026 sender rules **require** one-click unsubscribe for senders of 5K+/day. Below that it's a strong best practice that protects sender reputation. | Add a footer + `/unsubscribe?id=<uuid>` endpoint that adds the email to a `do_not_contact` table. |
| **No business-hour limit** | Sending at 3am looks bot-like and tanks open rates. | Add `send_hours_start/end` to app_config; tick skips outside range. |
| **No bounce handling** | Gmail bounces accumulate in `mddx90@`'s inbox. Hard bounces should mark the company invalid. | Add IMAP poller (separate cron) that reads `INBOX`, parses bounces, updates `companies.invalid_reason`. |
| **No spam-complaint monitoring** | Google ≥0.10% = throttle, ≥0.30% = block. | Manual check via Google Postmaster Tools (free) — document only. |
| **No domain authentication** | Using `@gmail.com` we inherit Google's SPF/DKIM. Fine for now. Risky only if we move to custom domain without setting up SPF/DKIM/DMARC. | Doc-only: covered in DEPLOYMENT.md if/when client adds custom domain. |

**Suggested handling:** add **warm-up + unsubscribe + business hours** as a small follow-up commit (about 100 lines + 1 new endpoint). Total effort: ~1.5 hrs. Recommend doing these BEFORE first real send to protect `mddx90@gmail.com`.

### 4.2 🔵 Out of scope (priced separately if client asks later)

- AI sector classifier for files without sectors
- Custom domain + SPF/DKIM/DMARC (~$35 + setup)
- Amazon SES / SendGrid integration (~$45)
- ZeroBounce email verification (~$25)
- Multi-step follow-up sequences
- A/B subject line testing

### 4.3 🔴 Deployment-side gaps (not code)

- Real Supabase project doesn't exist yet
- Vercel project doesn't exist yet
- Gemini API key not issued
- New Gmail for sending not created
- cron-job.org cron not configured
- **Client's 20,000-company file not yet received**
- **Client has not paid** (مستقل deposit)

---

## 5. Patterns Borrowed from Similar Projects (research notes)

| Project | What we adopted | What we did differently |
|---------|----------------|------------------------|
| [PaulleDemon/Email-automation](https://github.com/PaulleDemon/Email-automation) | Dynamic templates with placeholders | We use Gemini AI on top + safe fallback |
| [chinmaykhamkar/automate-cold-email](https://github.com/chinmaykhamkar/automate-cold-email) | Gmail SMTP + Excel input | We added stateless serverless model + multi-tenant |
| [Sandreke/email-automation](https://github.com/Sandreke/email-automation) | Excel + attachments | We persist state in Supabase for resume |
| [msinamsina/pyautomail](https://github.com/msinamsina/pyautomail) | Large-scale targeting | We added per-recipient sector + non-overlap |

**Key insight from research:** all the popular open-source tools acknowledge they're for "personal/legitimate" use and warn that sending to scraped lists will get the account banned. **This is exactly the risk with the client's 20K list.** Document it in the delivery PDF.

---

## 6. Next-Session Quick Start

When the next chat opens, the assistant should:

1. **Read `docs/HANDOFF.md` (this file)** — re-establishes context in 60s
2. **Run** `python tests/run_all.py` — verify nothing's broken (should be 16/16)
3. **Check** `git status` — see if Youssef made changes
4. Ask the user the **single triage question:**
   - "What stage are we at? (a) waiting for client file, (b) file just arrived, (c) ready to deploy, (d) something's broken, (e) other"
5. Branch from there:
   - **(a):** stay idle or build the warm-up / unsubscribe enhancements
   - **(b):** run `tools/preview_import.py` on the file, then `tools/import_companies.py`
   - **(c):** walk through `docs/DEPLOYMENT.md` step by step
   - **(d):** debug
   - **(e):** ask for specifics

**Do NOT re-research, re-design, or re-discuss pricing.** Decisions are locked (see §1).

---

## 7. Conversation Memory (lessons learned from the build)

Behavioural notes for the next assistant:

- **Client is a scope-creep risk.** He added 5 mid-build asks: random non-overlap, sectors, 20K list, Gemini AI, package sizes. Don't take "small add" at face value — always check math against earlier decisions before agreeing.
- **Client uses Arabic + emoji.** Replies should be Arabic, professional tone. He explicitly disliked emojis in the final scope doc.
- **Youssef wants to maximize the client lifetime.** Avoid burning the relationship for $5 differences. He accepted $80 even though scope grew.
- **Pricing is locked at $80** unless Youssef explicitly asks to re-open. Anything beyond the locked scope (§1) should be quoted separately, not bundled.
- **Don't deploy / spend real money** until Youssef confirms the deposit landed.

---

## 8. Open Questions Awaiting Client

These travel with the project until answered:

1. Does the 20K file have a sector column? (If not, AI classifier decision needed.)
2. Sample of the file expected — Youssef will forward it when received.
3. Daily cap: stay at 50 forever, or accept the proposed 50→80 ramp after first 14 days?
4. Is `Mm123456@@` final or just placeholder during dev?

---

## 9. Recommended Next Work Items (priority order)

If Youssef is idle waiting for the file, the assistant can productively do:

1. ⭐ **Add 14-day warm-up curve** (`app_config` table + tick check) — biggest deliverability win
2. ⭐ **Add unsubscribe footer + `/api/unsubscribe`** — 2026 compliance + reputation
3. **Add `send_hours_start/end` to app_config** — business-hour gating
4. **Build AI sector classifier** (defer until file confirms it's needed)
5. **Add bounce IMAP poller** (separate cron) — second-priority
6. **Custom domain setup guide** — doc only, for when client upgrades

Anything else → ask Youssef first.

---

## 10. Sources / Research References (June 2026)

- [Gmail 2026 sending limits — smartlead.ai](https://www.smartlead.ai/blog/gmail-sending-limits)
- [Google email sender guidelines (2026 changes) — litemail.ai](https://litemail.ai/blog/google-email-sender-guidelines-2026-changes)
- [Google's official sender guidelines](https://support.google.com/a/answer/81126)
- [Email sending limits comprehensive — growthlist.co](https://growthlist.co/email-sending-limits-of-various-email-service-providers/)
- [Open-source cold email reference — PaulleDemon/Email-automation](https://github.com/PaulleDemon/Email-automation)
- [Open-source bulk sender pattern — msinamsina/pyautomail](https://github.com/msinamsina/pyautomail)
- [Cold-email Excel pattern — chinmaykhamkar/automate-cold-email](https://github.com/chinmaykhamkar/automate-cold-email)
