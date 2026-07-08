"""
api/data_ingestion.py
=====================
SENTRIQ Data Ingestion Service - async multi-source fallback pipeline.

PROVENANCE (LLM Council, May 21 2026):
  The Swedish "data wall" was partly a ticker-discovery bug (BITCOIN-XBT.ST
  was live all along) and partly a real gap (Swedish mutual-fund NAV is not on
  free feeds). Solution: a tiered async-fallback ingestion service that cascades
  through ranked providers until one returns FINITE, FRESH data - never an empty
  placeholder, never a silent stale number.

ARCHITECTURE
  DataPoint / PriceSeries  - normalized output carrying source + as_of provenance
  DataMissingException     - raised only after ALL providers fail
  BaseProvider             - ABC with async fetch(symbol) -> Optional[PriceSeries]
  ProviderManager          - cascades registered providers; NaN-guard + staleness-guard
  DataIngestionService     - facade; one call per symbol

GUARANTEES
  - Every returned series has .source and .as_of (provenance, council-mandated).
  - Normalization drops NaN/inf AND rejects series staler than MAX_STALENESS_DAYS.
  - All-providers-fail -> log to sentriq_errors.log + raise DataMissingException
    (pipeline never crashes the caller).
  - Scraper provider respects robots.txt, rate-limits, and caches (council-mandated).

No float == comparisons. All thresholds are NAMED CONSTANTS. Full type hints.
"""
from __future__ import annotations

import abc
import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final, Optional, Sequence

# ── Logging: dedicated error log file (council-mandated) ──────────────────
logger = logging.getLogger("sentriq.data_ingestion")
if not logger.handlers:
    _fh = logging.FileHandler("sentriq_errors.log")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(_fh)
    logger.setLevel(logging.INFO)

# ── Named constants (no magic numbers) ────────────────────────────────────
MAX_STALENESS_DAYS:   Final = 7          # reject series whose last point is older
MIN_POINTS:           Final = 20         # minimum bars for a usable series
SCRAPE_RATE_LIMIT_S:  Final = 2.0        # min seconds between scraper hits per host
SCRAPE_CACHE_TTL_S:   Final = 3600.0     # scraped NAV cache TTL
PROVIDER_TIMEOUT_S:   Final = 20.0       # per-provider hard timeout
EPS:                  Final = 1e-9
SECONDS_PER_DAY:      Final = 86_400.0


# ── Output contracts ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class DataPoint:
    """One normalized OHLC bar (or NAV point with o=h=l=c)."""
    ts:    datetime
    open:  float
    high:  float
    low:   float
    close: float

    def is_finite(self) -> bool:
        return all(math.isfinite(x) for x in (self.open, self.high, self.low, self.close))


@dataclass
class PriceSeries:
    """Normalized series with provenance. `source` + `as_of` are mandatory."""
    symbol:      str
    points:      list[DataPoint]
    source:      str                       # e.g. "yfinance", "morningstar-se", "riksbank"
    as_of:       datetime                  # timestamp of the most recent point
    asset_class: str = "equity"
    currency:    Optional[str] = None
    meta:        dict = field(default_factory=dict)

    @property
    def closes(self) -> list[float]:
        return [p.close for p in self.points]

    @property
    def staleness_days(self) -> float:
        return (datetime.now(timezone.utc) - self.as_of).total_seconds() / SECONDS_PER_DAY


class DataMissingException(Exception):
    """Raised when every provider in the cascade fails for a symbol."""
    def __init__(self, symbol: str, tried: Sequence[str]):
        self.symbol = symbol
        self.tried = list(tried)
        super().__init__(f"No provider returned fresh, finite data for {symbol!r} "
                         f"(tried: {', '.join(tried) or 'none'})")


