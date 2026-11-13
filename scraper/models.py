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
Stance = Literal["loading_calls", "buying_dip", "taking_profits", "capitulating", "rotating_in", "holding", "split"]


def _clamp_pct(value: int) -> int:
    return max(0, min(100, int(value)))


def _norm_ticker(v: str) -> str:
    v = v.strip().upper().lstrip("$")
    if not TICKER_RE.match(v):
        raise ValueError(f"invalid ticker {v!r}")
    return v


def sentiment_for(bullish_pct: int) -> str:
    return "bullish" if bullish_pct >= 55 else "bearish" if bullish_pct <= 45 else "neutral"


# --------------------------------------------------------------------------- #
# What the language model must return
# --------------------------------------------------------------------------- #


class LLMTicker(BaseModel):
    ticker: str = Field(description="Official stock ticker, e.g. NVDA, AAPL, AMD.")
    company_name: str = Field(description="Full company name.")
    mentions_estimate: int = Field(description="Mentions in the last 24h; copy the number from the data table if one is given.")
    bullish_pct: int = Field(description="Share of bullish voices, 0-100. Use 50 if the forum text says nothing.")
    theme: Theme = Field(description="The dominant driver of retail interest.")
    stance: Stance = Field(description="How retail is positioned right now.")
    take: str = Field(description="Punchy one-liner, max 70 characters, about retail positioning only. No names, no numbers, no news.")

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return _norm_ticker(v)

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
        return clean_text(v, 140)

    @field_validator("mentions_estimate")
    @classmethod
    def _mentions(cls, v: int) -> int:
        return max(0, min(10_000_000, int(v)))

    @field_validator("bullish_pct")
    @classmethod
    def _bull(cls, v: int) -> int:
        return _clamp_pct(v)


class MarketMood(BaseModel):
    bullish_pct: int = Field(description="Overall bullish share, 0-100.")
    bearish_pct: int = Field(description="Overall bearish share, 0-100.")
    headline: str = Field(description="Punchy headline in sentence case, max 70 characters, about the retail mood. No names, no numbers.")

    @field_validator("headline")
    @classmethod
    def _headline(cls, v: str) -> str:
        return clean_text(v, 140)

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
    top_tickers: list[LLMTicker] = Field(description="The scored stocks, most discussed first.")

    @field_validator("top_tickers")
    @classmethod
    def _tickers(cls, v: list[LLMTicker]) -> list[LLMTicker]:
        seen: set[str] = set()
        unique = []
        for item in v:
            if item.ticker not in seen:
                seen.add(item.ticker)
                unique.append(item)
        if len(unique) < 3:
            raise ValueError(f"only {len(unique)} valid tickers returned (need at least 3)")
        return unique[:20]


# --------------------------------------------------------------------------- #
# Published report and history
# --------------------------------------------------------------------------- #


class TickerSentiment(BaseModel):
    rank: int
    ticker: str
    company_name: str
    mentions: int
    mentions_change_pct: int | None = None  # vs. 24h ago; None when there is no reliable baseline
    verified: bool = True  # False = mention count is a model estimate, not measured
    signal: bool = True  # False = the forum text said nothing about this ticker (mood/theme/take are blank)
    bullish_pct: int
    sentiment: Literal["bullish", "bearish", "neutral"] = "neutral"
    price_change_pct: str | None = None
    theme: Theme
    take: str

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return _norm_ticker(v)

    @field_validator("price_change_pct")
    @classmethod
    def _price(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v if PRICE_CHANGE_RE.match(v) else None

    @model_validator(mode="after")
    def _derive(self) -> "TickerSentiment":
        self.bullish_pct = _clamp_pct(self.bullish_pct)
        self.sentiment = sentiment_for(self.bullish_pct)  # keep the badge consistent with the number
        return self


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
    mentions_source: Literal["apewisdom", "estimate"] = "estimate"
    prices_source: Literal["yahoo", "none"] = "none"
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
