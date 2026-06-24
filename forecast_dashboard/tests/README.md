# Tests / smoke checks

These validate the system end-to-end against the real Kronos model and live data.

| File | What it checks |
|---|---|
| `test_accuracy_e2e.py` | log -> reconcile -> accuracy_summary loop with REAL yfinance closes. Fast (no model load). |
| `test_mcp_server.py` | spawns `mcp_server.py` over stdio, calls all four tools, asserts the honesty framing is present. Loads the model (cached after first run). |

Run from the project root:

```bash
python tests/test_accuracy_e2e.py
python tests/test_mcp_server.py
```

Module-level smoke tests also live in the core files:

```bash
python forecast_engine.py   # forecasts all 4 instruments, prints bands
python storage.py           # logging + reconciliation on a fake forecast
python instruments.py       # prints the instrument config
```
