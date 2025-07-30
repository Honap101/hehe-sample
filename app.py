import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import json

# AI Integration
try:
    import google.generativeai as genai
    AI_AVAILABLE = True
    # Configure Gemini API - USE ENVIRONMENT VARIABLES!
    genai.configure(api_key=st.secrets.get("GEMINI_API_KEY", "your-api-key-here"))
    model = genai.GenerativeModel('gemini-pro')
except ImportError:
    AI_AVAILABLE = False
    st.warning("Google AI not available. Install with: pip install google-generativeai")

def initialize_conversation_state():
    """Initialize conversation state for maintaining context"""
    if "conversation_messages" not in st.session_state:
        st.session_state.conversation_messages = []
    if "conversation_context" not in st.session_state:
        st.session_state.conversation_context = {
            'user_profile': {},
            'financial_data': {},
            'conversation_summary': '',
            'topics_discussed': []
        }
    if "chat_display" not in st.session_state:
        st.session_state.chat_display = []

def update_conversation_context(user_question, ai_response, fhi_context):
    """Update conversation context with new information"""
    # Add to conversation messages
    st.session_state.conversation_messages.extend([
        {"role": "user", "content": user_question},
        {"role": "assistant", "content": ai_response}
    ])
    
    # Update financial context
    st.session_state.conversation_context['financial_data'].update(fhi_context)
    
    # Extract topics from user question
    topics = extract_topics_from_question(user_question)
    for topic in topics:
        if topic not in st.session_state.conversation_context['topics_discussed']:
            st.session_state.conversation_context['topics_discussed'].append(topic)
    
    # Limit conversation history to last 20 messages (10 exchanges) to manage token limits
    if len(st.session_state.conversation_messages) > 20:
        st.session_state.conversation_messages = st.session_state.conversation_messages[-20:]

def extract_topics_from_question(question):
    """Extract financial topics from user question"""
    topics = []
    question_lower = question.lower()
    
    topic_keywords = {
        'emergency_fund': ['emergency', 'emergency fund', 'unexpected expenses'],
        'debt': ['debt', 'loan', 'credit card', 'owe', 'payment'],
        'investment': ['invest', 'stocks', 'bonds', 'portfolio', 'mutual fund'],
        'savings': ['save', 'savings', 'save money'],
        'retirement': ['retirement', 'pension', 'sss', 'pag-ibig'],
        'insurance': ['insurance', 'coverage', 'protection'],
        'budgeting': ['budget', 'expense', 'spending', 'money management']
    }
    
    for topic, keywords in topic_keywords.items():
        if any(keyword in question_lower for keyword in keywords):
            topics.append(topic)
    
    return topics

def build_conversation_prompt(user_question, fhi_context):
    """Build a comprehensive prompt with full conversation context"""
    
    # Get conversation history
    conversation_history = ""
    if st.session_state.conversation_messages:
        conversation_history = "\n".join([
            f"{'User' if msg['role'] == 'user' else 'FYNyx'}: {msg['content']}"
            for msg in st.session_state.conversation_messages[-10:]  # Last 5 exchanges
        ])
    
    # Get topics discussed
    topics_discussed = st.session_state.conversation_context.get('topics_discussed', [])
    
    fhi_score = fhi_context.get('FHI', 'Not calculated')
    income = fhi_context.get('income', 0)
    expenses = fhi_context.get('expenses', 0)
    savings = fhi_context.get('savings', 0)
    
    prompt = f"""
You are FYNyx, an AI financial advisor specifically designed for Filipino users. You provide practical, culturally-aware financial advice and maintain conversation context.

IMPORTANT CONTEXT:
- User is Filipino, use Philippine financial context
- Mention Philippine financial products when relevant (SSS, Pag-IBIG, GSIS, BPI, BDO, etc.)
- Use Philippine Peso (₱) in examples
- Consider Philippine economic conditions
- You are having an ongoing conversation - reference previous topics when relevant

USER'S FINANCIAL PROFILE:
- FHI Score: {fhi_score}/100
- Monthly Income: ₱{income:,.0f}
- Monthly Expenses: ₱{expenses:,.0f}
- Monthly Savings: ₱{savings:,.0f}

CONVERSATION HISTORY:
{conversation_history if conversation_history else "This is the start of your conversation."}

TOPICS PREVIOUSLY DISCUSSED:
{', '.join(topics_discussed) if topics_discussed else "None yet"}

CURRENT USER QUESTION: {user_question}

INSTRUCTIONS:
- Reference previous conversation when relevant (e.g., "As we discussed earlier...")
- Provide specific, actionable advice
- Keep response under 200 words unless user asks for detailed explanation
- Use friendly, encouraging tone
- Include specific numbers/percentages when helpful
- If user asks follow-up questions, build on previous advice
- If FHI score is low (<50), prioritize emergency fund and debt reduction
- If FHI score is medium (50-70), focus on investment and optimization
- If FHI score is high (>70), discuss advanced strategies

Respond naturally as if continuing an ongoing conversation with someone you're helping with their finances.
"""
    
    return prompt

