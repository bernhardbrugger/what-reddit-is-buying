"""Strictly validated radar configuration (config.toml)."""

from __future__ import annotations

import math
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import files
from models import TICKER_RE

ProviderName = Literal["gemini", "anthropic", "openai", "openrouter", "groq", "mistral", "deepseek", "xai"]

SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")
KEYWORD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ]{1,23}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,99}$")
LANGUAGE_RE = re.compile(r"^[A-Za-z][A-Za-z \-]{1,29}$")
FILTER_RE = re.compile(r"^[A-Za-z0-9_\-]{2,40}$")

# Google ignores words after roughly the 32nd; stay safely below that.
MAX_QUERY_TERMS = 30


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos in config.toml fail loudly


class Radar(_Strict):
    top_n: int = Field(default=10, ge=5, le=15)
    language: str = "English"

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        if not LANGUAGE_RE.match(v):
            raise ValueError("language must be a plain language name such as 'English'")
        return v


class Sources(_Strict):
    subreddits: list[str] = Field(min_length=1, max_length=40)
    keywords: list[str] = Field(default=["buying", "bought", "calls", "puts", "YOLO", "portfolio"], min_length=1, max_length=10)
    per_query: int = Field(default=6, ge=1, le=8)
    extra_sites: list[str] = Field(default_factory=list, max_length=4)
    daily_threads: bool = True
    market_data: bool = True
    max_searches: int = Field(default=6, ge=1, le=12)

    @field_validator("subreddits")
    @classmethod
    def _subreddits(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out = []
        for raw in values:
            name = raw.strip().removeprefix("r/")
            if not SUBREDDIT_RE.match(name):
                raise ValueError(f"invalid subreddit name {raw!r}")
            if name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
        return out

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, values: list[str]) -> list[str]:
        for word in values:
            if not KEYWORD_RE.match(word):
                raise ValueError(f"invalid keyword {word!r} (letters, digits and spaces only)")
        return values

    @field_validator("extra_sites")
    @classmethod
    def _sites(cls, values: list[str]) -> list[str]:
        for site in values:
            if not DOMAIN_RE.match(site) or site.endswith("reddit.com"):
                raise ValueError(f"invalid forum domain {site!r} (e.g. 'stocktwits.com')")
        return values


class Data(_Strict):
    mentions: Literal["apewisdom", "estimate"] = "apewisdom"
    apewisdom_filter: str = "all-stocks"
    prices: bool = True
    min_mentions: int = Field(default=20, ge=0, le=1000)
    exclude_tickers: list[str] = Field(
        default=["SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "TQQQ", "SQQQ", "SPXL", "SPXS", "UVXY", "VXX"], max_length=60
    )

    @field_validator("apewisdom_filter")
    @classmethod
    def _filter(cls, v: str) -> str:
        if not FILTER_RE.match(v):
            raise ValueError("apewisdom_filter must be a plain name such as 'all-stocks' or 'wallstreetbets'")
        return v

    @field_validator("exclude_tickers")
    @classmethod
    def _exclude(cls, values: list[str]) -> list[str]:
        for t in values:
            if not TICKER_RE.match(t):
                raise ValueError(f"invalid ticker {t!r}")
        return values


class Llm(_Strict):
    provider: ProviderName = "gemini"
    model: str = "gemini-3.6-flash"
    fallback_model: str | None = None

    @field_validator("model", "fallback_model")
    @classmethod
    def _model(cls, v: str | None) -> str | None:
        if v is not None and not MODEL_RE.match(v):
            raise ValueError(f"invalid model id {v!r}")
        return v


class Config(_Strict):
    radar: Radar = Field(default_factory=Radar)
    sources: Sources
    data: Data = Field(default_factory=Data)
    llm: Llm = Field(default_factory=Llm)

    @model_validator(mode="after")
    def _budget(self) -> "Config":
        src = self.sources
        group = min(src.per_query, len(src.subreddits))
        terms = (group * 2 - 1) + (len(src.keywords) * 2 - 1) + 1
        if terms > MAX_QUERY_TERMS:
            raise ValueError(
                f"each search would have {terms} query terms (limit {MAX_QUERY_TERMS}); "
                "lower sources.per_query or remove keywords"
            )
        planned = planned_searches(self)
        if planned > src.max_searches:
            raise ValueError(
                f"this config needs {planned} searches per run but sources.max_searches is "
                f"{src.max_searches}; raise the cap or scan fewer communities/sites"
            )
        return self


def planned_searches(cfg: Config) -> int:
    src = cfg.sources
    return (
        math.ceil(len(src.subreddits) / src.per_query)
        + len(src.extra_sites)
        + int(src.daily_threads)
        + int(src.market_data)
    )


def load_config(path: Path | None = None) -> Config:
    with open(path or files.CONFIG_PATH, "rb") as handle:
        return Config.model_validate(tomllib.load(handle))
