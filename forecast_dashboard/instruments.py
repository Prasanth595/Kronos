"""instruments.py — configuration for the four traded instruments.

Single source of truth for tickers, data quirks, and the honesty caveats that
MUST be surfaced in every client (dashboard, MCP server, notebook).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Instrument:
    """Static config for a single tradeable instrument.

    Attributes:
        key:                 stable internal id (used in storage + APIs).
        display_name:        human-friendly name shown in the UI.
        primary_ticker:      preferred Yahoo Finance ticker (futures = real volume).
        fallback_ticker:     used if the primary returns no/garbage data.
        has_reliable_volume: True when volume can be trusted; False routes the
                             fetch to the no-volume forecast path when volume is junk.
        confidence_caveat:   short string shown verbatim as a badge in the UI.
        event_sensitive:     True for instruments driven by scheduled headlines
                             the daily-candle model cannot see (e.g. OPEC for WTI).
    """

    key: str
    display_name: str
    primary_ticker: str
    fallback_ticker: Optional[str]
    has_reliable_volume: bool
    confidence_caveat: str
    event_sensitive: bool = False
    tags: tuple = field(default_factory=tuple)


# The four instruments — exactly these, in this order.
INSTRUMENTS: dict[str, Instrument] = {
    "silver": Instrument(
        key="silver",
        display_name="Silver (XAG/USD)",
        primary_ticker="SI=F",
        fallback_ticker="XAGUSD=X",
        has_reliable_volume=True,
        confidence_caveat="Futures volume is real. Model still sees price only.",
        event_sensitive=False,
        tags=("metal",),
    ),
    "gold": Instrument(
        key="gold",
        display_name="Gold (XAU/USD)",
        primary_ticker="GC=F",
        fallback_ticker="XAUUSD=X",
        has_reliable_volume=True,
        confidence_caveat="Futures volume is real. Model still sees price only.",
        event_sensitive=False,
        tags=("metal",),
    ),
    "wti": Instrument(
        key="wti",
        display_name="WTI Crude Oil",
        primary_ticker="CL=F",
        fallback_ticker=None,
        has_reliable_volume=True,
        confidence_caveat="EVENT-SENSITIVE: OPEC / inventory headlines are NOT seen by the model.",
        event_sensitive=True,
        tags=("energy",),
    ),
    "gbpjpy": Instrument(
        key="gbpjpy",
        display_name="GBP/JPY",
        primary_ticker="GBPJPY=X",
        fallback_ticker=None,
        has_reliable_volume=False,
        confidence_caveat="LOW CONFIDENCE: no reliable volume — forecast uses the no-volume path.",
        event_sensitive=True,
        tags=("fx",),
    ),
}

# Stable display order for "all four at a glance" views.
INSTRUMENT_ORDER: list[str] = ["silver", "gold", "wti", "gbpjpy"]


def get_instrument(key: str) -> Instrument:
    """Return the Instrument config for a key, raising a clear error if unknown."""
    try:
        return INSTRUMENTS[key]
    except KeyError as exc:
        valid = ", ".join(INSTRUMENTS)
        raise KeyError(f"Unknown instrument '{key}'. Valid keys: {valid}") from exc


def all_instruments() -> list[Instrument]:
    """Return all instruments in canonical display order."""
    return [INSTRUMENTS[k] for k in INSTRUMENT_ORDER]


if __name__ == "__main__":
    for inst in all_instruments():
        vol = "real-volume" if inst.has_reliable_volume else "NO-VOLUME PATH"
        print(f"{inst.key:8s} {inst.display_name:18s} {inst.primary_ticker:10s} "
              f"[{vol}] -> {inst.confidence_caveat}")
