"""news_sentiment.py — Layer 2: live news sentiment (the qualitative read).

This is a FIRST-CLASS layer, not a footnote. The application now shows two
honest, independent views side by side:

  Layer 1  Kronos price model     -> the distribution / band  (quantitative)
  Layer 2  News sentiment (here)   -> sentiment gauge + drivers (qualitative)

and then a COMBINED read that states whether they AGREE or DIVERGE.

Why this is honest (the whole point of the project):
  * We do NOT claim Kronos "read the news" — it is a price-only model. Pretending
    otherwise would be the lie. Instead we compute sentiment SEPARATELY and show
    where the two layers line up or conflict. Divergence is itself the signal.
  * Headlines are real (Yahoo Finance, free, no key). Sentiment scoring uses a
    proper LLM when available (Gemini via Vertex on GCP needs NO api key — the VM
    authenticates itself), and degrades to a transparent keyword baseline that is
    clearly LABELLED as crude, so the method is never hidden.
  * The sentiment score is about HEADLINE TONE, not a probability of price moves.
    It is never presented as a calibrated confidence.

Scoring methods, in priority order:
  1. gemini   — Vertex AI Gemini (no key on GCP) or GEMINI_API_KEY (dev)
  2. anthropic— if ANTHROPIC_API_KEY set
  3. lexicon  — deterministic keyword baseline (always works, clearly labelled)
"""

from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# --------------------------------------------------------------------------- #
# Instrument framing: search hints + the macro drivers that matter, and how the
# instrument typically reacts (used for the lexicon baseline + LLM context).
# --------------------------------------------------------------------------- #
INSTRUMENT_NEWS: dict[str, dict] = {
    "silver": {
        "aliases": ["silver", "xag", "precious metal", "bullion"],
        "drivers": ["Fed rate path", "CPI / inflation", "industrial demand",
                    "USD strength", "risk sentiment"],
        # safe-haven-ish but also industrial; hawkish Fed / strong USD = bearish
        "haven": True,
    },
    "gold": {
        "aliases": ["gold", "xau", "bullion", "precious metal"],
        "drivers": ["Fed rate path", "real yields", "central-bank buying",
                    "geopolitical risk", "USD strength"],
        "haven": True,
    },
    "wti": {
        "aliases": ["oil", "crude", "wti", "brent", "opec", "petroleum"],
        "drivers": ["OPEC+ supply", "inventories (EIA/API)", "supply disruptions",
                    "demand outlook", "geopolitics (Hormuz, sanctions)"],
        "haven": False,
    },
    "gbpjpy": {
        "aliases": ["pound", "sterling", "gbp", "yen", "jpy", "boe", "boj"],
        "drivers": ["BoE policy", "BoJ policy / intervention", "UK data (CPI/jobs/GDP)",
                    "risk sentiment (carry)", "USD/rate differentials"],
        "haven": False,
    },
}

# Sentiment is about the INSTRUMENT'S price, from a long perspective:
# positive score = headlines lean supportive of a HIGHER price.
SENTIMENT_LABELS = [
    (-1.01, -0.5, "strongly bearish"),
    (-0.5, -0.15, "bearish lean"),
    (-0.15, 0.15, "neutral / mixed"),
    (0.15, 0.5, "bullish lean"),
    (0.5, 1.01, "strongly bullish"),
]

DISCLAIMER = ("Sentiment reflects HEADLINE TONE only — it is not a probability or a "
              "confidence score, and it is a SEPARATE signal from the price model.")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Headline:
    title: str
    source: str = ""
    url: str = ""
    published: str = ""
    summary: str = ""


@dataclass
class ScoredHeadline:
    title: str
    source: str
    url: str
    published: str
    score: float            # -1..+1 (bullish positive) for THIS instrument
    rationale: str = ""     # short why (LLM) or matched terms (lexicon)


