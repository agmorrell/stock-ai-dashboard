import appdirs as ad
ad.user_cache_dir = lambda *args: "/tmp"  # Helps with some deployment environments

import streamlit as st
import pandas as pd
from yfinance import Ticker, Tickers
import plotly.express as px
import plotly.graph_objects as go
import requests
import os
from datetime import datetime
import sqlite3
import random

st.set_page_config(page_title="AI Stock Dashboard", layout="wide", page_icon="🚀")

# ----------------- CUSTOM CSS (Dark-mode friendly) -----------------
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { font-size: 1.5em !important; font-weight: 700 !important; }
    div[data-testid="stMetricLabel"] { font-size: 0.9em !important; color: #888888; }
    .stDataFrame { font-size: 0.95em; }
    </style>
""", unsafe_allow_html=True)

st.title("🚀 My Personal AI Stock Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M %p EST')}")

# ----------------- DATABASE -----------------
def get_db_connection():
    conn = sqlite3.connect('portfolio.db', check_same_thread=False)
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

# Helper DB functions (unchanged mostly, but cleaned)
def get_accounts():
    conn = get_db_connection()
    accounts = [row['account_name'] for row in conn.execute("SELECT account_name FROM accounts").fetchall()]
    conn.close()
    return accounts

def add_account(account_name):
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO accounts (account_name, risk_tolerance) VALUES (?, 'Moderate')", (account_name.strip(),))
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
                 (account_name, ticker.upper(), float(shares), float(cost_basis)))
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
    return float(row['cash']) if row else 0.0

def update_cash_balance(account_name, new_cash):
    conn = get_db_connection()
    conn.execute("REPLACE INTO cash_balance (account_name, cash) VALUES (?, ?)", (account_name, float(new_cash)))
    conn.commit()
    conn.close()

# Pending orders functions (similarly cleaned)
def add_pending_order(account_name, ticker, order_type, shares, limit_price):
    conn = get_db_connection()
    conn.execute("""INSERT INTO pending_orders (account_name, ticker, order_type, shares, limit_price)
                    VALUES (?, ?, ?, ?, ?)""", (account_name, ticker.upper(), order_type, float(shares), float(limit_price)))
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

# ----------------- PORTFOLIO CALCULATION (Improved) -----------------
@st.cache_data(ttl=300)  # 5 minutes cache
def calculate_portfolio(account_name):
    df = load_holdings(account_name)
    if df.empty:
        return pd.DataFrame(columns=['Ticker','Shares','Cost Basis','Current Price','Current Value',
                                     'Unrealized Gain $','Unrealized Gain %','Sector','Today % Change'])

    # Batch fetch where possible (faster)
    tickers_list = df['ticker'].tolist()
    try:
        tickers_obj = Tickers(" ".join(tickers_list))
    except:
        tickers_obj = None

    data = []
    for _, row in df.iterrows():
        ticker_str = row['ticker'].upper()
        try:
            if tickers_obj:
                t = tickers_obj.tickers.get(ticker_str)
            else:
                t = Ticker(ticker_str)
            
            info = t.info if t else {}
            current_price = float(info.get('currentPrice') or info.get('regularMarketPrice') or 
                                info.get('previousClose') or 0.0)
            sector = info.get('sector') or info.get('industry') or "Other"
            today_change = float(info.get('regularMarketChangePercent') or 0.0)

            current_value = row['shares'] * current_price
            gain_dollar = current_value - (row['shares'] * row['cost_basis'])
            gain_pct = (gain_dollar / (row['shares'] * row['cost_basis']) * 100) if row['cost_basis'] > 0 else 0.0

            data.append({
                'Ticker': ticker_str,
                'Shares': round(row['shares'], 4),
                'Cost Basis': round(row['cost_basis'], 2),
                'Current Price': round(current_price, 2),
                'Current Value': round(current_value, 2),
                'Unrealized Gain $': round(gain_dollar, 2),
                'Unrealized Gain %': round(gain_pct, 2),
                'Sector': sector,
                'Today % Change': round(today_change, 2)
            })
        except Exception:
            data.append({'Ticker': ticker_str, 'Shares': round(row['shares'], 4), 'Cost Basis': round(row['cost_basis'], 2),
                         'Current Price': "N/A", 'Current Value': "N/A", 'Unrealized Gain $': "N/A",
                         'Unrealized Gain %': "N/A", 'Sector': "Other", 'Today % Change': "N/A"})
    return pd.DataFrame(data)

# ----------------- GROK API (unchanged) -----------------
def call_grok(prompt, history=None):
    api_key = os.environ.get("GROK_API_KEY")
    if not api_key:
        return "❌ Grok API key not found. Set GROK_API_KEY environment variable."
   
    messages = history or []
    messages.append({"role": "user", "content": prompt})
   
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "grok-4-1-fast-reasoning", "messages": messages, "temperature": 0.7, "max_tokens": 7000},
            timeout=120
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ Grok API Error: {str(e)}"

# Full analysis function (unchanged logic, minor cleanup)
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
**Part 1: Market Overview** ... (rest of your original prompt)"""
    
    with st.spinner("🤖 Generating full analysis with Grok..."):
        result = call_grok(prompt)
        st.session_state.full_analysis = result
        st.session_state.conversation_history = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": result}
        ]
        return result

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.header("⚙️ Controls")
    selected_account = st.session_state.get("current_account", "Main Portfolio")
    
    if st.button("🔥 Run Full Daily Analysis", type="primary"):
        run_full_analysis(selected_account)
        st.success("✅ Analysis generated!")
    
    if st.button("🔄 Refresh All Prices"):
        st.cache_data.clear()
        st.success("Prices refreshed!")

