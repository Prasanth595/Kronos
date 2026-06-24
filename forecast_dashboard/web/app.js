/* ============================================================================
   Kronos dashboard — frontend app.
   Talks to the FastAPI backend (/api/*), draws charts with ECharts.
   Honesty-first: band is the most prominent chart element, median is dashed
   (clearly "not the answer"), no confidence score anywhere.
   ========================================================================== */

const THEMES = [
  { key: "paper", name: "Paper" },
  { key: "ink", name: "Ink" },
  { key: "slate", name: "Slate" },
  { key: "eink", name: "E-ink" },
];

const state = {
  instruments: [],
  timeframes: [],
  timeframe: "1d",
  current: null,
  view: "detail",
  themeIdx: 0,
  charts: {},          // id -> echarts instance
  lastForecast: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function fmt(n, d = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}

function decimals(v) {
  const a = Math.abs(v || 0);
  if (a >= 1000) return 1;
  if (a >= 100) return 2;
  if (a >= 1) return 3;
  return 4;
}

/* ---------------- API ---------------- */
async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`${res.status} ${t}`);
  }
  return res.json();
}

/* ---------------- Theme ---------------- */
function applyTheme(idx) {
  state.themeIdx = (idx + THEMES.length) % THEMES.length;
  const t = THEMES[state.themeIdx];
  document.documentElement.setAttribute("data-theme", t.key);
  $("#themeName").textContent = t.name;
  localStorage.setItem("kronos_theme", String(state.themeIdx));
  // redraw charts with new palette
  redrawAll();
}

/* ---------------- Overlay ---------------- */
function showOverlay(text) {
  $("#overlayText").textContent = text || "Working…";
  $("#overlay").classList.remove("hidden");
}
function hideOverlay() { $("#overlay").classList.add("hidden"); }

/* ---------------- Instrument tabs ---------------- */
function renderTabs() {
  const nav = $("#instrumentTabs");
  nav.innerHTML = "";
  state.instruments.forEach((inst) => {
    const b = document.createElement("button");
    b.className = "itab" + (inst.key === state.current ? " is-active" : "");
    let flag = "";
    if (!inst.has_reliable_volume) flag = '<span class="flag">LOW CONF</span>';
    else if (inst.event_sensitive) flag = '<span class="flag">EVENT</span>';
    b.innerHTML = inst.display_name + flag;
    b.onclick = () => selectInstrument(inst.key);
    nav.appendChild(b);
  });
}

/* ---------------- Timeframe switcher ---------------- */
function renderTimeframes() {
  const box = $("#tfToggle");
  if (!box) return;
  box.innerHTML = "";
  state.timeframes.forEach((tf) => {
    const b = document.createElement("button");
    b.className = "seg-btn" + (tf.key === state.timeframe ? " is-active" : "");
    b.dataset.tf = tf.key;
    b.textContent = tf.key === "1d" ? "Daily" : tf.key;
    b.title = tf.label + (tf.intraday ? " (intraday, ~15min delayed)" : "");
    b.onclick = () => selectTimeframe(tf.key);
    box.appendChild(b);
  });
}

function selectTimeframe(key) {
  if (key === state.timeframe) return;
  state.timeframe = key;
  localStorage.setItem("kronos_tf", key);
  renderTimeframes();
  // intraday horizon ranges differ from daily; update slider hints + unit
  const intraday = key !== "1d";
  const unit = $("#predLenUnit");
  if (unit) unit.textContent = intraday ? (key === "1h" ? "h" : " bars") : "d";
  runForecast(false);
}

/* lean -> arrow + word */
function leanDisplay(lean) {
  if (lean === "higher") return { arrow: "▲", word: "leans higher", cls: "up" };
  if (lean === "lower") return { arrow: "▼", word: "leans lower", cls: "down" };
  return { arrow: "▬", word: "flat", cls: "flat" };
}

/* ---------------- Charts ---------------- */
function getChart(id) {
  if (!state.charts[id]) {
    state.charts[id] = echarts.init(document.getElementById(id), null, { renderer: "canvas" });
  }
  return state.charts[id];
}

