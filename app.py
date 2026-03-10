"""
app.py — MarketAI Suite
Flask backend with Groq AI + Supabase authentication & history persistence.
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import requests
import re
import os
from functools import wraps
from dotenv import load_dotenv
from supabase_client import supabase, supabase_admin

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(32))
CORS(app, supports_credentials=True)

# ── Groq Config ──────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def call_groq(prompt: str) -> str:
    """Call Groq LLaMA API and return cleaned text response."""
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY is not set. Please add it to your .env file."
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    body = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    try:
        response = requests.post(GROQ_URL, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        data   = response.json()
        result = data["choices"][0]["message"]["content"]
        result = re.sub(r'[\*\_]{1,3}(.+?)[\*\_]{1,3}', r'\1', result)
        return result
    except requests.exceptions.Timeout:
        return "API Error: Request timed out. Please try again."
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            return "API Error: Invalid Groq API key. Check GROQ_API_KEY in .env."
        return f"API Error: {str(e)}. Please try again."
    except Exception as e:
        return f"API Error: {str(e)}. Please try again."


def login_required(f):
    """Decorator — requires a valid Supabase access token in the session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = session.get("access_token")
        if not token:
            return jsonify({"error": "Authentication required.", "code": "AUTH_REQUIRED"}), 401
        try:
            user_resp = supabase.auth.get_user(token)
            if not user_resp or not user_resp.user:
                session.clear()
                return jsonify({"error": "Session expired. Please log in again.", "code": "SESSION_EXPIRED"}), 401
            request.current_user = user_resp.user
        except Exception:
            session.clear()
            return jsonify({"error": "Session expired. Please log in again.", "code": "SESSION_EXPIRED"}), 401
        return f(*args, **kwargs)
    return decorated


def save_history(user_id: str, tool: str, input_data: dict, output: str):
    """Persist an AI result to the history table."""
    try:
        supabase_admin.table("history").insert({
            "user_id":    user_id,
            "tool":       tool,
            "input_data": input_data,
            "output":     output
        }).execute()
    except Exception as e:
        app.logger.warning(f"Failed to save history for user {user_id}: {e}")





