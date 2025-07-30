import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import json

# AI Integration
try:
    import google.generativeai as genai
    AI_AVAILABLE = True
    
    # Get API key from Streamlit secrets only
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
    except KeyError:
        st.error("⚠️ GEMINI_API_KEY not found in Streamlit secrets")
        st.info("💡 Add your API key in the Secrets section of your Streamlit Cloud app")
        AI_AVAILABLE = False
    except Exception as e:
        st.error(f"AI configuration error: {str(e)}")
        AI_AVAILABLE = False
        
except ImportError:
    AI_AVAILABLE = False
    st.warning("Google AI not available. Install with: pip install google-generativeai")

# Initialize session state
def initialize_session_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = {}
    if "calculation_history" not in st.session_state:
        st.session_state.calculation_history = []
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

def get_ai_response(user_question, fhi_context):
    """Get response from Gemini AI"""
    if not AI_AVAILABLE:
        return get_fallback_response(user_question, fhi_context)
    
    try:
        # Create detailed prompt with user context
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
    
    # Handle non-financial questions
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

def validate_financial_inputs(income, expenses, debt, savings):
    """Validate user financial inputs"""
    errors = []
    warnings = []
    
    if debt > income:
        errors.append("⚠️ Your monthly debt payments exceed your income")
    
    if expenses > income:
        warnings.append("⚠️ Your monthly expenses exceed your income")
    
    if savings + expenses + debt > income * 1.1:  # Allow 10% buffer
        warnings.append("⚠️ Your total monthly obligations seem high relative to income")
    
    return errors, warnings

def calculate_fhi(age, monthly_income, monthly_expenses, monthly_savings, monthly_debt, 
                  total_investments, net_worth, emergency_fund):
    """Calculate Financial Health Index and component scores"""
    
    # Age-based target multipliers
    if age < 30:
        alpha, beta = 2.5, 2.0
    elif age < 40:
        alpha, beta = 3.0, 3.0
    elif age < 50:
        alpha, beta = 3.5, 4.0
    else:
        alpha, beta = 4.0, 5.0

    annual_income = monthly_income * 12

    # Sub-scores
    Nworth = min(max((net_worth / (annual_income * alpha)) * 100, 0), 100) if annual_income > 0 else 0
    DTI = 100 - min((monthly_debt / monthly_income) * 100, 100) if monthly_income > 0 else 0
    Srate = min((monthly_savings / monthly_income) * 100, 100) if monthly_income > 0 else 0
    Invest = min(max((total_investments / (beta * annual_income)) * 100, 0), 100) if annual_income > 0 else 0
    Emerg = min((emergency_fund / monthly_expenses) / 6 * 100, 100) if monthly_expenses > 0 else 0

    # Final FHI Score
    FHI = 0.20 * Nworth + 0.15 * DTI + 0.15 * Srate + 0.15 * Invest + 0.20 * Emerg + 15
    
    components = {
        "Net Worth": Nworth,
        "Debt-to-Income": DTI,
        "Savings Rate": Srate,
        "Investment": Invest,
        "Emergency Fund": Emerg,
    }
    
    return FHI, components

def create_gauge_chart(fhi_score):
    """Create FHI gauge chart"""
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
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))
    fig.update_layout(height=300, margin=dict(t=20, b=20))
    return fig

def create_component_radar_chart(components):
    """Create radar chart for component breakdown"""
    categories = list(components.keys())
    values = list(components.values())
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name='Your Scores',
        line_color='blue'
    ))
    
    fig.add_trace(go.Scatterpolar(
        r=[70] * len(categories),  # Target scores
        theta=categories,
        fill='toself',
        name='Target (70%)',
        line_color='green',
        opacity=0.3
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100])
        ),
        showlegend=True,
        height=400,
        title="Financial Health Component Breakdown"
    )
    
    return fig

