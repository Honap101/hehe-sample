import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import json

# Page config
st.set_page_config(
    page_title="Fynstra – Financial Health Index", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Initialize session state
def initialize_session_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = {}
    if "calculation_history" not in st.session_state:
        st.session_state.calculation_history = []

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
            st.experimental_rerun()
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
    st.subheader("🤖 FYNyx - Your Financial Assistant")
    
    with st.container(border=True):
        st.markdown("Ask FYNyx about your finances and get personalized advice!")
        
        user_question = st.text_input("Ask FYNyx:", 
                                      placeholder="e.g., How can I improve my emergency fund?")
        
        if st.button("Ask FYNyx") and user_question:
            with st.spinner("FYNyx is thinking..."):
                # Simulated AI responses (replace with actual API integration)
                responses = {
                    "emergency": "Based on your expenses, aim for 6 months of emergency funds. Start by setting aside 10% of your income monthly in a high-yield savings account.",
                    "debt": "Focus on paying high-interest debt first (credit cards), then tackle other loans. Consider the debt avalanche method.",
                    "invest": "For Filipinos, consider starting with index funds like FMETF or blue-chip stocks. Diversify across different asset classes.",
                    "save": "Automate your savings! Set up automatic transfers to separate accounts for different goals (emergency, retirement, vacation).",
                    "retirement": "Start early with SSS, then add private retirement accounts. Aim to save 10-15% of income for retirement."
                }
                
                # Simple keyword matching (replace with actual AI)
                response = "I'd recommend focusing on building your emergency fund first, then increasing your investment allocation. Consider consulting with a certified financial planner for personalized advice."
                
                for keyword, suggested_response in responses.items():
                    if keyword in user_question.lower():
                        response = suggested_response
                        break
                
                if "FHI" in st.session_state:
                    fhi_context = f" With your current FHI score of {st.session_state['FHI']}, "
                    response = fhi_context + response
                
                st.info(f"🤖 **FYNyx says:** {response}")
                
                # Quick action buttons
                st.markdown("**Quick Actions:**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("💰 Improve Savings"):
                        st.info("💡 Try the 50/30/20 rule: 50% needs, 30% wants, 20% savings/debt payments")
                with col2:
                    if st.button("📈 Investment Tips"):
                        st.info("💡 Start with low-cost index funds. Dollar-cost averaging can help reduce risk.")
                with col3:
                    if st.button("🏦 Debt Strategy"):
                        st.info("💡 List all debts by interest rate. Pay minimums on all, extra on highest rate debt.")

# Footer
st.markdown("---")
st.markdown("**Fynstra AI** - Empowering Filipinos to **F**orecast, **Y**ield, and **N**avigate their financial future with confidence.")
st.markdown("*Developed by Team HI-4requency for DataWave 2025*")
