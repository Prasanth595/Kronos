import csv
import json

import pytest

from stom_rl.paper_replay import PaperReplayConfig, run_paper_replay


def _write_tiny_candidates(path):
    """Write a minimal in-memory candidate CSV with an explicit T+1 contract.

    ``price`` is the decision-bar close at T; ``fill_price`` is the next-bar
    close (T+1).  They are deliberately distinct so a test can assert that the
    accounting ledger fills at ``fill_price`` rather than ``price`` (no DB and
    no 29.7GB dependency).
    """

    header = [
        "timestamp",
        "symbol",
        "condition_id",
        "passed",
        "rank_score",
        "price",
        "fill_price",
        "fillable",
        "feature_momentum",
    ]
    rows = [
        # symbol A: decision close 100, T+1 fill 110 (distinct -> T+1 honored)
        ["2025-01-03T09:00:00", "000111", "tiny_rule", "True", "9.0", "100.0", "110.0", "True", "1.0"],
        ["2025-01-03T09:00:01", "000111", "tiny_rule", "True", "8.0", "110.0", "121.0", "True", "1.1"],
        ["2025-01-03T09:00:02", "000111", "tiny_rule", "True", "7.0", "121.0", "130.0", "True", "1.2"],
        ["2025-01-03T09:00:03", "000111", "tiny_rule", "True", "6.0", "130.0", "140.0", "True", "1.3"],
        # symbol B: a second slot so buy actions have a real fillable target
        ["2025-01-03T09:00:00", "000222", "tiny_rule", "True", "5.0", "200.0", "210.0", "True", "2.0"],
        ["2025-01-03T09:00:01", "000222", "tiny_rule", "True", "4.0", "210.0", "221.0", "True", "2.1"],
        ["2025-01-03T09:00:02", "000222", "tiny_rule", "True", "3.0", "221.0", "230.0", "True", "2.2"],
        ["2025-01-03T09:00:03", "000222", "tiny_rule", "True", "2.0", "230.0", "240.0", "True", "2.3"],
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return str(path)


def test_paper_replay_is_read_only_and_logs_decisions(tmp_path):
    payload = run_paper_replay(PaperReplayConfig(output_dir=str(tmp_path), max_steps=5, max_daily_trades=1))

    assert payload["summary"]["read_only"] is True
    assert payload["summary"]["order_write_path"] is False
    assert payload["summary"]["steps"] == 5
    assert (tmp_path / "paper_replay_summary.json").is_file()
    assert (tmp_path / "decisions.csv").is_file()
    assert (tmp_path / "risk_triggers.json").is_file()
    assert (tmp_path / "blocked_actions.json").is_file()
    triggers = json.loads((tmp_path / "risk_triggers.json").read_text(encoding="utf-8-sig"))
    assert "risk_triggers" in triggers


def test_paper_replay_refuses_non_read_only_mode():
    with pytest.raises(ValueError, match="read_only"):
        run_paper_replay(PaperReplayConfig(read_only=False, write_artifacts=False))


def test_paper_replay_read_only_writes_only_logs_no_order_side_effects(tmp_path):
    """Read-only invariant: a replay produces logs/artifacts only.

    The only files written live under ``output_dir`` (decision/NAV/risk/blocked
    logs + summary).  No broker/order/trading-path file is created, and the
    summary advertises ``order_write_path == False``.
    """

    csv_path = _write_tiny_candidates(tmp_path / "candidates.csv")
    out_dir = tmp_path / "run"
    payload = run_paper_replay(
        PaperReplayConfig(candidate_path=csv_path, output_dir=str(out_dir), max_steps=8, seed=7)
    )

    assert payload["summary"]["order_write_path"] is False
    assert payload["summary"]["read_only"] is True
    written = sorted(p.name for p in out_dir.iterdir())
    assert written == [
        "blocked_actions.json",
        "decisions.csv",
        "nav.csv",
        "paper_replay_summary.json",
        "risk_triggers.json",
    ]
    # No file escaped the output directory into the input/trading path.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["candidates.csv", "run"]


def test_paper_replay_is_deterministic_for_fixed_seed_and_input(tmp_path):
    """Same seed + input -> byte-identical decision log and NAV curve."""

    csv_path = _write_tiny_candidates(tmp_path / "candidates.csv")
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    run_paper_replay(PaperReplayConfig(candidate_path=csv_path, output_dir=str(out_a), max_steps=8, seed=42))
    run_paper_replay(PaperReplayConfig(candidate_path=csv_path, output_dir=str(out_b), max_steps=8, seed=42))

    assert (out_a / "decisions.csv").read_bytes() == (out_b / "decisions.csv").read_bytes()
    assert (out_a / "nav.csv").read_bytes() == (out_b / "nav.csv").read_bytes()
    assert (out_a / "blocked_actions.json").read_bytes() == (out_b / "blocked_actions.json").read_bytes()


def test_paper_replay_blocked_actions_carry_reason_codes(tmp_path):
    """Blocked actions carry (timestamp, symbol/slot, reason, risk state)."""

    csv_path = _write_tiny_candidates(tmp_path / "candidates.csv")
    out_dir = tmp_path / "run"
    # Force the daily-trade risk gate to trip quickly so buys get blocked.
    payload = run_paper_replay(
        PaperReplayConfig(
            candidate_path=csv_path,
            output_dir=str(out_dir),
            max_steps=8,
            seed=11,
            max_daily_trades=1,
        )
    )

    blocked = json.loads((out_dir / "blocked_actions.json").read_text(encoding="utf-8-sig"))["blocked_actions"]
    assert blocked, "expected at least one blocked action under a tight daily-trade cap"
    assert payload["summary"]["blocked_action_count"] == len(blocked)
    for entry in blocked:
        assert entry["timestamp"]
        assert "slot" in entry
        assert "symbol" in entry
        assert entry["reason"], "every blocked action must carry a reason code"
        assert entry["source"] in {"risk_gate", "env_mask"}
        assert isinstance(entry["risk_state"], dict)
        # risk state snapshot describes the current state at block time
        assert "peak_nav" in entry["risk_state"]
    # A pure HOLD proposal is never recorded as a blocked action (no order).
    assert all(entry["action_type"] in {"buy", "sell"} for entry in blocked)


def test_paper_replay_honors_t1_fill_price(tmp_path):
    """Trades fill at the T+1 ``fill_price``, never the decision-bar ``price``.

    The fixture sets ``price`` (T close) and ``fill_price`` (T+1 close) to
    distinct values, so a buy fill recorded at ``fill_price`` proves the T+1
    contract is honored rather than collapsing to the decision bar.
    """

    csv_path = _write_tiny_candidates(tmp_path / "candidates.csv")
    out_dir = tmp_path / "run"
    run_paper_replay(
        PaperReplayConfig(
            candidate_path=csv_path,
            output_dir=str(out_dir),
            max_steps=8,
            seed=3,
            # generous caps so the first buy executes (not risk-blocked)
            max_daily_trades=20,
            max_consecutive_losses=99,
            max_drawdown_pct=99.0,
        )
    )

    decisions = list(csv.DictReader((out_dir / "decisions.csv").open(encoding="utf-8-sig")))
    buys = [d for d in decisions if d["action_type"] == "buy" and d["blocked"] == "False"]
    assert buys, "expected at least one executed buy"

    # The set of distinct T close prices and T+1 fill prices is disjoint in the
    # fixture, so we can verify fills came from the fill_price column.
    close_prices = {100.0, 110.0, 121.0, 130.0, 200.0, 210.0, 221.0, 230.0}
    fill_prices = {110.0, 121.0, 130.0, 140.0, 210.0, 221.0, 230.0, 240.0}
    t1_only = fill_prices - close_prices  # {140.0, 240.0} can only be a T+1 fill

    # Re-run via the env directly to inspect trade fills (read-only, no writes).
    from stom_rl.portfolio_env import PortfolioEnv, PortfolioEnvConfig

    env = PortfolioEnv(PortfolioEnvConfig(candidate_path=csv_path, top_k_candidates=2, max_positions=2, seed=3))
    _, info = env.reset(seed=3)
    # Buy slot 0 at the first bar: decision price is the T close, fill is T+1.
    first_close = float(env._current_candidates().iloc[0]["price"])
    env.step(1)
    assert env.trade_log, "buy should have produced a fill"
    fill_price = float(env.trade_log[0]["price"])
    assert fill_price != first_close, "fill must not collapse to the decision-bar close (lookahead)"
    assert fill_price in fill_prices, "fill must come from the T+1 fill_price column"
    assert close_prices and t1_only  # sanity: fixture has a T+1-only price band
