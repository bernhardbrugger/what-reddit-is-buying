import pytest
from conftest import report_payload, ticker_payload
from pydantic import ValidationError

import models
import security


# --- secret redaction --------------------------------------------------------- #

def test_redact_masks_env_secrets(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "s3cr3t-serp-key-123456")
    monkeypatch.setenv("LLM_API_KEY", "llm-key-abcdefghijkl-999")
    text = "failed https://serpapi.com/search?api_key=s3cr3t-serp-key-123456 with llm-key-abcdefghijkl-999"
    out = security.redact(text)
    assert "s3cr3t-serp-key-123456" not in out and "llm-key-abcdefghijkl-999" not in out


@pytest.mark.parametrize(
    "secret",
    [
        "AIzaSyFAKEFAKEFAKEFAKEFAKE12345",
        "sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKE",
        "sk-proj-FAKEFAKEFAKEFAKEFAKE1234",
        "gsk_FAKEFAKEFAKEFAKEFAKEFAKE12",
        "xai-FAKEFAKEFAKEFAKEFAKEFAKE12",
        "abcdef0123456789abcdef0123456789abcdef01",
    ],
)
def test_redact_masks_provider_key_shapes(secret):
    assert secret not in security.redact(f"error talking to host with {secret} rejected")


def test_clean_text_strips_markup_and_controls():
    assert security.clean_text("<script>alert(1)</script>\x00 hi‮ there", 100) == "scriptalert(1)/script hi there"


def test_reddit_url_filter():
    assert security.reddit_url_or_empty("https://www.reddit.com/r/stocks/x")
    assert security.reddit_url_or_empty("https://evil.example/reddit.com") == ""
    assert security.reddit_url_or_empty("javascript:alert(1)") == ""


def test_md_escape_blocks_links_images_mentions():
    out = security.md_escape("![x](https://e.example) [a](b) @octocat `c` | #1 :smile:")
    for bad in ("![", "](", " @", "`c`", " | ", ":smile:"):
        assert bad not in out.replace("\\" + bad[-1:], "")  # every special char is backslash-escaped


# --- schema validation --------------------------------------------------------- #

def test_valid_report_is_sorted_and_ranked():
    payload = report_payload()
    payload["top_tickers"].reverse()
    report = models.LLMReport.model_validate(payload)
    assert [t.rank for t in report.top_tickers] == list(range(1, 7))
    mentions = [t.mentions_estimate for t in report.top_tickers]
    assert mentions == sorted(mentions, reverse=True)


def test_trimmed_keeps_top_n():
    report = models.LLMReport.model_validate(report_payload(count=8)).trimmed(5)
    assert len(report.top_tickers) == 5 and report.top_tickers[0].rank == 1


@pytest.mark.parametrize("bad", ["YOLO!!", "TOOLONGX", "nv da", "123", ""])
def test_invalid_tickers_are_rejected(bad):
    with pytest.raises(ValidationError):
        models.TickerSentiment.model_validate(ticker_payload(ticker=bad))


def test_unknown_theme_is_rejected():
    with pytest.raises(ValidationError):
        models.TickerSentiment.model_validate(ticker_payload(theme="<script>"))


def test_sentiment_label_follows_percentage():
    parse = models.TickerSentiment.model_validate
    assert parse(ticker_payload(sentiment="bearish", bullish_pct=80)).sentiment == "bullish"
    assert parse(ticker_payload(sentiment="bullish", bullish_pct=20)).sentiment == "bearish"
    assert parse(ticker_payload(sentiment="bullish", bullish_pct=50)).sentiment == "neutral"


def test_price_change_is_sanitised():
    parse = models.TickerSentiment.model_validate
    assert parse(ticker_payload(price_change_pct="3.4%")).price_change_pct == "+3.4%"
    assert parse(ticker_payload(price_change_pct="-6.5%")).price_change_pct == "-6.5%"
    assert parse(ticker_payload(price_change_pct="<b>hax</b>")).price_change_pct is None
    assert parse(ticker_payload(price_change_pct=None)).price_change_pct is None


def test_market_mood_never_overflows():
    mood = models.MarketMood(bullish_pct=90, bearish_pct=60, headline="Wild session on the desk")
    assert mood.bullish_pct + mood.bearish_pct <= 100


def test_too_few_or_duplicate_tickers_fail():
    with pytest.raises(ValidationError):
        models.LLMReport.model_validate(report_payload(count=4))
    dupes = report_payload(count=6)
    for t in dupes["top_tickers"]:
        t["ticker"] = "NVDA"
    with pytest.raises(ValidationError):
        models.LLMReport.model_validate(dupes)