# ----------------- MAIN APP -----------------
accounts = get_accounts()

tab1, tab2 = st.tabs(["📈 Full Analysis", "💼 My Portfolio"])

with tab1:
    st.header("Full Daily Market + Portfolio Analysis")
    if "full_analysis" in st.session_state:
        st.markdown(st.session_state.full_analysis)
        
        st.divider()
        st.subheader("💬 Ask Grok Follow-up")
        q = st.text_input("Your question:", placeholder="E.g., Why sell AAPL? Or explain the NVDA entry...")
        if st.button("Send to Grok"):
            if q.strip():
                if "conversation_history" not in st.session_state:
                    st.session_state.conversation_history = []
                resp = call_grok(q, st.session_state.conversation_history)
                st.session_state.conversation_history.append({"role": "user", "content": q})
                st.session_state.conversation_history.append({"role": "assistant", "content": resp})
                st.markdown("**Grok:**")
                st.markdown(resp)
    else:
        st.info("👈 Click 'Run Full Daily Analysis' in the sidebar to start.")

with tab2:
    st.header("💼 My Portfolio")
    
    col_a, col_b = st.columns([3, 2])
    with col_a:
        selected = st.selectbox("Select Account", accounts, 
                                index=accounts.index(selected_account) if selected_account in accounts else 0,
                                key="acc_select")
        st.session_state.current_account = selected
    with col_b:
        new_acc = st.text_input("New Account Name", placeholder="e.g., Roth IRA")
        if st.button("➕ Create Account"):
            if new_acc.strip():
                add_account(new_acc.strip())
                st.success(f"Account '{new_acc}' created!")
                st.rerun()

    # Risk tolerance
    curr_risk = get_risk_tolerance(selected)
    new_risk = st.selectbox("Risk Tolerance", ["Conservative", "Moderate", "Aggressive"], 
                            index=["Conservative","Moderate","Aggressive"].index(curr_risk))
    if new_risk != curr_risk:
        set_risk_tolerance(selected, new_risk)
        st.success("Risk tolerance updated!")
        st.rerun()

    st.divider()

    # Cash
    cash = get_cash_balance(selected)
    new_cash = st.number_input("Cash Balance ($)", value=float(cash), step=100.0, format="%.2f")
    if st.button("💰 Update Cash"):
        update_cash_balance(selected, new_cash)
        st.success("Cash updated!")
        st.rerun()

    st.divider()

    # Add Holding
    with st.expander("➕ Add / Edit Holding"):
        c1, c2, c3 = st.columns(3)
        with c1: ticker = st.text_input("Ticker", key="add_tkr").upper()
        with c2: shares = st.number_input("Shares", min_value=0.0001, value=10.0, key="add_sh")
        with c3: cost = st.number_input("Cost Basis per Share ($)", min_value=0.01, value=150.0, key="add_cb")
        if st.button("Save Holding"):
            if ticker:
                save_holding(selected, ticker, shares, cost)
                st.cache_data.clear()
                st.success(f"✅ Saved {ticker}")
                st.rerun()

    portfolio_df = calculate_portfolio(selected)
    total_holdings_value = float(pd.to_numeric(portfolio_df.get("Current Value", pd.Series()), errors='coerce').sum()) if not portfolio_df.empty else 0.0
    total_portfolio_value = total_holdings_value + cash

    # Metrics
    st.subheader("📊 Key Metrics")
    cols = st.columns(6)
    with cols[0]: st.metric("Total Value", f"${total_portfolio_value:,.2f}")
    with cols[1]: st.metric("Unrealized P/L", f"${pd.to_numeric(portfolio_df.get('Unrealized Gain $', pd.Series(0)), errors='coerce').sum():,.2f}")
    with cols[2]: st.metric("Avg Return %", f"{pd.to_numeric(portfolio_df.get('Unrealized Gain %', pd.Series(0)), errors='coerce').mean():.2f}%")
    with cols[3]: st.metric("Positions", len(portfolio_df))
    with cols[4]: st.metric("Largest Position %", f"{(pd.to_numeric(portfolio_df.get('Current Value', pd.Series(0)), errors='coerce').max() / total_portfolio_value * 100 if total_portfolio_value > 0 else 0):.1f}%")
    with cols[5]: st.metric("Cash %", f"{(cash / total_portfolio_value * 100 if total_portfolio_value > 0 else 0):.1f}%")

    if not portfolio_df.empty:
        st.subheader("Current Holdings")
        styled_df = portfolio_df.style.format({
            "Cost Basis": "${:.2f}", "Current Price": "${:.2f}", "Current Value": "${:.2f}",
            "Unrealized Gain $": "${:.2f}", "Unrealized Gain %": "{:.2f}%", "Today % Change": "{:.2f}%"
        }).apply(lambda x: ['color: lime' if v > 0 else 'color: red' if v < 0 else '' for v in x], 
                 subset=['Today % Change', 'Unrealized Gain %'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

        if st.button("📥 Export Portfolio to CSV"):
            csv = portfolio_df.to_csv(index=False)
            st.download_button("Download CSV", csv, f"portfolio_{selected}_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

    # Pending Orders (cleaner)
    pending = load_pending_orders(selected)
    if not pending.empty:
        st.subheader("📋 Pending Orders")
        for _, row in pending.iterrows():
            st.write(f"**{row['ticker']}** — {row['order_type']} {row['shares']:.2f} @ ${row['limit_price']:.2f}")
            if st.button("Delete", key=f"del_{row['id']}"):
                delete_pending_order(row['id'])
                st.rerun()
    else:
        st.info("No pending orders.")

    with st.expander("📋 Add Pending Order"):
        c1, c2 = st.columns(2)
        with c1:
            po_tkr = st.text_input("Ticker", key="po_tkr").upper()
            po_type = st.selectbox("Type", ["Buy", "Sell"], key="po_type")
        with c2:
            po_shares = st.number_input("Shares", min_value=0.0001, value=10.0, key="po_sh")
            po_price = st.number_input("Limit Price $", min_value=0.01, value=150.0, key="po_pr")
        if st.button("Add Order"):
            if po_tkr:
                add_pending_order(selected, po_tkr, po_type, po_shares, po_price)
                st.success("Order added!")
                st.rerun()

    # Charts
    if not portfolio_df.empty:
        st.subheader("📈 Intraday Charts (with Cost Basis)")
        cols = st.columns(min(3, len(portfolio_df)))
        for i, (_, row) in enumerate(portfolio_df.iterrows()):
            with cols[i % len(cols)]:
                try:
                    t = Ticker(row['Ticker'])
                    hist = t.history(period="1d", interval="5m")
                    if not hist.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], name="Price", line=dict(color='#1f77b4')))
                        fig.add_hline(y=row['Cost Basis'], line_dash="dash", line_color="red", 
                                      annotation_text=f"Cost: ${row['Cost Basis']:.2f}")
                        fig.update_layout(title=f"{row['Ticker']} Today", height=300, margin=dict(l=20,r=20,t=40,b=20))
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{i}")
                except:
                    st.caption(f"No intraday data for {row['Ticker']}")

    # Allocation
    if total_portfolio_value > 0:
        st.subheader("Allocation")
        c1, c2 = st.columns(2)
        with c1:
            pie_data = portfolio_df[['Ticker', 'Current Value']].copy() if not portfolio_df.empty else pd.DataFrame()
            pie_data = pd.concat([pie_data, pd.DataFrame({'Ticker': ['Cash'], 'Current Value': [cash]})])
            st.plotly_chart(px.pie(pie_data, values='Current Value', names='Ticker', title="Portfolio Allocation", hole=0.4), use_container_width=True)
        
        with c2:
            if not portfolio_df.empty:
                sector_df = portfolio_df.groupby('Sector')['Current Value'].sum().reset_index()
                sector_df['Percentage'] = sector_df['Current Value'] / total_holdings_value * 100
            else:
                sector_df = pd.DataFrame()
            sector_df = pd.concat([sector_df, pd.DataFrame({'Sector': ['Cash'], 'Current Value': [cash], 'Percentage': [cash / total_portfolio_value * 100]})])
            fig = px.bar(sector_df, x='Percentage', y='Sector', orientation='h', title="Sector + Cash Allocation (%)")
            st.plotly_chart(fig, use_container_width=True)

st.caption("Built with ❤️ using Streamlit • yfinance • Grok API • SQLite")
