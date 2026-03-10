"""
supabase_client.py
Initialises the Supabase client once and exposes it as `supabase`.
Set SUPABASE_URL and SUPABASE_ANON_KEY in your .env file.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str  = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str  = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError(
        "Missing SUPABASE_URL or SUPABASE_ANON_KEY in environment variables.\n"
        "Create a .env file with these values from your Supabase project settings."
    )

# Public (anon) client – used for auth operations
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Service-role client – used for server-side DB writes (bypasses RLS safely)
supabase_admin: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY if SUPABASE_SERVICE_KEY else SUPABASE_KEY
)
