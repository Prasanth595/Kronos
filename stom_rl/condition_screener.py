"""Safe condition screener for portfolio candidate generation.

The screener turns STOM feature rows into a deterministic candidate schema:
``timestamp, symbol, condition_id, passed, rank_score, price, fill_price,
feature...``.  Condition expressions are parsed with ``ast`` and interpreted
from a whitelist; there is no dynamic code execution path.

candidate.price time contract (Page 9, P0 leakage gate — defined once here so
Page 10/11/12 reuse it)
-----------------------------------------------------------------------------
* The decision / feature row is the **bar close at decision time T**.  Column
  ``price`` therefore always carries the close observed *at* ``T`` (point-in-time
  correct: no future value participates in the decision).
* **Fill must occur at the NEXT bar (T+1)**, never at the decision bar.  Column
  ``fill_price`` carries the symbol's next-available-bar price on the panel grid
  (the close at the very next timestamp at which that symbol is observed).
* The **last bar per symbol has no T+1** and therefore ``fill_price`` is ``NaN``;
  such a candidate is *unfillable* (``fillable == False``).  Callers either drop
  or flag these rows — they can never be executed because there is no future bar
  to fill against.

This contract is the blocking guarantee against decision/fill collapse
(look-ahead): ``fill_price`` is strictly drawn from a timestamp *after* the
decision timestamp ``T``.
"""

import argparse
import ast
import json
import operator
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd

from stom_rl.symbol_norm import read_candidates_csv


DEFAULT_ALLOWED_FUNCTIONS: Dict[str, Callable[..., float]] = {
    "abs": abs,
    "max": max,
    "min": min,
    "round": round,
}
SELL_ONLY_VARIABLES = {"holding_qty", "position_qty", "position_weight", "보유수량", "보유비중"}
FORBIDDEN_TOKENS = (
    "__",
    "import",
    "lambda",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "delattr",
    "subprocess",
    "os.",
    "sys.",
)


@dataclass(frozen=True)
class ConditionRule:
    condition_id: str
    expression: str
    rank_expression: str = "rank_score"
    side: str = "buy"


