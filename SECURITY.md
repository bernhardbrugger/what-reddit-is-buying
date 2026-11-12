# Security policy

## Design principles

This repository is public, so it is built to be safe by construction:

- **No secrets in the repo.** `SERPAPI_KEY` and `GEMINI_API_KEY` live only in GitHub Actions secrets. `.env` files are git-ignored.
- **No input surface.** The website is static: no forms, no text fields, no cookies, no backend, no third-party scripts or fonts. The only inputs to the pipeline are the two secrets and the hard-coded search queries.
- **Untrusted data stays untrusted.** Reddit/search text is sanitised and fenced in the AI prompt, the AI answer is re-validated against a strict schema, and the browser renders it with `textContent` only (no `innerHTML`).
- **Least privilege CI.** Workflows start with `permissions: {}`. Only the data-update job can write contents; only the deploy job can publish Pages; actions are pinned to commit SHAs.
- **Fail closed.** If a run fails, the previous JSON file stays in place.

## Reporting a vulnerability

Please open a private report via **GitHub → Security → Report a vulnerability** on this repository. Do not open a public issue for security problems.

## If a key ever leaks

1. Revoke/rotate the key immediately in the SerpAPI or Google AI Studio dashboard.
2. Update the GitHub secret with the new value.
3. Treat the old key as burned even if you rewrite git history.
