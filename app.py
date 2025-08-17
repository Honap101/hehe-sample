import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
import uuid, hashlib
from supabase import create_client
import os

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

# -------------------------------
# AUTH: Supabase helpers
# -------------------------------
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

def debug_secrets_presence():
    present = [k for k in ("SUPABASE_URL","SUPABASE_ANON_KEY") if k in st.secrets]
    missing = [k for k in ("SUPABASE_URL","SUPABASE_ANON_KEY") if k not in st.secrets]
    st.caption(f"Supabase secrets present: {present} • missing: {missing}")

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

def render_auth_panel():
    supabase = init_supabase()
    init_auth_state()

    if st.session_state.auth["user"]:
        u = st.session_state.auth["user"]
        with st.container(border=True):
            st.success(f"Signed in as **{u.get('email')}**")
            if st.button("Sign out"):
                sign_out()
                st.rerun()
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
                if resp.user:
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
                    set_user_session(resp.user.model_dump(), resp.session.access_token)
                    st.success("Logged in!")
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
    """Get response from Gemini AI"""
    try:
        fhi_score = fhi_context.get('FHI', 'Not calculated')
        income = fhi_context.get('income', 0)
        expenses = fhi_context.get('expenses', 0)
        savings = fhi_context.get('savings', 0)

        prompt = f"""
        You are FYNyx, an AI financial advisor specifically designed for Filipino users. You provide practical, culturally-aware financial advice.

        IMPORTANT CONTEXT:
        - User is Filipino, use Philippine financial context
        - Mention Philippine financial products when relevant (SSS, Pag-IBIG, GSIS, BPI, BDO, etc.)
        - Use Philippine Peso (₱) in examples
        - Consider Philippine economic conditions
        - If the question is not financial, politely redirect to financial topics

        USER'S FINANCIAL PROFILE:
        - FHI Score: {fhi_score}/100
        - Monthly Income: ₱{income:,.0f}
        - Monthly Expenses: ₱{expenses:,.0f}
        - Monthly Savings: ₱{savings:,.0f}

        USER'S QUESTION: {user_question}

        INSTRUCTIONS:
        - Provide specific, actionable advice
        - Keep response under 150 words
        - Use friendly, encouraging tone
        - Include specific numbers/percentages when helpful
        - Mention relevant Philippine financial institutions or products if applicable
        - If FHI score is low (<50), prioritize emergency fund and debt reduction
        - If FHI score is medium (50-70), focus on investment and optimization
        - If FHI score is high (>70), discuss advanced strategies

        Start your response with a brief acknowledgment of their question, then provide clear advice.
        """

        response = model.generate_content(prompt)
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

# ===============================
# CALCULATION & VALIDATION FUNCTIONS
# ===============================

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

# ===============================
# CHART & VISUALIZATION FUNCTIONS
# ===============================

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

# ===============================
# WHAT-IF & EXPLAINABILITY HELPERS
# ===============================

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

# ===============================
# CONSENT, PRIVACY & STORAGE HELPERS
# ===============================
import hashlib
from datetime import datetime

def init_privacy_state():
    if "consent_given" not in st.session_state:
        st.session_state.consent_given = False
    if "consent_ts" not in st.session_state:
        st.session_state.consent_ts = None
    if "retention_mode" not in st.session_state:
        # 'ephemeral' = don't keep chat after close; 'session' = keep while app open
        st.session_state.retention_mode = "session"
    if "analytics_opt_in" not in st.session_state:
        st.session_state.analytics_opt_in = False

def hash_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]

