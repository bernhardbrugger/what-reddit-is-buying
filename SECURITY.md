# Security policy

## Design principles

This repository is public, so it is built to be safe by construction:

- **No secrets in the repo.** `SERPAPI_KEY` and `LLM_API_KEY` live only in GitHub Actions secrets. `.env` files are git-ignored, and every log line passes through a redaction filter that knows the key formats of all supported providers.
- **No input surface.** There is no website, form or backend. The only inputs to a run are the secrets and `config.toml`, which is committed code that only people with write access can change. The workflow has no `workflow_dispatch` inputs, and pull requests from forks never receive secrets.
- **Keys only go where they belong.** The provider's API host is fixed in code, never taken from the config, so a config change cannot redirect a key to another server. `LLM_API_KEY` is only ever sent to the provider selected in `config.toml`; the legacy `GEMINI_API_KEY` is only used with the `gemini` provider.
- **Keyless data sources stay boxed in.** Mention counts and prices come from fixed HTTPS hosts, never from config or scraped text. Responses are size-limited and shape-checked, numbers are range-checked, and nothing a source returns is trusted as text. If a source fails, the run degrades (estimates marked `~`, blank prices) instead of inventing values.
- **The model cannot publish claims.** Mention counts, prices and ranks are taken from measured data, not from the model. Its one-liners and headline are filtered: anything with names, digits, links, @mentions or news words (CEO, lawsuit, merger, ...) is replaced by a fixed house phrase.
- **Strict config.** `config.toml` is validated on every run (names, domains, model ids, search budget). Unknown or malformed settings stop the run before any credit is spent.
- **Untrusted data stays untrusted.** Forum text is sanitised and fenced in the model prompt, the model answer is re-validated against a strict schema (tickers, numbers and themes are checked, not trusted), and every value is escaped before it is written to `README.md` (no links, images, HTML or @mentions) or into the generated SVG charts (no scripts, no external references).
- **Least privilege CI.** The workflow starts with `permissions: {}` and only the update job can write contents. Actions are pinned to commit SHAs and kept current by Dependabot.
- **Fail closed.** Everything is rendered before anything is written. If a run fails, the previous board stays in place.

## Reporting a vulnerability

Please open a private report via **GitHub → Security → Report a vulnerability** on this repository. Do not open a public issue for security problems.

## If a key ever leaks

1. Revoke/rotate the key immediately in the SerpAPI or your model provider's dashboard.
2. Update the GitHub secret with the new value.
3. Treat the old key as burned even if you rewrite git history.
