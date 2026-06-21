from openbb import obb

# List of stocks to analyze
tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]

for ticker in tickers:
    print("\n==============================")
    print(f"📊 {ticker} — Historical Prices")
    print("==============================")

    data = obb.equity.price.historical(ticker)
    df = data.to_dataframe()

    print(df.tail())  # show latest prices
