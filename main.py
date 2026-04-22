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

# ----------------- CSS for better metrics display -----------------
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] {
        font-size: 1.45em !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85em !important;
        color: #666666;
    }
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

def delete_holding(ticker):
    conn = get_db_connection()
    conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker.upper(),))
    conn.commit()
    conn.close()

def clear_all_holdings():
    conn = get_db_connection()
    conn.execute("DELETE FROM holdings")
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
@st.cache_data(ttl=180)
def calculate_portfolio():
    df = load_holdings()
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

    st.divider()

    # ================== FIXED CLEAR BUTTONS ==================
    st.subheader("Danger Zone")
    col_clear1, col_clear2 = st.columns(2)
    
    with col_clear1:
        if st.button("🗑️ Clear All Holdings", type="secondary"):
            if st.checkbox("⚠️ Yes, permanently delete ALL holdings", key="confirm_holdings"):
                clear_all_holdings()
                st.cache_data.clear()
                st.success("✅ All holdings have been deleted.")
                st.rerun()
            else:
                st.warning("Check the box to confirm deletion of all holdings.")

    with col_clear2:
        if st.button("🗑️ Clear All Pending Orders", type="secondary"):
            if st.checkbox("⚠️ Yes, permanently delete ALL pending orders", key="confirm_pending"):
                clear_all_pending_orders()
                st.cache_data.clear()
                st.success("✅ All pending orders have been deleted.")
                st.rerun()
            else:
                st.warning("Check the box to confirm deletion of all pending orders.")

    # Performance Metrics
    portfolio_df = calculate_portfolio()
    cash = get_cash_balance()
    
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

    # Compact Holdings with Individual Delete
    if not portfolio_df.empty:
        st.subheader("Current Holdings + Daily Performance")
        
        for idx, row in portfolio_df.iterrows():
            with st.expander(f"📌 {row['Ticker']} — ${row['Current Value']:,.2f} ({row['Today % Change']:.2f}%)", expanded=False):
                col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                with col1:
                    st.write(f"**Shares:** {row['Shares']}")
                    st.write(f"**Cost Basis:** ${row['Cost Basis']:.2f}")
                with col2:
                    st.write(f"**Current Price:** ${row['Current Price']:.2f}")
                    st.write(f"**Today % Change:** {row['Today % Change']:.2f}%")
                with col3:
                    st.write(f"**Unrealized P/L:** ${row['Unrealized Gain $']:.2f} ({row['Unrealized Gain %']:.2f}%)")
                with col4:
                    if st.button("🗑️ Delete", key=f"del_hold_{row['Ticker']}", help="Delete this holding"):
                        delete_holding(row['Ticker'])
                        st.cache_data.clear()
                        st.success(f"✅ Deleted {row['Ticker']}")
                        st.rerun()

        st.divider()

    # Intraday Charts with Cost Basis Line
    if not portfolio_df.empty:
        st.subheader("📈 Intraday Charts (1D) with Cost Basis")
        st.caption("Today's price movement — solid red line = your cost basis per share")

        cols = st.columns(3)
        for i, row in portfolio_df.iterrows():
            ticker_symbol = row['Ticker']
            cost_basis = row['Cost Basis']
            
            with cols[i % 3]:
                try:
                    t = Ticker(ticker_symbol)
                    hist = t.history(period="1d", interval="5m")
                    
                    if not hist.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=hist.index,
                            y=hist['Close'],
                            mode='lines',
                            name=ticker_symbol,
                            line=dict(color='#1f77b4', width=2)
                        ))
                        fig.add_hline(
                            y=cost_basis,
                            line_dash="solid",
                            line_color="red",
                            line_width=2.5,
                            annotation_text=f"Cost Basis (${cost_basis:.2f})",
                            annotation_position="top right",
                            annotation_font_size=11,
                            annotation_font_color="red"
                        )
                        fig.update_layout(
                            title=f"{ticker_symbol} Today",
                            xaxis_title="Time",
                            yaxis_title="Price ($)",
                            height=280,
                            margin=dict(l=40, r=40, t=50, b=40),
                            template="plotly_white"
                        )
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{ticker_symbol}_{i}")
                    else:
                        st.info(f"No intraday data for {ticker_symbol} yet.")
                except Exception:
                    st.info(f"Could not load chart for {ticker_symbol}")

    # Sector Allocation
    if not portfolio_df.empty:
        st.subheader("Sector Allocation (%)")
        sector_df = portfolio_df.groupby('Sector')['Current Value'].sum().reset_index()
        sector_df['Percentage'] = (sector_df['Current Value'] / total_holdings_value * 100) if total_holdings_value > 0 else 0
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

    # Pending Orders
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
        st.info("No pending orders yet.")

    st.info(f"💰 Available Cash: ${get_cash_balance():,.2f}")

st.caption("Built with Streamlit + yfinance + Grok API • Educational use only")
