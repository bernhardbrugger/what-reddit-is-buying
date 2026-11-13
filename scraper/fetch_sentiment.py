"""What Reddit Is Buying - daily radar run.

1. Reads config.toml (communities, sites, model).
2. Scans the forums and market levels through SerpAPI.
3. Scores the chatter with the configured language model (Gemini, Claude, OpenAI, ...).
4. Validates everything, then rewrites the board in README.md, the SVG graphics in assets/
   and the history in data/history.json.

Security notes
--------------
* API keys come from the environment only (GitHub Actions secrets in CI, an untracked
  ``.env`` file locally). Every printed line passes through ``redact()``.
* Everything scraped from the web is untrusted: cleaned, fenced in the prompt, validated
  against a strict schema, and escaped before it reaches Markdown or SVG.
* If anything fails, nothing is written and the script exits non-zero, so a bad run can
  never publish garbage.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import ValidationError

from config import load_config, planned_searches
from files import REPO_ROOT
from history import entry_from_report, load_history, previous_entry, rank_moves, save_history, with_entry
from llm import analyze, resolve_api_key
from marketdata import fetch_mentions, fetch_price_changes
from pipeline import build_report
from render import render_block, render_board_svg, render_trend_svg, update_readme, write_assets
from security import describe_error, log
from sources import fetch_serpapi_data


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # keep logging safe on non-UTF-8 consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv(REPO_ROOT / ".env")  # local development only; ignored by git

    try:
        cfg = load_config()
    except (OSError, ValueError, ValidationError) as exc:
        log(f"Invalid config.toml: {describe_error(exc)}")
        return 2

    serp_key = os.environ.get("SERPAPI_KEY", "").strip()
    llm_key = resolve_api_key(cfg.llm.provider)
    missing = []
    if not serp_key:
        missing.append("SERPAPI_KEY")
    if not llm_key:
        missing.append("LLM_API_KEY" + (" (or GEMINI_API_KEY)" if cfg.llm.provider == "gemini" else ""))
    if missing:  # fail before spending any credits
        log(f"Missing required environment variable(s): {', '.join(missing)}")
        return 2

    try:
        candidates = fetch_mentions(cfg)  # free, so it runs first and tells the forum search what to look for
        if 0 < len(candidates) < 5:
            log("[mentions] fewer than 5 measured tickers, falling back to model estimates")
            candidates = []

        log(f"Scanning {len(cfg.sources.subreddits)} communities (up to {planned_searches(cfg)} searches)...")
        raw_text, indexes = fetch_serpapi_data(serp_key, cfg, [c.ticker for c in candidates])

        log(f"Scoring with {cfg.llm.provider}...")
        scored = analyze(raw_text, cfg, llm_key, candidates)

        prices: dict[str, str] = {}
        if cfg.data.prices:
            wanted = [t.ticker for t in scored.top_tickers if not candidates or t.ticker in {c.ticker for c in candidates}]
            prices = fetch_price_changes(wanted[: cfg.radar.top_n])

        report = build_report(
            scored, candidates, prices, indexes, cfg,
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        history = load_history()
        moves = rank_moves(report, previous_entry(history, report.updated_at[:10]))
        history = with_entry(history, entry_from_report(report))

        # Render everything first, then write: a rendering error leaves all files untouched.
        board_svg = render_board_svg(report)
        trend_svg = render_trend_svg(history)
        block = render_block(report, moves, cfg.sources.subreddits, has_trend=trend_svg is not None)
        update_readme(block)  # also checks the README markers before the other files are touched
        write_assets(board_svg, trend_svg)
        save_history(history)
    except Exception as exc:  # noqa: BLE001 - report cleanly, keep the previous board
        log(f"Run failed, keeping the previous board: {describe_error(exc)}")
        return 1

    log("Done. Board, charts and history updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
