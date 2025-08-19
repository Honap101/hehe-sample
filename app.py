import streamlit as st
import plotly.graph_objects as go
import json
import gspread
import os
import io
import time, random
import uuid, hashlib

from datetime import datetime
from supabase import create_client
from google.oauth2.service_account import Credentials

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics import renderPDF

st.set_page_config(page_title="Fynstra", page_icon="⌧", layout="wide")

# ===============================
# GOOGLE SHEETS HELPERS
# ===============================

@st.cache_resource
def init_sheets_client():
    sa_info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource
def open_sheet():
    return init_sheets_client().open_by_key(st.secrets["SHEET_ID"])

def append_row(worksheet_name: str, row: list):
    """Append a row to a worksheet; create the sheet and header if missing."""
    sh = open_sheet()
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=1000, cols=30)
        ws.append_row([
            "ts","auth_method","user_id","email","display_name",
            "age","income","expenses","savings","debt","investments","net_worth","emergency_fund","FHI"
        ])
    ws.append_row(row, value_input_option="USER_ENTERED")

# --- Minimal identity (guest for now; upgrade later when you add real sign-in) ---
def _anon_id():
    if "anon_id" not in st.session_state:
        st.session_state.anon_id = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:12]
    return st.session_state.anon_id

def get_user_identity():
    return {
        "auth_method": st.session_state.get("auth_method", "guest"),
        "user_id": st.session_state.get("user_id", _anon_id()),
        "email": st.session_state.get("email", None),
        "display_name": st.session_state.get("display_name", None),
    }

def worksheet_for(identity: dict) -> str:
    mapping = {
        "google": "Log_Google",
        "email": "Log_Email",
        "guest": "Log_Guests",
    }
    return mapping.get(identity["auth_method"], "Log_Others")

with st.expander("🔧 Google Sheets connectivity test"):
    if st.button("Ping Sheet"):
        try:
            sh = open_sheet()
            st.success(f"Connected to: {sh.title}")
            try:
                ws = sh.worksheet("Log_Guests")
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet("Log_Guests", rows=1000, cols=30)
                ws.append_row(["ts","note"])
            ws.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "hello 👋"], value_input_option="USER_ENTERED")
            st.info("Appended a test row to Log_Guests.")
        except Exception as e:
            st.error(f"Sheets error: {e}")
            st.caption("Hints: Did you share the Sheet with your service account as Editor? Are Sheets/Drive APIs enabled? Is the JSON in secrets with \\n in the private_key?")


SCORE_TARGET = 70
SCORE_BANDS = [(0, 50, "salmon"), (50, 70, "gold"), (70, 100, "lightgreen")]

