"""Audita integridad y puerta de capital del journal de paper trading."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "paper_kronos_trend_4h"
ONE_SIDE_COST = 0.0012


def main() -> int:
    state = json.loads((OUT / "state.json").read_text(encoding="utf-8"))
    journal = pd.read_csv(OUT / "journal.csv")
    journal["bar_time"] = pd.to_datetime(journal["bar_time"], utc=True)
    errors: list[str] = []
    if not journal["bar_time"].is_monotonic_increasing:
        errors.append("timestamps desordenados")
    if not journal["bar_time"].is_unique:
        errors.append("velas duplicadas")
    gaps = journal["bar_time"].diff().dropna()
    if len(gaps) and not (gaps == pd.Timedelta(hours=4)).all():
        errors.append("faltan velas de 4h")
    if not np.isfinite(journal[["close", "equity", "drawdown"]].to_numpy()).all():
        errors.append("valores no finitos")
    exposure_units = journal["new_exposure"] / 0.125
    if not (((exposure_units - exposure_units.round()).abs() < 1e-9) & exposure_units.between(0, 4)).all():
        errors.append("exposición fuera de los cuatro componentes")
    if ((~journal["kronos_risk_ok"].astype(bool)) & (journal["new_exposure"] > journal["previous_exposure"] + 1e-12)).any():
        errors.append("entrada realizada con filtro Kronos bloqueado")

    initial = float(state["initial_equity"])
    expected = initial
    previous_close = None
    for row in journal.itertuples(index=False):
        if previous_close is not None:
            expected *= 1 + float(row.previous_exposure) * (float(row.close) / previous_close - 1)
        expected *= 1 - float(row.turnover) * ONE_SIDE_COST
        if not np.isclose(expected, float(row.equity), rtol=1e-10, atol=1e-6):
            errors.append(f"equity incoherente en {row.bar_time}")
            break
        previous_close = float(row.close)
    if "control_equity" in journal:
        expected_control = initial
        previous_close = None
        for row in journal.itertuples(index=False):
            control_value = getattr(row, "control_equity", float("nan"))
            if pd.isna(control_value):
                previous_close = float(row.close)
                continue
            if previous_close is not None:
                expected_control *= 1 + float(row.control_previous_exposure) * (float(row.close) / previous_close - 1)
            expected_control *= 1 - float(row.control_turnover) * ONE_SIDE_COST
            if not np.isclose(expected_control, float(control_value), rtol=1e-10, atol=1e-6):
                errors.append(f"equity del control incoherente en {row.bar_time}")
                break
            previous_close = float(row.close)
    if str(journal.iloc[-1]["bar_time"].isoformat()) != str(pd.Timestamp(state["last_processed_bar"]).isoformat()):
        errors.append("state y journal no coinciden en la última vela")

    starts = ((journal["previous_exposure"] == 0) & (journal["new_exposure"] > 0)).sum()
    completed = ((journal["previous_exposure"] > 0) & (journal["new_exposure"] == 0)).sum()
    elapsed_days = (journal.iloc[-1]["bar_time"] - journal.iloc[0]["bar_time"]).total_seconds() / 86400
    current_return = float(journal.iloc[-1]["equity"] / initial - 1)
    max_drawdown = float(journal["drawdown"].min())
    control_available = "control_equity" in journal and journal["control_equity"].notna().any()
    control_return = None
    kronos_incremental = None
    if control_available:
        control_rows = journal[journal["control_equity"].notna()].copy()
        control_start = float(control_rows.iloc[0]["control_equity"])
        control_end = float(control_rows.iloc[-1]["control_equity"])
        control_return = control_end / control_start - 1
        candidate_same_start = float(control_rows.iloc[0]["equity"])
        candidate_same_return = float(control_rows.iloc[-1]["equity"]) / candidate_same_start - 1
        kronos_incremental = candidate_same_return - control_return
    ready = bool(
        not errors
        and elapsed_days >= 90
        and completed >= 2
        and current_return > 0
        and max_drawdown >= -0.10
        and control_available
        and kronos_incremental is not None
        and kronos_incremental >= 0
        and not bool(state["halted"])
    )
    report = {
        "integrity_ok": not errors,
        "errors": errors,
        "bars": len(journal),
        "elapsed_days": elapsed_days,
        "entries_from_flat": int(starts),
        "completed_cycles": int(completed),
        "return_pct": current_return * 100,
        "max_drawdown_pct": max_drawdown * 100,
        "control_return_pct": None if control_return is None else control_return * 100,
        "kronos_incremental_pct_points": None if kronos_incremental is None else kronos_incremental * 100,
        "capital_review_ready": ready,
        "remaining": {
            "days_to_90": max(0.0, 90 - elapsed_days),
            "cycles_to_2": max(0, 2 - int(completed)),
        },
    }
    (OUT / "audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