def get_ai_response_with_context(user_question, fhi_context):
    """Get AI response with full conversation context"""
    if not AI_AVAILABLE:
        return get_contextual_fallback_response(user_question, fhi_context)
    
    try:
        # Rate limiting (same as before)
        import time
        current_time = time.time()
        
        if 'last_ai_call' not in st.session_state:
            st.session_state.last_ai_call = 0
        if 'ai_call_count' not in st.session_state:
            st.session_state.ai_call_count = 0
        if 'daily_reset' not in st.session_state:
            st.session_state.daily_reset = current_time
        
        # Daily reset
        if current_time - st.session_state.daily_reset > 86400:
            st.session_state.ai_call_count = 0
            st.session_state.daily_reset = current_time
        
        # Check limits
        if st.session_state.ai_call_count >= 100:
            st.warning("🤖 FYNyx has reached today's AI quota. Using smart fallback responses.")
            return get_contextual_fallback_response(user_question, fhi_context)
        
        if current_time - st.session_state.last_ai_call < 4:
            remaining_time = 4 - (current_time - st.session_state.last_ai_call)
            st.info(f"🤖 Please wait {remaining_time:.1f} seconds before next question...")
            time.sleep(remaining_time)
        
        # Build contextual prompt
        prompt = build_conversation_prompt(user_question, fhi_context)
        
        # Make API call
        response = model.generate_content(prompt)
        
        # Update counters
        st.session_state.last_ai_call = current_time
        st.session_state.ai_call_count += 1
        
        return response.text
        
    except Exception as e:
        error_msg = str(e).lower()
        if "quota" in error_msg or "limit" in error_msg:
            st.warning("🤖 FYNyx has reached the free API limit. Using smart fallback responses.")
        elif "rate" in error_msg:
            st.info("🤖 FYNyx is being rate limited. Please wait a moment.")
        else:
            st.warning(f"🤖 FYNyx encountered an issue. Using fallback response.")
        
        return get_contextual_fallback_response(user_question, fhi_context)

def get_contextual_fallback_response(user_question, fhi_context):
    """Enhanced fallback responses that consider conversation context"""
    question_lower = user_question.lower()
    fhi_score = fhi_context.get('FHI', 0)
    income = fhi_context.get('income', 0)
    expenses = fhi_context.get('expenses', 0)
    
    # Check if this is a follow-up question
    conversation_history = st.session_state.conversation_messages
    topics_discussed = st.session_state.conversation_context.get('topics_discussed', [])
    
    is_followup = len(conversation_history) > 0 and any(
        word in question_lower for word in ['more', 'how', 'what about', 'also', 'additionally', 'further']
    )
    
    # Context-aware responses
    if is_followup and 'emergency' in topics_discussed:
        if "how" in question_lower or "build" in question_lower:
            return "Since we discussed emergency funds earlier, here's how to build it faster: Set up automatic transfers right after payday, even if it's just ₱1,000 weekly. Use a separate high-yield savings account so you're not tempted to spend it. Consider side gigs or selling unused items to boost your emergency fund quickly."
    
    if is_followup and 'investment' in topics_discussed:
        if "start" in question_lower or "begin" in question_lower:
            return "Following up on our investment discussion: Start with index funds like FMETF through your bank's online platform. Begin with ₱2,000 monthly and increase gradually. COL Financial and BPI Trade are good platforms for beginners. Focus on cost averaging - invest the same amount monthly regardless of market conditions."
    
    # Standard fallback responses (same as before but with context references)
    if "emergency" in question_lower:
        target_emergency = expenses * 6
        monthly_target = target_emergency / 12
        context_note = " (building on our previous discussion)" if 'emergency' in topics_discussed else ""
        return f"Build an emergency fund of ₱{target_emergency:,.0f} (6 months of expenses){context_note}. Save ₱{monthly_target:,.0f} monthly to reach this in a year. Keep it in a high-yield savings account like BPI or BDO."
    
    elif "debt" in question_lower:
        if fhi_score < 50:
            return "Focus on high-interest debt first (credit cards, personal loans). Pay minimums on everything, then put extra money toward the highest interest rate debt. Consider debt consolidation with lower rates."
        else:
            return "You're managing debt well! Continue current payments and avoid taking on new high-interest debt. Consider investing surplus funds."
    
    elif "invest" in question_lower or "investment" in question_lower:
        context_note = " As we discussed before," if 'investment' in topics_discussed else ""
        if income < 30000:
            return f"{context_note} start small with ₱1,000/month in index funds like FMETF or mutual funds from BPI/BDO. Focus on emergency fund first, then gradually increase investments."
        else:
            return f"{context_note} consider diversifying: 60% stocks (FMETF, blue chips like SM, Ayala), 30% bonds (government treasury), 10% alternative investments. Start with ₱5,000-10,000 monthly."
    
    else:
        # General contextual response
        if is_followup:
            return "I understand you'd like to know more about this topic. Could you be more specific about what aspect you'd like me to elaborate on? I'm here to help you build on what we've discussed."
        else:
            if fhi_score < 50:
                return "Focus on basics: emergency fund (3-6 months expenses), pay down high-interest debt, and track your spending. Build a solid foundation before investing."
            elif fhi_score < 70:
                return "You're on the right track! Optimize your budget, increase investments gradually, and consider insurance for protection. Review and adjust quarterly."
            else:
                return "Great financial health! Consider advanced strategies: real estate investment, business opportunities, or international diversification."