# ── Provider ABC ───────────────────────────────────────────────────────────
class BaseProvider(abc.ABC):
    """A data source. Subclasses implement async fetch()."""
    name: str = "base"
    #: asset classes this provider can serve; empty = all
    handles: frozenset[str] = frozenset()

    def can_handle(self, asset_class: str) -> bool:
        return not self.handles or asset_class in self.handles

    @abc.abstractmethod
    async def fetch(self, symbol: str, asset_class: str, lookback_days: Optional[int] = None) -> Optional[PriceSeries]:
        """Return a PriceSeries, or None if this source has no data for `symbol`.

        MUST NOT raise for a simple miss - return None. Exceptions are caught by
        the manager and treated as a miss, but returning None is the contract.
        """
        raise NotImplementedError


# ── Tier 1: yfinance (sync lib wrapped in a thread executor) ───────────────
class YahooFinanceProvider(BaseProvider):
    """Tier 1 - yfinance daily history. Reliable for equities, ETFs, US funds,
    crypto, AND Nasdaq Stockholm crypto ETPs once the correct tickers are used.

    The ALIAS map fixes the council's root-cause finding: callers may ask for
    'BITCOIN-ZERO.ST' (dead) - we transparently resolve to the live tracker
    ('BITCOIN-XBT.ST') so the cell populates instead of falling through."""
    name = "yfinance"

    # Verified-live Nasdaq Stockholm ETP aliases (tested May 21 2026).
    ALIASES: Final[dict[str, str]] = {
        "BITCOIN-ZERO.ST": "BITCOIN-XBT.ST",
        "ETH-ZERO.ST":     "ETHEREUM-XBT.ST",
        "BTC.ST":          "BITCOIN-XBT.ST",
        "ETH.ST":          "ETHEREUM-XBT.ST",
    }

    def _sync_fetch(self, symbol: str, period: str = "1y") -> Optional[list[DataPoint]]:
        import yfinance as yf
        resolved = self.ALIASES.get(symbol, symbol)
        hist = yf.Ticker(resolved).history(period=period)
        if hist is None or len(hist) < MIN_POINTS:
            return None
        pts: list[DataPoint] = []
        for idx, row in hist.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            pts.append(DataPoint(
                ts=ts,
                open=float(row["Open"]), high=float(row["High"]),
                low=float(row["Low"]),  close=float(row["Close"]),
            ))
        return pts

    async def fetch(self, symbol: str, asset_class: str, lookback_days: Optional[int] = None) -> Optional[PriceSeries]:
        period = "1y" if not lookback_days else f"{max(1, (lookback_days + 364) // 365)}y"
        try:
            pts = await asyncio.wait_for(
                asyncio.to_thread(self._sync_fetch, symbol, period), timeout=PROVIDER_TIMEOUT_S
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001 - manager treats as miss
            logger.warning("yfinance miss for %s: %s", symbol, exc)
            return None
        if not pts:
            return None
        return PriceSeries(
            symbol=symbol, points=pts, source=self.name,
            as_of=pts[-1].ts, asset_class=asset_class,
            meta={"resolved": self.ALIASES.get(symbol, symbol)},
        )


# ── Tier 2 (licensed): EODHD — Swedish funds (0P….ST), equities, ETFs ───
class EODHDProvider(BaseProvider):
    """Tier 2 (licensed) - EODHD End-of-Day API. Closes the Swedish mutual-fund
    gap yfinance cannot: EODHD lists Swedish open-end funds under Morningstar
    '0P….ST' codes (verified at eodhd.com/exchange/ST, May 2026), plus equities
    and ETFs. DORMANT until EODHD_API_KEY is set, so it changes no behaviour until
    the operator opts in (mirrors the news-chain provider pattern).

    API contract (eodhd.com/financial-apis):
        GET https://eodhd.com/api/eod/{SYMBOL}?api_token={KEY}&fmt=json&period=d&order=a
        -> [ {date, open, high, low, close, adjusted_close, volume}, ... ]
    Free tier: 20 calls/day, 1y depth - enough for a handful of scanner tickers."""
    name = "eodhd"
    handles = frozenset({"equity", "etf", "fund"})  # crypto stays on yfinance Tier 1
    BASE_URL: Final = "https://eodhd.com/api/eod"

    @staticmethod
    def _key() -> Optional[str]:
        # <- FIXED [Phase3-Step2]: read lazily so the key is picked up regardless of
        #    whether .env loaded before this singleton was constructed (import-order safe).
        import os
        return os.getenv("EODHD_API_KEY") or None

    def can_handle(self, asset_class: str) -> bool:
        # Dormant unless a key is present (council: no behaviour change until opted in).
        return bool(self._key()) and (not self.handles or asset_class in self.handles)

    async def fetch(self, symbol: str, asset_class: str, lookback_days: Optional[int] = None) -> Optional[PriceSeries]:
        api_key = self._key()
        if not api_key:
            return None
        url = f"{self.BASE_URL}/{symbol}"
        params = {"api_token": api_key, "fmt": "json", "period": "d", "order": "a"}
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=PROVIDER_TIMEOUT_S) as r:
                    if r.status != 200:
                        logger.warning("eodhd HTTP %s for %s", r.status, symbol)
                        return None
                    rows = await r.json(content_type=None)
        except Exception as exc:  # noqa: BLE001 - manager treats as miss
            logger.warning("eodhd miss for %s: %s", symbol, exc)
            return None
        if not isinstance(rows, list) or not rows:
            return None
        pts: list[DataPoint] = []
        for row in rows:
            try:
                ts = datetime.strptime(row["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                close = float(row["close"])
                # Open-end funds report a single daily NAV; map o=h=l=c when OHLC absent/zero.
                o = float(row.get("open") or close)
                hi = float(row.get("high") or close)
                lo = float(row.get("low") or close)
                if o <= EPS or hi <= EPS or lo <= EPS:
                    o = hi = lo = close
                pts.append(DataPoint(ts=ts, open=o, high=hi, low=lo, close=close))
            except (KeyError, TypeError, ValueError):
                continue
        if len(pts) < MIN_POINTS:
            return None
        return PriceSeries(
            symbol=symbol, points=pts, source=self.name,
            as_of=pts[-1].ts, asset_class=asset_class,
            meta={"provider": "eodhd"},
        )


# ── Tier 2: scraper for Swedish fund NAV (Morningstar SE / fondmarknaden) ──
class CustomScraperProvider(BaseProvider):
    """Tier 2 - Swedish mutual-fund NAV via a modular scraper.

    COMPLIANCE (council-mandated): respects robots.txt, rate-limits per host,
    and caches results. The operator MUST ensure their use complies with each
    target site's Terms of Service. This is scaffolding: `_scrape_nav` is the
    single seam to implement against a specific site's public NAV endpoint.

    Returns None (graceful miss) whenever robots disallows, the fetch fails, or
    the parse yields nothing - it never raises for a miss and never fabricates."""
    name = "morningstar-se"
    handles = frozenset({"fund"})

    def __init__(self, base_url: str = "https://www.morningstar.se") -> None:
        self.base_url = base_url
        self._last_hit: dict[str, float] = {}
        self._cache: dict[str, tuple[float, PriceSeries]] = {}
        self._robots_ok: dict[str, bool] = {}

    async def _robots_allows(self, host: str, path: str) -> bool:
        """Check robots.txt once per host (cached). Fail-closed on error."""
        if host in self._robots_ok:
            return self._robots_ok[host]
        try:
            import urllib.robotparser
            import aiohttp
            rp = urllib.robotparser.RobotFileParser()
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://{host}/robots.txt", timeout=10) as r:
                    txt = await r.text()
            rp.parse(txt.splitlines())
            ok = rp.can_fetch("SENTRIQ-Research", f"https://{host}{path}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("robots check failed for %s (fail-closed): %s", host, exc)
            ok = False
        self._robots_ok[host] = ok
        return ok

    async def _respect_rate_limit(self, host: str) -> None:
        now = time.monotonic()
        last = self._last_hit.get(host, 0.0)
        wait = SCRAPE_RATE_LIMIT_S - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_hit[host] = time.monotonic()

    async def _scrape_nav(self, symbol: str) -> Optional[list[DataPoint]]:
        """SEAM: implement against the target site's public NAV table.

        Scaffold uses BeautifulSoup on a public fund page. Returns a list of
        daily NAV DataPoints (o=h=l=c=NAV) or None. Kept deliberately defensive:
        any structural change on the source yields None, not a crash."""
        try:
            import aiohttp
            from bs4 import BeautifulSoup  # noqa: F401  (parse seam)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scraper deps missing (aiohttp/bs4): %s", exc)
            return None

        host = self.base_url.split("//", 1)[-1].split("/", 1)[0]
        path = f"/funds/{symbol}"
        if not await self._robots_allows(host, path):
            logger.info("robots.txt disallows scrape of %s%s - skipping", host, path)
            return None
        await self._respect_rate_limit(host)

        try:
            import aiohttp
            async with aiohttp.ClientSession(headers={"User-Agent": "SENTRIQ-Research/2.0"}) as s:
                async with s.get(f"{self.base_url}{path}", timeout=PROVIDER_TIMEOUT_S) as r:
                    if r.status != 200:
                        logger.info("scrape %s -> HTTP %s", path, r.status)
                        return None
                    _html = await r.text()
            # Parse seam: site-specific NAV-table extraction goes here.
            # Returning None until wired to a specific licensed source.
            logger.info("scrape parse-seam not yet wired for %s", symbol)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("scrape failed for %s: %s", symbol, exc)
            return None

    async def fetch(self, symbol: str, asset_class: str, lookback_days: Optional[int] = None) -> Optional[PriceSeries]:
        cached = self._cache.get(symbol)
        if cached and (time.monotonic() - cached[0]) < SCRAPE_CACHE_TTL_S:
            return cached[1]
        pts = await self._scrape_nav(symbol)
        if not pts or len(pts) < 1:
            return None
        series = PriceSeries(
            symbol=symbol, points=pts, source=self.name,
            as_of=pts[-1].ts, asset_class="fund", currency="SEK",
        )
        self._cache[symbol] = (time.monotonic(), series)
        return series


# ── Tier 3: Riksbank macro context (SEK rates / FX) ────────────────────────
class RiksbankProvider(BaseProvider):
    """Tier 3 - Swedish macro context from the Riksbank public API
    (riksbanken.se / Swea API). Not a per-stock price source; provides SEK-based
    economic series (policy rate, FX) that enrich Swedish-asset context. Returns
    None for instrument symbols it doesn't cover."""
    name = "riksbank"
    handles = frozenset({"macro"})

    SWEA_BASE: Final = "https://api.riksbank.se/swea/v1"

    async def fetch(self, symbol: str, asset_class: str, lookback_days: Optional[int] = None) -> Optional[PriceSeries]:
        if asset_class != "macro":
            return None
        try:
            import aiohttp
            url = f"{self.SWEA_BASE}/Observations/{symbol}/latest"
            async with aiohttp.ClientSession(headers={"User-Agent": "SENTRIQ-Research/2.0"}) as s:
                async with s.get(url, timeout=PROVIDER_TIMEOUT_S) as r:
                    if r.status != 200:
                        return None
                    data = await r.json()
            val = float(data.get("value")) if isinstance(data, dict) else None
            if val is None or not math.isfinite(val):
                return None
            ts = datetime.now(timezone.utc)
            pt = DataPoint(ts=ts, open=val, high=val, low=val, close=val)
            return PriceSeries(symbol=symbol, points=[pt], source=self.name,
                               as_of=ts, asset_class="macro", currency="SEK")
        except Exception as exc:  # noqa: BLE001
            logger.warning("riksbank miss for %s: %s", symbol, exc)
            return None


# ── ProviderManager: the cascade ───────────────────────────────────────────
class ProviderManager:
    """Iterates registered providers in priority order until one returns a
    FINITE, FRESH series. Applies NaN-guard + staleness-guard normalization.
    Raises DataMissingException (logged) only after all eligible providers miss."""

    def __init__(self, providers: Optional[list[BaseProvider]] = None) -> None:
        self._providers: list[BaseProvider] = list(providers or [])

    def register(self, provider: BaseProvider) -> None:
        self._providers.append(provider)

    @staticmethod
    def _normalize(series: PriceSeries) -> Optional[PriceSeries]:
        """Drop non-finite points; reject if too few remain or series is stale."""
        clean = [p for p in series.points if p.is_finite() and p.close > EPS]
        if len(clean) < MIN_POINTS and series.asset_class != "macro":
            return None
        series.points = clean
        series.as_of = clean[-1].ts if clean else series.as_of
        # Staleness-guard (council-mandated): numeric-but-stale is still a miss.
        if series.asset_class != "macro" and series.staleness_days > MAX_STALENESS_DAYS:
            logger.info("rejecting stale series %s from %s (%.1f days old)",
                        series.symbol, series.source, series.staleness_days)
            return None
        return series

    async def get(self, symbol: str, asset_class: str = "equity", lookback_days: Optional[int] = None) -> PriceSeries:
        tried: list[str] = []
        for provider in self._providers:
            if not provider.can_handle(asset_class):
                continue
            tried.append(provider.name)
            try:
                raw = await provider.fetch(symbol, asset_class, lookback_days)
            except Exception as exc:  # noqa: BLE001 - never let a provider crash the cascade
                logger.warning("provider %s raised for %s: %s", provider.name, symbol, exc)
                continue
            if raw is None:
                continue
            norm = self._normalize(raw)
            if norm is not None:
                logger.info("resolved %s via %s (as_of %s, %d pts)",
                            symbol, norm.source, norm.as_of.date(), len(norm.points))
                return norm
        logger.error("DataMissing: %s (tried %s)", symbol, tried)
        raise DataMissingException(symbol, tried)


# ── Facade ───────────────────────────────────────────────────────────────--
class DataIngestionService:
    """Top-level entry point. Wires the default tiered cascade and exposes a
    single async `get_series`. Callers catch DataMissingException to render an
    honest, provenance-stamped empty state - never a fabricated number."""

    def __init__(self, manager: Optional[ProviderManager] = None) -> None:
        self.manager = manager or ProviderManager([
            YahooFinanceProvider(),     # Tier 1 (free: equities/ETFs/US funds/crypto)
            EODHDProvider(),            # Tier 2 (licensed: Swedish funds 0P….ST + eq/etf) - dormant w/o EODHD_API_KEY
            CustomScraperProvider(),    # Tier 3 (funds: scrape fallback)
            RiksbankProvider(),         # Tier 4 (macro)
        ])

    async def get_series(self, symbol: str, asset_class: str = "equity",
                         lookback_days: Optional[int] = None) -> PriceSeries:
        return await self.manager.get(symbol, asset_class, lookback_days)

    async def get_many(self, symbols: list[tuple[str, str]]) -> dict[str, Optional[PriceSeries]]:
        """Fetch many (symbol, asset_class) pairs concurrently. Missing -> None."""
        async def _one(sym: str, ac: str) -> tuple[str, Optional[PriceSeries]]:
            try:
                return sym, await self.get_series(sym, ac)
            except DataMissingException:
                return sym, None
        results = await asyncio.gather(*(_one(s, a) for s, a in symbols))
        return dict(results)


# Module-level singleton for convenient import.
service = DataIngestionService()
