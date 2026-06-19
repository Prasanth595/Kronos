"""Portfolio-level risk gate and blocked-action reason codes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class RiskGateConfig:
    max_drawdown_pct: float = 20.0
    max_consecutive_losses: int = 3
    max_daily_trades: int = 20
    max_position_weight: float = 0.50
    max_positions: int = 5


@dataclass
class RiskState:
    peak_nav: float
    consecutive_losses: int = 0
    daily_trade_count: int = 0
    last_nav: Optional[float] = None


class RiskGate:
    """Checks proposed portfolio actions before execution."""

    def __init__(self, config: Optional[RiskGateConfig] = None) -> None:
        self.config = config or RiskGateConfig()

    def evaluate(
        self,
        *,
        action_type: str,
        nav: float,
        position_count: int,
        proposed_weight: float = 0.0,
        state: RiskState,
    ) -> Dict[str, Any]:
        nav = float(nav)
        state.peak_nav = max(float(state.peak_nav), nav)
        drawdown_pct = 0.0
        if state.peak_nav > 0:
            drawdown_pct = (nav / state.peak_nav - 1.0) * 100.0

        allowed = True
        reason = ""
        if drawdown_pct <= -abs(float(self.config.max_drawdown_pct)):
            allowed = False
            reason = "max_drawdown"
        elif state.consecutive_losses >= int(self.config.max_consecutive_losses):
            allowed = False
            reason = "consecutive_losses"
        elif action_type == "buy" and state.daily_trade_count >= int(self.config.max_daily_trades):
            allowed = False
            reason = "daily_trade_count"
        elif action_type == "buy" and position_count >= int(self.config.max_positions):
            allowed = False
            reason = "max_positions"
        elif action_type == "buy" and proposed_weight > float(self.config.max_position_weight):
            allowed = False
            reason = "max_position_weight"

        return {
            "allowed": allowed,
            "reason": reason,
            "drawdown_pct": drawdown_pct,
            "state": asdict(state),
            "config": asdict(self.config),
        }

    def update_after_step(self, state: RiskState, *, nav_before: float, nav_after: float, traded: bool) -> RiskState:
        state.peak_nav = max(float(state.peak_nav), float(nav_after))
        if float(nav_after) < float(nav_before):
            state.consecutive_losses += 1
        elif float(nav_after) > float(nav_before):
            state.consecutive_losses = 0
        if traded:
            state.daily_trade_count += 1
        state.last_nav = float(nav_after)
        return state


def state_from_info(info: Mapping[str, Any]) -> RiskState:
    nav = float(info.get("nav", 0.0))
    return RiskState(peak_nav=nav, last_nav=nav)
