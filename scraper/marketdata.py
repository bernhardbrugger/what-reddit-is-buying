"""Measured data: Reddit mention counts (ApeWisdom) and last-session price moves (Yahoo Finance).

Both are free, keyless public endpoints on fixed HTTPS hosts. Everything they return is
untrusted: shapes are checked, numbers are range-checked and names are cleaned. If a source
is unavailable the run degrades gracefully instead of failing.
"""

from __future__ import annotations

import html
import json
import time
import urllib.request
from urllib.parse import quote

from pydantic import BaseModel, ValidationError, field_validator

from config import Config
from models import TICKER_RE
from security import clean_text, describe_error, log

APEWISDOM_URL = "https://apewisdom.io/api/v1.0/filter/{filter}/page/1"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
USER_AGENT = "Mozilla/5.0 (compatible; what-reddit-is-buying)"  # generic on purpose
MAX_BYTES = 2_000_000
MIN_BASELINE = 10  # ignore growth figures built on a tiny 24h-ago base


class Candidate(BaseModel):
    ticker: str
    name: str
    mentions: int
    mentions_24h_ago: int | None = None

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not TICKER_RE.match(v):
            raise ValueError("invalid ticker")
        return v

    @property
    def change_pct(self) -> int | None:
        base = self.mentions_24h_ago
        if base is None or base < MIN_BASELINE:
            return None
        return round((self.mentions - base) * 100 / base)


def _get_json(url: str, timeout: float = 20) -> object:
    if not url.startswith("https://"):
        raise ValueError("only https endpoints are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("response too large")
    return json.loads(raw)


def parse_candidates(payload: object, cfg: Config) -> list[Candidate]:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("unexpected ApeWisdom response shape")
    excluded = set(cfg.data.exclude_tickers)
    out: list[Candidate] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            ticker = str(item.get("ticker", ""))
            name = clean_text(html.unescape(str(item.get("name") or ticker)), 60) or ticker
            before = item.get("mentions_24h_ago")
            candidate = Candidate(
                ticker=ticker,
                name=name,
                mentions=int(item["mentions"]),
                mentions_24h_ago=int(before) if isinstance(before, (int, float)) else None,
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            continue
        if candidate.ticker in excluded or not 0 <= candidate.mentions <= 10_000_000:
            continue
        if candidate.mentions >= cfg.data.min_mentions:
            out.append(candidate)
    out.sort(key=lambda c: c.mentions, reverse=True)
    return out[: cfg.radar.top_n]


def fetch_mentions(cfg: Config) -> list[Candidate]:
    """Measured mention counts, or an empty list if the source is unavailable."""
    if cfg.data.mentions != "apewisdom":
        return []
    try:
        candidates = parse_candidates(_get_json(APEWISDOM_URL.format(filter=cfg.data.apewisdom_filter)), cfg)
        log(f"[mentions] ApeWisdom ({cfg.data.apewisdom_filter}): {len(candidates)} tickers above {cfg.data.min_mentions} mentions")
        return candidates
    except Exception as exc:  # noqa: BLE001 - fall back to model estimates
        log(f"[mentions] ApeWisdom unavailable, using model estimates ({describe_error(exc)})")
        return []


def extract_price_change(payload: object) -> float | None:
    """Last-session percent change from a Yahoo chart response, or None."""
    try:
        result = payload["chart"]["result"][0]  # type: ignore[index]
        pct = result["meta"].get("regularMarketChangePercent")
        if not isinstance(pct, (int, float)):
            closes = [c for c in result["indicators"]["quote"][0]["close"] if isinstance(c, (int, float))]
            if len(closes) < 2 or closes[-2] == 0:
                return None
            pct = (closes[-1] / closes[-2] - 1) * 100
    except (KeyError, IndexError, TypeError):
        return None
    return float(pct) if -95 <= pct <= 900 else None


def fetch_price_changes(tickers: list[str], pause: float = 0.4) -> dict[str, str]:
    """ticker -> '+3.4%' for every ticker that could be priced. Gives up after 3 failures in a row."""
    out: dict[str, str] = {}
    failures = 0
    for ticker in tickers:
        if failures >= 3:
            log("[prices] too many failures, skipping the rest")
            break
        try:
            pct = extract_price_change(_get_json(YAHOO_URL.format(symbol=quote(ticker.replace(".", "-"))), timeout=15))
            if pct is None:
                raise ValueError("no price in response")
            out[ticker] = f"{pct:+.1f}%"
            failures = 0
        except Exception as exc:  # noqa: BLE001 - a missing price is fine
            failures += 1
            log(f"[prices] {ticker}: unavailable ({describe_error(exc)})")
        time.sleep(pause)
    log(f"[prices] Yahoo Finance: {len(out)}/{len(tickers)} priced")
    return out
