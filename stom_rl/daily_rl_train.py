"""Research-only constrained daily portfolio RL runner.

D4 uses a tiny tabular Q policy over the constrained daily portfolio environment.
The output is falsification/evidence for later walk-forward gates, not a live,
broker, order, profit, or deployable-RL claim.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .daily_ohlcv_db import PRICE_BASIS, PRICE_BASIS_EVIDENCE, REPO_ROOT
from .daily_portfolio_env import (
    ACTION_NAMES,
    OBSERVATION_MODE_V1,
    DailyPortfolioEnv,
    build_observation_manifest,
    candidates_by_date,
    validate_observation_manifest,
)
from .daily_prediction import DEFAULT_PREDICTION_ROOT, ROUND_TRIP_COST_BP

DEFAULT_PORTFOLIO_ROOT = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_portfolio"
PORTFOLIO_SCHEMA_VERSION = 1
SAFE_RUN_RE = re.compile(r"^[0-9A-Za-z_.-]+$")
SCORE_COLUMN = "score_supervised_linear_ranker"
FROZEN_BASELINE_STRATEGIES = [
    "no_trade_cash",
    "shuffle_control",
    "equal_weight_topk_momentum",
    "vol_adjusted_momentum",
    "supervised_linear_ranker",
    "supervised_direction_classifier",
]
RESEARCH_GUARDRAIL = (
    "Research-only D4 constrained daily portfolio RL evidence; no profit guarantee, "
    "no live/broker/orders, no deployable model readiness claim."
)
ENTRY_ACTION_IDS = {1, 2}
ACTION_FILTER_MODE_NONE = "none"
ACTION_FILTER_MODE_DISABLED = "disabled"
ACTION_FILTER_MODE_PRIOR_DISABLED_CONTROL = "prior_disabled_control_v1"
TRADE_QUALITY_FILTER_THRESHOLDS = {
    "confidence_min_bucket": 3,
    "margin_min_bucket": 3,
    "risk_volatility_max_bucket": 3,
}
TRADE_QUALITY_FILTER_MODES = {
    ACTION_FILTER_MODE_NONE,
    ACTION_FILTER_MODE_DISABLED,
    ACTION_FILTER_MODE_PRIOR_DISABLED_CONTROL,
    "confidence_abstain_v1",
    "margin_abstain_v1",
    "confidence_margin_joint_v1",
    "risk_regime_abstain_v1",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    if not SAFE_RUN_RE.match(rid) or rid in {".", ".."} or "/" in rid or "\\" in rid:
        raise ValueError("run_id contains unsafe characters")
    return rid


def _latest_run_dir(root: Path, required_file: str) -> Path:
    candidates = sorted(root.glob(f"*/{required_file}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No {required_file} under {root}")
    return candidates[0].parent


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
def _source_hashes() -> dict[str, str]:
    source_paths = {
        "stom_rl/daily_rl_train.py": Path(__file__).resolve(),
        "stom_rl/daily_portfolio_env.py": REPO_ROOT / "stom_rl" / "daily_portfolio_env.py",
        "stom_rl/daily_prediction.py": REPO_ROOT / "stom_rl" / "daily_prediction.py",
    }
    return {name: _file_sha256(path) for name, path in source_paths.items()}




def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback_fields: list[str]) -> None:
    if rows:
        field_set = {key for row in rows for key in row.keys()}
        fields = [field for field in fallback_fields if field in field_set]
        fields.extend(sorted(field_set - set(fields)))
    else:
        fields = fallback_fields
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _resolve_prediction_run(prediction_run_dir: Path | str | None = None) -> Path:
    if prediction_run_dir is not None:
        run_dir = Path(prediction_run_dir).resolve()
        root = DEFAULT_PREDICTION_ROOT.resolve()
        run_dir.relative_to(root)
        if not (run_dir / "prediction_manifest.json").exists():
            raise FileNotFoundError(run_dir / "prediction_manifest.json")
        return run_dir
    return _latest_run_dir(DEFAULT_PREDICTION_ROOT, "prediction_manifest.json")


def _max_drawdown(equity_values: Iterable[float]) -> float:
    peak = 1.0
    max_dd = 0.0
    for value in equity_values:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, value / peak - 1.0)
    return max_dd


def _mean(values: Iterable[float]) -> float:
    clean = [float(value) for value in values]
    return sum(clean) / len(clean) if clean else 0.0
def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None



def _policy_action(
    q_table: dict[tuple[int, ...], list[float]],
    state: tuple[int, ...],
    mask: list[bool],
    *,
    epsilon: float,
    rng: random.Random,
    action_prior_values: list[float] | None = None,
) -> int:
    valid_actions = [idx for idx, valid in enumerate(mask) if valid]
    if not valid_actions:
        return 0
    if rng.random() < epsilon:
        return rng.choice(valid_actions)
    values = q_table[state]
    priors = action_prior_values or [0.0] * len(ACTION_NAMES)
    return max(valid_actions, key=lambda action: values[action] + priors[action])


def build_action_prior_values(*, mode: str = "none", strength: float = 0.0) -> list[float]:
    """Return diagnostic action priors used only for policy selection, not rewards."""

    clean_mode = str(mode or "none")
    clean_strength = max(0.0, float(strength or 0.0))
    priors = [0.0] * len(ACTION_NAMES)
    if clean_mode in {"none", "disabled"} or clean_strength == 0.0:
        return priors
    if clean_mode == "entry_bias_v1":
        priors[1] = clean_strength
        priors[2] = clean_strength
        return priors
    raise ValueError(f"Unsupported action_prior_mode: {clean_mode}")


def _clean_action_filter_mode(mode: str | None) -> str:
    clean_mode = str(mode or ACTION_FILTER_MODE_NONE)
    if clean_mode not in TRADE_QUALITY_FILTER_MODES:
        raise ValueError(f"Unsupported action_filter_mode: {clean_mode}")
    return clean_mode


def _action_filter_enabled(mode: str) -> bool:
    return mode not in {
        ACTION_FILTER_MODE_NONE,
        ACTION_FILTER_MODE_DISABLED,
        ACTION_FILTER_MODE_PRIOR_DISABLED_CONTROL,
    }


def _required_filter_state_fields(mode: str) -> list[str]:
    if mode == "confidence_abstain_v1":
        return ["d3_confidence_bucket"]
    if mode == "margin_abstain_v1":
        return ["score_margin_bucket"]
    if mode == "confidence_margin_joint_v1":
        return ["d3_confidence_bucket", "score_margin_bucket"]
    if mode == "risk_regime_abstain_v1":
        return ["recent_score_volatility_bucket"]
    return []


def _require_filter_state_fields(mode: str, state_details: dict[str, Any]) -> None:
    missing = [
        field
        for field in _required_filter_state_fields(mode)
        if field not in state_details or state_details.get(field) in (None, "")
    ]
    if missing:
        raise ValueError(
            "action_filter_mode requires action_induction_v2 state fields: "
            + ",".join(missing)
        )


def _state_bucket(state_details: dict[str, Any], key: str) -> int:
    try:
        return int(state_details.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def build_action_filter_decision(
    *,
    mode: str = ACTION_FILTER_MODE_NONE,
    state_details: dict[str, Any],
    mask: list[bool],
) -> dict[str, Any]:
    """Return causal D4 trade-quality filter decisions for buy/add actions.

    The filter reads only state_details fields already available before action
    selection. It never reads future_return_1d or reward diagnostics.
    """

    clean_mode = _clean_action_filter_mode(mode)
    filtered_mask = list(mask)
    reasons_by_action = {name: "not_entry_action" for name in ACTION_NAMES.values()}
    enabled = _action_filter_enabled(clean_mode)
    if enabled:
        _require_filter_state_fields(clean_mode, state_details)
    d3_confidence_bucket = _state_bucket(state_details, "d3_confidence_bucket")
    score_margin_bucket = _state_bucket(state_details, "score_margin_bucket")
    recent_score_volatility_bucket = _state_bucket(state_details, "recent_score_volatility_bucket")
    passed = True
    primary_reason = "filter_disabled"

    if clean_mode == "confidence_abstain_v1":
        passed = d3_confidence_bucket >= TRADE_QUALITY_FILTER_THRESHOLDS["confidence_min_bucket"]
        primary_reason = (
            "pass_confidence_bucket_gte_threshold"
            if passed
            else "blocked_confidence_bucket_below_threshold"
        )
    elif clean_mode == "margin_abstain_v1":
        passed = score_margin_bucket >= TRADE_QUALITY_FILTER_THRESHOLDS["margin_min_bucket"]
        primary_reason = (
            "pass_margin_bucket_gte_threshold"
            if passed
            else "blocked_margin_bucket_below_threshold"
        )
    elif clean_mode == "confidence_margin_joint_v1":
        confidence_pass = d3_confidence_bucket >= TRADE_QUALITY_FILTER_THRESHOLDS["confidence_min_bucket"]
        margin_pass = score_margin_bucket >= TRADE_QUALITY_FILTER_THRESHOLDS["margin_min_bucket"]
        passed = confidence_pass and margin_pass
        primary_reason = (
            "pass_confidence_and_margin_thresholds"
            if passed
            else "blocked_confidence_or_margin_below_threshold"
        )
    elif clean_mode == "risk_regime_abstain_v1":
        passed = recent_score_volatility_bucket <= TRADE_QUALITY_FILTER_THRESHOLDS["risk_volatility_max_bucket"]
        primary_reason = (
            "pass_recent_score_volatility_lte_threshold"
            if passed
            else "blocked_recent_score_volatility_above_threshold"
        )
    elif clean_mode == ACTION_FILTER_MODE_PRIOR_DISABLED_CONTROL:
        primary_reason = "prior_disabled_control_no_filter"
    elif clean_mode == ACTION_FILTER_MODE_DISABLED:
        primary_reason = "filter_disabled"
    elif clean_mode == ACTION_FILTER_MODE_NONE:
        primary_reason = "filter_disabled"

    for action_id in ENTRY_ACTION_IDS:
        action_name = ACTION_NAMES[action_id]
        if action_id >= len(mask) or not mask[action_id]:
            reasons_by_action[action_name] = "base_action_mask_blocked"
            continue
        if enabled and not passed:
            filtered_mask[action_id] = False
            reasons_by_action[action_name] = primary_reason
        else:
            reasons_by_action[action_name] = primary_reason

    blocked_entry_actions = [
        ACTION_NAMES[action_id]
        for action_id in ENTRY_ACTION_IDS
        if action_id < len(mask) and bool(mask[action_id]) and not bool(filtered_mask[action_id])
    ]
    return {
        "mode": clean_mode,
        "enabled": enabled,
        "thresholds": dict(TRADE_QUALITY_FILTER_THRESHOLDS),
        "filtered_mask": filtered_mask,
        "reasons_by_action": reasons_by_action,
        "primary_reason": primary_reason,
        "entry_filter_passed": passed,
        "blocked_entry_actions": blocked_entry_actions,
        "future_label_exposed": False,
        "state_buckets": {
            "d3_confidence_bucket": d3_confidence_bucket,
            "score_margin_bucket": score_margin_bucket,
            "recent_score_volatility_bucket": recent_score_volatility_bucket,
        },
    }


def _serialize_q_table(q_table: dict[tuple[int, ...], list[float]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for state, values in sorted(q_table.items()):
        rows.append(
            {
                "state_key": "|".join(str(part) for part in state),
                "state_dim": len(state),
                "position_count": state[0] if len(state) >= 1 else "",
                "score_bucket": state[1] if len(state) >= 2 else "",
                **{f"state_{index}": value for index, value in enumerate(state)},
                **{f"q_{ACTION_NAMES[index]}": value for index, value in enumerate(values)},
            }
        )
    return rows


def build_learning_curve(episode_rows: list[dict[str, Any]], *, window: int = 3) -> list[dict[str, Any]]:
    curve: list[dict[str, Any]] = []
    best_reward: float | None = None
    rewards: list[float] = []
    for row in episode_rows:
        reward = float(row.get("total_reward") or 0.0)
        rewards.append(reward)
        best_reward = reward if best_reward is None else max(best_reward, reward)
        rolling = rewards[-max(1, int(window)) :]
        steps = int(row.get("steps") or 0)
        invalid_actions = int(row.get("invalid_actions") or 0)
        curve.append(
            {
                "episode": int(row.get("episode") or len(curve) + 1),
                "total_reward": reward,
                "rolling_mean_reward": _mean(rolling),
                "best_total_reward": best_reward,
                "steps": steps,
                "final_equity": float(row.get("final_equity") or 0.0),
                "invalid_actions": invalid_actions,
                "invalid_action_rate": invalid_actions / steps if steps else 0.0,
            }
        )
    return curve


def build_action_distribution(action_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str, bool, str, bool], int] = defaultdict(int)
    totals_by_split: dict[str, int] = defaultdict(int)
    for row in action_rows:
        split = str(row.get("split") or "unknown")
        requested_action = str(row.get("requested_action") or row.get("action") or "unknown")
        executed_action = str(row.get("executed_action") or row.get("action") or "unknown")
        invalid = bool(row.get("invalid_action"))
        invalid_reason = str(row.get("invalid_action_reason") or "")
        no_trade_action = bool(row.get("no_trade_action"))
        counts[(split, requested_action, executed_action, invalid, invalid_reason, no_trade_action)] += 1
        totals_by_split[split] += 1
    return [
        {
            "split": split,
            "action": executed_action,
            "requested_action": requested_action,
            "executed_action": executed_action,
            "invalid_action": invalid,
            "invalid_action_reason": invalid_reason,
            "no_trade_action": no_trade_action,
            "count": count,
            "action_rate": count / totals_by_split[split] if totals_by_split[split] else 0.0,
        }
        for (split, requested_action, executed_action, invalid, invalid_reason, no_trade_action), count in sorted(counts.items())
    ]


def build_turnover_rows(reward_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "split": row.get("split"),
            "date": row.get("date"),
            "action": row.get("action"),
            "requested_action": row.get("requested_action"),
            "executed_action": row.get("executed_action"),
            "invalid_action_reason": row.get("invalid_action_reason"),
            "no_trade_action": row.get("no_trade_action"),
            "turnover": row.get("turnover"),
            "turnover_cost": row.get("cost"),
            "net_return_after_cost": row.get("net_return_after_cost"),
            "churn_penalty": row.get("churn_penalty"),
            "reward": row.get("reward"),
            "equity": row.get("equity"),
        }
        for row in reward_rows
    ]


def build_drawdown_rows(reward_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "split": row.get("split"),
            "date": row.get("date"),
            "action": row.get("action"),
            "requested_action": row.get("requested_action"),
            "executed_action": row.get("executed_action"),
            "invalid_action_reason": row.get("invalid_action_reason"),
            "no_trade_action": row.get("no_trade_action"),
            "equity": row.get("equity"),
            "current_drawdown": row.get("current_drawdown"),
            "drawdown_penalty": row.get("drawdown_penalty"),
            "reward_before_drawdown_penalty": row.get("reward_before_drawdown_penalty"),
            "reward": row.get("reward"),
        }
        for row in reward_rows
    ]


def build_reward_component_summary(reward_rows: list[dict[str, Any]]) -> dict[str, Any]:
    component_keys = [
        "gross_return",
        "cost",
        "net_return_after_cost",
        "exposure_penalty",
        "concentration_penalty",
        "invalid_action_penalty",
        "churn_penalty",
        "drawdown_penalty",
        "no_trade_hold_reward",
        "reward",
    ]
    by_split: dict[str, dict[str, float]] = {}
    for row in reward_rows:
        split = str(row.get("split") or "unknown")
        bucket = by_split.setdefault(
            split,
            {key: 0.0 for key in component_keys} | {"rows": 0.0, "no_trade_actions": 0.0, "invalid_actions": 0.0},
        )
        bucket["rows"] += 1.0
        bucket["no_trade_actions"] += 1.0 if bool(row.get("no_trade_action")) else 0.0
        bucket["invalid_actions"] += 1.0 if bool(row.get("invalid_action")) else 0.0
        for key in component_keys:
            bucket[key] += float(row.get(key) or 0.0)
    return {
        "component_keys": component_keys,
        "by_split": [
            {"split": split, **values}
            for split, values in sorted(by_split.items())
        ],
        "guardrail": "Reward components are accounting/diagnostic telemetry only; they are not a profit, live, broker, order, or model-build claim.",
    }


def build_reward_action_ablations(
    reward_rows: list[dict[str, Any]],
    action_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    actions_by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reward_rows:
        rows_by_split[str(row.get("split") or "unknown")].append(row)
    for row in action_rows:
        actions_by_split[str(row.get("split") or "unknown")].append(row)

    reward_scenarios = [
        ("recorded_reward", None, "Recorded constrained D4 reward after 23bp cost and penalties."),
        ("without_turnover_cost", "cost", "Counterfactual removes the explicit 23bp turnover cost component."),
        ("without_drawdown_penalty", "drawdown_penalty", "Counterfactual removes drawdown penalty only."),
        ("without_concentration_penalty", "concentration_penalty", "Counterfactual removes concentration penalty only."),
        ("without_churn_penalty", "churn_penalty", "Counterfactual removes turnover/churn penalty only."),
        ("without_invalid_action_penalty", "invalid_action_penalty", "Counterfactual removes invalid-action penalty only."),
    ]

    ablations: list[dict[str, Any]] = []
    for split in sorted(set(rows_by_split) | set(actions_by_split)):
        split_rows = rows_by_split.get(split, [])
        split_actions = actions_by_split.get(split, [])
        recorded_rewards = [float(row.get("reward") or 0.0) for row in split_rows]
        recorded_total = sum(recorded_rewards)
        action_count = len(split_actions)
        invalid_count = sum(1 for row in split_actions if bool(row.get("invalid_action")))
        no_trade_count = sum(1 for row in split_actions if bool(row.get("no_trade_action")))
        for name, add_back_key, description in reward_scenarios:
            adjusted_rewards = [
                float(row.get("reward") or 0.0) + (float(row.get(add_back_key) or 0.0) if add_back_key else 0.0)
                for row in split_rows
            ]
            total = sum(adjusted_rewards)
            ablations.append(
                {
                    "split": split,
                    "ablation_family": "reward_component",
                    "ablation": name,
                    "description": description,
                    "rows": len(adjusted_rewards),
                    "total_reward": total,
                    "mean_reward": total / len(adjusted_rewards) if adjusted_rewards else 0.0,
                    "delta_vs_recorded_reward": total - recorded_total,
                    "action_rows": action_count,
                    "invalid_action_count": invalid_count,
                    "invalid_action_rate": invalid_count / action_count if action_count else 0.0,
                    "no_trade_action_count": no_trade_count,
                    "no_trade_action_rate": no_trade_count / action_count if action_count else 0.0,
                    "cost_round_trip_bp": ROUND_TRIP_COST_BP,
                }
            )

        no_trade_rewards = [float(row.get("reward") or 0.0) for row in split_rows if bool(row.get("no_trade_action"))]
        no_trade_total = sum(no_trade_rewards)
        ablations.append(
            {
                "split": split,
                "ablation_family": "action_subset",
                "ablation": "observed_no_trade_hold_actions",
                "description": "Observed hold-with-empty-book rows; diagnostic no-trade behavior, not a tuned control.",
                "rows": len(no_trade_rewards),
                "total_reward": no_trade_total,
                "mean_reward": no_trade_total / len(no_trade_rewards) if no_trade_rewards else 0.0,
                "delta_vs_recorded_reward": no_trade_total - recorded_total,
                "action_rows": action_count,
                "invalid_action_count": invalid_count,
                "invalid_action_rate": invalid_count / action_count if action_count else 0.0,
                "no_trade_action_count": no_trade_count,
                "no_trade_action_rate": no_trade_count / action_count if action_count else 0.0,
                "cost_round_trip_bp": ROUND_TRIP_COST_BP,
            }
        )
    return ablations
def build_no_trade_opportunity_summary(opportunity_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize post-policy no-trade opportunity diagnostics without changing rewards."""

    rows_by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunity_rows:
        rows_by_split[str(row.get("split") or "unknown")].append(row)

    by_split: list[dict[str, Any]] = []
    for split, split_rows in sorted(rows_by_split.items()):
        no_trade_rows = [row for row in split_rows if bool(row.get("no_trade_action"))]
        labeled_no_trade_rows = [
            row
            for row in no_trade_rows
            if _optional_float(row.get("top_candidate_net_after_entry_cost")) is not None
        ]
        missed_rows = [
            row
            for row in labeled_no_trade_rows
            if (_optional_float(row.get("top_candidate_net_after_entry_cost")) or 0.0) > 0.0
        ]
        avoided_rows = [
            row
            for row in labeled_no_trade_rows
            if (_optional_float(row.get("top_candidate_net_after_entry_cost")) or 0.0) < 0.0
        ]
        flat_rows = [
            row
            for row in labeled_no_trade_rows
            if (_optional_float(row.get("top_candidate_net_after_entry_cost")) or 0.0) == 0.0
        ]
        missed_net = [_optional_float(row.get("top_candidate_net_after_entry_cost")) or 0.0 for row in missed_rows]
        avoided_net = [_optional_float(row.get("top_candidate_net_after_entry_cost")) or 0.0 for row in avoided_rows]
        top_scores = [
            _optional_float(row.get("top_candidate_score"))
            for row in no_trade_rows
            if _optional_float(row.get("top_candidate_score")) is not None
        ]
        by_split.append(
            {
                "split": split,
                "rows": len(split_rows),
                "no_trade_rows": len(no_trade_rows),
                "no_trade_rate": len(no_trade_rows) / len(split_rows) if split_rows else 0.0,
                "labeled_no_trade_rows": len(labeled_no_trade_rows),
                "missed_positive_no_trade_count": len(missed_rows),
                "risk_avoided_no_trade_count": len(avoided_rows),
                "flat_no_trade_count": len(flat_rows),
                "total_missed_positive_net_after_entry_cost": sum(missed_net),
                "mean_missed_positive_net_after_entry_cost": _mean(missed_net),
                "total_risk_avoided_net_after_entry_cost": sum(avoided_net),
                "mean_risk_avoided_net_after_entry_cost": _mean(avoided_net),
                "mean_top_candidate_score_on_no_trade": _mean(score for score in top_scores if score is not None),
            }
        )

    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "status": "POST_POLICY_DIAGNOSTIC_ONLY",
        "guardrail": "No-trade opportunity diagnostics use future labels only after the policy decision for failure analysis; they are not training state, profit evidence, live readiness, broker readiness, or retuning permission.",
        "training_state_uses_future_label": False,
        "diagnostic_uses_future_label_after_policy": True,
        "cost_round_trip_bp": ROUND_TRIP_COST_BP,
        "entry_cost_model": "top_candidate_future_return_1d minus one-position entry turnover share of 23bp round-trip cost; diagnostic only.",
        "by_split": by_split,
    }


