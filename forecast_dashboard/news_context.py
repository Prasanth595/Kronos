"""news_context.py — "things the model did NOT see" + text-based analysis.

Two honest jobs (SCOPE.md §0, §5.6):

1. Surface RECENT HEADLINES for an instrument, framed as context the price-only
   model could NOT have seen (Fed/BoE/BoJ, CPI, OPEC, risk events). This is NEVER
   a forecast input and NEVER produces a numeric reliability/confidence score.

2. Produce a TEXT-BASED ANALYSIS ("bot") that describes the forecast DISTRIBUTION
   in plain English — bands, skew, realized vol, calibration so far — and the blind
   spot. If an LLM is configured it can phrase the read, but it is explicitly
   labelled as an UNVALIDATED impression and is forbidden from emitting a score.

Everything degrades gracefully: with no API keys, the panel still works using a
deterministic, rule-based analysis built straight from the ForecastResult.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# Per-instrument search query + the macro events the daily model cannot see.
NEWS_QUERIES: dict[str, dict] = {
    "silver": {
        "query": "silver price XAG today Fed rate inflation industrial demand",
        "blind_spots": ["Fed rate decisions", "CPI / inflation prints",
                        "industrial demand shifts", "USD moves", "risk-on/off swings"],
    },
    "gold": {
        "query": "gold price XAU today Fed rate inflation safe haven central banks",
        "blind_spots": ["Fed rate decisions", "CPI / inflation prints",
                        "central-bank buying", "geopolitical risk", "real yields"],
    },
    "wti": {
        "query": "WTI crude oil price today OPEC inventory EIA supply demand",
        "blind_spots": ["OPEC+ production decisions", "EIA/API inventory reports",
                        "supply disruptions / sanctions", "demand outlook", "geopolitics"],
    },
    "gbpjpy": {
        "query": "GBP/JPY pound yen today BoE BoJ intervention rate decision",
        "blind_spots": ["BoE rate decisions", "BoJ policy / YCC", "MoF FX intervention",
                        "UK CPI / jobs", "global risk sentiment"],
    },
}

DISCLAIMER = ("LLM impression of headline tone — UNVALIDATED, do not weight heavily. "
              "This is NOT a forecast input and carries NO confidence score.")


@dataclass
class NewsItem:
    title: str
    source: str = ""
    url: str = ""
    published: str = ""


@dataclass
class NewsContext:
    instrument_key: str
    blind_spots: list
    items: list           # list[NewsItem]
    tone_note: Optional[str]   # optional LLM impression (labelled), or None
    enabled: bool         # whether live search ran
    notice: str           # explanation shown when search is disabled/empty


# --------------------------------------------------------------------------- #
# Live headline search (optional; Tavily if configured)
# --------------------------------------------------------------------------- #
def _search_tavily(query: str, max_results: int = 6) -> list:
    """Search headlines via Tavily if TAVILY_API_KEY is set. Returns [NewsItem]."""
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        import requests
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "topic": "news",
                "max_results": max_results,
                "search_depth": "basic",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for r in data.get("results", [])[:max_results]:
            items.append(NewsItem(
                title=r.get("title", "")[:200],
                source=(r.get("url", "").split("/")[2] if r.get("url") else ""),
                url=r.get("url", ""),
                published=r.get("published_date", "") or "",
            ))
        return items
    except Exception:  # noqa: BLE001 - news is best-effort
        return []


def _llm_tone_note(instrument_display: str, items: list) -> Optional[str]:
    """Ask an LLM for a one-line tone impression IF ANTHROPIC_API_KEY is set.

    Hard constraint: the prompt forbids any numeric score and requires the output
    to be a qualitative impression only. We still wrap it with the disclaimer.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or not items:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        headlines = "\n".join(f"- {it.title}" for it in items[:8])
        prompt = (
            "You are summarizing recent headline TONE for context only. "
            "Rules you MUST follow:\n"
            "1. Output ONE short sentence (max 25 words).\n"
            "2. Do NOT output any number, percentage, score, or probability.\n"
            "3. Do NOT give trading advice or a directional prediction.\n"
            "4. Only describe the qualitative tone (e.g. cautious, bullish chatter, "
            "mixed, focused on supply).\n\n"
            f"Instrument: {instrument_display}\nHeadlines:\n{headlines}\n\n"
            "One-sentence tone impression:"
        )
        msg = client.messages.create(
            model=model,
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        return text or None
    except Exception:  # noqa: BLE001 - LLM is best-effort
        return None


def get_news_context(instrument_key: str, instrument_display: str) -> NewsContext:
    """Build the 'context the model did NOT see' panel data."""
    cfg = NEWS_QUERIES.get(instrument_key, {"query": instrument_display, "blind_spots": []})
    items = _search_tavily(cfg["query"])
    enabled = bool(os.environ.get("TAVILY_API_KEY", "").strip())

    tone = _llm_tone_note(instrument_display, items) if items else None

    if not enabled:
        notice = ("Live news search is OFF (no TAVILY_API_KEY). The blind-spot list "
                  "below still shows the event types the model cannot see.")
    elif not items:
        notice = "No recent headlines returned. The blind-spot list still applies."
    else:
        notice = ""

    return NewsContext(
        instrument_key=instrument_key,
        blind_spots=cfg.get("blind_spots", []),
        items=items,
        tone_note=tone,
        enabled=enabled,
        notice=notice,
    )


# --------------------------------------------------------------------------- #
# Text-based analysis "bot" — deterministic, honesty-first
# --------------------------------------------------------------------------- #
def analyze_forecast_text(result, accuracy: Optional[dict] = None) -> str:
    """Generate a plain-English read of a ForecastResult.

    Always deterministic and rule-based (no API needed). Describes the
    distribution, band width, skew, realized vol, and calibration-so-far, and
    always restates the blind spot. Never emits a confidence score.
    """
    r = result
    last = r.last_close
    # Horizons to talk about: ~1wk and end.
    h_wk = min(4, r.pred_len - 1)
    h_end = r.pred_len - 1

    def band_pct(i):
        lo, hi = r.p10[i], r.p90[i]
        return (hi - lo) / last * 100 if last else float("nan")

    med_wk = r.median[h_wk]
    med_end = r.median[h_end]
    dir_wk = "higher" if med_wk > last else ("lower" if med_wk < last else "flat")

    lines = []
    lines.append(f"### Text analysis — {r.display_name}")
    lines.append("")
    lines.append(
        f"As of {r.last_history_date.date()} the last close was **{last:,.4f}** "
        f"(ticker `{r.ticker_used}`). The forecast is a **distribution of "
        f"{r.n_samples} independent sample paths**, not a single number."
    )
    lines.append("")
    lines.append(
        f"- **~1 week (+{h_wk+1}d):** median leans **{dir_wk}** at "
        f"{med_wk:,.4f}; the p10-p90 band spans {r.p10[h_wk]:,.4f} to "
        f"{r.p90[h_wk]:,.4f} (~{band_pct(h_wk):.1f}% of price wide)."
    )
    lines.append(
        f"- **End (+{h_end+1}d):** median {med_end:,.4f}; p10-p90 "
        f"{r.p10[h_end]:,.4f} to {r.p90[h_end]:,.4f} "
        f"(~{band_pct(h_end):.1f}% wide). The band widening with horizon is the "
        f"model telling you it knows less further out."
    )
    lines.append("")
    lines.append(f"- **Skew:** {r.skew_sentence()}")
    lines.append(
        f"- **Historical volatility:** {r.realized_vol_annualized*100:,.1f}% "
        f"annualized (from recent daily returns — this is realized history, "
        f"distinct from the forecast band width)."
    )

    # Calibration so far
    if accuracy and accuracy.get("n_reconciled", 0) > 0:
        if accuracy.get("enough_data"):
            lines.append(
                f"- **Track record:** {accuracy['calibration_note']} "
                f"(over {accuracy['n_reconciled']} reconciled points; "
                f"directional accuracy "
                f"{(accuracy.get('directional_accuracy') or 0)*100:.0f}%)."
            )
        else:
            lines.append(f"- **Track record:** {accuracy['calibration_note']}")
    else:
        lines.append(
            "- **Track record:** no reconciled forecasts yet — calibration is "
            "unknown until actuals come in. Do not assume the band is right."
        )

    lines.append("")
    if r.event_sensitive:
        lines.append(
            f"> **Blind spot:** {r.confidence_caveat} The model sees price candles "
            f"only; scheduled events can move this instrument outside the band."
        )
    else:
        lines.append(
            "> **Blind spot:** the model sees price candles only — no Fed/BoE/BoJ "
            "decisions, CPI, or headlines. Treat the band as price-history-implied, "
            "not all-knowing."
        )
    return "\n".join(lines)


def llm_narrative(result, accuracy: Optional[dict] = None) -> Optional[str]:
    """OPTIONAL: an LLM-phrased narrative of the deterministic analysis.

    Returns None unless ANTHROPIC_API_KEY is set. The LLM is given the already-
    computed numbers and asked to rephrase honestly; it is forbidden from adding
    a confidence score or directional advice. Output is labelled as unvalidated.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        facts = analyze_forecast_text(result, accuracy)
        prompt = (
            "Rewrite the following forecast read in 4-6 sentences of plain, honest "
            "English for a paper-trader. RULES:\n"
            "1. Keep all uncertainty framing; the forecast is a distribution.\n"
            "2. Do NOT invent any confidence score, probability, or new number.\n"
            "3. Do NOT give a buy/sell recommendation.\n"
            "4. Keep the blind-spot caveat.\n\n"
            f"{facts}"
        )
        msg = client.messages.create(
            model=model, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        if not text:
            return None
        return text + "\n\n_(LLM-phrased; unvalidated, no confidence score implied.)_"
    except Exception:  # noqa: BLE001
        return None
