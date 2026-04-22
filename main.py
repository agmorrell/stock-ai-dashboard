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
        CREATE TABLE IF NOT EXISTS pending_orders (id INTEGER PRIMARY KEY, account_name TEXT, ticker TEXT, order_type TEXT, shares REAL, limit_price REAL, status TEXT DEFAULT 'Pending');
    ''')
    conn.execute("INSERT OR IGNORE INTO accounts (account_name, risk_tolerance) VALUES ('Main Portfolio', 'Moderate')")
    conn.commit()
    conn.close()

init_db()

def get_accounts():
    conn = get_db_connection()
    accounts = [row['account_name'] for row in conn.execute("SELECT account_name FROM accounts").fetchall()]
    conn.close()
    return accounts

def add_account(account_name, risk_tolerance="Moderate"):
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO accounts (account_name, risk_tolerance) VALUES (?, ?)", (account_name, risk_tolerance))
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
        ticker_symbol = row['ticker']
        try:
            time.sleep(random.uniform(0.5, 1.0))
            ticker = Ticker(ticker_symbol)
            info = ticker.info
            current_price = float(info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0.0)
            sector = info.get('sector') or "Other"
            today_change_pct = float(info.get('regularMarketChangePercent') or 0.0)
            
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
                'Unrealized Gain %': round(gain_pct, 2),
                'Sector': sector,
                'Today % Change': round(today_change_pct, 2)
            })
        except Exception:
            data.append({
                'Ticker': ticker_symbol,
                'Shares': round(row['shares'], 4),
                'Cost Basis': round(row['cost_basis'], 2),
                'Current Price': "N/A",
                'Current Value': "N/A",
                'Unrealized Gain $': "N/A",
                'Unrealized Gain %': "N/A",
                'Sector': "Other",
                'Today % Change': "N/A"
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

# ----------------- FULL ANALYSIS (Detailed) -----------------
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
1. Identify the stock sectors with the **highest short-term momentum** right now and explain why they are leading.
2. Build a high-probability watchlist: Recommend 10 stocks with strong volatility, volume, and catalyst potential, prioritizing those in the top momentum sectors.
3. Create 5 actionable day trading setups with specific entry zones, stop losses, and profit targets.
4. Suggest a capital management strategy suitable for {risk_tolerance.lower()} risk tolerance.
5. List upcoming earnings, macro events, or news catalysts this week.

**Part 2: Personalized Recommendations (Focus on Highest Momentum Sectors)**
For each existing holding and new opportunities:
- Give a clear **Buy / Sell / Hold / Trim / Add** recommendation.
- Suggest specific entry or exit price zones or technical triggers.
- State **how much** to buy or sell (specific share counts or % of cash/portfolio).
- Recommend where to diversify or concentrate based on momentum.
- Provide clear reasoning tied to current momentum, catalysts, risk, and your cash/pending orders.
- Assign a risk level (Low / Medium / High) and suggest stop-loss ideas.

**Overall Portfolio Strategy**
- Aggressive cash deployment suggestions focused on highest momentum sectors.
- Advice on pending orders (keep, modify, or cancel).
- Rebalancing summary.
- How to compound daily gains responsibly.

Be very detailed, specific, and actionable. Use clear headings and bullet points."""

    with st.spinner(f"Generating full detailed analysis for {selected_account}..."):
        result = call_grok(prompt)
        st.session_state.full_analysis = result
        # Initialize conversation history if it doesn't exist
        if "conversation_history" not in st.session_state:
            st.session_state.conversation_history = []
        st.session_state.conversation_history = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": result}
        ]
        return result

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.header("Controls")
    if st.button("🔥 Run Full Daily Analysis", type="primary"):
        if "current_account" in st.session_state:
            run_full_analysis(st.session_state.current_account)
            st.success("✅ Full detailed analysis ready!")
        else:
            st.error("Please select an account first.")

    if st.button("🔄 Refresh Portfolio Prices"):
        st.cache_data.clear()
        st.success("Prices refreshed!")

# ----------------- ACCOUNT MANAGEMENT -----------------
if "current_account" not in st.session_state:
    st.session_state.current_account = "Main Portfolio"

accounts = get_accounts()

# ----------------- TABS -----------------
tab1, tab2 = st.tabs(["📈 Full Analysis", "💼 My Portfolio"])

with tab1:
    st.header("Full Daily Market + Portfolio Analysis")
    if "full_analysis" in st.session_state:
        st.markdown(st.session_state.full_analysis)
        
        st.divider()
        st.subheader("💬 Ask Grok for Clarification")
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
        
        user_question = st.text_input("Your question:", placeholder="Type your question here...", key="followup_input")
        
        if st.button("Send Question to Grok", key="send_followup"):
            if user_question.strip():
                with st.spinner("Getting clarification from Grok..."):
                    # Ensure conversation_history exists
                    if "conversation_history" not in st.session_state:
                        st.session_state.conversation_history = []
                    
                    response = call_grok(user_question, st.session_state.conversation_history)
                    st.session_state.conversation_history.append({"role": "user", "content": user_question})
                    st.session_state.conversation_history.append({"role": "assistant", "content": response})
                    st.markdown("**Grok's Response:**")
                    st.markdown(response)
            else:
                st.warning("Please enter a question.")
    else:
        st.info("Select an account and click 'Run Full Daily Analysis' in the sidebar.")

with tab2:
    st.header("Portfolio Tracker")
    
    # Account Selector + New Account
    st.subheader("Portfolio Account")
    col1, col2 = st.columns([3, 2])
    with col1:
        selected_account = st.selectbox("Select Account", accounts, 
                                      index=accounts.index(st.session_state.current_account) 
                                            if st.session_state.current_account in accounts else 0,
                                      key="account_selector")
        st.session_state.current_account = selected_account

    with col2:
        new_name = st.text_input("New Account Name", placeholder="e.g. IRA", key="new_account_name")
        if st.button("Create New Account"):
            if new_name.strip():
                add_account(new_name.strip())
                st.success(f"Account '{new_name}' created!")
                st.rerun()

    # Risk Tolerance
    current_risk = get_risk_tolerance(selected_account)
    new_risk = st.selectbox("Risk Tolerance", ["Conservative", "Moderate", "Aggressive"], 
                           index=["Conservative", "Moderate", "Aggressive"].index(current_risk))
    if new_risk != current_risk:
        set_risk_tolerance(selected_account, new_risk)
        st.success(f"Risk tolerance updated to {new_risk}")
        st.rerun()

    st.divider()

    # Cash Balance
    st.subheader("💰 Cash Balance")
    current_cash = get_cash_balance(selected_account)
    new_cash = st.number_input("Update Cash Available ($)", min_value=0.0, value=current_cash, step=100.0)
    if st.button("Update Cash Balance"):
        update_cash_balance(selected_account, new_cash)
        st.success(f"Cash updated to ${new_cash:,.2f}")
        st.rerun()

    st.divider()

    # Add Holding
    with st.expander("➕ Add or Update Holding"):
        col1, col2, col3 = st.columns(3)
        with col1:
            ticker = st.text_input("Ticker Symbol", placeholder="AAPL", key="hold_ticker").upper()
        with col2:
            shares = st.number_input("Shares", min_value=0.01, value=10.0, key="hold_shares")
        with col3:
            cost = st.number_input("Cost Basis per Share ($)", min_value=0.01, value=150.0, key="hold_cost")
        if st.button("Save Holding", type="primary", key="save_hold"):
            if ticker:
                save_holding(selected_account, ticker, shares, cost)
                st.cache_data.clear()
                st.success(f"✅ {ticker} saved!")
                st.rerun()

    # Portfolio Data
    portfolio_df = calculate_portfolio(selected_account)
    cash = get_cash_balance(selected_account)
    
    numeric_value = pd.to_numeric(portfolio_df["Current Value"], errors='coerce').fillna(0)
    numeric_gain = pd.to_numeric(portfolio_df["Unrealized Gain $"], errors='coerce').fillna(0)
    numeric_return = pd.to_numeric(portfolio_df["Unrealized Gain %"], errors='coerce').fillna(0)
    
    total_holdings_value = numeric_value.sum()
    total_portfolio_value = total_holdings_value + cash
    total_unrealized_gain = numeric_gain.sum()
    overall_return_pct = (total_unrealized_gain / (total_holdings_value + 0.0001) * 100) if total_holdings_value > 0 else 0.0
    num_positions = len(portfolio_df)
    avg_return_per_position = numeric_return.mean() if num_positions > 0 else 0.0
    
    largest_pos_pct = (numeric_value.max() / total_holdings_value * 100) if total_holdings_value > 0 else 0.0
    cash_pct = (cash / total_portfolio_value * 100) if total_portfolio_value > 0 else 0.0

    st.subheader("📊 Portfolio Performance Metrics")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Total Portfolio Value", f"${total_portfolio_value:,.2f}")
    with col2:
        st.metric("Total Unrealized P/L", f"${total_unrealized_gain:,.2f}", delta=f"{overall_return_pct:.2f}%")
    with col3:
        st.metric("Avg Return per Position", f"{avg_return_per_position:.2f}%")
    with col4:
        st.metric("Number of Positions", num_positions)
    with col5:
        st.metric("Largest Position", f"{largest_pos_pct:.1f}%")
    with col6:
        st.metric("Cash Allocation", f"{cash_pct:.1f}%")

    st.divider()

    # Holdings Table
    if not portfolio_df.empty:
        st.subheader("Current Holdings")
        styled_df = portfolio_df.style.format({
            "Cost Basis": "${:.2f}",
            "Current Price": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else x,
            "Current Value": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else x,
            "Unrealized Gain $": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else x,
            "Unrealized Gain %": lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) else x,
            "Today % Change": lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) else x
        })
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # Portfolio Allocation Pie Chart
    if total_portfolio_value > 0:
        st.subheader("Portfolio Allocation")
        alloc_data = portfolio_df[['Ticker', 'Current Value']].copy()
        alloc_data = alloc_data[pd.to_numeric(alloc_data['Current Value'], errors='coerce').notna()]
        if not alloc_data.empty:
            alloc_data.loc[len(alloc_data)] = ['Cash', cash]
            fig_pie = px.pie(alloc_data, values='Current Value', names='Ticker', 
                            title="Portfolio Allocation (Including Cash)", hole=0.45)
            fig_pie.update_traces(textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

    # Sector Allocation Bar Chart
    if not portfolio_df.empty and total_holdings_value > 0:
        st.subheader("Sector Allocation (%)")
        sector_df = portfolio_df.groupby('Sector')['Current Value'].sum().reset_index()
        sector_df['Percentage'] = (sector_df['Current Value'] / total_holdings_value * 100)
        sector_df.loc[len(sector_df)] = ['Cash', cash, (cash / total_portfolio_value * 100) if total_portfolio_value > 0 else 0]
        sector_df = sector_df.sort_values('Percentage', ascending=False)
        
        fig_sector = px.bar(
            sector_df, 
            x='Percentage', 
            y='Sector', 
            orientation='h',
            title="Allocation by Sector (%)",
            text='Percentage',
            color='Percentage',
            color_continuous_scale='Blues'
        )
        fig_sector.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_sector.update_layout(xaxis_title="Percentage of Total Portfolio (%)")
        st.plotly_chart(fig_sector, use_container_width=True)

    st.info(f"💰 Available Cash: ${cash:,.2f}")

st.caption("Built with Streamlit + yfinance + Grok API • Educational use only")
