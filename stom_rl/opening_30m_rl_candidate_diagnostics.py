"""Real OOS control and feature-ablation diagnostics for opening candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd  # noqa: PANDAS_OK - STOM tick/orderbook episodes are pandas frames

from .opening_30m_rl_candidate_training import _episodes_for_split, _make_env, feature_mask_details
from .opening_30m_rl_candidates import CandidateConfig
from .opening_30m_rl_context import normalize_feature_set_id
from .opening_30m_rl_realdata import JsonValue
from .orderbook_sb3_adapter import OrderbookEpisode


def evaluated_control_rows(
    best: Mapping[str, JsonValue],
    baseline_inputs: Mapping[str, float],
    *,
    frames: Sequence[pd.DataFrame],
    split_manifest: Mapping[str, JsonValue],
    output_dir: Path,
    config: CandidateConfig,
) -> list[dict[str, JsonValue]]:
    """Evaluate required controls on the frozen OOS split and write logs."""

    candidate_oos = float(best.get("oos_net_return_pct", 0.0) or 0.0)
    rows = [_baseline_row(best, key, value, candidate_oos, baseline_inputs) for key, value in baseline_inputs.items()]
    try:
        episodes = _episodes_for_split(frames, split_manifest, "oos")
    except ValueError:
        return rows + [_missing_policy_row(best, control_type, candidate_oos) for control_type in ("random_policy", "label_shuffle", "time_session_shuffle")]
    policies = {
        "random_policy": ("policy_eval_oos", episodes),
        "label_shuffle": ("label_shuffle_eval_oos", episodes),
        "time_session_shuffle": ("time_session_shuffle_eval_oos", _time_shuffled_episodes(episodes)),
    }
    for offset, (control_type, (source, control_episodes)) in enumerate(policies.items(), start=1):
        result = _evaluate_policy(control_episodes, config, control_type, int(config.seed) + 1000 + offset)
        log_path = _write_control_log(output_dir, control_type, result)
        rows.append(
            {
                "candidate_id": best["candidate_id"],
                "control_type": control_type,
                "verdict": _control_verdict(float(result["net_return_pct"]), candidate_oos, baseline_inputs, int(result["trade_count"])),
                "net_return_pct": result["net_return_pct"],
                "candidate_oos_net_return_pct": candidate_oos,
                "trade_count": result["trade_count"],
                "evaluation_source": source,
                "eval_log_path": str(log_path),
            }
        )
    return rows


def ablation_rows(best: Mapping[str, JsonValue], ablation_training: Mapping[str, JsonValue]) -> list[dict[str, JsonValue]]:
    """Compare ablation candidates against the full feature-set candidate."""

    rows = [row for row in ablation_training.get("candidates", []) if isinstance(row, dict)]
    full = next((row for row in rows if normalize_feature_set_id(str(row.get("feature_set_id", ""))) == "full_context"), None)
    full_oos = float(full.get("oos_net_return_pct", 0.0) or 0.0) if full else None
    return [_ablation_row(best, row, full_oos) for row in rows]


def oos_baseline_inputs(output_dir: Path, split_sessions: Sequence[str], split_hash: object) -> dict[str, float]:
    """Read baseline rows and sum only frozen OOS sessions."""

    path = output_dir / "baseline" / "opening_baseline_summary.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        return {}
    policy_map = {
        "no_trade": "no_trade",
        "buy_and_hold": "buy_and_hold",
        "ts_imb_same_decision_tp5_sl1_time": "ts_imb_rule",
    }
    oos_sessions = set(split_sessions)
    totals = {target: 0.0 for target in policy_map.values()}
    seen = {target: 0 for target in policy_map.values()}
    for row in rows:
        if not isinstance(row, dict) or str(row.get("session", "")) not in oos_sessions:
            continue
        target = policy_map.get(str(row.get("policy", "")))
        if target:
            totals[target] += float(row.get("net_return_pct", 0.0) or 0.0)
            seen[target] += 1
    if not all(seen.values()):
        return {}
    _write_json(
        output_dir / "opening_oos_baseline_controls.json",
        {"split_hash": split_hash, "oos_sessions": sorted(oos_sessions), "baseline_delta_inputs": totals, "row_counts": seen},
    )
    return totals


def _baseline_row(
    best: Mapping[str, JsonValue],
    control_type: str,
    net_return: float,
    candidate_oos: float,
    baselines: Mapping[str, float],
) -> dict[str, JsonValue]:
    return {
        "candidate_id": best["candidate_id"],
        "control_type": control_type,
        "verdict": _control_verdict(float(net_return), candidate_oos, baselines, 0),
        "net_return_pct": float(net_return),
        "candidate_oos_net_return_pct": candidate_oos,
        "trade_count": 0,
        "evaluation_source": "baseline_same_split",
    }


def _missing_policy_row(best: Mapping[str, JsonValue], control_type: str, candidate_oos: float) -> dict[str, JsonValue]:
    return {
        "candidate_id": best["candidate_id"],
        "control_type": control_type,
        "verdict": "MISSING",
        "net_return_pct": None,
        "candidate_oos_net_return_pct": candidate_oos,
        "trade_count": 0,
        "evaluation_source": "missing_real_oos_frames",
        "eval_log_path": "",
    }


def _evaluate_policy(
    episodes: Sequence[OrderbookEpisode],
    config: CandidateConfig,
    control_type: str,
    seed: int,
) -> dict[str, JsonValue]:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, JsonValue]] = []
    cumulative = 0.0
    trade_count = 0
    for index, episode in enumerate(episodes):
        env = _make_env([episode], config)
        observation, _ = env.reset(seed=seed + index)
        del observation
        labels = _shuffled_labels(rng)
        total_reward = 0.0
        actions: list[int] = []
        terminated = truncated = False
        last_info: Mapping[str, JsonValue] = {}
        while not (terminated or truncated):
            action = _control_action(control_type, rng, labels, len(actions))
            _, reward, terminated, truncated, last_info = env.step(action)
            total_reward += float(reward)
            actions.append(int(action))
        net_pct = total_reward * 100.0
        cumulative += net_pct
        trade_count += int(last_info.get("trade_count", 0) or 0)
        rows.append({"episode_id": episode.episode_id, "net_return_pct": net_pct, "actions": actions})
    return {"net_return_pct": cumulative, "trade_count": trade_count, "rows": rows}


def _control_action(control_type: str, rng: np.random.Generator, labels: Sequence[int], step: int) -> int:
    if control_type == "label_shuffle":
        return int(labels[min(step, len(labels) - 1)])
    return int(rng.integers(0, 2))


def _shuffled_labels(rng: np.random.Generator) -> list[int]:
    labels = [0, 0, 0, 1, 1]
    rng.shuffle(labels)
    return labels


def _time_shuffled_episodes(episodes: Sequence[OrderbookEpisode]) -> list[OrderbookEpisode]:
    shuffled = []
    for index, episode in enumerate(episodes):
        frame = episode.frame.copy()
        value_columns = [col for col in frame.columns if col not in {"index", "timestamp", "timestamp_key", "session", "symbol"}]
        if len(frame) > 1 and value_columns:
            values = frame[value_columns].sample(frac=1.0, random_state=7 + index).reset_index(drop=True)
            frame.loc[:, value_columns] = values.to_numpy()
        shuffled.append(OrderbookEpisode(f"{episode.episode_id}_time_shuffle", episode.symbol, episode.session, frame))
    return shuffled


def _write_control_log(output_dir: Path, control_type: str, result: Mapping[str, JsonValue]) -> Path:
    path = output_dir / "control_eval_logs" / f"{control_type}_oos.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def _write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _control_verdict(net_return: float, candidate_oos: float, baselines: Mapping[str, float], trade_count: int) -> str:
    threshold = max(float(value) for value in baselines.values()) if baselines else 0.0
    return "GO_CANDIDATE" if trade_count > 0 and net_return > threshold and net_return > candidate_oos else "NO-GO"


def _ablation_row(
    best: Mapping[str, JsonValue],
    row: Mapping[str, JsonValue],
    full_oos: float | None,
) -> dict[str, JsonValue]:
    feature_set_id = normalize_feature_set_id(str(row.get("feature_set_id", "")))
    details = feature_mask_details(feature_set_id=feature_set_id)
    oos = float(row.get("oos_net_return_pct", 0.0) or 0.0)
    unavailable = list(details["unavailable_feature_groups"])
    trained = str(row.get("status")) == "trained"
    delta = None if full_oos is None else oos - full_oos
    not_applicable = bool(unavailable)
    passed = trained and (not_applicable or feature_set_id == "full_context" or (delta is not None and delta <= 0.25))
    return {
        "candidate_id": best["candidate_id"],
        "ablation_candidate_id": row.get("candidate_id"),
        "feature_set_id": feature_set_id,
        "oos_net_return_pct": row.get("oos_net_return_pct"),
        "passed": passed,
        "model_path": row.get("model_path", ""),
        "evaluation_source": "trained_feature_mask_candidate",
        "comparison_status": "not_applicable_feature_absent" if not_applicable else "compared_to_full",
        "applicable": not not_applicable,
        "delta_vs_full_oos_pct": delta,
        **details,
    }