def interpret_component(label, score):
    """Provide interpretation and suggestions for each component"""
    if label == "Net Worth":
        interpretation = (
            "Your **net worth is low** relative to your income." if score < 40 else
            "Your **net worth is progressing**, but still has room to grow." if score < 70 else
            "You have a **strong net worth** relative to your income."
        )
        suggestions = [
            "Build your assets by saving and investing consistently.",
            "Reduce liabilities such as debts and loans.",
            "Track your net worth regularly to monitor growth."
        ]
    elif label == "Debt-to-Income":
        interpretation = (
            "Your **debt is taking a big chunk of your income**." if score < 40 else
            "You're **managing debt moderately well**, but aim to lower it further." if score < 70 else
            "Your **debt load is well-managed**."
        )
        suggestions = [
            "Pay down high-interest debts first.",
            "Avoid taking on new unnecessary credit obligations.",
            "Increase income to improve your ratio."
        ]
    elif label == "Savings Rate":
        interpretation = (
            "You're **saving very little** monthly." if score < 40 else
            "Your **savings rate is okay**, but can be improved." if score < 70 else
            "You're **saving consistently and strongly**."
        )
        suggestions = [
            "Automate savings transfers if possible.",
            "Set a target of saving at least 20% of income.",
            "Review expenses to increase what's saved."
        ]
    elif label == "Investment":
        interpretation = (
            "You're **not investing much yet**." if score < 40 else
            "You're **starting to invest**; try to boost it." if score < 70 else
            "You're **investing well** and building wealth."
        )
        suggestions = [
            "Start small and invest regularly.",
            "Diversify your portfolio for stability.",
            "Aim for long-term investing over short-term speculation."
        ]
    elif label == "Emergency Fund":
        interpretation = (
            "You have **less than 1 month saved** for emergencies." if score < 40 else
            "You're **halfway to a full emergency buffer**." if score < 70 else
            "✅ Your **emergency fund is solid**."
        )
        suggestions = [
            "Build up to 3–6 months of essential expenses.",
            "Keep it liquid and easily accessible.",
            "Set a monthly auto-save amount."
        ]
    
    return interpretation, suggestions

def generate_text_report(fhi_score, components, user_inputs):
    """Generate downloadable text report"""
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

# Initialize session state
initialize_session_state()

# Main App
st.title("⌧ Fynstra")
st.markdown("### AI-Powered Financial Health Platform for Filipinos")

# Show AI status
if AI_AVAILABLE:
    st.success("🤖 FYNyx AI is online and ready to help!")
else:
    st.warning("🤖 FYNyx AI is in basic mode. Install google-generativeai for full AI features.")

# Sidebar for navigation
st.sidebar.title("Navigation")
page = st.sidebar.selectbox("Choose a feature:", ["Financial Health Calculator", "Goal Tracker", "FYNyx Chatbot"])

