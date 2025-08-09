import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import time
import json

# ===============================
# PAGE CONFIGURATION
# ===============================
st.set_page_config(
    page_title="Fynstra - Your AI Financial Friend",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ===============================
# CUSTOM CSS FOR CHAT-FIRST DESIGN
# ===============================
st.markdown("""
<style>
    /* Make chat more prominent */
    .stChatInput {
        position: fixed;
        bottom: 0;
        background: white;
        z-index: 999;
        padding: 1rem;
        border-top: 2px solid #f0f0f0;
    }
    
    /* Dashboard cards styling */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    
    /* Smooth animations */
    @keyframes slideIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .animate-in {
        animation: slideIn 0.5s ease-out;
    }
</style>
""", unsafe_allow_html=True)

# ===============================
# SESSION STATE INITIALIZATION
# ===============================
def initialize_session_state():
    """Initialize all session state variables"""
    if 'conversation_stage' not in st.session_state:
        st.session_state.conversation_stage = 'greeting'
    
    if 'user_profile' not in st.session_state:
        st.session_state.user_profile = {}
    
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    if 'dashboard_revealed' not in st.session_state:
        st.session_state.dashboard_revealed = False
    
    if 'widgets_shown' not in st.session_state:
        st.session_state.widgets_shown = {
            'income': False,
            'expenses': False,
            'savings': False,
            'debt': False,
            'emergency': False,
            'fhi_score': False,
            'goals': False
        }
    
    if 'quick_insights' not in st.session_state:
        st.session_state.quick_insights = []
    
    if 'current_question' not in st.session_state:
        st.session_state.current_question = None
    
    if 'awaiting_response' not in st.session_state:
        st.session_state.awaiting_response = False

initialize_session_state()

# ===============================
# CHAT CONVERSATION FLOW
# ===============================
CONVERSATION_FLOW = {
    'greeting': {
        'message': "Hi! I'm FYNyx 👋 Your friendly financial companion. I'm here to help you understand your financial health - no judgment, just support!\n\nLet's start simple - **what's your first name?**",
        'next': 'get_name',
        'type': 'text'
    },
    'get_name': {
        'message': "Nice to meet you, {name}! 😊\n\nI'll ask you a few easy questions to understand your situation better. Don't worry if you don't know exact amounts - estimates are perfectly fine!\n\n**How much do you earn monthly? (in ₱)**",
        'next': 'get_income',
        'type': 'number',
        'widget': 'income'
    },
    'get_income': {
        'message': "₱{income:,.0f} monthly - that's great! You're earning more than {percentile}% of Filipino workers! 🎉\n\nNow, roughly **how much do you spend on expenses each month?** (rent, food, bills, etc.)",
        'next': 'get_expenses',
        'type': 'number',
        'widget': 'expenses',
        'insight': 'income_insight'
    },
    'get_expenses': {
        'message': "Got it! So you have about ₱{savings:,.0f} left each month. {savings_comment}\n\n**Do you have any monthly debt payments?** (loans, credit cards) - or just type 0 if none",
        'next': 'get_debt',
        'type': 'number',
        'widget': 'savings'
    },
    'get_debt': {
        'message': "{debt_comment}\n\n**How much do you have saved for emergencies?** (any amount is fine, even if it's 0 - we all start somewhere!)",
        'next': 'get_emergency',
        'type': 'number',
        'widget': 'debt'
    },
    'get_emergency': {
        'message': "{emergency_comment}\n\nBased on what you've shared, I've calculated your Financial Health Index (FHI)! 🎯\n\n**Would you like to see your personalized dashboard now?**",
        'next': 'reveal_dashboard',
        'type': 'confirm',
        'widget': 'emergency'
    },
    'reveal_dashboard': {
        'message': "Fantastic! Your dashboard is ready! 🎉\n\nYou can now:\n- See your FHI score and what it means\n- Track your progress with visual charts\n- Get personalized recommendations\n- Ask me anything about improving your finances\n\n**What would you like to explore first?**",
        'next': 'free_chat',
        'type': 'free',
        'widget': 'fhi_score'
    }
}

# ===============================
# HELPER FUNCTIONS
# ===============================
def calculate_income_percentile(income):
    """Calculate income percentile for Filipino context"""
    # Simplified percentile calculation based on Philippine income distribution
    if income < 10000: return 20
    elif income < 20000: return 40
    elif income < 30000: return 60
    elif income < 50000: return 75
    elif income < 75000: return 85
    elif income < 100000: return 92
    else: return 95

def get_savings_comment(savings):
    """Generate encouraging comment about savings"""
    if savings <= 0:
        return "That's quite tight! 😅 Don't worry, we'll work on optimizing your budget together."
    elif savings < 5000:
        return "Every peso saved counts! You're already doing better than many who live paycheck to paycheck."
    elif savings < 10000:
        return "That's a solid amount! You're building good financial habits."
    else:
        return "Impressive! You're saving well above average! 🌟"

def get_debt_comment(debt, income):
    """Generate comment about debt level"""
    if debt == 0:
        return "Excellent! No debt means more freedom for saving and investing! 🎉"
    elif debt / income < 0.2:
        return "Your debt is well-managed - under 20% of income is healthy!"
    elif debt / income < 0.4:
        return "Your debt is moderate. Let's work on strategies to reduce it faster."
    else:
        return "Your debt payments are quite high, but don't worry - we'll create a plan to tackle this!"

def get_emergency_comment(emergency, expenses):
    """Generate comment about emergency fund"""
    if emergency == 0:
        return "No emergency fund yet? No shame in that - 70% of Filipinos are in the same boat. Let's build one together!"
    elif emergency < expenses:
        return "You've started an emergency fund - that's great! Let's grow it to cover 3-6 months of expenses."
    elif emergency < expenses * 3:
        return "Good progress on your emergency fund! You're ahead of most people already."
    else:
        return "Excellent emergency fund! You're well-protected against unexpected events! 🛡️"

def calculate_simple_fhi(profile):
    """Calculate simplified FHI score"""
    income = profile.get('income', 0)
    expenses = profile.get('expenses', 0)
    debt = profile.get('debt', 0)
    emergency = profile.get('emergency', 0)
    
    if income == 0:
        return 0
    
    # Simple scoring components
    savings_rate_score = min(((income - expenses - debt) / income * 100), 40) if income > 0 else 0
    debt_score = max(40 - (debt / income * 100), 0) if income > 0 else 0
    emergency_score = min((emergency / (expenses * 6) * 100) * 0.2, 20) if expenses > 0 else 0
    
    return savings_rate_score + debt_score + emergency_score

# ===============================
# CHAT INTERFACE
# ===============================
def render_chat_interface():
    """Render the main chat interface"""
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.title("💬 Fynstra - Your Financial Journey Starts Here")
        
        # Chat container
        chat_container = st.container()
        
        with chat_container:
            # Display chat history
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
                    st.markdown(msg["content"])
            
            # Display current question if not already in history
            if st.session_state.current_question and not st.session_state.awaiting_response:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(st.session_state.current_question)
                st.session_state.awaiting_response = True
        
        # Chat input
        if st.session_state.conversation_stage != 'free_chat':
            user_input = st.chat_input("Type your answer here...")
            
            if user_input:
                # Add user message to history
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": user_input
                })
                
                # Process response based on stage
                process_user_response(user_input)
                st.session_state.awaiting_response = False
                st.rerun()
        else:
            user_question = st.chat_input("Ask me anything about your finances...")
            if user_question:
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": user_question
                })
                
                # Generate contextual response
                response = generate_ai_response(user_question)
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response
                })
                st.rerun()
    
    with col2:
        if st.session_state.dashboard_revealed:
            render_dashboard_widgets()
        else:
            render_progress_tracker()

