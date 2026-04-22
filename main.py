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
    pending_df = load_pending_orders
