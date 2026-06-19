"""Deterministic opening-window fixtures for STOM RL tests."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd  # noqa: PANDAS_OK - matches existing STOM orderbook test fixtures


OPENING_SECONDS: Final[tuple[int, ...]] = (0, 1, 2, 3, 4, 5)
KOREAN_COLUMNS: Final[tuple[str, ...]] = (
    "symbol",
    "session",
    "index",
    "현재가",
    "체결강도",
    "초당매수금액",
    "초당매도금액",
    "초당매수수량",
    "초당매도수량",
    "초당거래대금",
    "매수총잔량",
    "매도총잔량",
    "매수호가1",
    "매도호가1",
    "매수잔량1",
    "매도잔량1",
)


def _timestamp(session: str, second: int) -> int:
    return int(f"{session}0900{second:02d}")


def opening_orderbook_frame(
    *,
    symbol: str,
    session: str,
    missing_quote: bool = False,
    spread_edge: bool = False,
) -> pd.DataFrame:
    """Return a tiny deterministic STOM-like opening orderbook frame."""

    rows: list[dict[str, str | int | float]] = []
    for offset, second in enumerate(OPENING_SECONDS):
        price = 1000.0 + offset * 3.0
        bid1 = price - 1.0
        ask1 = price + (0.0 if spread_edge and offset == 2 else 1.0)
        bid_qty = 600.0 + offset * 25.0
        ask_qty = 420.0 - min(offset * 10.0, 50.0)
        if missing_quote and offset in {2, 4}:
            bid1 = 0.0
            ask1 = 0.0
            bid_qty = 0.0
            ask_qty = 0.0
        buy_amount = 1_200_000.0 + offset * 150_000.0
        sell_amount = 900_000.0 + offset * 50_000.0
        rows.append(
            {
                "symbol": symbol,
                "session": session,
                "index": _timestamp(session, second),
                "현재가": price,
                "체결강도": 115.0 + offset * 4.0,
                "초당매수금액": buy_amount,
                "초당매도금액": sell_amount,
                "초당매수수량": 100.0 + offset * 5.0,
                "초당매도수량": 80.0 + offset * 2.0,
                "초당거래대금": (buy_amount + sell_amount) / 1_000_000.0,
                "매수총잔량": 1_800.0 + offset * 60.0,
                "매도총잔량": 1_200.0 - offset * 20.0,
                "매수호가1": bid1,
                "매도호가1": ask1,
                "매수잔량1": bid_qty,
                "매도잔량1": ask_qty,
            }
        )
    return pd.DataFrame(rows, columns=list(KOREAN_COLUMNS))


def build_opening_fixture_frames() -> list[pd.DataFrame]:
    """Build chronological multi-session fixtures with preserved stock codes."""

    return [
        opening_orderbook_frame(symbol="000250", session="20250103"),
        opening_orderbook_frame(symbol="005930", session="20250106", spread_edge=True),
        opening_orderbook_frame(symbol="000660", session="20250107", missing_quote=True),
    ]


def quote_coverage_report(frame: pd.DataFrame) -> dict[str, float | int]:
    """Summarize best-quote coverage for a fixture frame."""

    has_quote = (
        frame["매수호가1"].astype(float).gt(0.0)
        & frame["매도호가1"].astype(float).gt(0.0)
        & frame["매수잔량1"].astype(float).gt(0.0)
        & frame["매도잔량1"].astype(float).gt(0.0)
    )
    total_rows = int(len(frame))
    quote_rows = int(has_quote.sum())
    missing_rows = total_rows - quote_rows
    coverage = quote_rows / total_rows if total_rows else 0.0
    return {
        "total_rows": total_rows,
        "quote_rows": quote_rows,
        "missing_quote_rows": missing_rows,
        "quote_coverage": coverage,
    }


def write_opening_fixture_csv(path: Path, frame: pd.DataFrame) -> None:
    """Write fixture data with UTF-8-SIG for Korean column compatibility."""

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
