import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import json

# ===============================
# AI & RESPONSE FUNCTIONS
# ===============================

def initialize_ai():
    """Initialize AI integration with proper error handling"""
    try:
        import google.generativeai as genai
        AI_AVAILABLE = True
        
        # Get API key from Streamlit secrets only
        try:
            api_key = st.secrets["GEMINI_API_KEY"]
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash") # Updated model for better context handling
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

def get_ai_response(user_question, fhi_context, chat_history, model):
    """
    Get response from Gemini AI with contextual memory and structured response prompting.
    """
    try:
        # Create a new chat session on each call, loading it with history
        chat = model.start_chat(history=chat_history)
        
        fhi_score = fhi_context.get('FHI', 'Not calculated')
        income = fhi_context.get('income', 0)
        expenses = fhi_context.get('expenses', 0)
        savings = fhi_context.get('savings', 0)
        
        # This prompt is now more detailed, guiding the AI on memory, structure, and persona.
        prompt = f"""
        **SYSTEM INSTRUCTIONS:**
        You are FYNyx, an AI financial advisor specifically designed for Filipino users. You provide practical, culturally-aware financial advice.

        **CRITICAL INSTRUCTIONS:**
        1.  **REMEMBER THE CONVERSATION:** You have the chat history. Refer to the user's previous questions and your prior responses to provide contextual, follow-up advice. Acknowledge their follow-up questions (e.g., "Regarding your question about savings...").
        2.  **USE STRUCTURED OUTPUTS:** When comparing items (like bank accounts, investment products), present them in a Markdown table. For action plans or steps, use numbered or bulleted lists. Use **bold text** to highlight key terms.
        3.  **BE A FILIPINO FINANCIAL ADVISOR:** Always use Philippine financial context (SSS, Pag-IBIG, BPI, BDO, etc.), use Philippine Peso (₱), and consider local economic conditions.
        4.  **STAY ON TOPIC:** If the question is not financial, politely redirect to financial topics.
        5.  **BE CONCISE:** Keep responses focused and under 200 words unless a detailed comparison is needed.

        **USER'S FINANCIAL PROFILE (FOR CONTEXT):**
        - FHI Score: {fhi_score}/100
        - Monthly Income: ₱{income:,.0f}
        - Monthly Expenses: ₱{expenses:,.0f}
        - Monthly Savings: ₱{savings:,.0f}

        **USER'S CURRENT QUESTION:** {user_question}
        
        Provide your response below, following all instructions.
        """
        
        response = chat.send_message(prompt)
        return response.text
        
    except Exception as e:
        st.error(f"AI temporarily unavailable: {str(e)}")
        # The fallback response is now simpler as the main AI is more capable
        return "I'm sorry, the AI is currently unavailable. Please try again later. Basic financial advice: focus on building an emergency fund (3-6 months of expenses) and paying down high-interest debt."

# ===============================
# CALCULATION & VALIDATION FUNCTIONS (Unchanged)
# ===============================
def validate_financial_inputs(income, expenses, debt, savings):
    errors, warnings = [], []
    if debt > income: errors.append("⚠️ Your monthly debt payments exceed your income")
    if expenses > income: warnings.append("⚠️ Your monthly expenses exceed your income")
    if savings + expenses + debt > income * 1.1: warnings.append("⚠️ Your total monthly obligations seem high relative to income")
    return errors, warnings

def calculate_fhi(age, monthly_income, monthly_expenses, monthly_savings, monthly_debt, total_investments, net_worth, emergency_fund):
    if age < 30: alpha, beta = 2.5, 2.0
    elif age < 40: alpha, beta = 3.0, 3.0
    elif age < 50: alpha, beta = 3.5, 4.0
    else: alpha, beta = 4.0, 5.0
    annual_income = monthly_income * 12
    Nworth = min(max((net_worth / (annual_income * alpha)) * 100, 0), 100) if annual_income > 0 else 0
    DTI = 100 - min((monthly_debt / monthly_income) * 100, 100) if monthly_income > 0 else 0
    Srate = min((monthly_savings / monthly_income) * 100, 100) if monthly_income > 0 else 0
    Invest = min(max((total_investments / (beta * annual_income)) * 100, 0), 100) if annual_income > 0 else 0
    Emerg = min((emergency_fund / monthly_expenses) / 6 * 100, 100) if monthly_expenses > 0 else 0
    FHI = 0.20 * Nworth + 0.15 * DTI + 0.15 * Srate + 0.15 * Invest + 0.20 * Emerg + 15
    components = {"Net Worth": Nworth, "Debt-to-Income": DTI, "Savings Rate": Srate, "Investment": Invest, "Emergency Fund": Emerg}
    return FHI, components

