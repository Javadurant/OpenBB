from openbb import obb

data = obb.equity.price.historical("AAPL")

df = data.to_dataframe()
print(df.head())
