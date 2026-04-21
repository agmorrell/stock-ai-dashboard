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

# ----------------- DATABASE -----------------
def get_db_connection():
    conn = sqlite3.connect('portfolio.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS holdings 
            (ticker TEXT PRIMARY KEY, shares REAL, cost_basis REAL);
        CREATE TABLE IF NOT EXISTS cash_balance 
            (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS pending_orders 
            (id INTEGER PRIMARY KEY, ticker TEXT, order_type TEXT, shares REAL, limit_price REAL, status TEXT DEFAULT 'Pending');
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
            current_price = float(info.get('currentPrice') or info.get('regularMarketPrice') or 
                                  info.get('previousClose') or 0.0)
            
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
def call_grok(prompt):
    api_key = os.environ.get("GROK_API_KEY")
    if not api_key:
        return "❌ Grok API key not found in Streamlit Secrets."
    
    model = "grok-4-1-fast-reasoning"
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 7000
            },
            timeout=150
        )
        if response.status_code != 200:
            return f"❌ API Error {response.status_code}: {response.text[:600]}"
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
    
    prompt = f"""You are a professional market analyst and portfolio manager. Today's date is {today}.

Current Portfolio Snapshot:
Cash Available: ${cash:,.2f}
Holdings:
{portfolio_text}
Pending Orders:
{pending_text}

**Part 1: Market Overview**
1. Highest short-term momentum sectors and why.
2. 10-stock high-probability watchlist.
3. 5 day trading setups with entry zones, stop losses, profit targets.
4. Capital management strategy.
5. Upcoming earnings / macro events this week.

**Part 2: Personalized Recommendations**
- Buy/Sell/Hold/Trim/Add for each holding
- Specific entry/exit price zones
- How much to buy/sell (considering cash)
- Diversification moves
- Reasoning based on momentum and your cash/pending orders
- Risk level and stop ideas

**Overall Strategy**
- Cash deployment suggestions
- Pending orders advice (keep/modify/cancel)
- Rebalancing and new position ideas
- Compounding plan

Use clear headings and bullet points."""

    with st.spinner("Generating full analysis..."):
        result = call_grok(prompt)
        st.session_state.full_analysis = result
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
    else:
        st.info("Click the button in the sidebar for today's full report.")

with tab2:
    st.header("Portfolio Tracker")
    
    # Cash Balance
    st.subheader("💰 Cash Balance")
    current_cash = get_cash_balance()
    new_cash = st.number_input("Update Cash Available ($)", min_value=0.0, value=current_cash, step=100.0)
    if st.button("Update Cash Balance"):
        update_cash_balance(new_cash)
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
                save_holding(ticker, shares, cost)
                st.cache_data.clear()
                st.success(f"✅ {ticker} saved!")
                st.rerun()

    # Add Pending Order
    with st.expander("📋 Add Pending Order"):
        col1, col2 = st.columns(2)
        with col1:
            po_ticker = st.text_input("Ticker", placeholder="NVDA", key="po_ticker").upper()
            po_type = st.selectbox("Order Type", ["Buy", "Sell"], key="po_type")
        with col2:
            po_shares = st.number_input("Shares", min_value=0.01, value=10.0, key="po_shares")
            po_price = st.number_input("Limit Price ($)", min_value=0.01, value=150.0, key="po_price")
        if st.button("Add Pending Order", type="primary", key="add_po"):
            if po_ticker:
                add_pending_order(po_ticker, po_type, po_shares, po_price)
                st.success(f"✅ Pending {po_type} for {po_ticker} added!")
                st.rerun()

    # Clear All Buttons
    col_clear1, col_clear2 = st.columns(2)
    with col_clear1:
        if st.button("🗑️ Clear All Holdings"):
            if st.checkbox("Confirm delete ALL holdings"):
                clear_all_holdings()
                st.cache_data.clear()
                st.success("All holdings cleared!")
                st.rerun()
    with col_clear2:
        if st.button("🗑️ Clear All Pending Orders"):
            if st.checkbox("Confirm delete ALL pending orders"):
                clear_all_pending_orders()
                st.success("All pending orders cleared!")
                st.rerun()

    # Display Holdings
    portfolio_df = calculate_portfolio()
    if not portfolio_df.empty:
        st.subheader("Current Holdings")
        styled_df = portfolio_df.style.format({
            "Cost Basis": "${:.2f}",
            "Current Price": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else str(x),
            "Current Value": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else str(x),
            "Unrealized Gain $": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else str(x),
            "Unrealized Gain %": lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) else str(x)
        })
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        numeric_gain = pd.to_numeric(portfolio_df["Unrealized Gain $"], errors='coerce').fillna(0)
        total_gain = numeric_gain.sum()
        st.metric("Total Unrealized P/L", f"${total_gain:,.2f}", delta="")

        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Portfolio Allocation")
            # Prepare data for semicircle pie chart (including cash)
            numeric_value = pd.to_numeric(portfolio_df["Current Value"], errors='coerce').fillna(0)
            total_holdings_value = numeric_value.sum()
            cash = get_cash_balance()
            total_portfolio_value = total_holdings_value + cash

            if total_portfolio_value > 0:
                # Create allocation data including cash
                alloc_data = portfolio_df[['Ticker', 'Current Value']].copy()
                alloc_data = alloc_data[pd.to_numeric(alloc_data['Current Value'], errors='coerce').notna()]
                alloc_data.loc[len(alloc_data)] = ['Cash', cash]  # Add cash as a slice
                
                fig_pie = px.pie(
                    alloc_data, 
                    values='Current Value', 
                    names='Ticker', 
                    title="Portfolio Allocation (Including Cash)",
                    hole=0.4,                    # Makes it a donut
                )
                # Make it a semicircle
                fig_pie.update_traces(
                    textinfo='percent+label',
                    pull=[0.05] * len(alloc_data),  # Slight pull for better look
                )
                fig_pie.update_layout(
                    showlegend=True,
                    height=400,
                    margin=dict(t=50, b=50)
                )
                # Force semicircle by rotating and clipping (Plotly trick)
                fig_pie.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=False),
                        angularaxis=dict(visible=False)
                    )
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Add holdings or cash to see allocation chart.")
        
        with col2:
            st.subheader("Gains / Losses")
            fig_bar = px.bar(portfolio_df, x='Ticker', y='Unrealized Gain $', 
                            title="Unrealized Profit/Loss by Position",
                            color='Unrealized Gain %',
                            color_continuous_scale='RdYlGn')
            st.plotly_chart(fig_bar, use_container_width=True)

    # Pending Orders with Instant Delete
    pending_df = load_pending_orders()
    if not pending_df.empty:
        st.subheader("📋 Pending Orders")
        
        for idx, row in pending_df.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([5, 3, 1])
                with col1:
                    st.write(f"**{row['ticker']}** — **{row['order_type']}** {row['shares']} shares @ **${row['limit_price']:.2f}**")
                with col2:
                    st.write(f"ID: {row['id']} | Status: {row['status']}")
                with col3:
                    if st.button("🗑️", key=f"del_{row['id']}", help="Delete this pending order"):
                        delete_pending_order(row['id'])
                        st.cache_data.clear()
                        st.success(f"✅ Deleted pending order for {row['ticker']}")
                        st.rerun()
    else:
        st.info("No pending orders yet. Add one using the expander above.")

    st.info(f"💰 Available Cash: ${get_cash_balance():,.2f}")

st.caption("Built with Streamlit + yfinance + Grok API • Educational use only")
