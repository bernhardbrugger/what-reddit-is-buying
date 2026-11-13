"""Data models. Validation here is the last gate before anything is published."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from security import clean_text

TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z])?$")
PRICE_CHANGE_RE = re.compile(r"^[+-]?\d{1,3}(?:\.\d{1,2})?%$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Theme = Literal["earnings", "momentum", "dip_buy", "squeeze", "rumor", "product", "macro", "sector", "other"]


def _clamp_pct(value: int) -> int:
    return max(0, min(100, int(value)))


# --------------------------------------------------------------------------- #
# What the language model must return
# --------------------------------------------------------------------------- #


class TickerSentiment(BaseModel):
    rank: int = Field(description="Rank 1..N by discussion volume.")
    ticker: str = Field(description="Official stock ticker, e.g. NVDA, AAPL, AMD.")
    company_name: str = Field(description="Full company name.")
    mentions_estimate: int = Field(
        description="Mentions in the last 24h; use the exact number if a ticker table in the data provides it."
    )
    sentiment: Literal["bullish", "bearish", "neutral"]
    bullish_pct: int = Field(description="Share of bullish voices, 0-100.")
    price_change_pct: str | None = Field(
        description="Latest price change only if it appears in the data, e.g. '+3.4%' or '-6.5%', else null."
    )
    theme: Theme = Field(description="The dominant driver of retail interest.")
    take: str = Field(
        description="Punchy one-liner (max 80 characters) about retail positioning. No news facts, no names of people."
    )

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        v = v.strip().upper().lstrip("$")
        if not TICKER_RE.match(v):
            raise ValueError(f"invalid ticker {v!r}")
        return v

    @field_validator("company_name")
    @classmethod
    def _company(cls, v: str) -> str:
        v = clean_text(v, 60)
        if not v:
            raise ValueError("empty company name")
        return v

    @field_validator("take")
    @classmethod
    def _take(cls, v: str) -> str:
        v = clean_text(v, 110)
        if len(v) < 8:
            raise ValueError("take too short")
        return v

    @field_validator("mentions_estimate")
    @classmethod
    def _mentions(cls, v: int) -> int:
        return max(0, min(10_000_000, int(v)))

    @field_validator("bullish_pct")
    @classmethod
    def _bull(cls, v: int) -> int:
        return _clamp_pct(v)

    @field_validator("price_change_pct")
    @classmethod
    def _price(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().replace("−", "-")
        if not v or v.lower() in {"null", "n/a", "none"}:
            return None
        if v[0].isdigit():
            v = f"+{v}"
        return v if PRICE_CHANGE_RE.match(v) else None

    @model_validator(mode="after")
    def _derive_sentiment(self) -> "TickerSentiment":
        # Keep the badge consistent with the number it is based on.
        if self.bullish_pct >= 55:
            self.sentiment = "bullish"
        elif self.bullish_pct <= 45:
            self.sentiment = "bearish"
        else:
            self.sentiment = "neutral"
        return self


class MarketMood(BaseModel):
    bullish_pct: int = Field(description="Overall bullish share, 0-100.")
    bearish_pct: int = Field(description="Overall bearish share, 0-100.")
    headline: str = Field(description="Punchy newspaper-style headline (max 80 characters) on the retail mood.")

    @field_validator("headline")
    @classmethod
    def _headline(cls, v: str) -> str:
        v = clean_text(v, 120)
        if len(v) < 5:
            raise ValueError("headline too short")
        return v

    @model_validator(mode="after")
    def _normalise(self) -> "MarketMood":
        bull, bear = _clamp_pct(self.bullish_pct), _clamp_pct(self.bearish_pct)
        total = bull + bear
        if total > 100:  # scale down proportionally so the bar never overflows
            bull = round(bull * 100 / total)
            bear = 100 - bull
        self.bullish_pct, self.bearish_pct = bull, bear
        return self


class LLMReport(BaseModel):
    """The part of the report the language model is asked to produce."""

    market_mood: MarketMood
    top_tickers: list[TickerSentiment] = Field(description="The most discussed stocks, most discussed first.")

    @field_validator("top_tickers")
    @classmethod
    def _tickers(cls, v: list[TickerSentiment]) -> list[TickerSentiment]:
        seen: set[str] = set()
        unique = []
        for item in v:
            if item.ticker not in seen:
                seen.add(item.ticker)
                unique.append(item)
        if len(unique) < 5:
            raise ValueError(f"only {len(unique)} valid tickers returned (need at least 5)")
        unique.sort(key=lambda t: t.mentions_estimate, reverse=True)
        return rerank(unique[:15])

    def trimmed(self, top_n: int) -> "LLMReport":
        return LLMReport(market_mood=self.market_mood, top_tickers=rerank(self.top_tickers[:top_n]))


def rerank(items: list[TickerSentiment]) -> list[TickerSentiment]:
    for position, item in enumerate(items, start=1):
        item.rank = position
    return items


# --------------------------------------------------------------------------- #
# Published report and history
# --------------------------------------------------------------------------- #


class IndexQuote(BaseModel):
    name: str
    price: float | None = None
    change_pct: float

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = clean_text(v, 40)
        if not v:
            raise ValueError("empty index name")
        return v


class DailyReport(BaseModel):
    updated_at: str
    market_mood: MarketMood
    indexes: list[IndexQuote] = Field(default_factory=list)
    top_tickers: list[TickerSentiment]


class TickerSnap(BaseModel):
    ticker: str
    rank: int
    mentions: int
    bullish_pct: int

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        if not TICKER_RE.match(v):
            raise ValueError("invalid ticker")
        return v


class HistoryEntry(BaseModel):
    date: str
    bullish_pct: int
    bearish_pct: int
    headline: str
    top: list[TickerSnap]

    @field_validator("date")
    @classmethod
    def _date(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError("invalid date")
        return v


class History(BaseModel):
    entries: list[HistoryEntry] = Field(default_factory=list)