function baseGrid() {
  return {
    textStyle: { fontFamily: "IBM Plex Mono, monospace", color: cssVar("--ink2") },
    grid: { left: 54, right: 18, top: 16, bottom: 28 },
    tooltip: {
      trigger: "axis",
      backgroundColor: cssVar("--panel"),
      borderColor: cssVar("--line2"),
      textStyle: { color: cssVar("--ink"), fontFamily: "IBM Plex Mono, monospace", fontSize: 11 },
      axisPointer: { lineStyle: { color: cssVar("--ink2") } },
    },
  };
}

function drawFan(d) {
  const chart = getChart("fanChart");
  const ink = cssVar("--ink"), ink2 = cssVar("--ink2"), grid = cssVar("--grid");
  const band = cssVar("--band"), band2 = cssVar("--band2"), sample = cssVar("--sample");
  const accent = cssVar("--accent");

  const histDates = d.history.dates;
  const fDates = d.forecast.dates;
  const allDates = histDates.concat(fDates);
  const nh = histDates.length;
  const pad = (arr) => new Array(nh).fill(null).concat(arr);

  const dp = decimals(d.last_close);

  // bands as stacked areas: base = p10, then (p25-p10), (median-p25)... we instead
  // use two stacked sets to render p10-p90 and p25-p75.
  const p10 = pad(d.forecast.p10);
  const p90 = pad(d.forecast.p90);
  const p25 = pad(d.forecast.p25);
  const p75 = pad(d.forecast.p75);
  const med = pad(d.forecast.median);

  const diff = (hi, lo) => hi.map((v, i) => (v === null || lo[i] === null ? null : +(v - lo[i]).toFixed(6)));

  const series = [];

  // Outer band p10..p90 (stack outer): base p10 (transparent) + (p90-p10)
  series.push({ name: "_p10base", type: "line", data: p10, stack: "outer", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { opacity: 0 }, silent: true });
  series.push({ name: "p10–p90 (80%)", type: "line", data: diff(p90, p10), stack: "outer", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color: band }, silent: true });

  // Inner band p25..p75 (stack inner)
  series.push({ name: "_p25base", type: "line", data: p25, stack: "inner", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { opacity: 0 }, silent: true });
  series.push({ name: "p25–p75 (50%)", type: "line", data: diff(p75, p25), stack: "inner", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color: band2 }, silent: true });

  // faint sample paths
  (d.sample_paths || []).forEach((sp) => {
    series.push({ type: "line", data: pad(sp), lineStyle: { color: sample, width: 1 }, symbol: "none", silent: true, z: 1 });
  });

  // median (dashed = not the answer)
  series.push({ name: "median (p50)", type: "line", data: med, lineStyle: { color: accent, width: 2, type: "dashed" }, symbol: "none", z: 4 });

  // history (solid)
  series.push({ name: "history", type: "line", data: histDates.map((_, i) => d.history.close[i]).concat(new Array(fDates.length).fill(null)), lineStyle: { color: ink, width: 2 }, symbol: "none", z: 3 });

  chart.setOption({
    ...baseGrid(),
    legend: { show: false },
    xAxis: {
      type: "category", data: allDates, boundaryGap: false,
      axisLine: { lineStyle: { color: cssVar("--line2") } },
      axisLabel: { color: ink2, fontSize: 10, hideOverlap: true },
      splitLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value", scale: true,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: ink2, fontSize: 10, formatter: (v) => fmt(v, v >= 100 ? 0 : 2) },
      splitLine: { lineStyle: { color: grid } },
    },
    tooltip: {
      ...baseGrid().tooltip,
      formatter: (params) => {
        const date = params[0].axisValue;
        const find = (n) => { const p = params.find((x) => x.seriesName === n); return p ? p.value : null; };
        const h = find("history"), m = find("median (p50)");
        let rows = `<div style="font-weight:600;margin-bottom:4px">${date}</div>`;
        if (h !== null && h !== undefined) rows += `history <b>${fmt(h, dp)}</b><br/>`;
        if (m !== null && m !== undefined) {
          const idx = fDates.indexOf(date);
          if (idx >= 0) {
            rows += `p90 ${fmt(d.forecast.p90[idx], dp)}<br/>`;
            rows += `median <b>${fmt(d.forecast.median[idx], dp)}</b><br/>`;
            rows += `p10 ${fmt(d.forecast.p10[idx], dp)}`;
          }
        }
        return rows;
      },
    },
    markLine: undefined,
    series,
  }, true);

  // last-close reference line via a markLine on the history series
  chart.setOption({
    series: [{ name: "history", markLine: {
      symbol: "none", silent: true,
      lineStyle: { color: ink2, type: "dotted", width: 1 },
      data: [{ yAxis: d.last_close }],
      label: { show: false },
    }}],
  });

  // legend (custom DOM)
  $("#fanLegend").innerHTML = `
    <span class="li"><span class="sw solid-line"></span>history</span>
    <span class="li"><span class="sw line"></span>median (p50)</span>
    <span class="li"><span class="sw" style="background:${band2}"></span>p25–p75</span>
    <span class="li"><span class="sw" style="background:${band}"></span>p10–p90</span>
    <span class="li"><span class="sw" style="background:${sample}"></span>sample paths</span>`;
}