def with_backoff(fn, tries: int = 4):
    """Run fn() with exponential backoff on transient errors."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep((2 ** i) + random.random())

def _dump_user(u):
    """Normalize Supabase user object → plain dict."""
    return u.model_dump() if hasattr(u, "model_dump") else dict(u)

def consent_required_or_stop():
    """Hard-stop if user hasn’t consented to processing."""
    if not st.session_state.get("consent_processing", False):
        st.warning("Please allow **Processing** in *Privacy & Consent* before running the calculator.")
        st.stop()

def append_row_safe(ws, row):
    with_backoff(lambda: ws.append_row(row, value_input_option="USER_ENTERED"))

CALCS_SHEET = "FHI_Calcs"
CHAT_EVENTS_SHEET = "Chat_Events"
WHATIF_SHEET = "WhatIf_Runs"   # optional

FHI_FORMULA_VERSION = "2025.02"
APP_VERSION = "0.9.0"

def fhi_band(score: float) -> str:
    if score < 50: return "Poor"
    if score < 70: return "Fair"
    if score < 85: return "Good"
    return "Excellent"

def compute_derived_metrics(mi, me, ms, md, inv, nw, ef) -> dict:
    """Derived KPIs to make logs more useful (rounded for readability)."""
    def r(x, n=2): 
        try: return round(float(x), n)
        except: return 0.0
    savings_rate_pct = r((ms/mi)*100, 1) if mi > 0 else 0.0
    dti_pct          = r((md/mi)*100, 1) if mi > 0 else 0.0
    months_efund     = r((ef/me), 2) if me > 0 else 0.0
    ef_target_months = 6
    ef_gap_amount    = r(max(0.0, ef_target_months*me - ef), 0)
    invest_to_inc    = r((inv/(mi*12))*100, 1) if mi > 0 else 0.0
    nwincome_x       = r((nw/(mi*12)), 2) if mi > 0 else 0.0
    return {
        "savings_rate_pct": savings_rate_pct,
        "dti_pct": dti_pct,
        "months_efund": months_efund,
        "efund_target_months": ef_target_months,
        "efund_gap_amount": ef_gap_amount,
        "invest_to_income_pct": invest_to_inc,
        "networth_to_income_x": nwincome_x,
    }

def _sheet_header(ws):
    try:
        return ws.row_values(1)
    except Exception:
        return []

def append_calc_log(FHI_rounded, components, inputs, warnings_list):
    """Write a detailed row into FHI_Calcs and store calc_id in session for joins."""
    if not st.session_state.get("consent_storage", False):
        return None  # respect user choice

    try:
        sh = open_sheet()
        ws = sh.worksheet(CALCS_SHEET)
        header = _sheet_header(ws)

        calc_id = uuid.uuid4().hex[:12]
        ident = get_user_identity()
        kpis = compute_derived_metrics(
            inputs["income"], inputs["expenses"], inputs["savings"], inputs["debt"],
            inputs["investments"], inputs["net_worth"], inputs["emergency_fund"]
        )

        row_map = {
            "calc_id": calc_id,
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "auth_method": ident["auth_method"],
            "user_id": ident["user_id"],
            "email": ident.get("email"),
            "display_name": ident.get("display_name"),
            "persona": st.session_state.get("persona_active"),
            "app_version": APP_VERSION,

            "consent_processing": st.session_state.get("consent_processing", False),
            "consent_storage": st.session_state.get("consent_storage", False),
            "consent_ai": st.session_state.get("consent_ai", False),
            "analytics_opt_in": st.session_state.get("analytics_opt_in", False),
            "consent_version": CONSENT_VERSION,
            "retention_mode": st.session_state.get("retention_mode", "session"),

            "age": inputs.get("age"),
            "monthly_income": inputs.get("income"),
            "monthly_expenses": inputs.get("expenses"),
            "monthly_savings": inputs.get("savings"),
            "monthly_debt": inputs.get("debt"),
            "total_investments": inputs.get("investments"),
            "net_worth": inputs.get("net_worth"),
            "emergency_fund": inputs.get("emergency_fund"),

            "FHI": FHI_rounded,
            "FHI_band": fhi_band(FHI_rounded),
            "NetWorth_component": round(components.get("Net Worth", 0), 1),
            "DTI_component": round(components.get("Debt-to-Income", 0), 1),
            "Savings_component": round(components.get("Savings Rate", 0), 1),
            "Invest_component": round(components.get("Investment", 0), 1),
            "Emergency_component": round(components.get("Emergency Fund", 0), 1),

            "savings_rate_pct": kpis["savings_rate_pct"],
            "dti_pct": kpis["dti_pct"],
            "months_efund": kpis["months_efund"],
            "efund_target_months": kpis["efund_target_months"],
            "efund_gap_amount": kpis["efund_gap_amount"],
            "invest_to_income_pct": kpis["invest_to_income_pct"],
            "networth_to_income_x": kpis["networth_to_income_x"],

            "warnings": " ; ".join(warnings_list) if warnings_list else "",
            "fhi_formula_version": FHI_FORMULA_VERSION,
        }

        append_row_safe(ws, [row_map.get(col, "") for col in header])
        st.session_state["last_calc_id"] = calc_id
        return calc_id
    except Exception as e:
        st.warning(f"Calc log error: {e}")
        return None

def classify_intent(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["emergency", "buffer", "rainy day"]): return "emergency_fund"
    if any(k in t for k in ["debt", "loan", "credit", "interest"]): return "debt"
    if any(k in t for k in ["invest", "stock", "fund", "bond", "mp2", "pera"]): return "investing"
    if any(k in t for k in ["save", "budget", "spend", "expense"]): return "savings_budget"
    if any(k in t for k in ["retire", "sss", "gsis"]): return "retirement"
    return "general"

def append_chat_event(calc_id: str, question: str, response: str, was_ai: bool, fhi_at_time: float):
    """Logs *only* metadata (no raw text) if analytics+storage are allowed."""
    if not (st.session_state.get("consent_storage", False) and st.session_state.get("analytics_opt_in", False)):
        return
    try:
        sh = open_sheet()
        ws = sh.worksheet(CHAT_EVENTS_SHEET)
        header = _sheet_header(ws)
        ident = get_user_identity()
        row_map = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": ident["user_id"],
            "auth_method": ident["auth_method"],
            "calc_id": calc_id or st.session_state.get("last_calc_id"),
            "FHI_at_time": fhi_at_time,
            "intent": classify_intent(question),
            "was_ai": bool(was_ai),
            "retention_mode": st.session_state.get("retention_mode", "session"),
            "len_question": len(question or ""),
            "len_response": len(response or ""),
        }
        append_row_safe(ws, [row_map.get(col, "") for col in header])
    except Exception as e:
        st.warning(f"Chat log error: {e}")

def append_whatif_run(name: str, base_fhi: float, new_fhi: float,
                      pct_deltas: dict, abs_deltas: dict):
    if not st.session_state.get("consent_storage", False):
        return
    try:
        sh = open_sheet()
        ws = sh.worksheet(WHATIF_SHEET)
        header = _sheet_header(ws)
        row_map = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": get_user_identity()["user_id"],
            "calc_id": st.session_state.get("last_calc_id"),
            "scenario_name": name,
            "base_FHI": round(base_fhi, 1),
            "scenario_FHI": round(new_fhi, 1),
            "delta_FHI": round(new_fhi - base_fhi, 1),
            "income_pct": pct_deltas.get("income_pct", 0),
            "expenses_pct": pct_deltas.get("expenses_pct", 0),
            "savings_pct": pct_deltas.get("savings_pct", 0),
            "debt_pct": pct_deltas.get("debt_pct", 0),
            "invest_pct": pct_deltas.get("invest_pct", 0),
            "efund_pct": pct_deltas.get("efund_pct", 0),
            "debt_abs_delta": abs_deltas.get("debt_abs_delta", 0),
            "savings_abs_delta": abs_deltas.get("savings_abs_delta", 0),
        }
        append_row_safe(ws, [row_map.get(col, "") for col in header])
        st.toast("Scenario saved", icon="✅")
    except Exception as e:
        st.warning(f"Scenario log error: {e}")

USERS_SHEET = "Users"
AUTH_EVENTS_SHEET = "Auth_Events"

def ensure_tables():
    sh = open_sheet()

    # Users table: 1 row per user
    try:
        sh.worksheet(USERS_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(USERS_SHEET, rows=2000, cols=30)
        ws.append_row([
            "user_id","email","username","created_at","last_login",
            # persisted profile fields
            "age","monthly_income","monthly_expenses","monthly_savings",
            "monthly_debt","total_investments","net_worth","emergency_fund",
            "last_FHI",
            # consent & prefs
            "consent_processing","consent_storage","consent_ai","analytics_opt_in",
            "consent_version","consent_ts"
        ])


    # Auth events log: append-only
    try:
        sh.worksheet(AUTH_EVENTS_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(AUTH_EVENTS_SHEET, rows=5000, cols=10)
        ws.append_row(["ts","event","user_id","email","username","note"])

    # Detailed calculation log (append-only, one row per calc)
    try:
        sh.worksheet(CALCS_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(CALCS_SHEET, rows=10000, cols=60)
        ws.append_row([
            # identity & meta
            "calc_id","ts","auth_method","user_id","email","display_name","persona","app_version",
            # consents snapshot
            "consent_processing","consent_storage","consent_ai","analytics_opt_in","consent_version","retention_mode",
            # inputs
            "age","monthly_income","monthly_expenses","monthly_savings","monthly_debt",
            "total_investments","net_worth","emergency_fund",
            # outputs
            "FHI","FHI_band","NetWorth_component","DTI_component","Savings_component","Invest_component","Emergency_component",
            # derived KPIs
            "savings_rate_pct","dti_pct","months_efund","efund_target_months","efund_gap_amount",
            "invest_to_income_pct","networth_to_income_x",
            # quality/flags
            "warnings","fhi_formula_version"
        ])

    # Chat analytics (privacy-minded, no raw text)
    try:
        sh.worksheet(CHAT_EVENTS_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(CHAT_EVENTS_SHEET, rows=20000, cols=20)
        ws.append_row([
            "ts","user_id","auth_method","calc_id","FHI_at_time","intent","was_ai",
            "retention_mode","len_question","len_response"
        ])

    # Optional: what-if scenarios
    try:
        sh.worksheet(WHATIF_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(WHATIF_SHEET, rows=10000, cols=30)
        ws.append_row([
            "ts","user_id","calc_id","scenario_name","base_FHI","scenario_FHI","delta_FHI",
            "income_pct","expenses_pct","savings_pct","debt_pct","invest_pct","efund_pct",
            "debt_abs_delta","savings_abs_delta"
        ])


@st.cache_data(show_spinner=False)
def _get_users_sheet_values():
    """Cached read to avoid frequent API calls; invalidated when we write."""
    sh = open_sheet()
    ws = sh.worksheet(USERS_SHEET)
    return ws.get_all_records()

def _invalidate_users_cache():
    _get_users_sheet_values.clear()

def log_auth_event(event: str, user: dict, note: str = ""):
    try:
        sh = open_sheet()
        ws = sh.worksheet(AUTH_EVENTS_SHEET)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            event,
            user.get("id"),
            user.get("email"),
            (user.get("user_metadata") or {}).get("username"),
            note
        ], value_input_option="USER_ENTERED")
    except Exception as e:
        st.warning(f"Auth log error: {e}")

def upsert_user_row(user: dict, payload: dict | None = None):
    """
    Create or update the Users row.
    `payload` can contain persisted profile fields (age, income, etc., last_FHI).
    """
    ensure_tables()
    payload = payload or {}
    try:
        sh = open_sheet()
        ws = sh.worksheet(USERS_SHEET)

        # Find by user_id
        values = ws.get_all_values()
        if not values:
            values = [[
                "user_id","email","username","created_at","last_login",
                "age","monthly_income","monthly_expenses","monthly_savings",
                "monthly_debt","total_investments","net_worth","emergency_fund",
                "last_FHI",
                "consent_processing","consent_storage","consent_ai","analytics_opt_in",
                "consent_version","consent_ts"
            ]]

        header = values[0]
        rows = values[1:]
        uid_idx = header.index("user_id") if "user_id" in header else None

        found_row_idx = None
        for i, row in enumerate(rows, start=2):  # 1-based header, data starts row 2
            if uid_idx is not None and len(row) > uid_idx and row[uid_idx] == user.get("id"):
                found_row_idx = i
                break

        # Build row dict from header
        base = {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "username": (user.get("user_metadata") or {}).get("username"),
        }
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if found_row_idx:
            update_map = {"last_login": now}
            update_map.update(payload)
            for k, v in update_map.items():
                if k in header:
                    ws.update_cell(found_row_idx, header.index(k) + 1, v)

        else:
            # new row with created_at + last_login
            base["created_at"] = now
            base["last_login"] = now
            base.update({
                "age": payload.get("age", ""),
                "monthly_income": payload.get("monthly_income", ""),
                "monthly_expenses": payload.get("monthly_expenses", ""),
                "monthly_savings": payload.get("monthly_savings", ""),
                "monthly_debt": payload.get("monthly_debt", ""),
                "total_investments": payload.get("total_investments", ""),
                "net_worth": payload.get("net_worth", ""),
                "emergency_fund": payload.get("emergency_fund", ""),
                "last_FHI": payload.get("last_FHI", ""),
            })
            row = [base.get(col, "") for col in header]
            ws.append_row(row, value_input_option="USER_ENTERED")

        _invalidate_users_cache()
    except Exception as e:
        st.warning(f"Users upsert error: {e}")

def load_user_profile_from_sheet(user_id: str) -> dict | None:
    try:
        rows = _get_users_sheet_values()
        for r in rows:
            if r.get("user_id") == user_id:
                keep = [
                    "age","monthly_income","monthly_expenses","monthly_savings",
                    "monthly_debt","total_investments","net_worth","emergency_fund",
                    "last_FHI",
                    # add consents & metadata
                    "consent_processing","consent_storage","consent_ai","analytics_opt_in",
                    "consent_version","consent_ts"
                ]
                return {k: r.get(k) for k in keep}
    except Exception as e:
        st.warning(f"Profile load error: {e}")
    return None



# ===============================
# AUTH: Supabase helpers
# ===============================
@st.cache_resource
def init_supabase():
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        missing = []
        if not url: missing.append("SUPABASE_URL")
        if not key: missing.append("SUPABASE_ANON_KEY")
        raise RuntimeError(
            f"Supabase credentials missing: {', '.join(missing)}. "
            "Add them to Streamlit secrets (or env vars) and restart."
        )
    return create_client(url, key)

def init_auth_state():
    if "auth" not in st.session_state:
        st.session_state.auth = {"user": None, "access_token": None}

def set_user_session(user, access_token=None):
    st.session_state.auth["user"] = user
    st.session_state.auth["access_token"] = access_token
    # Feed your existing identity pipe so Sheets logs include real users
    st.session_state["auth_method"] = "email"
    st.session_state["user_id"] = user.get("id")
    st.session_state["email"] = user.get("email")
    meta = (user.get("user_metadata") or {})
    st.session_state["display_name"] = meta.get("username") or user.get("email")

def sign_out():
    st.session_state.auth = {"user": None, "access_token": None}
    for k in ["auth_method","user_id","email","display_name"]:
        st.session_state.pop(k, None)

def set_guest_identity():
    # minimal guest identity
    st.session_state["auth_method"] = "guest"
    st.session_state["user_id"] = _anon_id()
    st.session_state["email"] = None
    st.session_state["display_name"] = "Guest"

def _bpi_gate_css():
    st.markdown("""
    <style>
      :root{
        /* BPI palette (accessible approximations) */
        --bpi-red:#9B1B30;      /* primary */
        --bpi-red-700:#7f1627;
        --bpi-gold:#C49A41;     /* accent */
        --bpi-gold-700:#9b7a33;
        --ink-900:#0f172a;      /* slate-900 */
        --ink-700:#334155;      /* slate-700 */
        --ink-600:#475569;
        --ink-500:#64748b;
        --line:#e5e7eb;
        --card:#ffffff;
        --chip:#f8fafc;
      }

      /* Background: subtle dual radial + top ribbon */
      .bpi-bg::before{
        content:"";
        position:fixed; inset:0; z-index:-1;
        background:
          radial-gradient(1000px 500px at 15% 10%, rgba(155,27,48,.09), transparent 60%),
          radial-gradient(900px 450px at 85% 90%, rgba(196,154,65,.10), transparent 55%),
          linear-gradient(180deg, #ffffff 0%, #ffffff 100%);
      }
      .block-container{padding-top:2rem !important;}

      .gate-shell{max-width:920px; margin:7vh auto;}
      .gate-card{
        background:var(--card);
        border:1px solid var(--line);
        border-radius:22px;
        padding:44px 52px;
        box-shadow:0 28px 80px rgba(15,23,42,.12), 0 6px 20px rgba(15,23,42,.06);
      }

      .gate-eyebrow{
        letter-spacing:.12em; text-transform:uppercase;
        font-size:.78rem; font-weight:700; color:var(--ink-500); margin-bottom:10px;
      }
      .gate-title{
        font-size:2.25rem; line-height:1.15; font-weight:800; margin:0 0 8px 0; color:var(--ink-900);
      }
      /* BPI gradient wordmark effect for “Fynstra” */
      .brand-accent{
        background:linear-gradient(90deg, var(--bpi-red) 0%, var(--bpi-gold) 100%);
        -webkit-background-clip:text; background-clip:text; color:transparent;
      }
      .gate-sub{color:var(--ink-600); font-size:1rem; max-width:58ch; margin-bottom:28px;}

      /* Buttons: pill styles with motion */
      .stButton>button{
        border-radius:9999px !important;
        padding:12px 18px !important;
        font-weight:700 !important;
        border:1px solid var(--line) !important;
        transition:transform .06s ease, box-shadow .2s ease, background-color .2s ease, border-color .2s ease;
      }
      .stButton>button:hover{ box-shadow:0 14px 30px rgba(15,23,42,.12); }
      .stButton>button:active{ transform:translateY(1px); }

      .btn-primary>button{
        background:var(--bpi-red) !important; color:#fff !important; border-color:var(--bpi-red) !important;
      }
      .btn-primary>button:hover{ background:var(--bpi-red-700) !important; border-color:var(--bpi-red-700) !important; }

      .btn-accent>button{
        background:var(--bpi-gold) !important; color:#1f2937 !important; border-color:var(--bpi-gold) !important;
      }
      .btn-accent>button:hover{ background:var(--bpi-gold-700) !important; border-color:var(--bpi-gold-700) !important; color:#111827 !important; }

      .btn-ghost>button{
        background:#fff !important; color:var(--ink-900) !important; border-color:var(--line) !important;
      }
      .btn-ghost>button:hover{ background:#f8fafc !important; }

      /* Feature mini-cards */
      .features{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:22px; }
      .feature{
        background:var(--chip); border:1px solid #e2e8f0; border-radius:14px; padding:14px 14px;
        display:flex; align-items:flex-start; gap:10px; min-height:64px;
      }
      .feature h4{ margin:0; font-weight:700; color:var(--ink-700); font-size:.98rem;}
      .feature p{ margin:2px 0 0 0; color:var(--ink-600); font-size:.88rem; line-height:1.2rem;}
      .ico{ width:22px; height:22px; flex:none; }

      .gate-foot{ margin-top:18px; color:var(--ink-500); font-size:.92rem; }
      .gate-foot a{ color:var(--ink-700); text-decoration:underline; }

      @media (max-width:900px){
        .gate-card{ padding:30px 22px; }
        .gate-title{ font-size:1.9rem; }
        .features{ grid-template-columns:1fr; }
      }
    </style>
    """, unsafe_allow_html=True)

def require_entry_gate():
    """
    BPI-themed entry gate: Log in (primary), Sign up (accent), Guest (ghost).
    Keeps your original logic, just upgrades the UI.
    """
    _bpi_gate_css()
    st.markdown("<div class='bpi-bg'></div>", unsafe_allow_html=True)

    init_auth_state()

    if st.session_state.auth.get("user"):
        st.session_state["entry_mode"] = "auth"
        return

    if "entry_mode" not in st.session_state:
        st.session_state.entry_mode = None

    if st.session_state.entry_mode is None:
        st.markdown("<div class='gate-shell'><div class='gate-card'>", unsafe_allow_html=True)
        st.markdown("<div class='gate-eyebrow'>Welcome</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='gate-title'>Welcome to <span class='brand-accent'>Fynstra</span></div>",
            unsafe_allow_html=True
        )
        st.markdown(
            "<div class='gate-sub'>AI-powered financial health for the Philippine context. "
            "Choose how you want to continue.</div>",
            unsafe_allow_html=True
        )

        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            st.markdown("<div class='btn-primary'>", unsafe_allow_html=True)
            if st.button("Log in", use_container_width=True, key="bpi_login"):
                st.session_state.entry_mode = "auth_login"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        with c2:
            st.markdown("<div class='btn-accent'>", unsafe_allow_html=True)
            if st.button("Sign up", use_container_width=True, key="bpi_signup"):
                st.session_state.entry_mode = "auth_signup"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        with c3:
            st.markdown("<div class='btn-ghost'>", unsafe_allow_html=True)
            if st.button("Continue as guest", use_container_width=True, key="bpi_guest"):
                st.session_state.entry_mode = "guest"
                set_guest_identity()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        # Feature mini-cards (SVG icons; no emojis)
        st.markdown("""
        <div class="features">
          <div class="feature">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="#9B1B30" stroke-width="1.8">
              <path d="M12 3l7 4v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V7l7-4z"/><path d="M9 12h6M9 9h6"/>
            </svg>
            <div><h4>Privacy-first onboarding</h4><p>Consent controls before any analysis or storage.</p></div>
          </div>
          <div class="feature">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="#C49A41" stroke-width="1.8">
              <path d="M3 6h18M3 18h18M7 6v12M17 6v12M12 6v12"/>
            </svg>
            <div><h4>Local context</h4><p>PH products, costs, and practical guidance.</p></div>
          </div>
          <div class="feature">
            <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="#9B1B30" stroke-width="1.8">
              <path d="M4 18v-7l5-2v9M14 18V9l6-2v11"/><circle cx="9" cy="8" r="1.5"/><circle cx="20" cy="6.5" r="1.5"/>
            </svg>
            <div><h4>Explainable scoring</h4><p>Transparent components and scenario testing.</p></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(
            "<div class='gate-foot'>By continuing, you agree to basic processing required to run the calculator. "
            "Data storage and AI sharing are optional and configurable in Privacy & Consent.</div>",
            unsafe_allow_html=True
        )
        st.markdown("</div></div>", unsafe_allow_html=True)  # /gate-card /gate-shell
        st.stop()

    if st.session_state.entry_mode in ("auth_login", "auth_signup", "auth"):
        st.markdown("<div class='gate-shell'><div class='gate-card'>", unsafe_allow_html=True)
        st.markdown("<div class='gate-eyebrow'>Account</div>", unsafe_allow_html=True)
        st.markdown("<div class='gate-title'>Access your account</div>", unsafe_allow_html=True)
        st.markdown("<div class='gate-sub'>Use your email to sign in or create a new account.</div>", unsafe_allow_html=True)

        render_auth_panel()

        st.divider()
        col = st.columns([1,1,1])[1]
        with col:
            st.caption("Prefer not to sign in?")
            st.markdown("<div class='btn-ghost'>", unsafe_allow_html=True)
            if st.button("Continue as guest", use_container_width=True, key="bpi_guest_from_auth"):
                st.session_state.entry_mode = "guest"
                set_guest_identity()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div></div>", unsafe_allow_html=True)
        st.stop()

    if st.session_state.entry_mode == "guest":
        return
        
def require_consent_gate():
    """
    Hard-stop the app until the user has submitted the privacy form at least once.
    'consent_ready' means they've clicked 'Save privacy preferences' (even if they opt-out of AI/storage).
    """
    init_privacy_state()  # make sure defaults are set and snapshot restore is applied

    # If the user is still on the auth flow (not logged in yet), let them finish auth first
    if st.session_state.get("entry_mode") in ("auth_login", "auth_signup") and not st.session_state.get("auth", {}).get("user"):
        # keep showing only the auth panel until done
        st.subheader("Account access")
        render_auth_panel()
        st.stop()

    # If consent has not been saved yet, show the form and block everything else
    if not st.session_state.get("consent_ready", False):
        st.title("Privacy & Consent")
        st.caption("Please review and save your preferences to continue.")
        render_consent_card()
        # If they didn’t submit yet, stop here
        st.info("Save your privacy preferences to continue.")
        st.stop()


def render_auth_panel():
    supabase = init_supabase()
    init_auth_state()

    if st.session_state.auth["user"]:
        u = st.session_state.auth["user"]
        with st.container(border=True):
            st.success(f"Signed in as **{u.get('email')}**")
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("Sign out"):
                    sign_out()
                    st.rerun()
            with c2:
                st.caption(f"User ID: `{st.session_state.get('user_id')}`")
    
        # ▼ Add this privacy section for logged-in users
        with st.expander("🔒 Privacy & data controls"):
            st.markdown("Download a copy of your data or delete your saved profile in Google Sheets.")
            export_my_data_ui()
    
            # small confirm gate for delete
            confirm = st.checkbox("I understand this will permanently delete my saved profile.")
            if confirm:
                forget_me_ui()
            else:
                st.caption("Check the box to enable deletion.")
    
        return


    st.markdown("### 🔐 Create an account or log in")
    tab_signup, tab_login = st.tabs(["Sign up", "Log in"])

    with tab_signup:
        with st.form("signup_form"):
            username = st.text_input("Username (display name)")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            try:
                resp = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {"data": {"username": username}}
                })
                # inside render_auth_panel() after successful SIGN UP:
                if resp.user:
                    u = resp.user.model_dump()
                    log_auth_event("signup", u)
                    # also create a Users row immediately
                    upsert_user_row(u, payload={})
                    st.success("Account created! Check your email to verify (if enabled), then log in.")
                else:
                    st.warning("Sign-up initiated. Check your email.")
            except Exception as e:
                st.error(f"Sign-up error: {e}")

    with tab_login:
        with st.form("login_form"):
            email_l = st.text_input("Email", key="login_email")
            password_l = st.text_input("Password", type="password", key="login_password")
            submitted_l = st.form_submit_button("Log in", type="primary")
        if submitted_l:
            try:
                resp = supabase.auth.sign_in_with_password({"email": email_l, "password": password_l})
                if resp.session and resp.user:
                    u = resp.user.model_dump()
                    set_user_session(u, resp.session.access_token)
                    log_auth_event("login", u)
                    # Try to load previously saved profile
                    saved = load_user_profile_from_sheet(u["id"])
                    if saved:
                        # Coerce numbers safely
                        def _num(x): 
                            try: return float(x)
                            except: return 0.0

                        for flag in ["consent_processing","consent_storage","consent_ai","analytics_opt_in"]:
                            if saved.get(flag) is not None and saved.get(flag) != "":
                                st.session_state[flag] = str(saved[flag]).lower() in ("true","1")
                    
                        if saved.get("consent_ts"):
                            st.session_state["consent_ts"] = saved["consent_ts"]

                        if saved.get("age"): st.session_state["persona_defaults"]["age"] = int(float(saved["age"]))
                        for k_src, k_dst in [
                            ("monthly_income","monthly_income"),
                            ("monthly_expenses","monthly_expenses"),
                            ("monthly_savings","current_savings"),
                            ("monthly_debt","monthly_debt"),
                            ("total_investments","total_investments"),
                            ("net_worth","net_worth"),
                            ("emergency_fund","emergency_fund"),
                        ]:
                            if saved.get(k_src) not in (None, ""):
                                st.session_state[k_dst] = _num(saved[k_src])
                                st.session_state.persona_defaults[k_src] = _num(saved[k_src])
                        if saved.get("last_FHI"):
                            try:
                                st.session_state["FHI"] = float(saved["last_FHI"])
                            except:
                                pass
                        st.toast("Loaded your saved profile from Google Sheet ✅", icon="✅")
                    else:
                        st.info("No saved profile yet. Calculate your FHI then click ‘Save profile’.")
                    st.rerun()

                else:
                    st.error("Login failed.")
            except Exception as e:
                st.error(f"Login error: {e}")


# ===============================
# AI & RESPONSE FUNCTIONS
# ===============================

def initialize_ai():
    """Initialize AI integration with proper error handling"""
    try:
        import google.generativeai as genai
        AI_AVAILABLE = True

        try:
            api_key = st.secrets["GEMINI_API_KEY"]
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            return True, model
        except KeyError:
            st.error("⚠️ GEMINI_API_KEY not found in Streamlit secrets")
            st.info("💡 Add your API key in the Secrets section of your Streamlit Cloud app")
            return False, None
        except Exception as e:
            st.error(f"AI configuration error: {str(e)}")
            return False, None

    except ImportError:
        st.warning("Google AI not available. Install with: pip install google-generativeai")
        return False, None

def get_ai_response(user_question, fhi_context, model):
    """Get response from Gemini AI (no artificial length limit)."""
    try:
        fhi_score = fhi_context.get('FHI', 'Not calculated')
        income = fhi_context.get('income', 0)
        expenses = fhi_context.get('expenses', 0)
        savings = fhi_context.get('savings', 0)

        prompt = f"""
        You are FYNyx, an AI financial advisor for Filipino users. Provide thorough, actionable,
        culturally-aware advice in Philippine context (₱, SSS, Pag-IBIG/MP2, GSIS, BPI/BDO, PERA, RTBs, etc.).

        CONTEXT SNAPSHOT
        - FHI Score: {fhi_score}/100
        - Monthly Income: ₱{income:,.0f}
        - Monthly Expenses: ₱{expenses:,.0f}
        - Monthly Savings: ₱{savings:,.0f}

        USER'S REQUEST
        {user_question}

        INSTRUCTIONS
        - Do NOT limit the length of your response—be as detailed as is genuinely helpful.
        - Use headings, bullets, and concrete peso amounts/percentages.
        - If FHI <50, emphasize liquidity and debt; 50–70 optimize; >70 advanced strategies.
        - Offer step-by-step actions, quick wins, and longer-term moves.
        - If you need to assume anything, state the assumption briefly.
        """

        # allow long outputs
        generation_cfg = {"max_output_tokens": 4096, "temperature": 0.7}
        response = model.generate_content(prompt, generation_config=generation_cfg)
        return response.text

    except Exception as e:
        st.error(f"AI temporarily unavailable: {str(e)}")
        return get_fallback_response(user_question, fhi_context)


def get_fallback_response(user_question, fhi_context):
    """Fallback responses when AI is unavailable"""
    question_lower = user_question.lower()
    fhi_score = fhi_context.get('FHI', 0)
    income = fhi_context.get('income', 0)
    expenses = fhi_context.get('expenses', 0)

    if not any(keyword in question_lower for keyword in ['money', 'save', 'invest', 'debt', 'financial', 'emergency', 'retirement', 'income', 'expense', 'fund', 'bank', 'loan']):
        return "I'm FYNyx, your financial advisor! While I can't help with non-financial questions, I'm here to assist with your financial health. Would you like to discuss savings strategies, investments, or debt management instead?"

    if "emergency" in question_lower:
        target_emergency = expenses * 6
        monthly_target = target_emergency / 12
        return f"Build an emergency fund of ₱{target_emergency:,.0f} (6 months of expenses). Save ₱{monthly_target:,.0f} monthly to reach this in a year. Keep it in a high-yield savings account like BPI or BDO."

    elif "debt" in question_lower:
        if fhi_score < 50:
            return "Focus on high-interest debt first (credit cards, personal loans). Pay minimums on everything, then put extra money toward the highest interest rate debt. Consider debt consolidation with lower rates."
        else:
            return "You're managing debt well! Continue current payments and avoid taking on new high-interest debt. Consider investing surplus funds."

    elif "invest" in question_lower or "investment" in question_lower:
        if income < 30000:
            return "Start small with ₱1,000/month in index funds like FMETF or mutual funds from BPI/BDO. Focus on emergency fund first, then gradually increase investments."
        else:
            return "Consider diversifying: 60% stocks (FMETF, blue chips like SM, Ayala), 30% bonds (government treasury), 10% alternative investments. Start with ₱5,000-10,000 monthly."

    elif "save" in question_lower or "savings" in question_lower:
        savings_rate = (fhi_context.get('savings', 0) / income * 100) if income > 0 else 0
        target_rate = 20
        if savings_rate < target_rate:
            needed_increase = (target_rate/100 * income) - fhi_context.get('savings', 0)
            return f"Your savings rate is {savings_rate:.1f}%. Aim for 20% (₱{target_rate/100 * income:,.0f}/month). Increase by ₱{needed_increase:,.0f} monthly through expense reduction or income increase."
        else:
            return f"Excellent {savings_rate:.1f}% savings rate! Consider automating transfers and exploring higher-yield options like time deposits or money market funds."

    elif "retirement" in question_lower:
        return "Maximize SSS contributions first, then add private retirement accounts. Aim to save 10-15% of income for retirement. Consider PERA (Personal Equity Retirement Account) for tax benefits."

    else:
        if fhi_score < 50:
            return "Focus on basics: emergency fund (3-6 months expenses), pay down high-interest debt, and track your spending. Build a solid foundation before investing."
        elif fhi_score < 70:
            return "You're on the right track! Optimize your budget, increase investments gradually, and consider insurance for protection. Review and adjust quarterly."
        else:
            return "Great financial health! Consider advanced strategies: real estate investment, business opportunities, or international diversification. Consult a certified financial planner."

# ===================================
# CALCULATION & VALIDATION FUNCTIONS
# ===================================

def validate_financial_inputs(income, expenses, debt, savings):
    errors = []
    warnings = []

    if debt > income:
        errors.append("⚠️ Your monthly debt payments exceed your income")

    if expenses > income:
        warnings.append("⚠️ Your monthly expenses exceed your income")

    if savings + expenses + debt > income * 1.1:
        warnings.append("⚠️ Your total monthly obligations seem high relative to income")

    return errors, warnings

def calculate_fhi(age, monthly_income, monthly_expenses, monthly_savings, monthly_debt,
                  total_investments, net_worth, emergency_fund):
    if age < 30:
        alpha, beta = 2.5, 2.0
    elif age < 40:
        alpha, beta = 3.0, 3.0
    elif age < 50:
        alpha, beta = 3.5, 4.0
    else:
        alpha, beta = 4.0, 5.0

    annual_income = monthly_income * 12

    Nworth = min(max((net_worth / (annual_income * alpha)) * 100, 0), 100) if annual_income > 0 else 0
    DTI = 100 - min((monthly_debt / monthly_income) * 100, 100) if monthly_income > 0 else 0
    Srate = min((monthly_savings / monthly_income) * 100, 100) if monthly_income > 0 else 0
    Invest = min(max((total_investments / (beta * annual_income)) * 100, 0), 100) if annual_income > 0 else 0
    Emerg = min((emergency_fund / monthly_expenses) / 6 * 100, 100) if monthly_expenses > 0 else 0

    FHI = 0.20 * Nworth + 0.15 * DTI + 0.15 * Srate + 0.15 * Invest + 0.20 * Emerg + 15

    components = {
        "Net Worth": Nworth,
        "Debt-to-Income": DTI,
        "Savings Rate": Srate,
        "Investment": Invest,
        "Emergency Fund": Emerg,
    }

    return FHI, components

# ================================
# CHART & VISUALIZATION FUNCTIONS
# ================================

def create_gauge_chart(fhi_score):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=fhi_score,
        title={"text": "Your FHI Score", "font": {"size": 20}},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, 50], 'color': "salmon"},
                {'range': [50, 70], 'color': "gold"},
                {'range': [70, 100], 'color': "lightgreen"}
            ],
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 90}
        }
    ))
    fig.update_layout(height=300, margin=dict(t=20, b=20))
    return fig

