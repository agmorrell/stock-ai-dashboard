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

# Clean, consistent CSS with better bullet control
st.markdown("""
    <style>
    .stMarkdown, .stMarkdown p, .stMarkdown li {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 1.05em;
        line-height: 1.72;
        margin-bottom: 0.85em;
    }
    .stMarkdown p, .stMarkdown li {
        white-space: pre-wrap;
        word-break: break-word;
        overflow-wrap: break-word;
    }
    .stMarkdown h1 { font-size: 1.85em; margin: 2.0em 0 0.8em 0; color: #1f77b4; }
    .stMarkdown h2 { font-size: 1.55em; margin: 1.8em 0 0.7em 0; color: #1f77b4; }
    .stMarkdown h3 { 
        font-size: 1.35em; 
        margin: 1.6em 0 0.6em 0; 
        color: #1f77b4; 
        border-left: 5px solid #1f77b4; 
        padding-left: 12px; 
    }
    .stMarkdown ul, .stMarkdown ol {
        padding-left: 1.9em;
        margin-bottom: 1.0em;
    }
    .stMarkdown li {
        margin-bottom: 0.5em;   /* Tight but readable between bullets */
    }
    .stMarkdown h3 + ul, .stMarkdown h3 + ol {
        background-color: #f8f9fa;
        padding: 1.1em 1.4em;
        border-radius: 8px;
        border-left: 5px solid #1f77b4;
        margin: 1.1em 0;
    }
    /* Fix italic/bold inside dense text */
    .stMarkdown em, .stMarkdown i, .stMarkdown strong, .stMarkdown b {
        margin: 0 2px;
    }
    </style>
""", unsafe_allow_html=True)

# Very aggressive cleaner for trading text
def clean_analysis_text(text):
    if not text:
        return text
    
    # 1. Basic punctuation
    text = re.sub(r'([a-zA-Z0-9)])([.,;:/])([a-zA-Z])', r'\1\2 \3', text)
    
    # 2. Number/letter separation
    text = re.sub(r'([a-zA-Z)])([0-9])', r'\1 \2', text)
    text = re.sub(r'([0-9])([a-zA-Z(])', r'\1 \2', text)
    
    # 3. Trading keywords
    text = re.sub(r'(\w+)(Long|Short|Entry|Stop|Target|StopLoss|Catalyst|Momentum|Squeeze|Play)', r'\1 \2', text, flags=re.IGNORECASE)
    
    # 4. Dashes, slashes, ranges
    text = re.sub(r'([0-9.])(−|-)([0-9.])', r'\1 - \3', text)
    text = re.sub(r'([0-9a-zA-Z)])([/\\])([0-9a-zA-Z(])', r'\1 / \3', text)
    
    # 5. Parentheses and price targets
    text = re.sub(r'\)([a-zA-Z0-9])', r') \1', text)
    text = re.sub(r'([a-zA-Z0-9])\(', r'\1 (', text)
    text = re.sub(r'([0-9,]+)\)([a-zA-Z])', r'\1) \2', text)
    
    # 6. Specific patterns from your examples
    text = re.sub(r'([0-9.])([A-Za-z])', r'\1 \2', text)
    text = re.sub(r'([A-Za-z])([0-9.])', r'\1 \2', text)
    text = re.sub(r'([a-z0-9)])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([0-9,]+)\)([a-z])', r'\1) \2', text, flags=re.IGNORECASE)
    
    # 7. Final aggressive cleanup for very dense strings
    text = re.sub(r'(\w{10,})([A-Z])', r'\1 \2', text)
    text = re.sub(r'([0-9.])([A-Z])', r'\1 \2', text)
    
    return text

