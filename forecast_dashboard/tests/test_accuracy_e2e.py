"""End-to-end accuracy flow test against REAL data.

1. Run a real forecast for gold, but backdate its target dates into the past so
   update_actuals() can fetch real closes and reconcile.
2. Verify accuracy_summary returns real numbers (band hit-rate etc).
This proves the log -> reconcile -> summarize loop works with live yfinance data.
"""
import os
import sys
import tempfile
import pandas as pd
from datetime import datetime, timezone

# Make the project root importable when run from tests/.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Use an isolated DB so we don't pollute the real one.
TMP_DB = os.path.join(tempfile.gettempdir(), "kronos_e2e.db")
os.environ["FORECAST_DB"] = TMP_DB
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)

import forecast_engine as fe
import storage

INST = "gold"

# Pull real history so we can place target dates on actual past trading days.
hist = fe.fetch_ohlcv(INST, lookback_days=120)
past = hist.iloc[-12:-6]  # 6 trading days that already happened
target_dates = [pd.Timestamp(t) for t in past["timestamps"]]
anchor = pd.Timestamp(hist["timestamps"].iloc[-13])
last_close = float(hist["close"].iloc[-13])

# Build a forecast-like dict whose target dates are those past trading days.
# Use a deliberately WIDE band so most actuals fall inside (sanity of hit-rate).
n = len(target_dates)
fake = {
    "instrument_key": INST,
    "ticker_used": hist.attrs["ticker_used"],
    "model_name": "test",
    "generated_at": anchor.isoformat(),
    "last_history_date": anchor.isoformat(),
    "last_close": last_close,
    "pred_len": n,
    "n_samples": 30,
    "used_volume_path": True,
    "T": 1.0, "top_p": 0.9,
    "future_timestamps": [t.isoformat() for t in target_dates],
    "p10": [last_close * 0.90] * n,
    "p25": [last_close * 0.95] * n,
    "median": [last_close] * n,
    "p75": [last_close * 1.05] * n,
    "p90": [last_close * 1.10] * n,
}
run_id = storage.log_forecast(fake, db_path=TMP_DB)
print("logged run_id:", run_id, "with", n, "past target dates")

n_recon = storage.update_actuals(INST, db_path=TMP_DB)
print("reconciled:", n_recon, "points against REAL closes")

summary = storage.accuracy_summary(INST, db_path=TMP_DB, min_points=3)
print("band_hit_rate:", summary["band_hit_rate"])
print("median_abs_error:", summary["median_abs_error"])
print("directional_accuracy:", summary["directional_accuracy"])
print("note:", summary["calibration_note"])

assert n_recon >= 3, "should reconcile several real trading days"
assert summary["band_hit_rate"] is not None
print("\n[OK] end-to-end accuracy flow works with real data.")
