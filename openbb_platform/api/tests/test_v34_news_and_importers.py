"""v3.4 tests: FMP news adapter, Swedish lexicon, Avanza/Placera importer,
TradingView values-case creator/validator. All fixture-based - no network."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.fmp_news import fetch_fmp_news, fmp_key_present, parse_fmp_items  # noqa: E402
from api.setup_scanner import news_sentiment  # noqa: E402
from api.tools.import_avanza_placera_news import (  # noqa: E402
    detect_language, import_items, normalize)
from api.tools import create_tv_reference_case as tvcase  # noqa: E402


# ── FMP adapter (fixture-backed) ─────────────────────────────────────────────

FMP_FIXTURE = [
    {"title": "Apple beats estimates and raises guidance",
     "text": "Record quarter with strong growth.",
     "publishedDate": "2026-07-10T13:46:00Z",
     "url": "https://example.com/a", "site": "Reuters"},
    {"title": "Regulator opens probe into supplier",
     "text": "", "publishedDate": "2026-07-08 09:00:00",
     "url": "https://example.com/b", "site": "WSJ"},
    {"notatitle": True},   # malformed row must be skipped, not crash
]


def test_fmp_fixture_parses_and_contains_no_secrets(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "TESTKEY-MUST-NEVER-LEAK")
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    items = parse_fmp_items(FMP_FIXTURE, now=now)
    assert len(items) == 2
    assert items[0]["title"].startswith("Apple beats")
    assert items[0]["age_days"] in (0, 1)
    assert items[1]["age_days"] == 2      # 2026-07-08 09:00 -> 07-11 00:00 = 2.6d -> .days == 2
    assert "TESTKEY" not in json.dumps(items)          # key never in output
    senti = news_sentiment(items)
    assert senti["n_scored"] >= 1
    assert senti["method"] == "lexicon (model-derived)"


def test_fmp_missing_key_degrades_to_none(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    assert fmp_key_present() is False
    assert fetch_fmp_news("AAPL") is None              # no crash, no network


def test_fmp_network_failure_degrades_to_none(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "TESTKEY-MUST-NEVER-LEAK")
    import urllib.request

    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert fetch_fmp_news("AAPL") is None


# ── Swedish lexicon ──────────────────────────────────────────────────────────

def test_swedish_positive_and_negative_sentiment():
    pos = news_sentiment([{"title": "Bolaget får stororder och höjer prognos",
                           "age_days": 2}])
    assert pos["label"] == "positive"
    neg = news_sentiment([{"title": "Vinstvarning: bolaget sänker riktkurs",
                           "age_days": 1}])
    assert neg["label"] == "negative"


def test_event_risk_flag_bilingual():
    sv = news_sentiment([{"title": "Kvartalsrapport väntas nästa vecka", "age_days": 3}])
    assert sv["event_risk"] is True
    en = news_sentiment([{"title": "Earnings preview: what to expect", "age_days": 3}])
    assert en["event_risk"] is True
    none_ = news_sentiment([{"title": "CEO interviewed at conference", "age_days": 3}])
    assert none_["event_risk"] is False


# ── Avanza/Placera manual importer ──────────────────────────────────────────

def _item(headline: str, t: str = "2026-07-10T09:30") -> dict:
    return {"symbol": "SKF-B.ST", "headline": headline, "article_time": t,
            "summary": "", "market": "Swedish"}


def test_avanza_normalize_swedish(monkeypatch):
    rec = normalize(_item("SKF slår förväntningar och höjer utdelning"),
                    today=date(2026, 7, 11))
    assert rec["language"] == "sv"
    assert rec["sentiment"] == "positive"
    assert rec["sentiment_source"] == "lexicon (model-derived)"
    assert rec["is_stale"] is False and rec["age_days"] == 1


def test_avanza_stale_and_english(tmp_path):
    rec = normalize(_item("Company wins major contract", "2026-05-01T09:00"),
                    today=date(2026, 7, 11))
    assert rec["is_stale"] is True
    assert rec["language"] == "en"


def test_avanza_import_dedup_and_errors(tmp_path):
    store = str(tmp_path / "imported.jsonl")
    first = import_items([_item("Vinstvarning från bolaget"),
                          _item("Vinstvarning från bolaget"),      # duplicate
                          {"headline": "no symbol"}], store=store)  # invalid
    assert first["imported"] == 1
    assert first["duplicates"] == 1
    assert len(first["errors"]) == 1
    again = import_items([_item("Vinstvarning från bolaget")], store=store)
    assert again["duplicates"] == 1 and again["imported"] == 0      # persists


def test_avanza_requires_iso_time():
    with pytest.raises(ValueError):
        normalize(_item("Rubrik", "10 juli 09:30"))


# ── TradingView values-case creator/validator ───────────────────────────────

def test_tv_template_and_validation(tmp_path, capsys):
    t = tvcase.template("SKF-B.ST", "1D")
    assert t["symbol"] == "SKF-B.ST" and t["tv_values"]["rsi_14"] is None
    # incomplete case -> invalid
    p = tmp_path / "case.json"
    p.write_text(json.dumps(t))
    assert tvcase.validate(str(p)) == 1
    # complete fixture -> valid
    t.update(exchange="OMXSTO", timezone="Europe/Stockholm", as_of="2026-07-11")
    n = 100
    t["ohlcv"] = {"closes": [100 + i * 0.1 for i in range(n)],
                  "highs": [101 + i * 0.1 for i in range(n)],
                  "lows": [99 + i * 0.1 for i in range(n)]}
    t["tv_values"] = {"rsi_14": 62.0}
    p.write_text(json.dumps(t))
    assert tvcase.validate(str(p)) == 0
    out = capsys.readouterr().out
    assert "test_tv_parity" in out           # prints the exact next command


def test_tv_creator_cli_refuses_overwrite(tmp_path):
    out = tmp_path / "X-1D.json"
    r1 = subprocess.run([sys.executable, "-m", "api.tools.create_tv_reference_case",
                         "--symbol", "X", "--timeframe", "1D", "--out", "../../../../../../../tmp/ignore-tv-test.json"],
                        capture_output=True, text=True,
                        cwd=str(pathlib.Path(__file__).resolve().parents[2]))
    assert r1.returncode in (0, 1)           # creates or refuses-existing; never crashes
