# TradingView reference cases — parity framework

Exact TradingView parity cannot be proven without authorized access to the same
data/feed/script internals. This directory implements the clean-room approach:
drop authorized TradingView exports here and `test_tv_parity.py` empirically
compares the Setup Scanner's indicator math against them.

## File format (one JSON per case)

```json
{
  "symbol": "SKF-B.ST",
  "as_of": "2026-07-09",
  "source": "TradingView Desktop (manual read / MCP data_get_study_values)",
  "ohlcv": {
    "closes": [ ... ],
    "highs":  [ ... ],
    "lows":   [ ... ]
  },
  "tv_values": {
    "rsi_14":    59.1,
    "tenkan":    256.10,
    "kijun":     251.65,
    "macd_hist_positive": true
  },
  "tolerances": { "rsi_14": 1.5, "tenkan_pct": 0.2, "kijun_pct": 0.2 }
}
```

- `ohlcv` must be the SAME bars TradingView displayed (export or MCP capture),
  otherwise differences measure the FEED, not the math.
- Omit any `tv_values` key you did not capture; only present keys are compared.
- Default tolerances: RSI ±1.5 points, Tenkan/Kijun ±0.2%, MACD sign match.

How to capture with the TradingView MCP (desktop app running):
`chart_get_state` → `data_get_ohlcv` → `data_get_study_values`, then save the
JSON here. The test suite skips silently when this directory has no cases.