@dataclass
class SentimentResult:
    instrument_key: str
    headlines: list = field(default_factory=list)   # list[ScoredHeadline]
    aggregate_score: float = 0.0                      # -1..+1
    label: str = "neutral / mixed"
    drivers: list = field(default_factory=list)       # key themes / drivers
    method: str = "lexicon"                           # gemini | anthropic | lexicon
    method_note: str = ""                             # human description of method
    n_headlines: int = 0
    as_of: str = ""
    notice: str = ""

    def to_dict(self) -> dict:
        return {
            "instrument": self.instrument_key,
            "aggregate_score": round(self.aggregate_score, 4),
            "label": self.label,
            "drivers": self.drivers,
            "method": self.method,
            "method_note": self.method_note,
            "n_headlines": self.n_headlines,
            "as_of": self.as_of,
            "notice": self.notice,
            "disclaimer": DISCLAIMER,
            "headlines": [
                {"title": h.title, "source": h.source, "url": h.url,
                 "published": h.published, "score": round(h.score, 3),
                 "rationale": h.rationale}
                for h in self.headlines
            ],
        }


# --------------------------------------------------------------------------- #
# 1. Fetch headlines (Yahoo Finance via yfinance — free, no key). Robust to both
#    the old and new yfinance news schemas.
# --------------------------------------------------------------------------- #
def _parse_news_item(item: dict) -> Optional[Headline]:
    # New schema: {'content': {'title','summary','pubDate','provider':{'displayName'},
    #              'canonicalUrl':{'url'} or 'clickThroughUrl':{'url'}}}
    c = item.get("content") if isinstance(item.get("content"), dict) else None
    if c:
        title = (c.get("title") or "").strip()
        summary = (c.get("summary") or "").strip()
        prov = c.get("provider") or {}
        source = (prov.get("displayName") if isinstance(prov, dict) else "") or ""
        url = ""
        for k in ("canonicalUrl", "clickThroughUrl"):
            u = c.get(k)
            if isinstance(u, dict) and u.get("url"):
                url = u["url"]
                break
        published = (c.get("pubDate") or c.get("displayTime") or "").strip()
        if title:
            return Headline(title=title, source=source, url=url,
                            published=published, summary=summary)
        return None
    # Old schema: {'title','publisher','link','providerPublishTime'(epoch)}
    title = (item.get("title") or "").strip()
    if not title:
        return None
    published = ""
    ts = item.get("providerPublishTime")
    if ts:
        try:
            published = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            published = ""
    return Headline(
        title=title,
        source=item.get("publisher", "") or "",
        url=item.get("link", "") or "",
        published=published,
        summary=(item.get("summary") or "").strip(),
    )


def fetch_headlines(ticker: str, max_items: int = 10) -> list:
    """Fetch recent headlines for a yfinance ticker. Best-effort, never raises."""
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news or []
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for item in raw:
        h = _parse_news_item(item)
        if not h:
            continue
        key = h.title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= max_items:
            break
    return out


