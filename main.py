import appdirs as ad
ad.user_cache_dir = lambda *args: "/tmp"

import streamlit as st
import pandas as pd
from yfinance import Ticker
import plotly.express as px
import requests
import os
import time
import random
import sqlite3
from datetime import datetime

st.set_page_config(page_title="AI Stock Dashboard", layout="wide")
st.title("🚀 My Personal AI Stock Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M %p EST')}")

# ----------------- DATABASE (unchanged) -----------------
def get_db_connection():
    conn = sqlite3.connect('portfolio.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS holdings (ticker TEXT PRIMARY KEY, shares REAL, cost_basis REAL);
        CREATE TABLE IF NOT EXISTS cash_balance (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS pending_orders (id INTEGER PRIMARY KEY, ticker TEXT, order_type TEXT, shares REAL, limit_price REAL, status TEXT DEFAULT 'Pending');
    ''')
    conn.commit()
    conn.close()

def load_holdings():
    init_db()
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM holdings", conn)
    conn.close()
    return df

def save_holding(ticker, shares, cost_basis):
    conn = get_db_connection()
    conn.execute("REPLACE INTO holdings (ticker, shares, cost_basis) VALUES (?, ?, ?)",
                 (ticker.upper(), shares, cost_basis))
    conn.commit()
    conn.close()

def clear_all_holdings():
    conn = get_db_connection()
    conn.execute("DELETE FROM holdings")
    conn.execute("DELETE FROM pending_orders")
    conn.commit()
    conn.close()

def get_cash_balance():
    init_db()
    conn = get_db_connection()
    row = conn.execute("SELECT cash FROM cash_balance WHERE id=1").fetchone()
    conn.close()
    return row['cash'] if row else 0.0

def update_cash_balance(new_cash):
    conn = get_db_connection()
    conn.execute("REPLACE INTO cash_balance (id, cash) VALUES (1, ?)", (new_cash,))
    conn.commit()
    conn.close()

def add_pending_order(ticker, order_type, shares, limit_price):
    conn = get_db_connection()
    conn.execute("""INSERT INTO pending_orders (ticker, order_type, shares, limit_price) 
                    VALUES (?, ?, ?, ?)""", (ticker.upper(), order_type, shares, limit_price))
    conn.commit()
    conn.close()

def load_pending_orders():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM pending_orders ORDER BY id", conn)
    conn.close()
    return df

def delete_pending_order(order_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM pending_orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

def clear_all_pending_orders():
    conn = get_db_connection()
    conn.execute("DELETE FROM pending_orders")
    conn.commit()
    conn.close()

# ----------------- PORTFOLIO CALCULATION -----------------
@st.cache_data(ttl=300)
def calculate_portfolio():
    df = load_holdings()
    if df.empty:
        return pd.DataFrame(columns=['Ticker','Shares','Cost Basis','Current Price','Current Value','Unrealized Gain $','Unrealized Gain %'])
    
    data = []
    for _, row in df.iterrows():
        ticker_symbol = row['ticker']
        try:
            time.sleep(random.uniform(0.6, 1.2))
            ticker = Ticker(ticker_symbol)
            info = ticker.info
            current_price = float(info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0.0)
            
            current_value = row['shares'] * current_price
            cost = row['shares'] * row['cost_basis']
            gain_dollar = current_value - cost
            gain_pct = (gain_dollar / cost * 100) if cost > 0 else 0.0
            
            data.append({
                'Ticker': ticker_symbol,
                'Shares': round(row['shares'], 4),
                'Cost Basis': round(row['cost_basis'], 2),
                'Current Price': round(current_price, 2),
                'Current Value': round(current_value, 2),
                'Unrealized Gain $': round(gain_dollar, 2),
                'Unrealized Gain %': round(gain_pct, 2)
            })
        except Exception:
            data.append({
                'Ticker': ticker_symbol,
                'Shares': round(row['shares'], 4),
                'Cost Basis': round(row['cost_basis'], 2),
                'Current Price': "N/A",
                'Current Value': "N/A",
                'Unrealized Gain $': "N/A",
                'Unrealized Gain %': "N/A"
            })
    
    return pd.DataFrame(data)

# ----------------- GROK API -----------------
def call_grok(prompt, conversation_history=None):
    api_key = os.environ.get("GROK_API_KEY")
    if not api_key:
        return "❌ Grok API key not found."
    
    model = "grok-4-1-fast-reasoning"
    messages = conversation_history or []
    messages.append({"role": "user", "content": prompt})
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 7000},
            timeout=150
        )
        if response.status_code != 200:
            return f"❌ API Error {response.status_code}"
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ Request Error: {str(e)}"

# ----------------- FULL ANALYSIS -----------------
def run_full_analysis():
    today = datetime.now().strftime("%B %d, %Y")
    portfolio_df = calculate_portfolio()
    cash = get_cash_balance()
    pending_df = load_pending_orders()
    
    portfolio_text = portfolio_df.to_string(index=False) if not portfolio_df.empty else "No holdings yet."
    pending_text = pending_df.to_string(index=False) if not pending_df.empty else "No pending orders."
    
    prompt = f"""You are a professional market analyst and portfolio manager with a **high risk tolerance**. Today's date is {today}.

Current Portfolio Snapshot:
Cash Available: ${cash:,.2f}
Holdings:
{portfolio_text}
Pending Orders:
{pending_text}

**Part 1: Market Overview**
1. Identify the stock sectors with the **highest short-term momentum** right now and explain why they are leading.
2. Build a high-probability watchlist: Recommend 10 stocks with strong volatility, volume, and catalyst potential, prioritizing those in the top momentum sectors.
3. Create 5 actionable day trading setups with specific entry zones, stop losses, and profit targets.
4. Suggest an aggressive capital management strategy suitable for high risk tolerance.
5. List upcoming earnings, macro events, or news catalysts this week.

**Part 2: Personalized Recommendations (High Risk Tolerance)**
Focus heavily on opportunities in the **highest short-term momentum sectors**. 
For each existing holding and potential new opportunities:
- Give a clear **Buy / Sell / Hold / Trim / Add** recommendation with an aggressive bias when momentum is strong.
- Suggest specific entry or exit price zones or technical triggers.
- State **how much** to buy or sell (be specific with share counts or % of cash/portfolio).
- Recommend diversification moves, but allow concentration in top momentum sectors when the setup is strong.
- Provide clear reasoning tied to current momentum, valuation, catalysts, risk, and your cash/pending orders.
- Assign a risk level (Low / Medium / High) and suggest stop-loss ideas.

**Overall Portfolio Strategy**
- Aggressive cash deployment suggestions focused on highest momentum sectors.
- Advice on pending orders (keep, modify, or cancel).
- Rebalancing summary — lean into strong momentum while maintaining basic risk controls.
- How to compound daily gains responsibly into long-term growth with a high risk tolerance approach.

Be detailed, realistic, and actionable. Use clear headings and bullet points. Prioritize momentum-driven opportunities."""

    with st.spinner("Generating full analysis..."):
        result = call_grok(prompt)
        st.session_state.full_analysis = result
        st.session_state.conversation_history = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": result}
        ]
        return result

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.header("Controls")
    if st.button("🔥 Run Full Daily Analysis + Portfolio Advice", type="primary"):
        run_full_analysis()
        st.success("✅ Full analysis ready!")
    
    if st.button("🔄 Refresh Portfolio Prices"):
        st.cache_data.clear()
        st.success("Prices refreshed!")

# ----------------- TABS -----------------
tab1, tab2 = st.tabs(["📈 Full Analysis", "💼 My Portfolio"])

with tab1:
    st.header("Full Daily Market + Portfolio Analysis")
    if "full_analysis" in st.session_state:
        st.markdown(st.session_state.full_analysis)
        
        st.divider()
        st.subheader("💬 Ask Grok for Clarification")
        
        # Tooltip / Helper text in light grey italic
        st.markdown(
            """
            <p style="color: #888888; font-style: italic; font-size: 0.95em;">
            You can ask follow-up questions like:<br>
            • “Why did you recommend selling AAPL?”<br>
            • “Can you explain the entry zone for NVDA?”<br>
            • “Should I add more to energy sector?”
            </p>
            """, 
            unsafe_allow_html=True
        )
        
        user_question = st.text_input("Your question:", placeholder="Type your question here...")
        
        if st.button("Send Question to Grok"):
            if user_question.strip():
                with st.spinner("Getting clarification from Grok..."):
                    response = call_grok(user_question, st.session_state.get("conversation_history", []))
                    st.session_state.conversation_history.append({"role": "user", "content": user_question})
                    st.session_state.conversation_history.append({"role": "assistant", "content": response})
                    st.markdown("**Grok's Response:**")
                    st.markdown(response)
            else:
                st.warning("Please enter a question.")
    else:
        st.info("Click the button in the sidebar to generate today's full report.")

with tab2:
    st.header("Portfolio Tracker")
    # [Your existing portfolio tab code remains unchanged]
    # Cash, holdings, pending orders, metrics, charts, etc.
    # (Copy the entire tab2 section from the previous working version)

    st.info(f"💰 Available Cash: ${get_cash_balance():,.2f}")

st.caption("Built with Streamlit + yfinance + Grok API • Educational use only")
