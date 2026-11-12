"""Offline tests: no network, no real API keys."""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetch_sentiment as fs  # noqa: E402

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "public" / "data" / "daily_sentiment.json"


def ticker(**overrides):
    base = {
        "rank": 1,
        "ticker": "NVDA",
        "company_name": "NVIDIA Corp.",
        "mentions_estimate": 100,
        "sentiment": "bullish",
        "bullish_pct": 70,
        "price_change_pct": "+3.4%",
        "reason": "Retail is buying the dip into earnings.",
        "source_subreddit": "r/wallstreetbets",
    }
    base.update(overrides)
    return base


def report_payload(count=6):
    symbols = ["NVDA", "TSLA", "AMD", "AAPL", "PLTR", "HOOD", "MSFT"]
    return {
        "market_mood": {"bullish_pct": 60, "bearish_pct": 30, "headline": "Retail buys the dip"},
        "top_tickers": [
            ticker(ticker=symbols[i], mentions_estimate=1000 - i * 10) for i in range(count)
        ],
    }


# --- the committed sample file must always satisfy the strict schema -------- #

def test_sample_json_is_valid():
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    report = fs.DailyReport.model_validate(data)
    assert report.is_sample is True
    assert 5 <= len(report.top_tickers) <= 10


# --- secret redaction -------------------------------------------------------- #

def test_redact_masks_env_secrets(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "s3cr3t-serp-key-123456")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFAKEFAKEFAKEFAKEFAKE12345")
    text = "failed: https://serpapi.com/search?api_key=s3cr3t-serp-key-123456&q=x using AIzaSyFAKEFAKEFAKEFAKEFAKE12345"
    out = fs.redact(text)
    assert "s3cr3t-serp-key-123456" not in out
    assert "AIzaSyFAKEFAKEFAKEFAKEFAKE12345" not in out


def test_redact_masks_unknown_keys_by_pattern():
    out = fs.redact("GET /search?api_key=abcdef0123456789abcdef0123456789abcdef01 failed")
    assert "abcdef0123456789abcdef0123456789abcdef01" not in out


# --- untrusted text -------------------------------------------------------- #

def test_clean_text_strips_markup_and_controls():
    assert fs.clean_text("<script>alert(1)</script>\x00 hi‮ there", 100) == "scriptalert(1)/script hi there"


def test_reddit_url_filter():
    assert fs.reddit_url_or_empty("https://www.reddit.com/r/stocks/x")
    assert fs.reddit_url_or_empty("https://evil.example/reddit.com") == ""
    assert fs.reddit_url_or_empty("javascript:alert(1)") == ""


# --- schema validation --------------------------------------------------------- #

def test_valid_report_is_sorted_and_ranked():
    payload = report_payload()
    payload["top_tickers"].reverse()
    report = fs.GeminiReport.model_validate(payload)
    assert [t.rank for t in report.top_tickers] == list(range(1, 7))
    mentions = [t.mentions_estimate for t in report.top_tickers]
    assert mentions == sorted(mentions, reverse=True)


@pytest.mark.parametrize("bad", ["YOLO!!", "TOOLONGX", "nv da", "123", ""])
def test_invalid_tickers_are_rejected(bad):
    with pytest.raises(ValidationError):
        fs.TickerSentiment.model_validate(ticker(ticker=bad))


def test_sentiment_label_follows_percentage():
    assert fs.TickerSentiment.model_validate(ticker(sentiment="bearish", bullish_pct=80)).sentiment == "bullish"
    assert fs.TickerSentiment.model_validate(ticker(sentiment="bullish", bullish_pct=20)).sentiment == "bearish"
    assert fs.TickerSentiment.model_validate(ticker(sentiment="bullish", bullish_pct=50)).sentiment == "neutral"


def test_price_change_is_sanitised():
    assert fs.TickerSentiment.model_validate(ticker(price_change_pct="3.4%")).price_change_pct == "+3.4%"
    assert fs.TickerSentiment.model_validate(ticker(price_change_pct="-6.5%")).price_change_pct == "-6.5%"
    assert fs.TickerSentiment.model_validate(ticker(price_change_pct="<b>hax</b>")).price_change_pct is None
    assert fs.TickerSentiment.model_validate(ticker(price_change_pct=None)).price_change_pct is None


