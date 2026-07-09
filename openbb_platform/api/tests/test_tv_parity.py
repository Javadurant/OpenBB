"""TradingView parity — empirical reference-case comparison.

Clean-room policy: exact TradingView parity cannot be proven without the same
feed/script internals, so this suite compares the Setup Scanner's indicator
math against AUTHORIZED TradingView reference exports placed in tv_reference/
(see its README for the JSON format and capture instructions).

Each case supplies the SAME OHLCV bars TradingView displayed plus the values
TradingView showed; only the keys present in `tv_values` are compared. The
whole suite skips when no reference cases exist yet.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

_REF_DIR = pathlib.Path(__file__).parent / "tv_reference"
_CASES = sorted(_REF_DIR.glob("*.json"))

DEFAULT_TOL = {"rsi_14": 1.5, "tenkan_pct": 0.2, "kijun_pct": 0.2}


def _load(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.skipif(not _CASES, reason="no TradingView reference cases exported yet "
                                       "(see api/tests/tv_reference/README.md)")
@pytest.mark.parametrize("case_path", _CASES, ids=[p.stem for p in _CASES])
def test_tv_reference_case(case_path):
    from api.setup_scanner import _atr, _ichimoku_state, _macd_state, _rsi
    case = _load(case_path)
    o = case["ohlcv"]
    closes, highs, lows = o["closes"], o["highs"], o["lows"]
    tv = case["tv_values"]
    tol = {**DEFAULT_TOL, **case.get("tolerances", {})}

    if "rsi_14" in tv:
        ours = _rsi(closes)
        assert ours is not None
        assert abs(ours - tv["rsi_14"]) <= tol["rsi_14"], (
            f"RSI mismatch: ours {ours:.2f} vs TV {tv['rsi_14']:.2f}")

    if "tenkan" in tv or "kijun" in tv:
        atr = _atr(highs, lows, closes)
        ichi = _ichimoku_state(highs, lows, closes, atr or 1.0)
        assert ichi is not None
        if "tenkan" in tv:
            assert abs(ichi["tenkan"] - tv["tenkan"]) / tv["tenkan"] * 100 <= tol["tenkan_pct"], (
                f"Tenkan mismatch: ours {ichi['tenkan']:.2f} vs TV {tv['tenkan']:.2f}")
        if "kijun" in tv:
            assert abs(ichi["kijun"] - tv["kijun"]) / tv["kijun"] * 100 <= tol["kijun_pct"], (
                f"Kijun mismatch: ours {ichi['kijun']:.2f} vs TV {tv['kijun']:.2f}")

    if "macd_hist_positive" in tv:
        macd = _macd_state(closes)
        assert macd is not None
        assert (macd["hist"] > 0) == bool(tv["macd_hist_positive"]), (
            f"MACD histogram sign mismatch: ours {macd['hist']:.4f}")