# ----------------- DATABASE (kept unchanged) -----------------
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
        cleaned_result = clean_analysis_text(raw_result)
        st.session_state.full_analysis = cleaned_result
        st.session_state.conversation_history = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": cleaned_result}
        ]
        return cleaned_result

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
        st.markdown(st.session_state.full_analysis)
        
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
    st.header("Portfolio Tracker")
    
    accounts = get_accounts()
    col_a, col_b = st.columns([3, 2])
    with col_a:
        selected = st.selectbox("Select Account", accounts, 
                              index=accounts.index(st.session_state.get("current_account", "Main Portfolio")),
                              key="acc_select")
        st.session_state.current_account = selected
    with col_b:
        new_acc = st.text_input("New Account Name", placeholder="IRA", key="new_acc")
        if st.button("Create Account"):
            if new_acc.strip():
                add_account(new_acc.strip())
                st.success(f"Created {new_acc}")
                st.rerun()

    curr_risk = get_risk_tolerance(selected)
    new_risk = st.selectbox("Risk Tolerance", ["Conservative", "Moderate", "Aggressive"], 
                           index=["Conservative","Moderate","Aggressive"].index(curr_risk))
    if new_risk != curr_risk:
        set_risk_tolerance(selected, new_risk)
        st.success("Risk tolerance updated")
        st.rerun()

    st.divider()

    cash = get_cash_balance(selected)
    new_cash = st.number_input("Cash Balance ($)", value=cash, step=100.0)
    if st.button("Update Cash"):
        update_cash_balance(selected, new_cash)
        st.success("Cash updated")
        st.rerun()

    st.divider()

    with st.expander("➕ Add Holding"):
        c1, c2, c3 = st.columns(3)
        with c1: ticker = st.text_input("Ticker", key="tkr").upper()
        with c2: shares = st.number_input("Shares", min_value=0.01, value=10.0, key="sh")
        with c3: cost = st.number_input("Cost Basis $", min_value=0.01, value=150.0, key="cb")
        if st.button("Save Holding"):
            if ticker:
                save_holding(selected, ticker, shares, cost)
                st.cache_data.clear()
                st.success(f"Saved {ticker}")
                st.rerun()

    with st.expander("📋 Add Pending Order"):
        c1, c2 = st.columns(2)
        with c1:
            po_tkr = st.text_input("Ticker", key="po_tkr").upper()
            po_type = st.selectbox("Type", ["Buy", "Sell"], key="po_type")
        with c2:
            po_shares = st.number_input("Shares", min_value=0.01, value=10.0, key="po_sh")
            po_price = st.number_input("Limit Price $", min_value=0.01, value=150.0, key="po_pr")
        if st.button("Add Pending Order"):
            if po_tkr:
                add_pending_order(selected, po_tkr, po_type, po_shares, po_price)
                st.success("Pending order added")
                st.rerun()

    df = calculate_portfolio(selected)
    cash = get_cash_balance(selected)
    total_value = (df["Current Value"].sum() if not df.empty else 0) + cash

    st.subheader("📊 Performance Metrics")
    cols = st.columns(6)
    with cols[0]: st.metric("Total Value", f"${total_value:,.2f}")
    with cols[1]: st.metric("Unrealized P/L", f"${df['Unrealized Gain $'].sum():,.2f}" if not df.empty else "$0.00")
    with cols[2]: st.metric("Avg Return %", f"{df['Unrealized Gain %'].mean():.2f}%" if not df.empty else "0.00%")
    with cols[3]: st.metric("Positions", len(df))
    with cols[4]: st.metric("Largest Position %", f"{(df['Current Value'].max() / total_value * 100):.2f}%" if not df.empty and total_value > 0 else "0.00%")
    with cols[5]: st.metric("Cash %", f"{(cash / total_value * 100):.2f}%" if total_value > 0 else "0.00%")

    st.divider()

    if not df.empty:
        st.subheader("Current Holdings + Daily Performance")
        styled_df = df.style.format({
            "Cost Basis": "${:.2f}",
            "Current Price": "${:.2f}",
            "Current Value": "${:.2f}",
            "Unrealized Gain $": "${:.2f}",
            "Unrealized Gain %": "{:.2f}%",
            "Today % Change": "{:.2f}%"
        }).apply(
            lambda x: ['color: #00cc00' if isinstance(v, (int, float)) and v > 0 else 
                       'color: #ff4444' if isinstance(v, (int, float)) and v < 0 else '' for v in x], 
            subset=['Today % Change']
        )
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

    if not df.empty:
        st.subheader("📈 Intraday Charts (1D) with Cost Basis")
        st.caption("Solid red line = your cost basis per share")
        cols = st.columns(3)
        for i, row in df.iterrows():
            ticker_symbol = row['Ticker']
            cost_basis = row['Cost Basis']
            with cols[i % 3]:
                try:
                    t = Ticker(ticker_symbol)
                    hist = t.history(period="1d", interval="5m")
                    if not hist.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', line=dict(color='#1f77b4', width=2)))
                        fig.add_hline(y=cost_basis, line_dash="solid", line_color="red", line_width=2.5,
                                      annotation_text=f"Cost Basis (${cost_basis:.2f})", annotation_position="top right")
                        fig.update_layout(title=f"{ticker_symbol} Today", height=300)
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{i}")
                except:
                    st.info(f"No chart for {ticker_symbol}")

    if total_value > 0:
        st.subheader("Allocation Charts")
        c1, c2 = st.columns(2)
        with c1:
            pie_data = df[['Ticker', 'Current Value']].copy()
            pie_data.loc[len(pie_data)] = ['Cash', cash]
            st.plotly_chart(px.pie(pie_data, values='Current Value', names='Ticker', title="Portfolio Allocation (Including Cash)", hole=0.45), use_container_width=True)
        with c2:
            sector_df = df.groupby('Sector')['Current Value'].sum().reset_index()
            sector_df['Percentage'] = (sector_df['Current Value'] / df['Current Value'].sum() * 100) if not df.empty else 0
            sector_df.loc[len(sector_df)] = ['Cash', cash, (cash / total_value * 100)]
            sector_df = sector_df.sort_values('Percentage', ascending=False)
            fig_sector = px.bar(sector_df, x='Percentage', y='Sector', orientation='h', title="Sector Allocation (%)", text='Percentage', color='Percentage', color_continuous_scale='Blues')
            fig_sector.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
            st.plotly_chart(fig_sector, use_container_width=True)

    pending = load_pending_orders(selected)
    if not pending.empty:
        st.subheader("📋 Pending Orders")
        for _, row in pending.iterrows():
            col1, col2, col3 = st.columns([5, 2, 1])
            with col1:
                st.write(f"**{row['ticker']}** — {row['order_type']} {row['shares']:.2f} shares @ **${row['limit_price']:.2f}**")
            with col3:
                if st.button("🗑️", key=f"del_po_{row['id']}"):
                    delete_pending_order(row['id'])
                    st.rerun()

    st.info(f"Available Cash: **${cash:,.2f}**")

st.caption("Built with Streamlit + yfinance + Grok API")