class SafeExpression:
    """Whitelist AST interpreter for numeric and boolean row expressions."""

    _binary_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_ops = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}
    _compare_ops = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
    }

    def __init__(
        self,
        expression: str,
        *,
        allowed_names: Iterable[str],
        allowed_functions: Optional[Mapping[str, Callable[..., float]]] = None,
    ) -> None:
        self.expression = str(expression)
        lowered = self.expression.lower()
        forbidden = [token for token in FORBIDDEN_TOKENS if token in lowered]
        if forbidden:
            raise ValueError(f"Forbidden token(s) in condition expression: {forbidden}")
        self.allowed_names = set(map(str, allowed_names))
        self.allowed_functions = dict(allowed_functions or DEFAULT_ALLOWED_FUNCTIONS)
        self.tree = ast.parse(self.expression, mode="eval")
        self.referenced_names = self._collect_names(self.tree)
        unknown = sorted(
            name
            for name in self.referenced_names
            if name not in self.allowed_names and name not in self.allowed_functions
        )
        if unknown:
            raise ValueError(f"Unknown variable(s) in condition expression: {unknown}")
        self._validate(self.tree)

    def _collect_names(self, node: ast.AST) -> set[str]:
        return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}

    def _validate(self, node: ast.AST) -> None:
        allowed_nodes = (
            ast.Expression,
            ast.BoolOp,
            ast.BinOp,
            ast.UnaryOp,
            ast.Compare,
            ast.Call,
            ast.Name,
            ast.Load,
            ast.Constant,
            ast.And,
            ast.Or,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
            ast.UAdd,
            ast.USub,
            ast.Not,
            ast.Eq,
            ast.NotEq,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,
        )
        for child in ast.walk(node):
            if not isinstance(child, allowed_nodes):
                raise ValueError(f"Disallowed expression node: {type(child).__name__}")
            if isinstance(child, ast.Call):
                if not isinstance(child.func, ast.Name) or child.func.id not in self.allowed_functions:
                    raise ValueError("Only whitelisted function calls are allowed")
                if child.keywords:
                    raise ValueError("Keyword arguments are not allowed in condition expressions")

    def calculate(self, row: Mapping[str, Any]) -> Any:
        return self._calculate_node(self.tree.body, row)

    def _calculate_node(self, node: ast.AST, row: Mapping[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, bool)):
                return node.value
            raise ValueError("Only numeric and boolean constants are allowed")
        if isinstance(node, ast.Name):
            if node.id not in self.allowed_names:
                raise ValueError(f"Unknown variable: {node.id}")
            return row.get(node.id, 0.0)
        if isinstance(node, ast.UnaryOp):
            return self._unary_ops[type(node.op)](self._calculate_node(node.operand, row))
        if isinstance(node, ast.BinOp):
            left = self._calculate_node(node.left, row)
            right = self._calculate_node(node.right, row)
            return self._binary_ops[type(node.op)](left, right)
        if isinstance(node, ast.BoolOp):
            values = [bool(self._calculate_node(value, row)) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = self._calculate_node(node.left, row)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._calculate_node(comparator, row)
                if not self._compare_ops[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            func = self.allowed_functions[node.func.id]
            args = [self._calculate_node(arg, row) for arg in node.args]
            return func(*args)
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def _timestamp_column(frame: pd.DataFrame) -> str:
    for column in ("timestamp", "date", "timestamps", "datetime"):
        if column in frame.columns:
            return column
    raise ValueError("candidate source requires a timestamp/date column")


def _symbol_column(frame: pd.DataFrame) -> str:
    if "symbol" in frame.columns:
        return "symbol"
    if "instrument" in frame.columns:
        return "instrument"
    raise ValueError("candidate source requires a symbol or instrument column")


def _price_column(frame: pd.DataFrame) -> str:
    for column in ("price", "close", "last", "현재가"):
        if column in frame.columns:
            return column
    raise ValueError("candidate source requires price/close column")


_EMPTY_CANDIDATE_COLUMNS = [
    "timestamp",
    "symbol",
    "condition_id",
    "passed",
    "rank_score",
    "price",
    "fill_price",
    "fillable",
]


def screen_frame(
    frame: pd.DataFrame,
    rules: Sequence[ConditionRule],
    *,
    feature_columns: Optional[Sequence[str]] = None,
    strategy_side: str = "buy",
    drop_unfillable: bool = False,
) -> pd.DataFrame:
    """Apply safe rules to a feature frame and return portfolio candidates.

    Output schema: ``timestamp, symbol, condition_id, passed, rank_score, price,
    fill_price, fillable, feature_*``.

    * ``price`` is the decision-bar close at ``T`` (point-in-time correct).
    * ``fill_price`` is that symbol's *next* observed bar price (T+1) on the input
      grid — the T+1 fill contract documented in the module docstring.  The last
      bar per symbol has no T+1 → ``fill_price`` is ``NaN`` and ``fillable`` is
      ``False``.
    * ``rank_score`` default (when no ``rank_score`` column and no explicit
      ``rank_expression``) is computed **per symbol** (groupby) to avoid
      cross-symbol contamination at symbol boundaries; rules that supply an
      explicit ``rank_expression`` are evaluated as-is per row.

    With ``drop_unfillable=True`` the last-bar (unfillable) candidates are
    removed from the result instead of flagged.
    """

    if frame.empty:
        return pd.DataFrame(columns=_EMPTY_CANDIDATE_COLUMNS)
    timestamp_col = _timestamp_column(frame)
    symbol_col = _symbol_column(frame)
    price_col = _price_column(frame)
    numeric = frame.copy()
    numeric[timestamp_col] = pd.to_datetime(numeric[timestamp_col], errors="coerce")
    numeric = (
        numeric.dropna(subset=[timestamp_col])
        .sort_values([symbol_col, timestamp_col], kind="mergesort")
        .reset_index(drop=True)
    )

    # T+1 fill contract: per symbol, fill_price = the NEXT bar's price.  Sorting
    # by (symbol, timestamp) then shifting -1 within each symbol group gives the
    # strictly-later bar; the last bar per symbol shifts to NaN (unfillable).
    price_numeric = pd.to_numeric(numeric[price_col], errors="coerce")
    numeric["fill_price"] = price_numeric.groupby(numeric[symbol_col]).shift(-1)
    numeric["fillable"] = numeric["fill_price"].notna()

    all_names = set(numeric.columns)
    has_rank_column = "rank_score" in all_names
    if not has_rank_column:
        # Per-symbol default rank_score (P1 fix): pct_change within each symbol so
        # symbol A's first row is never a pct_change off symbol B's last row.
        numeric["rank_score"] = (
            price_numeric.groupby(numeric[symbol_col])
            .pct_change(fill_method=None)
            .fillna(0.0)
        )
        all_names.add("rank_score")

    # The screening loop is driven in (timestamp, symbol) order for stable output.
    numeric = numeric.sort_values([timestamp_col, symbol_col], kind="mergesort").reset_index(drop=True)

    reserved = {timestamp_col, symbol_col, "fill_price", "fillable"}
    features = list(feature_columns or [col for col in numeric.columns if col not in reserved])
    rows: List[Dict[str, Any]] = []
    for rule in rules:
        condition = SafeExpression(rule.expression, allowed_names=all_names)
        ranker = SafeExpression(rule.rank_expression, allowed_names=all_names)
        if strategy_side == "buy" and SELL_ONLY_VARIABLES & condition.referenced_names:
            raise ValueError("Buy strategy condition cannot reference sell-only holding variables")
        for _, source_row in numeric.iterrows():
            context = source_row.to_dict()
            passed = bool(condition.calculate(context))
            if not passed:
                continue
            rank_score = float(ranker.calculate(context))
            fill_value = context.get("fill_price")
            fillable = bool(pd.notna(fill_value))
            if drop_unfillable and not fillable:
                continue
            row = {
                "timestamp": pd.Timestamp(context[timestamp_col]).isoformat(),
                "symbol": str(context[symbol_col]),
                "condition_id": rule.condition_id,
                "passed": True,
                "rank_score": rank_score,
                "price": float(context[price_col]),
                "fill_price": float(fill_value) if fillable else float("nan"),
                "fillable": fillable,
            }
            for column in features:
                if column in context and column not in reserved:
                    value = context[column]
                    try:
                        row[f"feature_{column}"] = float(value)
                    except (TypeError, ValueError):
                        row[f"feature_{column}"] = value
            rows.append(row)

    candidates = pd.DataFrame(rows)
    if candidates.empty:
        return pd.DataFrame(columns=_EMPTY_CANDIDATE_COLUMNS)
    return candidates.sort_values(["timestamp", "rank_score", "symbol"], ascending=[True, False, True]).reset_index(drop=True)


def load_rules(path: Path) -> List[ConditionRule]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        raw_rules = payload
    elif isinstance(payload, Mapping):
        raw_rules = payload.get("rules", [])
    else:
        raise ValueError("Rule file must be a list or an object with a 'rules' list")
    return [ConditionRule(**raw) for raw in raw_rules]


def write_candidates(path: Path, candidates: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".jsonl":
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in candidates.to_dict("records")) + "\n",
            encoding="utf-8-sig",
        )
    else:
        candidates.to_csv(path, index=False, encoding="utf-8-sig")


def screen_sqlite_table(
    db_path: Path,
    table: str,
    rules: Sequence[ConditionRule],
    *,
    limit: int = 0,
) -> pd.DataFrame:
    conn = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    try:
        sql = f'SELECT * FROM "{str(table).replace(chr(34), chr(34) + chr(34))}"'
        if limit and limit > 0:
            sql += f" LIMIT {int(limit)}"
        frame = pd.read_sql_query(sql, conn)
    finally:
        conn.close()
    return screen_frame(frame, rules)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate STOM portfolio candidates from safe condition rules.")
    parser.add_argument("--input-csv", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--table", default=None)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    rules = load_rules(Path(args.rules))
    if args.input_csv:
        frame = read_candidates_csv(args.input_csv)
        candidates = screen_frame(frame, rules)
    elif args.db and args.table:
        candidates = screen_sqlite_table(Path(args.db), args.table, rules, limit=args.limit)
    else:
        raise ValueError("Pass either --input-csv or both --db and --table")
    write_candidates(Path(args.output), candidates)
    print(json.dumps({"candidate_count": int(len(candidates)), "output": args.output}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
