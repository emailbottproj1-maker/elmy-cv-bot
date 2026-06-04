-- ============================================================
-- Elmy CV Bot — Web Edition Schema (Supabase)
-- Run once in Supabase SQL Editor.
-- ============================================================

-- ---------- master company list (built once, reused) ----------
create table if not exists public.companies (
    id           bigint generated always as identity primary key,
    company_name text not null,
    email        text not null unique,
    language     text default 'en' check (language in ('ar','en')),
    sector       text,
    city         text,
    source       text default 'manual',
    added_at     timestamptz default now()
);
create index if not exists idx_companies_email on public.companies(email);

-- ---------- one campaign per "Mohammed's customer" ----------
create table if not exists public.campaigns (
    id              bigint generated always as identity primary key,
    customer_label  text not null,                          -- e.g. "Ahmad - Senior Dev"
    cv_storage_path text not null,                          -- path in Storage bucket
    sender_name     text not null,
    subject_ar      text not null,
    subject_en      text not null,
    cover_letter_ar text not null,                          -- with {company_name}
    cover_letter_en text not null,
    use_ai          boolean default true,
    -- per-customer package size: 50 / 100 / 200 (configurable). NULL = full list.
    package_size    int,
    -- counts how many of the chosen recipients were RECYCLED (already used in
    -- previous campaigns) because the unclaimed pool was exhausted. 0 = clean.
    overlap_count   int default 0,
    -- sector filter: e.g. 'Healthcare'. NULL = no sector filter (any company).
    target_sector   text,
    status          text default 'draft' check (status in ('draft','active','paused','done','stopped')),
    created_at      timestamptz default now()
);

-- Backfill if the table already existed (idempotent).
alter table public.campaigns add column if not exists package_size int;
alter table public.campaigns add column if not exists overlap_count int default 0;
alter table public.campaigns add column if not exists target_sector text;
create index if not exists idx_companies_sector on public.companies(sector);

-- ============================================================
-- Canonical sector list (English codes used in DB / Arabic shown in UI).
-- The frontend maps the English code -> Arabic label.
-- Healthcare, Marketing, Technology, Finance, Engineering, Legal,
-- Retail, Education, HR, Hospitality, Logistics
-- ============================================================
create index if not exists idx_campaigns_status on public.campaigns(status);

-- ---------- per-recipient send tracking ----------
create table if not exists public.campaign_sends (
    id              bigint generated always as identity primary key,
    campaign_id     bigint not null references public.campaigns(id) on delete cascade,
    company_id      bigint not null references public.companies(id),
    status          text default 'pending' check (status in ('pending','sent','failed')),
    tracking_uuid   text unique,
    generated_body  text,                                   -- AI / template output for audit
    sent_at         timestamptz,
    error           text,
    attempts        int default 0,
    unique (campaign_id, company_id)
);
create index if not exists idx_sends_status on public.campaign_sends(campaign_id, status);
create index if not exists idx_sends_uuid   on public.campaign_sends(tracking_uuid);

-- ---------- pixel opens (kept from desktop edition, schema aligned) ----------
create table if not exists public.email_opens (
    id          bigint generated always as identity primary key,
    email_uuid  text not null,
    opened_at   timestamptz default now(),
    ip          text,
    user_agent  text
);
create index if not exists idx_opens_uuid on public.email_opens(email_uuid);

create or replace view public.email_opens_agg as
select email_uuid,
       count(*)::int as open_count,
       min(opened_at) as first_open_at,
       max(opened_at) as last_seen_at
from public.email_opens
group by email_uuid;

-- ---------- global app config (single-row key/value) ----------
create table if not exists public.app_config (
    key   text primary key,
    value jsonb not null,
    updated_at timestamptz default now()
);

-- defaults (idempotent)
insert into public.app_config(key, value) values
    ('daily_cap',       '50'::jsonb),
    ('min_delay_sec',   '60'::jsonb),
    ('max_delay_sec',   '180'::jsonb),
    ('last_global_send_at', 'null'::jsonb),
    ('sent_today',      '{"date":null,"count":0}'::jsonb)
on conflict (key) do nothing;

-- ============================================================
-- Security: all tables locked to service_role only
-- (Vercel functions use SUPABASE_SERVICE_KEY; the website
--  never touches Supabase directly from the browser.)
-- ============================================================
alter table public.companies      enable row level security;
alter table public.campaigns      enable row level security;
alter table public.campaign_sends enable row level security;
alter table public.email_opens    enable row level security;
alter table public.app_config     enable row level security;
-- (No public policies → only service_role can read/write.)

-- ============================================================
-- Storage bucket for CVs (run in Storage UI or via:)
-- insert into storage.buckets (id, name, public)
--   values ('cvs', 'cvs', false) on conflict do nothing;
-- ============================================================
