from openbb import obb  # type: ignore[attr-defined]

# Pull historical price data
data = obb.equity.price.historical("AAPL")  # type: ignore[attr-defined]

# Convert to pandas DataFrame — OpenBB 4.x uses .to_df() not .to_dataframe()
df = data.to_df()  # <- FIXED [FM-07]: to_dataframe() removed in OpenBB 4.x

# Basic analysis
print("\n=== LAST 5 DAYS ===")
print(df.tail())

print("\n=== SUMMARY ===")
print(df.describe())

print("\n=== RETURNS (%) ===")
returns = df["close"].pct_change() * 100
print(returns.tail())