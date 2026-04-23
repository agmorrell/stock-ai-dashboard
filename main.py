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
import re
from datetime import datetime

st.set_page_config(page_title="AI Stock Dashboard", layout="wide")
st.title("🚀 My Personal AI Stock Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M %p EST')}")

# Clean CSS
st.markdown("""
    <style>
    .stMarkdown, .stMarkdown p, .stMarkdown li {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 1.06em;
        line-height: 1.78;
        margin-bottom: 0.9em;
    }
    .stMarkdown p, .stMarkdown li {
        white-space: pre-wrap;
        word-break: break-word;
        overflow-wrap: break-word;
    }
    .stMarkdown h1 { font-size: 1.9em; margin: 2.2em 0 0.9em 0; color: #1f77b4; }
    .stMarkdown h2 { font-size: 1.6em; margin: 1.9em 0 0.8em 0; color: #1f77b4; }
    .stMarkdown h3 { 
        font-size: 1.4em; 
        margin: 1.7em 0 0.7em 0; 
        color: #1f77b4; 
        border-left: 5px solid #1f77b4; 
        padding-left: 12px; 
    }
    .stMarkdown ul, .stMarkdown ol {
        padding-left: 2.0em;
        margin-bottom: 1.2em;
    }
    .stMarkdown li { margin-bottom: 0.65em; }
    .stMarkdown h3 + ul, .stMarkdown h3 + ol {
        background-color: #f8f9fa;
        padding: 1.3em 1.6em;
        border-radius: 8px;
        border-left: 5px solid #1f77b4;
        margin: 1.3em 0;
    }
    </style>
""", unsafe_allow_html=True)

# Generic cleaner (kept simple as requested)
def clean_analysis_text(text):
    if not text:
        return text
    text = re.sub(r'([a-zA-Z0-9)])([.,;:/])([a-zA-Z])', r'\1\2 \3', text)
    text = re.sub(r'([a-zA-Z)])([0-9])', r'\1 \2', text)
    text = re.sub(r'([0-9])([a-zA-Z(])', r'\1 \2', text)
    text = re.sub(r'([0-9.])(−|-)([0-9.])', r'\1 - \3', text)
    text = re.sub(r'([0-9a-zA-Z)])([/\\+])([0-9a-zA-Z(])', r'\1 \2 \3', text)
    text = re.sub(r'\)([a-zA-Z0-9])', r') \1', text)
    text = re.sub(r'([a-zA-Z0-9])\(', r'\1 (', text)
    text = re.sub(r'([0-9,]+)\)([a-zA-Z])', r'\1) \2', text)
    text = re.sub(r'([a-z0-9)])([A-Z])', r'\1 \2', text)
    text = re.sub(r'(\w{12,})([A-Z])', r'\1 \2', text)
    return text

# New: Parse 5 Day Trading Setups into a clean table
def parse_trading_setups(text):
    setups = []
    lines = text.split('\n')
    current_setup = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Detect a new setup (ticker + action like Long/Short/Breakout/Play)
        if re.search(r'(Long|Short|Squeeze|Breakout|Play|Fade|Reverse|Gap Fill)', line, re.IGNORECASE) and re.search(r'^[A-Z]{2,5}', line):
            if current_setup:
                setups.append(current_setup)
            # Extract ticker and description
            match = re.match(r'([A-Z]{2,5})\s*(.*)', line)
            if match:
                ticker = match.group(1)
                desc = match.group(2).strip()
                current_setup = {"Ticker": ticker, "Setup": desc, "Entry": "", "Stop": "", "Target": "", "Catalyst": ""}
        elif current_setup:
            if "Entry" in line or "entry" in line.lower():
                current_setup["Entry"] = re.sub(r'Entry[:\s]*', '', line, flags=re.IGNORECASE).strip()
            elif "Stop" in line or "stop" in line.lower():
                current_setup["Stop"] = re.sub(r'Stop[:\s]*', '', line, flags=re.IGNORECASE).strip()
            elif "Target" in line or "target" in line.lower():
                current_setup["Target"] = re.sub(r'Target[:\s]*', '', line, flags=re.IGNORECASE).strip()
            elif "Catalyst" in line or "catalyst" in line.lower():
                current_setup["Catalyst"] = re.sub(r'Catalyst[:\s]*', '', line, flags=re.IGNORECASE).strip()
    
    if current_setup:
        setups.append(current_setup)
    
    if setups:
        return pd.DataFrame(setups)
    return None

