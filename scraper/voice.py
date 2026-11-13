"""The desk's voice, kept safe.

The language model writes one-liners and a headline, but nothing it says is published
unless it passes a strict filter. Anything that looks like a news claim, a name or a
number is replaced by a line from a fixed phrase bank. That keeps the tone punchy and
makes it impossible for a hallucinated "fact" to end up in the public README.
"""

from __future__ import annotations

import hashlib
import re

from models import Stance

PHRASES: dict[str, tuple[str, ...]] = {
    "loading_calls": ("Calls stacking up.", "Bulls loading calls.", "Call buyers on the offense."),
    "buying_dip": ("Dip buyers on duty.", "Every dip gets a bid.", "Retail buying the pullback."),
    "taking_profits": ("Bulls cashing in.", "Retail locking in gains.", "Profit-taking on the tape."),
    "capitulating": ("Retail heading for the exits.", "Bag holders folding.", "Conviction cracking."),
    "rotating_in": ("Fresh money rotating in.", "A new name catching a bid.", "Retail rotating into the move."),
    "holding": ("Diamond hands holding the line.", "Steady hands, steady bid.", "Retail not budging."),
    "split": ("Bulls and bears in a standoff.", "Retail split down the middle.", "Two camps, zero consensus."),
}
HEADLINES = {
    "bullish": ("Retail is leaning bullish", "Bulls have the retail floor", "Retail risk appetite is back"),
    "bearish": ("Retail is leaning bearish", "Bears have the retail floor", "Retail turns defensive"),
    "neutral": ("Retail is split down the middle", "No clear retail leader today", "Retail waits for a catalyst"),
}

# Words that signal a news claim or a named entity rather than crowd positioning.
BLOCKED = re.compile(
    r"\b(ceo|cfo|chairman|founder|executive|scandal|resign\w*|fired|lawsuit|sued|fraud|probe|investigat\w*|"
    r"bankrupt\w*|merger|acqui\w+|buyout|layoffs?|recall|downgrade\w*|upgrade\w*|indict\w*|arrest\w*|"
    r"hack\w*|breach|governance|government|congress|trump|biden|fed|sec|doj)\b",
    re.IGNORECASE,
)
URLISH = re.compile(r"https?://|www\.|@|#|\d")


def _pick(options: tuple[str, ...], seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return options[digest[0] % len(options)]


def is_clean_line(text: str, allowed_caps: set[str], min_len: int, max_len: int, *, sentence_case: bool = True) -> bool:
    if not (min_len <= len(text) <= max_len):
        return False
    if URLISH.search(text) or BLOCKED.search(text):
        return False
    if sentence_case:
        words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
        for word in words[1:]:
            if word[0].isupper() and word not in allowed_caps:
                return False  # a proper noun (person, company, product) - not allowed
    return True


def safe_take(take: str, stance: Stance, ticker: str, seed: str) -> str:
    if is_clean_line(take, {ticker, "I"}, 12, 72):
        return take
    return _pick(PHRASES[stance], f"{seed}:{ticker}")


def neutral_headline(seed: str) -> str:
    return _pick(HEADLINES["neutral"], seed)


def safe_headline(headline: str, bullish_pct: int, bearish_pct: int, tickers: set[str], seed: str) -> str:
    if is_clean_line(headline, tickers, 12, 80):
        return headline
    tone = "bullish" if bullish_pct >= bearish_pct + 15 else "bearish" if bearish_pct >= bullish_pct + 15 else "neutral"
    return _pick(HEADLINES[tone], seed)