def create_component_radar_chart(components):
    categories = list(components.keys())
    values = list(components.values())

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values, theta=categories, fill='toself', name='Your Scores', line_color='blue'))
    fig.add_trace(go.Scatterpolar(r=[70] * len(categories), theta=categories, fill='toself',
                                  name='Target (70%)', line_color='green', opacity=0.3))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                      showlegend=True, height=400, title="Financial Health Component Breakdown")
    return fig

# ===============================
# ANALYSIS & REPORTING FUNCTIONS
# ===============================

# Brand palette (accessible approximations)
BPI_RED   = colors.HexColor("#9B1B30")
BPI_GOLD  = colors.HexColor("#C49A41")
INK_900   = colors.HexColor("#0f172a")
INK_700   = colors.HexColor("#334155")
INK_600   = colors.HexColor("#475569")
INK_500   = colors.HexColor("#64748b")
LINE      = colors.HexColor("#e5e7eb")
CHIP      = colors.HexColor("#f8fafc")

def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=INK_900,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            textColor=INK_600,
            spaceAfter=12,
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=INK_500,
            spaceAfter=4,
            uppercase=True
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14.5,
            leading=18,
            textColor=INK_900,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            textColor=INK_700,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=INK_500,
        ),
        "kpi": ParagraphStyle(
            "kpi",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=32,
            textColor=BPI_RED,
        ),
        "label": ParagraphStyle(
            "label",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            textColor=INK_700,
        ),
    }
    return styles

