"""mcp_server.py — MCP server exposing the forecast engine as tools.

A THIN client over forecast_engine + storage (same core, no duplication). Lets the
user ask Claude to run forecasts live instead of opening the dashboard.

Every tool response carries the honesty framing (SCOPE.md §6):
  - the forecast is a DISTRIBUTION (band), never a naked point;
  - the per-instrument confidence caveat is included;
  - "the model did NOT see news / macro events" is always stated;
  - no fabricated confidence/sentiment score is ever returned.

Transport: stdio (the standard for local MCP servers).
Run:  python mcp_server.py
"""

from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from mcp.server.fastmcp import FastMCP

import forecast_engine as fe
import storage
from instruments import all_instruments, get_instrument

mcp = FastMCP("kronos-forecast")

GLOBAL_CAVEAT = (
    "The Kronos model sees PAST DAILY PRICE CANDLES ONLY. It cannot see Fed/BoE/BoJ "
    "decisions, CPI prints, OPEC headlines, or any risk events. This is a forecast "
    "DISTRIBUTION (a band), never a single prediction, and carries no confidence score."
)

DEF_DEVICE = os.environ.get("KRONOS_DEVICE", "cpu")
_predictor = None


def _get_predictor():
    global _predictor
    if _predictor is None:
        _predictor = fe.load_predictor(device=DEF_DEVICE)
    return _predictor


@mcp.tool()
def list_instruments():
    """List the four supported instruments and their honesty caveats. Returns text."""
    out = ["The four instruments (price-only daily forecasting):", ""]
    for inst in all_instruments():
        vol = "real volume" if inst.has_reliable_volume else "NO reliable volume (no-volume path)"
        out.append(f"- {inst.display_name} [{inst.key}] ticker={inst.primary_ticker} "
                   f"({vol})")
        out.append(f"    caveat: {inst.confidence_caveat}")
    out.append("")
    out.append(GLOBAL_CAVEAT)
    return "\n".join(out)


@mcp.tool()
def get_forecast(instrument: str, pred_len: int = 14, n_samples: int = 30):
    """Run a forecast for an instrument and return the band + skew + caveats.

    Args:
        instrument: one of silver | gold | wti | gbpjpy.
        pred_len:   forecast horizon in business days (<= 60 recommended).
        n_samples:  number of independent sample paths forming the distribution.

    Returns structured text including median/p10/p90 per horizon, the skew
    summary, the ticker used, the volume-path flag, and the confidence caveats.
    """
    try:
        inst = get_instrument(instrument)
    except KeyError as exc:
        return f"Error: {exc}"

    res = fe.run_forecast(
        inst.key,
        pred_len=int(pred_len),
        n_samples=int(n_samples),
        device=DEF_DEVICE,
        predictor=_get_predictor(),
    )
    try:
        storage.log_forecast(res)
    except Exception:  # noqa: BLE001 - logging is best-effort here
        pass

    # Structured payload + the human-readable honesty-framed summary.
    payload = {
        "instrument": inst.key,
        "display_name": res.display_name,
        "ticker_used": res.ticker_used,
        "used_volume_path": res.used_volume_path,
        "last_close": round(res.last_close, 6),
        "last_history_date": str(res.last_history_date.date()),
        "pred_len": res.pred_len,
        "n_samples": res.n_samples,
        "horizons": [
            {
                "h": i + 1,
                "date": str(res.future_timestamps[i].date()),
                "p10": round(float(res.p10[i]), 6),
                "median": round(float(res.median[i]), 6),
                "p90": round(float(res.p90[i]), 6),
            }
            for i in range(res.pred_len)
        ],
        "realized_vol_annualized_pct": round(res.realized_vol_annualized * 100, 2),
        "skew_note": res.skew_sentence(),
        "confidence_caveat": res.confidence_caveat,
        "global_caveat": GLOBAL_CAVEAT,
    }
    return res.summary_text() + "\n\nJSON:\n" + json.dumps(payload, indent=2)


@mcp.tool()
def get_accuracy(instrument: str):
    """Return the calibration / accuracy summary for an instrument from storage."""
    try:
        inst = get_instrument(instrument)
    except KeyError as exc:
        return f"Error: {exc}"
    summary = storage.accuracy_summary(inst.key)
    lines = [f"Accuracy so far for {inst.display_name}:"]
    if summary["n_reconciled"] == 0:
        lines.append("  No reconciled forecasts yet. Run get_forecast daily, then "
                     "refresh_actuals once target dates pass.")
    else:
        hr = summary["band_hit_rate"]
        lines.append(f"  Reconciled points: {summary['n_reconciled']}")
        lines.append(f"  Band hit-rate (p10-p90): "
                     f"{hr*100:.0f}% (nominal {summary['band_nominal']*100:.0f}%)")
        if summary["median_abs_error"] is not None:
            lines.append(f"  Median abs error: {summary['median_abs_error']:.4f}")
        if summary["directional_accuracy"] is not None:
            lines.append(f"  Directional accuracy: {summary['directional_accuracy']*100:.0f}%")
        lines.append(f"  Note: {summary['calibration_note']}")
    lines.append("")
    lines.append(GLOBAL_CAVEAT)
    return "\n".join(lines)


@mcp.tool()
def refresh_actuals(instrument: str = ""):
    """Reconcile logged forecasts against realized actuals.

    Args:
        instrument: optional single instrument key; empty = all instruments.
    """
    key = instrument.strip() or None
    if key is not None:
        try:
            get_instrument(key)
        except KeyError as exc:
            return f"Error: {exc}"
    n = storage.update_actuals(key)
    scope = key if key else "all instruments"
    return f"Reconciled {n} forecast point(s) against actuals for {scope}."


if __name__ == "__main__":
    mcp.run()
