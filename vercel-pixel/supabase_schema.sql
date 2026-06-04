-- ============================================================
-- Elmy CV Bot — Supabase schema for tracking pixel
-- Run this once in the Supabase SQL Editor.
-- ============================================================

-- Raw open events: one row per pixel hit.
create table if not exists public.email_opens (
    id          bigint generated always as identity primary key,
    email_uuid  text not null,
    opened_at   timestamptz not null default now(),
    ip          text,
    user_agent  text
);

create index if not exists idx_email_opens_uuid on public.email_opens (email_uuid);

-- Aggregated view: one row per email_uuid with open count + first/last seen.
create or replace view public.email_opens_agg as
select
    email_uuid,
    count(*)::int        as open_count,
    min(opened_at)       as first_open_at,
    max(opened_at)       as last_seen_at
from public.email_opens
group by email_uuid;

-- Security: the serverless functions use the SERVICE ROLE key, which bypasses
-- RLS. We still enable RLS and add NO public policies so the anon key cannot
-- read or write this data directly.
alter table public.email_opens enable row level security;

-- (No policies added on purpose: anon/public access is denied.
--  Only the service_role key used by the Vercel functions can read/write.)
