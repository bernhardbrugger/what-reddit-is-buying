import pytest
from conftest import REPO, report_payload
from pydantic import ValidationError

import config as cfgmod
import marketdata
import pipeline
import voice
from models import LLMReport
from marketdata import Candidate


def cfg(**data):
    return cfgmod.Config.model_validate(
        {"sources": {"subreddits": ["stocks", "options"]}, "data": data}
    )


# --- voice: nothing that looks like news or a name gets published --------------------- #

@pytest.mark.parametrize(
    "bad",
    [
        "Jensen Huang resignation rattles the crowd",   # proper nouns + blocked word
        "Retail panics after fresh executive scandal",  # news claim
        "Calls up 300% into the print",                 # digits
        "Buy NVDA now, see https://evil.example",       # link + advice
        "Traders follow @octocat into the move",        # mention
        "short",                                        # too short
        "x" * 90,                                       # too long
    ],
)
def test_unsafe_takes_are_replaced_by_house_phrases(bad):
    out = voice.safe_take(bad, "buying_dip", "NVDA", "2026-11-13")
    assert out in voice.PHRASES["buying_dip"]


def test_clean_take_is_kept_and_phrase_choice_is_deterministic():
    assert voice.safe_take("Dip buyers defending the gap hard.", "buying_dip", "NVDA", "d") == "Dip buyers defending the gap hard."
    first = voice.safe_take("Jensen is out", "split", "AMD", "2026-11-13")
    assert first == voice.safe_take("Jensen is out", "split", "AMD", "2026-11-13")


def test_headline_fallback_follows_the_mood():
    bad = "NVIDIA CEO Resigns, Markets Panic"
    assert voice.safe_headline(bad, 70, 20, {"NVDA"}, "d") in voice.HEADLINES["bullish"]
    assert voice.safe_headline(bad, 20, 70, {"NVDA"}, "d") in voice.HEADLINES["bearish"]
    assert voice.safe_headline(bad, 45, 45, {"NVDA"}, "d") in voice.HEADLINES["neutral"]
    ok = "Retail leans bearish on chips but keeps buying every dip"
    assert voice.safe_headline(ok, 40, 40, {"NVDA"}, "d") == ok


# --- data config ---------------------------------------------------------------------- #

def test_data_config_defaults_and_validation():
    shipped = cfgmod.load_config(REPO / "config.toml")
    assert shipped.data.mentions == "apewisdom" and "SPY" in shipped.data.exclude_tickers
    for bad in ({"apewisdom_filter": "../admin"}, {"exclude_tickers": ["not a ticker"]}, {"mentions": "scrape"}, {"min_mentions": -1}):
        with pytest.raises(ValidationError):
            cfg(**bad)


# --- measured mentions ---------------------------------------------------------------- #

def ape(**item):
    base = {"rank": 1, "ticker": "NVDA", "name": "NVIDIA", "mentions": 2483, "upvotes": 10, "rank_24h_ago": 1, "mentions_24h_ago": 2022}
    base.update(item)
    return base


def test_parse_candidates_filters_sorts_and_cleans():
    payload = {"results": [
        ape(ticker="SPY", name="SPDR S&amp;P 500", mentions=900),               # excluded ETF
        ape(ticker="AMD", name="AMD <b>x</b>", mentions=575, mentions_24h_ago=470),
        ape(ticker="LOW", name="Tiny", mentions=5),                              # below min_mentions
        ape(ticker="BAD!", name="Nope", mentions=500),                           # invalid ticker
        {"ticker": "ZZZ"},                                                        # missing fields
        "garbage",
        ape(),
    ]}
    out = marketdata.parse_candidates(payload, cfg())
    assert [c.ticker for c in out] == ["NVDA", "AMD"]
    assert out[1].name == "AMD bx/b"  # angle brackets stripped
    assert out[0].change_pct == 23    # (2483-2022)/2022
    with pytest.raises(ValueError):
        marketdata.parse_candidates({"nope": 1}, cfg())


def test_growth_needs_a_meaningful_baseline():
    assert Candidate(ticker="AMD", name="AMD", mentions=50, mentions_24h_ago=4).change_pct is None
    assert Candidate(ticker="AMD", name="AMD", mentions=50, mentions_24h_ago=None).change_pct is None
    assert Candidate(ticker="AMD", name="AMD", mentions=50, mentions_24h_ago=100).change_pct == -50


