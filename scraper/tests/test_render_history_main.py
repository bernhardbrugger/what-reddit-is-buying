import json
import xml.etree.ElementTree as ET

import pytest
from conftest import REPO, report_payload

import files
import fetch_sentiment
import history as hist
import render
from models import History, HistoryEntry, TickerSnap


def entry(date, bull=50, bear=30, order=("NVDA", "TSLA", "AMD", "AAPL", "PLTR", "HOOD")):
    return HistoryEntry(
        date=date, bullish_pct=bull, bearish_pct=bear, headline="Headline here",
        top=[TickerSnap(ticker=t, rank=i + 1, mentions=100 - i, bullish_pct=60) for i, t in enumerate(order)],
    )


# --- history ---------------------------------------------------------------------- #

def test_rank_moves(make_report):
    report = make_report()  # NVDA TSLA AMD AAPL PLTR HOOD
    assert set(hist.rank_moves(report, None).values()) == {""}
    previous = entry("2026-11-12", order=("TSLA", "NVDA", "AAPL", "AMD", "PLTR", "MSFT"))
    moves = hist.rank_moves(report, previous)
    assert moves["NVDA"] == 1 and moves["TSLA"] == -1 and moves["AMD"] == 1
    assert moves["AAPL"] == -1 and moves["PLTR"] == 0 and moves["HOOD"] == "new"


def test_history_one_entry_per_day_sorted_and_capped():
    history = History(entries=[entry("2026-11-10"), entry("2026-11-12")])
    history = hist.with_entry(history, entry("2026-11-12", bull=99))
    assert [e.date for e in history.entries] == ["2026-11-10", "2026-11-12"]
    assert history.entries[-1].bullish_pct == 99
    big = History(entries=[entry(f"2026-{m:02d}-{d:02d}") for m in range(1, 8) for d in range(1, 29)])
    assert len(hist.with_entry(big, entry("2026-12-01")).entries) == hist.KEEP_DAYS


def test_corrupt_history_starts_fresh(tmp_path):
    bad = tmp_path / "history.json"
    bad.write_text("{not json", encoding="utf-8")
    assert hist.load_history(bad).entries == []
    assert hist.load_history(tmp_path / "missing.json").entries == []


# --- rendering ----------------------------------------------------------------------- #

def test_block_has_board_table_and_no_discussion_text(make_report):
    block = render.render_block(make_report(), {"NVDA": 2, "TSLA": "new"}, ["stocks", "options"], has_trend=True)
    assert "assets/board.svg?v=202611131330" in block and "assets/trend.svg" in block
    assert "| 1 | ▲2 | **NVDA**" in block and "🆕" in block
    assert "🔥 +55%" in block and "🔴▼ -12%" in block  # mention growth vs. 24h ago
    assert "Scanning 2 communities: r/stocks · r/options" in block
    assert "Mentions: ApeWisdom (measured)" in block and "Prices: last session, Yahoo Finance" in block
    assert "Desk notes" not in block and "r/wallstreetbets" not in block


def test_block_neutralises_markdown_injection(make_report):
    evil = "Click ![x](https://evil.example/p.png) [here](https://evil.example) @octocat | <img src=x> `code`"
    block = render.render_block(make_report(company_name=evil, take=evil + " padding"), {}, ["stocks"], False)
    for dangerous in ("![x](", "[here](", " @octocat", " <img src=x", "`code`"):
        assert dangerous not in block
    assert "\\<img src=x\\>" in block  # the HTML is shown as inert text, not interpreted
    row = next(line for line in block.splitlines() if line.startswith("| 1 |"))
    assert row.count("|") - row.count("\\|") == 9  # real column separators only


def test_estimates_are_marked_with_a_tilde(make_report):
    report = make_report(verified=False, mentions_change_pct=None)
    report.mentions_source = "estimate"
    report.prices_source = "none"
    block = render.render_block(report, {}, ["stocks"], False)
    assert "| ~1,000 |" in block and "Mentions: estimated (~)" in block and "Prices: n/a" in block
    assert ">~1,000<" in render.render_board_svg(report)


def test_svgs_are_well_formed_and_inert(make_report):
    evil = make_report(company_name="<script>alert(1)</script> & co", take="x" * 10)
    board = render.render_board_svg(evil)
    trend = render.render_trend_svg(History(entries=[entry("2026-11-11"), entry("2026-11-12", 70, 20)]))
    for svg in (board, trend, (REPO / "assets" / "banner.svg").read_text(encoding="utf-8")):
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg")
        lowered = svg.lower()
        assert "<script" not in lowered and "onload" not in lowered and "href" not in lowered and "javascript:" not in lowered


def test_trend_needs_two_days():
    assert render.render_trend_svg(History(entries=[entry("2026-11-12")])) is None
    assert render.render_trend_svg(History()) is None


