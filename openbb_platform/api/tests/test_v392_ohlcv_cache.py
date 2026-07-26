# api/tests/test_v392_ohlcv_cache.py
"""v3.9.2 — shared on-disk OHLCV cache round-trip + safety. No network."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api import data_ingestion as di
from api.data_ingestion import (DataPoint, PriceSeries, _ohlcv_cache_read,
                                _ohlcv_cache_write, _ohlcv_key)


def _series(sym="VOLV-B.ST", n=30):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pts = [DataPoint(base, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 1000.0 + i) for i in range(n)]
    return PriceSeries(symbol=sym, points=pts, source="yfinance", as_of=base,
                       asset_class="equity", currency="SEK", meta={"resolved": sym})


def test_key_is_filesystem_safe():
    k = _ohlcv_key("OMXSTO:VOLV/B .ST", "equity", 1100)
    assert "/" not in k and ":" not in k and " " not in k
    assert k.endswith(".json")


def test_round_trip_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(di, "_OHLCV_CACHE_DIR", tmp_path)
    s = _series()
    assert _ohlcv_cache_read("VOLV-B.ST", "equity", 1100) is None       # cold miss
    _ohlcv_cache_write("VOLV-B.ST", "equity", 1100, s)
    got = _ohlcv_cache_read("VOLV-B.ST", "equity", 1100)
    assert got is not None
    assert got.meta.get("ohlcv_cache") == "hit"
    assert got.source == "yfinance"                                     # provenance preserved
    assert got.currency == "SEK"
    assert len(got.points) == len(s.points)
    assert abs(got.closes[-1] - s.closes[-1]) <= 1e-9
    assert got.as_of == s.as_of                                         # as_of preserved (not stale)


def test_ttl_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(di, "_OHLCV_CACHE_DIR", tmp_path)
    monkeypatch.setattr(di, "_OHLCV_TTL_S", 1.0)
    _ohlcv_cache_write("AAA", "equity", 1100, _series("AAA"))
    fp = tmp_path / _ohlcv_key("AAA", "equity", 1100)
    old = time.time() - 10  # older than the 1s TTL
    import os
    os.utime(fp, (old, old))
    assert _ohlcv_cache_read("AAA", "equity", 1100) is None             # expired -> miss


def test_corrupt_file_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(di, "_OHLCV_CACHE_DIR", tmp_path)
    (tmp_path / _ohlcv_key("BBB", "equity", 1100)).write_text("{ not json")
    assert _ohlcv_cache_read("BBB", "equity", 1100) is None             # never raises


def test_too_few_points_not_served(tmp_path, monkeypatch):
    monkeypatch.setattr(di, "_OHLCV_CACHE_DIR", tmp_path)
    _ohlcv_cache_write("CCC", "equity", 1100, _series("CCC", n=5))       # < MIN_POINTS
    assert _ohlcv_cache_read("CCC", "equity", 1100) is None
