"""Canonical symbol normalization for STOM portfolio candidate/panel CSVs.

Korean stock codes are **6-digit zero-padded** strings (the STOM tick DB stores
each symbol as a table whose name is the padded code, e.g. ``000250`` / ``000100``).
When such a code is written to a CSV and re-read with ``pandas.read_csv``, pandas
infers ``int64`` for the column and silently strips the leading zeros — ``000250``
becomes ``250``.  That is internally consistent (every read strips uniformly) but
breaks at boundaries: the dashboard displays ``250``, and a full-universe join
would mis-match the stripped candidate symbol against the DB table name ``000250``.

This module provides the single shared seam every CSV read of candidate/panel
data should use, so the fix lives in one place instead of a ``dtype={...}`` repeated
across six call sites.

Normalization contract
-----------------------
* Read the ``symbol`` column as **string** (never let pandas infer ``int64``).
* If the symbol is **all digits**, left-pad to the canonical 6-digit form via
  ``zfill(6)`` — so ``000250`` round-trips as ``000250`` even after an int-strip,
  and ``250`` is restored to ``000250``.
* If the symbol is **not all digits** (synthetic test fixtures such as ``"A"``),
  leave it unchanged — ``zfill(6)`` on ``"A"`` would corrupt it to ``"00000A"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

# Korean stock codes are 6-digit zero-padded.
KOREAN_SYMBOL_WIDTH: int = 6


def normalize_symbol(value: Any, width: int = KOREAN_SYMBOL_WIDTH) -> str:
    """Return the canonical symbol string for one value.

    All-digit codes are zero-padded to ``width`` (default 6); non-numeric symbols
    (e.g. synthetic ``"A"``) are returned unchanged as a string.  Values that are
    missing (``NaN``/``None``) collapse to an empty string so the caller can drop
    them with the same ``dropna(subset=["symbol"])`` it already uses.
    """

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text == "":
        return ""
    if text.isdigit():
        return text.zfill(int(width))
    return text


def normalize_symbol_series(series: pd.Series, width: int = KOREAN_SYMBOL_WIDTH) -> pd.Series:
    """Vectorized :func:`normalize_symbol` over a pandas ``Series``.

    Coerces to string first (so an already-stripped ``int64`` column becomes the
    text form), then zero-pads only the all-digit entries, leaving non-numeric
    symbols untouched.
    """

    text = series.astype(str).str.strip()
    digit_mask = text.str.fullmatch(r"\d+").fillna(False)
    padded = text.where(~digit_mask, text.str.zfill(int(width)))
    return padded


def read_candidates_csv(
    path: Union[str, Path],
    *,
    symbol_column: str = "symbol",
    width: int = KOREAN_SYMBOL_WIDTH,
    encoding: str = "utf-8-sig",
    **read_csv_kwargs: Any,
) -> pd.DataFrame:
    """Read a candidate/panel CSV with the symbol column normalized.

    The symbol column is forced to ``str`` at read time (``dtype={symbol: str}``)
    so pandas never strips leading zeros, then normalized to the canonical
    6-digit form for all-digit codes.  Any caller-supplied ``dtype`` is merged
    (the symbol entry always wins).  When the file has no symbol column the read
    is a plain ``read_csv`` — no normalization is attempted.
    """

    dtype: Optional[dict] = read_csv_kwargs.pop("dtype", None)
    merged_dtype = dict(dtype) if isinstance(dtype, dict) else None
    if merged_dtype is None:
        merged_dtype = {}
    merged_dtype.setdefault(symbol_column, str)

    frame = pd.read_csv(path, encoding=encoding, dtype=merged_dtype, **read_csv_kwargs)
    if symbol_column in frame.columns:
        frame[symbol_column] = normalize_symbol_series(frame[symbol_column], width=width)
    return frame
