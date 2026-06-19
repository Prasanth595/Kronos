"""Stage A: PortfolioEnv -> Gymnasium adapter contract + leakage tests.

Three groups:

* **contract** — the wrapped env is a faithful passthrough of ``PortfolioEnv``
  (identical obs/reward for an identical action sequence; ``action_masks()``
  equals ``action_mask()``);
* **check_env** — the adapter passes Gymnasium's ``check_env`` cleanly;
* **adapter leakage canary (V6b)** — the wrapped-env obs/reward at step ``T`` is
  a pure function of bars ``<= T``; appending FUTURE candidate rows does not
  change obs/reward at steps ``<= T``, and ``reset()`` does not surface later
  bars.  This guards the SB3 wrapper specifically (distinct from the env/CSV
  canary in ``tests/test_stom_rl_portfolio_walk_forward.py``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stom_rl.portfolio_env import PortfolioEnv, synthetic_candidates
from stom_rl.portfolio_sb3_adapter import (
    PortfolioSb3GymEnv,
    make_portfolio_sb3_env,
)


def _action_sequence() -> list[int]:
    # hold, buy slot 0, hold, buy slot 1, hold, sell slot 0, hold ...
    return [0, 1, 0, 2, 0, 4, 0, 0]


# --------------------------------------------------------------------------- #
# Group 1: contract — faithful passthrough
# --------------------------------------------------------------------------- #
def test_spaces_match_underlying_env():
    raw = PortfolioEnv(candidates=synthetic_candidates())
    wrapped = PortfolioSb3GymEnv(candidates=synthetic_candidates())
    assert wrapped.action_space.n == raw.action_space.n
    assert wrapped.observation_space.shape == raw.observation_space.shape
    assert wrapped.observation_space.dtype == np.float32


def test_wrapped_obs_reward_equal_raw_env_for_identical_actions():
    raw = PortfolioEnv(candidates=synthetic_candidates())
    wrapped = PortfolioSb3GymEnv(candidates=synthetic_candidates())

    raw_obs, _ = raw.reset(seed=7)
    wrapped_obs, _ = wrapped.reset(seed=7)
    np.testing.assert_array_equal(wrapped_obs, raw_obs)

    for action in _action_sequence():
        r_obs, r_reward, r_term, r_trunc, _ = raw.step(action)
        w_obs, w_reward, w_term, w_trunc, _ = wrapped.step(action)
        np.testing.assert_array_equal(w_obs, r_obs)
        assert w_reward == pytest.approx(r_reward)
        assert w_term == r_term
        assert w_trunc == r_trunc
        if r_term:
            break


def test_action_masks_plural_equals_singular_action_mask():
    raw = PortfolioEnv(candidates=synthetic_candidates())
    wrapped = PortfolioSb3GymEnv(candidates=synthetic_candidates())
    raw.reset(seed=11)
    wrapped.reset(seed=11)

    # At reset and after a buy, the mask must agree element-wise.
    np.testing.assert_array_equal(wrapped.action_masks(), raw.action_mask())
    raw.step(1)
    wrapped.step(1)
    masks = wrapped.action_masks()
    np.testing.assert_array_equal(masks, raw.action_mask())
    assert masks.dtype == np.int8
    assert masks.shape == (wrapped.action_space.n,)


def test_factory_builds_equivalent_env():
    wrapped = make_portfolio_sb3_env(candidates=synthetic_candidates(), seed=3)
    assert isinstance(wrapped, PortfolioSb3GymEnv)
    obs, info = wrapped.reset(seed=3)
    assert obs.shape == wrapped.observation_space.shape
    assert "action_mask" in info


# --------------------------------------------------------------------------- #
# Group 2: Gymnasium check_env passes cleanly
# --------------------------------------------------------------------------- #
def test_check_env_passes():
    from gymnasium.utils.env_checker import check_env

    wrapped = PortfolioSb3GymEnv(candidates=synthetic_candidates())
    # skip_render_check default True; raises on any space/dtype/contract issue.
    check_env(wrapped, skip_render_check=True)


# --------------------------------------------------------------------------- #
# Group 3: adapter leakage canary (V6b)
# --------------------------------------------------------------------------- #
def _early_bars(frame: pd.DataFrame, keep_steps: int) -> pd.DataFrame:
    """Return only the first ``keep_steps`` distinct timestamps' rows."""

    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    keep_ts = sorted(frame["timestamp"].unique())[:keep_steps]
    return frame[frame["timestamp"].isin(keep_ts)].reset_index(drop=True)


def test_adapter_obs_reward_pure_function_of_past_bars():
    """Appending FUTURE candidate bars must not change obs/reward at steps <= T.

    Build a base frame, then a ``+future`` frame that is byte-identical for the
    first ``T`` bars but has extra LATER timestamps appended.  Running the same
    action prefix on both wrapped envs must yield identical obs/reward for every
    step up to ``T`` — i.e. the wrapped obs at step ``t`` depends only on bars
    ``<= t``, never on appended future rows.
    """

    full = synthetic_candidates()
    full["timestamp"] = pd.to_datetime(full["timestamp"])
    distinct_ts = sorted(full["timestamp"].unique())
    cut = 5  # number of leading bars we compare over (well under the 8 total)

    base = _early_bars(full, cut)
    with_future = full  # identical first ``cut`` bars + extra later bars

    env_base = PortfolioSb3GymEnv(candidates=base)
    env_future = PortfolioSb3GymEnv(candidates=with_future)

    obs_base, _ = env_base.reset(seed=21)
    obs_future, _ = env_future.reset(seed=21)
    # reset() must not surface any later-bar data.
    np.testing.assert_array_equal(obs_future, obs_base)

    actions = [0, 1, 0, 2]  # stays within the first ``cut`` bars
    for step_idx, action in enumerate(actions):
        ob_b, rew_b, term_b, _, _ = env_base.step(action)
        ob_f, rew_f, term_f, _, _ = env_future.step(action)
        # The base env terminates at its own horizon; only compare while both
        # envs are still inside the shared past window.
        if term_b:
            break
        np.testing.assert_array_equal(
            ob_f, ob_b, err_msg=f"future bars leaked into obs at step {step_idx}"
        )
        assert rew_f == pytest.approx(rew_b), f"future bars leaked into reward at step {step_idx}"

    assert len(distinct_ts) > cut  # sanity: there really were future bars to leak


def test_adapter_reset_does_not_surface_future_bars():
    """``reset()`` obs equals the obs computed from only the first bar's data."""

    full = synthetic_candidates()
    first_bar_only = _early_bars(full, 1)

    env_full = PortfolioSb3GymEnv(candidates=full)
    env_first = PortfolioSb3GymEnv(candidates=first_bar_only)

    obs_full, _ = env_full.reset(seed=99)
    obs_first, _ = env_first.reset(seed=99)
    np.testing.assert_array_equal(obs_full, obs_first)