def train_tabular_q_policy(
    train_candidates: dict[str, list[Any]],
    *,
    episodes: int = 8,
    seed: int = 7,
    max_positions: int = 5,
    alpha: float = 0.2,
    gamma: float = 0.85,
    epsilon: float = 0.15,
    observation_mode: str = OBSERVATION_MODE_V1,
    action_prior_mode: str = "none",
    action_prior_strength: float = 0.0,
    action_filter_mode: str = ACTION_FILTER_MODE_NONE,
) -> tuple[dict[tuple[int, ...], list[float]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    action_prior_values = build_action_prior_values(mode=action_prior_mode, strength=action_prior_strength)
    q_table: dict[tuple[int, ...], list[float]] = defaultdict(lambda: [0.0] * len(ACTION_NAMES))
    episode_rows: list[dict[str, Any]] = []
    for episode in range(1, int(episodes) + 1):
        env = DailyPortfolioEnv(train_candidates, max_positions=max_positions, observation_mode=observation_mode)
        state = env.reset()
        total_reward = 0.0
        steps = 0
        while not env.done():
            mask = env.action_mask()
            filter_decision = build_action_filter_decision(
                mode=action_filter_mode,
                state_details=env.state_details(),
                mask=mask,
            )
            filtered_mask = list(filter_decision["filtered_mask"])
            action = _policy_action(q_table, state, filtered_mask, epsilon=epsilon, rng=rng, action_prior_values=action_prior_values)
            next_state, reward, done, _info = env.step(action)
            best_next = max(q_table[next_state]) if not done else 0.0
            q_table[state][action] += alpha * (reward + gamma * best_next - q_table[state][action])
            total_reward += reward
            steps += 1
            state = next_state
        episode_rows.append(
            {
                "episode": episode,
                "total_reward": total_reward,
                "steps": steps,
                "final_equity": env.equity,
                "invalid_actions": env.invalid_actions,
                "mean_reward": total_reward / steps if steps else 0.0,
                "invalid_action_rate": env.invalid_actions / steps if steps else 0.0,
                "observation_mode": observation_mode,
                "action_prior_mode": action_prior_mode,
                "action_prior_strength": float(action_prior_strength),
                "action_filter_mode": action_filter_mode,
            }
        )
    return dict(q_table), episode_rows


def evaluate_policy(
    candidates: dict[str, list[Any]],
    q_table: dict[tuple[int, ...], list[float]],
    *,
    split_label: str,
    max_positions: int = 5,
    observation_mode: str = OBSERVATION_MODE_V1,
    action_prior_mode: str = "none",
    action_prior_strength: float = 0.0,
    action_filter_mode: str = ACTION_FILTER_MODE_NONE,
) -> dict[str, Any]:
    env = DailyPortfolioEnv(candidates, max_positions=max_positions, observation_mode=observation_mode)
    action_prior_values = build_action_prior_values(mode=action_prior_mode, strength=action_prior_strength)
    state = env.reset()
    positions_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    reward_rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []
    opportunity_rows: list[dict[str, Any]] = []
    abstention_rows: list[dict[str, Any]] = []
    equity_values: list[float] = []
    total_reward = 0.0

    while not env.done():
        mask = env.action_mask()
        state_details = env.state_details()
        filter_decision = build_action_filter_decision(
            mode=action_filter_mode,
            state_details=state_details,
            mask=mask,
        )
        filtered_mask = list(filter_decision["filtered_mask"])
        current_candidates = env._current_candidates()
        top_candidate = current_candidates[0] if current_candidates else None
        top_candidate_future_return = _optional_float(top_candidate.future_return) if top_candidate else None
        top_candidate_entry_cost = (1.0 / env.max_positions) * env.cost_rate if top_candidate else 0.0
        top_candidate_net_after_entry_cost = (
            top_candidate_future_return - top_candidate_entry_cost
            if top_candidate_future_return is not None
            else None
        )
        position_count = int(state[0])
        exposure_fraction = position_count / env.max_positions
        cash_fraction = max(0.0, 1.0 - exposure_fraction)
        held_codes = "|".join(str(code).zfill(6) for code in env.positions)
        values = q_table.get(state, [0.0] * len(ACTION_NAMES))
        valid_actions = [idx for idx, valid in enumerate(filtered_mask) if valid]
        action = max(valid_actions or [0], key=lambda idx: values[idx] + action_prior_values[idx])
        next_state, reward, _done, info = env.step(action)
        equity_values.append(float(info["equity"]))
        total_reward += float(reward)
        mask_text = "|".join(str(int(v)) for v in mask)
        filter_mask_text = "|".join(str(int(v)) for v in filtered_mask)
        mask_reasons = info.get("action_mask_reasons", {})
        mask_reason_fields = {f"mask_reason_{name}": str(mask_reasons.get(name, "")) for name in ACTION_NAMES.values()}
        filter_reasons = filter_decision.get("reasons_by_action", {})
        filter_reason_fields = {f"filter_reason_{name}": str(filter_reasons.get(name, "")) for name in ACTION_NAMES.values()}
        policy_value_fields = {
            f"policy_value_{name}": values[index]
            for index, name in ACTION_NAMES.items()
        }
        action_prior_fields = {
            f"action_prior_{name}": action_prior_values[index]
            for index, name in ACTION_NAMES.items()
        }
        policy_score_fields = {
            f"policy_score_{name}": values[index] + action_prior_values[index]
            for index, name in ACTION_NAMES.items()
        }
        state_rows.append(
            {
                "split": split_label,
                "date": info["date"],
                "observation_position_count": position_count,
                "observation_top_score_bucket": int(state_details["top_score_bucket"]),
                "observation_score_margin_bucket": state_details.get("score_margin_bucket", ""),
                "observation_candidate_count_bucket": state_details.get("candidate_count_bucket", ""),
                "observation_recent_score_volatility_bucket": state_details.get("recent_score_volatility_bucket", ""),
                "observation_d3_confidence_bucket": state_details.get("d3_confidence_bucket", ""),
                "observation_mode": observation_mode,
                "observation_state_key": "|".join(str(part) for part in state),
                "cash_fraction": cash_fraction,
                "exposure_fraction": exposure_fraction,
                "held_codes": held_codes,
                "candidate_count": len(current_candidates),
                "top_candidate_code": str(top_candidate.code).zfill(6) if top_candidate else "",
                "top_candidate_rank": 1 if top_candidate else "",
                "top_candidate_score": top_candidate.score if top_candidate else "",
                "top_candidate_reward_label_available": bool(top_candidate.reward_label_available) if top_candidate else False,
                "action_mask_hold_buy_add_sell_reduce": mask_text,
                "future_label_exposed": False,
                "action_prior_mode": action_prior_mode,
                "action_prior_strength": float(action_prior_strength),
                "action_filter_mode": action_filter_mode,
                "action_filter_enabled": bool(filter_decision["enabled"]),
                "action_filter_reason": filter_decision["primary_reason"],
                "entry_filter_passed": bool(filter_decision["entry_filter_passed"]),
                "blocked_entry_actions": "|".join(str(action_name) for action_name in filter_decision["blocked_entry_actions"]),
                "filtered_action_mask_hold_buy_add_sell_reduce": filter_mask_text,
                **mask_reason_fields,
                **filter_reason_fields,
                **policy_value_fields,
                **action_prior_fields,
                **policy_score_fields,
            }
        )
        blocked_entry_actions_text = "|".join(str(action_name) for action_name in filter_decision["blocked_entry_actions"])
        entry_abstained_by_filter = bool(blocked_entry_actions_text) and info["executed_action"] not in {"buy", "add"}
        abstention_rows.append(
            {
                "split": split_label,
                "date": info["date"],
                "action_filter_mode": action_filter_mode,
                "action_filter_enabled": bool(filter_decision["enabled"]),
                "action_filter_reason": filter_decision["primary_reason"],
                "entry_filter_passed": bool(filter_decision["entry_filter_passed"]),
                "blocked_entry_actions": blocked_entry_actions_text,
                "entry_abstained_by_filter": entry_abstained_by_filter,
                "selected_action": ACTION_NAMES.get(action, "unknown"),
                "requested_action": info["requested_action"],
                "executed_action": info["executed_action"],
                "base_action_mask_hold_buy_add_sell_reduce": mask_text,
                "filtered_action_mask_hold_buy_add_sell_reduce": filter_mask_text,
                "base_buy_valid": bool(mask[1]) if len(mask) > 1 else False,
                "base_add_valid": bool(mask[2]) if len(mask) > 2 else False,
                "filtered_buy_valid": bool(filtered_mask[1]) if len(filtered_mask) > 1 else False,
                "filtered_add_valid": bool(filtered_mask[2]) if len(filtered_mask) > 2 else False,
                "observation_d3_confidence_bucket": state_details.get("d3_confidence_bucket", ""),
                "observation_score_margin_bucket": state_details.get("score_margin_bucket", ""),
                "observation_recent_score_volatility_bucket": state_details.get("recent_score_volatility_bucket", ""),
                "future_label_exposed": False,
                "guardrail": "decision_time_trade_quality_filter_no_future_label_no_profit_claim",
                **filter_reason_fields,
            }
        )

        invalid_rows.append(
            {
                "split": split_label,
                "date": info["date"],
                "action": info["action"],
                "requested_action": info["requested_action"],
                "executed_action": info["executed_action"],
                "invalid_action": bool(info["invalid_action"]),
                "invalid_action_reason": info["invalid_action_reason"] or "",
                "no_trade_action": bool(info["no_trade_action"]),
                "action_mask_hold_buy_add_sell_reduce": mask_text,
                **mask_reason_fields,
            }
        )
        reward_rows.append(
            {
                "split": split_label,
                "date": info["date"],
                "action": info["action"],
                "requested_action": info["requested_action"],
                "executed_action": info["executed_action"],
                "invalid_action": bool(info["invalid_action"]),
                "invalid_action_reason": info["invalid_action_reason"] or "",
                "no_trade_action": bool(info["no_trade_action"]),
                "gross_return": info["gross_return"],
                "cost": info["cost"],
                "net_return_after_cost": info["net_return_after_cost"],
                "slippage_cost": 0.0,
                "turnover": info["turnover"],
                "exposure": info["exposure"],
                "concentration": info["concentration"],
                "exposure_penalty": info["exposure_penalty"],
                "concentration_penalty": info["concentration_penalty"],
                "invalid_action_penalty": info["invalid_action_penalty"],
                "reward": info["reward"],
                "churn_penalty": info["churn_penalty"],
                "drawdown_penalty": info["drawdown_penalty"],
                "no_trade_hold_reward": info["no_trade_hold_reward"],
                "current_drawdown": info["current_drawdown"],
                "reward_before_drawdown_penalty": info["reward_before_drawdown_penalty"],
                "equity": info["equity"],
                "missing_reward_label_count": info["missing_reward_label_count"],
                **mask_reason_fields,
            }
        )
        if not bool(info["no_trade_action"]):
            no_trade_diagnostic = "NOT_NO_TRADE_ACTION"
        elif top_candidate_future_return is None:
            no_trade_diagnostic = "NO_REWARD_LABEL_FOR_TOP_CANDIDATE"
        elif (top_candidate_net_after_entry_cost or 0.0) > 0.0:
            no_trade_diagnostic = "NO_TRADE_MISSED_POSITIVE_TOP_CANDIDATE_AFTER_ENTRY_COST"
        elif (top_candidate_net_after_entry_cost or 0.0) < 0.0:
            no_trade_diagnostic = "NO_TRADE_AVOIDED_NEGATIVE_TOP_CANDIDATE_AFTER_ENTRY_COST"
        else:
            no_trade_diagnostic = "NO_TRADE_TOP_CANDIDATE_FLAT_AFTER_ENTRY_COST"
        opportunity_rows.append(
            {
                "split": split_label,
                "date": info["date"],
                "action": info["action"],
                "requested_action": info["requested_action"],
                "executed_action": info["executed_action"],
                "no_trade_action": bool(info["no_trade_action"]),
                "observation_position_count": position_count,
                "candidate_count": len(current_candidates),
                "top_candidate_code": str(top_candidate.code).zfill(6) if top_candidate else "",
                "top_candidate_score": top_candidate.score if top_candidate else "",
                "top_candidate_reward_label_available": bool(top_candidate.reward_label_available) if top_candidate else False,
                "top_candidate_future_return_1d": top_candidate_future_return if top_candidate_future_return is not None else "",
                "top_candidate_entry_cost": top_candidate_entry_cost if top_candidate else "",
                "top_candidate_net_after_entry_cost": top_candidate_net_after_entry_cost if top_candidate_net_after_entry_cost is not None else "",
                "no_trade_opportunity_flag": bool(info["no_trade_action"])
                and top_candidate_net_after_entry_cost is not None
                and top_candidate_net_after_entry_cost > 0.0,
                "no_trade_risk_avoided_flag": bool(info["no_trade_action"])
                and top_candidate_net_after_entry_cost is not None
                and top_candidate_net_after_entry_cost < 0.0,
                "diagnostic": no_trade_diagnostic,
                "diagnostic_future_label_exposed": top_candidate_future_return is not None,
                "future_label_used_for_training_state": False,
                "guardrail": "post_policy_failure_analysis_only_not_training_state_or_profit_claim",
            }
        )
        for rank, code in enumerate(info["positions"], start=1):
            positions_rows.append(
                {
                    "split": split_label,
                    "date": info["date"],
                    "rank": rank,
                    "code": str(code).zfill(6),
                    "action": info["action"],
                    "equity": info["equity"],
                }
            )
        state = next_state

    reward_values = [float(row["reward"]) for row in reward_rows]
    turnover_values = [float(row["turnover"]) for row in reward_rows]
    exposure_values = [float(row["exposure"]) for row in reward_rows]
    concentration_values = [float(row["concentration"]) for row in reward_rows]
    invalid_count = sum(1 for row in invalid_rows if row["invalid_action"])
    step_count = len(reward_rows)
    metrics = {
        "split": split_label,
        "steps": step_count,
        "position_rows": len(positions_rows),
        "final_equity": env.equity,
        "total_reward": total_reward,
        "mean_daily_reward": _mean(reward_values),
        "total_net_return": env.equity - 1.0,
        "max_drawdown": _max_drawdown(equity_values),
        "mean_turnover": _mean(turnover_values),
        "mean_exposure": _mean(exposure_values),
        "mean_slippage_cost": 0.0,
        "mean_concentration": _mean(concentration_values),
        "invalid_actions": invalid_count,
        "invalid_action_rate": invalid_count / step_count if step_count else 0.0,
        "max_current_drawdown": min((float(row["current_drawdown"]) for row in reward_rows), default=0.0),
    }
    return {
        "metrics": metrics,
        "positions": positions_rows,
        "invalid_actions": invalid_rows,
        "reward_breakdown": reward_rows,
        "state_observations": state_rows,
        "no_trade_opportunity_diagnostics": opportunity_rows,
        "abstention_reasons": abstention_rows,
    }


def _split_rows(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("split")) == split]


def _best_baseline(baseline_metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not baseline_metrics:
        return None
    return max(baseline_metrics, key=lambda row: float(row.get("total_net_return") or 0.0))


def _metric_for_strategy(baseline_metrics: list[dict[str, Any]], strategy: str) -> dict[str, Any] | None:
    for row in baseline_metrics:
        if row.get("strategy") == strategy:
            return row
    return None


def build_policy_baseline_comparison(
    *,
    policy_metrics: dict[str, Any],
    baseline_metrics: list[dict[str, Any]],
    required_strategies: list[str] | None = None,
) -> list[dict[str, Any]]:
    required = required_strategies or FROZEN_BASELINE_STRATEGIES
    rows: list[dict[str, Any]] = []
    policy_total = float(policy_metrics.get("total_net_return") or 0.0)
    policy_mdd = float(policy_metrics.get("max_drawdown") or 0.0)
    policy_turnover = float(policy_metrics.get("mean_turnover") or 0.0)
    policy_concentration = float(policy_metrics.get("mean_concentration") or 0.0)
    for strategy in required:
        baseline = _metric_for_strategy(baseline_metrics, strategy)
        if baseline is None:
            rows.append(
                {
                    "baseline_strategy": strategy,
                    "baseline_status": "MISSING",
                    "comparison_status": "MISSING_BASELINE",
                    "cost_round_trip_bp": ROUND_TRIP_COST_BP,
                }
            )
            continue
        baseline_total = float(baseline.get("total_net_return") or 0.0)
        baseline_mdd = float(baseline.get("max_drawdown") or 0.0)
        baseline_turnover = float(baseline.get("mean_turnover") or 0.0)
        delta_total = policy_total - baseline_total
        rows.append(
            {
                "baseline_strategy": strategy,
                "baseline_family": baseline.get("strategy_family"),
                "baseline_status": "LOADED",
                "comparison_status": "POLICY_BEATS_BASELINE" if delta_total > 0 else "POLICY_UNDERPERFORMS_OR_TIES",
                "policy_strategy": "tabular_q_constrained_daily_portfolio_rl",
                "policy_split": policy_metrics.get("split"),
                "policy_total_net_return": policy_total,
                "policy_nav": 1.0 + policy_total,
                "policy_max_drawdown": policy_mdd,
                "policy_mean_turnover": policy_turnover,
                "policy_mean_concentration": policy_concentration,
                "baseline_total_net_return": baseline_total,
                "baseline_nav": 1.0 + baseline_total,
                "baseline_max_drawdown": baseline_mdd,
                "baseline_mean_turnover": baseline_turnover,
                "baseline_positions": baseline.get("positions"),
                "baseline_delta_total_net_return": delta_total,
                "baseline_delta_nav": delta_total,
                "baseline_delta_max_drawdown": policy_mdd - baseline_mdd,
                "baseline_delta_mean_turnover": policy_turnover - baseline_turnover,
                "cost_round_trip_bp": ROUND_TRIP_COST_BP,
            }
        )
    return rows


def build_policy_nav_rows(reward_rows: list[dict[str, Any]], *, split: str = "val+test") -> list[dict[str, Any]]:
    return [
        {
            "split": row.get("split"),
            "date": row.get("date"),
            "policy_nav": row.get("equity"),
            "policy_reward": row.get("reward"),
            "policy_turnover": row.get("turnover"),
            "policy_concentration": row.get("concentration"),
            "policy_current_drawdown": row.get("current_drawdown"),
        }
        for row in reward_rows
        if row.get("split") == split
    ]


def load_prediction_artifacts(prediction_run_dir: Path | str | None = None) -> dict[str, Any]:
    run_dir = _resolve_prediction_run(prediction_run_dir)
    manifest_path = run_dir / "prediction_manifest.json"
    predictions_path = run_dir / "predictions.csv"
    baseline_metrics_path = run_dir / "baseline_metrics.json"
    verdict_path = run_dir / "verdict.json"
    manifest = _read_json(manifest_path)
    prediction_artifact_hashes = {
        "prediction_manifest": _file_sha256(manifest_path),
        "predictions": _file_sha256(predictions_path),
        "baseline_metrics": _file_sha256(baseline_metrics_path),
        "verdict": _file_sha256(verdict_path),
    }
    declared_hashes = manifest.get("artifact_hashes") if isinstance(manifest.get("artifact_hashes"), dict) else {}
    hash_mismatches = [
        key
        for key in ("predictions", "baseline_metrics", "verdict")
        if declared_hashes.get(key) and declared_hashes.get(key) != prediction_artifact_hashes[key]
    ]
    return {
        "run_dir": run_dir,
        "manifest": manifest,
        "prediction_manifest_sha256": prediction_artifact_hashes["prediction_manifest"],
        "prediction_artifact_hashes": prediction_artifact_hashes,
        "prediction_declared_artifact_hashes": dict(declared_hashes),
        "prediction_artifact_hash_mismatches": hash_mismatches,
        "predictions": _read_csv(predictions_path),
        "baseline_metrics": _read_json(baseline_metrics_path).get("metrics", []),
        "verdict": _read_json(verdict_path),
    }


def _verdict_for_d4(
    *,
    prediction_verdict: dict[str, Any],
    manifest: dict[str, Any],
    eval_metrics: dict[str, Any],
) -> dict[str, Any]:
    d3_status = str(prediction_verdict.get("status") or manifest.get("verdict", {}).get("status") or "UNKNOWN")
    d3_status_normalized = d3_status.upper().replace("_", "-")
    d3_blocked = d3_status_normalized in {"FAIL", "FAILED", "NO-GO", "NOGO", "BLOCK", "BLOCKED", "SKIPPED"}
    gate_dependency = "D3_FAILED_OR_SKIPPED" if d3_blocked else "D3_WATCH_D5_NOT_RUN"
    reasons = [
        "RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM",
        "D5_WALK_FORWARD_NOT_RUN",
        "PRICE_BASIS_UNKNOWN",
        "UNIVERSE_WATCH_HEURISTIC",
        "DAILY_RL_POLICY_IS_RESTRICTED_RESEARCH_PATH",
    ]
    if d3_blocked:
        reasons.append("D3_FAILED_OR_SKIPPED_FORCE_RESEARCH_OVERRIDE")
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "status": "RESEARCH_ONLY",
        "ui_badge": "RESEARCH_ONLY",
        "go_summary_allowed": False,
        "model_build_allowed": False,
        "readiness_status": "D4_RESEARCH_ONLY_DIAGNOSTICS",
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "implementation_unlocked": False,
        "research_override": bool(d3_blocked),
        "gate_dependency": gate_dependency,
        "d3_status": d3_status,
        "d3_status_normalized": d3_status_normalized,
        "requires_before_model_build": [
            "D5 walk-forward folds n>=5",
            "shuffle controls",
            "cost/slippage sensitivity",
            "official/manual universe review",
            "price-basis verification",
        ],
        "invalid_action_rate": eval_metrics.get("invalid_action_rate", 0.0),
        "reasons": reasons,
    }


def run_daily_rl(
    *,
    prediction_run_dir: Path | str | None = None,
    score_column: str = SCORE_COLUMN,
    candidate_limit: int = 20,
    max_positions: int = 5,
    episodes: int = 8,
    seed: int = 7,
    observation_mode: str = OBSERVATION_MODE_V1,
    action_prior_mode: str = "none",
    action_prior_strength: float = 0.0,
    action_filter_mode: str = ACTION_FILTER_MODE_NONE,
) -> dict[str, Any]:
    artifacts = load_prediction_artifacts(prediction_run_dir)
    prediction_rows = artifacts["predictions"]
    baseline_metrics = artifacts["baseline_metrics"]
    run_dir: Path = artifacts["run_dir"]

    split_groups = {
        split: candidates_by_date(_split_rows(prediction_rows, split), score_column=score_column, candidate_limit=candidate_limit)
        for split in ("train", "val", "test")
    }
    q_table, episode_rows = train_tabular_q_policy(
        split_groups["train"],
        episodes=episodes,
        seed=seed,
        max_positions=max_positions,
        observation_mode=observation_mode,
        action_prior_mode=action_prior_mode,
        action_prior_strength=action_prior_strength,
        action_filter_mode=action_filter_mode,
    )

    combined_eval_candidates = {**split_groups["val"], **split_groups["test"]}
    evaluations = [
        evaluate_policy(split_groups["train"], q_table, split_label="train", max_positions=max_positions, observation_mode=observation_mode, action_prior_mode=action_prior_mode, action_prior_strength=action_prior_strength, action_filter_mode=action_filter_mode),
        evaluate_policy(split_groups["val"], q_table, split_label="val", max_positions=max_positions, observation_mode=observation_mode, action_prior_mode=action_prior_mode, action_prior_strength=action_prior_strength, action_filter_mode=action_filter_mode),
        evaluate_policy(split_groups["test"], q_table, split_label="test", max_positions=max_positions, observation_mode=observation_mode, action_prior_mode=action_prior_mode, action_prior_strength=action_prior_strength, action_filter_mode=action_filter_mode),
        evaluate_policy(combined_eval_candidates, q_table, split_label="val+test", max_positions=max_positions, observation_mode=observation_mode, action_prior_mode=action_prior_mode, action_prior_strength=action_prior_strength, action_filter_mode=action_filter_mode),
    ]
    metrics = [evaluation["metrics"] for evaluation in evaluations]
    eval_metric = next(row for row in metrics if row["split"] == "val+test")

    positions: list[dict[str, Any]] = []
    invalid_actions: list[dict[str, Any]] = []
    reward_breakdown: list[dict[str, Any]] = []
    state_observations: list[dict[str, Any]] = []
    no_trade_opportunity_diagnostics: list[dict[str, Any]] = []
    abstention_reasons: list[dict[str, Any]] = []
    for evaluation in evaluations:
        positions.extend(evaluation["positions"])
        invalid_actions.extend(evaluation["invalid_actions"])
        reward_breakdown.extend(evaluation["reward_breakdown"])
        state_observations.extend(evaluation["state_observations"])
        no_trade_opportunity_diagnostics.extend(evaluation["no_trade_opportunity_diagnostics"])
        abstention_reasons.extend(evaluation["abstention_reasons"])

    learning_curve = build_learning_curve(episode_rows)
    action_distribution = build_action_distribution(invalid_actions)
    turnover_rows = build_turnover_rows(reward_breakdown)
    drawdown_rows = build_drawdown_rows(reward_breakdown)
    reward_component_summary = build_reward_component_summary(reward_breakdown)
    policy_baseline_comparison = build_policy_baseline_comparison(policy_metrics=eval_metric, baseline_metrics=baseline_metrics)
    policy_nav = build_policy_nav_rows(reward_breakdown)
    reward_action_ablations = build_reward_action_ablations(reward_breakdown, invalid_actions)
    no_trade_opportunity_summary = build_no_trade_opportunity_summary(no_trade_opportunity_diagnostics)
    reward_action_ablation_summary = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "guardrail": "Reward/action ablations are diagnostics for failure analysis only; they are not retuning, profit, live, broker, order, or deployable model evidence.",
        "ablation_count": len(reward_action_ablations),
        "ablation_names": sorted({str(row.get("ablation")) for row in reward_action_ablations}),
        "splits": sorted({str(row.get("split")) for row in reward_action_ablations}),
        "cost_round_trip_bp": ROUND_TRIP_COST_BP,
    }
    source_hashes = _source_hashes()
    clean_action_filter_mode = _clean_action_filter_mode(action_filter_mode)
    policy_type = (
        "tabular_q_trade_quality_filter_v1"
        if clean_action_filter_mode not in {ACTION_FILTER_MODE_NONE, ACTION_FILTER_MODE_DISABLED, ACTION_FILTER_MODE_PRIOR_DISABLED_CONTROL}
        else "tabular_q_action_prior_v2"
        if action_prior_mode != "none"
        else "tabular_q"
    )

    best = _best_baseline(baseline_metrics)
    equal_weight = _metric_for_strategy(baseline_metrics, "equal_weight_topk_momentum")
    no_trade = _metric_for_strategy(baseline_metrics, "no_trade_cash")
    baseline_total = float(best.get("total_net_return") or 0.0) if best else 0.0
    baseline_comparison = {
        "policy_strategy": policy_type,
        "policy_split": "val+test",
        "policy_total_net_return": eval_metric["total_net_return"],
        "policy_max_drawdown": eval_metric["max_drawdown"],
        "policy_mean_turnover": eval_metric["mean_turnover"],
        "best_d3_strategy": best.get("strategy") if best else None,
        "best_d3_total_net_return": baseline_total,
        "delta_vs_best_d3_total_net_return": eval_metric["total_net_return"] - baseline_total,
        "equal_weight_topk_total_net_return": (equal_weight or {}).get("total_net_return"),
        "no_trade_cash_total_net_return": (no_trade or {}).get("total_net_return"),
        "cost_round_trip_bp": ROUND_TRIP_COST_BP,
        "slippage_assumption": "No separate daily slippage model is inferred from OHLCV; use 23bp round-trip cost and D5 sensitivity before any model-build claim.",
        "comparison_note": "D4 is research-only and cannot unlock model build without D5 forward validation.",
        "required_frozen_baselines": list(FROZEN_BASELINE_STRATEGIES),
        "missing_frozen_baselines": [row["baseline_strategy"] for row in policy_baseline_comparison if row.get("baseline_status") == "MISSING"],
        "frozen_baseline_comparison": policy_baseline_comparison,
    }

    observation_manifest = build_observation_manifest(
        max_positions=max_positions,
        score_column=score_column,
        candidate_limit=candidate_limit,
        observation_mode=observation_mode,
        action_prior_mode=action_prior_mode,
        action_prior_strength=action_prior_strength,
        action_filter_mode=clean_action_filter_mode,
    )
    observation_manifest_validation = validate_observation_manifest(observation_manifest)

    verdict = _verdict_for_d4(
        prediction_verdict=artifacts["verdict"],
        manifest=artifacts["manifest"],
        eval_metrics=eval_metric,
    )
    manifest = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "guardrail": RESEARCH_GUARDRAIL,
        "prediction_run_dir": str(run_dir),
        "prediction_manifest_sha": artifacts["prediction_manifest_sha256"],
        "prediction_artifact_hashes": artifacts["prediction_artifact_hashes"],
        "prediction_declared_artifact_hashes": artifacts["prediction_declared_artifact_hashes"],
        "prediction_artifact_hash_mismatches": artifacts["prediction_artifact_hash_mismatches"],
        "source_hashes": source_hashes,
        "prediction_verdict_status": artifacts["verdict"].get("status"),
        "score_column": score_column,
        "action_space": ACTION_NAMES,
        "invalid_action_constraint": "mask_valid_actions_only; invalid_action_rate is still emitted as a guardrail metric",
        "candidate_limit": max(1, int(candidate_limit)),
        "max_positions": max(1, int(max_positions)),
        "episodes": int(episodes),
        "seed": int(seed),
        "observation_mode": observation_mode,
        "policy_type": policy_type,
        "action_prior_mode": action_prior_mode,
        "action_prior_strength": float(action_prior_strength),
        "action_filter_mode": clean_action_filter_mode,
        "trade_quality_filter_thresholds": dict(TRADE_QUALITY_FILTER_THRESHOLDS),
        "cost_assumption_round_trip_bp": ROUND_TRIP_COST_BP,
        "slippage_assumption": "No separate daily slippage model is inferred from OHLCV; use 23bp round-trip cost and D5 sensitivity before any model-build claim.",
        "price_basis": artifacts["manifest"].get("price_basis") or PRICE_BASIS,
        "price_basis_evidence": artifacts["manifest"].get("price_basis_evidence") or PRICE_BASIS_EVIDENCE,
        "universe_review_status": artifacts["manifest"].get("universe_review_status"),
        "no_live_broker_order_readiness": True,
        "go_summary_allowed": False,
        "model_build_allowed": False,
        "paper_forward_allowed": False,
        "live_broker_order_allowed": False,
        "readiness_status": "D4_RESEARCH_ONLY_DIAGNOSTICS",
        "observation_manifest": observation_manifest,
        "observation_manifest_validation": observation_manifest_validation,
        "state_contract_status": observation_manifest_validation["status"],
        "row_counts": {
            "prediction_rows": len(prediction_rows),
            "position_rows": len(positions),
            "reward_rows": len(reward_breakdown),
            "invalid_action_rows": len(invalid_actions),
            "state_observation_rows": len(state_observations),
            "q_policy_rows": len(q_table),
            "learning_curve_rows": len(learning_curve),
            "action_distribution_rows": len(action_distribution),
            "turnover_rows": len(turnover_rows),
            "drawdown_rows": len(drawdown_rows),
            "policy_baseline_comparison_rows": len(policy_baseline_comparison),
            "policy_nav_rows": len(policy_nav),
            "reward_action_ablation_rows": len(reward_action_ablations),
            "no_trade_opportunity_diagnostic_rows": len(no_trade_opportunity_diagnostics),
            "abstention_reason_rows": len(abstention_reasons),
        },
        "telemetry": {
            "status": "READY_RESEARCH_ONLY",
            "training_status": "TABULAR_Q_TELEMETRY_RECORDED",
            "visualization_stack": ["csv_artifacts", "flask_api_payload", "svelte_dashboard_cards", "plotly_compatible_series"],
            "state_contract": "D4_OBSERVATION_STATE_MANIFEST_REQUIRED",
            "canonical_artifacts": [
                "observation_manifest.json",
                "state_observations.csv",
                "training_manifest.json",
                "episode_metrics.csv",
                "learning_curve.csv",
                "reward_breakdown.csv",
                "reward_component_summary.json",
                "action_distribution.csv",
                "invalid_actions.csv",
                "turnover.csv",
                "drawdown.csv",
                "policy_baseline_comparison.csv",
                "policy_nav.csv",
                "reward_action_ablations.csv",
                "reward_action_ablation_summary.json",
                "no_trade_opportunity_diagnostics.csv",
                "no_trade_opportunity_summary.json",
                "abstention_reasons.csv",
                "source_hashes.json",
            ],
            "tensorboard_status": "NOT_EMITTED_DEPENDENCY_FREE_TABULAR_Q_RUN",
            "sb3_monitor_status": "NOT_EMITTED_NON_SB3_TABULAR_Q_RUN",
            "guardrail": "Telemetry visualizes learning/accounting diagnostics only; no profit, live, broker, order, or deployable model claim.",
        },
        "verdict": verdict,
    }
    return {
        "manifest": manifest,
        "observation_manifest": observation_manifest,
        "observation_manifest_validation": observation_manifest_validation,
        "policy_metrics": {"metrics": metrics, "training_episodes": episode_rows, "q_policy_rows": _serialize_q_table(q_table)},
        "episode_metrics": episode_rows,
        "positions": positions,
        "invalid_actions": invalid_actions,
        "reward_breakdown": reward_breakdown,
        "state_observations": state_observations,
        "learning_curve": learning_curve,
        "action_distribution": action_distribution,
        "turnover": turnover_rows,
        "drawdown": drawdown_rows,
        "reward_component_summary": reward_component_summary,
        "reward_action_ablations": reward_action_ablations,
        "reward_action_ablation_summary": reward_action_ablation_summary,
        "no_trade_opportunity_diagnostics": no_trade_opportunity_diagnostics,
        "no_trade_opportunity_summary": no_trade_opportunity_summary,
        "abstention_reasons": abstention_reasons,
        "policy_baseline_comparison": policy_baseline_comparison,
        "policy_nav": policy_nav,
        "baseline_comparison": baseline_comparison,
        "source_hashes": source_hashes,
        "verdict": verdict,
    }