def _score_banner(fhi_score: float) -> Drawing:
    """Big score banner with BPI gradient bar."""
    d = Drawing(520, 70)
    # gradient substitute: two rects
    d.add(Rect(0, 0, 520, 70, fillColor=colors.white, strokeColor=LINE, strokeWidth=1, radius=10))
    d.add(Rect(0, 50, 520, 6, fillColor=BPI_RED, strokeColor=BPI_RED, strokeWidth=0))
    d.add(Rect(260, 50, 260, 6, fillColor=BPI_GOLD, strokeColor=BPI_GOLD, strokeWidth=0))
    title = String(16, 28, "Financial Health Index", fontName="Helvetica-Bold", fontSize=14, fillColor=INK_900)
    score = String(400, 22, f"{fhi_score:.1f} / 100", fontName="Helvetica-Bold", fontSize=22, fillColor=BPI_RED)
    d.add(title); d.add(score)
    return d

def _components_chart(components: dict) -> Drawing:
    """Horizontal bar chart for component scores (0-100)."""
    labels = list(components.keys())
    values = [float(components[k]) for k in labels]

    dw, dh = 520, 200
    d = Drawing(dw, dh)
    chart = HorizontalBarChart()
    chart.x = 70
    chart.y = 20
    chart.height = 160
    chart.width = 420
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 9.5
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 9
    chart.valueAxis.strokeColor = LINE
    chart.categoryAxis.strokeColor = LINE

    # bar styling
    chart.bars[0].fillColor = BPI_RED
    chart.bars[0].strokeColor = colors.white
    chart.barLabelFormat = "%0.0f"
    chart.barLabels.fontName = "Helvetica-Bold"
    chart.barLabels.fontSize = 9
    chart.barLabels.fillColor = INK_900
    d.add(chart)
    return d

def _kv_table(rows):
    t = Table(rows, colWidths=[140, 360])
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "Helvetica", 10),
        ("TEXTCOLOR", (0,0), (0,-1), INK_600),
        ("TEXTCOLOR", (1,0), (1,-1), INK_900),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, CHIP]),
        ("LINEBELOW", (0,0), (-1,-1), 0.25, LINE),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    return t

def build_fynstra_pdf(
    fhi_score: float,
    components: dict,
    user_inputs: dict,
    recommendations: list[str] | None = None,
    app_name: str = "Fynstra",
    org_name: str = "BPI"
) -> bytes:
    """
    Returns a BPI-themed PDF (bytes).
    `user_inputs` expects keys like: age, income, expenses, savings, debt, investments, net_worth, emergency_fund
    """

    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
        title=f"{app_name} Financial Health Report"
    )

    story = []

    # Header (eyebrow + title + subtitle)
    story.append(Paragraph("Report", styles["eyebrow"]))
    story.append(Paragraph(f"{app_name} — Financial Health Report", styles["title"]))
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} · {org_name} theme",
        styles["subtitle"]
    ))

    # Score banner
    story.append(_score_banner(fhi_score))
    story.append(Spacer(1, 10))

    # Profile snapshot
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=8, spaceAfter=12))
    story.append(Paragraph("Profile snapshot", styles["h2"]))

    rows = [
        ["Age", str(user_inputs.get("age", "N/A"))],
        ["Monthly Income (₱)", f"{user_inputs.get('income', 0):,.0f}"],
        ["Monthly Expenses (₱)", f"{user_inputs.get('expenses', 0):,.0f}"],
        ["Monthly Savings (₱)", f"{user_inputs.get('savings', 0):,.0f}"],
        ["Monthly Debt (₱)", f"{user_inputs.get('debt', 0):,.0f}"],
        ["Total Investments (₱)", f"{user_inputs.get('investments', 0):,.0f}"],
        ["Net Worth (₱)", f"{user_inputs.get('net_worth', 0):,.0f}"],
        ["Emergency Fund (₱)", f"{user_inputs.get('emergency_fund', 0):,.0f}"],
    ]
    story.append(_kv_table(rows))
    story.append(Spacer(1, 10))

    # Component breakdown
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=8, spaceAfter=12))
    story.append(Paragraph("Component breakdown", styles["h2"]))
    story.append(Paragraph(
        "Scores are normalized from 0 to 100. Higher is better. Bars show how you’re doing across Net Worth, Debt-to-Income, Savings Rate, Investment, and Emergency Fund.",
        styles["body"]
    ))
    story.append(_components_chart(components))
    story.append(Spacer(1, 10))

    # Optional recommendations
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=8, spaceAfter=12))
    story.append(Paragraph("Recommendations", styles["h2"]))
    if recommendations:
        for r in recommendations:
            story.append(Paragraph(f"• {r}", styles["body"]))
    else:
        story.append(Paragraph(
            "Focus on improving any components below 60%. Build liquidity first (Emergency Fund, Savings Rate), then lower debt, and grow investments for long-term resilience.",
            styles["body"]
        ))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This report is informational and does not constitute financial advice. For personalized planning, consult a licensed advisor.",
        styles["small"]
    ))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def interpret_component(label, score):
    if label == "Net Worth":
        interpretation = ("Your **net worth is low** relative to your income." if score < 40 else
                          "Your **net worth is progressing**, but still has room to grow." if score < 70 else
                          "You have a **strong net worth** relative to your income.")
        suggestions = ["Build your assets by saving and investing consistently.",
                       "Reduce liabilities such as debts and loans.",
                       "Track your net worth regularly to monitor growth."]
    elif label == "Debt-to-Income":
        interpretation = ("Your **debt is taking a big chunk of your income**." if score < 40 else
                          "You're **managing debt moderately well**, but aim to lower it further." if score < 70 else
                          "Your **debt load is well-managed**.")
        suggestions = ["Pay down high-interest debts first.",
                       "Avoid taking on new unnecessary credit obligations.",
                       "Increase income to improve your ratio."]
    elif label == "Savings Rate":
        interpretation = ("You're **saving very little** monthly." if score < 40 else
                          "Your **savings rate is okay**, but can be improved." if score < 70 else
                          "You're **saving consistently and strongly**.")
        suggestions = ["Automate savings transfers if possible.",
                       "Set a target of saving at least 20% of income.",
                       "Review expenses to increase what's saved."]
    elif label == "Investment":
        interpretation = ("You're **not investing much yet**." if score < 40 else
                          "You're **starting to invest**; try to boost it." if score < 70 else
                          "You're **investing well** and building wealth.")
        suggestions = ["Start small and invest regularly.",
                       "Diversify your portfolio for stability.",
                       "Aim for long-term investing over short-term speculation."]
    elif label == "Emergency Fund":
        interpretation = ("You have **less than 1 month saved** for emergencies." if score < 40 else
                          "You're **halfway to a full emergency buffer**." if score < 70 else
                          "✅ Your **emergency fund is solid**.")
        suggestions = ["Build up to 3–6 months of essential expenses.",
                       "Keep it liquid and easily accessible.",
                       "Set a monthly auto-save amount."]
    return interpretation, suggestions

