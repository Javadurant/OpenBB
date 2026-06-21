# engine/processor.py
import json
from features.indicators import calculate_fib_levels

def generate_fibonacci_blocks(data_list: list) -> list:
    """
    Generates JSON data blocks for DFEE compliance.
    Matches the [OUTPUT_SCHEMA] requested.
    """
    output = []
    for i, item in enumerate(data_list):
        sh = item['sh']
        sl = item['sl']
        levels = calculate_fib_levels(sh, sl)
        
        block = {
            "point_id": i,
            "asset": item.get('asset', 'N/A'),
            "swing_high": float(sh),
            "swing_low": float(sl),
            "levels": levels,
            "checksum": round((sh - sl) * 0.618, 8)
        }
        output.append(block)
    return output

if __name__ == "__main__":
    # Integration of the 10 provided data points
    input_data = [
        {"asset": "OMXS30", "sl": 2097.58, "sh": 3191.47},
        {"asset": "TEDPIX", "sl": 2000000.0, "sh": 4481000.0},
        {"asset": "Investor AB", "sl": 235.40, "sh": 370.70},
        {"asset": "Volvo AB", "sl": 220.15, "sh": 353.20},
        {"asset": "S&P 500", "sl": 4700.12, "sh": 6896.70},
        {"asset": "Bitcoin", "sl": 38505.00, "sh": 104200.00},
        {"asset": "Gold", "sl": 1984.00, "sh": 5186.25},
        {"asset": "Nvidia", "sl": 45.00, "sh": 192.85},
        {"asset": "EUR/USD", "sl": 1.0450, "sh": 1.1820},
        {"asset": "Tesla", "sl": 138.80, "sh": 409.40}
    ]
    
    blocks = generate_fibonacci_blocks(input_data)
    print(json.dumps(blocks, indent=2))