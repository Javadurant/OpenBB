from openbb import obb

# Pull historical price data
data = obb.equity.price.historical("AAPL")

# Convert to pandas DataFrame
df = data.to_dataframe()

# Basic analysis
print("\n=== LAST 5 DAYS ===")
print(df.tail())

print("\n=== SUMMARY ===")
print(df.describe())

print("\n=== RETURNS (%) ===")
returns = df["close"].pct_change() * 100
print(returns.tail())
