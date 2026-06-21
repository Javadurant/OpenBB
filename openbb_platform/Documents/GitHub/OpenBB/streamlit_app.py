import streamlit as st
from openbb import obb

st.set_page_config(page_title="OpenBB Starter App", layout="wide")

st.title("📈 OpenBB Stock Dashboard (Beginner Safe Version)")

# Sidebar
st.sidebar.header("Stock Selection")
ticker = st.sidebar.text_input("Enter a stock ticker", value="AAPL")

if st.sidebar.button("Load Data"):
    with st.spinner("Fetching data from OpenBB..."):
        data = obb.equity.price.historical(ticker)

        df = data.to_dataframe()

        st.subheader(f"Price Data for {ticker}")
        st.dataframe(df.tail(10))

        st.line_chart(df["close"])
