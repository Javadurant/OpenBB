"""v3.5 limitation-removal tests: FMP capability probe, Avanza scanner hook,
intraday importer, TV template exclusion, conflict-type mapper."""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ── FMP capability probe ─────────────────────────────────────────────────────

def test_fmp_capabilities_no_key(monkeypatch):
    from api import fmp_news
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr(fmp_news, "_CAPS_CACHE", {})
    caps = fmp_news.fmp_capabilities(force=True)
    assert caps["fmp_key_present"] is False
    assert caps["fmp_plan_gate_reason"] == "FMP_API_KEY not set"
    assert caps["fmp_news_available"] is False


def test_fmp_capabilities_plan_gate_reason_no_secret(monkeypatch):
    import urllib.error
    import urllib.request
    from api import fmp_news
    monkeypatch.setenv("FMP_API_KEY", "SECRETKEY-NEVER-SHOWN")
    monkeypatch.setattr(fmp_news, "_CAPS_CACHE", {})

    def gated(req, timeout=0):
        raise urllib.error.HTTPError(url="x", code=402, msg="Payment Required",
                                     hdrs=None, fp=None)
    monkeypatch.setattr(urllib.request, "urlopen", gated)
    caps = fmp_news.fmp_capabilities(force=True)
    assert caps["fmp_key_present"] is True
    assert caps["fmp_news_available"] is False
    assert "HTTP 402" in caps["fmp_plan_gate_reason"]
    assert "SECRETKEY" not in json.dumps(caps)


# ── Avanza scanner consumption hook ──────────────────────────────────────────

def test_load_avanza_news_fresh_only(tmp_path):
    from api.tools.import_avanza_placera_news import import_items, load_avanza_news
    store = str(tmp_path / "imported.jsonl")
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT09:00")
    old = "2026-01-05T09:00"
    import_items([
        {"symbol": "SKF-B.ST", "headline": "SKF slår förväntningar", "article_time": recent},
        {"symbol": "SKF-B.ST", "headline": "Gammal nyhet om SKF", "article_time": old},
        {"symbol": "VOLV-B.ST", "headline": "Volvo orderingång", "article_time": recent},
    ], store=store)
    items = load_avanza_news("SKF-B.ST", store=store)
    assert len(items) == 1                      # stale + other-symbol excluded
    assert items[0]["title"] == "SKF slår förväntningar"
    assert items[0]["age_days"] <= 3
    assert load_avanza_news("MISSING.ST", store=store) == []


def test_avanza_samples_file_imports(tmp_path):
    from api.tools.import_avanza_placera_news import import_items
    samples = json.loads((_ROOT / "news_reference" / "avanza_placera"
                          / "samples.json").read_text(encoding="utf-8"))
    res = import_items(samples, store=str(tmp_path / "s.jsonl"))
    assert res["imported"] == 4 and not res["errors"]


# ── Intraday importer ────────────────────────────────────────────────────────

def _bars(n=40, start_h=9):
    out = []
    t0 = datetime(2026, 7, 10, start_h, 0)
    for i in range(n):
        t = t0 + timedelta(minutes=15 * i)
        px = 100 + i * 0.1
        out.append({"time": t.isoformat(), "open": px, "high": px + 0.2,
                    "low": px - 0.2, "close": px + 0.05, "volume": 1000})
    return out


def test_intraday_validate_and_roundtrip(tmp_path, monkeypatch):
    from api.tools import import_intraday as ii
    monkeypatch.setattr(ii, "REF_DIR", str(tmp_path))
    good = {"symbol": "SKF-B.ST", "timeframe": "15m",
            "timezone": "Europe/Stockholm", "source": "tradingview_export",
            "bars": _bars()}
    assert ii.validate_series(good) == []
    ii.save_series(good)
    ref = ii.load_intraday_reference("SKF-B.ST")
    assert ref is not None
    highs, lows, closes, per_day = ref
    assert len(closes) == 40 and per_day == 34   # .ST 15m session bars
    # refiner consumes it directly
    from api.setup_scanner import refine_target_time_intraday
    r = refine_target_time_intraday("2026-07-21", 2.0, highs, lows, closes,
                                    per_day, "Europe/Stockholm")
    assert r["intraday_available"] is True


def test_intraday_validation_rejects_garbage():
    from api.tools.import_intraday import validate_series
    assert any("timeframe" in e for e in validate_series(
        {"symbol": "X", "timeframe": "3m", "timezone": "T", "source": "s",
         "bars": _bars()}))
    assert any("bars" in e for e in validate_series(
        {"symbol": "X", "timeframe": "15m", "timezone": "T", "source": "s",
         "bars": _bars(5)}))
    bad = _bars()
    bad[3]["high"] = bad[3]["low"] - 1            # OHLC sanity violation
    assert any("sanity" in e for e in validate_series(
        {"symbol": "X", "timeframe": "15m", "timezone": "T", "source": "s",
         "bars": bad}))


# ── TV templates excluded from parity + conflict-type mapper ────────────────

def test_tv_templates_excluded_from_parity_glob():
    import api.tests.test_tv_parity as tp
    assert all(not p.name.startswith("TEMPLATE-") for p in tp._CASES)
    templates = list((_ROOT / "api" / "tests" / "tv_reference").glob("TEMPLATE-*.json"))
    assert len(templates) >= 3                    # SKF/VOLV/AAPL ready to fill


def test_conflict_type_mapper():
    from api.tools.backtest_v33 import conflict_type
    assert conflict_type("earnings report 2026-07-17 inside the target window - x") == "earnings_window"
    assert conflict_type("MACD histogram falling while trend is up") == "macd_fading"
    assert conflict_type("Elliott preferred count is a bearish IMPULSE (Wave 3 in_progress) - structure argues against a buy") == "elliott_bearish_preferred"
    assert conflict_type("overhead pivot resistance ~261.37 within 1 ATR, before the target") == "overhead_resistance"
    assert conflict_type("market regime risk-off: ^OMX below its 200-day MA - x") == "regime_risk_off"
    assert conflict_type("something entirely new") == "other"