def generate_text_report(fhi_score, components, user_inputs):
    report_text = f"""
FYNSTRA FINANCIAL HEALTH REPORT
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

OVERALL SCORE: {fhi_score:.1f}/100

COMPONENT BREAKDOWN:
- Net Worth Score: {components['Net Worth']:.1f}/100
- Debt-to-Income Score: {components['Debt-to-Income']:.1f}/100
- Savings Rate Score: {components['Savings Rate']:.1f}/100
- Investment Score: {components['Investment']:.1f}/100
- Emergency Fund Score: {components['Emergency Fund']:.1f}/100

USER PROFILE:
- Age: {user_inputs.get('age', 'N/A')}
- Monthly Income: ₱{user_inputs.get('income', 0):,.0f}
- Monthly Expenses: ₱{user_inputs.get('expenses', 0):,.0f}
- Monthly Savings: ₱{user_inputs.get('savings', 0):,.0f}

RECOMMENDATIONS:
Based on your FHI score, focus on improving areas scoring below 60%.
Visit app for detailed improvement suggestions.

---
Generated by Fynstra AI - Your Personal Financial Health Platform
"""
    return report_text

# =================================
# WHAT-IF & EXPLAINABILITY HELPERS
# =================================

def get_component_weights():
    # Match your FHI formula (sum(weights)=0.85; base bump=15)
    return {
        "Net Worth": 0.20,
        "Debt-to-Income": 0.15,
        "Savings Rate": 0.15,
        "Investment": 0.15,
        "Emergency Fund": 0.20,
        "_base": 15.0,  # constant bump
    }

def compute_fhi_from_inputs(age, monthly_income, monthly_expenses, monthly_savings,
                             monthly_debt, total_investments, net_worth, emergency_fund):
    """Wrapper so we can reuse your existing calculate_fhi() but return a nice dict"""
    FHI, components = calculate_fhi(
        age, monthly_income, monthly_expenses, monthly_savings,
        monthly_debt, total_investments, net_worth, emergency_fund
    )
    return FHI, components

def explain_fhi(components):
    """Return weighted contributions per component (excluding the constant base)."""
    w = get_component_weights()
    contrib = {k: round(v * w[k], 2) for k, v in components.items()}  # 0..100 * weight
    total_weighted = round(sum(contrib.values()), 2)
    return contrib, total_weighted, w["_base"]

def top_component_changes(old_components, new_components, k=2):
    """Identify the biggest movers for narrative explainability."""
    deltas = {k: round(new_components[k] - v, 1) for k, v in old_components.items()}
    sorted_up = sorted([x for x in deltas.items() if x[1] > 0], key=lambda x: -x[1])[:k]
    sorted_down = sorted([x for x in deltas.items() if x[1] < 0], key=lambda x: x[1])[:k]
    return sorted_up, sorted_down

# ===============================
# PERSONA PRESETS (ONBOARDING)
# ===============================

def init_persona_state():
    if "persona_active" not in st.session_state:
        st.session_state.persona_active = None
    if "persona_defaults" not in st.session_state:
        st.session_state.persona_defaults = {}

def get_persona_presets():
    # Tuned for quick demo realism (PH context)
    return {
        "Young Professional": {
            "age": 24,
            "monthly_income": 32000.0,
            "monthly_expenses": 21000.0,
            "monthly_savings": 3000.0,
            "monthly_debt": 2500.0,
            "total_investments": 5000.0,
            "net_worth": 20000.0,
            "emergency_fund": 10000.0,
        },
        "Young Family": {
            "age": 31,
            "monthly_income": 60000.0,
            "monthly_expenses": 45000.0,
            "monthly_savings": 5000.0,
            "monthly_debt": 7000.0,
            "total_investments": 30000.0,
            "net_worth": 150000.0,
            "emergency_fund": 40000.0,
        },
        "MSME Owner": {
            "age": 38,
            "monthly_income": 90000.0,
            "monthly_expenses": 65000.0,
            "monthly_savings": 8000.0,
            "monthly_debt": 12000.0,
            "total_investments": 120000.0,
            "net_worth": 450000.0,
            "emergency_fund": 90000.0,
        },
        "Pre-Retiree": {
            "age": 52,
            "monthly_income": 110000.0,
            "monthly_expenses": 70000.0,
            "monthly_savings": 15000.0,
            "monthly_debt": 4000.0,
            "total_investments": 800000.0,
            "net_worth": 1800000.0,
            "emergency_fund": 200000.0,
        },
    }

def apply_persona(preset_name):
    presets = get_persona_presets()
    data = presets.get(preset_name, {})
    st.session_state.persona_active = preset_name
    st.session_state.persona_defaults = data.copy()
    # Also prefill calculator context so FYNyx can use it immediately
    st.session_state["monthly_income"]   = data.get("monthly_income", 0.0)
    st.session_state["monthly_expenses"] = data.get("monthly_expenses", 0.0)
    st.session_state["current_savings"]  = data.get("monthly_savings", 0.0)

# ===================================
# CONSENT, PRIVACY & STORAGE HELPERS
# ===================================
CONSENT_VERSION = "v1"

