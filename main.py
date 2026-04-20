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

def clear_all_holdings():
    conn = get_db_connection()
    conn.execute("DELETE FROM holdings")
    conn.commit()
    conn.close()

# ----------------- PORTFOLIO CALCULATION -----------------
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

# ----------------- GROK API CALL -----------------
def call_grok(prompt):
    api_key = os.environ.get("GROK_API_KEY")
    if not api_key:
        return "❌ Grok API key not found in Streamlit Secrets."
    
    model = "grok-4.1-fast-reasoning"
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 6000
            },
            timeout=120
        )
        
        if response.status_code != 200:
            return f"❌ API Error {response.status_code}: {response.text[:600]}"
        
        return response.json()['choices'][0]['message']['content']
    
    except Exception as e:
        return f"❌ Request Error: {str(e)}"

# ----------------- COMBINED FULL ANALYSIS -----------------
def run_full_analysis():
    today = datetime.now().strftime("%B %d, %Y")
    
    portfolio_df = calculate_portfolio()
    portfolio_text = portfolio_df.to_string(index=False) if not portfolio_df.empty else "No holdings yet."
    
    prompt = f"""You are a professional market analyst and portfolio manager. Today's date is {today}.

Provide a **comprehensive daily report** that combines market analysis with personalized portfolio advice.

**Part 1: Market Overview**
1. Identify stock sectors with the highest short-term momentum and explain why.
2. Build a high-probability watchlist: 10 stocks with strong volatility, volume, and catalyst potential for active traders.
3. Create 5 actionable day trading setups with specific entry zones, stop losses, and profit targets.
4. Suggest a capital management / risk strategy for aggressive gains while limiting downside.
5. List upcoming earnings, macro events, or news catalysts that could move stocks this week.

**Part 2: Personalized Portfolio Analysis & Recommendations**
My current portfolio:
{portfolio_text}

For each existing holding and potential new opportunities:
- Give a clear **Buy / Sell / Hold / Trim / Add** recommendation
- Suggest **specific entry or exit price zones** or technical triggers
- State **how much** to buy or sell (e.g., "Trim 25% of position", "Add 15-20 shares", "% of total portfolio", or dollar amount)
- Recommend **diversification moves** (e.g., rotate capital from Tech into Energy or Industrials)
- Provide clear reasoning tied to current momentum, valuation, catalysts, and risk
- Assign a risk level (Low / Medium / High) and suggest stop-loss ideas

**Overall Portfolio Strategy**
- Rebalancing summary: What percentage should be in hot momentum sectors vs defensive plays?
- Suggested new positions or watchlist stocks for entry
- How to compound daily gains responsibly into long-term growth
- Risk management notes for aggressive but sustainable growth

Be detailed, realistic, and actionable. Use clear headings, bullet points, and sections for easy reading."""

    with st.spinner("Generating full daily market analysis + personalized portfolio recommendations..."):
        result = call_grok(prompt)
        st.session_state.full_analysis = result
        return result

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.header("Controls")
    if st.button("🔥 Run Full Daily Analysis + Portfolio Advice", type="primary"):
        run_full_analysis()
        st.success("✅ Full analysis with portfolio recommendations ready!")
    
    if st.button("🔄 Refresh Portfolio Prices"):
        st.cache_data.clear()
        st.success("Portfolio prices refreshed!")

# ----------------- TABS -----------------
tab1, tab2 = st.tabs(["📈 Full Analysis", "💼 My Portfolio"])

with tab1:
    st.header("Full Daily Market + Portfolio Analysis")
    if "full_analysis" in st.session_state:
        st.markdown(st.session_state.full_analysis)
    else:
        st.info("Click the big button in the sidebar to generate today's comprehensive report.")

with tab2:
    st.header("Portfolio Tracker")
    
    # Add or Update Holding
    with st.expander("➕ Add or Update Holding"):
        col1, col2, col3 = st.columns(3)
        with col1:
            ticker = st.text_input("Ticker Symbol", placeholder="AAPL").upper()
        with col2:
            shares = st.number_input("Number of Shares", min_value=0.01, value=10.0)
        with col3:
            cost = st.number_input("Cost Basis per Share ($)", min_value=0.01, value=150.0)
        
        if st.button("Save Holding", type="primary"):
            if ticker and shares > 0 and cost > 0:
                save_holding(ticker, shares, cost)
                st.cache_data.clear()
                st.success(f"✅ {ticker} saved successfully!")
                time.sleep(0.8)
                st.rerun()
            else:
                st.error("Please fill in all fields correctly.")
    
    # NEW: Clear Portfolio Button
    if st.button("🗑️ Clear All Portfolio Data", type="secondary"):
        if st.checkbox("⚠️ I confirm I want to permanently delete ALL holdings"):
            clear_all_holdings()
            st.cache_data.clear()
            st.success("✅ All portfolio data has been cleared!")
            time.sleep(1.0)
            st.rerun()
        else:
            st.warning("Please check the confirmation box to clear all data.")
    
    # Display Portfolio
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
    else:
        st.info("No holdings yet. Add some using the form above.")

st.caption("Built with Streamlit + yfinance + Grok API • For educational use only • Trade responsibly")
