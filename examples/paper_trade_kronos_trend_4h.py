"""Paper trader BTCUSDT 4h: ensemble tendencial + filtro de riesgo Kronos.

No contiene integración con exchange privado y nunca envía órdenes reales.
Ejecutar una vez después del cierre de cada vela o usar ``--loop``.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "paper_kronos_trend_4h"
STATE_FILE = OUTPUT / "state.json"
JOURNAL_FILE = OUTPUT / "journal.csv"
LOCK_FILE = OUTPUT / "paper_trader.lock"
HISTORY_FILE = ROOT / "outputs" / "kronos_research_4h_3y" / "ensemble_predictions.csv"
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
COMPONENTS = ((20, 100), (20, 200), (50, 100), (50, 200))
COMPONENT_EXPOSURE = 0.125
MAX_EXPOSURE = 0.50
ONE_SIDE_COST = 0.0012
MAX_DRAWDOWN = 0.20
DAILY_LOSS_LIMIT = 0.04
INITIAL_EQUITY = 10_000.0


def download_closed_bars(limit: int = 500) -> pd.DataFrame:
    response = requests.get(
        BINANCE_URL,
        params={"symbol": "BTCUSDT", "interval": "4h", "limit": limit},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    frame = pd.DataFrame(
        rows,
        columns=["open_time", "open", "high", "low", "close", "volume", "close_time", "amount", "trades", "taker_base", "taker_quote", "ignore"],
    )
    now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    frame = frame[frame["close_time"].astype("int64") < now_ms].copy()
    frame["timestamps"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    bars = frame[["timestamps", "open", "high", "low", "close", "volume", "amount"]].reset_index(drop=True)
    validate_market_bars(bars)
    return bars


def validate_market_bars(bars: pd.DataFrame) -> None:
    required = ["timestamps", "open", "high", "low", "close", "volume", "amount"]
    if len(bars) < 400 or bars[required].isna().any().any():
        raise ValueError("Histórico Binance incompleto o con valores nulos")
    if not bars["timestamps"].is_monotonic_increasing or not bars["timestamps"].is_unique:
        raise ValueError("Timestamps Binance desordenados o duplicados")
    if not (bars["timestamps"].diff().dropna() == pd.Timedelta(hours=4)).all():
        raise ValueError("Histórico Binance con huecos distintos de 4h")
    prices = bars[["open", "high", "low", "close"]]
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Precio Binance no finito o no positivo")
    if not ((bars["high"] >= prices[["open", "close"]].max(axis=1)) & (bars["low"] <= prices[["open", "close"]].min(axis=1))).all():
        raise ValueError("Relación OHLC imposible en datos Binance")
    if (bars[["volume", "amount"]] < 0).any().any():
        raise ValueError("Volumen Binance negativo")


def initial_std_history() -> list[float]:
    if not HISTORY_FILE.exists():
        return []
    values = pd.read_csv(HISTORY_FILE, usecols=["predicted_return_std"])["predicted_return_std"].dropna()
    return [float(x) for x in values.tail(1080)]


def load_state() -> dict[str, object]:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        # Migración compatible desde el primer estado, antes del benchmark.
        state.setdefault("control_equity", float(state["equity"]))
        state.setdefault("control_peak_equity", float(state["peak_equity"]))
        state.setdefault("control_components", {f"ema_{fast}_{slow}": False for fast, slow in COMPONENTS})
        state.setdefault("control_day", state.get("day"))
        state.setdefault("control_day_start_equity", float(state["control_equity"]))
        state.setdefault("control_halted", False)
        state.setdefault("control_halt_reason", None)
        state["schema_version"] = 2
        return state
    return {
        "schema_version": 2,
        "initial_equity": INITIAL_EQUITY,
        "equity": INITIAL_EQUITY,
        "peak_equity": INITIAL_EQUITY,
        "previous_close": None,
        "last_processed_bar": None,
        "components": {f"ema_{fast}_{slow}": False for fast, slow in COMPONENTS},
        "control_equity": INITIAL_EQUITY,
        "control_peak_equity": INITIAL_EQUITY,
        "control_components": {f"ema_{fast}_{slow}": False for fast, slow in COMPONENTS},
        "control_day": None,
        "control_day_start_equity": INITIAL_EQUITY,
        "control_halted": False,
        "control_halt_reason": None,
        "prediction_std_history": initial_std_history(),
        "day": None,
        "day_start_equity": INITIAL_EQUITY,
        "halted": False,
        "halt_reason": None,
    }


def save_state(state: dict[str, object]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATE_FILE)


def predict_ensemble(bars: pd.DataFrame, api_url: str) -> tuple[list[float], float, float]:
    history = bars.tail(400).copy()
    history["timestamps"] = history["timestamps"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    payload = {"history": history.to_dict(orient="records"), "pred_len": 1, "freq": "4h"}
    current_close = float(bars.iloc[-1]["close"])
    base_seed = int(bars.iloc[-1]["timestamps"].timestamp()) % (2**31 - 1)
    predicted_returns: list[float] = []
    for offset in (42, 43, 44):
        payload["seed"] = base_seed + offset
        response = requests.post(api_url, json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()
        if not result or "close" not in result[0]:
            raise ValueError("Respuesta Kronos sin precio close")
        predicted_return = float(result[0]["close"]) / current_close - 1
        if not np.isfinite(predicted_return) or abs(predicted_return) > 0.25:
            raise ValueError(f"Predicción Kronos fuera de límites: {predicted_return}")
        predicted_returns.append(predicted_return)
    return predicted_returns, float(np.mean(predicted_returns)), float(np.std(predicted_returns, ddof=1))


def append_journal(row: dict[str, object]) -> None:
    """Inserta/reemplaza una vela de forma atómica; nunca crea duplicados."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    existing = pd.read_csv(JOURNAL_FILE) if JOURNAL_FILE.exists() else pd.DataFrame()
    if len(existing) and "bar_time" in existing:
        existing = existing[existing["bar_time"].astype(str) != str(row["bar_time"])]
    combined = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    combined["_sort_time"] = pd.to_datetime(combined["bar_time"], utc=True)
    combined = combined.sort_values("_sort_time").drop(columns="_sort_time")
    temporary = JOURNAL_FILE.with_suffix(".csv.tmp")
    combined.to_csv(temporary, index=False)
    temporary.replace(JOURNAL_FILE)


