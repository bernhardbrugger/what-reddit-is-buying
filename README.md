# What Reddit Is Buying

Every US trading day, a GitHub Action reads what Reddit is buying, selling and arguing about and rewrites the ranking below. No website, no server, nothing to click. This page is the product.

<!-- RANKING:START -->
**Updated:** Thursday, 12 Nov 2026 · 14:57 UTC

### Jensen Huang Resignation Rattles Tech as Retail Catches Falling Knives

🟩🟩🟩🟩🟩🟩🟩🟩🟥🟥🟥🟥🟥🟥🟥🟥🟥🟥🟥🟥

🟩 **Bullish 42%** · ⬜ Neutral 0% · 🟥 **Bearish 58%**

> **Dow Jones** 🟢 ▲ 0.11% · **S\&P 500** 🔴 ▼ 0.23% · **Nasdaq** 🔴 ▼ 0.41% · **Russell** 🔴 ▼ 0.72% · **VIX** 🟢 ▲ 5.26%

| # | Ticker | Company | Mentions 24h | Reddit mood | Price |
|--:|:--|:--|--:|:--|--:|
| 1 | **NVDA** | Nvidia Corporation | 2,450 | 🔴 Bearish 38% | – |
| 2 | **LUNR** | Intuitive Machines, Inc. | 180 | 🟢 Bullish 65% | – |
| 3 | **MSTR** | MicroStrategy Incorporated | 140 | 🟢 Bullish 60% | – |
| 4 | **AMAT** | Applied Materials, Inc. | 95 | 🟢 Bullish 58% | – |
| 5 | **SMCI** | Super Micro Computer, Inc. | 85 | 🔴 Bearish 30% | – |
| 6 | **ONDS** | Ondas Holdings Inc. | 55 | ⚪ Neutral 50% | – |
| 7 | **TSHA** | Taysha Gene Therapies, Inc. | 40 | ⚪ Neutral 52% | – |
| 8 | **OTCM** | OTC Markets Group Inc. | 30 | ⚪ Neutral 50% | – |

#### Desk notes

- **NVDA** (r/wallstreetbets): Traders are scrambling as CEO Jensen Huang's sudden resignation triggers heavy selling alongside aggressive dip-buying.
- **LUNR** (r/IntuitiveMachines): Retail interest builds around the space exploration company following its Q3 earnings release.
- **MSTR** (r/MSTR): Daily discussion threads remain active as Bitcoin proxies continue drawing steady retail capital.
- **AMAT** (r/stocks): Retail portfolios are targeting semiconductor equipment makers as potential lower-risk plays amid tech volatility.
- **SMCI** (r/wallstreetbets): The stock is caught in a broader pre-market semiconductor selloff following Nvidia's executive turmoil.
- **ONDS** (r/stocks): Q3 earnings report triggers fresh chatter around the wireless network provider's operational outlook.
- **TSHA** (r/stocks): Q3 earnings announcement draws speculative biotech traders looking for clinical milestone updates.
- **OTCM** (r/stocks): Quarterly earnings release prompts quiet interest in the financial market operator's platform volumes.
<!-- RANKING:END -->

<sub>Not investment advice. This is an automated summary of public discussion, written by an AI model from search results. Mention counts and sentiment are estimates and can be wrong. Do your own research.</sub>

---

## How it works

`.github/workflows/daily_update.yml` runs Monday to Friday at 13:30 UTC (one hour before the US open in winter, at the open in summer) and:

1. pulls Reddit chatter and market levels through **SerpAPI** (exactly 4 searches),
2. has **Google Gemini** turn it into a structured ranking,
3. validates every field, rewrites the section between the `RANKING` markers in this file and commits it.

The commit history of `README.md` is the archive of past rankings.

## Setup

1. Add two repository secrets (*Settings → Secrets and variables → Actions*). The value is prompted for, so it never ends up in your shell history:
   ```bash
   gh secret set SERPAPI_KEY
   gh secret set GEMINI_API_KEY
   ```
   Keys: [SerpAPI](https://serpapi.com/manage-api-key) · [Google AI Studio](https://aistudio.google.com/apikey)
2. Start the first run: *Actions → Daily Reddit Stock Radar → Run workflow*. After that it runs by itself.

## Safe for a public repo

- Keys exist only as GitHub secrets, inside the job, masked in logs. `.env` is git-ignored.
- Nobody can feed anything in: only the schedule (and collaborators with write access) can start a run, and the workflow has no inputs. Pull requests from forks never get the secrets.
- Reddit text is treated as untrusted: cleaned, fenced in the AI prompt, validated against a strict schema and Markdown-escaped before it is written here.
- Workflows start with no permissions, actions are pinned to commit SHAs, and a failed run leaves the previous ranking untouched.

See [SECURITY.md](SECURITY.md).

## Local run and tests

```bash
pip install -r scraper/requirements-dev.txt
python -m pytest scraper/tests          # offline, no keys needed
cp .env.example .env                    # add your own keys, never commit this file
python scraper/fetch_sentiment.py       # rewrites the ranking in README.md
```

## Notes

- 4 SerpAPI credits per run: at most 92 per month with 23 weekdays, plus manual runs.
- `gemini-2.5-flash` is deprecated (shutdown December 1, 2026), so the script uses `gemini-3.6-flash` with a fallback to `gemini-3.5-flash-lite` (`GEMINI_MODELS` in `fetch_sentiment.py`).
- Google Finance no longer offers a "most active" list through SerpAPI, so the market line shows index levels.

## License

[MIT](LICENSE)
