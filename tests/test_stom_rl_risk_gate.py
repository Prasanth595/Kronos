from stom_rl.risk_gate import RiskGate, RiskGateConfig, RiskState


def test_risk_gate_blocks_drawdown_position_count_and_daily_trades():
    gate = RiskGate(RiskGateConfig(max_drawdown_pct=5.0, max_daily_trades=1, max_positions=1))
    state = RiskState(peak_nav=100.0, daily_trade_count=1)

    drawdown = gate.evaluate(action_type="buy", nav=94.0, position_count=0, state=state)
    assert drawdown["allowed"] is False
    assert drawdown["reason"] == "max_drawdown"

    state = RiskState(peak_nav=100.0, daily_trade_count=1)
    daily = gate.evaluate(action_type="buy", nav=100.0, position_count=0, state=state)
    assert daily["allowed"] is False
    assert daily["reason"] == "daily_trade_count"

    state = RiskState(peak_nav=100.0, daily_trade_count=0)
    positions = gate.evaluate(action_type="buy", nav=100.0, position_count=1, state=state)
    assert positions["allowed"] is False
    assert positions["reason"] == "max_positions"