# ----------------- DATABASE -----------------
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
        CREATE TABLE IF NOT EXISTS pending_orders (
            id INTEGER PRIMARY KEY, 
            account_name TEXT, 
            ticker TEXT, 
            order_type TEXT, 
            shares REAL, 
            limit_price REAL, 
            status TEXT DEFAULT 'Pending'
        );
    ''')
    conn.execute("INSERT OR IGNORE INTO accounts (account_name, risk_tolerance) VALUES ('Main Portfolio', 'Moderate')")
    conn.commit()
    conn.close()

init_db()

def get_accounts():
    conn = get_db_connection()
    return [row['account_name'] for row in conn.execute("SELECT account_name FROM accounts").fetchall()]

def add_account(account_name):
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO accounts (account_name, risk_tolerance) VALUES (?, 'Moderate')", (account_name,))
    conn.commit()
    conn.close()

def get_risk_tolerance(account_name):
    conn = get_db_connection()
    row = conn.execute("SELECT risk_tolerance FROM accounts WHERE account_name = ?", (account_name,)).fetchone()
    conn.close()
    return row['risk_tolerance'] if row else "Moderate"

def set_risk_tolerance(account_name, risk_tolerance):
    conn = get_db_connection()
    conn.execute("UPDATE accounts SET risk_tolerance = ? WHERE account_name = ?", (risk_tolerance, account_name))
    conn.commit()
    conn.close()

def load_holdings(account_name):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM holdings WHERE account_name = ?", conn, params=(account_name,))
    conn.close()
    return df

def save_holding(account_name, ticker, shares, cost_basis):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO holdings (account_name, ticker, shares, cost_basis) VALUES (?, ?, ?, ?)",
                 (account_name, ticker.upper(), shares, cost_basis))
    conn.commit()
    conn.close()

def delete_holding(account_name, ticker):
    conn = get_db_connection()
    conn.execute("DELETE FROM holdings WHERE account_name = ? AND ticker = ?", (account_name, ticker.upper()))
    conn.commit()
    conn.close()

def get_cash_balance(account_name):
    conn = get_db_connection()
    row = conn.execute("SELECT cash FROM cash_balance WHERE account_name = ?", (account_name,)).fetchone()
    conn.close()
    return row['cash'] if row else 0.0

def update_cash_balance(account_name, new_cash):
    conn = get_db_connection()
    conn.execute("REPLACE INTO cash_balance (account_name, cash) VALUES (?, ?)", (account_name, new_cash))
    conn.commit()
    conn.close()

def add_pending_order(account_name, ticker, order_type, shares, limit_price):
    conn = get_db_connection()
    conn.execute("""INSERT INTO pending_orders (account_name, ticker, order_type, shares, limit_price) 
                    VALUES (?, ?, ?, ?, ?)""", (account_name, ticker.upper(), order_type, shares, limit_price))
    conn.commit()
    conn.close()

def load_pending_orders(account_name):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM pending_orders WHERE account_name = ? ORDER BY id", conn, params=(account_name,))
    conn.close()
    return df

def delete_pending_order(order_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM pending_orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

# ----------------- PORTFOLIO CALCULATION -----------------
@st.cache_data(ttl=180)
def calculate_portfolio(account_name):
    df = load_holdings(account_name)
    if df.empty:
        return pd.DataFrame(columns=['Ticker','Shares','Cost Basis','Current Price','Current Value','Unrealized Gain $','Unrealized Gain %','Sector','Today % Change'])
    
    data = []
    for _, row in df.iterrows():
        try:
            time.sleep(random.uniform(0.5, 1.0))
            ticker = Ticker(row['ticker'])
            info = ticker.info
            current_price = float(info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0)
            sector = info.get('sector') or "Other"
            today_change = float(info.get('regularMarketChangePercent') or 0)
            
            current_value = row['shares'] * current_price
            gain_dollar = current_value - (row['shares'] * row['cost_basis'])
            gain_pct = (gain_dollar / (row['shares'] * row['cost_basis']) * 100) if row['cost_basis'] > 0 else 0
            
            data.append({
                'Ticker': row['ticker'],
                'Shares': round(row['shares'], 4),
                'Cost Basis': round(row['cost_basis'], 2),
                'Current Price': round(current_price, 2),
                'Current Value': round(current_value, 2),
                'Unrealized Gain $': round(gain_dollar, 2),
                'Unrealized Gain %': round(gain_pct, 2),
                'Sector': sector,
                'Today % Change': round(today_change, 2)
            })
        except:
            data.append({'Ticker': row['ticker'], 'Shares': row['shares'], 'Cost Basis': row['cost_basis'],
                         'Current Price': "N/A", 'Current Value': "N/A", 'Unrealized Gain $': "N/A",
                         'Unrealized Gain %': "N/A", 'Sector': "Other", 'Today % Change': "N/A"})
    return pd.DataFrame(data)

# ----------------- GROK API -----------------
def call_grok(prompt, history=None):
    api_key = os.environ.get("GROK_API_KEY")
    if not api_key:
        return "❌ Grok API key not found."
    
    messages = history or []
    messages.append({"role": "user", "content": prompt})
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "grok-4-1-fast-reasoning", "messages": messages, "temperature": 0.7, "max_tokens": 7000},
            timeout=120
        )
        if response.status_code != 200:
            return f"❌ API Error {response.status_code}"
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ Request Error: {str(e)}"

# ----------------- FULL ANALYSIS -----------------
def run_full_analysis(selected_account):
    today = datetime.now().strftime("%B %d, %Y")
    portfolio_df = calculate_portfolio(selected_account)
    cash = get_cash_balance(selected_account)
    risk = get_risk_tolerance(selected_account)
    pending_df = load_pending_orders(selected_account)
    
    prompt = f"""You are a professional market analyst with **{risk.lower()} risk tolerance**. Date: {today}.

Portfolio ({selected_account}):
Cash: ${cash:,.2f}
Holdings:\n{portfolio_df.to_string(index=False) if not portfolio_df.empty else "None"}
Pending Orders:\n{pending_df.to_string(index=False) if not pending_df.empty else "None"}

**Part 1: Market Overview**
- Highest short-term momentum sectors + why
- 10-stock watchlist with volatility/volume/catalysts
- 5 day trading setups (entry, stop, target)
- Capital management strategy
- Upcoming catalysts this week

**Part 2: Personalized Recommendations**
For every holding and new ideas:
- Clear **Buy/Sell/Hold/Trim/Add** with specific share amounts or % of cash
- Entry/exit zones or triggers
- Reasoning tied to momentum
- Risk level and stop-loss ideas

Be detailed, specific, and actionable. Use headings and bullets."""

    with st.spinner("Generating full analysis..."):
        raw_result = call_grok(prompt)
        cleaned = clean_analysis_text(raw_result)
        
        # Store raw cleaned text
        st.session_state.full_analysis = cleaned
        st.session_state.conversation_history = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": cleaned}
        ]
        return cleaned

# ----------------- SIDEBAR & TABS -----------------
with st.sidebar:
    st.header("Controls")
    if st.button("🔥 Run Full Daily Analysis", type="primary"):
        run_full_analysis(st.session_state.get("current_account", "Main Portfolio"))
        st.success("Analysis complete!")

    if st.button("🔄 Refresh Prices"):
        st.cache_data.clear()
        st.success("Prices refreshed!")

tab1, tab2 = st.tabs(["📈 Full Analysis", "💼 My Portfolio"])

with tab1:
    st.header("Full Daily Market + Portfolio Analysis")
    if "full_analysis" in st.session_state:
        full_text = st.session_state.full_analysis
        
        # Split the text into sections
        sections = re.split(r'(?m)^(#{1,3}\s|5 Day Trading Setups)', full_text)
        
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            if "5 Day Trading Setups" in section or "day trading setups" in section.lower():
                st.subheader("📊 5 Day Trading Setups")
                setups_df = parse_trading_setups(full_text)
                if setups_df is not None and not setups_df.empty:
                    # Display as nice table
                    st.dataframe(
                        setups_df.style.set_properties(**{'text-align': 'left'}),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.markdown(section)
            else:
                st.markdown(section)
        
        st.divider()
        st.subheader("💬 Ask Grok for Clarification")
        st.markdown("""<p style="color:#888; font-style:italic; font-size:0.95em;">
        Example questions:<br>
        • “Why did you recommend selling AAPL?”<br>
        • “Can you explain the entry zone for NVDA?”<br>
        • “Should I add more to energy sector?”
        </p>""", unsafe_allow_html=True)
        
        q = st.text_input("Your question:", placeholder="Ask Grok...", key="q_input")
        if st.button("Send to Grok", key="send_q"):
            if q.strip():
                if "conversation_history" not in st.session_state:
                    st.session_state.conversation_history = []
                raw_resp = call_grok(q, st.session_state.conversation_history)
                cleaned_resp = clean_analysis_text(raw_resp)
                st.session_state.conversation_history.append({"role": "user", "content": q})
                st.session_state.conversation_history.append({"role": "assistant", "content": cleaned_resp})
                st.markdown("**Grok:**")
                st.markdown(cleaned_resp)
    else:
        st.info("Click 'Run Full Daily Analysis' in sidebar.")

with tab2:
    # (Your existing Portfolio tab code remains unchanged - omitted here for brevity)
    # ... [all the portfolio code you already have]
    st.info("Portfolio tab code is unchanged from previous version.")

st.caption("Built with Streamlit + yfinance + Grok API")
