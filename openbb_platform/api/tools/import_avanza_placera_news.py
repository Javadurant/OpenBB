"""Avanza / Placera manual-news importer (v3.4) — safe visible-copy route ONLY.

Avanza is a native authenticated app: no login automation, no scraping, no
session data, no account/holdings access. The authorized route is what YOU can
see and copy: headline, timestamp, summary.

Workflow:
  1. Open the Avanza app -> stock page -> news (Placera).
  2. Copy headline + timestamp (+ summary if shown).
  3. venv/bin/python -m api.tools.import_avanza_placera_news --template item.json
  4. Fill item.json (one item or a list), then:
     venv/bin/python -m api.tools.import_avanza_placera_news --import item.json
  5. Imported items land in news_reference/avanza_placera/imported.jsonl with
     model-derived (lexicon) sentiment incl. Swedish terms, staleness and
     event-risk flags, deduplicated on (headline, article_time).

The scanner consumes these via its news_context shape ({title, summary,
age_days}); source provenance marks them Avanza/Placera manual-copy.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

NEWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "news_reference", "avanza_placera")
STORE = os.path.join(NEWS_DIR, "imported.jsonl")
REQUIRED = ("symbol", "headline", "article_time")
_SV_HINTS = re.compile(r"[åäöÅÄÖ]|(\b(och|för|höjer|sänker|rapport|aktien|bolaget)\b)", re.I)

TEMPLATE = {
    "source": "Avanza/Placera",
    "capture_method": "app_visible_copy",
    "symbol": "SKF-B.ST",
    "company_name": "",
    "market": "Swedish",
    "asset_class": "stock",
    "headline": "",
    "summary": "",
    "article_time": "2026-07-11T09:30",
    "capture_time": "",
    "url_or_reference": "",
    "language": "",
    "notes": "",
}


def detect_language(text: str) -> str:
    return "sv" if _SV_HINTS.search(text or "") else "en"


def normalize(item: dict, today: date | None = None) -> dict:
    """Validate + enrich one manual item. Raises ValueError on missing fields."""
    from api.setup_scanner import NEWS_STALE_DAYS, news_sentiment
    missing = [k for k in REQUIRED if not item.get(k)]
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    today = today or datetime.now(timezone.utc).date()
    try:
        art = datetime.fromisoformat(str(item["article_time"]).replace("Z", "+00:00"))
        age_days = max(0, (today - art.date()).days)
    except ValueError as exc:
        raise ValueError(f"article_time not ISO-8601: {item['article_time']}") from exc
    text = f"{item['headline']} {item.get('summary', '')}"
    lang = item.get("language") or detect_language(text)
    senti = news_sentiment([{"title": item["headline"],
                             "summary": item.get("summary", ""),
                             "age_days": age_days}])
    return {
        **{k: item.get(k, "") for k in TEMPLATE},
        "language": lang,
        "age_days": age_days,
        "is_stale": age_days > NEWS_STALE_DAYS,
        "sentiment": senti["label"],
        "sentiment_score": senti["score"],
        "sentiment_source": "lexicon (model-derived)",
        "sentiment_confidence": senti["confidence"],
        "event_risk": senti.get("event_risk", False),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def dedup_key(item: dict) -> str:
    return f"{(item.get('headline') or '').strip().lower()}|{item.get('article_time')}"


def import_items(items: list[dict], store: str = STORE) -> dict:
    os.makedirs(os.path.dirname(store), exist_ok=True)
    seen: set[str] = set()
    if os.path.exists(store):
        with open(store, encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.add(dedup_key(json.loads(line)))
                except json.JSONDecodeError:
                    continue
    imported, duplicates, errors = 0, 0, []
    with open(store, "a", encoding="utf-8") as fh:
        for raw in items:
            try:
                rec = normalize(raw)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if dedup_key(rec) in seen:
                duplicates += 1
                continue
            seen.add(dedup_key(rec))
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            imported += 1
    return {"imported": imported, "duplicates": duplicates, "errors": errors,
            "store": store}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--template")
    p.add_argument("--import", dest="import_path")
    a = p.parse_args()
    if a.template:
        with open(a.template, "w", encoding="utf-8") as fh:
            json.dump(TEMPLATE, fh, indent=2, ensure_ascii=False)
        print(f"template written: {a.template} (single item or a JSON list)")
        return 0
    if a.import_path:
        with open(a.import_path, encoding="utf-8") as fh:
            data = json.load(fh)
        result = import_items(data if isinstance(data, list) else [data])
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if not result["errors"] else 1
    p.error("use --template FILE or --import FILE")
    return 2


if __name__ == "__main__":
    sys.exit(main())
