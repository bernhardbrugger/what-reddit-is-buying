"""Shared fixtures. Tests are offline: no network, no real API keys."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import DailyReport, IndexQuote, MarketMood, TickerSentiment  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYMBOLS = ["NVDA", "TSLA", "AMD", "AAPL", "PLTR", "HOOD", "MSFT", "SOFI"]


def ticker_payload(**overrides):
    """One item as the language model returns it."""
    base = {
        "ticker": "NVDA",
        "company_name": "NVIDIA Corp.",
        "mentions_estimate": 100,
        "bullish_pct": 70,
        "theme": "momentum",
        "stance": "loading_calls",
        "take": "Calls stacking into the print.",
    }
    base.update(overrides)
    return base


def report_payload(count=6):
    return {
        "market_mood": {"bullish_pct": 60, "bearish_pct": 30, "headline": "Retail buys the dip"},
        "top_tickers": [
            ticker_payload(ticker=SYMBOLS[i], mentions_estimate=1000 - i * 10) for i in range(count)
        ],
    }


@pytest.fixture
def make_report():
    """A published DailyReport with 6 rows. Overrides apply to the first row, unvalidated (worst case)."""

    def build(**first_row_overrides):
        rows = [
            TickerSentiment(
                rank=i + 1,
                ticker=SYMBOLS[i],
                company_name="NVIDIA Corp.",
                mentions=1000 - i * 10,
                mentions_change_pct={0: 55, 1: -12}.get(i),
                verified=True,
                bullish_pct=70,
                price_change_pct="+3.4%",
                theme="momentum",
                take="Calls stacking into the print.",
            )
            for i in range(6)
        ]
        if first_row_overrides:
            rows[0] = rows[0].model_copy(update=first_row_overrides)
        return DailyReport(
            updated_at="2026-11-13T13:30:00Z",
            market_mood=MarketMood(bullish_pct=60, bearish_pct=30, headline="Retail buys the dip"),
            indexes=[IndexQuote(name="S&P 500", price=6100.0, change_pct=0.42)],
            mentions_source="apewisdom",
            prices_source="yahoo",
            top_tickers=rows,
        )

    return build
