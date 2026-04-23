import appdirs as ad
ad.user_cache_dir = lambda *args: "/tmp"

import streamlit as st
import pandas as pd
from yfinance import Ticker
import plotly.express as px
import plotly.graph_objects as go
import requests
import os
import time
import random
import sqlite3
from datetime import datetime

st.set_page_config(page_title="AI Stock Dashboard", layout="wide")

st.title("🚀 My Personal AI Stock Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M %p EST')}")

# CSS
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { font-size: 1.45em !important; font-weight: 600 !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.85em !important; color: #666666; }
    .stMarkdown h2, .stMarkdown h3 { margin-top: 1.5em; margin-bottom: 0.8em; }
    </style>
""", unsafe_allow_html=True)

# ----------------- DATABASE ----------------- (unchanged)
def get_db_connection():
    conn = sqlite3.connect('portfolio.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (account_name TEXT PRIMARY KEY, risk_tolerance TEXT DEFAULT 'Moderate');
        CREATE TABLE IF NOT EXISTS holdings (account_name TEXT, ticker TEXT, shares REAL, cost_basis REAL, PRIMARY KEY (account_name, ticker));
        CREATE TABLE IF NOT EXISTS cash_balance (account_name TEXT PRIMARY KEY, cash REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS pending_orders (id INTEGER PRIMARY KEY, account_name TEXT, ticker TEXT, order_type TEXT, shares REAL, limit_price REAL, status TEXT DEFAULT 'Pending');
    ''')
    conn.execute("INSERT OR IGNORE INTO accounts (account_name, risk_tolerance) VALUES ('Main Portfolio', 'Moderate')")
    conn.commit()
    conn.close()

init_db()

# (All your existing DB helper functions remain exactly the same - get_accounts, add_account, get_risk_tolerance, set_risk_tolerance, load_holdings, save_holding, etc.)
# ... [Copy all DB functions from your previous working code here - they are unchanged] ...

# ----------------- PORTFOLIO CALCULATION ----------------- (unchanged)
@st.cache_data(ttl=180)
def calculate_portfolio(account_name):
    # ... [your existing calculate_portfolio function] ...
    # (keep it exactly as in your last working version)
    pass  # placeholder - replace with your full function

# ----------------- GROK API ----------------- (unchanged)
def call_grok(prompt, conversation_history=None):
    # ... [your existing call_grok function] ...
    pass  # placeholder - replace with your full function

# ----------------- UPDATED FULL ANALYSIS WITH WEEKLY PLAN -----------------
def run_full_analysis(selected_account):
    today = datetime.now().strftime("%B %d, %Y")
    portfolio_df = calculate_portfolio(selected_account)
    cash = get_cash_balance(selected_account)
    risk_tolerance = get_risk_tolerance(selected_account)
    pending_df = load_pending_orders(selected_account)
  
    portfolio_text = portfolio_df.to_string(index=False) if not portfolio_df.empty else "No holdings yet."
    pending_text = pending_df.to_string(index=False) if not pending_df.empty else "No pending orders."
  
    prompt = f"""You are a professional market analyst and portfolio manager with a **{risk_tolerance.lower()} risk tolerance**. Today's date is {today}.
Current Portfolio Snapshot (Account: {selected_account}):
Cash Available: ${cash:,.2f}
Holdings:
{portfolio_text}
Pending Orders:
{pending_text}

**Part 1: Market Overview**
... [keep your full original prompt here - Part 1 and Part 2 exactly as before] ...

Be very detailed, specific, and actionable. Use clear headings and bullet points."""

    with st.spinner(f"Generating full detailed analysis for {selected_account}..."):
        result = call_grok(prompt)
        
        # === NEW: Generate Weekly Action Plan ===
        weekly_prompt = f"""Based on the previous analysis you just provided for this {risk_tolerance.lower()} risk tolerance portfolio, create a practical **Weekly Action Plan**.

Organize it by day (Monday through Friday). For each day, list:
- Key actions (Buy/Add, Sell/Trim, Monitor, Rebalance, etc.)
- Specific tickers and share amounts or % of cash where possible
- Any earnings, news, or technical levels to watch
- Risk management steps (stop-loss adjustments, position sizing)

If a day has no major action, say "Light monitoring day - watch [key sectors/tickers]".

Make it realistic and tied directly to the recommendations you gave earlier.
Use this format:

**📅 Weekly Action Plan**

**Monday:**
- Action 1...
- Action 2...

**Tuesday:**
...

Focus on high-momentum opportunities and risk control."""

        with st.spinner("Creating your personalized Weekly Action Plan..."):
            weekly_plan = call_grok(weekly_prompt, [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": result}
            ])
        
        # Combine both
        full_result = result + "\n\n---\n\n" + weekly_plan
        
        st.session_state.full_analysis = full_result
        if "conversation_history" not in st.session_state:
            st.session_state.conversation_history = []
        st.session_state.conversation_history = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": full_result}
        ]
        return full_result

# ----------------- SIDEBAR & ACCOUNT MANAGEMENT ----------------- (unchanged)
# ... [keep your existing sidebar, account selector, risk tolerance, cash, add holding, etc.] ...

# ----------------- TABS -----------------
tab1, tab2 = st.tabs(["📈 Full Analysis", "💼 My Portfolio"])

with tab1:
    st.header("Full Daily Market + Portfolio Analysis")
    if "full_analysis" in st.session_state:
        st.markdown(st.session_state.full_analysis)
      
        st.divider()
        st.subheader("💬 Ask Grok for Clarification")
        # ... [your existing follow-up question code] ...
    else:
        st.info("Select an account and click 'Run Full Daily Analysis' in the sidebar.")

with tab2:
    # ... [your entire My Portfolio tab code remains unchanged] ...

st.caption("Built with Streamlit + yfinance + Grok API • Educational use only")