# ===============================
# RESPONSE PROCESSING
# ===============================
def process_user_response(user_input):
    """Process user response and advance conversation"""
    current_flow = CONVERSATION_FLOW[st.session_state.conversation_stage]
    
    # Store response in profile
    if st.session_state.conversation_stage == 'get_name':
        st.session_state.user_profile['name'] = user_input
    elif current_flow['type'] == 'number':
        try:
            value = float(user_input.replace(',', '').replace('₱', '').strip())
            
            if st.session_state.conversation_stage == 'get_income':
                st.session_state.user_profile['income'] = value
                st.session_state.widgets_shown['income'] = True
            elif st.session_state.conversation_stage == 'get_expenses':
                st.session_state.user_profile['expenses'] = value
                st.session_state.user_profile['savings'] = st.session_state.user_profile['income'] - value
                st.session_state.widgets_shown['expenses'] = True
                st.session_state.widgets_shown['savings'] = True
            elif st.session_state.conversation_stage == 'get_debt':
                st.session_state.user_profile['debt'] = value
                st.session_state.widgets_shown['debt'] = True
            elif st.session_state.conversation_stage == 'get_emergency':
                st.session_state.user_profile['emergency'] = value
                st.session_state.widgets_shown['emergency'] = True
                # Calculate FHI when we have all data
                st.session_state.user_profile['fhi'] = calculate_simple_fhi(st.session_state.user_profile)
        except ValueError:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "I didn't quite catch that number. Could you type it again? (just the number, like 25000)"
            })
            return
    elif st.session_state.conversation_stage == 'reveal_dashboard':
        if 'yes' in user_input.lower() or 'sure' in user_input.lower() or 'ok' in user_input.lower():
            st.session_state.dashboard_revealed = True
            st.session_state.widgets_shown['fhi_score'] = True
    
    # Move to next stage
    next_stage = current_flow['next']
    st.session_state.conversation_stage = next_stage
    
    # Generate next message
    if next_stage in CONVERSATION_FLOW:
        next_flow = CONVERSATION_FLOW[next_stage]
        message = generate_contextual_message(next_flow['message'])
        
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": message
        })
        st.session_state.current_question = message

