"""Shared portfolio accounting primitives for STOM RL.

The portfolio pages use one source of truth for cash, holdings, NAV, and trade
costs.  The module is intentionally small and deterministic so the single
symbol environment, portfolio environment, risk gate, and paper replay can all
share the same invariants without introducing a broker dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Mapping, Optional


FLOAT_TOLERANCE = 1e-8


@dataclass
class PositionLot:
    """Long-only position state for one symbol."""

    symbol: str
    quantity: float = 0.0
    average_price: float = 0.0

    def market_value(self, price: float) -> float:
        return float(self.quantity) * float(price)

    def to_dict(self, price: Optional[float] = None) -> Dict[str, float | str]:
        payload: Dict[str, float | str] = {
            "symbol": self.symbol,
            "quantity": float(self.quantity),
            "average_price": float(self.average_price),
        }
        if price is not None:
            payload["market_price"] = float(price)
            payload["market_value"] = self.market_value(float(price))
            payload["unrealized_pnl"] = (float(price) - self.average_price) * self.quantity
        return payload


@dataclass(frozen=True)
class TradeFill:
    """Executed trade record with explicit cost/slippage accounting."""

    timestamp: str
    symbol: str
    side: str
    price: float
    quantity: float
    gross_value: float
    cost: float
    cash_after: float
    realized_pnl: float = 0.0

    def to_dict(self) -> Dict[str, float | str]:
        return asdict(self)


@dataclass
class PortfolioAccount:
    """Long-only cash account with explicit NAV invariants.

    Costs are applied exactly once per fill as ``gross_value * cost_pct`` where
    ``cost_pct = (cost_bps + slippage_bps) / 10_000``.  Margin is deliberately
    unsupported; buy orders that would make cash negative are rejected.
    """

    initial_cash: float = 1_000_000.0
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    cash: Optional[float] = None
    positions: Dict[str, PositionLot] = field(default_factory=dict)
    realized_pnl: float = 0.0
    trade_count: int = 0

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.cash is None:
            self.cash = float(self.initial_cash)
        if self.cash < -FLOAT_TOLERANCE:
            raise ValueError("cash cannot be negative")

    @property
    def cost_pct(self) -> float:
        return (float(self.cost_bps) + float(self.slippage_bps)) / 10_000.0

    def clone(self) -> "PortfolioAccount":
        return PortfolioAccount(
            initial_cash=float(self.initial_cash),
            cost_bps=float(self.cost_bps),
            slippage_bps=float(self.slippage_bps),
            cash=float(self.cash or 0.0),
            positions={symbol: PositionLot(pos.symbol, pos.quantity, pos.average_price) for symbol, pos in self.positions.items()},
            realized_pnl=float(self.realized_pnl),
            trade_count=int(self.trade_count),
        )

    def position(self, symbol: str) -> PositionLot:
        return self.positions.get(str(symbol), PositionLot(str(symbol)))

    def holdings_value(self, prices: Mapping[str, float]) -> float:
        value = 0.0
        for symbol, position in self.positions.items():
            if position.quantity <= FLOAT_TOLERANCE:
                continue
            if symbol not in prices:
                raise KeyError(f"Missing mark price for held symbol: {symbol}")
            value += position.market_value(float(prices[symbol]))
        return float(value)

    def nav(self, prices: Mapping[str, float]) -> float:
        return float(self.cash or 0.0) + self.holdings_value(prices)

    def assert_invariants(self, prices: Mapping[str, float]) -> None:
        if (self.cash or 0.0) < -FLOAT_TOLERANCE:
            raise AssertionError(f"cash is negative: {self.cash}")
        for symbol, position in self.positions.items():
            if position.quantity < -FLOAT_TOLERANCE:
                raise AssertionError(f"{symbol} quantity is negative: {position.quantity}")
            if position.quantity > FLOAT_TOLERANCE and position.average_price <= 0:
                raise AssertionError(f"{symbol} average_price must be positive")
        expected_nav = float(self.cash or 0.0) + self.holdings_value(prices)
        actual_nav = self.nav(prices)
        if abs(actual_nav - expected_nav) > FLOAT_TOLERANCE:
            raise AssertionError(f"NAV drift: actual={actual_nav}, expected={expected_nav}")

    def buy(
        self,
        *,
        symbol: str,
        price: float,
        quantity: Optional[float] = None,
        notional: Optional[float] = None,
        timestamp: str = "",
    ) -> TradeFill:
        symbol = str(symbol)
        price = float(price)
        if price <= 0:
            raise ValueError("price must be positive")
        if quantity is None:
            if notional is None:
                raise ValueError("quantity or notional is required")
            quantity = float(notional) / price
        quantity = float(quantity)
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        gross = price * quantity
        cost = gross * self.cost_pct
        cash_needed = gross + cost
        if cash_needed > float(self.cash or 0.0) + FLOAT_TOLERANCE:
            raise ValueError("buy would make cash negative")

        previous = self.positions.get(symbol, PositionLot(symbol))
        new_qty = previous.quantity + quantity
        new_avg = ((previous.quantity * previous.average_price) + gross) / new_qty
        self.positions[symbol] = PositionLot(symbol=symbol, quantity=float(new_qty), average_price=float(new_avg))
        self.cash = float(self.cash or 0.0) - cash_needed
        self.trade_count += 1
        return TradeFill(
            timestamp=timestamp,
            symbol=symbol,
            side="buy",
            price=price,
            quantity=quantity,
            gross_value=gross,
            cost=cost,
            cash_after=float(self.cash),
        )

    def sell(
        self,
        *,
        symbol: str,
        price: float,
        quantity: Optional[float] = None,
        timestamp: str = "",
    ) -> TradeFill:
        symbol = str(symbol)
        price = float(price)
        if price <= 0:
            raise ValueError("price must be positive")
        position = self.positions.get(symbol)
        if position is None or position.quantity <= FLOAT_TOLERANCE:
            raise ValueError(f"no position to sell for {symbol}")
        sell_qty = position.quantity if quantity is None else float(quantity)
        if sell_qty <= 0:
            raise ValueError("quantity must be positive")
        if sell_qty > position.quantity + FLOAT_TOLERANCE:
            raise ValueError("sell quantity exceeds position quantity")

        sell_qty = min(sell_qty, position.quantity)
        gross = price * sell_qty
        cost = gross * self.cost_pct
        realized = (price - position.average_price) * sell_qty - cost
        self.cash = float(self.cash or 0.0) + gross - cost
        remaining = position.quantity - sell_qty
        if remaining <= FLOAT_TOLERANCE:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = PositionLot(symbol=symbol, quantity=float(remaining), average_price=position.average_price)
        self.realized_pnl += realized
        self.trade_count += 1
        return TradeFill(
            timestamp=timestamp,
            symbol=symbol,
            side="sell",
            price=price,
            quantity=sell_qty,
            gross_value=gross,
            cost=cost,
            cash_after=float(self.cash),
            realized_pnl=realized,
        )

    def snapshot(self, prices: Mapping[str, float]) -> Dict[str, object]:
        return {
            "cash": float(self.cash or 0.0),
            "holdings_value": self.holdings_value(prices),
            "nav": self.nav(prices),
            "realized_pnl": float(self.realized_pnl),
            "trade_count": int(self.trade_count),
            "positions": [position.to_dict(prices.get(symbol)) for symbol, position in sorted(self.positions.items())],
        }