if page == "Financial Health Calculator":
    # Form input container
    with st.container(border=True):
        st.subheader("Calculate your FHI Score")
        st.markdown("Enter your financial details to get your personalized Financial Health Index score and recommendations.")
        
        col1, col2 = st.columns(2)
        with col1:
            age = st.number_input("Your Age", min_value=18, max_value=100, step=1, help="Your current age in years.")
            monthly_expenses = st.number_input("Monthly Living Expenses (₱)", min_value=0.0, step=50.0,
                                               help="E.g., rent, food, transportation, utilities.")
            monthly_savings = st.number_input("Monthly Savings (₱)", min_value=0.0, step=50.0,
                                              help="The amount saved monthly.")
            emergency_fund = st.number_input("Emergency Fund Amount (₱)", min_value=0.0, step=500.0,
                                             help="For medical costs, job loss, or other emergencies.")

        with col2:
            monthly_income = st.number_input("Monthly Gross Income (₱)", min_value=0.0, step=100.0,
                                             help="Income before taxes and deductions.")
            monthly_debt = st.number_input("Monthly Debt Payments (₱)", min_value=0.0, step=50.0,
                                           help="Loans, credit cards, etc.")
            total_investments = st.number_input("Total Investments (₱)", min_value=0.0, step=500.0,
                                                help="Stocks, bonds, retirement accounts.")
            net_worth = st.number_input("Net Worth (₱)", min_value=0.0, step=500.0,
                                        help="Total assets minus total liabilities.")

    # FHI calculation logic
    if st.button("Check My Financial Health", type="primary"):
        # Validate inputs first
        errors, warnings = validate_financial_inputs(monthly_income, monthly_expenses, monthly_debt, monthly_savings)
        
        if errors:
            for error in errors:
                st.error(error)
            st.info("💡 Please review your inputs and try again.")
        elif monthly_income == 0 or monthly_expenses == 0:
            st.warning("Please input your income and expenses.")
        else:
            # Show warnings if any
            for warning in warnings:
                st.warning(warning)
            
            # Calculate FHI
            FHI, components = calculate_fhi(age, monthly_income, monthly_expenses, monthly_savings, 
                                          monthly_debt, total_investments, net_worth, emergency_fund)
            FHI_rounded = round(FHI, 2)
            
            # Store in session state
            st.session_state["FHI"] = FHI_rounded
            st.session_state["monthly_income"] = monthly_income
            st.session_state["monthly_expenses"] = monthly_expenses
            st.session_state["current_savings"] = monthly_savings
            st.session_state["components"] = components
            
            st.markdown("---")
            
            # Display results
            score_col, text_col = st.columns([1, 2])
            
            with score_col:
                fig = create_gauge_chart(FHI_rounded)
                st.plotly_chart(fig, use_container_width=True)

            with text_col:
                st.markdown(f"### Overall FHI Score: **{FHI_rounded}/100**")

                # Identify weak areas
                weak_areas = []
                for component, score in components.items():
                    if score < 60:
                        weak_areas.append(component.lower())

                # Construct weakness text
                weak_text = ""
                if weak_areas:
                    if len(weak_areas) == 1:
                        weak_text = f" However, your {weak_areas[0]} needs improvement."
                    else:
                        all_but_last = ", ".join(weak_areas[:-1])
                        weak_text = f" However, your {all_but_last} and {weak_areas[-1]} need improvement."

                    weak_text += " Addressing this will help strengthen your overall financial health."

                # Final output based on FHI
                if FHI >= 85:
                    st.success(f"🎯 Excellent! You're in great financial shape and well-prepared for the future.{weak_text}")
                elif FHI >= 70:
                    st.info(f"🟢 Good! You have a solid foundation. Stay consistent and work on gaps where needed.{weak_text}")
                elif FHI >= 50:
                    st.warning(f"🟡 Fair. You're on your way, but some areas need attention to build a stronger safety net.{weak_text}")
                else:
                    st.error(f"🔴 Needs Improvement. Your finances require urgent attention — prioritize stabilizing your income, debt, and savings.{weak_text}")

            # Component radar chart
            st.subheader("📈 Financial Health Breakdown")
            radar_fig = create_component_radar_chart(components)
            st.plotly_chart(radar_fig, use_container_width=True)

            # Component interpretations
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
            
            # Peer comparison
            st.subheader("👥 How You Compare")
            
            # Simulated peer data
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
            
            # Download report
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

elif page == "Goal Tracker":
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