def test_readme_replace_keeps_surroundings_and_fails_without_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"intro\n{render.RANKING_START}\nold\n{render.RANKING_END}\noutro\n", encoding="utf-8")
    render.update_readme("NEW BOARD", readme)
    text = readme.read_text(encoding="utf-8")
    assert text.startswith("intro\n") and text.endswith("outro\n") and "old" not in text and "NEW BOARD" in text
    assert [p.name for p in tmp_path.iterdir()] == ["README.md"]
    readme.write_text("no markers", encoding="utf-8")
    with pytest.raises(RuntimeError):
        render.update_readme("x", readme)
    assert readme.read_text(encoding="utf-8") == "no markers"


def test_repo_readme_has_markers_and_assets_exist():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert text.count(render.RANKING_START) == 1 and text.count(render.RANKING_END) == 1
    assert (REPO / "assets" / "banner.svg").exists()
    assert "this page is the product" not in text.lower() and "GitHub Action reads" not in text


# --- the full run, offline ------------------------------------------------------------- #

def test_main_without_keys_fails_before_any_network(monkeypatch):
    for name in ("SERPAPI_KEY", "LLM_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(fetch_sentiment, "load_dotenv", lambda *_a, **_k: None)

    def boom(*_a, **_k):
        raise AssertionError("network must not be touched without keys")

    monkeypatch.setattr(fetch_sentiment, "fetch_serpapi_data", boom)
    assert fetch_sentiment.main() == 2


def test_main_end_to_end_writes_board_assets_and_history(monkeypatch, tmp_path, make_report):
    readme = tmp_path / "README.md"
    readme.write_text(f"top\n{render.RANKING_START}\nplaceholder\n{render.RANKING_END}\nbottom\n", encoding="utf-8")
    monkeypatch.setattr(files, "README_PATH", readme)
    monkeypatch.setattr(files, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(files, "HISTORY_PATH", tmp_path / "data" / "history.json")
    hist.save_history(History(entries=[entry("2026-11-12")]))  # yesterday, so a trend and rank moves exist

    report = make_report()
    monkeypatch.setattr(fetch_sentiment, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("SERPAPI_KEY", "serp-key-value-1234")
    monkeypatch.setenv("LLM_API_KEY", "llm-key-value-12345")
    monkeypatch.setattr(fetch_sentiment, "fetch_serpapi_data", lambda key, cfg, tickers=None: ("raw", report.indexes))
    from marketdata import Candidate
    from models import LLMReport

    cands = [Candidate(ticker=t.ticker, name=t.company_name, mentions=t.mentions, mentions_24h_ago=500) for t in report.top_tickers]
    monkeypatch.setattr(fetch_sentiment, "fetch_mentions", lambda cfg: cands)
    monkeypatch.setattr(fetch_sentiment, "fetch_price_changes", lambda tickers: {t: "+1.0%" for t in tickers})
    scored = LLMReport.model_validate(report_payload(count=6))
    monkeypatch.setattr(fetch_sentiment, "analyze", lambda raw, cfg, key, candidates=None: scored)

    assert fetch_sentiment.main() == 0
    text = readme.read_text(encoding="utf-8")
    assert text.startswith("top\n") and text.endswith("bottom\n") and "placeholder" not in text
    assert "assets/trend.svg" in text and "**NVDA**" in text and "▲ 1.0%" in text
    assert (tmp_path / "assets" / "board.svg").exists() and (tmp_path / "assets" / "trend.svg").exists()
    saved = json.loads((tmp_path / "data" / "history.json").read_text(encoding="utf-8"))
    assert [e["date"] for e in saved["entries"]][-1] == report.updated_at[:10] or len(saved["entries"]) == 2
    for secret in ("serp-key-value-1234", "llm-key-value-12345"):
        assert secret not in text


def test_main_failure_leaves_everything_untouched(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    original = f"top\n{render.RANKING_START}\nkeep me\n{render.RANKING_END}\n"
    readme.write_text(original, encoding="utf-8")
    monkeypatch.setattr(files, "README_PATH", readme)
    monkeypatch.setattr(files, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(files, "HISTORY_PATH", tmp_path / "data" / "history.json")
    monkeypatch.setattr(fetch_sentiment, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("SERPAPI_KEY", "serp-key-value-1234")
    monkeypatch.setenv("LLM_API_KEY", "llm-key-value-12345")

    def fail(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(fetch_sentiment, "fetch_serpapi_data", fail)
    assert fetch_sentiment.main() == 1
    assert readme.read_text(encoding="utf-8") == original
    assert not (tmp_path / "assets").exists() and not (tmp_path / "data").exists()


def test_rows_without_signal_render_dashes_not_filler(make_report):
    report = make_report(signal=False, take="", bullish_pct=50)
    block = render.render_block(report, {}, ["stocks"], False)
    row = next(line for line in block.splitlines() if line.startswith("| 1 |"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[4] == "–" and cells[6] == "–" and cells[7] == "–"  # mood, theme, signal
    assert "no signal" in render.render_board_svg(report)