def display_chat_interface():
    """Display the enhanced chat interface with conversation context"""
    st.subheader("🤖 FYNyx - Your AI Financial Assistant")
    
    # Initialize conversation state
    initialize_conversation_state()
    
    # Display conversation history
    if st.session_state.chat_display:
        st.markdown("### 💬 Our Conversation")
        
        # Create a scrollable chat container
        chat_container = st.container()
        with chat_container:
            for i, message in enumerate(st.session_state.chat_display):
                if message['role'] == 'user':
                    # User message
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"""
                        <div style='background-color: #e3f2fd; padding: 10px; border-radius: 10px; margin: 5px 0;'>
                        <strong>You:</strong> {message['content']}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # AI message
                    col1, col2 = st.columns([1, 4])
                    with col2:
                        st.markdown(f"""
                        <div style='background-color: #f1f8e9; padding: 10px; border-radius: 10px; margin: 5px 0;'>
                        <strong>🤖 FYNyx:</strong> {message['content']}
                        </div>
                        """, unsafe_allow_html=True)
        
        st.markdown("---")
    
    # Current conversation input
    with st.container():
        st.markdown("### 💭 Continue Our Conversation")
        
        # Show conversation context if available
        if st.session_state.conversation_context['topics_discussed']:
            st.info(f"📝 **Topics we've discussed:** {', '.join(st.session_state.conversation_context['topics_discussed'])}")
        
        # Input area
        user_question = st.text_area(
            "Ask FYNyx or continue our conversation:",
            placeholder="e.g., 'Can you tell me more about that investment strategy?' or 'What about emergency funds?'",
            height=100,
            key="conversation_input"
        )
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            send_button = st.button("💬 Send Message", type="primary")
        with col2:
            if st.button("🔄 New Topic"):
                st.session_state.conversation_messages = []
                st.session_state.conversation_context = {
                    'user_profile': {},
                    'financial_data': {},
                    'conversation_summary': '',
                    'topics_discussed': []
                }
                st.success("Started fresh conversation!")
                st.rerun()
        with col3:
            if st.button("🗑️ Clear All History"):
                st.session_state.chat_display = []
                st.session_state.conversation_messages = []
                st.session_state.conversation_context = {
                    'user_profile': {},
                    'financial_data': {},
                    'conversation_summary': '',
                    'topics_discussed': []
                }
                st.success("All conversation history cleared!")
                st.rerun()
        
        if send_button and user_question.strip():
            with st.spinner("🤖 FYNyx is thinking..."):
                # Prepare context
                fhi_context = {
                    'FHI': st.session_state.get('FHI', 0),
                    'income': st.session_state.get('monthly_income', 0),
                    'expenses': st.session_state.get('monthly_expenses', 0),
                    'savings': st.session_state.get('current_savings', 0)
                }
                
                # Get AI response with context
                response = get_ai_response_with_context(user_question, fhi_context)
                
                # Update conversation context
                update_conversation_context(user_question, response, fhi_context)
                
                # Add to display history
                st.session_state.chat_display.extend([
                    {'role': 'user', 'content': user_question, 'timestamp': datetime.now()},
                    {'role': 'assistant', 'content': response, 'timestamp': datetime.now()}
                ])
                
                # Keep display history manageable
                if len(st.session_state.chat_display) > 20:
                    st.session_state.chat_display = st.session_state.chat_display[-20:]
                
                st.rerun()
    
    # Quick conversation starters
    if not st.session_state.conversation_messages:
        st.markdown("### 🚀 Start Our Conversation")
        starter_questions = [
            "What should I prioritize first with my finances?",
            "How can I start investing with a small budget?",
            "What's the best way to build an emergency fund?",
            "Should I pay off debt or save first?",
            "How do I create a realistic budget?"
        ]
        
        cols = st.columns(2)
        for i, question in enumerate(starter_questions):
            if cols[i % 2].button(f"💡 {question}", key=f"starter_{i}"):
                st.session_state.conversation_input = question
                st.rerun()

# Usage in main app:
# Replace the existing chatbot page with:
if page == "FYNyx Chatbot":
    display_chat_interface()
    
    # Show context awareness
    if "FHI" in st.session_state:
        st.markdown("---")
        st.markdown("**🎯 FYNyx knows your financial context:**")
        context_col1, context_col2, context_col3 = st.columns(3)
        with context_col1:
            st.metric("Your FHI", f"{st.session_state['FHI']}")
        with context_col2:
            st.metric("Monthly Income", f"₱{st.session_state.get('monthly_income', 0):,.0f}")
        with context_col3:
            st.metric("Monthly Savings", f"₱{st.session_state.get('current_savings', 0):,.0f}")
