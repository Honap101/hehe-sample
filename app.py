import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import hashlib
import time
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from functools import lru_cache

# ===============================
# CONFIGURATION & CONSTANTS
# ===============================
@dataclass
class Config:
    """Application configuration and constants"""
    APP_NAME = "Fynstra"
    VERSION = "2.0"
    
    # FHI Thresholds
    FHI_EXCELLENT = 85
    FHI_GOOD = 70
    FHI_FAIR = 50
    
    # Financial Constants
    EMERGENCY_FUND_MONTHS = 6
    TARGET_SAVINGS_RATE = 0.20
    MAX_DEBT_TO_INCOME = 0.40
    
    # UI Configuration
    COLORS = {
        'primary': '#667eea',
        'secondary': '#764ba2',
        'success': '#48bb78',
        'warning': '#ed8936',
        'danger': '#f56565',
        'info': '#4299e1'
    }
    
    # AI Rate Limiting
    AI_REQUESTS_PER_HOUR = 20
    CACHE_EXPIRY_HOURS = 24
    
    # Achievement Thresholds
    ACHIEVEMENTS = {
        'first_step': {'name': '🌱 First Step', 'desc': 'Calculated your first FHI score', 'requirement': 'first_calculation'},
        'saver': {'name': '💰 Smart Saver', 'desc': 'Achieved 20% savings rate', 'requirement': 'savings_rate_20'},
        'debt_free': {'name': '🎯 Debt Master', 'desc': 'Debt-to-income ratio below 20%', 'requirement': 'dti_below_20'},
        'emergency_ready': {'name': '🛡️ Emergency Ready', 'desc': 'Built 6 months emergency fund', 'requirement': 'emergency_6_months'},
        'fhi_champion': {'name': '🏆 FHI Champion', 'desc': 'Achieved FHI score above 85', 'requirement': 'fhi_85'}
    }

# ===============================
# CUSTOM CSS & UI STYLING
# ===============================
def load_custom_css():
    """Load comprehensive custom CSS for modern UI"""
    st.markdown("""
    <style>
        /* Hide Streamlit defaults */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Main container styling */
        .main {
            padding-top: 0rem;
        }
        
        /* Custom gradient header */
        .main-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 15px;
            color: white;
            margin-bottom: 2rem;
            text-align: center;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
        }
        
        .header-title {
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }
        
        .header-subtitle {
            font-size: 1.2rem;
            opacity: 0.95;
        }
        
        /* Metric cards */
        div[data-testid="metric-container"] {
            background: linear-gradient(135deg, #f6f8fb 0%, #ffffff 100%);
            border: 1px solid #e2e8f0;
            padding: 1.2rem;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
        }
        
        div[data-testid="metric-container"]:hover {
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.15);
        }
        
        /* Enhanced buttons */
        .stButton > button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            font-weight: 600;
            border-radius: 10px;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }
        
        /* Input fields */
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input {
            border-radius: 10px;
            border: 2px solid #e2e8f0;
            padding: 0.75rem;
            transition: all 0.3s;
        }
        
        .stTextInput > div > div > input:focus,
        .stNumberInput > div > div > input:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: #f7fafc;
            padding: 0.5rem;
            border-radius: 12px;
        }
        
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px;
            color: #4a5568;
            font-weight: 600;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        /* Alert boxes */
        .stAlert {
            border-radius: 12px;
            border-left: 5px solid;
            padding: 1.2rem;
        }
        
        /* Success animation */
        @keyframes successPulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .success-animation {
            animation: successPulse 0.5s ease-in-out;
        }
        
        /* Progress bars */
        .stProgress > div > div > div {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
        }
        
        /* Containers */
        div[data-testid="stVerticalBlock"] > div {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            margin-bottom: 1rem;
        }
        
        /* Sidebar styling */
        .css-1d391kg {
            background: linear-gradient(180deg, #f7fafc 0%, #edf2f7 100%);
        }
        
        /* Expander styling */
        .streamlit-expanderHeader {
            background: linear-gradient(135deg, #f7fafc 0%, #ffffff 100%);
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            font-weight: 600;
        }
        
        /* Achievement badge */
        .achievement-badge {
            display: inline-block;
            padding: 0.5rem 1rem;
            background: linear-gradient(135deg, #ffd700 0%, #ffed4e 100%);
            border-radius: 20px;
            font-weight: 600;
            box-shadow: 0 3px 10px rgba(255, 215, 0, 0.3);
            margin: 0.25rem;
        }
        
        /* FHI Score display */
        .fhi-score-display {
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            margin: 1rem 0;
        }
    </style>
    """, unsafe_allow_html=True)

