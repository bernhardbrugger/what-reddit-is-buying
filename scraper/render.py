"""Turns a validated report into the README board and its SVG graphics.

Every value that reaches Markdown or SVG is either validated (tickers, numbers, enums) or
escaped (free text), so scraped text can never inject links, images, HTML or scripts.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import files
from files import atomic_write_text
from models import DailyReport, History
from security import md_escape

RANKING_START = "<!-- RANKING:START -->"
RANKING_END = "<!-- RANKING:END -->"

BULL, BEAR, NEUTRAL, AMBER = "#00d26a", "#ff3b4e", "#8794a0", "#ffb000"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace"
SERIF = "'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, serif"

THEMES = {
    "earnings": ("📊", "Earnings"),
    "momentum": ("🚀", "Momentum"),
    "dip_buy": ("🛒", "Dip buy"),
    "squeeze": ("🔥", "Squeeze"),
    "rumor": ("👀", "Rumor"),
    "product": ("🧪", "Product"),
    "macro": ("🌐", "Macro"),
    "sector": ("🏭", "Sector"),
    "other": ("💬", "Chatter"),
}
SENTIMENT_COLOR = {"bullish": BULL, "bearish": BEAR, "neutral": NEUTRAL}


def _arrow(pct: float) -> str:
    return "🟢 ▲" if pct > 0 else "🔴 ▼" if pct < 0 else "⚪ ▬"


def _move_cell(move: int | str) -> str:
    if move == "":
        return "·"
    if move == "new":
        return "🆕"
    if move > 0:
        return f"▲{move}"
    if move < 0:
        return f"▼{abs(move)}"
    return "–"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------- #
# Markdown block
# --------------------------------------------------------------------------- #


def render_block(
    report: DailyReport,
    moves: dict[str, int | str],
    communities: list[str],
    has_trend: bool,
) -> str:
    updated = datetime.strptime(report.updated_at, "%Y-%m-%dT%H:%M:%SZ")
    version = updated.strftime("%Y%m%d%H%M")
    alt = html.escape(f"Reddit sentiment board: {report.market_mood.headline}", quote=True)

    lines = [
        f'<img src="assets/board.svg?v={version}" alt="{alt}" width="100%">',
        "",
        f"<sub>Updated {updated:%A, %d %b %Y} · {updated:%H:%M} UTC</sub>",
        "",
    ]

    if report.indexes:
        tape = " · ".join(
            f"**{md_escape(q.name)}** {_arrow(q.change_pct)} {abs(q.change_pct):.2f}%" for q in report.indexes
        )
        lines += [f"> {tape}", ""]

    lines += [
        "| # | Move | Ticker | Mentions | Mood | Day | Theme | Signal |",
        "|--:|:-:|:--|--:|:--|--:|:--|:--|",
    ]
    for t in report.top_tickers:
        badge = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}[t.sentiment]
        price = "–"
        if t.price_change_pct:
            value = float(t.price_change_pct.rstrip("%"))
            price = f"{_arrow(value)} {md_escape(t.price_change_pct.lstrip('+-'))}"
        emoji, theme = THEMES[t.theme]
        lines.append(
            f"| {t.rank} | {_move_cell(moves.get(t.ticker, ''))} "
            f"| **{t.ticker}**<br><sub>{md_escape(t.company_name)}</sub> "
            f"| {t.mentions_estimate:,} | {badge} {t.bullish_pct}% bull | {price} "
            f"| {emoji} {theme} | {md_escape(t.take)} |"
        )

    if has_trend:
        lines += [
            "",
            f'<img src="assets/trend.svg?v={version}" alt="Retail sentiment trend over the last sessions" width="100%">',
        ]

    watching = " · ".join(f"r/{md_escape(name)}" for name in communities)
    lines += ["", f"<sub>Watching {len(communities)} communities: {watching}</sub>"]
    return "\n".join(lines)


def update_readme(block: str, path: Path | None = None) -> None:
    """Replace the text between the RANKING markers, atomically."""
    path = path or files.README_PATH
    original = path.read_text(encoding="utf-8")
    start, end = original.find(RANKING_START), original.find(RANKING_END)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("RANKING:START / RANKING:END markers not found in README.md")
    updated = original[: start + len(RANKING_START)] + "\n" + block + "\n" + original[end:]
    atomic_write_text(path, updated)


# --------------------------------------------------------------------------- #
# SVG graphics
# --------------------------------------------------------------------------- #


def _t(x: float, y: float, text: str, size: int, fill: str, *, anchor: str = "start", weight: str = "400",
       family: str = MONO, spacing: str = "0", style: str = "normal") -> str:
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'font-style="{style}" letter-spacing="{spacing}" fill="{fill}" text-anchor="{anchor}">{xml_escape(text)}</text>'
    )


def render_board_svg(report: DailyReport) -> str:
    width, row_h, top = 960, 40, 186
    count = len(report.top_tickers)
    height = top + count * row_h + 46
    mood = report.market_mood
    neutral = 100 - mood.bullish_pct - mood.bearish_pct
    updated = datetime.strptime(report.updated_at, "%Y-%m-%dT%H:%M:%SZ")
    max_mentions = max((t.mentions_estimate for t in report.top_tickers), default=1) or 1

    gauge_w = 896
    bull_w = gauge_w * mood.bullish_pct / 100
    neutral_w = gauge_w * neutral / 100
    bear_w = gauge_w - bull_w - neutral_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="Reddit sentiment board">',
        f'<title>{xml_escape(_truncate(mood.headline, 120))}</title>',
        f'<defs><clipPath id="card"><rect width="{width}" height="{height}" rx="16"/></clipPath>'
        f'<linearGradient id="glow" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{AMBER}" stop-opacity="0.16"/>'
        f'<stop offset="1" stop-color="{AMBER}" stop-opacity="0"/></linearGradient></defs>',
        '<g clip-path="url(#card)">',
        f'<rect width="{width}" height="{height}" fill="#0b0f12"/>',
        f'<rect width="{width}" height="170" fill="url(#glow)"/>',
        f'<rect width="{width}" height="4" fill="{AMBER}"/>',
        _t(32, 44, "WHAT REDDIT IS BUYING", 13, AMBER, weight="700", spacing="4"),
        _t(928, 44, f"{updated:%a %d %b %Y} · {updated:%H:%M} UTC", 13, "#7d8b96", anchor="end"),
        _t(32, 90, _truncate(mood.headline, 68), 24, "#ffffff", weight="700", family=SERIF),
        f'<rect x="32" y="114" width="{bull_w:.1f}" height="16" fill="{BULL}"/>',
        f'<rect x="{32 + bull_w:.1f}" y="114" width="{neutral_w:.1f}" height="16" fill="#2b3640"/>',
        f'<rect x="{32 + bull_w + neutral_w:.1f}" y="114" width="{bear_w:.1f}" height="16" fill="{BEAR}"/>',
        _t(32, 156, f"BULLISH {mood.bullish_pct}%", 13, BULL, weight="700", spacing="2"),
        _t(480, 156, f"NEUTRAL {neutral}%", 13, NEUTRAL, anchor="middle", spacing="2"),
        _t(928, 156, f"BEARISH {mood.bearish_pct}%", 13, BEAR, anchor="end", weight="700", spacing="2"),
        f'<line x1="32" y1="{top - 6}" x2="928" y2="{top - 6}" stroke="#1e272e"/>',
    ]

    for i, t in enumerate(report.top_tickers):
        y = top + i * row_h
        base = y + 27
        color = SENTIMENT_COLOR[t.sentiment]
        bar_w = max(4.0, 400 * t.mentions_estimate / max_mentions)
        parts += [
            _t(32, base, f"{t.rank:02d}", 18, "#8a6100", weight="700"),
            _t(76, base, t.ticker, 20, "#ffffff", weight="700"),
            f'<rect x="176" y="{y + 11}" width="{bar_w:.1f}" height="16" rx="2" fill="{color}" fill-opacity="0.9"/>',
            _t(176 + bar_w + 10, base - 2, f"{t.mentions_estimate:,}", 13, "#aab6bf"),
            _t(700, base, f"{t.bullish_pct}% bull", 14, color, weight="700"),
        ]
        if t.price_change_pct:
            value = float(t.price_change_pct.rstrip("%"))
            glyph = "▲" if value > 0 else "▼" if value < 0 else "▬"
            parts.append(
                _t(928, base, f"{glyph} {t.price_change_pct.lstrip('+-')}", 14,
                   BULL if value > 0 else BEAR if value < 0 else NEUTRAL, anchor="end", weight="700")
            )
        else:
            parts.append(_t(928, base, "–", 14, "#5a6770", anchor="end"))
        if i < count - 1:
            parts.append(f'<line x1="32" y1="{y + row_h}" x2="928" y2="{y + row_h}" stroke="#141a1f"/>')

    parts += [
        _t(32, height - 18, "MENTIONS · MOOD · DAY MOVE", 11, "#5a6770", spacing="2"),
        _t(928, height - 18, "Automated estimate. Not financial advice.", 11, "#5a6770", anchor="end"),
        "</g></svg>",
    ]
    return "\n".join(parts) + "\n"


def render_trend_svg(history: History, max_points: int = 30) -> str | None:
    entries = history.entries[-max_points:]
    if len(entries) < 2:
        return None

    width, height = 960, 250
    left, right, top, bottom = 64, 928, 70, 196
    plot_w, plot_h = right - left, bottom - top

    def x_at(i: int) -> float:
        return left + plot_w * i / (len(entries) - 1)

    def y_at(pct: int) -> float:
        return bottom - plot_h * pct / 100

    def polyline(values: list[int], color: str) -> str:
        pts = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(values))
        dots = "".join(f'<circle cx="{x_at(i):.1f}" cy="{y_at(v):.1f}" r="3.5" fill="{color}"/>' for i, v in enumerate(values))
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>{dots}'

    bull = [e.bullish_pct for e in entries]
    bear = [e.bearish_pct for e in entries]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="Retail sentiment trend">',
        "<title>Retail sentiment trend</title>",
        f'<defs><clipPath id="card"><rect width="{width}" height="{height}" rx="16"/></clipPath></defs>',
        '<g clip-path="url(#card)">',
        f'<rect width="{width}" height="{height}" fill="#0b0f12"/>',
        f'<rect width="{width}" height="4" fill="{AMBER}"/>',
        _t(32, 44, f"RETAIL SENTIMENT · LAST {len(entries)} SESSIONS", 13, AMBER, weight="700", spacing="4"),
        _t(776, 44, "● BULLISH", 12, BULL, weight="700", spacing="2"),
        _t(928, 44, "● BEARISH", 12, BEAR, anchor="end", weight="700", spacing="2"),
    ]
    for pct in (0, 25, 50, 75, 100):
        y = y_at(pct)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#1e272e"/>')
        parts.append(_t(left - 10, y + 4, f"{pct}%", 11, "#5a6770", anchor="end"))
    parts += [polyline(bear, BEAR), polyline(bull, BULL)]
    parts += [
        _t(left, height - 22, entries[0].date, 11, "#7d8b96"),
        _t(right, height - 22, entries[-1].date, 11, "#7d8b96", anchor="end"),
        "</g></svg>",
    ]
    return "\n".join(parts) + "\n"


def write_assets(board_svg: str, trend_svg: str | None, assets_dir: Path | None = None) -> None:
    """Write board.svg (always) and trend.svg (once there are two days of history)."""
    assets_dir = assets_dir or files.ASSETS_DIR
    atomic_write_text(assets_dir / "board.svg", board_svg)
    if trend_svg is not None:
        atomic_write_text(assets_dir / "trend.svg", trend_svg)
