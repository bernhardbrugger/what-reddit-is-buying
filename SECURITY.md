# Security policy

## Design principles

This repository is public, so it is built to be safe by construction:

- **No secrets in the repo.** `SERPAPI_KEY` and `GEMINI_API_KEY` live only in GitHub Actions secrets. `.env` files are git-ignored.
- **No input surface.** There is no website, form or backend. The only inputs to the pipeline are the two secrets and the hard-coded search queries. The workflow has no `workflow_dispatch` inputs.
- **Untrusted data stays untrusted.** Reddit/search text is sanitised and fenced in the AI prompt, the AI answer is re-validated against a strict schema, and every value is Markdown-escaped (no links, images, HTML or @mentions) before it is written to `README.md`.
- **Least privilege CI.** The workflow starts with `permissions: {}` and only the update job can write contents. Actions are pinned to commit SHAs.
- **Fail closed.** If a run fails, the previous ranking stays in place.

## Reporting a vulnerability

Please open a private report via **GitHub → Security → Report a vulnerability** on this repository. Do not open a public issue for security problems.

## If a key ever leaks

1. Revoke/rotate the key immediately in the SerpAPI or Google AI Studio dashboard.
2. Update the GitHub secret with the new value.
3. Treat the old key as burned even if you rewrite git history.