# --------------------------------------------------------------------------- #
# 2a. Lexicon baseline scorer (deterministic, always available, clearly crude).
# --------------------------------------------------------------------------- #
# Generic price-direction polarity. Positive = supportive of higher price.
_POS = {
    "rebound": 1, "rebounds": 1, "rally": 1, "rallies": 1, "surge": 1, "surges": 1,
    "gain": 1, "gains": 1, "rise": 1, "rises": 1, "rose": 1, "jump": 1, "jumps": 1,
    "climb": 1, "climbs": 1, "soar": 1, "soars": 1, "higher": 1, "boost": 1,
    "boosts": 1, "support": 1, "supported": 1, "strength": 1, "strengthens": 1,
    "demand": 1, "tighten": 1, "tightens": 1, "shortage": 1, "upgrade": 1,
    "bullish": 1, "record": 1, "stabilize": 0.5, "stabilizes": 0.5, "steadies": 0.4,
    "steady": 0.4, "firm": 0.6, "firmer": 0.6, "optimism": 0.6, "recovers": 1,
}
_NEG = {
    "slide": 1, "slides": 1, "fall": 1, "falls": 1, "fell": 1, "drop": 1, "drops": 1,
    "retreat": 1, "retreats": 1, "decline": 1, "declines": 1, "slump": 1, "slumps": 1,
    "plunge": 1, "plunges": 1, "tumble": 1, "tumbles": 1, "weak": 1, "weaker": 1,
    "lower": 1, "pressure": 1, "pressured": 1, "pullback": 1, "pull back": 1,
    "cut": 0.8, "cuts": 0.8, "downgrade": 1, "bearish": 1, "glut": 1, "oversupply": 1,
    "selloff": 1, "sell-off": 1, "loss": 0.8, "losses": 0.8, "drag": 0.8, "drags": 0.8,
    "sinks": 1, "sink": 1, "dips": 0.7, "dip": 0.7, "soft": 0.6, "softer": 0.6,
}
# Macro modifiers whose sign depends on the instrument.
# For HAVEN metals (gold/silver): hawkish/strong-USD/higher-yields = bearish;
#   dovish/risk-off/geopolitics = bullish.
# For OIL: supply disruption/sanctions/OPEC cut = bullish; demand fears/glut = bearish.
# For GBPJPY (carry/risk): hawkish BoE / risk-on = bullish; dovish BoE / risk-off = bearish.
_MACRO = {
    "hawkish": {"gold": -1, "silver": -1, "gbpjpy": +0.6, "wti": -0.4},
    "dovish": {"gold": +1, "silver": +1, "gbpjpy": -0.6, "wti": +0.2},
    "rate hike": {"gold": -0.8, "silver": -0.8, "gbpjpy": +0.6, "wti": -0.3},
    "rate cut": {"gold": +0.8, "silver": +0.8, "gbpjpy": -0.6, "wti": +0.2},
    "strong dollar": {"gold": -0.9, "silver": -0.9, "wti": -0.6, "gbpjpy": -0.3},
    "stronger dollar": {"gold": -0.9, "silver": -0.9, "wti": -0.6, "gbpjpy": -0.3},
    "weak dollar": {"gold": +0.9, "silver": +0.9, "wti": +0.5},
    "safe haven": {"gold": +0.8, "silver": +0.5},
    "geopolitical": {"gold": +0.6, "silver": +0.3, "wti": +0.6},
    "tension": {"gold": +0.4, "wti": +0.6},
    "sanction": {"wti": +0.7}, "sanctions": {"wti": +0.7},
    "disruption": {"wti": +0.8}, "supply": {"wti": +0.2},
    "inventory build": {"wti": -0.7}, "stockpile": {"wti": -0.4},
    "peace": {"wti": -0.6, "gold": -0.3}, "ceasefire": {"wti": -0.7, "gold": -0.4},
    "opec": {"wti": +0.2},
}


def _lexicon_score_one(instrument_key: str, text: str) -> tuple[float, str]:
    t = " " + text.lower() + " "

    # Relevance gate: if the headline doesn't mention this instrument or any of
    # its driver topics, the keyword baseline is too unreliable to take a side.
    cfg = INSTRUMENT_NEWS.get(instrument_key, {})
    aliases = cfg.get("aliases", [])
    macro_terms = [p for p in _MACRO if instrument_key in _MACRO[p]]
    relevant = any(a in t for a in aliases) or any(p in t for p in macro_terms)
    if not relevant:
        return 0.0, "off-topic for this instrument"

    raw, matched = 0.0, []
    for w, wt in _POS.items():
        if re.search(rf"\b{re.escape(w)}\b", t):
            raw += wt; matched.append(f"+{w}")
    for w, wt in _NEG.items():
        if re.search(rf"\b{re.escape(w)}\b", t):
            raw -= wt; matched.append(f"-{w}")
    for phrase, table in _MACRO.items():
        if phrase in t and instrument_key in table:
            raw += table[instrument_key]
            matched.append(f"{'+' if table[instrument_key] > 0 else ''}{phrase}")
    # squash to -1..+1
    score = max(-1.0, min(1.0, raw / 2.5))
    return score, ", ".join(matched[:5])


def _score_lexicon(instrument_key: str, headlines: list) -> list:
    scored = []
    for h in headlines:
        s, why = _lexicon_score_one(instrument_key, f"{h.title}. {h.summary}")
        scored.append(ScoredHeadline(
            title=h.title, source=h.source, url=h.url, published=h.published,
            score=s, rationale=(why or "no strong sentiment terms")))
    return scored


