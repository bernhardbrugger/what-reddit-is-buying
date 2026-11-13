"""Shared fixtures. Tests are offline: no network, no real API keys."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import DailyReport, IndexQuote, LLMReport, MarketMood  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYMBOLS = ["NVDA", "TSLA", "AMD", "AAPL", "PLTR", "HOOD", "MSFT", "SOFI"]


def ticker_payload(**overrides):
    base = {
        "rank": 1,
        "ticker": "NVDA",
        "company_name": "NVIDIA Corp.",
        "mentions_estimate": 100,
        "sentiment": "bullish",
        "bullish_pct": 70,
        "price_change_pct": "+3.4%",
        "theme": "momentum",
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
    def build(**first_ticker_overrides):
        scored = LLMReport.model_validate(report_payload())
        tickers = scored.top_tickers
        if first_ticker_overrides:
            from models import TickerSentiment

            tickers[0] = TickerSentiment.model_validate(ticker_payload(**first_ticker_overrides))
        return DailyReport(
            updated_at="2026-11-13T13:30:00Z",
            market_mood=MarketMood(bullish_pct=60, bearish_pct=30, headline="Retail buys the dip"),
            indexes=[IndexQuote(name="S&P 500", price=6100.0, change_pct=0.42)],
            top_tickers=tickers,
        )

    return build