elif page == "FYNyx Chatbot":
    st.subheader("🤖 FYNyx - Your AI Financial Assistant")
    
    # Display chat history
    if st.session_state.chat_history:
        st.markdown("### Previous Conversations")
        for i, chat in enumerate(st.session_state.chat_history[-5:]):  # Show last 5 conversations
            with st.expander(f"Q: {chat['question'][:50]}..." if len(chat['question']) > 50 else f"Q: {chat['question']}"):
                st.markdown(f"**You asked:** {chat['question']}")
                st.markdown(f"**FYNyx replied:** {chat['response']}")
                st.caption(f"Asked on {chat['timestamp']}")
                
                # Show if response was AI or fallback
                if 'was_ai_response' in chat:
                    if chat['was_ai_response']:
                        st.caption("🤖 AI-powered response")
                    else:
                        st.caption("🧠 Smart fallback response")
    
    with st.container(border=True):
        st.markdown("Ask FYNyx about your finances and get personalized AI-powered advice!")
        
        # Sample questions
        st.markdown("**Try asking:**")
        sample_questions = [
            "How can I improve my emergency fund?",
            "What investments are good for beginners in the Philippines?",
            "How should I pay off my debt faster?",
            "What's a good savings rate for someone my age?",
            "Should I invest in stocks or save more first?"
        ]
        
        cols = st.columns(len(sample_questions))
        for i, question in enumerate(sample_questions):
            if cols[i % len(cols)].button(f"💡 {question}", key=f"sample_{i}"):
                st.session_state.user_question = question
                st.rerun()
        
        user_question = st.text_input(
            "Ask FYNyx:", 
            value=st.session_state.get('user_question', ''),
            placeholder="e.g., How can I improve my emergency fund?",
            key="question_input"
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            ask_button = st.button("🚀 Ask FYNyx", type="primary")
        with col2:
            if st.button("🗑️ Clear Chat History"):
                st.session_state.chat_history = []
                st.success("Chat history cleared!")
                st.rerun()
        
        if ask_button and user_question.strip():
            with st.spinner("🤖 FYNyx is analyzing your question..."):
                # Prepare context for AI
                fhi_context = {
                    'FHI': st.session_state.get('FHI', 0),
                    'income': st.session_state.get('monthly_income', 0),
                    'expenses': st.session_state.get('monthly_expenses', 0),
                    'savings': st.session_state.get('current_savings', 0)
                }
                
                # Get AI response
                response = get_ai_response(user_question, fhi_context)
                
                # Display response
                st.markdown("### 🤖 FYNyx's Response:")
                st.info(response)
                
                # Save to chat history
                chat_entry = {
                    'question': user_question,
                    'response': response,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'fhi_context': fhi_context,
                    'was_ai_response': AI_AVAILABLE
                }
                st.session_state.chat_history.append(chat_entry)
                
                # Clear the question from session state
                if 'user_question' in st.session_state:
                    del st.session_state.user_question
                
                # Quick action buttons based on response
                st.markdown("**Quick Actions:**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("💰 More Savings Tips", key="savings_tip"):
                        st.session_state.user_question = "Give me more specific tips to increase my savings rate"
                        st.rerun()
                with col2:
                    if st.button("📈 Investment Advice", key="investment_tip"):
                        st.session_state.user_question = "What specific investments should I consider for my situation?"
                        st.rerun()
                with col3:
                    if st.button("🏦 Debt Strategy", key="debt_tip"):
                        st.session_state.user_question = "What's the best strategy for my debt situation?"
                        st.rerun()
        
        # Show context awareness
        if "FHI" in st.session_state:
            st.markdown("---")
            st.markdown("**🎯 FYNyx knows your context:**")
            context_col1, context_col2, context_col3 = st.columns(3)
            with context_col1:
                st.metric("Your FHI", f"{st.session_state['FHI']}")
            with context_col2:
                st.metric("Monthly Income", f"₱{st.session_state.get('monthly_income', 0):,.0f}")
            with context_col3:
                st.metric("Monthly Savings", f"₱{st.session_state.get('current_savings', 0):,.0f}")

# Footer
st.markdown("---")
st.markdown("**Fynstra AI** - Empowering Filipinos to **F**orecast, **Y**ield, and **N**avigate their financial future with confidence.")
st.markdown("*Developed by Team HI-4requency for DataWave 2025*")
