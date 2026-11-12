/* What Reddit Is Buying - renders public/data/daily_sentiment.json.
 *
 * Security model: the JSON is treated as untrusted. It is shape-checked and clamped here,
 * and rendered exclusively through textContent / DOM APIs. There is no innerHTML, no
 * user input and no outbound request other than the same-origin JSON file.
 */
(() => {
  'use strict';

  const DATA_URL = 'data/daily_sentiment.json';
  const STALE_AFTER_HOURS = 96;
  const TICKER_RE = /^[A-Z]{1,5}(?:[.-][A-Z])?$/;
  const SUBREDDIT_RE = /^r\/[A-Za-z0-9_]{2,21}$/;
  const SENTIMENTS = ['bullish', 'bearish', 'neutral'];
  const PRICE_RE = /^[+-]?\d{1,3}(?:\.\d{1,2})?%$/;

  const $ = (id) => document.getElementById(id);
  const numberFmt = new Intl.NumberFormat('en-US');

  /* ---------- tiny DOM helpers ---------- */

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
  const isNum = (n) => typeof n === 'number' && Number.isFinite(n);
  const cleanStr = (s, max) =>
    typeof s === 'string' ? s.replace(/[\u0000-\u001f\u007f<>]/g, '').trim().slice(0, max) : '';

  function direction(n) {
    if (n > 0) return 'up';
    if (n < 0) return 'down';
    return 'flat';
  }

  function arrow(n) {
    if (n > 0) return '▲';
    if (n < 0) return '▼';
    return '▬';
  }

  /* ---------- validation ---------- */

  function normalize(raw) {
    if (!raw || typeof raw !== 'object') throw new Error('bad payload');

    const updated = new Date(raw.updated_at);
    if (Number.isNaN(updated.getTime())) throw new Error('bad timestamp');

    const mood = raw.market_mood || {};
    const bull = clamp(Math.round(isNum(mood.bullish_pct) ? mood.bullish_pct : 0), 0, 100);
    const bear = clamp(Math.round(isNum(mood.bearish_pct) ? mood.bearish_pct : 0), 0, 100 - bull);

    const tickers = (Array.isArray(raw.top_tickers) ? raw.top_tickers : [])
      .map((t) => {
        if (!t || typeof t !== 'object') return null;
        const ticker = cleanStr(t.ticker, 8).toUpperCase();
        if (!TICKER_RE.test(ticker)) return null;
        const pct = clamp(Math.round(isNum(t.bullish_pct) ? t.bullish_pct : 50), 0, 100);
        const price = typeof t.price_change_pct === 'string' && PRICE_RE.test(t.price_change_pct)
          ? t.price_change_pct
          : null;
        const sub = typeof t.source_subreddit === 'string' && SUBREDDIT_RE.test(t.source_subreddit)
          ? t.source_subreddit
          : '';
        return {
          ticker,
          company: cleanStr(t.company_name, 60),
          mentions: clamp(Math.round(isNum(t.mentions_estimate) ? t.mentions_estimate : 0), 0, 1e7),
          sentiment: SENTIMENTS.includes(t.sentiment) ? t.sentiment : 'neutral',
          bullishPct: pct,
          price,
          reason: cleanStr(t.reason, 260),
          sub,
        };
      })
      .filter(Boolean)
      .slice(0, 10);

    const indexes = (Array.isArray(raw.indexes) ? raw.indexes : [])
      .map((i) => (i && isNum(i.change_pct) && cleanStr(i.name, 40)
        ? { name: cleanStr(i.name, 40), price: isNum(i.price) ? i.price : null, change: i.change_pct }
        : null))
      .filter(Boolean)
      .slice(0, 8);

    return {
      updated,
      isSample: raw.is_sample === true,
      headline: cleanStr(mood.headline, 140),
      bull,
      bear,
      neutral: 100 - bull - bear,
      tickers,
      indexes,
    };
  }

  /* ---------- rendering ---------- */

  function renderTape(data) {
    const track = $('tape-track');
    track.replaceChildren();

    const items = [];
    data.indexes.forEach((i) => {
      items.push({ sym: i.name.toUpperCase(), px: i.price === null ? '' : numberFmt.format(i.price), change: i.change, label: `${i.change > 0 ? '+' : ''}${i.change.toFixed(2)}%` });
    });
    data.tickers.forEach((t) => {
      const signed = t.price ? parseFloat(t.price) : null;
      items.push({ sym: t.ticker, px: `${numberFmt.format(t.mentions)} mentions`, change: signed, label: t.price || '' });
    });
    if (!items.length) return;

    const makeGroup = (hidden) => {
      const group = el('div', 'tape__group');
      if (hidden) group.setAttribute('aria-hidden', 'true');
      items.forEach((item) => {
        const node = el('span', 'tape__item');
        node.appendChild(el('span', 'tape__sym', item.sym));
        if (item.px) node.appendChild(el('span', 'tape__px', item.px));
        if (item.label) {
          const dir = direction(item.change);
          node.appendChild(el('span', dir, `${arrow(item.change)} ${item.label.replace(/^[+-]/, '')}`));
        }
        group.appendChild(node);
      });
      return group;
    };

    track.appendChild(makeGroup(false));
    track.appendChild(makeGroup(true));
    // ~7 seconds per item keeps the tape readable at any length.
    track.style.setProperty('--tape-duration', `${Math.max(30, items.length * 7)}s`);
  }

  function renderStatus(data) {
    const ageHours = (Date.now() - data.updated.getTime()) / 36e5;
    const stale = ageHours > STALE_AFTER_HOURS;

    const dot = $('status-dot');
    dot.className = `dot ${data.isSample ? 'dot--stale' : stale ? 'dot--stale' : 'dot--live'}`;
    $('status-text').textContent = data.isSample ? 'SAMPLE FEED' : stale ? 'STALE FEED' : 'FEED OK';

    const stamp = data.updated.toISOString().replace('T', ' ').slice(0, 16);
    $('status-asof').textContent = `AS OF ${stamp} UTC`;

    $('banner-sample').hidden = !data.isSample;
    $('banner-stale').hidden = !stale || data.isSample;

    $('status-next').textContent = `NEXT RUN ${nextRunLabel()}`;
  }

  // The workflow runs Monday-Friday at 13:30 UTC.
  function nextRunLabel() {
    const now = new Date();
    const candidate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 13, 30));
    if (candidate <= now) candidate.setUTCDate(candidate.getUTCDate() + 1);
    while (candidate.getUTCDay() === 0 || candidate.getUTCDay() === 6) {
      candidate.setUTCDate(candidate.getUTCDate() + 1);
    }
    const day = candidate.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' }).toUpperCase();
    return `${day} 13:30 UTC`;
  }

  function renderMood(data) {
    $('deck').textContent = data.headline || 'The retail desk is warming up.';
    $('seg-bull').style.width = `${data.bull}%`;
    $('seg-neutral').style.width = `${data.neutral}%`;
    $('seg-bear').style.width = `${data.bear}%`;
    $('val-bull').textContent = `${data.bull}%`;
    $('val-neutral').textContent = `${data.neutral}%`;
    $('val-bear').textContent = `${data.bear}%`;
    $('gauge').setAttribute(
      'aria-label',
      `Overall Reddit sentiment: ${data.bull} percent bullish, ${data.neutral} percent neutral, ${data.bear} percent bearish`
    );
  }

  function buildRow(t, rank, index, maxMentions) {
    const li = el('li', 'row');
    li.dataset.sentiment = t.sentiment;
    li.style.setProperty('--i', String(index));

    li.appendChild(el('div', 'row__rank', String(rank).padStart(2, '0')));

    const id = el('div', 'row__id');
    id.appendChild(el('span', 'row__ticker', t.ticker));
    if (t.company) id.appendChild(el('span', 'row__company', t.company));
    if (t.sub) id.appendChild(el('span', 'row__sub', t.sub));
    li.appendChild(id);

    const mentions = el('div', 'metric metric--mentions');
    mentions.appendChild(el('span', 'metric__label', 'Mentions 24h'));
    mentions.appendChild(el('span', 'metric__value', numberFmt.format(t.mentions)));
    const bar = el('div', 'meter');
    const fill = el('span', 'meter__fill');
    fill.style.setProperty('--w', String(maxMentions ? Math.round((t.mentions / maxMentions) * 100) : 0));
    bar.appendChild(fill);
    mentions.appendChild(bar);
    li.appendChild(mentions);

    const mood = el('div', 'metric metric--mood');
    const moodLabel = el('span', 'metric__label', 'Reddit mood');
    mood.appendChild(moodLabel);
    const moodLine = el('div');
    moodLine.appendChild(el('span', `badge badge--${t.sentiment}`, t.sentiment));
    moodLine.appendChild(el('span', 'metric__value', `${t.bullishPct}% bull`));
    mood.appendChild(moodLine);
    const moodBar = el('div', 'meter meter--mood');
    const moodFill = el('span', 'meter__fill meter__fill--mood');
    moodFill.style.setProperty('--w', String(t.bullishPct));
    moodBar.appendChild(moodFill);
    mood.appendChild(moodBar);
    li.appendChild(mood);

    const move = el('div', 'row__move');
    if (t.price) {
      const value = parseFloat(t.price);
      const dir = direction(value);
      move.classList.add(dir);
      move.appendChild(el('small', undefined, 'Price'));
      move.appendChild(document.createTextNode(`${arrow(value)} ${t.price.replace(/^[+-]/, '')}`));
    } else {
      move.classList.add('flat');
      move.appendChild(el('small', undefined, 'Price'));
      move.appendChild(document.createTextNode('n/a'));
    }
    li.appendChild(move);

    if (t.reason) li.appendChild(el('p', 'row__note', t.reason));
    return li;
  }

  function setupBoard(data) {
    const rows = $('rows');
    const maxMentions = Math.max(0, ...data.tickers.map((t) => t.mentions));
    const counts = {
      all: data.tickers.length,
      bullish: data.tickers.filter((t) => t.sentiment === 'bullish').length,
      bearish: data.tickers.filter((t) => t.sentiment === 'bearish').length,
    };
    Object.keys(counts).forEach((key) => { $(`n-${key}`).textContent = String(counts[key]); });

    const buttons = Array.from(document.querySelectorAll('.filter'));

    function render(filter) {
      rows.replaceChildren();
      const visible = data.tickers
        .map((t, i) => ({ t, rank: i + 1 }))
        .filter(({ t }) => filter === 'all' || t.sentiment === filter);
      visible.forEach(({ t, rank }, i) => rows.appendChild(buildRow(t, rank, i, maxMentions)));
      $('empty').hidden = visible.length > 0;
      $('live').textContent = `Showing ${visible.length} ${filter === 'all' ? '' : `${filter} `}ticker${visible.length === 1 ? '' : 's'}.`;
    }

    buttons.forEach((button) => {
      button.addEventListener('click', () => {
        buttons.forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
        render(button.dataset.filter);
      });
    });

    render('all');
  }

  function showError() {
    $('error').hidden = false;
    $('status-dot').className = 'dot dot--down';
    $('status-text').textContent = 'FEED DOWN';
    $('deck').textContent = 'The retail desk is off the air.';
  }

  async function init() {
    $('status-next').textContent = `NEXT RUN ${nextRunLabel()}`;
    try {
      const response = await fetch(DATA_URL, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = normalize(await response.json());
      if (!data.tickers.length) throw new Error('no tickers');
      renderStatus(data);
      renderMood(data);
      renderTape(data);
      setupBoard(data);
    } catch (err) {
      console.error('Feed error:', err);
      showError();
    }
  }

  init();
})();