# --------------------------------------------------------------------------- #
# 2b. LLM scorer — Gemini (Vertex, no key on GCP) or Anthropic. Returns per-
#     headline scores + rationale + extracted drivers, as strict JSON.
# --------------------------------------------------------------------------- #
def _llm_prompt(instrument_key: str, display: str, headlines: list) -> str:
    cfg = INSTRUMENT_NEWS.get(instrument_key, {})
    drivers = ", ".join(cfg.get("drivers", []))
    items = "\n".join(f"{i+1}. {h.title}" for i, h in enumerate(headlines))
    return (
        f"You are a markets analyst scoring HEADLINE TONE for {display}.\n"
        f"Key drivers for this instrument: {drivers}.\n\n"
        "For EACH headline, give a sentiment score from -1.0 to +1.0 for the "
        f"instrument's PRICE, where +1 = clearly supportive of a HIGHER {display} "
        "price and -1 = clearly supportive of a LOWER price. Account for context "
        "(e.g. a hawkish Fed / stronger dollar is bearish for gold; a supply "
        "disruption is bullish for oil). Use 0 for irrelevant or neutral.\n\n"
        "Also extract 2-4 short DRIVER phrases summarising what is moving the "
        "narrative right now.\n\n"
        "RULES:\n"
        "- Output STRICT JSON only, no prose, no markdown.\n"
        "- Do NOT output probabilities or a confidence score; this is tone only.\n"
        "- Do NOT give buy/sell advice.\n\n"
        'Schema: {"headlines":[{"i":1,"score":-0.4,"why":"short reason"}],'
        '"drivers":["phrase","phrase"]}\n\n'
        f"Headlines:\n{items}\n\nJSON:"
    )


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    # strip code fences
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:  # noqa: BLE001
                return None
    return None


def _score_gemini(instrument_key, display, headlines):
    """Gemini via google-genai. Uses Vertex (ADC, no key) on GCP if
    GOOGLE_GENAI_USE_VERTEXAI=true, else GEMINI_API_KEY. Returns (scored, drivers)."""
    try:
        from google import genai
    except Exception:  # noqa: BLE001
        return None
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not use_vertex and not api_key:
        return None
    try:
        if use_vertex:
            client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
        else:
            client = genai.Client(api_key=api_key)
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-001")
        prompt = _llm_prompt(instrument_key, display, headlines)
        resp = client.models.generate_content(model=model, contents=prompt)
        data = _extract_json(getattr(resp, "text", "") or "")
        if not data:
            return None
        return _apply_llm_scores(headlines, data)
    except Exception:  # noqa: BLE001
        return None


def _score_anthropic(instrument_key, display, headlines):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        prompt = _llm_prompt(instrument_key, display, headlines)
        msg = client.messages.create(model=model, max_tokens=700,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in msg.content)
        data = _extract_json(text)
        if not data:
            return None
        return _apply_llm_scores(headlines, data)
    except Exception:  # noqa: BLE001
        return None


def _apply_llm_scores(headlines, data) -> tuple:
    by_i = {}
    for row in data.get("headlines", []):
        try:
            by_i[int(row["i"])] = (float(row.get("score", 0.0)),
                                   str(row.get("why", ""))[:140])
        except Exception:  # noqa: BLE001
            continue
    scored = []
    for idx, h in enumerate(headlines, start=1):
        s, why = by_i.get(idx, (0.0, ""))
        s = max(-1.0, min(1.0, s))
        scored.append(ScoredHeadline(
            title=h.title, source=h.source, url=h.url, published=h.published,
            score=s, rationale=why))
    drivers = [str(d)[:60] for d in data.get("drivers", [])][:4]
    return scored, drivers


# --------------------------------------------------------------------------- #
# 3. Public entry point
# --------------------------------------------------------------------------- #
def _label_for(score: float) -> str:
    for lo, hi, lab in SENTIMENT_LABELS:
        if lo <= score < hi:
            return lab
    return "neutral / mixed"


