import appdirs as ad
ad.user_cache_dir = lambda *args: "/tmp"   # Critical for Streamlit Cloud

import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
from datetime import datetime
import json
import sqlite3
import requests
import os

st.set_page_config(page_title="AI Stock Dashboard", layout="wide")
st.title("🚀 My Personal AI Stock Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M %p EST')}")

# ----------------- HELPER FUNCTIONS -----------------
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

import time
import random
from yfinance import Ticker

def calculate_portfolio():
    df = load_holdings()
    if df.empty:
        return pd.DataFrame()
    
    data = []
    for _, row in df.iterrows():
        ticker_symbol = row['ticker']
        try:
            # Small random delay to avoid hammering Yahoo
            time.sleep(random.uniform(0.8, 1.5))
            
            ticker = Ticker(ticker_symbol)
            info = ticker.info
            
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or \
                           info.get('previousClose') or info.get('regularMarketPreviousClose', 0)
            
            if current_price == 0:
                current_price = 0  # fallback
            
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
            
        except Exception as e:  # Catch rate limit and other yfinance errors
            data.append({
                'Ticker': ticker_symbol,
                'Shares': row['shares'],
                'Cost Basis': round(row['cost_basis'], 2),
                'Current Price': "Error",
                'Current Value': "N/A",
                'Unrealized Gain $': "N/A",
                'Unrealized Gain %': "N/A"
            })
            st.warning(f"Could not fetch data for {ticker_symbol}: {str(e)[:100]}...")
    
    return pd.DataFrame(data)



# ----------------- GROK API CALL -----------------
def call_grok(prompt):
    api_key = os.environ.get("GROK_API_KEY")
    if not api_key:
        return "❌ Grok API key not found in Streamlit Secrets."
    
    # Updated model - try these one at a time
    model = "grok-4.1-fast-reasoning"
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4000
            },
            timeout=90
        )
        
        if response.status_code != 200:
            error_detail = response.text[:500]  # Show more info
            return f"❌ API Error {response.status_code}: {error_detail}"
        
        data = response.json()
        return data['choices'][0]['message']['content']
    
    except requests.exceptions.RequestException as e:
        return f"❌ Request Error: {str(e)}"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return f"❌ Response parsing error: {str(e)}\nRaw response: {response.text[:300]}"

# ----------------- DAILY ANALYSIS -----------------
def run_daily_analysis():
    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""You are a professional market analyst. Today's date is {today}.

Run this full analysis in today's market:

1. Identify stock sectors with the highest short-term momentum and explain why.
2. Build a high-probability watchlist: Give me 10 stocks with volatility, volume, and catalyst potential for active traders.
3. Create 5 day trading setups with entry zones, stop losses, and profit targets.
4. Create a capital management strategy to target aggressive gains while limiting downside.
5. Find upcoming earnings, macro events, or news that could move stocks this week.
6. Show how to compound daily gains responsibly into long-term capital growth.

Be concise, actionable, and use real-time market context. Format with clear headings and bullet points."""
    
    with st.spinner("Calling Grok for today's full market analysis..."):
        result = call_grok(prompt)
        st.session_state.daily_results = result
        return result

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Run Today's Full Market Analysis", type="primary"):
        run_daily_analysis()
        st.success("✅ Daily report ready!")
    
    st.divider()
    st.write("**Portfolio Tools**")
    if st.button("🤖 Get AI Buy/Sell Suggestions"):
        st.session_state.show_suggestions = True

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
    
    # Add/Edit Holding
    with st.expander("➕ Add or Update Holding"):
        col1, col2, col3 = st.columns(3)
        with col1:
            ticker = st.text_input("Ticker Symbol", placeholder="AAPL").upper()
        with col2:
            shares = st.number_input("Number of Shares", min_value=0.01, value=10.0)
        with col3:
            cost = st.number_input("Cost Basis per Share ($)", min_value=0.01, value=150.0)
        
        if st.button("Save Holding"):
            save_holding(ticker, shares, cost)
            st.success(f"✅ {ticker} saved!")
            st.rerun()
    
    # Display Portfolio
    portfolio_df = calculate_portfolio()
    if not portfolio_df.empty:
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
        
        # === NEW: Simple Visuals (Charts) ===
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Portfolio Allocation")
            if "Current Value" in portfolio_df.columns and portfolio_df["Current Value"].sum() > 0:
                fig_pie = px.pie(
                    portfolio_df, 
                    values='Current Value', 
                    names='Ticker', 
                    title="Allocation by Ticker"
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Add holdings with positive value to see allocation chart.")
        
        with col2:
            st.subheader("Gains / Losses")
            fig_bar = px.bar(
                portfolio_df, 
                x='Ticker', 
                y='Unrealized Gain $', 
                title="Unrealized Profit/Loss by Position",
                color='Unrealized Gain %',
                color_continuous_scale='RdYlGn'  # Green = profit, Red = loss
            )
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No holdings yet. Add some using the form above.")
        st.metric("Total Unrealized P/L", f"${total_gain:,.2f}", 
                  delta=f"{(total_gain/total_cost*100):.2f}%" if total_cost > 0 else "0%")
    else:
        st.info("No holdings yet. Add some using the form above.")

    # AI Suggestions
    if st.button("🤖 Get AI Buy/Sell/Hold Recommendations") or st.session_state.get("show_suggestions", False):
        if not portfolio_df.empty:
            portfolio_text = portfolio_df.to_string(index=False)
            suggestion_prompt = f"""Analyze this portfolio and give specific buy, sell, or hold recommendations.

Portfolio:
{portfolio_text}

Today's top momentum sectors and watchlist (from earlier analysis): [Insert latest if available, otherwise use general knowledge]

Give clear actions with reasoning, risk levels, and suggested position sizes."""
            
            with st.spinner("Analyzing your portfolio..."):
                suggestions = call_grok(suggestion_prompt)
                st.subheader("🤖 AI Recommendations")
                st.markdown(suggestions)
        else:
            st.warning("Add some holdings first.")

st.caption("Built with Streamlit + yfinance + Grok API on Replit. Trade responsibly — this is for educational use.")