# ===============================
# ENHANCED UI COMPONENTS CLASS
# ===============================
class UIComponents:
    """Reusable UI components with consistent styling"""
    
    @staticmethod
    def render_header():
        """Render the main application header"""
        st.markdown("""
            <div class="main-header">
                <div class="header-title">⌧ Fynstra</div>
                <div class="header-subtitle">AI-Powered Financial Health Platform for Filipinos</div>
            </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def render_metric_card(col, title: str, value: str, delta: str = None, delta_color: str = "normal"):
        """Render a styled metric card"""
        with col:
            st.metric(label=title, value=value, delta=delta, delta_color=delta_color)
    
    @staticmethod
    def render_progress_bar(label: str, value: float, max_value: float = 100, show_percentage: bool = True):
        """Render a labeled progress bar"""
        progress = min(value / max_value, 1.0)
        st.markdown(f"**{label}**")
        st.progress(progress)
        if show_percentage:
            st.caption(f"{value:.1f}% / {max_value:.0f}%")
    
    @staticmethod
    def render_achievement_badges(achievements: List[str]):
        """Render achievement badges"""
        if achievements:
            st.markdown("### 🏆 Your Achievements")
            badges_html = ""
            for achievement in achievements:
                badge_info = Config.ACHIEVEMENTS.get(achievement, {})
                badges_html += f'<span class="achievement-badge">{badge_info.get("name", "")}</span>'
            st.markdown(badges_html, unsafe_allow_html=True)

# ===============================
# FHI CALCULATOR CLASS
# ===============================
class FHICalculator:
    """Financial Health Index calculation engine"""

    @staticmethod
    def validate_inputs(income: float, expenses: float, debt: float, savings: float, 
                        age: int) -> Tuple[List[str], List[str]]:
        """Enhanced input validation with comprehensive checks"""
        errors: List[str] = []
        warnings: List[str] = []

        # Critical errors
        if income <= 0:
            errors.append("❌ Income must be greater than zero")

        if age < 18 or age > 100:
            errors.append("❌ Please enter a valid age between 18 and 100")

        # Logical validations
        if debt > income:
            errors.append("❌ Monthly debt payments exceed income - this is unsustainable")

        if expenses > income:
            warnings.append("⚠️ Expenses exceed income - you're running a deficit")

        if (expenses + debt + savings) > income * 1.1:
            warnings.append("⚠️ Total obligations exceed income - please verify your numbers")

        # Ratio checks
        if income > 0:
            debt_ratio = debt / income
            if debt_ratio > Config.MAX_DEBT_TO_INCOME:
                warnings.append(
                    f"⚠️ Debt-to-income ratio ({debt_ratio:.1%}) is above recommended {Config.MAX_DEBT_TO_INCOME:.0%}"
                )

            expense_ratio = expenses / income
            if expense_ratio > 0.8:
                warnings.append(
                    f"⚠️ You're spending {expense_ratio:.1%} of income on expenses - consider budgeting"
                )

        return errors, warnings

    @staticmethod
    @st.cache_data(ttl=3600)
    def calculate(age: int, monthly_income: float, monthly_expenses: float, 
                  monthly_savings: float, monthly_debt: float, total_investments: float, 
                  net_worth: float, emergency_fund: float) -> Tuple[float, Dict[str, float]]:
        """Calculate FHI (cached)"""

        # Age-based multipliers
        if age < 30:
            alpha, beta = 2.5, 2.0
        elif age < 40:
            alpha, beta = 3.0, 3.0
        elif age < 50:
            alpha, beta = 3.5, 4.0
        else:
            alpha, beta = 4.0, 5.0

        annual_income = monthly_income * 12

        # Component calculations with safety checks
        components: Dict[str, float] = {}

        # Net Worth Score
        if annual_income > 0:
            components["Net Worth"] = min(max((net_worth / (annual_income * alpha)) * 100, 0), 100)
        else:
            components["Net Worth"] = 0

        # Debt-to-Income Score
        if monthly_income > 0:
            components["Debt-to-Income"] = 100 - min((monthly_debt / monthly_income) * 100, 100)
        else:
            components["Debt-to-Income"] = 100 if monthly_debt == 0 else 0

        # Savings Rate Score
        if monthly_income > 0:
            components["Savings Rate"] = min((monthly_savings / monthly_income) * 100, 100)
        else:
            components["Savings Rate"] = 0

        # Investment Score
        if annual_income > 0:
            components["Investment"] = min(max((total_investments / (beta * annual_income)) * 100, 0), 100)
        else:
            components["Investment"] = 0

        # Emergency Fund Score
        if monthly_expenses > 0:
            components["Emergency Fund"] = min((emergency_fund / monthly_expenses) / 6 * 100, 100)
        else:
            components["Emergency Fund"] = 100 if emergency_fund > 0 else 0

        # Weighted FHI calculation
        fhi = (
            0.20 * components["Net Worth"] +
            0.15 * components["Debt-to-Income"] +
            0.15 * components["Savings Rate"] +
            0.15 * components["Investment"] +
            0.20 * components["Emergency Fund"] +
            15
        )

        return round(fhi, 2), components

# ===============================
# AI ASSISTANT CLASS
# ===============================
class AIAssistant:
    """Enhanced AI integration with caching and rate limiting"""
    
    def __init__(self):
        self.model = None
        self.ai_available = False
        self.request_cache = {}
        self.request_timestamps = []
        self.initialize()
    
    def initialize(self):
        """Initialize AI with proper error handling"""
        try:
            import google.generativeai as genai
            
            if "GEMINI_API_KEY" in st.secrets:
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                self.model = genai.GenerativeModel("gemini-1.5-flash")
                self.ai_available = True
            else:
                st.warning("⚠️ AI API key not configured. Using smart fallback responses.")
        except ImportError:
            st.info("💡 Install google-generativeai for AI features: pip install google-generativeai")
        except Exception as e:
            st.error(f"AI initialization error: {str(e)}")
    
    def check_rate_limit(self) -> bool:
        """Check if rate limit is exceeded"""
        current_time = datetime.now()
        hour_ago = current_time - timedelta(hours=1)
        
        # Clean old timestamps
        self.request_timestamps = [ts for ts in self.request_timestamps if ts > hour_ago]
        
        if len(self.request_timestamps) >= Config.AI_REQUESTS_PER_HOUR:
            return False
        
        self.request_timestamps.append(current_time)
        return True
    
    def get_cache_key(self, question: str, context: Dict) -> str:
        """Generate cache key for responses"""
        context_str = json.dumps(context, sort_keys=True)
        combined = f"{question}_{context_str}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get_response(self, question: str, context: Dict) -> Tuple[str, bool]:
        """Get AI response with caching and rate limiting"""
        
        # Check cache first
        cache_key = self.get_cache_key(question, context)
        if cache_key in self.request_cache:
            cached_response, cache_time = self.request_cache[cache_key]
            age_secs = (datetime.now() - cache_time).total_seconds()
            if age_secs < Config.CACHE_EXPIRY_HOURS * 3600:
                return cached_response, True
        
        # Check rate limit
        if not self.check_rate_limit():
            return "⏳ Rate limit reached. Please wait a moment before asking another question.", False
        
        # Get response
        if self.ai_available and self.model:
            try:
                response = self._get_ai_response(question, context)
                self.request_cache[cache_key] = (response, datetime.now())
                return response, True
            except Exception as e:
                st.error(f"AI error: {str(e)}")
                return self._get_fallback_response(question, context), False
        else:
            return self._get_fallback_response(question, context), False
    
    def _get_ai_response(self, question: str, context: Dict) -> str:
        """Internal method to get AI response"""
        prompt = f"""
        You are FYNyx, an AI financial advisor for Filipino users.
        
        USER CONTEXT:
        - FHI Score: {context.get('FHI', 'Not calculated')}/100
        - Monthly Income: ₱{context.get('income', 0):,.0f}
        - Monthly Expenses: ₱{context.get('expenses', 0):,.0f}
        - Monthly Savings: ₱{context.get('savings', 0):,.0f}
        
        USER QUESTION: {question}
        
        Provide specific, actionable advice in 150 words or less.
        Consider Philippine context (SSS, Pag-IBIG, local banks).
        Be encouraging and practical.
        """
        
        response = self.model.generate_content(prompt)
        return response.text
    
    def _get_fallback_response(self, question: str, context: Dict) -> str:
        """Enhanced fallback responses"""
        question_lower = question.lower()
        
        # Category detection
        categories = {
            'emergency': ['emergency', 'fund', 'safety net'],
            'debt': ['debt', 'loan', 'credit', 'payment'],
            'investment': ['invest', 'stocks', 'mutual', 'portfolio'],
            'savings': ['save', 'savings', 'budget'],
            'retirement': ['retirement', 'pension', 'sss', 'pagibig']
        }
        
        detected_category = None
        for category, keywords in categories.items():
            if any(keyword in question_lower for keyword in keywords):
                detected_category = category
                break
        
        # Generate contextual response
        fhi = context.get('FHI', 0)
        income = context.get('income', 0)
        
        responses = {
            'emergency': f"Build ₱{context.get('expenses', 0) * 6:,.0f} (6 months expenses) emergency fund. Start with ₱{context.get('expenses', 0) * 6 / 12:,.0f} monthly savings.",
            'debt': "Focus on high-interest debt first. Use avalanche method: minimum payments on all, extra on highest rate.",
            'investment': f"Start with ₱{min(income * 0.1, 5000):,.0f} monthly in FMETF or equity funds. Diversify as you grow.",
            'savings': f"Target {Config.TARGET_SAVINGS_RATE * 100:.0f}% savings rate. You need ₱{income * Config.TARGET_SAVINGS_RATE:,.0f} monthly.",
            'retirement': "Maximize SSS/GSIS contributions, add PERA account for tax benefits. Target 15% for retirement."
        }
        
        return responses.get(detected_category, 
                            "Focus on building emergency fund, reducing debt, and increasing savings rate for better financial health.")

# ===============================
# VISUALIZATION ENGINE CLASS
# ===============================
class VisualizationEngine:
    """Enhanced chart and visualization creation"""
    
    @staticmethod
    def create_gauge_chart(fhi_score: float) -> go.Figure:
        """Create animated FHI gauge chart"""
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=fhi_score,
            title={'text': "FHI Score", 'font': {'size': 24, 'color': '#2d3748'}},
            delta={'reference': 70, 'increasing': {'color': "green"}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 2, 'tickcolor': "#cbd5e0"},
                'bar': {'color': "rgba(102, 126, 234, 0.8)", 'thickness': 0.75},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "#e2e8f0",
                'steps': [
                    {'range': [0, 50], 'color': "rgba(245, 101, 101, 0.3)"},
                    {'range': [50, 70], 'color': "rgba(237, 137, 54, 0.3)"},
                    {'range': [70, 100], 'color': "rgba(72, 187, 120, 0.3)"}
                ],
                'threshold': {
                    'line': {'color': "#2d3748", 'width': 4},
                    'thickness': 0.75,
                    'value': fhi_score
                }
            }
        ))
        
        fig.update_layout(
            height=350,
            margin=dict(l=20, r=20, t=40, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font={'family': "Arial, sans-serif"}
        )
        
        return fig
    
    @staticmethod
    def create_component_radar(components: Dict[str, float]) -> go.Figure:
        """Create enhanced radar chart"""
        categories = list(components.keys())
        values = list(components.values())
        
        fig = go.Figure()
        
        # Actual scores
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            name='Your Scores',
            line=dict(color='#667eea', width=3),
            marker=dict(size=8, color='#667eea'),
            fillcolor='rgba(102, 126, 234, 0.3)'
        ))
        
        # Target scores
        fig.add_trace(go.Scatterpolar(
            r=[70] * len(categories),
            theta=categories,
            fill='toself',
            name='Target (Good)',
            line=dict(color='#48bb78', width=2, dash='dash'),
            fillcolor='rgba(72, 187, 120, 0.1)'
        ))
        
        # Excellent scores
        fig.add_trace(go.Scatterpolar(
            r=[85] * len(categories),
            theta=categories,
            fill='toself',
            name='Excellent',
            line=dict(color='#ffd700', width=2, dash='dot'),
            fillcolor='rgba(255, 215, 0, 0.05)'
        ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100],
                    tickfont=dict(size=10),
                    gridcolor='#e2e8f0'
                ),
                angularaxis=dict(
                    tickfont=dict(size=12, color='#2d3748'),
                    gridcolor='#e2e8f0'
                )
            ),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5
            ),
            height=450,
            margin=dict(l=80, r=80, t=80, b=80),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        
        return fig
    
    @staticmethod
    def create_expense_breakdown(expenses: float, income: float, savings: float, debt: float) -> go.Figure:
        """Create expense breakdown pie chart"""
        labels = ['Living Expenses', 'Savings', 'Debt Payments', 'Remaining']
        values = [expenses, savings, debt, max(0, income - expenses - savings - debt)]
        colors = ['#f56565', '#48bb78', '#ed8936', '#4299e1']
        
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker=dict(colors=colors, line=dict(color='white', width=2)),
            textfont=dict(size=12),
            textposition='outside',
            textinfo='label+percent'
        )])
        
        fig.update_layout(
            height=400,
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.1)
        )
        
        return fig
    
    @staticmethod
    def create_progress_timeline(current_value: float, target_value: float, months: int) -> go.Figure:
        """Create savings progress timeline"""
        months_list = list(range(months + 1))
        monthly_increment = (target_value - current_value) / months if months > 0 else 0
        projected_values = [current_value + (monthly_increment * m) for m in months_list]
        
        fig = go.Figure()
        
        # Projected line
        fig.add_trace(go.Scatter(
            x=months_list,
            y=projected_values,
            mode='lines+markers',
            name='Projected Progress',
            line=dict(color='#667eea', width=3),
            marker=dict(size=8, color='#667eea'),
            fill='tonexty',
            fillcolor='rgba(102, 126, 234, 0.1)'
        ))
        
        # Target line
        fig.add_trace(go.Scatter(
            x=[0, months],
            y=[target_value, target_value],
            mode='lines',
            name='Target',
            line=dict(color='#48bb78', width=2, dash='dash')
        ))
        
        fig.update_layout(
            title="Savings Progress Timeline",
            xaxis_title="Months",
            yaxis_title="Amount (₱)",
            height=350,
            margin=dict(l=60, r=20, t=40, b=40),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor='#e2e8f0'),
            yaxis=dict(gridcolor='#e2e8f0', tickformat=',.0f')
        )
        
        return fig

# ===============================
# GAMIFICATION SYSTEM
# ===============================
class GamificationSystem:
    """Handle achievements and progress tracking"""
    
    @staticmethod
    def check_achievements(fhi_score: float, components: Dict, user_data: Dict) -> List[str]:
        """Check and award achievements"""
        achievements = st.session_state.get('achievements', [])
        new_achievements = []
        
        # First calculation
        if 'first_step' not in achievements and fhi_score > 0:
            achievements.append('first_step')
            new_achievements.append('first_step')
        
        # Savings rate achievement
        if 'saver' not in achievements and components.get('Savings Rate', 0) >= 20:
            achievements.append('saver')
            new_achievements.append('saver')
        
        # Debt achievement
        if 'debt_free' not in achievements and components.get('Debt-to-Income', 0) >= 80:
            achievements.append('debt_free')
            new_achievements.append('debt_free')
        
        # Emergency fund achievement
        if 'emergency_ready' not in achievements and components.get('Emergency Fund', 0) >= 100:
            achievements.append('emergency_ready')
            new_achievements.append('emergency_ready')
        
        # FHI champion
        if 'fhi_champion' not in achievements and fhi_score >= Config.FHI_EXCELLENT:
            achievements.append('fhi_champion')
            new_achievements.append('fhi_champion')
        
        st.session_state['achievements'] = achievements
        
        # Show celebration for new achievements
        if new_achievements:
            st.balloons()
            for achievement in new_achievements:
                badge_info = Config.ACHIEVEMENTS.get(achievement, {})
                st.success(f"🎉 Achievement Unlocked: {badge_info.get('name', '')} - {badge_info.get('desc', '')}")
        
        return achievements
    
    @staticmethod
    def get_user_level(fhi_score: float) -> Tuple[str, int, float]:
        """Determine user level based on FHI score"""
        levels = [
            (0, "💚 Financial Beginner"),
            (30, "🌱 Financial Learner"),
            (50, "💪 Financial Builder"),
            (70, "⭐ Financial Expert"),
            (85, "🏆 Financial Master"),
            (95, "👑 Financial Legend")
        ]
        
        for i, (threshold, title) in enumerate(levels):
            if fhi_score < threshold:
                level = i
                level_title = levels[i-1][1] if i > 0 else levels[0][1]
                progress_to_next = (fhi_score - (levels[i-1][0] if i > 0 else 0)) / (threshold - (levels[i-1][0] if i > 0 else 0))
                return level_title, level, progress_to_next
        
        # Max level reached
        return levels[-1][1], len(levels), 1.0

# ===============================
# MAIN APPLICATION CLASS
# ===============================
class FynstraApp:
    """Main application orchestrator"""
    
    def __init__(self):
        self.setup_page_config()
        self.initialize_session_state()
        load_custom_css()
        self.ai_assistant = AIAssistant()
        self.fhi_calculator = FHICalculator()
        self.viz_engine = VisualizationEngine()
        self.gamification = GamificationSystem()
    
    def setup_page_config(self):
        """Configure Streamlit page settings"""
        st.set_page_config(
            page_title="Fynstra - Financial Health Platform",
            page_icon="⌧",
            layout="wide",
            initial_sidebar_state="expanded",
            menu_items={
                'About': "Fynstra v2.0 - Empowering Filipino Financial Health",
                'Get Help': 'https://github.com/yourusername/fynstra',
                'Report a bug': 'https://github.com/yourusername/fynstra/issues'
            }
        )
    
    def initialize_session_state(self):
        """Initialize all session state variables"""
        defaults = {
            'user_data': {},
            'calculation_history': [],
            'chat_history': [],
            'achievements': [],
            'fhi_calculated': False,
            'current_page': 'dashboard',
            'FHI': 0,
            'components': {},
            'monthly_income': 0,
            'monthly_expenses': 0,
            'current_savings': 0,
            'goals': [],
            'last_calculation_time': None
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def render_sidebar(self):
        """Render enhanced sidebar navigation"""
        with st.sidebar:
            st.markdown("### 🧭 Navigation")
            
            # Navigation buttons with icons
            pages = {
                "📊 Dashboard": "dashboard",
                "💳 FHI Calculator": "calculator",
                "🎯 Goal Tracker": "goals",
                "🤖 FYNyx Chat": "chat",
                "📈 Analytics": "analytics",
                "🏆 Achievements": "achievements"
            }
            
            for label, page_id in pages.items():
                if st.button(label, key=f"nav_{page_id}", use_container_width=True):
                    st.session_state.current_page = page_id
                    st.rerun()
            
            st.markdown("---")
            
            # Quick stats
            if st.session_state.get('FHI', 0) > 0:
                st.markdown("### 📊 Quick Stats")
                
                fhi = st.session_state.FHI
                color = "#48bb78" if fhi >= 70 else "#ed8936" if fhi >= 50 else "#f56565"
                
                st.markdown(f"""
                    <div style='text-align: center; padding: 1rem; background: linear-gradient(135deg, {color}22 0%, {color}11 100%); border-radius: 10px;'>
                        <div style='font-size: 2.5rem; font-weight: bold; color: {color};'>{fhi}</div>
                        <div style='font-size: 0.9rem; color: #718096;'>FHI Score</div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Level progress
                level_title, level, progress = self.gamification.get_user_level(fhi)
                st.markdown(f"**Level:** {level_title}")
                st.progress(progress)
                
                # Achievement count
                achievements = st.session_state.get('achievements', [])
                st.metric("🏆 Achievements", f"{len(achievements)}/{len(Config.ACHIEVEMENTS)}")
            
            st.markdown("---")
            st.caption("Fynstra v2.0 | Team HI-4requency")
    
    def render_dashboard(self):
        """Render main dashboard view"""
        st.markdown("## 📊 Financial Health Dashboard")
        
        if st.session_state.get('FHI', 0) == 0:
            st.info("👋 Welcome to Fynstra! Start by calculating your FHI score to unlock your personalized dashboard.")
            if st.button("Calculate My FHI Score", type="primary"):
                st.session_state.current_page = 'calculator'
                st.rerun()
        else:
            # Main metrics row
            col1, col2, col3, col4 = st.columns(4)
            
            fhi = st.session_state.FHI
            income = st.session_state.get('monthly_income', 0)
            expenses = st.session_state.get('monthly_expenses', 0)
            savings = st.session_state.get('current_savings', 0)
            
            UIComponents.render_metric_card(col1, "FHI Score", f"{fhi}/100", 
                                           f"{fhi-70:+.0f} vs target", 
                                           "normal" if fhi >= 70 else "inverse")
            UIComponents.render_metric_card(col2, "Monthly Income", f"₱{income:,.0f}")
            UIComponents.render_metric_card(col3, "Monthly Savings", f"₱{savings:,.0f}",
                                           f"{(savings/income*100) if income > 0 else 0:.1f}%")
            UIComponents.render_metric_card(col4, "Savings Rate", 
                                           f"{(savings/income*100) if income > 0 else 0:.0f}%",
                                           "Target: 20%", 
                                           "normal" if savings/income >= 0.2 else "inverse")
            
            st.markdown("---")
            
            # Charts row
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 🎯 Financial Health Components")
                components = st.session_state.get('components', {})
                if components:
                    fig = self.viz_engine.create_component_radar(components)
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("### 💰 Monthly Budget Breakdown")
                if income > 0:
                    fig = self.viz_engine.create_expense_breakdown(expenses, income, savings, 
                                                                  st.session_state.get('monthly_debt', 0))
                    st.plotly_chart(fig, use_container_width=True)
            
            # Recommendations section
            st.markdown("### 💡 Personalized Recommendations")
            
            components = st.session_state.get('components', {})
            weak_areas = [(name, score) for name, score in components.items() if score < 60]
            
            if weak_areas:
                weak_areas.sort(key=lambda x: x[1])  # Sort by score
                
                cols = st.columns(min(3, len(weak_areas)))
                for i, (area, score) in enumerate(weak_areas[:3]):
                    with cols[i]:
                        with st.container():
                            st.markdown(f"""
                                <div style='padding: 1rem; background: linear-gradient(135deg, #fed7d7 0%, #fff5f5 100%); 
                                           border-radius: 10px; border-left: 4px solid #f56565;'>
                                    <h4 style='color: #c53030; margin: 0;'>Improve {area}</h4>
                                    <p style='font-size: 2rem; font-weight: bold; color: #f56565; margin: 0.5rem 0;'>{score:.0f}%</p>
                                    <p style='color: #742a2a; font-size: 0.9rem;'>Below target of 60%</p>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            if st.button(f"Get Tips", key=f"tips_{area}"):
                                st.session_state.user_question = f"How can I improve my {area}?"
                                st.session_state.current_page = 'chat'
                                st.rerun()
            else:
                st.success("🎉 Great job! All your financial health components are above 60%!")
            
            # Quick actions
            st.markdown("### ⚡ Quick Actions")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("📊 Recalculate FHI", use_container_width=True):
                    st.session_state.current_page = 'calculator'
                    st.rerun()
            
            with col2:
                if st.button("🎯 Set New Goal", use_container_width=True):
                    st.session_state.current_page = 'goals'
                    st.rerun()
            
            with col3:
                if st.button("🤖 Ask FYNyx", use_container_width=True):
                    st.session_state.current_page = 'chat'
                    st.rerun()
            
            with col4:
                if st.button("📈 View Analytics", use_container_width=True):
                    st.session_state.current_page = 'analytics'
                    st.rerun()
    
    def render_calculator(self):
        """Render FHI calculator page"""
        st.markdown("## 💳 Financial Health Index Calculator")
        
        # Form inputs
        with st.form("fhi_calculator_form"):
            st.markdown("### Enter Your Financial Information")
            
            col1, col2 = st.columns(2)
            
            with col1:
                age = st.number_input("Your Age", min_value=18, max_value=100, value=30, step=1,
                                     help="Your current age affects target multipliers")
                monthly_income = st.number_input("Monthly Gross Income (₱)", min_value=0.0, value=50000.0, step=1000.0,
                                                help="Total income before taxes")
                monthly_expenses = st.number_input("Monthly Living Expenses (₱)", min_value=0.0, value=30000.0, step=500.0,
                                                  help="Rent, food, utilities, transportation")
                monthly_savings = st.number_input("Monthly Savings (₱)", min_value=0.0, value=10000.0, step=500.0,
                                                 help="Amount saved each month")
            
            with col2:
                monthly_debt = st.number_input("Monthly Debt Payments (₱)", min_value=0.0, value=5000.0, step=500.0,
                                              help="Loans, credit cards, etc.")
                total_investments = st.number_input("Total Investments (₱)", min_value=0.0, value=100000.0, step=5000.0,
                                                   help="Stocks, bonds, mutual funds, etc.")
                net_worth = st.number_input("Net Worth (₱)", min_value=0.0, value=200000.0, step=5000.0,
                                           help="Total assets minus total liabilities")
                emergency_fund = st.number_input("Emergency Fund (₱)", min_value=0.0, value=60000.0, step=5000.0,
                                                help="Liquid savings for emergencies")
            
            submitted = st.form_submit_button("Calculate My FHI Score", type="primary", use_container_width=True)
        
        if submitted:
            # Validate inputs
            errors, warnings = self.fhi_calculator.validate_inputs(
                monthly_income, monthly_expenses, monthly_debt, monthly_savings, age
            )
            
            if errors:
                for error in errors:
                    st.error(error)
            else:
                # Show warnings
                for warning in warnings:
                    st.warning(warning)
                
                # Calculate FHI
                with st.spinner("Calculating your Financial Health Index..."):
                    time.sleep(0.5)  # Brief pause for effect
                    
                    fhi, components = self.fhi_calculator.calculate(
                        age, monthly_income, monthly_expenses, monthly_savings,
                        monthly_debt, total_investments, net_worth, emergency_fund
                    )
                    
                    # Store in session state
                    st.session_state.FHI = fhi
                    st.session_state.components = components
                    st.session_state.monthly_income = monthly_income
                    st.session_state.monthly_expenses = monthly_expenses
                    st.session_state.current_savings = monthly_savings
                    st.session_state.monthly_debt = monthly_debt
                    st.session_state.fhi_calculated = True
                    st.session_state.last_calculation_time = datetime.now()
                    
                    # Add to history
                    st.session_state.calculation_history.append({
                        'timestamp': datetime.now(),
                        'fhi': fhi,
                        'components': components
                    })
                
                # Display results
                st.markdown("---")
                st.markdown("## 📊 Your Results")
                
                # FHI Score display
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    fig = self.viz_engine.create_gauge_chart(fhi)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown(f'<div class="fhi-score-display">{fhi}/100</div>', unsafe_allow_html=True)
                    
                    # Interpretation
                    if fhi >= Config.FHI_EXCELLENT:
                        st.success("🎯 **Excellent!** You're in outstanding financial health!")
                        level_color = "#48bb78"
                    elif fhi >= Config.FHI_GOOD:
                        st.info("🟢 **Good!** You have solid financial foundations.")
                        level_color = "#4299e1"
                    elif fhi >= Config.FHI_FAIR:
                        st.warning("🟡 **Fair.** Room for improvement in key areas.")
                        level_color = "#ed8936"
                    else:
                        st.error("🔴 **Needs Attention.** Focus on building financial stability.")
                        level_color = "#f56565"
                    
                    # Level and achievements
                    level_title, level, progress = self.gamification.get_user_level(fhi)
                    st.markdown(f"**Your Level:** {level_title}")
                    st.progress(progress)
                
                # Check for new achievements
                achievements = self.gamification.check_achievements(fhi, components, {
                    'income': monthly_income,
                    'expenses': monthly_expenses,
                    'savings': monthly_savings
                })
                
                # Component breakdown
                st.markdown("### 📈 Component Analysis")
                
                # Radar chart
                fig = self.viz_engine.create_component_radar(components)
                st.plotly_chart(fig, use_container_width=True)
                
                # Detailed component cards
                st.markdown("### 💡 Detailed Breakdown & Recommendations")
                
                component_descriptions = {
                    "Net Worth": {
                        'icon': '💎',
                        'desc': "Assets minus liabilities - your overall wealth position",
                        'tips': [
                            "Increase assets through savings and investments",
                            "Reduce liabilities by paying down debt",
                            "Track net worth monthly to monitor progress"
                        ]
                    },
                    "Debt-to-Income": {
                        'icon': '💳',
                        'desc': "How much of your income goes to debt payments",
                        'tips': [
                            "Keep debt payments below 30% of income",
                            "Pay off high-interest debt first (avalanche method)",
                            "Avoid taking new debt unless necessary"
                        ]
                    },
                    "Savings Rate": {
                        'icon': '💰',
                        'desc': "Percentage of income you save monthly",
                        'tips': [
                            "Aim for at least 20% savings rate",
                            "Automate savings transfers after payday",
                            "Track expenses to find saving opportunities"
                        ]
                    },
                    "Investment": {
                        'icon': '📈',
                        'desc': "How well you're growing wealth through investments",
                        'tips': [
                            "Start with low-cost index funds (FMETF)",
                            "Diversify across asset classes",
                            "Invest consistently regardless of market conditions"
                        ]
                    },
                    "Emergency Fund": {
                        'icon': '🛡️',
                        'desc': "Financial buffer for unexpected expenses",
                        'tips': [
                            "Build 3-6 months of expenses",
                            "Keep in high-yield savings account",
                            "Only use for true emergencies"
                        ]
                    }
                }
                
                cols = st.columns(2)
                for i, (component, score) in enumerate(components.items()):
                    with cols[i % 2]:
                        info = component_descriptions.get(component, {})
                        
                        # Determine status color
                        if score >= 80:
                            status_color = "#48bb78"
                            status_text = "Excellent"
                        elif score >= 60:
                            status_color = "#4299e1"
                            status_text = "Good"
                        elif score >= 40:
                            status_color = "#ed8936"
                            status_text = "Fair"
                        else:
                            status_color = "#f56565"
                            status_text = "Needs Work"
                        
                        with st.expander(f"{info.get('icon', '')} **{component}** - {score:.0f}% ({status_text})", expanded=score < 60):
                            st.markdown(f"*{info.get('desc', '')}*")
                            
                            # Progress bar
                            st.progress(score / 100)
                            
                            # Tips
                            st.markdown("**How to improve:**")
                            for tip in info.get('tips', []):
                                st.markdown(f"• {tip}")
                            
                            # Quick action button
                            if st.button(f"Get personalized advice", key=f"advice_{component}"):
                                st.session_state.user_question = f"How can I improve my {component} score which is currently at {score:.0f}%?"
                                st.session_state.current_page = 'chat'
                                st.rerun()
                
                # Peer comparison
                st.markdown("### 👥 Peer Comparison")
                
                age_group = "18-25" if age < 26 else "26-35" if age < 36 else "36-50" if age < 51 else "50+"
                peer_data = {
                    "18-25": {"FHI": 45, "Savings": 15, "Emergency": 35},
                    "26-35": {"FHI": 55, "Savings": 18, "Emergency": 55},
                    "36-50": {"FHI": 65, "Savings": 22, "Emergency": 70},
                    "50+": {"FHI": 75, "Savings": 25, "Emergency": 85}
                }[age_group]
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    delta = fhi - peer_data['FHI']
                    st.metric("Your FHI vs Peers", f"{fhi:.0f}", f"{delta:+.0f}",
                             delta_color="normal" if delta >= 0 else "inverse")
                
                with col2:
                    savings_rate = components.get('Savings Rate', 0)
                    delta = savings_rate - peer_data['Savings']
                    st.metric("Your Savings vs Peers", f"{savings_rate:.0f}%", f"{delta:+.0f}%",
                             delta_color="normal" if delta >= 0 else "inverse")
                
                with col3:
                    emergency = components.get('Emergency Fund', 0)
                    delta = emergency - peer_data['Emergency']
                    st.metric("Your Emergency Fund vs Peers", f"{emergency:.0f}%", f"{delta:+.0f}%",
                             delta_color="normal" if delta >= 0 else "inverse")
                
                st.caption(f"*Comparing with {age_group} age group in the Philippines*")
                
                # Export options
                st.markdown("### 📄 Export Your Report")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📧 Email Report", use_container_width=True):
                        st.info("Email feature coming soon!")
                
                with col2:
                    report_text = self.generate_report(fhi, components, {
                        'age': age,
                        'income': monthly_income,
                        'expenses': monthly_expenses,
                        'savings': monthly_savings,
                        'debt': monthly_debt,
                        'investments': total_investments,
                        'net_worth': net_worth,
                        'emergency_fund': emergency_fund
                    })
                    
                    st.download_button(
                        "📥 Download Report",
                        data=report_text,
                        file_name=f"fynstra_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
    
    def render_goals(self):
        """Render goal tracker page"""
        st.markdown("## 🎯 Financial Goal Tracker")
        
        if not st.session_state.get('FHI'):
            st.info("Please calculate your FHI score first to use the Goal Tracker.")
            if st.button("Calculate FHI Score"):
                st.session_state.current_page = 'calculator'
                st.rerun()
            return
        
        # Add new goal
        with st.expander("➕ Add New Financial Goal", expanded=True):
            with st.form("add_goal_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    goal_name = st.text_input("Goal Name", placeholder="e.g., Emergency Fund, New Car, House Down Payment")
                    goal_amount = st.number_input("Target Amount (₱)", min_value=0.0, step=1000.0)
                    current_amount = st.number_input("Current Amount Saved (₱)", min_value=0.0, step=1000.0)
                
                with col2:
                    goal_category = st.selectbox("Category", 
                                                ["Emergency Fund", "Investment", "Major Purchase", "Debt Payment", "Other"])
                    goal_months = st.number_input("Time Frame (months)", min_value=1, max_value=360, value=12)
                    goal_priority = st.select_slider("Priority", options=["Low", "Medium", "High"])
                
                if st.form_submit_button("Add Goal", type="primary"):
                    if goal_name and goal_amount > 0:
                        new_goal = {
                            'id': len(st.session_state.goals) + 1,
                            'name': goal_name,
                            'amount': goal_amount,
                            'current': current_amount,
                            'category': goal_category,
                            'months': goal_months,
                            'priority': goal_priority,
                            'created': datetime.now(),
                            'monthly_target': (goal_amount - current_amount) / goal_months
                        }
                        st.session_state.goals.append(new_goal)
                        st.success(f"✅ Goal '{goal_name}' added successfully!")
                        st.rerun()
        
        # Display existing goals
        if st.session_state.goals:
            st.markdown("### 📋 Your Financial Goals")
            
            # Summary metrics
            total_goals = len(st.session_state.goals)
            total_target = sum(g['amount'] for g in st.session_state.goals)
            total_saved = sum(g['current'] for g in st.session_state.goals)
            overall_progress = (total_saved / total_target * 100) if total_target > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Goals", total_goals)
            with col2:
                st.metric("Total Target", f"₱{total_target:,.0f}")
            with col3:
                st.metric("Total Saved", f"₱{total_saved:,.0f}")
            with col4:
                st.metric("Overall Progress", f"{overall_progress:.1f}%")
            
            st.markdown("---")
            
            # Goal cards
            for goal in st.session_state.goals:
                progress = (goal['current'] / goal['amount'] * 100) if goal['amount'] > 0 else 0
                monthly_savings = st.session_state.get('current_savings', 0)
                
                # Priority color
                priority_colors = {"High": "#f56565", "Medium": "#ed8936", "Low": "#4299e1"}
                priority_color = priority_colors.get(goal['priority'], "#718096")
                
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.markdown(f"""
                            <div style='display: flex; align-items: center; gap: 1rem;'>
                                <div style='width: 4px; height: 40px; background: {priority_color}; border-radius: 2px;'></div>
                                <div>
                                    <h4 style='margin: 0;'>{goal['name']}</h4>
                                    <p style='margin: 0; color: #718096; font-size: 0.9rem;'>{goal['category']} • {goal['priority']} Priority</p>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Progress bar
                        st.progress(progress / 100)
                        st.caption(f"₱{goal['current']:,.0f} / ₱{goal['amount']:,.0f} ({progress:.1f}%)")
                    
                    with col2:
                        months_remaining = goal['months'] - ((datetime.now() - goal['created']).days // 30)
                        monthly_needed = goal['monthly_target']
                        
                        if monthly_savings >= monthly_needed:
                            status = "✅ On Track"
                            status_color = "normal"
                        else:
                            status = f"⚠️ Need ₱{monthly_needed - monthly_savings:,.0f} more/month"
                            status_color = "inverse"
                        
                        st.metric("Monthly Target", f"₱{monthly_needed:,.0f}", status, delta_color=status_color)
                        st.caption(f"{max(0, months_remaining)} months remaining")
                    
                    with col3:
                        col_update, col_delete = st.columns(2)
                        with col_update:
                            if st.button("📝", key=f"edit_{goal['id']}", help="Update progress"):
                                amount = st.number_input(f"Update amount for {goal['name']}", 
                                                       value=goal['current'], key=f"update_{goal['id']}")
                                goal['current'] = amount
                                st.rerun()
                        
                        with col_delete:
                            if st.button("🗑️", key=f"delete_{goal['id']}", help="Delete goal"):
                                st.session_state.goals = [g for g in st.session_state.goals if g['id'] != goal['id']]
                                st.rerun()
                    
                    st.markdown("---")
            
            # Projection chart
            if st.session_state.goals:
                st.markdown("### 📈 Savings Projection")
                
                selected_goal = st.selectbox("Select goal to visualize", 
                                           [g['name'] for g in st.session_state.goals])
                
                goal_data = next(g for g in st.session_state.goals if g['name'] == selected_goal)
                
                fig = self.viz_engine.create_progress_timeline(
                    goal_data['current'],
                    goal_data['amount'],
                    goal_data['months']
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No goals yet. Add your first financial goal above!")
    
    def render_chat(self):
        """Render FYNyx chatbot page"""
        st.markdown("## 🤖 FYNyx - Your AI Financial Assistant")
        
        # Display chat history
        if st.session_state.chat_history:
            st.markdown("### 💬 Recent Conversations")
            
            for i, chat in enumerate(reversed(st.session_state.chat_history[-5:])):
                with st.expander(f"Q: {chat['question'][:60]}...", expanded=(i == 0)):
                    st.markdown(f"**You:** {chat['question']}")
                    st.markdown(f"**FYNyx:** {chat['response']}")
                    st.caption(f"🕒 {chat['timestamp']}")
        
        # Chat interface
        with st.container():
            st.markdown("### 💭 Ask FYNyx Anything About Finance")
# ===== ENTRYPOINT =====
def render_current_page(app: "FynstraApp"):
    app.render_sidebar()
    page = st.session_state.get("current_page", "dashboard")
    if page == "dashboard":
        app.render_dashboard()
    elif page == "calculator":
        app.render_calculator()
    elif page == "goals":
        app.render_goals()
    elif page == "chat":
        app.render_chat()
    else:
        app.render_dashboard()
# ===============================
# FLOATING FYNYX CHAT (lower-right, Streamlit-widgets only)
# ===============================
def render_floating_chat(app: "FynstraApp"):
    # --- session state ---
    ss = st.session_state
    ss.setdefault("fyn_chat_open", False)
    ss.setdefault("fyn_chat_messages", [])  # list[{"role": "user"|"assistant", "content": str, "ts": str}]
    ss.setdefault("fyn_unread", 0)

    def ask_fyn(user_text: str) -> str:
        context = {
            "FHI": ss.get("FHI", 0),
            "income": ss.get("monthly_income", 0),
            "expenses": ss.get("monthly_expenses", 0),
            "savings": ss.get("current_savings", 0),
        }
        try:
            reply, _ = app.ai_assistant.get_response(user_text, context)
            return reply
        except Exception as e:
            st.error(f"AI error: {e}")
            return app.ai_assistant._get_fallback_response(user_text, context)

    # Root fixed container anchored bottom-right
    root = st.container()
    with root:
        st.markdown('<div class="fyn-chat-anchor"></div>', unsafe_allow_html=True)

        # Fixed panel styles (no :has selector, wide compatibility)
        open_w, open_h = 380, 520
        st.markdown(f"""
        <style>
          /* Pin the parent block that contains .fyn-chat-anchor */
          div.block-container div:has(> .fyn-chat-anchor) {{
            position: fixed; right: 16px; bottom: 16px;
            width: {open_w if ss.fyn_chat_open else 64}px;
            height: {open_h if ss.fyn_chat_open else 64}px;
            z-index: 1000; border-radius: 16px;
            box-shadow: 0 12px 30px rgba(0,0,0,.18);
            overflow: hidden; transition: all .2s ease-in-out;
            background: {"#ffffff" if ss.fyn_chat_open else "linear-gradient(135deg,#667eea,#764ba2)"};
            border: {"1px solid #e2e8f0" if ss.fyn_chat_open else "none"};
          }}
          .fyn-mini {{
            display: { "flex" if not ss.fyn_chat_open else "none" };
            height: 100%; width: 100%; align-items: center; justify-content: center; gap: 6px;
          }}
          .fyn-unread {{
            position: absolute; top: 4px; right: 4px;
            min-width: 18px; height: 18px; padding: 0 5px;
            background:#ef4444; color:#fff; border-radius: 9px; font-size: 11px; line-height: 18px;
          }}
          .fyn-head {{ display:flex; align-items:center; justify-content:space-between;
            background: linear-gradient(135deg,#667eea,#764ba2); color:#fff; padding:10px 12px; }}
          .fyn-body {{ height: {open_h - 124}px; overflow-y:auto; background:#fafbff; padding:10px 12px 0 12px; }}
          .fyn-foot {{ padding:8px 12px 12px 12px; background:#fff; border-top:1px solid #eef2f7; }}
          .fyn-bot {{ background:#fff; border:1px solid #edf0f7; border-radius:12px 12px 12px 2px; padding:8px 10px; margin:8px 40px 8px 0; }}
          .fyn-user {{ background:#e9ecff; color:#1c2a6b; border-radius:12px 12px 2px 12px; padding:8px 10px; margin:8px 0 8px 40px; }}
          .fyn-quick {{ display:inline-block; margin:6px 6px 0 0; padding:6px 10px; font-size:12px;
                        background:#f1f4ff; border:1px solid #dfe6ff; border-radius:999px; }}
          /* Make the tiny open/close buttons look like icons */
          .stButton>button.small {{"{"
        }}padding:6px 10px; border-radius:10px; font-size:14px;{{"}"}}
        </style>
        """, unsafe_allow_html=True)

        # -------- CLOSED (mini FAB with real Streamlit button) --------
        if not ss.fyn_chat_open:
            col = st.columns([1])[0]
            with col:
                st.markdown('<div class="fyn-mini">', unsafe_allow_html=True)
                # Real Streamlit button that toggles open state
                if st.button("⌧", key="fyn_open_btn", help="Open FYNyx", use_container_width=True):
                    ss.fyn_chat_open = True
                    ss.fyn_unread = 0
                    st.rerun()
                st.markdown(
                    f"{f'<div class=\"fyn-unread\">{ss.fyn_unread}</div>' if ss.fyn_unread else ''}",
                    unsafe_allow_html=True
                )
                st.markdown('</div>', unsafe_allow_html=True)
            return

        # -------- OPEN (chat panel) --------
        # Header with Close + Clear
        c1, c2, c3 = st.columns([6, 1, 1])
        with c1:
            st.markdown('<div class="fyn-head"><b>FYNyx • Financial Assistant</b><span>🇵🇭</span></div>', unsafe_allow_html=True)
        with c2:
            if st.button("✖", key="fyn_close", help="Close", use_container_width=True):
                ss.fyn_chat_open = False
                st.rerun()
        with c3:
            if st.button("🧹", key="fyn_clear", help="Clear conversation", use_container_width=True):
                ss.fyn_chat_messages = []
                st.rerun()

        # Messages
        st.markdown('<div class="fyn-body">', unsafe_allow_html=True)
        if not ss.fyn_chat_messages:
            st.markdown("<div class='fyn-bot'>Hi! Ask me about savings, debt, investments, or your FHI. 😊</div>", unsafe_allow_html=True)
            st.markdown(
                "<div>"
                "<span class='fyn-quick'>How do I build my emergency fund?</span>"
                "<span class='fyn-quick'>Am I saving enough each month?</span>"
                "<span class='fyn-quick'>What investments are good for beginners?</span>"
                "</div>",
                unsafe_allow_html=True
            )
        else:
            for m in ss.fyn_chat_messages[-80:]:
                klass = "fyn-user" if m["role"] == "user" else "fyn-bot"
                st.markdown(f"<div class='{klass}'><div style='font-size:12px;opacity:.55'>{m['ts']}</div>{m['content']}</div>",
                            unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Input + Send row
        st.markdown('<div class="fyn-foot">', unsafe_allow_html=True)
        with st.form("fyn_chat_form", clear_on_submit=True):
            i1, i2 = st.columns([6, 1])
            with i1:
                txt = st.text_input("Type your message",
                                    key="fyn_text_input",
                                    label_visibility="collapsed",
                                    placeholder="Ask about savings, debt, or investing…")
            with i2:
                send = st.form_submit_button("➤", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        if send and txt.strip():
            user_text = txt.strip()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            ss.fyn_chat_messages.append({"role": "user", "content": user_text, "ts": ts})
            reply = ask_fyn(user_text)
            ts2 = datetime.now().strftime("%Y-%m-%d %H:%M")
            ss.fyn_chat_messages.append({"role": "assistant", "content": reply, "ts": ts2})
            st.rerun()

if __name__ == "__main__":
    app = FynstraApp()
    render_current_page(app)
    render_floating_chat(app)

