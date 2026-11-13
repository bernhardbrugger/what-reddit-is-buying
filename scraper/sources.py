"""Forum and market data collection through SerpAPI."""

from __future__ import annotations

import time
from typing import Any

import serpapi
from pydantic import ValidationError

from config import Config, planned_searches
from models import IndexQuote
from security import clean_text, describe_error, log, reddit_url_or_empty

MAX_RESULTS_PER_QUERY = 15
MAX_SNIPPET_CHARS = 400


def _keyword_clause(keywords: list[str]) -> str:
    return "(" + " OR ".join(f'"{k}"' for k in keywords) + ")"


def build_searches(cfg: Config) -> list[dict[str, Any]]:
    """Turn the config into the exact list of SerpAPI searches for this run."""
    src = cfg.sources
    keywords = _keyword_clause(src.keywords)
    searches: list[dict[str, Any]] = []

    groups = [src.subreddits[i : i + src.per_query] for i in range(0, len(src.subreddits), src.per_query)]
    for number, group in enumerate(groups, start=1):
        sites = " OR ".join(f"site:reddit.com/r/{name}" for name in group)
        searches.append(
            {
                "label": f"Reddit communities {number}/{len(groups)}",
                "kind": "forum",
                "params": {
                    "engine": "google_forums",
                    "q": f"{sites} {keywords}",
                    "period_unit": "d",
                    "period_value": 1,
                    "hl": "en",
                    "gl": "us",
                },
            }
        )

    for domain in src.extra_sites:
        searches.append(
            {
                "label": f"Forum {domain}",
                "kind": "forum",
                "params": {
                    "engine": "google_forums",
                    "q": f"site:{domain} {keywords}",
                    "period_unit": "d",
                    "period_value": 1,
                    "hl": "en",
                    "gl": "us",
                },
            }
        )

    if src.daily_threads:
        searches.append(
            {
                "label": "Reddit daily discussion threads",
                "kind": "forum",
                "params": {
                    "engine": "google",
                    "q": 'site:reddit.com ("What are your moves tomorrow" OR "Daily Discussion Thread" OR "Weekend Discussion")',
                    "tbs": "qdr:d",
                    "hl": "en",
                    "gl": "us",
                },
            }
        )

    if src.market_data:
        # Google Finance only accepts trend="indexes" these days.
        searches.append(
            {
                "label": "Market levels",
                "kind": "market",
                "params": {"engine": "google_finance_markets", "trend": "indexes"},
            }
        )

    assert len(searches) == planned_searches(cfg)
    return searches


def _as_dict(response: Any) -> dict[str, Any]:
    return response.as_dict() if hasattr(response, "as_dict") else dict(response)


def _search_with_retry(client: serpapi.Client, params: dict[str, Any]) -> dict[str, Any]:
    """One retry, and only for transient network failures (failed calls are not billed)."""
    try:
        return _as_dict(client.search(params))
    except (serpapi.HTTPConnectionError, serpapi.TimeoutError):
        time.sleep(3)
        return _as_dict(client.search(params))


def format_forum_block(label: str, response: dict[str, Any]) -> tuple[str, int]:
    lines = [f"=== {label} ==="]
    count = 0
    for result in (response.get("organic_results") or [])[:MAX_RESULTS_PER_QUERY]:
        if not isinstance(result, dict):
            continue
        title = clean_text(result.get("title"), 200)
        snippet = clean_text(result.get("snippet"), MAX_SNIPPET_CHARS)
        link = reddit_url_or_empty(result.get("link"))
        if not (title or snippet):
            continue
        count += 1
        lines.append(f"- {title} ({link}): {snippet}")
    return "\n".join(lines), count


def extract_market(response: dict[str, Any]) -> tuple[str, list[IndexQuote]]:
    lines = ["=== Market levels ==="]
    quotes: list[IndexQuote] = []
    markets = response.get("markets")
    if isinstance(markets, dict):
        for region in ("us", "futures", "europe", "asia"):
            for item in markets.get(region) or []:
                if not isinstance(item, dict):
                    continue
                movement = item.get("price_movement") or {}
                pct = movement.get("percentage")
                name = clean_text(item.get("name"), 40)
                if not name or not isinstance(pct, (int, float)):
                    continue
                pct = -abs(pct) if str(movement.get("movement", "")).lower() == "down" else abs(pct)
                price = item.get("price")
                price = float(price) if isinstance(price, (int, float)) else None
                lines.append(f"- [{region}] {name}: {price} ({pct:+.2f}%)")
                if region == "us" and len(quotes) < 8:
                    try:
                        quotes.append(IndexQuote(name=name, price=price, change_pct=round(pct, 2)))
                    except ValidationError:
                        continue
    for item in (response.get("news_results") or [])[:8]:
        if isinstance(item, dict):
            snippet = clean_text(item.get("snippet"), 200)
            if snippet:
                lines.append(f"- news: {snippet}")
    return "\n".join(lines), quotes


def fetch_serpapi_data(api_key: str, cfg: Config) -> tuple[str, list[IndexQuote]]:
    client = serpapi.Client(api_key=api_key, timeout=45)
    blocks: list[str] = []
    indexes: list[IndexQuote] = []
    forum_hits = 0

    for search in build_searches(cfg):
        label = search["label"]
        try:
            response = _search_with_retry(client, search["params"])
            if search["kind"] == "forum":
                block, hits = format_forum_block(label, response)
                forum_hits += hits
                log(f"[serpapi] {label}: {hits} usable results")
            else:
                block, indexes = extract_market(response)
                log(f"[serpapi] {label}: {len(indexes)} index quotes")
            blocks.append(block)
        except Exception as exc:  # noqa: BLE001 - one failing call must not abort the run
            log(f"[serpapi] {label}: FAILED ({describe_error(exc)})")
            blocks.append(f"=== {label} === (no data available)")

    if forum_hits == 0:
        raise RuntimeError("No forum results came back from SerpAPI; refusing to generate a report.")
    return "\n".join(blocks), indexes
