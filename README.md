# MarketAI Suite 🚀

AI-powered Sales & Marketing platform built with **Flask + Groq LLaMA 3.3 70B + Supabase**.

## Features

| Feature | Description |
|---|---|
| 📣 Campaign Generator | Full marketing strategy: objectives, content ideas, ad copy, CTAs, tracking |
| 🎯 Sales Pitch Creator | Personalized B2B pitches: elevator pitch, value prop, differentiators, objection handlers |
| ⭐ Lead Qualifier | BANT-based lead scoring 0–100 with conversion probability |
| 🔐 Auth (Supabase) | Email/password sign-up, login, JWT session, profile management |
| 🕘 History | Every AI result auto-saved per user; filterable, expandable, deletable |

---

## Project Structure

```
marketai/
├── app.py                  # Flask backend — all routes (auth + AI + history)
├── supabase_client.py      # Supabase client initialisation
├── schema.sql              # Run once in Supabase SQL Editor
├── requirements.txt        # Python dependencies
├── .env.example            # Copy to .env and fill in your keys
├── static/
│   └── style.css           # Full dark UI stylesheet
└── templates/
    └── index.html          # Single-page app (auth modal + 3 tools + history)
```

---

## Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd marketai
pip install -r requirements.txt
```

### 2. Set up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** → paste the contents of `schema.sql` → **Run**
3. Go to **Authentication → Settings**:
   - Set **Site URL** to `http://localhost:5000`
   - Add **Redirect URL**: `http://localhost:5000/auth/callback`
   - (Optional for dev) Disable email confirmation
4. Go to **Authentication → Providers → Google**:
   - Enable Google provider
   - Add your Google OAuth Client ID and Client Secret
   - In Google Cloud Console, add this authorized redirect URI:
     `https://<your-project-ref>.supabase.co/auth/v1/callback`
5. Go to **Project Settings → API** and copy:
   - **Project URL**
   - **anon/public key**
   - **service_role key** (keep secret!)

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual keys
```

```env
GROQ_API_KEY=gsk_...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...
FLASK_SECRET_KEY=some-long-random-string
# Optional: override callback URL in production
SUPABASE_REDIRECT_URL=http://localhost:5000/auth/callback
```

### 4. Run

```bash
python app.py
```

Open `http://localhost:5000`

### If Supabase Tables Are Missing

If login works but profile/history features fail, your DB schema is not applied yet.

1. Open Supabase dashboard → **SQL Editor**.
2. Open local `schema.sql` and paste the full content.
3. Click **Run**.
4. Verify in **Table Editor** that `profiles` and `history` exist under `public` schema.
5. Optional verification query:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
   and table_name in ('profiles', 'history')
order by table_name;
```

---

## API Reference

### Auth

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/signup` | Register with email, password, full_name |
| POST | `/auth/login` | Login, returns session |
| POST | `/auth/logout` | Invalidate session |
| GET  | `/auth/me` | Current user info |
| PUT  | `/auth/update_profile` | Update name & company |

### AI Tools (🔒 require login)

| Method | Endpoint | Form Fields |
|---|---|---|
| POST | `/generate_campaign` | product, audience, platform |
| POST | `/generate_pitch` | product, customer |
| POST | `/lead_score` | name, budget, need, urgency |

### History (🔒 require login)

| Method | Endpoint | Description |
|---|---|---|
| GET    | `/history` | Get last 50 records (optional `?tool=campaign\|pitch\|lead_score`) |
| DELETE | `/history/<id>` | Delete single record |
| DELETE | `/history/clear` | Delete all records |

---

## Lead Score Tiers

| Score  | Category    | Action              |
|--------|-------------|---------------------|
| 90–100 | 🔥 Hot Lead | Immediate follow-up |
| 75–89  | ♨️ Warm     | Priority outreach   |
| 60–74  | 🌡️ Lukewarm | Nurture sequence    |
| < 60   | ❄️ Cold     | Defer / disqualify  |

---

## Tech Stack

- **Backend**: Python 3.8+, Flask, Flask-CORS
- **Auth & DB**: Supabase (PostgreSQL + GoTrue Auth + Row-Level Security)
- **AI**: Groq API — LLaMA 3.3 70B Versatile
- **Frontend**: Vanilla HTML/CSS/JS (zero framework dependency)
- **Fonts**: Syne + DM Sans

---

## Production Deployment

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Set `FLASK_SECRET_KEY` to a strong random value and disable Flask debug mode.