def generate_contextual_message(template):
    """Generate message with user context"""
    profile = st.session_state.user_profile
    
    # Calculate dynamic values
    income = profile.get('income', 0)
    expenses = profile.get('expenses', 0)
    savings = income - expenses
    debt = profile.get('debt', 0)
    emergency = profile.get('emergency', 0)
    
    # Generate contextual comments
    percentile = calculate_income_percentile(income)
    savings_comment = get_savings_comment(savings)
    debt_comment = get_debt_comment(debt, income) if income > 0 else ""
    emergency_comment = get_emergency_comment(emergency, expenses) if expenses > 0 else ""
    
    # Format message with context
    return template.format(
        name=profile.get('name', 'there'),
        income=income,
        expenses=expenses,
        savings=savings,
        debt=debt,
        emergency=emergency,
        percentile=percentile,
        savings_comment=savings_comment,
        debt_comment=debt_comment,
        emergency_comment=emergency_comment
    )

# ===============================
# DASHBOARD WIDGETS
# ===============================
def render_dashboard_widgets():
    """Render progressive dashboard widgets"""
    st.markdown("### 📊 Your Financial Dashboard")
    
    profile = st.session_state.user_profile
    
    # FHI Score (shows when revealed)
    if st.session_state.widgets_shown.get('fhi_score'):
        fhi = profile.get('fhi', 0)
        color = "🔴" if fhi < 40 else "🟡" if fhi < 70 else "🟢"
        st.metric("Financial Health Index", f"{color} {fhi:.0f}/100")
        
        # Progress bar
        st.progress(fhi / 100)
        
        if fhi < 40:
            st.info("💡 Room to grow! Let's work on building your financial foundation.")
        elif fhi < 70:
            st.info("💡 You're on track! A few tweaks will boost your score.")
        else:
            st.success("💡 Excellent financial health! You're doing great!")
    
    # Show widgets progressively
    if st.session_state.widgets_shown.get('income'):
        st.metric("💰 Monthly Income", f"₱{profile.get('income', 0):,.0f}")
    
    if st.session_state.widgets_shown.get('expenses'):
        st.metric("📊 Monthly Expenses", f"₱{profile.get('expenses', 0):,.0f}")
    
    if st.session_state.widgets_shown.get('savings'):
        savings = profile.get('savings', 0)
        savings_rate = (savings / profile.get('income', 1)) * 100 if profile.get('income', 0) > 0 else 0
        st.metric("💵 Monthly Savings", f"₱{savings:,.0f}", f"{savings_rate:.1f}% rate")
    
    if st.session_state.widgets_shown.get('debt'):
        debt = profile.get('debt', 0)
        debt_ratio = (debt / profile.get('income', 1)) * 100 if profile.get('income', 0) > 0 else 0
        st.metric("💳 Monthly Debt", f"₱{debt:,.0f}", f"{debt_ratio:.1f}% of income")
    
    if st.session_state.widgets_shown.get('emergency'):
        emergency = profile.get('emergency', 0)
        months_covered = emergency / profile.get('expenses', 1) if profile.get('expenses', 0) > 0 else 0
        st.metric("🛡️ Emergency Fund", f"₱{emergency:,.0f}", f"{months_covered:.1f} months")
    
    # Quick actions
    if st.session_state.dashboard_revealed:
        st.markdown("### 🎯 Quick Actions")
        if st.button("📈 Get Investment Tips"):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "What investment options should I consider?"
            })
            st.rerun()
        
        if st.button("💡 Improve My Score"):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "How can I improve my FHI score?"
            })
            st.rerun()
        
        if st.button("🎯 Set Financial Goals"):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "Help me set realistic financial goals"
            })
            st.rerun()