def get_sentiment(instrument_key: str, display_name: str, ticker: str,
                  max_items: int = 10) -> SentimentResult:
    """Fetch headlines and score sentiment for an instrument (Layer 2)."""
    cfg = INSTRUMENT_NEWS.get(instrument_key, {})
    headlines = fetch_headlines(ticker, max_items=max_items)
    as_of = datetime.now(timezone.utc).isoformat()

    if not headlines:
        return SentimentResult(
            instrument_key=instrument_key, headlines=[], aggregate_score=0.0,
            label="no headlines", drivers=cfg.get("drivers", []),
            method="none", method_note="No headlines returned by the news source.",
            n_headlines=0, as_of=as_of,
            notice="No recent headlines available; sentiment unavailable right now.")

    scored = None
    method = "lexicon"
    method_note = ""
    drivers = []

    llm = _score_gemini(instrument_key, display_name, headlines)
    if llm:
        scored, drivers = llm
        method = "gemini"
        method_note = "Scored by Gemini (Vertex AI) with instrument-aware context."
    else:
        llm = _score_anthropic(instrument_key, display_name, headlines)
        if llm:
            scored, drivers = llm
            method = "anthropic"
            method_note = "Scored by Claude with instrument-aware context."

    if scored is None:
        scored = _score_lexicon(instrument_key, headlines)
        method = "lexicon"
        method_note = ("Keyword baseline (no LLM configured). Crude — it matches "
                       "sentiment words and macro phrases; trust it less than the "
                       "LLM method.")
        drivers = cfg.get("drivers", [])

    # Aggregate: emphasise headlines that actually carry sentiment. We average
    # the non-zero scores (off-topic / neutral headlines should not drag the
    # signal toward a false "neutral"). If nothing carries signal, it IS neutral.
    nonzero = [s.score for s in scored if abs(s.score) > 1e-6]
    if nonzero:
        agg = sum(nonzero) / len(nonzero)
    else:
        agg = 0.0
    agg = max(-1.0, min(1.0, agg))

    return SentimentResult(
        instrument_key=instrument_key,
        headlines=scored,
        aggregate_score=agg,
        label=_label_for(agg),
        drivers=drivers or cfg.get("drivers", []),
        method=method,
        method_note=method_note,
        n_headlines=len(scored),
        as_of=as_of,
        notice="",
    )


# --------------------------------------------------------------------------- #
# 4. Combined read — where Layer 1 (price model) and Layer 2 (news) agree/diverge.
#    THIS is the headline output of the reframed app.
# --------------------------------------------------------------------------- #
def combine(price_lean: str, sentiment: SentimentResult) -> dict:
    """price_lean is 'higher' | 'lower' | 'flat' from the model's median vs last.

    Returns a structured agree/diverge verdict. We never collapse the two layers
    into one number; we report alignment honestly.
    """
    s = sentiment.aggregate_score
    news_lean = "higher" if s > 0.15 else ("lower" if s < -0.15 else "flat")

    if price_lean == "flat" or news_lean == "flat":
        status = "partial"
        if price_lean == "flat" and news_lean == "flat":
            verdict = "Both the price model and the news tone are roughly neutral."
        elif price_lean == "flat":
            verdict = (f"The price model is roughly flat while headlines lean "
                       f"{news_lean}. Mild tilt from news only.")
        else:
            verdict = (f"The price model leans {price_lean} while news tone is "
                       f"neutral. Tilt from price history only.")
    elif price_lean == news_lean:
        status = "aligned"
        verdict = (f"Price model and news BOTH lean {price_lean}. The two "
                   f"independent views agree — higher conviction, but both can "
                   f"still be wrong together.")
    else:
        status = "divergent"
        verdict = (f"DIVERGENCE: the price model leans {price_lean} but news tone "
                   f"leans {news_lean}. Treat with caution — the price-only model "
                   f"may be missing what the headlines are pricing in (or vice "
                   f"versa).")

    return {
        "status": status,                 # aligned | divergent | partial
        "price_lean": price_lean,
        "news_lean": news_lean,
        "sentiment_score": round(s, 4),
        "sentiment_label": sentiment.label,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------- #
# Smoke test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tickers = {"silver": "SI=F", "gold": "GC=F", "wti": "CL=F", "gbpjpy": "GBPJPY=X"}
    names = {"silver": "Silver (XAG/USD)", "gold": "Gold (XAU/USD)",
             "wti": "WTI Crude Oil", "gbpjpy": "GBP/JPY"}
    for k, tk in tickers.items():
        r = get_sentiment(k, names[k], tk)
        print(f"\n==== {names[k]} | method={r.method} | n={r.n_headlines} ====")
        print(f"aggregate={r.aggregate_score:+.3f}  -> {r.label}")
        print(f"drivers: {r.drivers}")
        for h in r.headlines[:5]:
            print(f"  {h.score:+.2f}  {h.title[:80]}  [{h.rationale[:40]}]")
        # demo combine
        for lean in ("higher", "lower", "flat"):
            c = combine(lean, r)
            print(f"  price={lean:6} -> {c['status']:9} {c['verdict'][:80]}")
    print("\nDONE")
