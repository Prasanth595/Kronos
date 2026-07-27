"""Fetch OHLCV candles from Binance and save as Kronos CSV."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

POPULAR_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
]


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int | None = None) -> list:
    rows: list = []
    cursor = start_ms
    while True:
        params: dict = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": cursor,
            "limit": 1000,
        }
        if end_ms is not None:
            params["endTime"] = end_ms

        url = f"{BINANCE_KLINES}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"Binance API error {exc.code}: {body}") from exc

        if not batch:
            break

        rows.extend(batch)
        next_cursor = batch[-1][0] + 1
        if end_ms is not None and next_cursor >= end_ms:
            break
        if len(batch) < 1000:
            break
        cursor = next_cursor

    return rows


def klines_to_dataframe(klines: list) -> pd.DataFrame:
    # Binance kline: [open_time, open, high, low, close, volume, close_time, quote_volume, ...]
    records = []
    for k in klines:
        records.append(
            {
                "timestamps": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "amount": float(k[7]),  # quote asset volume
            }
        )
    return pd.DataFrame(records)


def resolve_time_range(period: str) -> tuple[int, int, str]:
    """Return (start_ms, end_ms, label) for a period key or YYYY-MM-DD day."""
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)

    if period == "today":
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        label = now.date().isoformat()
        return int(start.timestamp() * 1000), end_ms, label

    if period.startswith("last_"):
        days = int(period.split("_", 1)[1])
        start = now - timedelta(days=days)
        label = f"last{days}d"
        return int(start.timestamp() * 1000), end_ms, label

    # Single UTC calendar day YYYY-MM-DD
    day = datetime.strptime(period, "%Y-%m-%d").date()
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000), day.isoformat()


def download_candles(
    symbol: str,
    interval: str = "5m",
    period: str = "last_7",
    out_path: str | Path | None = None,
) -> tuple[pd.DataFrame, Path]:
    """Download candles and save CSV. Returns (dataframe, saved_path)."""
    symbol = symbol.upper().strip()
    if not symbol:
        raise ValueError("Symbol cannot be empty")

    start_ms, end_ms, label = resolve_time_range(period)
    klines = fetch_klines(symbol, interval, start_ms, end_ms)
    if not klines:
        raise ValueError(f"No candles returned for {symbol} ({interval}, {period})")

    df = klines_to_dataframe(klines)
    root = Path(__file__).resolve().parents[1]
    out = Path(out_path) if out_path else root / "data" / f"{symbol}_{interval}_{label}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df, out


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Binance candles to Kronos CSV")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair (default: BTCUSDT)")
    parser.add_argument("--interval", default="5m", help="Candle interval (default: 5m)")
    parser.add_argument(
        "--period",
        default="today",
        help="Period: today | last_3 | last_7 | last_30 | YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--day",
        default=None,
        help="Deprecated alias for a single UTC day (YYYY-MM-DD or 'today')",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: data/<symbol>_<interval>_<period>.csv)",
    )
    args = parser.parse_args()

    period = args.day if args.day else args.period
    print(f"Fetching {args.symbol} {args.interval} for period={period} (UTC)...")
    df, out = download_candles(args.symbol, args.interval, period, args.out)
    print(f"Saved {len(df)} candles -> {out}")
    print(df.head(3).to_string(index=False))
    print("...")
    print(df.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