def process_latest_bar(bars: pd.DataFrame, api_url: str) -> str:
    if len(bars) < 400:
        raise RuntimeError("Se necesitan al menos 400 velas cerradas")
    latest = bars.iloc[-1]
    bar_time = latest["timestamps"].isoformat()
    close = float(latest["close"])
    state = load_state()
    if state["last_processed_bar"] == bar_time:
        return f"Sin vela nueva; última procesada: {bar_time}"

    components = {str(k): bool(v) for k, v in dict(state["components"]).items()}
    control_components = {str(k): bool(v) for k, v in dict(state["control_components"]).items()}
    previous_exposure = sum(components.values()) * COMPONENT_EXPOSURE
    previous_control_exposure = sum(control_components.values()) * COMPONENT_EXPOSURE
    equity = float(state["equity"])
    control_equity = float(state["control_equity"])
    equity_before_bar = equity
    control_equity_before_bar = control_equity
    previous_close = state["previous_close"]
    if previous_close is not None:
        equity *= 1 + previous_exposure * (close / float(previous_close) - 1)
        control_equity *= 1 + previous_control_exposure * (close / float(previous_close) - 1)

    # La marca de Binance es la apertura; el PnL se conoce al cierre cuatro horas después.
    day = (latest["timestamps"] + pd.Timedelta(hours=4)).strftime("%Y-%m-%d")
    if state["day"] != day:
        state["day"] = day
        state["day_start_equity"] = equity_before_bar
    if state["control_day"] != day:
        state["control_day"] = day
        state["control_day_start_equity"] = control_equity_before_bar
    day_return = equity / float(state["day_start_equity"]) - 1
    control_day_return = control_equity / float(state["control_day_start_equity"]) - 1

    # Si la inferencia no está disponible no se confirma la vela. El loop la
    # reintentará completa y así no se pierde ni se duplica contabilidad.
    predictions, mean_prediction, prediction_std = predict_ensemble(bars, api_url)

    std_history = [float(x) for x in state.get("prediction_std_history", [])][-1080:]
    risk_threshold = float(np.quantile(std_history, 0.90)) if len(std_history) >= 270 else float("nan")
    kronos_risk_ok = prediction_std <= risk_threshold
    std_history.append(prediction_std)
    state["prediction_std_history"] = std_history[-1080:]

    peak_before = max(float(state["peak_equity"]), equity)
    drawdown = equity / peak_before - 1
    risk_halt = drawdown <= -MAX_DRAWDOWN
    daily_halt = day_return <= -DAILY_LOSS_LIMIT
    control_peak_before = max(float(state["control_peak_equity"]), control_equity)
    control_drawdown_before = control_equity / control_peak_before - 1
    control_risk_halt = control_drawdown_before <= -MAX_DRAWDOWN
    control_daily_halt = control_day_return <= -DAILY_LOSS_LIMIT
    if risk_halt:
        state["halted"] = True
        state["halt_reason"] = f"drawdown {drawdown:.2%}"
    if control_risk_halt:
        state["control_halted"] = True
        state["control_halt_reason"] = f"drawdown {control_drawdown_before:.2%}"

    desired: dict[str, bool] = {}
    desired_control: dict[str, bool] = {}
    for fast, slow in COMPONENTS:
        key = f"ema_{fast}_{slow}"
        fast_value = float(bars["close"].ewm(span=fast, adjust=False).mean().iloc[-1])
        slow_value = float(bars["close"].ewm(span=slow, adjust=False).mean().iloc[-1])
        trend = fast_value > slow_value
        desired_control[key] = trend and not control_daily_halt and not bool(state["control_halted"])
        if components[key]:
            desired[key] = trend and not daily_halt and not bool(state["halted"])
        else:
            desired[key] = trend and kronos_risk_ok and not daily_halt and not bool(state["halted"])
    new_exposure = sum(desired.values()) * COMPONENT_EXPOSURE
    new_control_exposure = sum(desired_control.values()) * COMPONENT_EXPOSURE
    turnover = sum(abs(float(desired[k]) - float(components[k])) for k in components) * COMPONENT_EXPOSURE
    control_turnover = sum(
        abs(float(desired_control[k]) - float(control_components[k])) for k in control_components
    ) * COMPONENT_EXPOSURE
    equity *= 1 - turnover * ONE_SIDE_COST
    control_equity *= 1 - control_turnover * ONE_SIDE_COST
    peak = max(peak_before, equity)
    control_peak = max(float(state["control_peak_equity"]), control_equity)
    drawdown = equity / peak - 1

    state.update(
        {
            "equity": equity,
            "peak_equity": peak,
            "previous_close": close,
            "last_processed_bar": bar_time,
            "components": desired,
            "control_equity": control_equity,
            "control_peak_equity": control_peak,
            "control_components": desired_control,
        }
    )
    journal_row = {
            "bar_time": bar_time,
            "close": close,
            "prediction_1": predictions[0] if len(predictions) > 0 else "",
            "prediction_2": predictions[1] if len(predictions) > 1 else "",
            "prediction_3": predictions[2] if len(predictions) > 2 else "",
            "prediction_mean": mean_prediction,
            "prediction_std": prediction_std,
            "risk_threshold": risk_threshold,
            "kronos_risk_ok": kronos_risk_ok,
            "previous_exposure": previous_exposure,
            "new_exposure": new_exposure,
            "turnover": turnover,
            "control_previous_exposure": previous_control_exposure,
            "control_new_exposure": new_control_exposure,
            "control_turnover": control_turnover,
            "control_equity": control_equity,
            "control_drawdown": control_equity / control_peak - 1,
            "equity": equity,
            "drawdown": drawdown,
            "daily_return": day_return,
            "halted": state["halted"],
            "prediction_error": "",
        }
    # Journal primero: si el proceso cae antes del estado, el reintento reemplaza
    # esta misma vela. El orden inverso podría dejar una vela imposible de recuperar.
    append_journal(journal_row)
    save_state(state)
    return (
        f"Vela {bar_time} | BTC {close:,.2f} | Kronos μ={mean_prediction:+.3%}, "
        f"σ={prediction_std:.3%}, riesgo={'OK' if kronos_risk_ok else 'ALTO/NO DISPONIBLE'} | "
        f"exposición {new_exposure:.1%} | equity ${equity:,.2f} | control ${control_equity:,.2f} | DD {drawdown:.2%}"
    )


