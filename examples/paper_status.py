"""Resumen legible del paper trader Kronos 4h."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "paper_kronos_trend_4h"


def main() -> int:
    state_path = OUT / "state.json"
    journal_path = OUT / "journal.csv"
    if not state_path.exists():
        print("El paper trader todavía no tiene estado.")
        return 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    journal = pd.read_csv(journal_path) if journal_path.exists() else pd.DataFrame()
    initial = float(state["initial_equity"])
    equity = float(state["equity"])
    active = [name for name, value in state["components"].items() if value]
    print("PAPER TRADING KRONOS · BTCUSDT 4H")
    print(f"Última vela: {state['last_processed_bar']}")
    print(f"Equity virtual: ${equity:,.2f} ({equity / initial - 1:+.2%})")
    control_equity = float(state.get("control_equity", initial))
    print(f"Control sin Kronos: ${control_equity:,.2f} ({control_equity / initial - 1:+.2%})")
    print(f"Aporte Kronos: {equity / control_equity - 1:+.2%}")
    print(f"Drawdown: {equity / float(state['peak_equity']) - 1:.2%}")
    print(f"Exposición: {len(active) * 12.5:.1f}%")
    print(f"Componentes activos: {', '.join(active) if active else 'ninguno'}")
    print(f"Parado: {'SÍ - ' + str(state['halt_reason']) if state['halted'] else 'no'}")
    print(f"Velas registradas: {len(journal)}")
    if len(journal):
        print(f"Último filtro Kronos: {'riesgo permitido' if bool(journal.iloc[-1]['kronos_risk_ok']) else 'riesgo alto'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
