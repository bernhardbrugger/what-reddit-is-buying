"""Secret-safe logging and untrusted-text handling."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

SECRET_ENV_VARS = ("SERPAPI_KEY", "LLM_API_KEY", "GEMINI_API_KEY")

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|key|token|authorization)=([^&\s\"']+)"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),  # OpenAI, Anthropic, DeepSeek, OpenRouter
    re.compile(r"\b(?:gsk|xai)[_-][A-Za-z0-9]{20,}"),  # Groq, xAI
    re.compile(r"\b[0-9a-f]{40,64}\b"),  # SerpAPI-style hex keys
)


def redact(text: object, extra_secrets: tuple[str, ...] = ()) -> str:
    """Return ``text`` with anything that looks like a credential masked."""
    out = str(text)
    env_values = [os.environ.get(name, "") for name in SECRET_ENV_VARS]
    for secret in (*env_values, *extra_secrets):
        if secret and len(secret) >= 8:
            out = out.replace(secret, "***")
    out = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}=***", out)
    for pattern in _SECRET_PATTERNS[1:]:
        out = pattern.sub("***", out)
    return out


def log(message: object) -> None:
    print(redact(message), flush=True)


def describe_error(exc: BaseException | None) -> str:
    return redact(f"{type(exc).__name__}: {exc}")[:300]


# --------------------------------------------------------------------------- #
# Untrusted text
# --------------------------------------------------------------------------- #

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")
_WHITESPACE = re.compile(r"\s+")
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!|~<>&@:$])")


def clean_text(value: object, limit: int) -> str:
    """Collapse whitespace, strip control/bidi characters and angle brackets."""
    if not isinstance(value, str):
        return ""
    text = _CONTROL_CHARS.sub("", value)
    text = text.replace("<", "").replace(">", "")
    return _WHITESPACE.sub(" ", text).strip()[:limit]


def reddit_url_or_empty(value: object) -> str:
    if not isinstance(value, str):
        return ""
    try:
        host = (urlparse(value).hostname or "").lower()
    except ValueError:
        return ""
    if host == "reddit.com" or host.endswith(".reddit.com"):
        return clean_text(value, 200)
    return ""


def md_escape(value: str) -> str:
    """Neutralise Markdown/HTML, links, images, @mentions and emoji codes in untrusted text."""
    return _MD_SPECIAL.sub(r"\\\1", value)