def init_privacy_state():
    """
    Sticky + idempotent consent init.
    Uses one switch (consent_ready) and a snapshot dict to restore consents
    *before* any UI decides to show the consent card.
    """
    # First-run defaults (never overwrite existing values)
    defaults = {
        "consent_processing": False,
        "consent_storage": False,
        "consent_ai": False,
        "retention_mode": "session",
        "analytics_opt_in": False,
        "consent_given": False,
        "consent_ts": None,
        "consent_ready": False,           # <-- user has saved preferences at least once
        "__consent_snapshot": None,       # <-- last saved values
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # If the user already saved once, *force-restore* from the snapshot
    if st.session_state.get("consent_ready") and isinstance(st.session_state["__consent_snapshot"], dict):
        snap = st.session_state["__consent_snapshot"]
        # Force these to the last saved choices so reruns can't blank them
        st.session_state["consent_processing"] = bool(snap.get("consent_processing", True))
        st.session_state["consent_ai"]         = bool(snap.get("consent_ai", True))
        st.session_state["consent_storage"]    = bool(snap.get("consent_storage", False))
        st.session_state["retention_mode"]     = snap.get("retention_mode", "session")
        st.session_state["analytics_opt_in"]   = bool(snap.get("analytics_opt_in", False))
        st.session_state["consent_given"]      = True
        st.session_state["consent_ts"]         = snap.get("consent_ts", st.session_state["consent_ts"])

def save_user_consents(user_id_email_meta):
    user_stub = {
        "id": user_id_email_meta["id"],
        "email": user_id_email_meta.get("email"),
        "user_metadata": {"username": user_id_email_meta.get("display_name")}
    }
    upsert_user_row(user_stub, payload={
        "consent_processing": st.session_state.consent_processing,
        "consent_storage": st.session_state.consent_storage,
        "consent_ai": st.session_state.consent_ai,
        "analytics_opt_in": st.session_state.analytics_opt_in,
        "consent_version": CONSENT_VERSION,
        "consent_ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

def render_consent_card():
    with st.container(border=True):
        st.subheader("🔐 Privacy & Consent")
        st.write("Choose what you’re comfortable with. Refresh the page if you want to change your preferences")

        with st.form("privacy_form", clear_on_submit=False):
            c1, c2 = st.columns(2)

            with c1:
                # Bind directly to session_state via explicit keys
                st.checkbox(
                    "Allow processing to compute FHI (required)",
                    key="consent_processing",
                )
                st.checkbox(
                    "Allow saving my profile & calculations to Google Sheets",
                    key="consent_storage",
                )
                st.checkbox(
                    "Allow sending my questions/context to the AI provider",
                    key="consent_ai",
                )

            with c2:
                # Plain-language labels mapped to your existing internal values
                _retention_labels = {
                    "Keep recent chat (recommended)": "session",
                    "Only keep the last Q&A (privacy)": "ephemeral",
                }
                
                # Respect whatever is already in session_state to set the default label
                _current_internal = st.session_state.get("retention_mode", "session")
                _current_label = next((k for k, v in _retention_labels.items() if v == _current_internal),
                                      "Keep recent chat (recommended)")
                
                choice = st.radio(
                    "Chat history",
                    options=list(_retention_labels.keys()),
                    index=list(_retention_labels.keys()).index(_current_label),
                    horizontal=True,
                    help=(
                        "Controls only the chat panel in this app. "
                        "'Keep recent chat' shows your last few messages. "
                        "'Only keep the last Q&A' shows only your latest question and my reply."
                    ),
                )
                
                # Map the friendly label back to your original values used elsewhere
                st.session_state["retention_mode"] = _retention_labels[choice]
                
                # Extra clarity under the control
                st.caption("This doesn’t save anything to Google Sheets and doesn’t change what’s sent to the AI.")

                st.checkbox(
                    "Allow anonymized analytics (counts only)",
                    key="analytics_opt_in",
                )

            # Don't disable the button — validate after click
            submitted = st.form_submit_button("Save privacy preferences", type="primary")

        if submitted:
            if not st.session_state.get("consent_processing", False):
                st.error("You must allow processing to compute FHI.")
                return

            st.session_state.consent_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.consent_given = True
            
            # Sticky snapshot (source of truth on future reruns)
            st.session_state["__consent_snapshot"] = {
                "consent_processing": st.session_state.get("consent_processing", False),
                "consent_storage":    st.session_state.get("consent_storage", False),
                "consent_ai":         st.session_state.get("consent_ai", False),
                "retention_mode":     st.session_state.get("retention_mode", "session"),
                "analytics_opt_in":   st.session_state.get("analytics_opt_in", False),
                "consent_ts":         st.session_state.get("consent_ts"),
            }
            st.session_state["consent_ready"] = True  # <-- KEY: drives UI
            
            # Persist consents (save to Users sheet for both logged-in users and guests)
            identity = get_user_identity()
            user_stub = {
                "id": identity["user_id"],
                "email": identity.get("email"),
                "user_metadata": {"username": identity.get("display_name")},
            }
            save_user_consents({
                "id": identity["user_id"],
                "email": identity.get("email"),
                "display_name": identity.get("display_name"),
            })
            
            st.session_state.show_privacy = False
            st.success("Preferences saved")
            st.rerun()
            
def consent_ok() -> bool:
    """
    Use the sticky switch + snapshot to decide if features can run.
    This avoids flicker when live flags briefly read False during reruns.
    """
    if st.session_state.get("consent_ready") and isinstance(st.session_state.get("__consent_snapshot"), dict):
        snap = st.session_state["__consent_snapshot"]
        return bool(snap.get("consent_processing")) and bool(snap.get("consent_ai"))
    # Before first save, fall back to live flags
    return bool(st.session_state.get("consent_processing")) and bool(st.session_state.get("consent_ai"))


def hash_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]

def prune_chat_history():
    """
    Enforce retention policy:
      - ephemeral: keep only the latest exchange (for immediate UI), drop older
      - session: keep up to 50 messages
    """
    if "chat_history" not in st.session_state:
        return
    if st.session_state.retention_mode == "ephemeral":
        st.session_state.chat_history = st.session_state.chat_history[-2:]  # last Q/A at most
    else:
        st.session_state.chat_history = st.session_state.chat_history[-50:]

def export_my_data_ui():
    if not st.session_state.get("user_id"):
        return
    if st.button("📦 Export my data"):
        try:
            sh = open_sheet()
            users = sh.worksheet(USERS_SHEET).get_all_records()
            events = sh.worksheet(AUTH_EVENTS_SHEET).get_all_records()
            uid = st.session_state["user_id"]
            my_user = [r for r in users if r.get("user_id")==uid]
            my_events = [r for r in events if r.get("user_id")==uid]
            payload = json.dumps({"user": my_user, "events": my_events}, indent=2)
            st.download_button("Download JSON", data=payload, file_name="fynstra_export.json")
        except Exception as e:
            st.warning(f"Export failed: {e}")

def _delete_rows_by_uid(ws, uid: str, uid_col_name: str = "user_id"):
    """Delete all rows where uid_col_name equals uid (bottom-up to keep indices valid)."""
    vals = ws.get_all_values()
    if not vals:
        return 0
    header, rows = vals[0], vals[1:]
    if uid_col_name not in header:
        return 0
    uid_idx = header.index(uid_col_name)
    to_delete = [i + 2 for i, r in enumerate(rows) if len(r) > uid_idx and r[uid_idx] == uid]
    for row_idx in reversed(to_delete):
        with_backoff(lambda: ws.delete_rows(row_idx))
    return len(to_delete)

def _purge_user_everywhere(uid: str):
    """Best-effort removal of user across Users, Auth_Events, and log sheets."""
    sh = open_sheet()
    removed = {}
    # Primary profile table
    try:
        removed["Users"] = _delete_rows_by_uid(sh.worksheet(USERS_SHEET), uid)
    except Exception:
        removed["Users"] = 0
    # Auth events
    try:
        removed["Auth_Events"] = _delete_rows_by_uid(sh.worksheet(AUTH_EVENTS_SHEET), uid)
    except Exception:
        removed["Auth_Events"] = 0
    # Per-auth log sheets (guest/email/google/others)
    for name in ["Log_Guests", "Log_Email", "Log_Google", "Log_Others"]:
        try:
            removed[name] = _delete_rows_by_uid(sh.worksheet(name), uid)
        except Exception:
            removed[name] = 0
    return removed

def forget_me_ui():
    if not st.session_state.get("user_id"):
        return

    if st.button("🗑️ Delete my saved profile"):
        try:
            uid = st.session_state["user_id"]
            removed = _purge_user_everywhere(uid)

            # Reset local state (profile + scores)
            for k in [
                "persona_defaults", "FHI", "monthly_income", "monthly_expenses",
                "current_savings", "components", "email", "display_name"
            ]:
                st.session_state.pop(k, None)

            # Reset consent snapshot and gate so the user must review again
            st.session_state["__consent_snapshot"] = None
            st.session_state["consent_ready"] = False
            for flag in ["consent_processing","consent_storage","consent_ai","analytics_opt_in"]:
                st.session_state[flag] = False

            # Optional: sign out entirely (comment if you want to keep session)
            if "auth" in st.session_state:
                st.session_state.auth = {"user": None, "access_token": None}

            st.success(
                "Your data has been deleted from our Google Sheets logs and profile tables. "
                "You’ll be asked to review Privacy & Consent again next time."
            )
            with st.expander("Deletion details (dev)"):
                st.json(removed)

            st.rerun()

        except Exception as e:
            st.warning(f"Delete failed: {e}")

def basic_mode_badge(ai_available: bool) -> str:
    return ("<span style='padding:2px 8px;border-radius:9999px;background:#e2fee2;color:#065f46;font-weight:600;font-size:12px;'>"
            "AI Online</span>") if ai_available else \
           ("<span style='padding:2px 8px;border-radius:9999px;background:#fee2e2;color:#7f1d1d;font-weight:600;font-size:12px;'>"
            "Basic Mode</span>")

# ===============================
# Results flow (survives reruns)
# ===============================

def handle_calculation_click(
    age, monthly_income, monthly_expenses, monthly_savings,
    monthly_debt, total_investments, net_worth, emergency_fund
):
    """Runs validation, computes FHI, stores everything in session_state,
    and (optionally) logs to Sheets if the user allowed storage."""
    consent_required_or_stop()

    errors, warnings_ = validate_financial_inputs(
        monthly_income, monthly_expenses, monthly_debt, monthly_savings
    )
    if errors:
        for e in errors: st.error(e)
        st.info("💡 Please review your inputs and try again.")
        st.stop()

    if monthly_income == 0 or monthly_expenses == 0:
        st.warning("Please input your income and expenses.")
        st.stop()

    for w in warnings_:
        st.warning(w)

    # Compute
    FHI, components = calculate_fhi(
        age, monthly_income, monthly_expenses, monthly_savings,
        monthly_debt, total_investments, net_worth, emergency_fund
    )
    FHI_rounded = round(FHI, 2)

    # Persist for rerun-safe UI
    st.session_state["FHI"] = FHI_rounded
    st.session_state["components"] = components
    st.session_state["inputs_for_pdf"] = {
        "age": age,
        "income": monthly_income,
        "expenses": monthly_expenses,
        "savings": monthly_savings,
        "debt": monthly_debt,
        "investments": total_investments,
        "net_worth": net_worth,
        "emergency_fund": emergency_fund,
    }
    st.session_state["show_results"] = True

    # ---------- Optional: autosave profile for email-auth users ----------
    try:
        if st.session_state.get("auth_method") == "email" and st.session_state.get("user_id"):
            if st.session_state.get("consent_storage", False):
                user_stub = {
                    "id": st.session_state["user_id"],
                    "email": st.session_state.get("email"),
                    "user_metadata": {"username": st.session_state.get("display_name")},
                }
                upsert_user_row(user_stub, payload={
                    "age": age,
                    "monthly_income": monthly_income,
                    "monthly_expenses": monthly_expenses,
                    "monthly_savings": monthly_savings,
                    "monthly_debt": monthly_debt,
                    "total_investments": total_investments,
                    "net_worth": net_worth,
                    "emergency_fund": emergency_fund,
                    "last_FHI": FHI_rounded
                })
                st.toast("Autosaved profile to Google Sheet ✅", icon="✅")
                try:
                    log_auth_event("profile_autosaved", user_stub, note="Saved after calculation")
                except Exception:
                    pass
            else:
                st.caption("Autosave is off (you disabled storage).")
    except Exception as e:
        st.warning(f"Could not update profile: {e}")

    # ---------- Optional: append a calc log row if storage consent ----------
    try:
        if st.session_state.get("consent_storage", False):
            ident = get_user_identity()
            ws_name = worksheet_for(ident)
            sh = open_sheet()
            try:
                ws = sh.worksheet(ws_name)
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title=ws_name, rows=1000, cols=30)
                ws.append_row([
                    "ts","auth_method","user_id","email","display_name",
                    "age","income","expenses","savings","debt","investments",
                    "net_worth","emergency_fund","FHI"
                ], value_input_option="USER_ENTERED")
            append_row_safe(ws, [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ident["auth_method"], ident["user_id"], ident["email"], ident["display_name"],
                age, monthly_income, monthly_expenses, monthly_savings, monthly_debt,
                total_investments, net_worth, emergency_fund, FHI_rounded
            ])
            st.toast("💾 Saved to Google Sheet", icon="✅")
    except Exception as e:
        st.warning(f"Could not log to Google Sheet: {e}")


def _build_recommendations(components: dict) -> list[str]:
    """Simple rules that turn component gaps into bullets for the PDF."""
    recs = []
    if components.get("Emergency Fund", 0) < 60:
        recs.append("Increase cash buffer toward 3–6 months of expenses in a high-yield account.")
    if components.get("Debt-to-Income", 0) < 60:
        recs.append("Prioritize high-interest debt; target a DTI below 30%.")
    if components.get("Savings Rate", 0) < 20:
        recs.append("Aim to save at least 20% of monthly income via automated transfers.")
    if components.get("Investment", 0) < 50:
        recs.append("Start or increase regular contributions to diversified, low-cost funds.")
    if components.get("Net Worth", 0) < 50:
        recs.append("Track assets & liabilities monthly to steadily grow net worth.")
    return recs


def render_results_and_report_ui():
    if not (st.session_state.get("show_results") and
            "FHI" in st.session_state and "components" in st.session_state):
        return

    FHI_rounded = st.session_state["FHI"]
    components = st.session_state["components"]

    st.markdown("---")
    score_col, text_col = st.columns([1, 2])  # <- correct indent (fixes your error)

    with score_col:
        st.plotly_chart(create_gauge_chart(FHI_rounded), use_container_width=True)

    with text_col:
        st.markdown(f"### Overall FHI Score: **{FHI_rounded}/100**")

        weak_areas = [c.lower() for c, s in components.items() if s < 60]
        weak_text = ""
        if weak_areas:
            if len(weak_areas) == 1:
                weak_text = f" However, your {weak_areas[0]} needs improvement."
            else:
                weak_text = f" However, your {', '.join(weak_areas[:-1])} and {weak_areas[-1]} need improvement."
            weak_text += " Addressing this will help strengthen your overall financial health."

        if FHI_rounded >= 85:
            st.success(f"🎯 Excellent! You're in great financial shape and well-prepared for the future.{weak_text}")
        elif FHI_rounded >= 70:
            st.info(f"🟢 Good! You have a solid foundation. Stay consistent and work on gaps where needed.{weak_text}")
        elif FHI_rounded >= 50:
            st.warning(f"🟡 Fair. You're on your way, but some areas need attention to build a stronger safety net.{weak_text}")
        else:
            st.error(f"🔴 Needs Improvement. Your finances require urgent attention — prioritize stabilizing your income, debt, and savings.{weak_text}")

    st.subheader("📈 Financial Health Breakdown")
    st.plotly_chart(create_component_radar_chart(components), use_container_width=True)

    st.subheader("📊 Detailed Analysis & Recommendations")
    component_descriptions = {
        "Net Worth": "Your assets minus liabilities — shows your financial position. Higher is better.",
        "Debt-to-Income": "Proportion of income used to pay debts. Lower is better.",
        "Savings Rate": "How much of your income you save. Higher is better.",
        "Investment": "Proportion of assets invested for growth. Higher means better long-term potential.",
        "Emergency Fund": "Covers how well you're protected in financial emergencies. Higher is better."
    }

    col1, col2 = st.columns(2)
    for i, (label, score) in enumerate(components.items()):
        with (col1 if i % 2 == 0 else col2):
            with st.container(border=True):
                st.markdown(f"**{label} Score:** {round(score)} / 100",
                            help=component_descriptions.get(label, "Higher is better."))
                interpretation, suggestions = interpret_component(label, score)
                st.markdown(f"<span style='font-size:13px; color:#444;'>{interpretation}</span>",
                            unsafe_allow_html=True)
                with st.expander("💡 How to improve"):
                    for tip in suggestions:
                        st.write(f"- {tip}")

    # Simple “peer” metrics demo
    age = st.session_state.get("inputs_for_pdf", {}).get("age", 25)
    peer_averages = {
        "18-25": {"FHI": 45, "Savings Rate": 15, "Emergency Fund": 35},
        "26-35": {"FHI": 55, "Savings Rate": 18, "Emergency Fund": 55},
        "36-50": {"FHI": 65, "Savings Rate": 22, "Emergency Fund": 70},
        "50+":   {"FHI": 75, "Savings Rate": 25, "Emergency Fund": 85}
    }
    age_group = "18-25" if age < 26 else "26-35" if age < 36 else "36-50" if age < 51 else "50+"
    peer_data = peer_averages[age_group]

    c1, c2, c3 = st.columns(3)
    c1.metric("Your FHI", f"{FHI_rounded}", f"{FHI_rounded - peer_data['FHI']:+.0f} vs peers")
    c2.metric("Your Savings Rate", f"{components['Savings Rate']:.0f}%",
              f"{components['Savings Rate'] - peer_data['Savings Rate']:+.0f}% vs peers")
    c3.metric("Your Emergency Fund", f"{components['Emergency Fund']:.0f}%",
              f"{components['Emergency Fund'] - peer_data['Emergency Fund']:+.0f}% vs peers")

    # ---- Generate PDF ----
    if st.button("📄 Generate Report", key="gen_pdf"):
        recs = _build_recommendations(components)
        user_data = st.session_state.get("inputs_for_pdf", {})
        st.session_state.report_pdf = build_fynstra_pdf(
            st.session_state["FHI"], components, user_data,
            recommendations=recs, org_name="BPI"
        )
        st.success("Report generated. Use the button below to download.")

    if st.session_state.get("report_pdf"):
        st.download_button(
            label="⬇️ Download PDF report",
            data=st.session_state["report_pdf"],
            file_name=f"fynstra_report_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="dl_pdf",
        )

# ===============================
# SESSION STATE & INITIALIZATION
# ===============================

def initialize_session_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = {}
    if "calculation_history" not in st.session_state:
        st.session_state.calculation_history = []
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False
    if "user_question" not in st.session_state:
        st.session_state.user_question = ""
    if "auto_process_question" not in st.session_state:
        st.session_state.auto_process_question = False
    if "show_privacy" not in st.session_state:
        st.session_state.show_privacy = False
    if "report_pdf" not in st.session_state:
        st.session_state.report_pdf = None

# ===============================
# HELPER: FLOATING CHAT WIDGET
# ===============================

def render_floating_chat(ai_available, model):
    """
    Renders a bottom-right floating chat widget:
    - A FAB (floating action button) to open/close
    - A compact chat panel with history and input
    """
    # --- CSS for floating widget
    st.markdown("""
    <style>
      /* Floating container shell */
      .fynyx-fab-container {
        position: fixed;
        right: 20px;
        bottom: 20px;
        z-index: 9999;
      }
      .fynyx-fab-container .fab-btn button {
        border-radius: 9999px;
        padding: 10px 16px;
        font-weight: 600;
        box-shadow: 0 6px 16px rgba(0,0,0,0.15);
      }
      /* Chat panel */
      .fynyx-chat-panel {
        position: fixed;
        right: 20px;
        bottom: 80px;
        width: min(420px, 94vw);
        max-height: min(70vh, 680px);
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        box-shadow: 0 12px 30px rgba(0,0,0,0.18);
        overflow: hidden;
        z-index: 9999;
      }
      .fynyx-chat-header {
        padding: 10px 12px;
        background: #0f172a; /* slate-900 */
        color: #fff;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .fynyx-chat-body {
        padding: 10px 12px 8px 12px;
        max-height: 50vh;
        overflow-y: auto;
      }
      .fynyx-msg {
        margin: 8px 0;
        padding: 10px 12px;
        border-radius: 10px;
        font-size: 0.92rem;
        line-height: 1.3rem;
      }
      .fynyx-user { background: #eef2ff; align-self: flex-end; }
      .fynyx-bot { background: #f1f5f9; }
      .fynyx-chat-footer {
        padding: 8px 10px 12px 10px;
        border-top: 1px solid #e5e7eb;
        background: #fff;
      }
      .fynyx-meta {
        font-size: 0.74rem; color: #64748b; margin-top: 4px;
      }
      @media (max-width: 480px) {
        .fynyx-chat-panel { bottom: 70px; right: 10px; width: 94vw; }
      }
    </style>
    """, unsafe_allow_html=True)

    # --- Floating Action Button (FAB)
    fab_col = st.container()
    with fab_col:
        # We wrap Streamlit buttons in a container and rely on the CSS above to fix it
        fab_placeholder = st.empty()
        with fab_placeholder.container():
            cols = st.columns([1])  # minimal structure
            with cols[0]:
                open_label = "💬 Chat with FYNyx" if not st.session_state.chat_open else "✖ Close chat"
                if st.button(open_label, key="fyn_fab_btn", help="Ask about savings, investing, debt, etc."):
                    st.session_state.chat_open = not st.session_state.chat_open
        # Pin the container visually
        st.markdown("<div class='fynyx-fab-container'></div>", unsafe_allow_html=True)

    # --- Chat Panel
    if st.session_state.chat_open:
        # Visual shell for the panel
        st.markdown("<div class='fynyx-chat-panel'>", unsafe_allow_html=True)

        # Header
        status_html = basic_mode_badge(ai_available)
        st.markdown(
            f"<div class='fynyx-chat-header'>"
            f"<span>🤖 FYNyx — Financial Assistant</span>"
            f"<span style='font-size:12px;opacity:.95;'>{status_html}</span>"
            f"</div>",
            unsafe_allow_html=True
        )


        # Body: show last 10 messages
        body_container = st.container()
        with body_container:
            st.markdown("<div class='fynyx-chat-body'>", unsafe_allow_html=True)
            history = st.session_state.chat_history[-10:]
            if not history:
                st.caption("Start a conversation. FYNyx tailors answers using your FHI and inputs.")
            for chat in history:
                st.markdown(
                    f"<div class='fynyx-msg fynyx-user'><b>You:</b> {chat['question']}</div>",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"<div class='fynyx-msg fynyx-bot'><b>FYNyx:</b> {chat['response']}"
                    f"<div class='fynyx-meta'>"
                    f"{'🤖 AI' if chat.get('was_ai_response') else '🧠 Fallback'} • {chat['timestamp']}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            st.markdown("</div>", unsafe_allow_html=True)

        # Footer: input + actions
        st.markdown("<div class='fynyx-chat-footer'>", unsafe_allow_html=True)
        form_disabled = not consent_ok()

        with st.form(key="fyn_chat_form", clear_on_submit=True):
            q = st.text_input("Ask FYNyx", value="", placeholder="e.g., How can I build my emergency fund?", disabled=form_disabled)
            submitted = st.form_submit_button("Send", disabled=form_disabled)
        st.markdown("</div>", unsafe_allow_html=True)

        if submitted and q.strip():
            fhi_context = {
                'FHI': st.session_state.get('FHI', 0),
                'income': st.session_state.get('monthly_income', 0),
                'expenses': st.session_state.get('monthly_expenses', 0),
                'savings': st.session_state.get('current_savings', 0)
            }
        
            use_ai = st.session_state.get("consent_ai", False)
            if use_ai and ai_available and model:
                response = get_ai_response(q, fhi_context, model)
                was_ai = True
            else:
                response = get_fallback_response(q, fhi_context)
                was_ai = False
        
            st.session_state.chat_history.append({
                "question": q.strip(),
                "response": response,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fhi_context": fhi_context,
                "was_ai_response": was_ai,
            })
            try:
                append_chat_event(
                    calc_id=st.session_state.get("last_calc_id"),
                    question=q, response=response, was_ai=was_ai,
                    fhi_at_time=fhi_context.get("FHI", 0)
                )
            except Exception:
                pass

            prune_chat_history()
            st.rerun()

        # Close panel shell
        st.markdown("</div>", unsafe_allow_html=True)

# ===============================
# MAIN APPLICATION
# ===============================

initialize_session_state()
init_persona_state()
init_privacy_state()  # must run BEFORE any checks/UI

# stable guest id early
if "anon_id" not in st.session_state:
    st.session_state.anon_id = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:12]

AI_AVAILABLE, model = initialize_ai()

# 1) Entry (login/signup/guest) and 2) hard consent gate.
# These functions may render UI and call st.stop() as needed.
require_entry_gate()
require_consent_gate()

# ---- OPTIONAL: open the consent form as a settings page (only AFTER consent is ready)
if st.session_state.get("consent_ready", False):
    if st.button("⚙️ Privacy & consent settings"):
        st.session_state.show_privacy = True
        st.rerun()

    if st.session_state.get("show_privacy", False):
        st.title("🔐 Privacy & Consent")
        render_consent_card()
        st.stop()  # stop here so settings page stands alone on this run

# ---- From here on, we are past both gates
st.title("⌧ Fynstra")
st.markdown("### AI-Powered Financial Health Platform for Filipinos")
st.markdown(basic_mode_badge(AI_AVAILABLE), unsafe_allow_html=True)

try:
    ensure_tables()
except Exception as e:
    st.warning(f"Could not ensure Sheets tables yet: {e}")

if AI_AVAILABLE:
    st.success("🤖 FYNyx AI is online and ready to help!")
else:
    st.warning("🤖 FYNyx AI is in basic mode. Install google-generativeai for full AI features.")

tab_calc, tab_goals = st.tabs(["Financial Health Calculator", "Goal Tracker"])

# ===================================
# TAB 1: FINANCIAL HEALTH CALCULATOR
# ===================================
with tab_calc:
        with st.container(border=True):
            st.subheader("⚡ Quick Start: Choose a Persona (optional)")
            st.caption("Prefill realistic values so you can see insights immediately. You can still edit any field below.")
        
            presets = get_persona_presets()
            cols = st.columns(len(presets) + 1)
        
            # Render persona buttons
            for i, name in enumerate(presets.keys()):
                label = f"👤 {name}"
                if cols[i].button(label, key=f"persona_{name}"):
                    apply_persona(name)
                    st.success(f"Loaded preset: {name}")
                    st.rerun()
        
            # Clear button
            if cols[-1].button("↺ Clear preset", help="Reset to blank inputs"):
                st.session_state.persona_active = None
                st.session_state.persona_defaults = {}
                st.rerun()
        
            # Show active persona chip
            if st.session_state.persona_active:
                st.markdown(
                    f"**Active persona:** `{st.session_state.persona_active}` – values prefilled below. "
                    "Feel free to tweak anything."
                )
        with st.container(border=True):
            st.subheader("Calculate your FHI Score")
            st.markdown("Enter your financial details to get your personalized Financial Health Index score and recommendations.")
    
            # Use persona defaults when available
            pdft = st.session_state.persona_defaults  # shorthand
            
            col1, col2 = st.columns(2)
            with col1:
                age = st.number_input(
                    "Your Age",
                    min_value=18, max_value=100, step=1,
                    value=int(pdft.get("age", 25)),
                    help="Your current age in years."
                )
                monthly_expenses = st.number_input(
                    "Monthly Living Expenses (₱)",
                    min_value=0.0, step=50.0,
                    value=float(pdft.get("monthly_expenses", 0.0)),
                    help="E.g., rent, food, transportation, utilities."
                )
                monthly_savings = st.number_input(
                    "Monthly Savings (₱)",
                    min_value=0.0, step=50.0,
                    value=float(pdft.get("monthly_savings", 0.0)),
                    help="The amount saved monthly."
                )
                emergency_fund = st.number_input(
                    "Emergency Fund Amount (₱)",
                    min_value=0.0, step=500.0,
                    value=float(pdft.get("emergency_fund", 0.0)),
                    help="For medical costs, job loss, or other emergencies."
                )
            
            with col2:
                monthly_income = st.number_input(
                    "Monthly Gross Income (₱)",
                    min_value=0.0, step=100.0,
                    value=float(pdft.get("monthly_income", 0.0)),
                    help="Income before taxes and deductions."
                )
                monthly_debt = st.number_input(
                    "Monthly Debt Payments (₱)",
                    min_value=0.0, step=50.0,
                    value=float(pdft.get("monthly_debt", 0.0)),
                    help="Loans, credit cards, etc."
                )
                total_investments = st.number_input(
                    "Total Investments (₱)",
                    min_value=0.0, step=500.0,
                    value=float(pdft.get("total_investments", 0.0)),
                    help="Stocks, bonds, retirement accounts."
                )
                net_worth = st.number_input(
                    "Net Worth (₱)",
                    min_value=0.0, step=500.0,
                    value=float(pdft.get("net_worth", 0.0)),
                    help="Total assets minus total liabilities."
                )
    
        # Compute & persist results
        if st.button("Check My Financial Health", type="primary", key="calc"):
            handle_calculation_click(
                age=age,
                monthly_income=monthly_income,
                monthly_expenses=monthly_expenses,
                monthly_savings=monthly_savings,
                monthly_debt=monthly_debt,
                total_investments=total_investments,
                net_worth=net_worth,
                emergency_fund=emergency_fund,
            )
        
        # Always render (if present in session) so results survive reruns
        render_results_and_report_ui()

            
        # ===============================
        # WHAT-IF SANDBOX + EXPLAINABILITY
        # ===============================
        
        st.markdown("---")
        st.subheader("🧪 What-If Sandbox")
        
        with st.container(border=True):
            st.caption("Try scenarios and see how your score changes. Sliders adjust current inputs temporarily.")
        
            # --- Presets row (quick scenarios)
            c1, c2, c3, c4 = st.columns(4)
            preset = None
            if c1.button("📉 2-Month Job Loss"):
                preset = {"income_pct": -100, "expenses_pct": 0, "savings_pct": -100, "debt_pct": 0, "invest_pct": 0, "efund_pct": 0}
            if c2.button("📈 10% Salary Raise"):
                preset = {"income_pct": 10, "expenses_pct": 0, "savings_pct": 0, "debt_pct": 0, "invest_pct": 0, "efund_pct": 0}
            if c3.button("💳 +₱3k Debt Payment"):
                # model: same income/expenses, but increase 'monthly_debt' by -3000 (i.e., pay more so DTI improves).
                # For simplicity, treat as -3000 on debt payment ratio input (bounded to >=0).
                preset = {"income_pct": 0, "expenses_pct": 0, "savings_pct": 0, "debt_abs_delta": -3000, "invest_pct": 0, "efund_pct": 0}
            if c4.button("🏦 Start MP2 ₱1k/mo"):
                # Model as +1000 on monthly_savings and +1000/12*beta weight into investment grows slowly—keep simple: savings +1k
                preset = {"income_pct": 0, "expenses_pct": 0, "savings_abs_delta": 1000, "debt_pct": 0, "invest_pct": 0, "efund_pct": 0}
        
            # --- Sliders (percentage deltas)
            st.write("**Adjust inputs (vs current):**")
            s1, s2, s3 = st.columns(3)
            with s1:
                income_pct   = st.slider("Income Δ (%)", -30, 30, preset["income_pct"] if preset and "income_pct" in preset else 0, step=1)
                expenses_pct = st.slider("Expenses Δ (%)", -30, 30, preset["expenses_pct"] if preset and "expenses_pct" in preset else 0, step=1)
            with s2:
                savings_pct  = st.slider("Savings Δ (%)", -30, 30, preset["savings_pct"] if preset and "savings_pct" in preset else 0, step=1)
                debt_pct     = st.slider("Debt Payments Δ (%)", -30, 30, preset["debt_pct"] if preset and "debt_pct" in preset else 0, step=1)
            with s3:
                invest_pct   = st.slider("Total Investments Δ (%)", -30, 30, preset["invest_pct"] if preset and "invest_pct" in preset else 0, step=1)
                efund_pct    = st.slider("Emergency Fund Δ (%)", -30, 30, preset["efund_pct"] if preset and "efund_pct" in preset else 0, step=1)
        
            # Optional absolute overrides from presets (like debt −3000, savings +1000)
            debt_abs_delta    = preset.get("debt_abs_delta", 0) if preset else 0
            savings_abs_delta = preset.get("savings_abs_delta", 0) if preset else 0
        
            # --- Baseline (from current inputs)
            base_inputs = {
                "age": age,
                "income": monthly_income,
                "expenses": monthly_expenses,
                "savings": monthly_savings,
                "debt": monthly_debt,
                "invest": total_investments,
                "efund": emergency_fund,
                "networth": net_worth,
            }
        
            # --- Apply scenario deltas
            scen = {}
            scen["income"]   = max(0.0, base_inputs["income"]   * (1 + income_pct/100))
            scen["expenses"] = max(0.0, base_inputs["expenses"] * (1 + expenses_pct/100))
            # Savings can be % + absolute delta (from preset like MP2 +1k)
            scen["savings"]  = max(0.0, base_inputs["savings"]  * (1 + savings_pct/100) + savings_abs_delta)
            # Debt can be % + absolute delta (from preset like −3k)
            scen["debt"]     = max(0.0, base_inputs["debt"]     * (1 + debt_pct/100) + debt_abs_delta)
            scen["invest"]   = max(0.0, base_inputs["invest"]   * (1 + invest_pct/100))
            scen["efund"]    = max(0.0, base_inputs["efund"]    * (1 + efund_pct/100))
            scen["networth"] = base_inputs["networth"]  # keep net worth as-is unless you want to model it
        
            # --- Compute baseline & scenario FHIs
            base_fhi, base_comp = compute_fhi_from_inputs(
                base_inputs["age"], base_inputs["income"], base_inputs["expenses"], base_inputs["savings"],
                base_inputs["debt"], base_inputs["invest"], base_inputs["networth"], base_inputs["efund"]
            )
            new_fhi, new_comp = compute_fhi_from_inputs(
                base_inputs["age"], scen["income"], scen["expenses"], scen["savings"],
                scen["debt"], scen["invest"], scen["networth"], scen["efund"]
            )

            if st.button("💾 Save this scenario to Google Sheet"):
                append_whatif_run(
                    name="Custom scenario",
                    base_fhi=base_fhi, new_fhi=new_fhi,
                    pct_deltas={
                        "income_pct": income_pct, "expenses_pct": expenses_pct,
                        "savings_pct": savings_pct, "debt_pct": debt_pct,
                        "invest_pct": invest_pct, "efund_pct": efund_pct,
                    },
                    abs_deltas={"debt_abs_delta": debt_abs_delta, "savings_abs_delta": savings_abs_delta},
                )

            # --- Headline metrics
            c5, c6, c7 = st.columns(3)
            with c5:
                st.metric("Baseline FHI", f"{base_fhi:.1f}")
            with c6:
                st.metric("Scenario FHI", f"{new_fhi:.1f}", delta=f"{(new_fhi - base_fhi):+.1f}")
            with c7:
                # Simple liquidity proxy: Emergency Fund and Savings Rate movement
                st.metric("Liquidity Pulse (EF & Savings)", 
                          f"{new_comp['Emergency Fund']:.0f}% / {new_comp['Savings Rate']:.0f}%",
                          delta=f"{(new_comp['Emergency Fund']-base_comp['Emergency Fund']):+.0f}% / {(new_comp['Savings Rate']-base_comp['Savings Rate']):+.0f}%")
        
            # --- Component table (old vs new vs Δ)
            st.write("**Component changes:**")
            comp_rows = []
            for k in ["Net Worth", "Debt-to-Income", "Savings Rate", "Investment", "Emergency Fund"]:
                comp_rows.append({
                    "Component": k,
                    "Baseline": round(base_comp[k], 1),
                    "Scenario": round(new_comp[k], 1),
                    "Δ": round(new_comp[k] - base_comp[k], 1)
                })
            st.dataframe(comp_rows, use_container_width=True, hide_index=True)
        
            # --- Narrative: biggest movers
            up, down = top_component_changes(base_comp, new_comp, k=2)
            if up or down:
                bullets = []
                if up:
                    bullets.append("**Improved:** " + ", ".join([f"{k} ({v:+.1f})" for k, v in up]))
                if down:
                    bullets.append("**Declined:** " + ", ".join([f"{k} ({v:+.1f})" for k, v in down]))
                st.markdown(" • " + "\n • ".join(bullets))
        
        # Explainability
        with st.expander("🧠 How this score is computed (explainability)"):
            st.caption("We combine five component scores with fixed weights, plus a constant base score. Higher is better.")
            w = get_component_weights()
            st.latex(r"""
                \textbf{FHI} \;=\; 0.20\cdot NW \;+\; 0.15\cdot DTI \;+\; 0.15\cdot SR \;+\; 0.15\cdot INV \;+\; 0.20\cdot EF \;+\; 15
            """)
            st.write(f"**Weights:** Net Worth {int(w['Net Worth']*100)}%, Debt-to-Income {int(w['Debt-to-Income']*100)}%, "
                     f"Savings Rate {int(w['Savings Rate']*100)}%, Investment {int(w['Investment']*100)}%, "
                     f"Emergency Fund {int(w['Emergency Fund']*100)}%  •  **Base:** {w['_base']} points")
        
            # Baseline contributions
            base_contrib, base_weighted, base_const = explain_fhi(base_comp)
            scen_contrib, scen_weighted, _ = explain_fhi(new_comp)
        
            st.markdown("**Per-component weighted contributions (Baseline vs Scenario):**")
            rows = []
            for k in ["Net Worth", "Debt-to-Income", "Savings Rate", "Investment", "Emergency Fund"]:
                rows.append({
                    "Component": k,
                    "Baseline (weighted)": base_contrib[k],
                    "Scenario (weighted)": scen_contrib[k],
                    "Δ (weighted)": round(scen_contrib[k] - base_contrib[k], 2)
                })
            rows.append({
                "Component": "Constant Base",
                "Baseline (weighted)": base_const,
                "Scenario (weighted)": base_const,
                "Δ (weighted)": 0.0
            })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        
            st.caption("Rule of thumb: Liquidity (Emergency Fund, Savings Rate), Stability (DTI), Growth (Investment, Net Worth).")

# ===============================
# TAB 2: GOAL TRACKER
# ===============================
with tab_goals:
        st.subheader("🎯 Goal Tracker")
    
        if "FHI" not in st.session_state:
            st.info("Please calculate your FHI score first to use the Goal Tracker.")
            if st.button("Go to Calculator"):
                st.rerun()
        else:
            with st.container(border=True):
                st.markdown("Set and track your financial goals")
    
                col1, col2 = st.columns(2)
                with col1:
                    goal_amount = st.number_input("Savings Goal (₱)", min_value=0.0, step=1000.0)
                    goal_months = st.number_input("Time to Goal (months)", min_value=1, max_value=120, step=1)
    
                with col2:
                    current_savings = st.session_state.get("current_savings", 0.0)
                    monthly_savings = st.session_state.get("inputs_for_pdf", {}).get("savings", 0.0)
    
                    if goal_amount > 0 and goal_months > 0:
                        needed_monthly = (goal_amount - current_savings) / goal_months if goal_amount > current_savings else 0
                        progress = (current_savings / goal_amount) * 100 if goal_amount > 0 else 0
    
                        st.metric("Monthly Savings Needed", f"₱{needed_monthly:,.0f}")
                        st.metric("Current Progress", f"{progress:.1f}%")
    
                        if monthly_savings >= needed_monthly:
                            st.success("✅ You're on track!")
                        else:
                            shortfall = needed_monthly - monthly_savings
                            st.warning(f"⚠️ Increase savings by ₱{shortfall:,.0f}/month")

# ===============================
# FOOTER
# ===============================

st.markdown("---")
st.markdown("**Fynstra AI** - Empowering Filipinos to **F**orecast, **Y**ield, and **N**avigate their financial future with confidence.")
st.markdown("*Developed by Team HI-4requency for DataWave 2025*")

# ====================================
# RENDER FLOATING CHAT (on all pages)
# ====================================

render_floating_chat(AI_AVAILABLE, model)
# Small mode hint so users always know what will happen to their chat
_mode = st.session_state.get("retention_mode", "session")
_hint = ("Keeping recent chat until you close the tab."
         if _mode == "session"
         else "Showing only your latest Q&A for privacy.")
st.markdown(
    f"<div class='fynyx-meta' style='padding:6px 12px'>{_hint}</div>",
    unsafe_allow_html=True
)

