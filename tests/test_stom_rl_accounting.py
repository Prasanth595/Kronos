import pytest

from stom_rl.accounting import PortfolioAccount


def test_portfolio_account_buy_partial_sell_full_sell_invariants():
    account = PortfolioAccount(initial_cash=1_000.0, cost_bps=10.0)

    buy = account.buy(symbol="000001", price=100.0, quantity=5.0, timestamp="t0")
    assert buy.cost == pytest.approx(0.5)
    assert account.cash == pytest.approx(499.5)
    account.assert_invariants({"000001": 110.0})
    assert account.nav({"000001": 110.0}) == pytest.approx(1_049.5)

    partial = account.sell(symbol="000001", price=120.0, quantity=2.0, timestamp="t1")
    assert partial.cost == pytest.approx(0.24)
    assert account.position("000001").quantity == pytest.approx(3.0)
    assert account.position("000001").average_price == pytest.approx(100.0)
    account.assert_invariants({"000001": 120.0})

    account.sell(symbol="000001", price=90.0, timestamp="t2")
    assert account.position("000001").quantity == pytest.approx(0.0)
    account.assert_invariants({})


def test_portfolio_account_rejects_overspend_and_oversell():
    account = PortfolioAccount(initial_cash=100.0, cost_bps=0.0)

    with pytest.raises(ValueError, match="cash"):
        account.buy(symbol="000001", price=101.0, quantity=1.0)

    account.buy(symbol="000001", price=50.0, quantity=1.0)
    with pytest.raises(ValueError, match="exceeds"):
        account.sell(symbol="000001", price=50.0, quantity=2.0)