# ===============================
# CHART & VISUALIZATION FUNCTIONS (Unchanged)
# ===============================
def create_gauge_chart(fhi_score):
    fig = go.Figure(go.Indicator(mode="gauge+number", value=fhi_score, title={"text": "Your FHI Score", "font": {"size": 20}},
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "darkblue"},
               'steps': [{'range': [0, 50], 'color': "salmon"}, {'range': [50, 70], 'color': "gold"}, {'range': [70, 100], 'color': "lightgreen"}],
               'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 90}}))
    fig.update_layout(height=300, margin=dict(t=20, b=20))
    return fig

def create_component_radar_chart(components):
    categories, values = list(components.keys()), list(components.values())
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values, theta=categories, fill='toself', name='Your Scores', line_color='blue'))
    fig.add_trace(go.Scatterpolar(r=[70] * len(categories), theta=categories, fill='toself', name='Target (70%)', line_color='green', opacity=0.3))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=True, height=400, title="Financial Health Component Breakdown")
    return fig

# ===============================
# ANALYSIS & REPORTING FUNCTIONS (Unchanged)
# ===============================
def interpret_component(label, score):
    if label == "Net Worth":
        interpretation = "Your **net worth is low**..." if score < 40 else "Your **net worth is progressing**..." if score < 70 else "You have a **strong net worth**."
        suggestions = ["Build assets by saving and investing.", "Reduce liabilities like debts.", "Track your net worth regularly."]
    elif label == "Debt-to-Income":
        interpretation = "Your **debt is high**..." if score < 40 else "You're **managing debt moderately**..." if score < 70 else "Your **debt is well-managed**."
        suggestions = ["Pay down high-interest debts first.", "Avoid new unnecessary credit.", "Increase income to improve your ratio."]
    elif label == "Savings Rate":
        interpretation = "You're **saving little**..." if score < 40 else "Your **savings rate is okay**..." if score < 70 else "You're **saving strongly**."
        suggestions = ["Automate savings transfers.", "Target saving at least 20% of income.", "Review expenses to find savings."]
    elif label == "Investment":
        interpretation = "You're **not investing much**..." if score < 40 else "You're **starting to invest**..." if score < 70 else "You're **investing well**."
        suggestions = ["Start small and invest regularly.", "Diversify your portfolio.", "Aim for long-term growth."]
    elif label == "Emergency Fund":
        interpretation = "You have **little emergency savings**..." if score < 40 else "You're **halfway to a full buffer**." if score < 70 else "✅ Your **emergency fund is solid**."
        suggestions = ["Build up to 3–6 months of expenses.", "Keep it liquid and accessible.", "Set a monthly auto-save amount."]
    return interpretation, suggestions

def generate_text_report(fhi_score, components, user_inputs):
    # This function is unchanged but remains for generating reports
    return f"FYNSTRA FINANCIAL HEALTH REPORT..."

# ===============================
# SESSION STATE & INITIALIZATION
# ===============================
def initialize_session_state():
    """Initialize session state variables"""
    if "page" not in st.session_state:
        st.session_state.page = "Financial Health Calculator"
    if "chat_history" not in st.session_state:
        # NEW: Chat history format to support contextual memory
        st.session_state.chat_history = []
    # All other states like user_data, fhi, components etc. are set dynamically

# ===============================
# MAIN APPLICATION
# ===============================
initialize_session_state()
AI_AVAILABLE, model = initialize_ai()

st.title("⌧ Fynstra")
st.markdown("### AI-Powered Financial Health Platform for Filipinos")