def run_once(api_url: str) -> str:
    """Procesa en orden todas las velas cerradas desde la última confirmada."""
    bars = download_closed_bars()
    if len(bars) < 400:
        raise RuntimeError("Se necesitan al menos 400 velas cerradas")
    state = load_state()
    last = state.get("last_processed_bar")
    if last is None:
        return process_latest_bar(bars, api_url)
    last_timestamp = pd.Timestamp(last)
    pending = bars.index[bars["timestamps"] > last_timestamp].tolist()
    if not pending:
        return f"Sin vela nueva; última procesada: {last}"
    if last_timestamp < bars.iloc[0]["timestamps"]:
        raise RuntimeError("La interrupción supera las 500 velas descargadas; se requiere reconstrucción manual")
    messages: list[str] = []
    for index in pending:
        messages.append(process_latest_bar(bars.iloc[: index + 1].copy(), api_url))
    return "\n".join(messages)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Mantener activo y comprobar periódicamente")
    parser.add_argument("--poll-seconds", type=int, default=300)
    args = parser.parse_args()
    api_url = os.environ.get("KRONOS_API_URL", "http://127.0.0.1:7080/predict")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Paper trader ya está ejecutándose; no se inicia una segunda instancia.", flush=True)
            return 2
        while True:
            try:
                print(run_once(api_url), flush=True)
            except Exception as exc:  # El loop debe sobrevivir a fallos temporales de datos.
                print(f"ERROR paper trader: {exc}", flush=True)
                if not args.loop:
                    return 1
            if not args.loop:
                return 0
            time.sleep(max(60, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
