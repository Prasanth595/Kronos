"""Stage-B tests: SB3 portfolio trainer + trained_ppo/supervised_ranker wiring.

Most tests use a lightweight STUB model (no SB3 training) so the wiring,
leakage-guard, and masking logic run instantly.  One bounded REAL-train test
proves determinism (V4) within the explicit ``atol=1e-6, rtol=1e-5`` tolerance;
it is kept tiny but still exercises the actual SB3 PPO path.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from stom_rl import portfolio_walk_forward as pwf
from stom_rl.portfolio_env import ACTION_HOLD, PortfolioEnv
from stom_rl.portfolio_sb3_train import (
    MASKABLE_PPO_INVALID_ACTION_TRIGGER,
    _best_valid_action,
    make_trained_policy_fn,
)

warnings.filterwarnings("ignore", category=RuntimeWarning)


# --------------------------------------------------------------------------- #
# Fixtures: tiny holdout candidate frame (no DB dependency) + a stub model.
# --------------------------------------------------------------------------- #
def _holdout_candidates(n_steps: int = 12) -> pd.DataFrame:
    """Two symbols, ``n_steps`` one-second bars, Page-9 T+1 fill contract."""

    base = pd.Timestamp("2025-07-09 09:00:00")
    rows = []
    for symbol, start in (("A", 100.0), ("B", 50.0)):
        series = [start + step for step in range(n_steps)]
        for t, price in enumerate(series):
            fill = series[t + 1] if t + 1 < len(series) else float("nan")
            rows.append(
                {
                    "timestamp": (base + pd.Timedelta(seconds=t)).isoformat(),
                    "symbol": symbol,
                    "condition_id": "holdout_fixture",
                    "passed": True,
                    "rank_score": float((100 - t) if symbol == "A" else (50 - t)),
                    "price": float(price),
                    "fill_price": fill,
                    "fillable": not np.isnan(fill),
                    "feature_momentum": float(t),
                }
            )
    return pd.DataFrame(rows)


class _StubModel:
    """Deterministic stand-in for an SB3 model.

    ``predict`` returns a fixed action (default: buy slot 1) regardless of obs, so
    tests are instant and seed-independent while still exercising the obs-decode +
    masking bridge.  ``always_invalid`` makes it return an out-of-range action to
    prove the masked fallback never executes an invalid action.
    """

    def __init__(self, action: int = 1, *, always_invalid: bool = False) -> None:
        self._action = int(action)
        self._always_invalid = bool(always_invalid)

    def predict(self, observation, deterministic: bool = True):
        observation = np.asarray(observation)
        action = 999 if self._always_invalid else self._action
        return np.asarray(action), None


def _write_csv(frame: pd.DataFrame, path) -> str:
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return str(path)


# --------------------------------------------------------------------------- #
# trained_ppo wiring: factory delivers the model through _fit_policy.
# --------------------------------------------------------------------------- #
def test_trained_ppo_factory_delivers_model_through_fit_policy(tmp_path):
    """A registered trained_ppo factory's PolicyFn runs through the holdout.

    Proves P0-2: ``_fit_policy`` consults ``TRAINED_POLICY_FACTORIES`` and the
    trained branch runs BEFORE the ``del`` (the factory receives train_frame).
    """

    csv = _write_csv(_holdout_candidates(), tmp_path / "cands.csv")
    seen = {}

    def _factory(*, train_frame, config, fold_index):
        # The factory MUST receive a real train_frame (proves it ran before del).
        seen["train_rows"] = int(len(train_frame))
        seen["fold_index"] = int(fold_index)
        return make_trained_policy_fn(_StubModel(action=1))

    pwf.register_trained_policy_factory("trained_ppo", _factory)
    try:
        cfg = pwf.PortfolioWalkForwardConfig(
            candidate_path=csv,
            n_folds=2,
            max_steps_per_fold=8,
            write_artifacts=False,
            baselines=("no_trade", "trained_ppo"),
        )
        payload = pwf.run_portfolio_walk_forward(cfg)
    finally:
        pwf.unregister_trained_policy_factory("trained_ppo")

    policies = {row["policy"] for row in payload["folds"]}
    assert "trained_ppo" in policies
    assert seen["train_rows"] > 0  # factory saw a non-empty TRAIN segment
    # The trained policy actually traded (the stub buys), distinguishing it from
    # no_trade — proving the model handoff reached the eval, not a no-op.
    trained_trades = [row["trade_count"] for row in payload["folds"] if row["policy"] == "trained_ppo"]
    assert any(tc > 0 for tc in trained_trades)


def test_fit_policy_trained_branch_runs_before_del():
    """Directly exercise ``_fit_policy`` for a trained key: it returns the factory's
    PolicyFn (the train_frame is consumed, not deleted, for the trained branch)."""

    frame = _holdout_candidates()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    captured = {}

    def _factory(*, train_frame, config, fold_index):
        captured["len"] = len(train_frame)
        return make_trained_policy_fn(_StubModel(action=1))

    pwf.register_trained_policy_factory("trained_ppo", _factory)
    try:
        cfg = pwf.PortfolioWalkForwardConfig(write_artifacts=False)
        policy_fn = pwf._fit_policy("trained_ppo", frame, cfg, 0)
    finally:
        pwf.unregister_trained_policy_factory("trained_ppo")
    assert callable(policy_fn)
    assert captured["len"] == len(frame)


def test_trained_policy_fn_is_deterministic_for_fixed_model(tmp_path):
    """The obs-decode PolicyFn is deterministic given a fixed (stub) model."""

    csv = _write_csv(_holdout_candidates(), tmp_path / "cands.csv")

    def _factory(*, train_frame, config, fold_index):
        return make_trained_policy_fn(_StubModel(action=1))

    pwf.register_trained_policy_factory("trained_ppo", _factory)
    try:
        cfg = pwf.PortfolioWalkForwardConfig(
            candidate_path=csv, n_folds=2, max_steps_per_fold=8,
            write_artifacts=False, baselines=("trained_ppo",),
        )
        first = pwf.run_portfolio_walk_forward(cfg)
        second = pwf.run_portfolio_walk_forward(cfg)
    finally:
        pwf.unregister_trained_policy_factory("trained_ppo")
    assert first["folds"] == second["folds"]


# --------------------------------------------------------------------------- #
# Masking: the obs-decode PolicyFn never executes an invalid action.
# --------------------------------------------------------------------------- #
def test_best_valid_action_prefers_predicted_when_valid():
    assert _best_valid_action(1, [1, 1, 0, 0]) == 1


def test_best_valid_action_falls_back_when_invalid():
    # predicted=2 is masked off -> first valid non-HOLD (index 1).
    assert _best_valid_action(2, [1, 1, 0, 0]) == 1
    # nothing valid except HOLD -> HOLD.
    assert _best_valid_action(3, [1, 0, 0, 0]) == ACTION_HOLD
    # out-of-range prediction -> fallback.
    assert _best_valid_action(999, [1, 1, 0, 0]) == 1


def test_masked_policy_never_emits_invalid_action(tmp_path):
    """An always-invalid stub model, wrapped, never executes a masked action."""

    frame = _holdout_candidates()
    env = PortfolioEnv(candidates=frame, top_k_candidates=3, max_positions=2)
    _, info = env.reset(seed=1)
    policy_fn = make_trained_policy_fn(_StubModel(always_invalid=True))
    terminated = truncated = False
    steps = 0
    while not (terminated or truncated) and steps < 8:
        mask = list(info["action_mask"])
        action = policy_fn(env, info)
        assert mask[action] == 1, f"masked action {action} executed at step {steps}"
        _, _, terminated, truncated, info = env.step(action)
        steps += 1
    assert env.invalid_actions == []  # zero invalid actions reached the engine


# --------------------------------------------------------------------------- #
# supervised_ranker: TRAIN-fit, holdout-eval, no leakage.
# --------------------------------------------------------------------------- #
def test_parse_baselines_accepts_trained_and_ranker_keys():
    """_parse_baselines accepts trained_ppo + supervised_ranker (no ValueError)."""

    parsed = pwf._parse_baselines("no_trade,equal_weight_candidate,supervised_ranker,trained_ppo")
    assert parsed == ("no_trade", "equal_weight_candidate", "supervised_ranker", "trained_ppo")


def test_parse_baselines_still_rejects_unknown_key():
    """Existing typo-guard is intact for genuinely unknown keys."""

    with pytest.raises(ValueError, match="totally_bogus"):
        pwf._parse_baselines("no_trade,totally_bogus")


def test_existing_default_baselines_unaffected(tmp_path):
    """All six DEFAULT_BASELINES still run unchanged through the holdout."""

    csv = _write_csv(_holdout_candidates(), tmp_path / "cands.csv")
    cfg = pwf.PortfolioWalkForwardConfig(
        candidate_path=csv, n_folds=2, max_steps_per_fold=8, write_artifacts=False
    )
    payload = pwf.run_portfolio_walk_forward(cfg)
    policies = {row["policy"] for row in payload["folds"]}
    assert policies == set(pwf.DEFAULT_BASELINES)


def test_supervised_ranker_fits_on_train_and_runs_on_holdout(tmp_path):
    """supervised_ranker selects candidates on the disjoint holdout (P1-5b)."""

    csv = _write_csv(_holdout_candidates(), tmp_path / "cands.csv")
    cfg = pwf.PortfolioWalkForwardConfig(
        candidate_path=csv, n_folds=2, max_steps_per_fold=8,
        write_artifacts=False, baselines=("no_trade", "equal_weight_candidate", "supervised_ranker"),
    )
    payload = pwf.run_portfolio_walk_forward(cfg)
    ranker_rows = [row for row in payload["folds"] if row["policy"] == "supervised_ranker"]
    assert ranker_rows, "supervised_ranker must appear in the fold report"
    for row in ranker_rows:
        assert row["cost_bps"] == 25.0  # explicit non-zero cost
        assert row["total_cost"] >= 0.0


def test_supervised_ranker_fit_does_not_see_test_segment(tmp_path):
    """Leakage guard: perturbing the TEST tail must not change the fitted ranker.

    Build two frames identical on TRAIN but differing on the latest timestamps
    (which fall in TEST).  Because ``_fit_supervised_ranker`` is handed only the
    train_frame, the fold-0 fit (whose train excludes the perturbed tail) must be
    identical — proving the ranker never peeks at TEST data.
    """

    frame = _holdout_candidates(n_steps=12)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    folds = pwf.build_expanding_window_folds(frame, n_folds=3)
    fold0 = folds[0]
    cfg = pwf.PortfolioWalkForwardConfig(write_artifacts=False)

    train_max = max(pd.Timestamp(ts) for ts in fold0.train_frame["timestamp"].unique())
    perturbed = frame.copy()
    later = perturbed["timestamp"] > train_max
    assert later.any()
    perturbed.loc[later, "feature_momentum"] = perturbed.loc[later, "feature_momentum"] + 1000.0
    perturbed.loc[later, "price"] = perturbed.loc[later, "price"] * 3.0
    perturbed_fold0 = pwf.build_expanding_window_folds(perturbed, n_folds=3)[0]

    # fold0 TRAIN is byte-identical (perturbation was TEST-only).
    pd.testing.assert_frame_equal(
        fold0.train_frame.reset_index(drop=True),
        perturbed_fold0.train_frame.reset_index(drop=True),
    )

    fit_clean = pwf._fit_supervised_ranker(train_frame=fold0.train_frame, config=cfg, fold_index=0)
    fit_perturbed = pwf._fit_supervised_ranker(
        train_frame=perturbed_fold0.train_frame, config=cfg, fold_index=0
    )
    # Same TRAIN => identical fit metadata, regardless of the future TEST tail.
    assert fit_clean.frozen_params == fit_perturbed.frozen_params
    # And the TRAIN-only labels are byte-identical (the fit never saw the tail).
    X_clean, y_clean = pwf._next_bar_return_labels(fold0.train_frame)
    X_pert, y_pert = pwf._next_bar_return_labels(perturbed_fold0.train_frame)
    np.testing.assert_array_equal(X_clean, X_pert)
    np.testing.assert_array_equal(y_clean, y_pert)


def test_supervised_ranker_label_uses_only_train_returns(tmp_path):
    """The next-bar-return label is built from TRAIN rows only (no TEST shift)."""

    frame = _holdout_candidates(n_steps=6)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    X, y = pwf._next_bar_return_labels(frame)
    # Every symbol loses its last bar (no next price) -> rows = (n_steps-1)*2.
    assert X.shape[0] == (6 - 1) * 2
    assert y.shape[0] == X.shape[0]
    assert set(np.unique(y)).issubset({0, 1})


# --------------------------------------------------------------------------- #
# Determinism (V4): bounded REAL SB3 train, reproducible within atol/rtol.
# --------------------------------------------------------------------------- #
def test_invalid_action_trigger_threshold_is_five_percent():
    assert MASKABLE_PPO_INVALID_ACTION_TRIGGER == 0.05


# torch's DLL can fail to initialise inside the pytest process on Windows
# (WinError 1114 / c10.dll), an environment quirk the repo's other SB3 tests
# already sidestep by training in a SUBPROCESS and skipping on that signature
# (see tests/test_stom_rl_sb3_eval.py:61-80).  We follow the same convention so
# the determinism gate exercises a REAL SB3 train without the in-process DLL flake.
_SKIP_MARKERS = (
    "ModuleNotFoundError",
    "DLL load failed",
    "WinError 1114",
    "c10.dll",
    "Error loading",
)


def _run_python(code: str):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, check=False
    )
    combined = result.stderr + result.stdout
    if result.returncode != 0 and any(marker in combined for marker in _SKIP_MARKERS):
        pytest.skip(combined)
    return result


def test_real_ppo_train_is_reproducible_within_tolerance():
    """Two trains, same seed/data => eval metrics agree within atol=1e-6, rtol=1e-5.

    Bounded to a tiny budget; the pins in ``apply_determinism``
    (use_deterministic_algorithms + single-thread + cpu) are what make this pass —
    without them the gate is untestable (V4).  Run in a subprocess to dodge the
    Windows in-process torch DLL flake (skips on that signature, never silently).
    """

    code = (
        "import warnings; warnings.filterwarnings('ignore')\n"
        "from stom_rl.portfolio_sb3_train import PortfolioSb3TrainConfig, assert_reproducible\n"
        "cfg = PortfolioSb3TrainConfig(algorithm='ppo', total_timesteps=64, ppo_n_steps=16,\n"
        "    ppo_batch_size=8, ppo_n_epochs=1, write_artifacts=False)\n"
        "res = assert_reproducible(cfg, atol=1e-6, rtol=1e-5)\n"
        "assert res['reproducible'] is True, res\n"
        "print('DETERMINISM_OK', res['folds_compared'])\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "DETERMINISM_OK" in (result.stdout + result.stderr)


# --------------------------------------------------------------------------- #
# Story A: SB3 training-loop telemetry -> live training dashboard stream.
# --------------------------------------------------------------------------- #
def test_training_event_config_flag_defaults_on():
    """``write_training_events`` is default-on (the "watch it learn" stream)."""

    from stom_rl.portfolio_sb3_train import PortfolioSb3TrainConfig

    assert PortfolioSb3TrainConfig().write_training_events is True
    assert PortfolioSb3TrainConfig(write_training_events=False).write_training_events is False


def test_cli_no_training_events_flag_disables_stream():
    """``--no-training-events`` flips the config flag off without touching writes."""

    from stom_rl.portfolio_sb3_train import _parse_args

    on, _ = _parse_args([])
    off, _ = _parse_args(["--no-training-events"])
    assert on.write_training_events is True
    assert off.write_training_events is False
    # The flag is independent of artifact writing (default-on write_artifacts).
    assert off.write_artifacts is True


def test_real_ppo_train_emits_well_formed_live_events(tmp_path):
    """A tiny REAL ``model.learn`` streams well-formed phase=train live events.

    Asserts (round-tripped via ``read_live_events``):
      * >=1 event with ``phase=='train'`` and ``algorithm=='portfolio_ppo'``;
      * ``global_step`` is monotonic non-decreasing and finite;
      * every ``reward`` is finite (mean episode reward);
      * the dashboard signature (sb3_smoke_summary.json) + rl_live_summary.json
        are written so the run is follow/replay-visible.

    Subprocess + skip-on-DLL convention (see module header) so this exercises a
    REAL SB3 train without the Windows in-process torch DLL flake.
    """

    out_dir = (tmp_path / "train_live").as_posix()
    code = (
        "import warnings, json, math; warnings.filterwarnings('ignore')\n"
        "from pathlib import Path\n"
        "from stom_rl.portfolio_sb3_train import PortfolioSb3TrainConfig, train_and_save, SB3_SMOKE_SIGNATURE_FILE\n"
        "from stom_rl.rl_events import read_live_events\n"
        f"out = Path({out_dir!r})\n"
        "cfg = PortfolioSb3TrainConfig(algorithm='ppo', total_timesteps=96, ppo_n_steps=32,\n"
        "    ppo_batch_size=8, ppo_n_epochs=1, output_dir=str(out))\n"
        "summary = train_and_save(cfg)\n"
        "rows, _ = read_live_events(out / 'rl_live_events.jsonl', limit=500)\n"
        "train_rows = [r for r in rows if r.get('phase') == 'train']\n"
        "assert train_rows, ('no phase=train events', rows)\n"
        "assert all(r.get('algorithm') == 'portfolio_ppo' for r in train_rows), rows\n"
        "steps = [int(r['global_step']) for r in train_rows]\n"
        "assert steps == sorted(steps), ('global_step not monotonic', steps)\n"
        "assert all(math.isfinite(float(r['reward'])) for r in train_rows), rows\n"
        "assert (out / SB3_SMOKE_SIGNATURE_FILE).is_file(), 'missing dashboard signature'\n"
        "assert (out / 'rl_live_summary.json').is_file(), 'missing live summary'\n"
        "assert int(summary['live_events']['event_count']) == len(rows)\n"
        "print('LIVE_EVENTS_OK', len(train_rows), steps[-1])\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "LIVE_EVENTS_OK" in (result.stdout + result.stderr)


def test_training_events_disabled_writes_no_jsonl(tmp_path):
    """With ``write_training_events=False`` no live-event JSONL/signature appears.

    Proves the stream is opt-out and that the default-off path leaves the run dir
    free of the live-event artifacts (so disabling truly disables).
    """

    out_dir = (tmp_path / "train_no_events").as_posix()
    code = (
        "import warnings; warnings.filterwarnings('ignore')\n"
        "from pathlib import Path\n"
        "from stom_rl.portfolio_sb3_train import PortfolioSb3TrainConfig, train_and_save, SB3_SMOKE_SIGNATURE_FILE\n"
        f"out = Path({out_dir!r})\n"
        "cfg = PortfolioSb3TrainConfig(algorithm='ppo', total_timesteps=64, ppo_n_steps=16,\n"
        "    ppo_batch_size=8, ppo_n_epochs=1, output_dir=str(out), write_training_events=False)\n"
        "summary = train_and_save(cfg)\n"
        "assert not (out / 'rl_live_events.jsonl').is_file(), 'jsonl written while disabled'\n"
        "assert not (out / SB3_SMOKE_SIGNATURE_FILE).is_file(), 'signature written while disabled'\n"
        "assert 'live_events' not in summary, summary.keys()\n"
        "print('NO_EVENTS_OK')\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "NO_EVENTS_OK" in (result.stdout + result.stderr)


def test_dashboard_serves_training_events(tmp_path):
    """The trained run is dashboard-visible: /table/events serves phase=train rows.

    Trains into a temp ``rl_runs`` root, points the dashboard's RL_RUN_ROOTS at it,
    and asserts the existing follow/replay route returns the live training stream
    with no new ``/api/*`` surface.
    """

    runs_root = (tmp_path / "rl_runs").as_posix()
    code = (
        "import warnings; warnings.filterwarnings('ignore')\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from stom_rl.portfolio_sb3_train import PortfolioSb3TrainConfig, train_and_save\n"
        f"runs_root = Path({runs_root!r})\n"
        "run_dir = runs_root / 'portfolio_train_dash'\n"
        "cfg = PortfolioSb3TrainConfig(algorithm='ppo', total_timesteps=96, ppo_n_steps=32,\n"
        "    ppo_batch_size=8, ppo_n_epochs=1, output_dir=str(run_dir))\n"
        "train_and_save(cfg)\n"
        "sys.path.insert(0, 'webui')\n"
        "import rl_dashboard as dash\n"
        "dash.RL_RUN_ROOTS = [runs_root]\n"
        "names = [r['name'] for r in dash.list_rl_runs()]\n"
        "assert 'portfolio_train_dash' in names, names\n"
        "tbl = dash.load_rl_table('portfolio_train_dash', 'events', limit=500)\n"
        "assert tbl['row_count'] > 0, tbl\n"
        "assert tbl['source_file'] == 'rl_live_events.jsonl', tbl\n"
        "assert all(r.get('phase') == 'train' for r in tbl['rows']), tbl['rows']\n"
        "print('DASH_OK', tbl['row_count'])\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "DASH_OK" in (result.stdout + result.stderr)
