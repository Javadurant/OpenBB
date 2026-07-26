from openbb import obb
from engine.structure.swings import find_pivots
from engine.analysis.elliott import validate_wave_2, project_wave_3

def run_production_pipeline(ticker: str):
    print(f"--- [INITIALIZING DATA FETCH: {ticker}] ---")
    df = obb.equity.price.historical(ticker, provider="yfinance").to_df()
    data_filtered = obb.technical.ema(df, target="close", window=10).to_df()
    pivots = find_pivots(data_filtered)
    
    for i in range(3, 10):
        if len(pivots) < i: break
        p1, p2, p3 = pivots['close'].iloc[-i], pivots['close'].iloc[-(i-1)], pivots['close'].iloc[-(i-2)]
        analysis = validate_wave_2(p1, p2, p3)
        
        if analysis['is_valid']:
            targets = project_wave_3(p1, p2, p3)
            print(f"\n🚀 ANALYSIS FOR {ticker}:")
            print(f"Structure: Valid Wave 1-2 found.")
            print(f"Retrace Ratio: {analysis['ratio']}")
            print("-" * 30)
            print(f"W3 MIN TARGET (1.00): {targets['min_target_100']}")
            print(f"W3 MAIN TARGET (1.618): {targets['target_1618']}")
            print("-" * 30)
            break

if __name__ == "__main__":
    run_production_pipeline("SPY")
