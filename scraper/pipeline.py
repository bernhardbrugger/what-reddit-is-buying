"""Merges measured data (mentions, prices) with the model's mood scores into the published report."""

from __future__ import annotations

from config import Config
from marketdata import Candidate
from models import DailyReport, IndexQuote, LLMReport, TickerSentiment
from security import log
from voice import neutral_headline, safe_headline, safe_take

MIN_ESTIMATED_TICKERS = 5


def build_report(
    scored: LLMReport,
    candidates: list[Candidate],
    prices: dict[str, str],
    indexes: list[IndexQuote],
    cfg: Config,
    updated_at: str,
) -> DailyReport:
    seed = updated_at[:10]
    measured = bool(candidates)
    by_ticker = {c.ticker: c for c in candidates}

    rows: list[TickerSentiment] = []
    for item in scored.top_tickers:
        if measured:
            candidate = by_ticker.get(item.ticker)
            if candidate is None:
                log(f"[merge] ignoring {item.ticker}: not in the measured data")
                continue
            mentions, change, name = candidate.mentions, candidate.change_pct, candidate.name
        else:
            mentions, change, name = item.mentions_estimate, None, item.company_name
            if mentions < cfg.data.min_mentions:
                continue
        # The model's contract: no evidence in the forum text -> 50, theme "other". Show that honestly.
        has_signal = not (item.bullish_pct == 50 and item.theme == "other")
        rows.append(
            TickerSentiment(
                rank=0,
                ticker=item.ticker,
                company_name=name,
                mentions=mentions,
                mentions_change_pct=change,
                verified=measured,
                signal=has_signal,
                bullish_pct=item.bullish_pct,
                price_change_pct=prices.get(item.ticker),
                theme=item.theme,
                take=safe_take(item.take, item.stance, item.ticker, seed) if has_signal else "",
            )
        )

    minimum = 3 if measured else MIN_ESTIMATED_TICKERS
    if len(rows) < minimum:
        raise RuntimeError(f"only {len(rows)} usable tickers after merging (need at least {minimum})")

    rows.sort(key=lambda t: t.mentions, reverse=True)
    rows = rows[: cfg.radar.top_n]
    for position, row in enumerate(rows, start=1):
        row.rank = position

    mood = scored.market_mood
    if any(r.signal for r in rows):
        mood.headline = safe_headline(mood.headline, mood.bullish_pct, mood.bearish_pct, {r.ticker for r in rows}, seed)
    else:  # nothing to base a mood on: say so instead of passing off the model's guess
        mood.bullish_pct = mood.bearish_pct = 0
        mood.headline = neutral_headline(seed)

    return DailyReport(
        updated_at=updated_at,
        market_mood=mood,
        indexes=indexes,
        mentions_source="apewisdom" if measured else "estimate",
        prices_source="yahoo" if prices else "none",
        top_tickers=rows,
    )
