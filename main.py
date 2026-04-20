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
    conn.execute('''CREATE TABLE IF NOT EXISTS holdings 
                    (ticker TEXT PRIMARY KEY, shares REAL, cost_basis REAL)''')
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

# ----------------- PORTFOLIO (with cache) -----------------
@st.cache_data(ttl=300)
def calculate_portfolio():
    df = load_holdings()
    if df.empty:
        return pd.DataFrame()
    
    data = []
    for _, row in df.iterrows():
        ticker_symbol = row['ticker']
        try:
            time.sleep(random.uniform(0.6, 1.2))
            ticker = Ticker(ticker_symbol)
            info = ticker.info
            current_price = (info.get('currentPrice') or info.get('regularMarketPrice') or 
                            info.get('previousClose') or 0)
            
            current_value = row['shares'] * current_price
            cost = row['shares'] * row['cost_basis']
            gain_dollar = current_value - cost
            gain_pct = (gain_dollar / cost * 100) if cost > 0 else 0
            
            data.append({
                'Ticker': ticker_symbol,
                'Shares': row['shares'],
                'Cost Basis': round(row['cost_basis'], 2),
                'Current Price': round(current_price, 2),
                'Current Value': round(current_value, 2),
                'Unrealized Gain $': round(gain_dollar, 2),
                'Unrealized Gain %': round(gain_pct, 2)
            })
        except Exception:
            data.append({
                'Ticker': ticker_symbol,
                'Shares': row['shares'],
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
    
    model = "grok-4.1-fast-reasoning"   # Fast & reliable for daily use
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4000
            },
            timeout=90
        )
        
        if response.status_code != 200:
            return f"❌ API Error {response.status_code}: {response.text[:500]}"
        
        return response.json()['choices'][0]['message']['content']
    
    except Exception as e:
        return f"❌ Request Error: {str(e)}"

# ----------------- DAILY ANALYSIS -----------------
def run_daily_analysis():
    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""You are a professional market analyst. Today's date is {today}.

Run this full analysis:
1. Identify stock sectors with highest short-term momentum and why.
2. 10-stock high-probability watchlist with volatility, volume, catalyst potential.
3. 5 day trading setups with entry, stop loss, profit targets.
4. Capital management strategy for aggressive gains with limited downside.
5. Upcoming earnings, macro events, or news this week.
6. How to compound daily gains responsibly.

Be concise, actionable, use real-time context. Use clear headings."""

    with st.spinner("Generating today's market analysis..."):
        result = call_grok(prompt)
        st.session_state.daily_results = result
        return result

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Run Today's Full Market Analysis", type="primary"):
        run_daily_analysis()
        st.success("✅ Daily report ready!")
    
    if st.button("🔄 Refresh Portfolio Prices"):
        st.cache_data.clear()
        st.success("Prices refreshed!")

# ----------------- TABS -----------------
tab1, tab2 = st.tabs(["📈 Daily Opportunities", "💼 My Portfolio"])

with tab1:
    st.header("Daily Market Analyst Report")
    if "daily_results" in st.session_state:
        st.markdown(st.session_state.daily_results)
    else:
        st.info("Click the button in the sidebar to generate today's report.")

with tab2:
    st.header("Portfolio Tracker")
    
    with st.expander("➕ Add or Update Holding"):
        col1, col2, col3 = st.columns(3)
        with col1:
            ticker = st.text_input("Ticker", placeholder="AAPL").upper()
        with col2:
            shares = st.number_input("Shares", min_value=0.01, value=10.0)
        with col3:
            cost = st.number_input("Cost Basis per Share ($)", min_value=0.01, value=150.0)
        if st.button("Save Holding"):
            save_holding(ticker, shares, cost)
            st.success(f"{ticker} saved!")
            st.rerun()
    
    portfolio_df = calculate_portfolio()
    if not portfolio_df.empty:
        st.dataframe(portfolio_df.style.format({
            "Current Price": "${:.2f}",
            "Current Value": "${:.2f}",
            "Unrealized Gain $": "${:.2f}",
            "Unrealized Gain %": "{:.2f}%"
        }), use_container_width=True, hide_index=True)
        
        total_gain = portfolio_df["Unrealized Gain $"].sum()
        total_cost = (portfolio_df["Shares"] * portfolio_df["Cost Basis"]).sum()
        st.metric("Total Unrealized P/L", f"${total_gain:,.2f}", 
                  delta=f"{(total_gain/total_cost*100):.2f}%" if total_cost > 0 else "0%")
        
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Portfolio Allocation")
            if portfolio_df["Current Value"].sum() > 0:
                fig_pie = px.pie(portfolio_df, values='Current Value', names='Ticker', title="Allocation by Ticker")
                st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            st.subheader("Gains / Losses")
            fig_bar = px.bar(
                portfolio_df, 
                x='Ticker', 
                y='Unrealized Gain $', 
                title="Unrealized Profit/Loss by Position",
                color='Unrealized Gain %',
                color_continuous_scale='RdYlGn'
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        
        if st.button("🤖 Get AI Buy/Sell Recommendations"):
            portfolio_text = portfolio_df.to_string(index=False)
            suggestion_prompt = f"Analyze this portfolio and suggest buy/sell/hold actions with reasoning:\n\n{portfolio_text}"
            with st.spinner("Analyzing..."):
                suggestions = call_grok(suggestion_prompt)
                st.subheader("🤖 AI Recommendations")
                st.markdown(suggestions)
    else:
        st.info("No holdings yet. Add some above.")

st.caption("Built with Streamlit + yfinance + Grok API • Trade responsibly")