# ══════════════════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/auth/signup", methods=["POST"])
def signup():
    data      = request.get_json(silent=True) or {}
    email     = (data.get("email") or "").strip().lower()
    password  = (data.get("password") or "").strip()
    full_name = (data.get("full_name") or "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    try:
        resp = supabase.auth.sign_up({
            "email":    email,
            "password": password,
            "options":  {"data": {"full_name": full_name}}
        })
        if resp.user is None:
            return jsonify({"error": "Sign-up failed. The email may already be in use."}), 400

        # Explicitly create profile for new user (trigger may not fire if email confirmation is required)
        try:
            supabase_admin.table("profiles").upsert({
                "id": resp.user.id,
                "full_name": full_name
            }).execute()
            app.logger.info(f"Profile created for new user {resp.user.id}")
        except Exception as profile_err:
            app.logger.warning(f"Profile creation failed (may be OK if trigger worked): {profile_err}")

        if resp.session:
            session["access_token"]  = resp.session.access_token
            session["refresh_token"] = resp.session.refresh_token
            session["user_id"]       = resp.user.id
            session.modified = True
            return jsonify({
                "message": "Account created successfully.",
                "user": {
                    "id":        resp.user.id,
                    "email":     resp.user.email,
                    "full_name": full_name
                }
            }), 201

        return jsonify({
            "message":       "Account created! Check your email to confirm your address.",
            "confirm_email": True,
            "user": {
                "id": resp.user.id,
                "email": resp.user.email,
                "full_name": full_name
            }
        }), 201

    except Exception as e:
        err = str(e)
        app.logger.error(f"Signup error: {err}")
        if "already registered" in err.lower() or "already exists" in err.lower():
            return jsonify({"error": "An account with this email already exists."}), 409
        return jsonify({"error": f"Sign-up error: {err}"}), 500


@app.route("/auth/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    try:
        resp = supabase.auth.sign_in_with_password({
            "email":    email,
            "password": password
        })
        if not resp.session:
            return jsonify({"error": "Invalid email or password."}), 401

        session["access_token"]  = resp.session.access_token
        session["refresh_token"] = resp.session.refresh_token
        session["user_id"]       = resp.user.id
        session.modified = True

        # Ensure profile exists (create if missing)
        try:
            profile_resp = supabase_admin.table("profiles") \
                .select("full_name, company") \
                .eq("id", resp.user.id) \
                .maybe_single() \
                .execute()
            profile = profile_resp.data or {}
            
            # If profile doesn't exist, create it
            if not profile:
                supabase_admin.table("profiles").insert({
                    "id": resp.user.id,
                    "full_name": resp.user.user_metadata.get("full_name", "")
                }).execute()
                profile = {"full_name": resp.user.user_metadata.get("full_name", ""), "company": ""}
        except Exception as profile_err:
            app.logger.warning(f"Profile query/create error: {profile_err}")
            profile = {}

        return jsonify({
            "message": "Logged in successfully.",
            "user": {
                "id":        resp.user.id,
                "email":     resp.user.email,
                "full_name": profile.get("full_name") or resp.user.user_metadata.get("full_name", ""),
                "company":   profile.get("company", "")
            }
        })

    except Exception as e:
        err = str(e)
        app.logger.error(f"Login error: {err}")
        if "invalid" in err.lower() or "credentials" in err.lower():
            return jsonify({"error": "Invalid email or password."}), 401
        return jsonify({"error": f"Login error: {err}"}), 500


@app.route("/auth/callback", methods=["GET", "POST"])
def auth_callback():
    """Handle OAuth callback from Supabase. Session is set client-side via JS SDK."""
    # When using Supabase JS SDK with OAuth, the session is managed client-side.
    # This route can be used to verify/sync session if needed.
    error = request.args.get("error", "")
    error_description = request.args.get("error_description", "")
    
    if error or error_description:
        msg = error_description or error
        return redirect(f"/?auth_error={msg}")
    
    # Session was set client-side, just redirect home
    return redirect("/?auth_complete=true")


@app.route("/auth/logout", methods=["POST"])
def logout():
    token = session.get("access_token")
    if token:
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
    session.clear()
    return jsonify({"message": "Logged out successfully."})


@app.route("/auth/me", methods=["GET"])
def me():
    token = session.get("access_token")
    if not token:
        return jsonify({"authenticated": False}), 200
    try:
        user_resp = supabase.auth.get_user(token)
        if not user_resp or not user_resp.user:
            session.clear()
            return jsonify({"authenticated": False}), 200
        user = user_resp.user
        
        # Try to get profile, create if missing
        try:
            profile_resp = supabase_admin.table("profiles") \
                .select("full_name, company") \
                .eq("id", user.id) \
                .maybe_single() \
                .execute()
            profile = profile_resp.data or {}
            
            # If profile missing, create it
            if not profile:
                full_name = user.user_metadata.get("full_name", user.email.split("@")[0])
                supabase_admin.table("profiles").insert({
                    "id": user.id,
                    "full_name": full_name
                }).execute()
                profile = {"full_name": full_name, "company": ""}
        except Exception as err:
            app.logger.warning(f"Profile fetch/create error: {err}")
            profile = {}
        
        return jsonify({
            "authenticated": True,
            "user": {
                "id":        user.id,
                "email":     user.email,
                "full_name": profile.get("full_name") or user.user_metadata.get("full_name", ""),
                "company":   profile.get("company", "")
            }
        })
    except Exception:
        session.clear()
        return jsonify({"authenticated": False}), 200


@app.route("/auth/sync-session", methods=["POST"])
def sync_session():
    """Sync Supabase SDK session (from client) to Flask server session."""
    data = request.get_json(silent=True) or {}
    access_token = (data.get("access_token") or "").strip()
    refresh_token = (data.get("refresh_token") or "").strip()
    
    if not access_token:
        return jsonify({"error": "Missing access_token"}), 400
    
    try:
        # Verify the token is valid by getting user info
        user_resp = supabase.auth.get_user(access_token)
        if not user_resp or not user_resp.user:
            return jsonify({"error": "Invalid token"}), 401
        
        user = user_resp.user
        user_id = user.id
        
        # Ensure profile exists for this user (important for OAuth users)
        try:
            full_name = user.user_metadata.get("full_name", user.email.split("@")[0])
            supabase_admin.table("profiles").upsert({
                "id": user_id,
                "full_name": full_name
            }).execute()
            app.logger.info(f"Profile ensured for user {user_id}")
        except Exception as profile_err:
            app.logger.warning(f"Profile upsert error (non-critical): {profile_err}")
        
        # Store tokens in Flask server session
        session["access_token"] = access_token
        if refresh_token:
            session["refresh_token"] = refresh_token
        session["user_id"] = user_id
        session.modified = True
        
        app.logger.info(f"Session synced for user {user_id}")
        return jsonify({"authenticated": True})
    except Exception as e:
        app.logger.error(f"Session sync error: {str(e)}")
        return jsonify({"error": str(e)}), 401


@app.route("/auth/update_profile", methods=["PUT"])
@login_required
def update_profile():
    data      = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    company   = (data.get("company") or "").strip()
    user_id   = request.current_user.id
    try:
        supabase_admin.table("profiles").upsert({
            "id":        user_id,
            "full_name": full_name,
            "company":   company
        }).execute()
        return jsonify({"message": "Profile updated.", "full_name": full_name, "company": company})
    except Exception as e:
        return jsonify({"error": f"Update failed: {str(e)}"}), 500


# ══════════════════════════════════════════════════════════════════════════════
#  HISTORY ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/history", methods=["GET"])
@login_required
def get_history():
    user_id = request.current_user.id
    tool    = request.args.get("tool")
    limit   = min(int(request.args.get("limit", 50)), 100)
    try:
        query = supabase_admin.table("history") \
            .select("id, tool, input_data, output, created_at") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(limit)
        if tool:
            query = query.eq("tool", tool)
        resp = query.execute()
        return jsonify({"history": resp.data or []})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch history: {str(e)}"}), 500


@app.route("/history/<record_id>", methods=["DELETE"])
@login_required
def delete_history(record_id):
    user_id = request.current_user.id
    try:
        supabase_admin.table("history") \
            .delete() \
            .eq("id", record_id) \
            .eq("user_id", user_id) \
            .execute()
        return jsonify({"message": "Record deleted."})
    except Exception as e:
        return jsonify({"error": f"Delete failed: {str(e)}"}), 500


@app.route("/history/clear", methods=["DELETE"])
@login_required
def clear_history():
    user_id = request.current_user.id
    try:
        supabase_admin.table("history") \
            .delete() \
            .eq("user_id", user_id) \
            .execute()
        return jsonify({"message": "History cleared."})
    except Exception as e:
        return jsonify({"error": f"Clear failed: {str(e)}"}), 500


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    # Pass Supabase credentials to frontend for JS SDK initialization
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    return render_template("index.html", 
                         supabase_url=supabase_url,
                         supabase_anon_key=supabase_anon_key)


# ══════════════════════════════════════════════════════════════════════════════
#  AI ROUTES  (require login)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/generate_campaign", methods=["POST"])
@login_required
def generate_campaign():
    product  = request.form.get("product",  "").strip()
    audience = request.form.get("audience", "").strip()
    platform = request.form.get("platform", "").strip()

    if not product or not audience or not platform:
        return jsonify({"result": "Error: Please fill in all fields."})

    prompt = f"""Generate a detailed and comprehensive marketing campaign strategy.

Product: {product}
Target Audience: {audience}
Platform: {platform}

Please include ALL of the following sections, clearly labeled:

1. CAMPAIGN OBJECTIVES - State 3 clear, measurable campaign objectives

2. CONTENT IDEAS (provide exactly 5) - Tailored to {platform} and the target audience

3. AD COPY VARIATIONS (provide exactly 3)
   - Variation 1 (Problem-Agitate-Solve)
   - Variation 2 (Social Proof)
   - Variation 3 (Limited-Time Offer)

4. CALL-TO-ACTION SUGGESTIONS (provide exactly 5) - Tailored to {platform}

5. TRACKING & MEASUREMENT - 4 key metrics and tools

Make each section detailed and specifically tailored to {platform}."""

    output = call_groq(prompt)
    save_history(
        user_id=request.current_user.id, tool="campaign",
        input_data={"product": product, "audience": audience, "platform": platform},
        output=output
    )
    return jsonify({"result": output})


@app.route("/generate_pitch", methods=["POST"])
@login_required
def generate_pitch():
    product  = request.form.get("product",  "").strip()
    customer = request.form.get("customer", "").strip()

    if not product or not customer:
        return jsonify({"result": "Error: Please fill in all fields."})

    prompt = f"""Create a compelling, personalized B2B sales pitch.

Product/Solution: {product}
Customer Persona: {customer}

Please include ALL of the following sections, clearly labeled:

1. 30-SECOND ELEVATOR PITCH - Concise, engaging, specific to the customer persona.

2. VALUE PROPOSITION - Clear, quantifiable value with ROI indicators.

3. KEY DIFFERENTIATORS (list 5) - Competitive advantages addressing the customer's pain points

4. OBJECTION HANDLERS - 3 common objections with persuasive responses

5. CALL-TO-ACTION - 2-3 specific next steps to move the deal forward

Avoid generic language. Be specific to the persona described."""

    output = call_groq(prompt)
    save_history(
        user_id=request.current_user.id, tool="pitch",
        input_data={"product": product, "customer": customer},
        output=output
    )
    return jsonify({"result": output})


@app.route("/lead_score", methods=["POST"])
@login_required
def lead_score():
    name    = request.form.get("name",    "").strip()
    budget  = request.form.get("budget",  "").strip()
    need    = request.form.get("need",    "").strip()
    urgency = request.form.get("urgency", "").strip()

    if not name or not budget or not need or not urgency:
        return jsonify({"result": "Error: Please fill in all fields."})

    prompt = f"""Perform a comprehensive lead qualification analysis and scoring.

Lead Name: {name}
Budget Information: {budget}
Business Need: {need}
Urgency Level: {urgency}

Please provide a detailed analysis with ALL of the following sections:

1. LEAD QUALIFICATION SCORE (0-100)
   - 90-100 = Hot Lead, 75-89 = Warm Lead, 60-74 = Lukewarm Lead, Below 60 = Cold Lead

2. SCORING BREAKDOWN
   - Budget Score (0-30), Need Score (0-30), Urgency Score (0-40), Total

3. DETAILED REASONING - Explain each score dimension

4. PROBABILITY OF CONVERSION - Percentage + explanation

5. RECOMMENDED NEXT ACTIONS - 4-5 specific steps for the sales team

6. OPTIMAL OUTREACH TIMING - Best timing and channel

Be specific and data-driven."""

    output = call_groq(prompt)
    save_history(
        user_id=request.current_user.id, tool="lead_score",
        input_data={"name": name, "budget": budget, "need": need, "urgency": urgency},
        output=output
    )
    return jsonify({"result": output})


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(debug=True)
