<p align="center">
  <img src="assets/banner.svg" alt="What Reddit Is Buying" width="100%">
</p>

<p align="center">
  <b>The stocks retail is piling into, ranked every trading day.</b><br>
  Mood-scored · Rank moves · Fresh before the US open
</p>

<p align="center">
  <a href="https://github.com/bernhardbrugger/what-reddit-is-buying/actions/workflows/daily_update.yml"><img alt="Daily update" src="https://github.com/bernhardbrugger/what-reddit-is-buying/actions/workflows/daily_update.yml/badge.svg"></a>
  <img alt="Updates every trading day" src="https://img.shields.io/badge/updates-every%20trading%20day-ffb000">
  <img alt="Bring your own model" src="https://img.shields.io/badge/models-Gemini%20%C2%B7%20Claude%20%C2%B7%20OpenAI%20%C2%B7%20more-00d26a">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-8794a0"></a>
</p>

---

## Today's board

<!-- RANKING:START -->
<img src="assets/board.svg?v=202611130705" alt="Reddit sentiment board: Retail Bears Feast on Tech Turmoil as Nvidia Shockwaves Ripple" width="100%">

<sub>Updated Friday, 13 Nov 2026 · 07:05 UTC</sub>

> **Dow Jones** 🔴 ▼ 0.36% · **S\&P 500** 🔴 ▼ 0.35% · **Nasdaq** 🔴 ▼ 0.39% · **Russell** 🔴 ▼ 1.66% · **VIX** 🟢 ▲ 6.92%

| # | Move | Ticker | Mentions | Mood | Day | Theme | Signal |
|--:|:-:|:--|--:|:--|--:|:--|:--|
| 1 | · | **NVDA**<br><sub>NVIDIA Corporation</sub> | 450 | 🔴 35% bull | – | 👀 Rumor | Retail is heavily divided as dip buyers fight fresh executive scandal panic. |
| 2 | · | **RKLB**<br><sub>Rocket Lab USA, Inc.</sub> | 198 | 🟢 75% bull | – | 🚀 Momentum | Retail bulls stack long positions in the dedicated daily forum. |
| 3 | · | **MSTR**<br><sub>MicroStrategy Incorporated</sub> | 23 | 🟢 65% bull | – | 🚀 Momentum | Dedicated holders maintain steady bullish positioning despite market noise. |
| 4 | · | **GME**<br><sub>GameStop Corp.</sub> | 12 | 🟢 60% bull | – | 👀 Rumor | Retail stays engaged as AI narrative speculative interest resurfaces. |
| 5 | · | **PARA**<br><sub>Paramount Global</sub> | 8 | 🟢 70% bull | – | 🔥 Squeeze | Speculators snap up cheap share blocks hunting a sharp rebound. |
| 6 | · | **TSLA**<br><sub>Tesla, Inc.</sub> | 5 | 🔴 45% bull | – | 💬 Chatter | Options gamblers flip contracts rapidly across shifting volatility. |
| 7 | · | **VRT**<br><sub>Vertiv Holdings Co.</sub> | 3 | ⚪ 50% bull | – | 🏭 Sector | After-hours interest builds as retail tracks broader AI infrastructure. |
| 8 | · | **INTC**<br><sub>Intel Corporation</sub> | 2 | 🔴 40% bull | – | 🌐 Macro | Retail monitors government involvement while remaining mostly hesitant. |
| 9 | · | **EBAY**<br><sub>eBay Inc.</sub> | 2 | ⚪ 50% bull | – | 💬 Chatter | Peripheral retail chatter touches on speculative acquisition ideas. |

<sub>Watching 12 communities: r/wallstreetbets · r/stocks · r/investing · r/ValueInvesting · r/StockMarket · r/options · r/Superstonk · r/RobinHood · r/smallstreetbets · r/StocksAndTrading · r/Daytrading · r/pennystocks</sub>
<!-- RANKING:END -->

---

## How it works

```mermaid
flowchart LR
    A([⏰ Every trading day<br/>13:30 UTC]) --> B[🔎 Scan the forums<br/>your communities]
    B --> C[🧠 Score the mood<br/>any model you choose]
    C --> D[🛡️ Validate and sanitize]
    D --> E[📊 Board and trend charts]
    E --> F[(📜 Git history<br/>is the archive)]
    classDef n fill:#0f1418,stroke:#ffb000,color:#ffffff;
    class A,B,C,D,E,F n;
```

Mentions, mood and rank moves update on their own. Every board is a commit, so the whole history of the radar lives in this repo.

## Make it yours

Everything is controlled from one file, [`config.toml`](config.toml):

```toml
[sources]
subreddits = ["wallstreetbets", "stocks", "investing", "options", "thetagang"]  # any public subreddit
extra_sites = ["stocktwits.com"]                                                # any forum site

[llm]
provider = "anthropic"          # gemini · anthropic · openai · openrouter · groq · mistral · deepseek · xai
model = "claude-sonnet-5-5"
```

| Setting | What it does |
| --- | --- |
| `sources.subreddits` | Communities on the radar. Add or remove any public subreddit |
| `sources.extra_sites` | Extra forum sites, one search each |
| `sources.keywords` | Words that signal trading activity |
| `sources.per_query` | Communities per search. Fewer means deeper results and more credits |
| `radar.top_n` | Tickers on the board (5 to 15) |
| `radar.language` | Language of the one-liners |
| `llm.provider`, `llm.model` | Which model scores the mood. Add `llm.fallback_model` for a backup |

The config is validated on every run. If it would need more searches than `sources.max_searches`, the run stops before it spends a single credit.

## Launch your own

1. Create a repo from this code and enable Actions.
2. Add two repository secrets: `SERPAPI_KEY` ([get one](https://serpapi.com/manage-api-key)) and `LLM_API_KEY` (the key of the provider you picked in `config.toml`).
   ```bash
   gh secret set SERPAPI_KEY
   gh secret set LLM_API_KEY
   ```
   For the default `gemini` provider, a secret named `GEMINI_API_KEY` works too.
3. Run **Actions → Daily Reddit Stock Radar → Run workflow** once. From then on it runs itself, Monday to Friday.

Searches per run: `ceil(communities / per_query)` plus extra sites, daily threads and market data. The default setup uses 4 SerpAPI credits per run.

## Built to be public

Keys live only in GitHub secrets and are masked everywhere. Nobody can feed anything in: the workflow has no inputs, forks never get the secrets, and everything scraped from the web is cleaned, validated and escaped before it is published. Details in [SECURITY.md](SECURITY.md).

<details>
<summary>Run it locally</summary>

```bash
pip install -r scraper/requirements-dev.txt
python -m pytest scraper/tests          # offline, no keys needed
cp .env.example .env                    # add your own keys, never commit this file
python scraper/fetch_sentiment.py       # rewrites the board, charts and history
```

</details>

<sub>Not financial advice. Rankings are automated estimates of public chatter and can be wrong.</sub>

## License

[MIT](LICENSE)
