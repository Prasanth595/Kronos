"""Deterministic SB3 training for the STOM portfolio env (Stage B).

This is the Stage-B trainer that turns the Stage-A Gymnasium adapter
(:func:`stom_rl.portfolio_sb3_adapter.make_portfolio_sb3_env`) into a *trained*,
deterministic SB3 ``PPO``/``DQN`` policy, then exposes that policy as a
``PolicyFn`` for the ``portfolio_walk_forward._fit_policy`` seam (the
``trained_ppo`` baseline).

REUSED from ``stom_rl.sb3_smoke`` (cited):
    * ``_sb3_imports`` (:79)  -> :func:`_sb3_imports` here (same import shim).
    * ``_torch_runtime`` (:86) -> determinism pins + runtime probe.
    * ``_check_env`` (:111)    -> the ``check_env`` invocation pattern.
    * ``_train_model`` (:130)  -> the PPO/DQN construction + ``model.learn`` loop
      and the bounded ``n_steps``/``batch_size`` clamping.
    * ``_evaluate_model`` (:354) -> the ``model.predict(deterministic=True)`` eval
      pattern (here folded into the masked obs-decode ``PolicyFn``).

NET-NEW here (not in ``sb3_smoke``):
    * Determinism HARDENING: ``torch.use_deterministic_algorithms(True)``,
      ``torch.set_num_threads(1)``, ``device="cpu"``, all RNGs seeded, plus a
      reproducibility assertion within an explicit ``atol=1e-6, rtol=1e-5`` on
      eval metrics (sb3_smoke never asserts byte/metric reproducibility).
    * A *portfolio* obs-decode ``PolicyFn`` (:func:`make_trained_policy_fn`) that
      respects the multi-asset ``action_mask`` by selecting the best *valid*
      action — sb3_smoke's single-symbol eval has no portfolio masking.
    * An eval **invalid-action rate** measurement feeding the MaskablePPO trigger
      (penalty-PPO-first; ``sb3-contrib`` is NOT installed here — only the trigger
      is recorded per the plan's Option-C decision).

Determinism is enforced, not hoped for: SB3+torch is not bit-reproducible by
default, so the pins above are applied at import-of-torch time inside
:func:`apply_determinism`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .portfolio_env import ACTION_HOLD, PortfolioEnv
from .portfolio_sb3_adapter import PortfolioSb3GymEnv, make_portfolio_sb3_env
from .rl_events import RlLiveEventWriter, summarize_live_event_file


# Live-event semantics for the SB3 *training loop* (Story A): the trainer streams
# per-rollout telemetry into the SAME ``rl_live_events.jsonl`` schema the
# deterministic ``portfolio_train`` smoke emits, so the dashboard's realtime
# follow/replay view watches the model learn.  ``algorithm`` is the per-algorithm
# label the dashboard groups by; ``phase`` is always "train" for this stream.
PORTFOLIO_TRAIN_LIVE_ALGORITHM = {"ppo": "portfolio_ppo", "dqn": "portfolio_dqn"}
PORTFOLIO_TRAIN_LIVE_PHASE = "train"
# Dashboard signature file written into the train run dir so the existing
# ``iter_run_dirs``/``_detect_artifact_type`` recognises the directory as a run
# and serves the ``rl_live_events.jsonl`` through ``/table/events``.
SB3_SMOKE_SIGNATURE_FILE = "sb3_smoke_summary.json"


# Stage-B trigger threshold (Section 1 Decision, Option C "penalty-PPO-first"):
# adopt sb3-contrib MaskablePPO ONLY if the eval invalid-action rate exceeds this
# OR training reward fails to beat no_trade across >=2 seeds.  We never install
# sb3-contrib here; we only RECORD whether the trigger fired.
MASKABLE_PPO_INVALID_ACTION_TRIGGER: float = 0.05

DEFAULT_DEEP_RL_TRAIN_OUTPUT_DIR = Path(".omx") / "artifacts" / "deep_rl" / "stageB_train"


@dataclass(frozen=True)
class PortfolioSb3TrainConfig:
    """Bounded, deterministic SB3 training config for the portfolio env."""

    candidate_path: Optional[str] = None
    output_dir: str = str(DEFAULT_DEEP_RL_TRAIN_OUTPUT_DIR)
    algorithm: str = "ppo"  # "ppo" | "dqn"
    total_timesteps: int = 5_000
    top_k_candidates: int = 3
    max_positions: int = 2
    initial_cash: float = 1_000_000.0
    buy_fraction: float = 0.25
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    invalid_action_penalty: float = 0.001
    # Cost-aware reward: must be > 0 for Stage B (the env teaches the policy to
    # trade only when worth the execution cost).
    turnover_penalty_lambda: float = 1.0
    seed: int = 100
    device: str = "cpu"  # pinned for determinism (see apply_determinism)
    ppo_n_steps: int = 256
    ppo_batch_size: int = 64
    ppo_n_epochs: int = 4
    dqn_learning_starts: int = 64
    dqn_buffer_size: int = 4_096
    dqn_batch_size: int = 64
    max_eval_steps: int = 64
    write_artifacts: bool = True
    # Story A: stream per-rollout training telemetry into ``rl_live_events.jsonl``
    # so the dashboard can watch the model learn in real time.  Default-on, but
    # write-only (a pure side-effect): the callback never touches the env, RNG, or
    # the gradient step, so determinism (V4) is preserved.  Events are only written
    # when this flag is on AND ``write_artifacts`` yields a real output path.
    write_training_events: bool = True


# --------------------------------------------------------------------------- #
# REUSE: sb3_smoke import shim + runtime probe.
# --------------------------------------------------------------------------- #
def _sb3_imports():
    """Mirror ``sb3_smoke._sb3_imports`` (:79): lazy SB3 import shim."""

    from stable_baselines3 import DQN, PPO
    from stable_baselines3.common.env_checker import check_env

    return DQN, PPO, check_env


def apply_determinism(seed: int, *, device: str = "cpu") -> Dict[str, Any]:
    """Pin every RNG + torch flag so the same seed reproduces eval metrics.

    NET-NEW vs sb3_smoke (which never pins these).  Applies, in order:
      * ``random.seed`` / ``np.random.seed`` / ``torch.manual_seed``.
      * ``torch.use_deterministic_algorithms(True)`` (raises on nondeterministic
        kernels rather than silently diverging).
      * ``torch.set_num_threads(1)`` (multi-thread reductions are nondeterministic).
      * ``device="cpu"`` for the determinism rerun (CUDA is not bit-reproducible).

    Returns the runtime probe (mirrors ``sb3_smoke._torch_runtime`` :86) plus the
    pins applied, for evidence logging.
    """

    import random as _random

    import torch

    _random.seed(int(seed))
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():  # pragma: no cover - CPU CI has no CUDA
        torch.cuda.manual_seed_all(int(seed))
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    return {
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "device_pinned": device,
        "use_deterministic_algorithms": True,
        "num_threads": 1,
        "seed": int(seed),
    }


def _bounded(value: int, *, lo: int, hi: int) -> int:
    return max(lo, min(int(value), hi))


def _make_training_callback(
    algorithm: str,
    *,
    event_writer: RlLiveEventWriter,
) -> Any:
    """Build an SB3 ``BaseCallback`` that streams per-rollout training telemetry.

    Story A (NET-NEW): ``model.learn`` runs silently by default.  This callback
    reads the rollout stats SB3 already maintains and appends one ``RlLiveEvent``
    per rollout (and a final flush at training end) so the dashboard's realtime
    follow/replay view watches the model learn — the "watch it learn" experience.

    Stats emitted per event:
      * ``global_step`` = ``self.num_timesteps`` (monotonic across rollouts).
      * ``reward``      = mean episode reward over ``ep_info_buffer`` (the rolling
        window SB3 logs as ``rollout/ep_rew_mean``); falls back to the latest
        logged value, then 0.0 if no episode has finished yet.
      * ``loss``        = the most recent ``train/loss`` (PPO) /
        ``train/loss``-equivalent from ``logger.name_to_value`` if the optimiser
        has stepped, else ``None`` (first rollout hasn't trained yet).
      * ``equity``      = OMITTED — no cheap mid-train NAV is available without a
        full eval rollout, which would perturb determinism; left ``None``.
      * ``info``        = ``{timesteps, iterations, ep_count}`` for context.

    The callback is WRITE-ONLY: it never reads/writes the env, RNG, or gradient,
    so a fixed seed still reproduces eval metrics (determinism V4 preserved).
    """

    from stable_baselines3.common.callbacks import BaseCallback

    live_algorithm = PORTFOLIO_TRAIN_LIVE_ALGORITHM.get(
        algorithm.lower(), f"portfolio_{algorithm.lower()}"
    )

    class RlLiveEventTrainingCallback(BaseCallback):
        """Append-only RL live-event emitter driven by SB3 rollout hooks."""

        def __init__(self) -> None:
            super().__init__(verbose=0)
            self._iterations = 0

        def _mean_episode_reward(self) -> Optional[float]:
            buffer = getattr(self.model, "ep_info_buffer", None)
            if buffer:
                rewards = [ep.get("r") for ep in buffer if ep.get("r") is not None]
                if rewards:
                    return float(np.mean(rewards))
            logged = self.logger.name_to_value.get("rollout/ep_rew_mean") if self.logger else None
            return float(logged) if logged is not None else None

        def _latest_loss(self) -> Optional[float]:
            if not self.logger:
                return None
            values = self.logger.name_to_value
            for key in ("train/loss", "train/value_loss", "train/policy_gradient_loss"):
                value = values.get(key)
                if value is not None:
                    try:
                        candidate = float(value)
                    except (TypeError, ValueError):
                        continue
                    if np.isfinite(candidate):
                        return candidate
            return None

        def _ep_count(self) -> int:
            buffer = getattr(self.model, "ep_info_buffer", None)
            return int(len(buffer)) if buffer else 0

        def _emit(self) -> None:
            reward = self._mean_episode_reward()
            event_writer.write_step(
                algorithm=live_algorithm,
                phase=PORTFOLIO_TRAIN_LIVE_PHASE,
                global_step=int(self.num_timesteps),
                reward=reward if reward is not None else 0.0,
                loss=self._latest_loss(),
                source="portfolio_sb3_train",
                info={
                    "timesteps": int(self.num_timesteps),
                    "iterations": int(self._iterations),
                    "ep_count": self._ep_count(),
                },
            )

        def _on_step(self) -> bool:  # noqa: D401 - SB3 hook
            return True

        def _on_rollout_end(self) -> None:  # noqa: D401 - SB3 hook
            self._iterations += 1
            self._emit()

        def _on_training_end(self) -> None:  # noqa: D401 - SB3 hook
            # Final flush so short runs (no completed rollout boundary) still
            # produce at least one terminal event carrying the last stats.
            self._emit()

    return RlLiveEventTrainingCallback()


def _make_train_env(config: PortfolioSb3TrainConfig) -> PortfolioSb3GymEnv:
    """Build the Stage-A Gym env for training (cost-aware reward via λ>0)."""

    return make_portfolio_sb3_env(
        candidate_path=config.candidate_path,
        top_k_candidates=config.top_k_candidates,
        max_positions=config.max_positions,
        initial_cash=config.initial_cash,
        buy_fraction=config.buy_fraction,
        cost_bps=config.cost_bps,
        slippage_bps=config.slippage_bps,
        invalid_action_penalty=config.invalid_action_penalty,
        turnover_penalty_lambda=config.turnover_penalty_lambda,
        seed=config.seed,
    )


def check_train_env(config: PortfolioSb3TrainConfig) -> Dict[str, Any]:
    """REUSE: sb3_smoke ``_check_env`` (:111) pattern on the portfolio adapter."""

    _, _, check_env = _sb3_imports()
    env = _make_train_env(config)
    try:
        check_env(env, warn=True, skip_render_check=True)
        return {
            "passed": True,
            "observation_space": str(env.observation_space),
            "action_space": str(env.action_space),
        }
    finally:
        env.close()


def train_portfolio_model(
    config: PortfolioSb3TrainConfig,
    *,
    live_events_path: Optional[Path] = None,
) -> Tuple[Any, Dict[str, Any]]:
    """Train a deterministic SB3 PPO/DQN model on the Stage-A env.

    REUSE: the PPO/DQN construction + bounded ``n_steps``/``batch_size`` clamping
    and the ``model.learn`` loop mirror ``sb3_smoke._train_model`` (:130).
    NET-NEW: determinism pins applied BEFORE model construction; ``device`` pinned.

    Story A: when ``live_events_path`` is given AND ``config.write_training_events``
    is on, a write-only ``RlLiveEventTrainingCallback`` streams per-rollout
    telemetry into ``live_events_path`` during ``model.learn``.  The callback is a
    pure side-effect (no env/RNG/gradient interaction), so determinism (V4) holds.
    Passing no path (the default, used by ``assert_reproducible``) emits nothing.
    """

    runtime = apply_determinism(config.seed, device=config.device)
    DQN, PPO, _ = _sb3_imports()
    env = _make_train_env(config)
    policy_kwargs = {"net_arch": [64, 32]}
    algorithm = config.algorithm.lower()
    try:
        if algorithm == "dqn":
            learning_starts = _bounded(
                config.dqn_learning_starts, lo=1, hi=max(1, config.total_timesteps // 4)
            )
            model = DQN(
                "MlpPolicy",
                env,
                seed=config.seed,
                device=config.device,
                verbose=0,
                learning_starts=learning_starts,
                buffer_size=max(int(config.dqn_buffer_size), int(config.total_timesteps), 64),
                batch_size=_bounded(config.dqn_batch_size, lo=2, hi=max(2, config.total_timesteps)),
                train_freq=4,
                gradient_steps=1,
                target_update_interval=64,
                exploration_fraction=0.4,
                exploration_final_eps=0.05,
                policy_kwargs=policy_kwargs,
            )
        elif algorithm == "ppo":
            n_steps = _bounded(config.ppo_n_steps, lo=8, hi=max(8, config.total_timesteps))
            model = PPO(
                "MlpPolicy",
                env,
                seed=config.seed,
                device=config.device,
                verbose=0,
                n_steps=n_steps,
                batch_size=_bounded(config.ppo_batch_size, lo=2, hi=n_steps),
                n_epochs=max(1, int(config.ppo_n_epochs)),
                policy_kwargs=policy_kwargs,
            )
        else:
            raise ValueError(f"Unknown algorithm: {config.algorithm!r}; expected 'ppo' or 'dqn'.")

        callback = None
        if config.write_training_events and live_events_path is not None:
            event_writer = RlLiveEventWriter(live_events_path, run_id=Path(live_events_path).parent.name)
            event_writer.reset()
            callback = _make_training_callback(algorithm, event_writer=event_writer)

        model.learn(
            total_timesteps=int(config.total_timesteps),
            progress_bar=False,
            callback=callback,
        )
        return model, runtime
    finally:
        env.close()


def _predict_action(model: Any, observation: np.ndarray) -> int:
    """REUSE: sb3_smoke ``model.predict(deterministic=True)`` (:354) pattern."""

    action, _ = model.predict(observation, deterministic=True)
    return int(np.asarray(action).item())


def _best_valid_action(predicted: int, mask: Sequence[int]) -> int:
    """Pick the model's action if valid, else the best valid fallback.

    NET-NEW (no sb3_smoke analog): the portfolio env masks invalid actions, so a
    plain (non-Maskable) PPO/DQN can emit a masked action.  Penalty-PPO learns to
    avoid them via ``invalid_action_penalty``, but at eval we still must NOT
    execute an invalid action.  Fallback order is deterministic: prefer the
    predicted action, else the lowest-index valid non-HOLD action, else HOLD.
    """

    if 0 <= predicted < len(mask) and mask[predicted]:
        return predicted
    for action in range(1, len(mask)):
        if mask[action]:
            return action
    return ACTION_HOLD


def make_trained_policy_fn(model: Any) -> Callable[[PortfolioEnv, Mapping[str, Any]], int]:
    """Wrap a trained SB3 model as a ``portfolio_walk_forward.PolicyFn``.

    The returned closure decodes the *current* env observation, runs the model
    deterministically, and maps the prediction onto the best *valid* action via
    the per-step ``action_mask`` from ``info``.  This is the obs-decode bridge the
    ``_fit_policy`` ``trained_ppo`` seam consumes (NET-NEW).
    """

    def _policy(env: PortfolioEnv, info: Mapping[str, Any]) -> int:
        observation = env._observation()  # noqa: SLF001 - read-only obs snapshot
        predicted = _predict_action(model, observation)
        mask = list(info["action_mask"])
        return _best_valid_action(predicted, mask)

    return _policy


def measure_invalid_action_rate(
    model: Any,
    config: PortfolioSb3TrainConfig,
    *,
    use_masked_policy: bool = False,
) -> Dict[str, Any]:
    """Run a bounded deterministic eval and measure the invalid-action rate.

    ``use_masked_policy=False`` measures the RAW model (no fallback) so the rate
    reflects how often the *unmasked* policy would have chosen an invalid action
    — the quantity the MaskablePPO trigger keys on.  ``use_masked_policy=True``
    confirms the masked obs-decode ``PolicyFn`` emits zero invalid actions.
    """

    env = make_portfolio_sb3_env(
        candidate_path=config.candidate_path,
        top_k_candidates=config.top_k_candidates,
        max_positions=config.max_positions,
        initial_cash=config.initial_cash,
        buy_fraction=config.buy_fraction,
        cost_bps=config.cost_bps,
        slippage_bps=config.slippage_bps,
        invalid_action_penalty=config.invalid_action_penalty,
        turnover_penalty_lambda=config.turnover_penalty_lambda,
        seed=config.seed,
    )
    raw_env = env.raw_env
    observation, info = env.reset(seed=config.seed)
    steps = 0
    invalid = 0
    try:
        terminated = False
        truncated = False
        while not (terminated or truncated):
            if steps >= int(config.max_eval_steps):
                break
            mask = list(info["action_mask"])
            predicted = _predict_action(model, observation)
            action = _best_valid_action(predicted, mask) if use_masked_policy else predicted
            if not (0 <= action < len(mask)) or not mask[action]:
                invalid += 1
            observation, _reward, terminated, truncated, info = env.step(int(action))
            steps += 1
    finally:
        env.close()
    rate = float(invalid) / float(steps) if steps else 0.0
    return {
        "steps": steps,
        "invalid_action_count": invalid,
        "invalid_action_rate": rate,
        "engine_invalid_action_count": int(raw_env.invalid_actions and len(raw_env.invalid_actions) or 0),
        "use_masked_policy": bool(use_masked_policy),
        "trigger_threshold": MASKABLE_PPO_INVALID_ACTION_TRIGGER,
        "maskable_ppo_trigger_fired": bool(rate > MASKABLE_PPO_INVALID_ACTION_TRIGGER),
    }


def train_and_save(config: PortfolioSb3TrainConfig) -> Dict[str, Any]:
    """Train, save the model, measure invalid-action rate; return a summary.

    Story A: when ``write_artifacts`` AND ``write_training_events`` are on, the
    train run dir gains an ``rl_live_events.jsonl`` (the per-rollout telemetry
    stream), an ``rl_live_summary.json`` rollup, and an ``sb3_smoke_summary.json``
    signature so the existing dashboard recognises the directory as a run and
    serves the live events through ``/table/events`` (follow/replay).
    """

    check_result = check_train_env(config)

    output_dir = Path(config.output_dir)
    emit_events = bool(config.write_artifacts and config.write_training_events)
    live_events_path = output_dir / "rl_live_events.jsonl"
    if emit_events:
        output_dir.mkdir(parents=True, exist_ok=True)

    model, runtime = train_portfolio_model(
        config, live_events_path=live_events_path if emit_events else None
    )
    raw_rate = measure_invalid_action_rate(model, config, use_masked_policy=False)
    masked_rate = measure_invalid_action_rate(model, config, use_masked_policy=True)

    model_path: Optional[str] = None
    if config.write_artifacts:
        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = str(output_dir / f"portfolio_{config.algorithm}_model.zip")
        model.save(model_path)

    live_summary: Optional[Dict[str, Any]] = None
    if emit_events and live_events_path.is_file():
        live_summary = summarize_live_event_file(live_events_path)

    summary: Dict[str, Any] = {
        "mode": "stom_rl_portfolio_sb3_train",
        "config": asdict(config),
        "runtime": runtime,
        "check_env": check_result,
        "raw_invalid_action": raw_rate,
        "masked_invalid_action": masked_rate,
        "maskable_ppo_trigger": {
            "threshold": MASKABLE_PPO_INVALID_ACTION_TRIGGER,
            "raw_rate": raw_rate["invalid_action_rate"],
            "fired_on_rate": bool(raw_rate["maskable_ppo_trigger_fired"]),
            "recommendation": (
                "ESCALATE: record sb3-contrib MaskablePPO recommendation "
                "(NOT installed in Stage B)"
                if raw_rate["maskable_ppo_trigger_fired"]
                else "no escalation: penalty-PPO invalid-action rate within budget"
            ),
        },
        "model_path": model_path,
    }
    if live_summary is not None:
        summary["live_events"] = live_summary
    if config.write_artifacts:
        (output_dir / "portfolio_sb3_train_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig"
        )
    if live_summary is not None:
        _write_train_run_signature(output_dir, config=config, live_summary=live_summary)
        (output_dir / "rl_live_summary.json").write_text(
            json.dumps(live_summary, ensure_ascii=False, indent=2), encoding="utf-8-sig"
        )
    return summary


def _write_train_run_signature(
    output_dir: Path,
    *,
    config: PortfolioSb3TrainConfig,
    live_summary: Mapping[str, Any],
) -> None:
    """Write the dashboard signature so the train run is follow/replay-visible.

    The dashboard's ``_detect_artifact_type`` recognises a run by a signature
    file; ``sb3_smoke_summary.json`` is one of them and its ``live_events`` block
    is read by ``load_rl_run``.  Writing it here makes the SB3 *training* stream
    appear in the same realtime view the deterministic smoke run uses — without a
    separate publish step or any new ``/api/*`` route.
    """

    live_algorithm = PORTFOLIO_TRAIN_LIVE_ALGORITHM.get(
        config.algorithm.lower(), f"portfolio_{config.algorithm.lower()}"
    )
    signature = {
        "mode": "stom_rl_portfolio_sb3_train",
        "run_name": output_dir.name,
        "config": asdict(config),
        "summary": {
            "algorithm": config.algorithm,
            "best_model": live_algorithm,
            "total_timesteps": int(config.total_timesteps),
            "live_event_count": int(live_summary.get("event_count", 0)),
            "feature_columns": [],
        },
        "models": [
            {
                "model": live_algorithm,
                "algorithm": config.algorithm,
                "total_timesteps": int(config.total_timesteps),
            }
        ],
        "live_events": dict(live_summary),
    }
    (output_dir / SB3_SMOKE_SIGNATURE_FILE).write_text(
        json.dumps(signature, ensure_ascii=False, indent=2), encoding="utf-8-sig"
    )


def load_trained_model(model_path: str, *, algorithm: str = "ppo") -> Any:
    """Load a saved SB3 model from ``model_path`` (PPO or DQN)."""

    DQN, PPO, _ = _sb3_imports()
    cls = DQN if algorithm.lower() == "dqn" else PPO
    return cls.load(model_path, device="cpu")


def trained_eval_metrics(model: Any, candidate_path: Optional[str], *, n_folds: int = 2) -> List[Dict[str, Any]]:
    """Run the trained policy through the walk-forward holdout and return folds.

    Helper used by the determinism reproducibility assertion: two trains with the
    same seed must agree within ``atol=1e-6, rtol=1e-5`` on per-fold metrics.
    """

    from . import portfolio_walk_forward as pwf

    factory_key = "__determinism_probe__"
    pwf.register_trained_policy_factory(factory_key, lambda **_: make_trained_policy_fn(model))
    try:
        cfg = pwf.PortfolioWalkForwardConfig(
            candidate_path=candidate_path,
            n_folds=n_folds,
            baselines=(factory_key,),
            write_artifacts=False,
        )
        payload = pwf.run_portfolio_walk_forward(cfg)
        return [
            {
                "fold_index": row["fold_index"],
                "return_pct": float(row["return_pct"]),
                "max_drawdown_pct": float(row["max_drawdown_pct"]),
                "turnover": float(row["turnover"]),
            }
            for row in payload["folds"]
        ]
    finally:
        pwf.unregister_trained_policy_factory(factory_key)


def assert_reproducible(
    config: PortfolioSb3TrainConfig,
    *,
    atol: float = 1e-6,
    rtol: float = 1e-5,
) -> Dict[str, Any]:
    """Train twice with the same seed/data and assert eval metrics agree.

    Determinism gate (V4): without the pins in :func:`apply_determinism` this is
    untestable, so the pins are applied at every train.  Compares per-fold
    ``return_pct``/``max_drawdown_pct``/``turnover`` within the explicit tolerance.
    """

    model_a, _ = train_portfolio_model(config)
    folds_a = trained_eval_metrics(model_a, config.candidate_path, n_folds=2)
    model_b, _ = train_portfolio_model(config)
    folds_b = trained_eval_metrics(model_b, config.candidate_path, n_folds=2)

    assert len(folds_a) == len(folds_b), "fold count diverged across reruns"
    for fa, fb in zip(folds_a, folds_b):
        for key in ("return_pct", "max_drawdown_pct", "turnover"):
            np.testing.assert_allclose(
                fa[key], fb[key], atol=atol, rtol=rtol,
                err_msg=f"determinism: fold {fa['fold_index']} {key} diverged",
            )
    return {"reproducible": True, "atol": atol, "rtol": rtol, "folds_compared": len(folds_a)}


def run_stage_b_smoke(config: PortfolioSb3TrainConfig, *, n_folds: int = 2) -> Dict[str, Any]:
    """Bounded Stage-B smoke: pre-register, train, then advisory holdout compare.

    Honesty contract: on the 3-symbol universe ``n_folds`` can only be 2, so per
    the plan's P0-1 power floor this is ADVISORY-ONLY — NO alpha may be claimed.
    The summary records the pre-registered primary config and ``M`` (configs
    tried) BEFORE the holdout comparison, and labels the whole result advisory.
    """

    from . import portfolio_walk_forward as pwf

    # --- Pre-registration (P0-1): written BEFORE any test-fold metric. ---
    pre_registration = {
        "primary_config": {
            "algorithm": config.algorithm,
            "turnover_penalty_lambda": config.turnover_penalty_lambda,
            "top_k_candidates": config.top_k_candidates,
            "seed_set": [config.seed],
            "cost_bps": config.cost_bps,
        },
        "candidate_config_set": [
            {"algorithm": config.algorithm, "lambda": config.turnover_penalty_lambda,
             "top_k": config.top_k_candidates, "seed": config.seed},
        ],
        "M_configs_tried": 1,
        "n_folds": n_folds,
        "advisory_only": True,
        "advisory_reason": (
            f"n_folds={n_folds} < 5 power floor (P0-1); 3-symbol universe. "
            "NO alpha claim. Real alpha verdict deferred to Stage E (n_folds>=5)."
        ),
    }

    train_summary = train_and_save(config)
    model = load_trained_model(train_summary["model_path"], algorithm=config.algorithm) \
        if train_summary["model_path"] else train_portfolio_model(config)[0]

    pwf.register_trained_policy_factory(
        "trained_ppo", lambda **_: make_trained_policy_fn(model)
    )
    try:
        wf_cfg = pwf.PortfolioWalkForwardConfig(
            candidate_path=config.candidate_path,
            output_dir=str(Path(config.output_dir) / "walk_forward"),
            n_folds=n_folds,
            baselines=("no_trade", "equal_weight_candidate", "supervised_ranker", "trained_ppo"),
            top_k_candidates=config.top_k_candidates,
            max_positions=config.max_positions,
            cost_bps=config.cost_bps,
            slippage_bps=config.slippage_bps,
            write_artifacts=config.write_artifacts,
        )
        wf_payload = pwf.run_portfolio_walk_forward(wf_cfg)
    finally:
        pwf.unregister_trained_policy_factory("trained_ppo")

    # Advisory comparison: trained_ppo vs no_trade / equal_weight / supervised_ranker.
    by_policy: Dict[str, List[float]] = {}
    for row in wf_payload["folds"]:
        by_policy.setdefault(row["policy"], []).append(float(row["return_pct"]))
    mean_ret = {p: (sum(v) / len(v) if v else 0.0) for p, v in by_policy.items()}
    trained = mean_ret.get("trained_ppo", 0.0)
    ranker = mean_ret.get("supervised_ranker", 0.0)
    advisory = {
        "mean_return_pct_by_policy": mean_ret,
        "cost_bps": config.cost_bps,
        "rl_vs_ranker": "RL_<=_ranker" if trained <= ranker else "RL_>_ranker",
        "ranker_floor_verdict": (
            "RECOMMEND ABANDONING RL (trained_ppo <= supervised_ranker on holdout)"
            if trained <= ranker
            else "RL clears the ranker floor (advisory, n_folds<5)"
        ),
        "alpha_claim": "FORBIDDEN (advisory-only, n_folds<5 per P0-1)",
    }

    summary = {
        "mode": "stom_rl_portfolio_sb3_stage_b_smoke",
        "pre_registration": pre_registration,
        "train": train_summary,
        "walk_forward_folds": wf_payload["folds"],
        "advisory_comparison": advisory,
    }
    if config.write_artifacts:
        out = Path(config.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "stage_b_smoke_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig"
        )
    return summary


def _parse_args(argv: Optional[Sequence[str]] = None) -> Tuple[PortfolioSb3TrainConfig, int]:
    import argparse

    parser = argparse.ArgumentParser(description="Stage-B deterministic SB3 portfolio train + advisory holdout.")
    parser.add_argument("--candidate-csv", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_DEEP_RL_TRAIN_OUTPUT_DIR))
    parser.add_argument("--algorithm", default="ppo", choices=("ppo", "dqn"))
    parser.add_argument("--total-timesteps", type=int, default=5_000)
    parser.add_argument("--top-k-candidates", type=int, default=3)
    parser.add_argument("--max-positions", type=int, default=2)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--turnover-penalty-lambda", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--n-folds", type=int, default=2)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument(
        "--no-training-events",
        action="store_true",
        help="Disable the live training-event stream (rl_live_events.jsonl).",
    )
    args = parser.parse_args(argv)
    config = PortfolioSb3TrainConfig(
        candidate_path=args.candidate_csv,
        output_dir=args.output_dir,
        algorithm=args.algorithm,
        total_timesteps=args.total_timesteps,
        top_k_candidates=args.top_k_candidates,
        max_positions=args.max_positions,
        cost_bps=args.cost_bps,
        turnover_penalty_lambda=args.turnover_penalty_lambda,
        seed=args.seed,
        write_artifacts=not args.no_write,
        write_training_events=not args.no_training_events,
    )
    return config, args.n_folds


def main(argv: Optional[Sequence[str]] = None) -> int:
    config, n_folds = _parse_args(argv)
    summary = run_stage_b_smoke(config, n_folds=n_folds)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


__all__ = [
    "PortfolioSb3TrainConfig",
    "MASKABLE_PPO_INVALID_ACTION_TRIGGER",
    "PORTFOLIO_TRAIN_LIVE_ALGORITHM",
    "PORTFOLIO_TRAIN_LIVE_PHASE",
    "SB3_SMOKE_SIGNATURE_FILE",
    "apply_determinism",
    "check_train_env",
    "train_portfolio_model",
    "make_trained_policy_fn",
    "measure_invalid_action_rate",
    "train_and_save",
    "load_trained_model",
    "trained_eval_metrics",
    "assert_reproducible",
    "run_stage_b_smoke",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