def write_rl_artifacts(
    result: dict[str, Any],
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_root or DEFAULT_PORTFOLIO_ROOT).resolve()
    default_root = DEFAULT_PORTFOLIO_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV portfolio artifacts must stay under webui/rl_runs/daily_ohlcv_portfolio")
    rid = _validate_run_id(run_id or f"portfolio_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out_dir = (root / rid).resolve()
    out_dir.relative_to(root)
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Portfolio artifact run_id already exists: {rid}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "rl_manifest": out_dir / "rl_manifest.json",
        "observation_manifest": out_dir / "observation_manifest.json",
        "training_manifest": out_dir / "training_manifest.json",
        "policy_metrics": out_dir / "policy_metrics.json",
        "episode_metrics": out_dir / "episode_metrics.csv",
        "positions": out_dir / "positions.csv",
        "invalid_actions": out_dir / "invalid_actions.csv",
        "reward_breakdown": out_dir / "reward_breakdown.csv",
        "state_observations": out_dir / "state_observations.csv",
        "learning_curve": out_dir / "learning_curve.csv",
        "action_distribution": out_dir / "action_distribution.csv",
        "turnover": out_dir / "turnover.csv",
        "drawdown": out_dir / "drawdown.csv",
        "reward_component_summary": out_dir / "reward_component_summary.json",
        "reward_action_ablations": out_dir / "reward_action_ablations.csv",
        "reward_action_ablation_summary": out_dir / "reward_action_ablation_summary.json",
        "no_trade_opportunity_diagnostics": out_dir / "no_trade_opportunity_diagnostics.csv",
        "no_trade_opportunity_summary": out_dir / "no_trade_opportunity_summary.json",
        "abstention_reasons": out_dir / "abstention_reasons.csv",
        "source_hashes": out_dir / "source_hashes.json",
        "policy_baseline_comparison": out_dir / "policy_baseline_comparison.csv",
        "policy_nav": out_dir / "policy_nav.csv",
        "policy_evaluation_manifest": out_dir / "policy_evaluation_manifest.json",
        "baseline_comparison": out_dir / "baseline_comparison.json",
        "verdict": out_dir / "verdict.json",
    }
    manifest = {**result["manifest"], "run_id": rid, "artifact_dir": str(out_dir), "artifacts": {key: str(path) for key, path in paths.items()}}
    _write_json(paths["rl_manifest"], manifest)
    _write_json(paths["training_manifest"], manifest)
    _write_json(paths["observation_manifest"], {**result["observation_manifest"], "run_id": rid})
    _write_json(paths["policy_metrics"], result["policy_metrics"])
    _write_json(paths["baseline_comparison"], result["baseline_comparison"])
    _write_json(paths["verdict"], result["verdict"])
    _write_csv(paths["episode_metrics"], result["episode_metrics"], ["episode", "total_reward", "steps", "final_equity", "invalid_actions"])
    _write_csv(paths["learning_curve"], result["learning_curve"], ["episode", "total_reward", "rolling_mean_reward", "best_total_reward", "steps", "final_equity", "invalid_actions", "invalid_action_rate"])
    _write_csv(paths["positions"], result["positions"], ["split", "date", "rank", "code", "action", "equity"])
    _write_csv(
        paths["invalid_actions"],
        result["invalid_actions"],
        [
            "split",
            "date",
            "action",
            "requested_action",
            "executed_action",
            "invalid_action",
            "invalid_action_reason",
            "no_trade_action",
            "action_mask_hold_buy_add_sell_reduce",
            "mask_reason_hold",
            "mask_reason_buy",
            "mask_reason_add",
            "mask_reason_sell",
            "mask_reason_reduce",
        ],
    )
    _write_csv(
        paths["reward_breakdown"],
        result["reward_breakdown"],
        [
            "split",
            "date",
            "action",
            "requested_action",
            "executed_action",
            "invalid_action",
            "invalid_action_reason",
            "no_trade_action",
            "gross_return",
            "cost",
            "net_return_after_cost",
            "slippage_cost",
            "turnover",
            "exposure",
            "concentration",
            "exposure_penalty",
            "concentration_penalty",
            "invalid_action_penalty",
            "churn_penalty",
            "drawdown_penalty",
            "no_trade_hold_reward",
            "current_drawdown",
            "reward_before_drawdown_penalty",
            "missing_reward_label_count",
            "reward",
            "equity",
            "mask_reason_hold",
            "mask_reason_buy",
            "mask_reason_add",
            "mask_reason_sell",
            "mask_reason_reduce",
        ],
    )
    _write_csv(
        paths["state_observations"],
        result["state_observations"],
        [
            "split",
            "date",
            "observation_position_count",
            "observation_top_score_bucket",
            "observation_score_margin_bucket",
            "observation_candidate_count_bucket",
            "observation_recent_score_volatility_bucket",
            "observation_d3_confidence_bucket",
            "observation_mode",
            "observation_state_key",
            "cash_fraction",
            "exposure_fraction",
            "held_codes",
            "candidate_count",
            "top_candidate_code",
            "top_candidate_rank",
            "top_candidate_score",
            "top_candidate_reward_label_available",
            "action_mask_hold_buy_add_sell_reduce",
            "future_label_exposed",
            "action_prior_mode",
            "action_prior_strength",
            "policy_value_hold",
            "policy_value_buy",
            "policy_value_add",
            "policy_value_sell",
            "policy_value_reduce",
            "action_prior_hold",
            "action_prior_buy",
            "action_prior_add",
            "action_prior_sell",
            "action_prior_reduce",
            "policy_score_hold",
            "policy_score_buy",
            "policy_score_add",
            "policy_score_sell",
            "policy_score_reduce",
            "mask_reason_hold",
            "mask_reason_buy",
            "mask_reason_add",
            "mask_reason_sell",
            "mask_reason_reduce",
        ],
    )
    _write_csv(
        paths["action_distribution"],
        result["action_distribution"],
        [
            "split",
            "action",
            "requested_action",
            "executed_action",
            "invalid_action",
            "invalid_action_reason",
            "no_trade_action",
            "count",
            "action_rate",
        ],
    )
    _write_csv(
        paths["turnover"],
        result["turnover"],
        [
            "split",
            "date",
            "action",
            "requested_action",
            "executed_action",
            "invalid_action_reason",
            "no_trade_action",
            "turnover",
            "turnover_cost",
            "net_return_after_cost",
            "churn_penalty",
            "reward",
            "equity",
        ],
    )
    _write_csv(
        paths["drawdown"],
        result["drawdown"],
        [
            "split",
            "date",
            "action",
            "requested_action",
            "executed_action",
            "invalid_action_reason",
            "no_trade_action",
            "equity",
            "current_drawdown",
            "drawdown_penalty",
            "reward_before_drawdown_penalty",
            "reward",
        ],
    )
    _write_json(paths["reward_component_summary"], result["reward_component_summary"])
    _write_csv(
        paths["reward_action_ablations"],
        result["reward_action_ablations"],
        [
            "split",
            "ablation_family",
            "ablation",
            "description",
            "rows",
            "total_reward",
            "mean_reward",
            "delta_vs_recorded_reward",
            "action_rows",
            "invalid_action_count",
            "invalid_action_rate",
            "no_trade_action_count",
            "no_trade_action_rate",
            "cost_round_trip_bp",
        ],
    )
    _write_json(paths["reward_action_ablation_summary"], result["reward_action_ablation_summary"])
    _write_csv(
        paths["no_trade_opportunity_diagnostics"],
        result["no_trade_opportunity_diagnostics"],
        [
            "split",
            "date",
            "action",
            "requested_action",
            "executed_action",
            "no_trade_action",
            "observation_position_count",
            "candidate_count",
            "top_candidate_code",
            "top_candidate_score",
            "top_candidate_reward_label_available",
            "top_candidate_future_return_1d",
            "top_candidate_entry_cost",
            "top_candidate_net_after_entry_cost",
            "no_trade_opportunity_flag",
            "no_trade_risk_avoided_flag",
            "diagnostic",
            "diagnostic_future_label_exposed",
            "future_label_used_for_training_state",
            "guardrail",
        ],
    )
    _write_json(paths["no_trade_opportunity_summary"], result["no_trade_opportunity_summary"])
    _write_csv(
        paths["abstention_reasons"],
        result["abstention_reasons"],
        [
            "split",
            "date",
            "action_filter_mode",
            "action_filter_enabled",
            "action_filter_reason",
            "entry_filter_passed",
            "blocked_entry_actions",
            "entry_abstained_by_filter",
            "selected_action",
            "requested_action",
            "executed_action",
            "base_action_mask_hold_buy_add_sell_reduce",
            "filtered_action_mask_hold_buy_add_sell_reduce",
            "base_buy_valid",
            "base_add_valid",
            "filtered_buy_valid",
            "filtered_add_valid",
            "observation_d3_confidence_bucket",
            "observation_score_margin_bucket",
            "observation_recent_score_volatility_bucket",
            "future_label_exposed",
            "guardrail",
            "filter_reason_hold",
            "filter_reason_buy",
            "filter_reason_add",
            "filter_reason_sell",
            "filter_reason_reduce",
        ],
    )
    _write_json(
        paths["source_hashes"],
        {
            "schema_version": PORTFOLIO_SCHEMA_VERSION,
            "source_hashes": result["source_hashes"],
            "guardrail": "Source hashes provide provenance for research-only D4 telemetry, not model-build or live-readiness evidence.",
        },
    )
    _write_csv(paths["policy_baseline_comparison"], result["policy_baseline_comparison"], ["baseline_strategy", "baseline_family", "baseline_status", "comparison_status", "policy_strategy", "policy_split", "policy_total_net_return", "policy_nav", "policy_max_drawdown", "policy_mean_turnover", "policy_mean_concentration", "baseline_total_net_return", "baseline_nav", "baseline_max_drawdown", "baseline_mean_turnover", "baseline_positions", "baseline_delta_total_net_return", "baseline_delta_nav", "baseline_delta_max_drawdown", "baseline_delta_mean_turnover", "cost_round_trip_bp"])
    _write_csv(paths["policy_nav"], result["policy_nav"], ["split", "date", "policy_nav", "policy_reward", "policy_turnover", "policy_concentration", "policy_current_drawdown"])
    _write_json(
        paths["policy_evaluation_manifest"],
        {
            "schema_version": PORTFOLIO_SCHEMA_VERSION,
            "run_id": rid,
            "status": result["verdict"].get("status"),
            "readiness_status": result["verdict"].get("readiness_status"),
            "guardrail": RESEARCH_GUARDRAIL,
            "required_frozen_baselines": list(FROZEN_BASELINE_STRATEGIES),
            "missing_frozen_baselines": result["baseline_comparison"].get("missing_frozen_baselines", []),
            "policy_split": "val+test",
            "policy_type": result["manifest"].get("policy_type"),
            "observation_mode": result["manifest"].get("observation_mode"),
            "action_prior_mode": result["manifest"].get("action_prior_mode"),
            "action_prior_strength": result["manifest"].get("action_prior_strength"),
            "action_filter_mode": result["manifest"].get("action_filter_mode"),
            "observation_fields": [
                field.get("name")
                for field in result["observation_manifest"].get("observation_fields", [])
                if isinstance(field, dict)
            ],
            "cost_round_trip_bp": ROUND_TRIP_COST_BP,
            "policy_baseline_comparison_rows": len(result["policy_baseline_comparison"]),
            "policy_nav_rows": len(result["policy_nav"]),
            "reward_action_ablation_rows": len(result["reward_action_ablations"]),
            "no_trade_opportunity_diagnostic_rows": len(result["no_trade_opportunity_diagnostics"]),
            "abstention_reason_rows": len(result["abstention_reasons"]),
            "source_hashes": result["source_hashes"],
            "model_build_allowed": False,
            "go_summary_allowed": False,
            "paper_forward_allowed": False,
            "live_broker_order_allowed": False,
            "no_live_broker_order_readiness": True,
        },
    )
    artifact_hashes = {
        key: _file_sha256(path)
        for key, path in paths.items()
        if key not in {"rl_manifest", "training_manifest"}
    }
    manifest["artifact_hashes"] = artifact_hashes
    _write_json(paths["rl_manifest"], manifest)
    _write_json(paths["training_manifest"], manifest)
    rl_manifest_sha = _file_sha256(paths["rl_manifest"])
    training_manifest_sha = _file_sha256(paths["training_manifest"])
    return {
        "run_id": rid,
        "artifact_dir": str(out_dir),
        "rl_manifest_sha256": rl_manifest_sha,
        "training_manifest_sha256": training_manifest_sha,
        "artifact_hashes": {
            **artifact_hashes,
            "rl_manifest": rl_manifest_sha,
            "training_manifest": training_manifest_sha,
        },
        **{f"{key}_path": str(path) for key, path in paths.items()},
    }


def run_and_write_daily_rl(
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    result = run_daily_rl(**kwargs)
    written = write_rl_artifacts(result, run_id=run_id, artifact_root=artifact_root, overwrite=overwrite)
    return {"result": result, "written": written}


__all__ = [
    "build_action_prior_values",
    "build_action_filter_decision",
    "build_action_distribution",
    "build_drawdown_rows",
    "build_learning_curve",
    "build_reward_component_summary",
    "build_reward_action_ablations",
    "build_no_trade_opportunity_summary",
    "build_policy_baseline_comparison",
    "build_policy_nav_rows",
    "build_turnover_rows",
    "DEFAULT_PORTFOLIO_ROOT",
    "PORTFOLIO_SCHEMA_VERSION",
    "SCORE_COLUMN",
    "evaluate_policy",
    "load_prediction_artifacts",
    "run_and_write_daily_rl",
    "run_daily_rl",
    "train_tabular_q_policy",
    "write_rl_artifacts",
]