function drawSkew(d) {
  const chart = getChart("skewChart");
  const accent = cssVar("--accent"), ink2 = cssVar("--ink2"), grid = cssVar("--grid");
  chart.setOption({
    ...baseGrid(),
    grid: { left: 44, right: 12, top: 24, bottom: 24 },
    legend: { top: 0, right: 0, textStyle: { color: ink2, fontFamily: "IBM Plex Mono", fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
    xAxis: { type: "category", data: d.skew.horizon, axisLabel: { color: ink2, fontSize: 9 }, axisLine: { lineStyle: { color: cssVar("--line2") } }, axisTick: { show: false } },
    yAxis: { type: "value", axisLabel: { color: ink2, fontSize: 9 }, splitLine: { lineStyle: { color: grid } }, axisLine: { show: false } },
    series: [
      { name: "downside", type: "bar", data: d.skew.downside, itemStyle: { color: accent }, barWidth: "38%" },
      { name: "upside", type: "bar", data: d.skew.upside, itemStyle: { color: ink2 }, barWidth: "38%" },
    ],
  }, true);
}

function drawProb(d) {
  const chart = getChart("probChart");
  const accent = cssVar("--accent"), ink2 = cssVar("--ink2"), grid = cssVar("--grid");
  chart.setOption({
    ...baseGrid(),
    grid: { left: 40, right: 12, top: 14, bottom: 24 },
    xAxis: { type: "category", data: d.skew.horizon, axisLabel: { color: ink2, fontSize: 9 }, axisLine: { lineStyle: { color: cssVar("--line2") } }, axisTick: { show: false } },
    yAxis: { type: "value", min: 0, max: 100, axisLabel: { color: ink2, fontSize: 9, formatter: "{value}%" }, splitLine: { lineStyle: { color: grid } }, axisLine: { show: false } },
    series: [
      { type: "line", data: d.skew.prob_below_last_close.map((v) => +(v * 100).toFixed(1)), lineStyle: { color: accent, width: 2 }, symbol: "none", areaStyle: { color: cssVar("--band") },
        markLine: { symbol: "none", silent: true, lineStyle: { color: ink2, type: "dotted" }, data: [{ yAxis: 50 }], label: { show: false } } },
    ],
  }, true);
}

function drawSpark(id, card) {
  const chart = getChart(id);
  const accent = cssVar("--accent"), band = cssVar("--band");
  const n = card.median_series.length;
  const xs = Array.from({ length: n }, (_, i) => i + 1);
  const diff = card.p90_series.map((v, i) => +(v - card.p10_series[i]).toFixed(6));
  chart.setOption({
    grid: { left: 2, right: 2, top: 6, bottom: 6 },
    xAxis: { type: "category", data: xs, show: false, boundaryGap: false },
    yAxis: { type: "value", scale: true, show: false },
    tooltip: { show: false },
    series: [
      { type: "line", data: card.p10_series, stack: "b", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { opacity: 0 }, silent: true },
      { type: "line", data: diff, stack: "b", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color: band }, silent: true },
      { type: "line", data: card.median_series, lineStyle: { color: accent, width: 1.5, type: "dashed" }, symbol: "none", silent: true },
    ],
  }, true);
}

function redrawAll() {
  if (state.view === "detail" && state.lastForecast) {
    drawFan(state.lastForecast);
    drawSkew(state.lastForecast);
    drawProb(state.lastForecast);
  }
  Object.values(state.charts).forEach((c) => c.resize());
}

/* ---------------- Render detail ---------------- */
function renderDetail(d) {
  state.lastForecast = d;
  const dp = decimals(d.last_close);

  $("#instName").textContent = d.display_name;

  // badges
  const badges = [];
  if (!d.has_reliable_volume) badges.push(`<span class="badge warn">low confidence · no volume</span>`);
  if (d.event_sensitive) badges.push(`<span class="badge warn">event-sensitive</span>`);
  badges.push(`<span class="badge ${d.used_volume_path ? "" : "soft"}">${d.used_volume_path ? "volume path" : "no-volume path"}</span>`);
  badges.push(`<span class="badge soft">${d.timeframe_label}</span>`);
  $("#badges").innerHTML = badges.join("");

  // stats
  $("#stripStats").innerHTML = `
    <div class="stat"><span class="k">Last close</span><span class="v">${fmt(d.last_close, dp)}</span></div>
    <div class="stat"><span class="k">Ticker</span><span class="v mono">${d.ticker_used}</span></div>
    <div class="stat"><span class="k">As of</span><span class="v mono">${d.last_history_date}</span></div>
    <div class="stat"><span class="k">Realized vol</span><span class="v">${fmt(d.realized_vol_annualized * 100, 1)}%</span></div>`;

  // table
  const f = d.forecast;
  const col = d.is_intraday ? "Time (UTC)" : "Date";
  let rows = `<thead><tr><th>${col}</th><th>Low p10</th><th>p25</th><th>Median</th><th>p75</th><th>High p90</th></tr></thead><tbody>`;
  f.dates.forEach((date, i) => {
    rows += `<tr><td>${date}</td><td>${fmt(f.p10[i], dp)}</td><td>${fmt(f.p25[i], dp)}</td><td class="med">${fmt(f.median[i], dp)}</td><td>${fmt(f.p75[i], dp)}</td><td>${fmt(f.p90[i], dp)}</td></tr>`;
  });
  rows += `</tbody>`;
  $("#distTable").innerHTML = rows;

  // charts
  drawFan(d);
  drawSkew(d);
  drawProb(d);
  $("#skewSentence").textContent = d.skew_sentence;

  // accuracy
  renderAccuracy(d.accuracy);

  // analysis (markdown-ish -> html)
  $("#analysisBody").innerHTML = mdToHtml(d.analysis_text);

  // Layer 2 + combined read (sentiment is in the forecast payload now)
  renderCombined(d);
  renderSentiment(d.sentiment);
  renderHeadlines(d.sentiment);
}

/* ---------------- Combined read (the headline) ---------------- */
function renderCombined(d) {
  const c = d.combined;
  const priceL = leanDisplay(d.price_lean);
  $("#priceLean").innerHTML = `<span class="${priceL.cls}">${priceL.arrow}</span> ${priceL.word}`;
  $("#priceSub").textContent = `${d.timeframe_label} median vs last close`;

  if (!c) {
    $("#newsLean").innerHTML = "—";
    $("#verdictStatus").textContent = "no news";
    $("#verdictStatus").className = "verdict-status";
    $("#verdictText").textContent = "News sentiment unavailable; showing the price model only.";
    $("#combinedBanner").dataset.status = "partial";
    return;
  }
  const newsL = leanDisplay(c.news_lean);
  $("#newsLean").innerHTML = `<span class="${newsL.cls}">${newsL.arrow}</span> ${newsL.word}`;
  $("#newsSub").textContent = `${c.sentiment_label} (${c.sentiment_score >= 0 ? "+" : ""}${fmt(c.sentiment_score, 2)})`;

  const statusLabel = { aligned: "Agree", divergent: "Diverge", partial: "Partial" }[c.status] || c.status;
  $("#verdictStatus").textContent = statusLabel;
  $("#verdictStatus").className = "verdict-status " + c.status;
  $("#verdictText").textContent = c.verdict;
  $("#combinedBanner").dataset.status = c.status;
}

/* ---------------- News sentiment (Layer 2) ---------------- */
function renderSentiment(s) {
  const body = $("#sentimentBody");
  const methodEl = $("#sentMethod");
  if (!s) {
    methodEl.textContent = "unavailable";
    body.innerHTML = `<div class="news-notice">News sentiment unavailable right now.</div>`;
    return;
  }
  const methodLabel = { gemini: "Gemini (Vertex)", anthropic: "Claude", lexicon: "keyword baseline", none: "no headlines" }[s.method] || s.method;
  methodEl.textContent = methodLabel;

  // gauge: -1..+1 mapped to 0..100%
  const score = s.aggregate_score;
  const pct = Math.round((score + 1) / 2 * 100);
  const scoreCls = score > 0.15 ? "up" : (score < -0.15 ? "down" : "flat");

  let html = `
    <div class="sent-gauge">
      <div class="gauge-track">
        <div class="gauge-mid"></div>
        <div class="gauge-marker" style="left:${pct}%"></div>
      </div>
      <div class="gauge-labels"><span>bearish</span><span>neutral</span><span>bullish</span></div>
    </div>
    <div class="sent-head">
      <div class="sent-score ${scoreCls}">${score >= 0 ? "+" : ""}${fmt(score, 2)}</div>
      <div class="sent-label">${s.label}<span class="sent-n">${s.n_headlines} headline${s.n_headlines === 1 ? "" : "s"}</span></div>
    </div>`;

  if (s.drivers && s.drivers.length) {
    html += `<div class="drivers">` + s.drivers.map((d) => `<span class="chip">${esc(d)}</span>`).join("") + `</div>`;
  }
  if (s.method === "lexicon") {
    html += `<div class="sent-method-note">${esc(s.method_note)}</div>`;
  }
  html += `<div class="disc">${esc(s.disclaimer)}</div>`;
  body.innerHTML = html;
}

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* scored headlines list */
function renderHeadlines(s) {
  const body = $("#newsBody");
  if (!s || !s.headlines || !s.headlines.length) {
    body.innerHTML = `<div class="news-notice">No recent headlines.</div>`;
    return;
  }
  let html = "";
  s.headlines.forEach((h) => {
    const cls = h.score > 0.1 ? "up" : (h.score < -0.1 ? "down" : "flat");
    const sign = h.score >= 0 ? "+" : "";
    const link = h.url ? `<a href="${h.url}" target="_blank" rel="noopener">${esc(h.title)}</a>` : esc(h.title);
    html += `<div class="hl">
      <span class="hl-score ${cls}">${sign}${fmt(h.score, 2)}</span>
      <span class="hl-body">${link}
        ${h.source ? `<span class="src">${esc(h.source)}</span>` : ""}
        ${h.rationale ? `<span class="why">${esc(h.rationale)}</span>` : ""}
      </span></div>`;
  });
  body.innerHTML = html;
}

function renderAccuracy(acc) {
  const body = $("#accBody");
  if (!acc || acc.n_reconciled === 0) {
    body.innerHTML = `<div class="acc-empty">No reconciled forecasts yet. Run forecasts over several days, then hit <b>Refresh actuals</b> once target dates pass. Calibration is unknown until then — do not assume the band is right.</div>`;
    return;
  }
  const pct = (v) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
  body.innerHTML = `
    <div class="acc-metrics">
      <div class="acc-metric"><div class="k">Band hit-rate</div><div class="v">${pct(acc.band_hit_rate)}</div></div>
      <div class="acc-metric"><div class="k">Median abs err</div><div class="v">${fmt(acc.median_abs_error, 3)}</div></div>
      <div class="acc-metric"><div class="k">Directional</div><div class="v">${pct(acc.directional_accuracy)}</div></div>
    </div>
    <div class="acc-note">${acc.calibration_note} <br/><span style="opacity:.7">${acc.n_reconciled} reconciled points · nominal band coverage ${Math.round(acc.band_nominal * 100)}%.</span></div>`;
}

/* tiny markdown subset -> html (bold, italics, headings, lists, blockquote) */
function mdToHtml(md) {
  if (!md) return "—";
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = md.split("\n");
  let html = "", inList = false;
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\*(.+?)\*/g, "<i>$1</i>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
  for (let raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { if (inList) { html += "</ul>"; inList = false; } continue; }
    if (line.startsWith("### ")) { if (inList) { html += "</ul>"; inList = false; } html += `<h4>${inline(line.slice(4))}</h4>`; }
    else if (line.startsWith("> ")) { if (inList) { html += "</ul>"; inList = false; } html += `<blockquote>${inline(line.slice(2))}</blockquote>`; }
    else if (line.startsWith("- ")) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(line.slice(2))}</li>`; }
    else { if (inList) { html += "</ul>"; inList = false; } html += `<p>${inline(line)}</p>`; }
  }
  if (inList) html += "</ul>";
  return html;
}

/* ---------------- Glance ---------------- */
async function loadGlance() {
  showOverlay("Loading all four…");
  try {
    const data = await api(`/api/glance`);
    const grid = $("#glanceGrid");
    grid.innerHTML = "";
    data.cards.forEach((c) => {
      const div = document.createElement("div");
      div.className = "gcard";
      if (c.error) {
        div.innerHTML = `<div class="gcard-head"><span class="name">${c.display_name}</span></div><div class="gcard-range">error: ${c.error}</div>`;
        grid.appendChild(div);
        return;
      }
      const dp = decimals(c.last_close);
      const lean = leanDisplay(c.price_lean || (c.median_1w > c.last_close * 1.001 ? "higher" : (c.median_1w < c.last_close * 0.999 ? "lower" : "flat")));
      const flag = !c.has_reliable_volume ? "LOW CONF" : (c.event_sensitive ? "EVENT" : "");
      const sparkId = `spark_${c.instrument}`;
      // combined verdict chip
      let verdict = "";
      if (c.combined) {
        const st = c.combined.status;
        const lbl = { aligned: "agree", divergent: "diverge", partial: "partial" }[st] || st;
        verdict = `<span class="gverdict ${st}">${lbl}</span>`;
      }
      const sScore = (c.sentiment_score === null || c.sentiment_score === undefined)
        ? "" : `<span class="gsent ${c.sentiment_score > 0.15 ? "up" : (c.sentiment_score < -0.15 ? "down" : "flat")}">news ${c.sentiment_score >= 0 ? "+" : ""}${fmt(c.sentiment_score, 2)}</span>`;
      div.innerHTML = `
        <div class="gcard-head">
          <div><div class="name">${c.display_name}</div><div class="tk">${c.ticker_used}${flag ? " · " + flag : ""}</div></div>
          ${verdict}
        </div>
        <div class="gcard-price">${fmt(c.last_close, dp)}</div>
        <div class="gcard-range">1wk median ${fmt(c.median_1w, dp)} · p10–p90 ${fmt(c.p10_1w, dp)}–${fmt(c.p90_1w, dp)}</div>
        <div class="gcard-lean"><span class="lean-tag"><span class="${lean.cls}">${lean.arrow}</span> price ${lean.word}</span>${sScore}</div>
        <div class="gcard-spark" id="${sparkId}"></div>`;
      div.onclick = () => { selectInstrument(c.instrument); setView("detail"); };
      grid.appendChild(div);
      setTimeout(() => drawSpark(sparkId, c), 0);
    });
  } catch (e) {
    $("#glanceGrid").innerHTML = `<div class="news-notice">Failed: ${e.message}</div>`;
  } finally {
    hideOverlay();
  }
}

/* ---------------- Actions ---------------- */
async function runForecast(force) {
  const inst = state.current;
  const pred_len = +$("#predLen").value;
  const lookback = +$("#lookback").value;
  const n_samples = +$("#nSamples").value;
  const tf = state.timeframe;
  showOverlay(force ? "Running forecast…" : "Loading forecast…");
  try {
    const d = await api(`/api/forecast/${inst}?pred_len=${pred_len}&lookback=${lookback}&n_samples=${n_samples}&timeframe=${tf}&force=${force ? "true" : "false"}`);
    renderDetail(d);
    $("#footStatus").textContent = `${d.timeframe_label} forecast · generated ${new Date(d.generated_at).toLocaleString()}`;
  } catch (e) {
    alert("Forecast failed: " + e.message);
  } finally {
    hideOverlay();
  }
}

async function refreshActuals() {
  showOverlay("Reconciling against realized actuals…");
  try {
    const r = await api(`/api/refresh-actuals`, { method: "POST" });
    $("#footStatus").textContent = `reconciled ${r.reconciled} point(s)`;
    if (state.lastForecast) {
      const acc = await api(`/api/accuracy/${state.current}`);
      renderAccuracy(acc);
    }
  } catch (e) {
    alert("Refresh failed: " + e.message);
  } finally {
    hideOverlay();
  }
}

function selectInstrument(key) {
  state.current = key;
  localStorage.setItem("kronos_inst", key);
  renderTabs();
  if (state.view === "detail") runForecast(false);
}

function setView(view) {
  state.view = view;
  $$("#viewToggle .seg-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.view === view));
  $("#detailView").classList.toggle("hidden", view !== "detail");
  $("#glanceView").classList.toggle("hidden", view !== "glance");
  if (view === "glance") loadGlance();
  else { renderTabs(); if (!state.lastForecast) runForecast(false); else redrawAll(); }
}

/* ---------------- Init ---------------- */
async function init() {
  // theme
  const savedTheme = +(localStorage.getItem("kronos_theme") || 0);
  applyTheme(Number.isNaN(savedTheme) ? 0 : savedTheme);

  $("#themeBtn").onclick = () => applyTheme(state.themeIdx + 1);
  $$("#viewToggle .seg-btn").forEach((b) => (b.onclick = () => setView(b.dataset.view)));
  $("#runBtn").onclick = () => runForecast(true);
  $("#refreshBtn").onclick = refreshActuals;

  // control labels
  const bind = (id, out) => { const el = $(id), o = $(out); el.oninput = () => (o.textContent = el.value); };
  bind("#predLen", "#predLenOut");
  bind("#lookback", "#lookbackOut");
  bind("#nSamples", "#nSamplesOut");

  window.addEventListener("resize", () => Object.values(state.charts).forEach((c) => c.resize()));

  // load instruments
  try {
    const data = await api("/api/instruments");
    state.instruments = data.order.map((k) => data.instruments.find((i) => i.key === k));
    const savedInst = localStorage.getItem("kronos_inst");
    state.current = (savedInst && state.instruments.some((i) => i.key === savedInst)) ? savedInst : state.instruments[0].key;
    renderTabs();

    // load timeframes + restore selection
    try {
      const tfData = await api("/api/timeframes");
      state.timeframes = tfData.timeframes || [];
      const savedTf = localStorage.getItem("kronos_tf");
      if (savedTf && state.timeframes.some((t) => t.key === savedTf)) state.timeframe = savedTf;
      else state.timeframe = tfData.default || "1d";
      renderTimeframes();
    } catch (e) { /* timeframes optional */ }

    const h = await api("/api/health");
    $("#footStatus").textContent = `${h.model} · ${h.device}`;
    runForecast(false);
  } catch (e) {
    document.body.innerHTML = `<div style="padding:40px;font-family:monospace">Backend not reachable: ${e.message}</div>`;
  }
}

init();