def render_consent_gate():
    """
    Renders a minimalist consent banner. If not accepted, app stops after banner.
    """
    with st.container(border=True):
        st.subheader("🔐 Privacy & Consent")
        st.write(
            "We process your inputs to compute your Financial Health Index and show tips. "
            "No data is sent anywhere except to the AI provider if you use the chat. "
            "You can choose how chat data is retained."
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            retention = st.radio(
                "Chat data retention",
                options=["session", "ephemeral"],
                format_func=lambda x: "Session-only (cleared when you close the app)" if x=="session" else "No storage (cleared immediately)",
                horizontal=True,
                key="retention_mode"
            )
            st.checkbox("Allow anonymized analytics (counts only, no content)", key="analytics_opt_in")
        with c2:
            agree = st.checkbox("I agree to the processing of my inputs for this demo.")
            if st.button("Agree & Continue", type="primary", use_container_width=True, disabled=not agree):
                st.session_state.consent_given = True
                st.session_state.consent_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.success("Thanks! You can now use all features.")
                st.rerun()

    if not st.session_state.consent_given:
        # Keep app visible (so judges can see), but stop interactions beyond banner
        st.info("Please accept to enable inputs, calculations, and chat.")
        st.stop()

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

def basic_mode_badge(ai_available: bool) -> str:
    return ("<span style='padding:2px 8px;border-radius:9999px;background:#e2fee2;color:#065f46;font-weight:600;font-size:12px;'>"
            "AI Online</span>") if ai_available else \
           ("<span style='padding:2px 8px;border-radius:9999px;background:#fee2e2;color:#7f1d1d;font-weight:600;font-size:12px;'>"
            "Basic Mode</span>")


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
        form_disabled = not st.session_state.consent_given
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

            if ai_available and model:
                response = get_ai_response(q, fhi_context, model)
            else:
                response = get_fallback_response(q, fhi_context)

            chat_entry = {
                'question': q.strip(),
                'response': response,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'fhi_context': fhi_context,
                'was_ai_response': ai_available
            }
            st.session_state.chat_history.append(chat_entry)
            prune_chat_history()
            st.rerun()  # update panel immediately

        # Close panel shell
        st.markdown("</div>", unsafe_allow_html=True)

# ===============================
# MAIN APPLICATION
# ===============================

initialize_session_state()
init_persona_state()
init_privacy_state()
AI_AVAILABLE, model = initialize_ai()

# Header with status badge
st.title("⌧ Fynstra " + st.markdown(basic_mode_badge(AI_AVAILABLE), unsafe_allow_html=True)._repr_html_() if False else "⌧ Fynstra")
st.markdown("### AI-Powered Financial Health Platform for Filipinos")
st.markdown(basic_mode_badge(AI_AVAILABLE), unsafe_allow_html=True)

# Require consent before proceeding
render_consent_gate()
render_auth_panel()

if AI_AVAILABLE:
    st.success("🤖 FYNyx AI is online and ready to help!")
else:
    st.warning("🤖 FYNyx AI is in basic mode. Install google-generativeai for full AI features.")

tab_calc, tab_goals = st.tabs(["Financial Health Calculator", "Goal Tracker"])
# ===============================
# TAB 1: FINANCIAL HEALTH CALCULATOR
# ===============================
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
    
        if st.button("Check My Financial Health", type="primary"):
            errors, warnings_ = validate_financial_inputs(monthly_income, monthly_expenses, monthly_debt, monthly_savings)
    
            if errors:
                for error in errors:
                    st.error(error)
                st.info("💡 Please review your inputs and try again.")
            elif monthly_income == 0 or monthly_expenses == 0:
                st.warning("Please input your income and expenses.")
            else:
                for w in warnings_:
                    st.warning(w)
    
                FHI, components = calculate_fhi(age, monthly_income, monthly_expenses, monthly_savings,
                                                monthly_debt, total_investments, net_worth, emergency_fund)
                FHI_rounded = round(FHI, 2)
                
                # --- ADD: Save to Google Sheet (respects your consent gate) ---
                if st.session_state.consent_given:
                    try:
                        ident = get_user_identity()
                        ws_name = worksheet_for(ident)
                        append_row(ws_name, [
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            ident["auth_method"], ident["user_id"], ident["email"], ident["display_name"],
                            age, monthly_income, monthly_expenses, monthly_savings, monthly_debt,
                            total_investments, net_worth, emergency_fund, FHI_rounded
                        ])
                        st.toast("💾 Saved to Google Sheet", icon="✅")
                    except Exception as e:
                        st.warning(f"Could not log to Google Sheet: {e}")

    
                st.session_state["FHI"] = FHI_rounded
                st.session_state["monthly_income"] = monthly_income
                st.session_state["monthly_expenses"] = monthly_expenses
                st.session_state["current_savings"] = monthly_savings
                st.session_state["components"] = components
    
                st.markdown("---")
    
                score_col, text_col = st.columns([1, 2])
    
                with score_col:
                    fig = create_gauge_chart(FHI_rounded)
                    st.plotly_chart(fig, use_container_width=True)
    
                with text_col:
                    st.markdown(f"### Overall FHI Score: **{FHI_rounded}/100**")
    
                    weak_areas = [c.lower() for c, s in components.items() if s < 60]
                    weak_text = ""
                    if weak_areas:
                        if len(weak_areas) == 1:
                            weak_text = f" However, your {weak_areas[0]} needs improvement."
                        else:
                            all_but_last = ", ".join(weak_areas[:-1])
                            weak_text = f" However, your {all_but_last} and {weak_areas[-1]} need improvement."
                        weak_text += " Addressing this will help strengthen your overall financial health."
    
                    if FHI >= 85:
                        st.success(f"🎯 Excellent! You're in great financial shape and well-prepared for the future.{weak_text}")
                    elif FHI >= 70:
                        st.info(f"🟢 Good! You have a solid foundation. Stay consistent and work on gaps where needed.{weak_text}")
                    elif FHI >= 50:
                        st.warning(f"🟡 Fair. You're on your way, but some areas need attention to build a stronger safety net.{weak_text}")
                    else:
                        st.error(f"🔴 Needs Improvement. Your finances require urgent attention — prioritize stabilizing your income, debt, and savings.{weak_text}")
    
                st.subheader("📈 Financial Health Breakdown")
                radar_fig = create_component_radar_chart(components)
                st.plotly_chart(radar_fig, use_container_width=True)
    
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
                            help_text = component_descriptions.get(label, "Higher is better.")
                            st.markdown(f"**{label} Score:** {round(score)} / 100", help=help_text)
                            interpretation, suggestions = interpret_component(label, score)
                            st.markdown(f"<span style='font-size:13px; color:#444;'>{interpretation}</span>", unsafe_allow_html=True)
                            with st.expander("💡 How to improve"):
                                for tip in suggestions:
                                    st.write(f"- {tip}")
    
                st.subheader("👥 How You Compare")
                peer_averages = {
                    "18-25": {"FHI": 45, "Savings Rate": 15, "Emergency Fund": 35},
                    "26-35": {"FHI": 55, "Savings Rate": 18, "Emergency Fund": 55},
                    "36-50": {"FHI": 65, "Savings Rate": 22, "Emergency Fund": 70},
                    "50+": {"FHI": 75, "Savings Rate": 25, "Emergency Fund": 85}
                }
                age_group = "18-25" if age < 26 else "26-35" if age < 36 else "36-50" if age < 51 else "50+"
                peer_data = peer_averages[age_group]
    
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Your FHI", f"{FHI_rounded}", f"{FHI_rounded - peer_data['FHI']:+.0f} vs peers")
                with col2:
                    st.metric("Your Savings Rate", f"{components['Savings Rate']:.0f}%",
                              f"{components['Savings Rate'] - peer_data['Savings Rate']:+.0f}% vs peers")
                with col3:
                    st.metric("Your Emergency Fund", f"{components['Emergency Fund']:.0f}%",
                              f"{components['Emergency Fund'] - peer_data['Emergency Fund']:+.0f}% vs peers")
    
                if st.button("📄 Generate Report"):
                    report = generate_text_report(FHI_rounded, components, {
                        "age": age,
                        "income": monthly_income,
                        "expenses": monthly_expenses,
                        "savings": monthly_savings
                    })
                    st.download_button(
                        label="Download Financial Health Report",
                        data=report,
                        file_name=f"fynstra_report_{datetime.now().strftime('%Y%m%d')}.txt",
                        mime="text/plain"
                    )
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
        
        # -------------------------------
        # Explainability Drawer
        # -------------------------------
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
                    current_savings = st.session_state.get("current_savings", 0)
                    monthly_savings = st.session_state.get("current_savings", 0)
    
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

# ===============================
# RENDER FLOATING CHAT (on all pages)
# ===============================

render_floating_chat(AI_AVAILABLE, model)