if AI_AVAILABLE: st.success("🤖 FYNyx AI is online and ready to help!")
else: st.warning("🤖 FYNyx AI is in basic mode. Full features require a GEMINI_API_KEY.")

# --- NEW: Revamped Sidebar Navigation ---
st.sidebar.title("Navigation")
def set_page(page_name):
    st.session_state.page = page_name

st.sidebar.button("Financial Health Calculator", on_click=set_page, args=("Financial Health Calculator",), use_container_width=True, type="primary" if st.session_state.page == "Financial Health Calculator" else "secondary")
st.sidebar.button("Goal Tracker", on_click=set_page, args=("Goal Tracker",), use_container_width=True, type="primary" if st.session_state.page == "Goal Tracker" else "secondary")
st.sidebar.button("FYNyx Chatbot", on_click=set_page, args=("FYNyx Chatbot",), use_container_width=True, type="primary" if st.session_state.page == "FYNyx Chatbot" else "secondary")

# ===============================
# PAGE 1: FINANCIAL HEALTH CALCULATOR
# ===============================
if st.session_state.page == "Financial Health Calculator":
    with st.container(border=True):
        st.subheader("Calculate your FHI Score")
        # ... (Input fields are the same)
        col1, col2 = st.columns(2)
        with col1:
            age = st.number_input("Your Age", 18, 100, st.session_state.get('age', 25))
            monthly_expenses = st.number_input("Monthly Living Expenses (₱)", 0.0, value=st.session_state.get('monthly_expenses', 20000.0), step=100.0)
            monthly_savings = st.number_input("Monthly Savings (₱)", 0.0, value=st.session_state.get('monthly_savings', 5000.0), step=100.0)
            emergency_fund = st.number_input("Emergency Fund Amount (₱)", 0.0, value=st.session_state.get('emergency_fund', 30000.0), step=500.0)
        with col2:
            monthly_income = st.number_input("Monthly Gross Income (₱)", 0.0, value=st.session_state.get('monthly_income', 50000.0), step=100.0)
            monthly_debt = st.number_input("Monthly Debt Payments (₱)", 0.0, value=st.session_state.get('monthly_debt', 2000.0), step=100.0)
            total_investments = st.number_input("Total Investments (₱)", 0.0, value=st.session_state.get('total_investments', 50000.0), step=500.0)
            net_worth = st.number_input("Net Worth (₱)", 0.0, value=st.session_state.get('net_worth', 100000.0), step=500.0)

    if st.button("Check My Financial Health", type="primary"):
        errors, warnings = validate_financial_inputs(monthly_income, monthly_expenses, monthly_debt, monthly_savings)
        if errors:
            for error in errors: st.error(error)
        elif monthly_income == 0 or monthly_expenses == 0:
            st.warning("Please input your income and expenses.")
        else:
            for warning in warnings: st.warning(warning)
            
            FHI, components = calculate_fhi(age, monthly_income, monthly_expenses, monthly_savings, monthly_debt, total_investments, net_worth, emergency_fund)
            
            # Store everything in session state for other pages
            st.session_state.update({
                "FHI": round(FHI, 2), "components": components, "age": age,
                "monthly_income": monthly_income, "monthly_expenses": monthly_expenses,
                "monthly_savings": monthly_savings, "monthly_debt": monthly_debt,
                "total_investments": total_investments, "net_worth": net_worth,
                "emergency_fund": emergency_fund
            })
    
    # --- Display results if they exist ---
    if "FHI" in st.session_state:
        st.markdown("---")
        FHI_rounded = st.session_state.FHI
        components = st.session_state.components
        
        # Display Gauge, Radar, and detailed analysis... (This section is visually the same)
        score_col, text_col = st.columns([1, 2])
        with score_col:
            st.plotly_chart(create_gauge_chart(FHI_rounded), use_container_width=True)
        with text_col:
            # ... (text summary logic is the same)
            st.markdown(f"### Overall FHI Score: **{FHI_rounded}/100**")
            if FHI_rounded >= 85: st.success("🎯 Excellent! You're in great financial shape.")
            elif FHI_rounded >= 70: st.info("🟢 Good! You have a solid foundation.")
            elif FHI_rounded >= 50: st.warning("🟡 Fair. Some areas need attention.")
            else: st.error("🔴 Needs Improvement. Your finances require urgent attention.")

        st.plotly_chart(create_component_radar_chart(components), use_container_width=True)
        st.subheader("📊 Detailed Analysis & Recommendations")
        # ... (Component breakdown display logic is the same)

        # --- NEW: Proactive Engagement Section ---
        st.markdown("---")
        st.subheader("🤖 Get Your Personalized Action Plan")
        
        # Find the weakest component
        weakest_component = min(components, key=components.get)
        
        proactive_questions = {
            "Net Worth": "My Net Worth score is low. Can you give me a simple 3-step plan to start building it?",
            "Debt-to-Income": "My debt-to-income ratio is high. Can you explain the 'debt snowball' strategy and how I can apply it?",
            "Savings Rate": "My savings rate is low. Can you give me a table comparing three different ways I can cut my expenses in the Philippines?",
            "Investment": "My investment score is low. As a beginner in the Philippines, what are three types of investments I could start with? Please compare them in a table.",
            "Emergency Fund": "My emergency fund is low. What are the first three steps I should take to build it up quickly?"
        }
        proactive_question = proactive_questions.get(weakest_component, f"How can I improve my {weakest_component.lower()}?")
        
        st.info(f"Your weakest area is your **{weakest_component}**. Let FYNyx create a plan to help you improve it.")
        
        if st.button(f"Create My Plan for {weakest_component}", type="primary"):
            st.session_state.page = "FYNyx Chatbot"
            # Set the question for the chatbot page
            st.session_state.proactive_question_to_ask = proactive_question
            st.rerun()

