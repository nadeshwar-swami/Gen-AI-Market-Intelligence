-- ================================================================
-- MarketAI Suite — Supabase Database Schema
-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor)
-- ================================================================

-- Needed for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── 1. Profiles table (extends auth.users) ───────────────────────
CREATE TABLE IF NOT EXISTS public.profiles (
  id          UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name   TEXT,
  company     TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-create a profile row whenever a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.profiles (id, full_name)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'full_name'
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ── 2. History table ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.history (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tool        TEXT        NOT NULL CHECK (tool IN ('campaign', 'pitch', 'lead_score', 'image_banner', 'video_ad')),
  input_data  JSONB       NOT NULL DEFAULT '{}',
  output      TEXT        NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Keep existing environments in sync when this file is re-run.
ALTER TABLE public.history DROP CONSTRAINT IF EXISTS history_tool_check;
ALTER TABLE public.history
  ADD CONSTRAINT history_tool_check
  CHECK (tool IN ('campaign', 'pitch', 'lead_score', 'image_banner', 'video_ad'));

-- Index for fast per-user queries
CREATE INDEX IF NOT EXISTS history_user_id_idx ON public.history (user_id, created_at DESC);

-- ── 3. Row-Level Security ─────────────────────────────────────────
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.history   ENABLE ROW LEVEL SECURITY;

-- Re-running schema should not fail because policies already exist.
DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own" ON public.profiles;
DROP POLICY IF EXISTS "history_select_own" ON public.history;
DROP POLICY IF EXISTS "history_insert_own" ON public.history;
DROP POLICY IF EXISTS "history_delete_own" ON public.history;

-- Profiles: users can only read/update their own row
CREATE POLICY "profiles_select_own" ON public.profiles
  FOR SELECT USING (auth.uid() = id);

CREATE POLICY "profiles_update_own" ON public.profiles
  FOR UPDATE USING (auth.uid() = id);

-- History: users can only see/insert/delete their own rows
CREATE POLICY "history_select_own" ON public.history
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "history_insert_own" ON public.history
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "history_delete_own" ON public.history
  FOR DELETE USING (auth.uid() = user_id);

-- Service role bypass (needed for server-side inserts using service key)
-- Supabase service role automatically bypasses RLS — no extra policy needed.

-- ── 4. Useful view: history with profile info ─────────────────────
CREATE OR REPLACE VIEW public.history_with_profile AS
SELECT
  h.*,
  p.full_name,
  p.company
FROM public.history h
JOIN public.profiles p ON p.id = h.user_id;

-- ================================================================
-- Done! Go to Authentication → Settings in Supabase dashboard and:
--   • Set Site URL to http://localhost:5000
--   • Add Redirect URL: http://localhost:5000/auth/callback
--   • Optionally enable email confirmations (disable for dev)
-- ================================================================