def render_progress_tracker():
    """Show conversation progress"""
    st.markdown("### 🚀 Your Progress")
    
    stages = ['Name', 'Income', 'Expenses', 'Debt', 'Emergency Fund', 'Dashboard']
    current_index = {
        'greeting': 0,
        'get_name': 0,
        'get_income': 1,
        'get_expenses': 2,
        'get_debt': 3,
        'get_emergency': 4,
        'reveal_dashboard': 5,
        'free_chat': 6
    }.get(st.session_state.conversation_stage, 0)
    
    for i, stage in enumerate(stages):
        if i < current_index:
            st.markdown(f"✅ {stage}")
        elif i == current_index:
            st.markdown(f"📍 **{stage}**")
        else:
            st.markdown(f"⏳ {stage}")
    
    # Motivation
    progress = (current_index / len(stages)) * 100
    st.progress(progress / 100)
    st.caption(f"{progress:.0f}% complete - You're doing great!")

# ===============================
# AI RESPONSE GENERATION
# ===============================
def generate_ai_response(question):
    """Generate contextual AI response"""
    profile = st.session_state.user_profile
    
    # Context-aware responses
    question_lower = question.lower()
    
    if 'improve' in question_lower and 'score' in question_lower:
        if profile.get('fhi', 0) < 40:
            return """Based on your FHI score, here are your top 3 priorities:

1. **Build Emergency Fund** 🛡️
   Start with ₱1,000/month until you reach ₱{expenses} (1 month of expenses)
   
2. **Reduce Debt** 💳
   Focus on highest interest debt first. Even ₱500 extra monthly makes a difference!
   
3. **Track Spending** 📊
   Use apps like Money Lover or just a notebook. Awareness is the first step!

Which one would you like to tackle first?""".format(expenses=profile.get('expenses', 10000))
        else:
            return "Your score is already good! Focus on increasing your savings rate and exploring investment options like FMETF or Pag-IBIG MP2."
    
    elif 'invest' in question_lower:
        income = profile.get('income', 0)
        if income < 30000:
            return """For beginners with your income level, I recommend:

1. **Pag-IBIG MP2** - Safe, 6-7% yearly, start with ₱500/month
2. **Digital banks** - Maya (6%), SeaBank (4.5%) for emergency funds
3. **FMETF** - Philippine stock index, start with ₱1,000 through brokers like COL Financial

Build your emergency fund first, then start with #1!"""
        else:
            return """With your income, you have great investment options:

1. **Emergency Fund** - 3-6 months in digital banks (Maya 6%, SeaBank 4.5%)
2. **Pag-IBIG MP2** - ₱5,000/month for guaranteed returns
3. **Stock Market** - 20% of savings in FMETF or blue chips
4. **Consider VUL** - If you also need insurance

What interests you most?"""
    
    elif 'goal' in question_lower:
        return """Let's set SMART financial goals! Based on your profile:

**Short-term (3-6 months):**
- Save ₱{target1:,.0f} for emergency fund
- Reduce expenses by 10%

**Medium-term (1 year):**
- Increase income by 20% (side hustle?)
- Start investing ₱{invest:,.0f}/month

**Long-term (3-5 years):**
- Build ₱{target2:,.0f} investment portfolio
- Create passive income stream

Which timeline excites you most?""".format(
    target1=profile.get('expenses', 10000) * 3,
    invest=max(profile.get('savings', 0) * 0.3, 1000),
    target2=profile.get('income', 30000) * 12
)
    
    else:
        return """Great question! Based on your financial profile:

Income: ₱{income:,.0f}
Savings Rate: {rate:.0f}%
FHI Score: {fhi:.0f}

I can help you with:
- Creating a budget that works
- Finding ways to save more
- Investment strategies for beginners
- Debt reduction plans
- Building emergency funds

What specific area would you like to explore?""".format(
    income=profile.get('income', 0),
    rate=(profile.get('savings', 0) / profile.get('income', 1) * 100) if profile.get('income', 0) > 0 else 0,
    fhi=profile.get('fhi', 0)
)

# ===============================
# MAIN APP LOGIC
# ===============================
def main():
    # Initialize first message
    if not st.session_state.chat_history and st.session_state.conversation_stage == 'greeting':
        first_message = CONVERSATION_FLOW['greeting']['message']
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": first_message
        })
        st.session_state.current_question = first_message
        st.session_state.conversation_stage = 'get_name'
    
    # Render the chat interface
    render_chat_interface()
    
    # Footer
    st.markdown("---")
    with st.expander("ℹ️ About Fynstra"):
        st.markdown("""
        **Fynstra** is your personal AI financial companion designed specifically for Filipinos.
        
        We make financial planning simple, friendly, and achievable - one conversation at a time.
        
        🔒 Your data is private and secure
        🎯 Personalized for Philippine context
        💬 Always here to help, no judgment
        
        *Built with ❤️ for DataWave 2025*
        """)

if __name__ == "__main__":
    main()