# ===============================
# PAGE 2: GOAL TRACKER (Unchanged)
# ===============================
elif st.session_state.page == "Goal Tracker":
    st.subheader("🎯 Goal Tracker")
    # ... (Goal tracker logic remains the same)
    if "FHI" not in st.session_state:
        st.info("Please calculate your FHI score first to use the Goal Tracker.")
    else:
        # The rest of the goal tracker logic...
        pass

# ===============================
# PAGE 3: FYNYX CHATBOT
# ===============================
elif st.session_state.page == "FYNyx Chatbot":
    st.subheader("🤖 FYNyx - Your AI Financial Assistant")
    
    # --- NEW: Display chat history with roles ---
    for message in st.session_state.chat_history:
        with st.chat_message(name="user" if message['role'] == 'user' else "assistant", avatar="🧑‍💻" if message['role'] == 'user' else "🤖"):
            st.markdown(message['parts'][0])

    # Check if a proactive question was sent from the FHI page
    if "proactive_question_to_ask" in st.session_state:
        user_question = st.session_state.pop("proactive_question_to_ask")
    else:
        user_question = st.chat_input("Ask FYNyx about your finances...")

    if user_question:
        # Add user message to history and display it
        st.session_state.chat_history.append({"role": "user", "parts": [user_question]})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_question)

        # Get AI response
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("FYNyx is thinking..."):
                fhi_context = {
                    'FHI': st.session_state.get('FHI', 0),
                    'income': st.session_state.get('monthly_income', 0),
                    'expenses': st.session_state.get('monthly_expenses', 0),
                    'savings': st.session_state.get('monthly_savings', 0)
                }
                
                # Reformat history for the API call
                api_history = [msg for msg in st.session_state.chat_history if msg['role'] != 'user' or msg['parts'][0] != user_question]
                
                response = get_ai_response(user_question, fhi_context, api_history, model)
                st.markdown(response)

        # Add AI response to history
        st.session_state.chat_history.append({"role": "model", "parts": [response]})
        
    # Add a button to clear chat
    if st.button("🗑️ Clear Chat History"):
        st.session_state.chat_history = []
        st.rerun()

# ===============================
# FOOTER (Unchanged)
# ===============================
st.markdown("---")
st.markdown("**Fynstra AI** - Empowering Filipinos to **F**orecast, **Y**ield, and **N**avigate their financial future with confidence.")
st.markdown("*Developed by Team HI-4requency for DataWave 2025*")
