# generate_mock_data.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_mock_harmonic_data(points: int = 100) -> pd.DataFrame:
    """Generates a DataFrame with OHLC columns for testing."""
    np.random.seed(42)
    base_price = 100.0
    
    # Create a random walk to simulate stock movement
    changes = np.random.normal(0, 0.5, points)
    prices = base_price + np.cumsum(changes)
    
    dates = [datetime.now() - timedelta(minutes=i) for i in range(points)]
    dates.reverse()

    df = pd.DataFrame({
        'Open': prices,
        'High': prices + 0.2,
        'Low': prices - 0.2,
        'Close': prices,
        'Volume': np.random.randint(1000, 5000, points)
    }, index=dates)
    
    return df

if __name__ == "__main__":
    test_df = create_mock_harmonic_data()
    print("✅ Mock Data Generated")
    print(test_df.head())
    
    try:
        from engine.analysis.harmonics import HarmonicEngine
        engine = HarmonicEngine()
        patterns = engine.detect(test_df)
        print(f"✅ Detection run complete. Found {len(patterns)} patterns.")
    except Exception as e:
        print(f"❌ Detection failed: {e}")
