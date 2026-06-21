import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("📈 OpenBB Stock Analysis Dashboard")
st.subheader("Analyze multiple stocks locally using OpenBB-style data")

# --- SIDEBAR ---
st.sidebar.header("Settings")

tickers_input = st.sidebar.text_input(
    "Enter stock tickers (comma-separated)",
    value="AAPL,MSFT,NVDA"
)

start_date = st.sidebar.date_input("Start date", pd.to_datetime("2023-01-01"))
end_date = st.sidebar.date_input("End date", pd.to_datetime("today"))

run = st.sidebar.button("Run Analysis")

# --- MAIN LOGIC ---
if run:
    tickers = [t.strip().upper() for t in tickers_input.split(",")]

    prices = yf.download(
        tickers,
        start=start_date,
        end=end_date,
        auto_adjust=True
    )["Close"]

    st.subheader("📊 Price Data")
    st.dataframe(prices.tail())

    # Normalize prices
    normalized = prices / prices.iloc[0] * 100

    st.subheader("📈 Normalized Performance (Start = 100)")
    fig = px.line(
        normalized,
        labels={"value": "Normalized Price", "index": "Date"},
        title="Stock Performance Comparison"
    )
    st.plotly_chart(fig, width="stretch")

    # Returns table
    returns = ((prices.iloc[-1] / prices.iloc[0]) - 1) * 100
    returns_df = returns.to_frame(name="Total Return (%)").round(2)

    st.subheader("📌 Total Returns")
    st.table(returns_df)