def test_market_mood_never_overflows():
    mood = fs.MarketMood(bullish_pct=90, bearish_pct=60, headline="Wild session on the desk")
    assert mood.bullish_pct + mood.bearish_pct <= 100


def test_too_few_or_duplicate_tickers_fail():
    payload = report_payload(count=4)
    with pytest.raises(ValidationError):
        fs.GeminiReport.model_validate(payload)
    dupes = report_payload(count=6)
    for t in dupes["top_tickers"]:
        t["ticker"] = "NVDA"
    with pytest.raises(ValidationError):
        fs.GeminiReport.model_validate(dupes)


def test_subreddit_normalised():
    assert fs.TickerSentiment.model_validate(ticker(source_subreddit="wallstreetbets")).source_subreddit == "r/wallstreetbets"
    assert fs.TickerSentiment.model_validate(ticker(source_subreddit="r/<evil>")).source_subreddit == "r/wallstreetbets"


# --- SerpAPI formatting & orchestration ------------------------------------- #

def test_market_extraction_signs_and_limits():
    response = {
        "markets": {
            "us": [
                {"name": "Dow Jones", "price": 100.5, "price_movement": {"percentage": 0.7, "movement": "Down"}},
                {"name": "Nasdaq", "price": 200.0, "price_movement": {"percentage": 1.2, "movement": "Up"}},
                {"name": "", "price_movement": {"percentage": 1.0, "movement": "Up"}},
            ]
        },
        "news_results": [{"snippet": "Stocks rally"}],
    }
    text, quotes = fs.extract_market(response)
    assert [(q.name, q.change_pct) for q in quotes] == [("Dow Jones", -0.7), ("Nasdaq", 1.2)]
    assert "Stocks rally" in text


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def search(self, params):
        self.calls.append(params)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run_fetch(monkeypatch, responses):
    client = FakeClient(responses)
    monkeypatch.setattr(fs.serpapi, "Client", lambda **_: client)
    return client, fs.fetch_serpapi_data("dummy-key")


def reddit_response():
    return {"organic_results": [{"title": "Daily Discussion", "snippet": "1 NVDA 4.2k", "link": "https://www.reddit.com/r/wsb/1"}]}


def test_exactly_four_searches_and_partial_failure_is_tolerated(monkeypatch):
    client, (raw, _) = run_fetch(
        monkeypatch,
        [reddit_response(), RuntimeError("boom api_key=abcdef0123456789abcdef0123456789abcdef01"), {}, {"markets": {}}],
    )
    assert len(client.calls) == 4
    assert "abcdef0123456789" not in raw
    assert "no data available" in raw
    assert client.calls[3] == {"engine": "google_finance_markets", "trend": "indexes"}


def test_no_reddit_data_aborts(monkeypatch):
    with pytest.raises(RuntimeError):
        run_fetch(monkeypatch, [{}, {}, {}, {"markets": {}}])


# --- atomic write ------------------------------------------------------------- #

def test_write_report_is_atomic_and_clean(tmp_path):
    report = fs.DailyReport(
        updated_at="2026-11-12T13:30:00Z",
        market_mood=fs.MarketMood(bullish_pct=60, bearish_pct=30, headline="Retail buys the dip"),
        top_tickers=fs.GeminiReport.model_validate(report_payload()).top_tickers,
    )
    target = tmp_path / "out" / "daily_sentiment.json"
    fs.write_report(report, target)
    assert json.loads(target.read_text(encoding="utf-8"))["top_tickers"][0]["ticker"] == "NVDA"
    assert [p.name for p in target.parent.iterdir()] == ["daily_sentiment.json"]


def test_main_without_keys_exits_cleanly(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(fs, "load_dotenv", lambda *_a, **_k: None)
    assert fs.main() == 2
