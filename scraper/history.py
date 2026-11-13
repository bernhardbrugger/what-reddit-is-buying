"""Daily history: powers rank moves and the sentiment trend chart."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

import files
from files import atomic_write_text
from models import DailyReport, History, HistoryEntry, TickerSnap
from security import describe_error, log

KEEP_DAYS = 120


def load_history(path: Path | None = None) -> History:
    path = path or files.HISTORY_PATH
    if not path.exists():
        return History()
    try:
        return History.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError, OSError) as exc:
        log(f"[history] unreadable, starting a fresh one ({describe_error(exc)})")
        return History()


def entry_from_report(report: DailyReport) -> HistoryEntry:
    return HistoryEntry(
        date=report.updated_at[:10],
        bullish_pct=report.market_mood.bullish_pct,
        bearish_pct=report.market_mood.bearish_pct,
        headline=report.market_mood.headline,
        top=[
            TickerSnap(ticker=t.ticker, rank=t.rank, mentions=t.mentions, bullish_pct=t.bullish_pct)
            for t in report.top_tickers
        ],
    )


def previous_entry(history: History, today: str) -> HistoryEntry | None:
    older = [e for e in history.entries if e.date < today]
    return older[-1] if older else None


def rank_moves(report: DailyReport, previous: HistoryEntry | None) -> dict[str, int | str]:
    """ticker -> rank change (positive = climbed), 'new' for first appearance, '' without a baseline."""
    if previous is None:
        return {t.ticker: "" for t in report.top_tickers}
    before = {s.ticker: s.rank for s in previous.top}
    return {
        t.ticker: ("new" if t.ticker not in before else before[t.ticker] - t.rank)
        for t in report.top_tickers
    }


def with_entry(history: History, entry: HistoryEntry) -> History:
    """One entry per day (a re-run replaces it), oldest first, capped."""
    entries = [e for e in history.entries if e.date != entry.date] + [entry]
    entries.sort(key=lambda e: e.date)
    return History(entries=entries[-KEEP_DAYS:])


def save_history(history: History, path: Path | None = None) -> None:
    path = path or files.HISTORY_PATH
    payload = json.dumps(history.model_dump(), ensure_ascii=False, indent=1) + "\n"
    atomic_write_text(path, payload)
