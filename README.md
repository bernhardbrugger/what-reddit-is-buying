# What Reddit Is Buying

A trading-desk read on the stocks Reddit is buying, selling and arguing about, refreshed once every US trading day (Monday to Friday) and published as a static dark-mode website.

Once per run the pipeline:

1. pulls Reddit finance chatter and market levels through **SerpAPI** (exactly 4 searches),
2. lets **Google Gemini** turn the raw text into a strictly structured report (top tickers, mention counts, sentiment, one punchy "desk note" each),
3. validates everything again locally and commits `public/data/daily_sentiment.json`,
4. deploys the static site in `public/` to **GitHub Pages**.

There is no server, no database, no login and nothing a visitor can type into. The only moving part is a scheduled GitHub Action that you own.

```
GitHub Actions (cron, Mon-Fri 13:30 UTC)
   |  secrets: SERPAPI_KEY, GEMINI_API_KEY  (exist only inside the job)
   v
scraper/fetch_sentiment.py -> public/data/daily_sentiment.json -> GitHub Pages
```

## Project layout

| Path | Purpose |
| --- | --- |
| `scraper/fetch_sentiment.py` | Data fetch, AI analysis, validation, atomic write |
| `scraper/tests/` | Offline unit tests (no network, no keys) |
| `public/index.html`, `public/assets/` | The dashboard (plain HTML, CSS and JS, no CDN) |
| `public/data/daily_sentiment.json` | Output file; ships with clearly labelled **sample data** |
| `.github/workflows/daily_update.yml` | Scheduled update + deploy |
| `.github/workflows/pages.yml` | Deploys the site on changes to `public/` |
| `.github/workflows/ci.yml` | Runs the tests on pushes and pull requests |

## Setup (about five minutes)

1. **Create a public repository** from this code and push it to `main`.
2. **Get two API keys**
   - SerpAPI: <https://serpapi.com/manage-api-key>
   - Google Gemini: <https://aistudio.google.com/apikey>
3. **Store them as secrets**: *Settings → Secrets and variables → Actions → New repository secret*
   - `SERPAPI_KEY`
   - `GEMINI_API_KEY`

   Or from a terminal (the value is prompted for, so it never lands in your shell history):
   ```bash
   gh secret set SERPAPI_KEY
   gh secret set GEMINI_API_KEY
   ```
4. **Enable Pages**: *Settings → Pages → Build and deployment → Source: GitHub Actions*.
5. **Run it once**: *Actions → Daily Reddit Stock Radar → Run workflow*. From then on it runs by itself.

Until the first successful run the site shows a visible **SAMPLE DATA** banner.

## Keeping a public repo safe

The code is built so that nothing sensitive can leak or be abused. The remaining switches live in repository settings, so please turn them on:

- **Secret scanning + push protection**: *Settings → Code security*. Free for public repositories.
- **Fork pull request workflows**: *Settings → Actions → General → Fork pull request workflows*: require approval for all outside collaborators. Forks never receive your secrets, but this also saves compute.
- **Workflow permissions**: set the default `GITHUB_TOKEN` to *read repository contents* (every workflow here requests what it needs explicitly).
- **Spend/usage caps**: keep an eye on your SerpAPI plan and set a quota/budget in Google AI Studio.
- **Branch protection**: the bot pushes straight to `main`. If you require pull requests on `main`, add a ruleset bypass for GitHub Actions.

What the code already does for you:

| Risk | Mitigation |
| --- | --- |
| Keys committed to git | Keys only come from the environment; `.env*` is git-ignored; `.env.example` is blank |
| Keys printed in logs or in the AI prompt | Every log line passes through `redact()`; SDK error text is masked before use |
| Strangers triggering runs or injecting parameters | Only `schedule` and a button for collaborators; **no workflow inputs**; fork PRs get no secrets |
| Malicious Reddit text (prompt injection / XSS) | Text is cleaned and fenced in the prompt; output is schema-validated; the browser renders via `textContent` only |
| Third-party script compromise | No CDN scripts or web fonts; strict CSP (`script-src 'self'`) |
| Supply chain | Actions pinned to commit SHAs; dependencies pinned; Dependabot enabled |
| Bad run overwriting good data | Atomic write only after validation; failed runs keep yesterday's file |

See [SECURITY.md](SECURITY.md) for reporting and key-rotation steps.

## Running locally

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r scraper/requirements-dev.txt
python -m pytest scraper/tests  # offline tests

cp .env.example .env            # then add your own keys (never commit this file)
python scraper/fetch_sentiment.py

python -m http.server -d public 8000   # open http://localhost:8000
```

## Costs and limits

- Each run uses **4 SerpAPI credits**. With up to 23 weekdays per month that is at most 92 credits, plus any manual runs. Check this against your SerpAPI plan.
- One Gemini request per run, far below the free tier.

## Good to know

- **Schedule**: `13:30 UTC` is one hour before the US open during US standard time (winter) and exactly at the open during daylight saving time (summer). GitHub may start scheduled jobs a few minutes late. Move the cron line if you want it earlier in summer.
- **Models**: `gemini-2.5-flash` is deprecated (shutdown December 1, 2026), so the script uses `gemini-3.6-flash` and falls back to `gemini-3.5-flash-lite`. Change `GEMINI_MODELS` in `fetch_sentiment.py` when Google retires them.
- **Market tape**: Google Finance no longer offers a "most active" list through SerpAPI (`trend` only accepts `indexes`), so the tape shows index levels plus the day's top Reddit tickers.
- **Accuracy**: mention counts and sentiment are estimates derived from search snippets by an AI model. This is entertainment and research input, **not investment advice**.

## License

[MIT](LICENSE)