def test_fetch_mentions_degrades_gracefully(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(marketdata, "_get_json", boom)
    assert marketdata.fetch_mentions(cfg()) == []
    assert marketdata.fetch_mentions(cfg(mentions="estimate")) == []  # estimate mode never calls out


def test_only_https_endpoints_are_fetched():
    with pytest.raises(ValueError):
        marketdata._get_json("http://apewisdom.io/api")
    with pytest.raises(ValueError):
        marketdata._get_json("file:///etc/passwd")


# --- prices ------------------------------------------------------------------------------ #

def yahoo(meta=None, closes=None):
    return {"chart": {"result": [{"meta": meta or {}, "indicators": {"quote": [{"close": closes or []}]}}]}}


def test_price_change_extraction():
    assert marketdata.extract_price_change(yahoo({"regularMarketChangePercent": -4.34})) == -4.34
    assert marketdata.extract_price_change(yahoo(closes=[100.0, None, 103.0])) == pytest.approx(3.0)
    assert marketdata.extract_price_change(yahoo(closes=[100.0])) is None
    assert marketdata.extract_price_change(yahoo({"regularMarketChangePercent": 5000})) is None  # implausible
    assert marketdata.extract_price_change({"chart": None}) is None
    assert marketdata.extract_price_change("junk") is None


def test_fetch_price_changes_formats_and_gives_up_after_three_failures(monkeypatch):
    monkeypatch.setattr(marketdata.time, "sleep", lambda s: None)
    calls = []

    def fake(url, timeout=0):
        calls.append(url)
        if "NVDA" in url:
            return yahoo({"regularMarketChangePercent": -4.34})
        raise OSError("blocked")

    monkeypatch.setattr(marketdata, "_get_json", fake)
    out = marketdata.fetch_price_changes(["NVDA", "A", "B", "C", "D", "E"])
    assert out == {"NVDA": "-4.3%"}
    assert len(calls) == 4  # NVDA + three failures, then it stops hammering the endpoint


# --- merge -------------------------------------------------------------------------------- #

def scored(**first):
    payload = report_payload(count=6)
    payload["top_tickers"][0].update(first)
    return LLMReport.model_validate(payload)


def cands():
    return [
        Candidate(ticker="NVDA", name="NVIDIA", mentions=2483, mentions_24h_ago=2022),
        Candidate(ticker="TSLA", name="Tesla", mentions=900, mentions_24h_ago=1000),
        Candidate(ticker="AMD", name="AMD", mentions=575, mentions_24h_ago=470),
        Candidate(ticker="AAPL", name="Apple", mentions=300),
    ]


def test_measured_mode_uses_real_numbers_and_ignores_invented_tickers():
    payload = report_payload(count=6)
    payload["top_tickers"][5]["ticker"] = "FAKE"  # model invents a ticker that is not in the data
    payload["top_tickers"][0]["mentions_estimate"] = 99999  # and a wrong count
    report = pipeline.build_report(LLMReport.model_validate(payload), cands(), {"NVDA": "-2.1%"}, [], cfg(), "2026-11-13T13:30:00Z")
    assert [t.ticker for t in report.top_tickers] == ["NVDA", "TSLA", "AMD", "AAPL"]
    first = report.top_tickers[0]
    assert first.mentions == 2483 and first.mentions_change_pct == 23 and first.verified is True
    assert first.company_name == "NVIDIA" and first.price_change_pct == "-2.1%"
    assert report.top_tickers[1].price_change_pct is None  # no price -> blank, never invented
    assert report.mentions_source == "apewisdom" and report.prices_source == "yahoo"
    assert [t.rank for t in report.top_tickers] == [1, 2, 3, 4]


def test_unsafe_model_text_is_replaced_before_publishing():
    bad = scored(take="Jensen Huang resigned, panic selling", stance="capitulating")
    bad.market_mood.headline = "NVIDIA CEO resigns, markets panic"
    report = pipeline.build_report(bad, cands(), {}, [], cfg(), "2026-11-13T13:30:00Z")
    assert report.top_tickers[0].take in voice.PHRASES["capitulating"]
    assert report.market_mood.headline in sum(voice.HEADLINES.values(), ())


def test_estimate_mode_marks_unverified_and_applies_the_minimum():
    payload = report_payload(count=8)
    payload["top_tickers"][7]["mentions_estimate"] = 3  # below min_mentions (20)
    report = pipeline.build_report(LLMReport.model_validate(payload), [], {}, [], cfg(), "2026-11-13T13:30:00Z")
    assert len(report.top_tickers) == 7 and all(not t.verified for t in report.top_tickers)
    assert report.mentions_source == "estimate" and report.prices_source == "none"


def test_too_few_usable_tickers_aborts():
    with pytest.raises(RuntimeError):
        pipeline.build_report(scored(), cands()[:2], {}, [], cfg(), "2026-11-13T13:30:00Z")
    with pytest.raises(RuntimeError):
        pipeline.build_report(LLMReport.model_validate(report_payload(count=4)), [], {}, [], cfg(), "2026-11-13T13:30:00Z")


# --- no evidence -> no made-up mood --------------------------------------------------------- #

def test_tickers_without_forum_evidence_are_shown_without_a_mood():
    payload = report_payload(count=6)
    payload["top_tickers"][1].update(bullish_pct=50, theme="other", stance="holding", take="Retail stays calm and holds steady.")
    report = pipeline.build_report(LLMReport.model_validate(payload), cands(), {}, [], cfg(), "2026-11-13T13:30:00Z")
    nvda, tsla = report.top_tickers[0], report.top_tickers[1]
    assert nvda.signal is True and nvda.take
    assert tsla.signal is False and tsla.take == ""
    assert report.market_mood.bullish_pct > 0  # other rows still carry a real mood


def test_no_signal_anywhere_means_a_neutral_gauge_and_house_headline():
    payload = report_payload(count=6)
    for t in payload["top_tickers"]:
        t.update(bullish_pct=50, theme="other", stance="holding")
    payload["market_mood"] = {"bullish_pct": 80, "bearish_pct": 10, "headline": "Retail is on fire today folks"}
    report = pipeline.build_report(LLMReport.model_validate(payload), cands(), {}, [], cfg(), "2026-11-13T13:30:00Z")
    assert all(not t.signal for t in report.top_tickers)
    assert report.market_mood.bullish_pct == 0 and report.market_mood.bearish_pct == 0
    assert report.market_mood.headline in voice.HEADLINES["neutral"]
