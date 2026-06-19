"""Constrained daily portfolio environment for research-only D4 experiments."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTION_NAMES = {
    0: "hold",
    1: "buy",
    2: "add",
    3: "sell",
    4: "reduce",
}
ROUND_TRIP_COST_RATE = 23 / 10_000.0
ROUND_TRIP_COST_BP = 23
FILL_ASSUMPTION = "close_to_next_close_research_label; no live/broker/order fill is inferred from daily OHLCV"
DEFAULT_ENV_INSPECTION_ROOT = Path("webui") / "rl_runs" / "daily_ohlcv_portfolio_env"
ENV_INSPECTION_SCHEMA_VERSION = 1
OBSERVATION_MANIFEST_SCHEMA_VERSION = 2
OBSERVATION_MODE_V1 = "v1"
OBSERVATION_MODE_ACTION_INDUCTION_V2 = "action_induction_v2"
VALID_OBSERVATION_MODES = {OBSERVATION_MODE_V1, OBSERVATION_MODE_ACTION_INDUCTION_V2}
OBSERVATION_STATE_FIELDS = ["position_count", "top_score_bucket"]
ACTION_INDUCTION_V2_STATE_FIELDS = [
    "position_count",
    "top_score_bucket",
    "score_margin_bucket",
    "candidate_count_bucket",
    "recent_score_volatility_bucket",
    "d3_confidence_bucket",
]
REQUIRED_OBSERVATION_MANIFEST_SECTIONS = [
    "feature_timing",
    "holdings_identity",
    "cash_exposure",
    "candidate_rank_score_features",
    "horizon_alignment",
    "action_mask_semantics",
    "leakage_checks",
    "frozen_d3_comparison",
]
FROZEN_D3_COMPARISON_REQUIREMENTS = [
    "no_trade_cash",
    "shuffle_control",
    "equal_weight_topk_momentum",
    "vol_adjusted_momentum",
    "supervised_linear_ranker",
    "supervised_direction_classifier",
]
FUTURE_LABEL_COLUMNS = ["future_return", "future_return_1d"]
REQUIRED_LEAKAGE_CHECKS = [
    "future_return_1d_excluded_from_state",
    "future_return_1d_excluded_from_action_mask",
    "future_label_availability_not_candidate_filter",
    "reward_label_post_action_only",
    "leading_zero_code_identity",
]
SAFE_RUN_RE = re.compile(r"^[0-9A-Za-z_.-]+$")


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None
def _bucket_by_threshold(value: float | None, thresholds: tuple[float, ...]) -> int:
    if value is None:
        return 0
    clean = abs(float(value))
    for index, threshold in enumerate(thresholds, start=1):
        if clean < threshold:
            return index
    return len(thresholds) + 1


def _score_sign_bucket(score: float | None) -> int:
    if score is None:
        return 0
    return 1 if score > 0 else -1 if score < 0 else 0


def _validate_observation_mode(observation_mode: str) -> str:
    mode = str(observation_mode or OBSERVATION_MODE_V1)
    if mode not in VALID_OBSERVATION_MODES:
        raise ValueError(f"Unsupported observation_mode: {mode}")
    return mode


def _observation_fields_for_mode(observation_mode: str) -> list[str]:
    mode = _validate_observation_mode(observation_mode)
    if mode == OBSERVATION_MODE_ACTION_INDUCTION_V2:
        return list(ACTION_INDUCTION_V2_STATE_FIELDS)
    return list(OBSERVATION_STATE_FIELDS)



def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    if not SAFE_RUN_RE.match(rid) or rid in {".", ".."} or "/" in rid or "\\" in rid:
        raise ValueError("run_id contains unsafe characters")
    return rid


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


def _action_mask_payload(mask: list[bool]) -> dict[str, bool]:
    return {ACTION_NAMES[index]: bool(value) for index, value in enumerate(mask)}
def _action_mask_reason(valid: bool, valid_reason: str, invalid_reason: str) -> str:
    return valid_reason if valid else invalid_reason


@dataclass(frozen=True)
class DailyCandidate:
    date: str
    code: str
    split: str
    score: float
    future_return: float | None
    reward_label_available: bool


def candidates_by_date(rows: list[dict[str, Any]], *, score_column: str, candidate_limit: int = 20) -> dict[str, list[DailyCandidate]]:
    grouped: dict[str, list[DailyCandidate]] = {}
    for row in rows:
        score = _safe_float(row.get(score_column))
        future_return = _safe_float(row.get("future_return_1d"))
        if score is None:
            continue
        candidate = DailyCandidate(
            date=str(row.get("date")),
            code=str(row.get("code") or "").zfill(6),
            split=str(row.get("split")),
            score=score,
            future_return=future_return,
            reward_label_available=future_return is not None,
        )
        grouped.setdefault(candidate.date, []).append(candidate)
    limit = max(1, int(candidate_limit))
    return {
        date: sorted(items, key=lambda item: item.score, reverse=True)[:limit]
        for date, items in sorted(grouped.items())
    }


class DailyPortfolioEnv:
    """A minimal constrained portfolio environment over daily candidate slots."""

    action_names = ACTION_NAMES

    def __init__(
        self,
        candidates: dict[str, list[DailyCandidate]],
        *,
        max_positions: int = 5,
        cost_rate: float = ROUND_TRIP_COST_RATE,
        invalid_action_penalty: float = 0.001,
        exposure_penalty: float = 0.00005,
        concentration_penalty: float = 0.00005,
        drawdown_penalty: float = 0.01,
        churn_penalty: float = 0.00002,
        fill_assumption: str = FILL_ASSUMPTION,
        observation_mode: str = OBSERVATION_MODE_V1,
    ) -> None:
        self.candidates = candidates
        self.dates = sorted(candidates)
        self.max_positions = max(1, int(max_positions))
        self.cost_rate = float(cost_rate)
        self.invalid_action_penalty = float(invalid_action_penalty)
        self.exposure_penalty = float(exposure_penalty)
        self.concentration_penalty = float(concentration_penalty)
        self.drawdown_penalty = float(drawdown_penalty)
        self.churn_penalty = float(churn_penalty)
        self.fill_assumption = fill_assumption
        self.observation_mode = _validate_observation_mode(observation_mode)
        self.observation_state_fields = _observation_fields_for_mode(self.observation_mode)
        self.reset()

    def reset(self) -> tuple[int, ...]:
        self.index = 0
        self.positions: list[str] = []
        self.equity = 1.0
        self.peak_equity = 1.0
        self.current_drawdown = 0.0
        self.invalid_actions = 0
        self.steps = 0
        return self.state()

    def _recent_score_volatility_bucket(self, *, lookback: int = 5) -> int:
        if self.index <= 0:
            return 0
        prior_dates = self.dates[max(0, self.index - int(lookback)) : self.index]
        top_scores = [
            self.candidates[date][0].score
            for date in prior_dates
            if self.candidates.get(date)
        ]
        if len(top_scores) < 2:
            return 0
        mean_score = sum(top_scores) / len(top_scores)
        variance = sum((score - mean_score) ** 2 for score in top_scores) / len(top_scores)
        return _bucket_by_threshold(math.sqrt(variance), (0.001, 0.005, 0.02))

    def state_details(self) -> dict[str, int | str]:
        candidates = self._current_candidates()
        top_score = candidates[0].score if candidates else None
        second_score = candidates[1].score if len(candidates) > 1 else None
        score_margin = (top_score - second_score) if top_score is not None and second_score is not None else top_score
        details: dict[str, int | str] = {
            "observation_mode": self.observation_mode,
            "position_count": len(self.positions),
            "top_score_bucket": _score_sign_bucket(top_score),
        }
        if self.observation_mode == OBSERVATION_MODE_ACTION_INDUCTION_V2:
            details.update(
                {
                    "score_margin_bucket": _bucket_by_threshold(score_margin, (0.001, 0.005, 0.02)),
                    "candidate_count_bucket": 0
                    if not candidates
                    else 1
                    if len(candidates) == 1
                    else 2
                    if len(candidates) <= 4
                    else 3,
                    "recent_score_volatility_bucket": self._recent_score_volatility_bucket(),
                    "d3_confidence_bucket": _bucket_by_threshold(top_score, (0.001, 0.005, 0.02)),
                }
            )
        return details

    def state(self) -> tuple[int, ...]:
        details = self.state_details()
        return tuple(int(details[field]) for field in self.observation_state_fields)

    def done(self) -> bool:
        return self.index >= len(self.dates)

    def _current_candidates(self) -> list[DailyCandidate]:
        if self.done():
            return []
        return self.candidates.get(self.dates[self.index], [])

    def action_mask_details(self) -> dict[str, dict[str, Any]]:
        candidates = self._current_candidates()
        has_new_candidate = any(candidate.code not in self.positions for candidate in candidates)
        has_position = bool(self.positions)
        max_reached = len(self.positions) >= self.max_positions
        details = {
            "hold": {
                "valid": True,
                "reason": "always_valid_no_trade_or_hold",
            },
            "buy": {
                "valid": not has_position and has_new_candidate,
                "reason": _action_mask_reason(
                    not has_position and has_new_candidate,
                    "flat_portfolio_has_new_candidate",
                    "blocked_existing_position" if has_position else "blocked_no_new_candidate",
                ),
            },
            "add": {
                "valid": has_position and not max_reached and has_new_candidate,
                "reason": _action_mask_reason(
                    has_position and not max_reached and has_new_candidate,
                    "has_position_capacity_and_new_candidate",
                    "blocked_no_position" if not has_position else "blocked_max_positions" if max_reached else "blocked_no_new_candidate",
                ),
            },
            "sell": {
                "valid": has_position,
                "reason": _action_mask_reason(has_position, "has_position_to_sell", "blocked_no_position"),
            },
            "reduce": {
                "valid": len(self.positions) > 1,
                "reason": _action_mask_reason(len(self.positions) > 1, "multiple_positions_to_reduce", "blocked_requires_multiple_positions"),
            },
        }
        return details

    def action_mask(self) -> list[bool]:
        details = self.action_mask_details()
        return [bool(details[ACTION_NAMES[index]]["valid"]) for index in sorted(ACTION_NAMES)]


    def choose_first_new_candidate(self) -> str | None:
        for candidate in self._current_candidates():
            if candidate.code not in self.positions:
                return candidate.code
        return None

    def step(self, action: int) -> tuple[tuple[int, ...], float, bool, dict[str, Any]]:
        if self.done():
            raise StopIteration("Environment is done")
        requested_action = int(action)
        action = requested_action
        details = self.action_mask_details()
        mask = [bool(details[ACTION_NAMES[index]]["valid"]) for index in sorted(ACTION_NAMES)]
        requested_action_name = self.action_names.get(requested_action, "unknown")
        action_name = requested_action_name
        if requested_action not in self.action_names:
            invalid_reason = "unknown_action"
        else:
            invalid_reason = None if mask[requested_action] else str(details[requested_action_name]["reason"])
        invalid = invalid_reason is not None
        previous_positions = list(self.positions)
        if invalid:
            self.invalid_actions += 1
            action = 0
            action_name = "hold"
        elif action in {1, 2}:
            code = self.choose_first_new_candidate()
            if code is not None and len(self.positions) < self.max_positions:
                self.positions.append(code)
        elif action == 3:
            self.positions.clear()
        elif action == 4 and self.positions:
            self.positions.pop()

        returns_by_code = {candidate.code: candidate.future_return for candidate in self._current_candidates()}
        missing_reward_label_codes = [code for code in self.positions if returns_by_code.get(code) is None]
        held_returns = [float(returns_by_code.get(code) or 0.0) for code in self.positions]
        gross_return = sum(held_returns) / len(held_returns) if held_returns else 0.0
        changed = len(set(previous_positions) ^ set(self.positions))
        turnover = min(1.0, changed / self.max_positions)
        cost = turnover * self.cost_rate
        net_return_after_cost = gross_return - cost
        exposure = len(self.positions) / self.max_positions
        concentration = 1.0 / len(self.positions) if self.positions else 0.0
        exposure_cost = exposure * self.exposure_penalty
        concentration_cost = max(0.0, concentration - 0.5) * self.concentration_penalty
        invalid_cost = self.invalid_action_penalty if invalid else 0.0
        churn_cost = turnover * self.churn_penalty
        no_trade_hold_reward = 0.0
        reward_before_drawdown = net_return_after_cost - exposure_cost - concentration_cost - invalid_cost - churn_cost + no_trade_hold_reward
        projected_equity = self.equity * (1.0 + reward_before_drawdown)
        projected_peak = max(self.peak_equity, projected_equity)
        projected_drawdown = projected_equity / projected_peak - 1.0 if projected_peak else 0.0
        drawdown_cost = abs(min(0.0, projected_drawdown)) * self.drawdown_penalty
        reward = reward_before_drawdown - drawdown_cost
        self.equity *= 1.0 + reward
        self.peak_equity = max(self.peak_equity, self.equity)
        self.current_drawdown = self.equity / self.peak_equity - 1.0 if self.peak_equity else 0.0
        date = self.dates[self.index]
        self.index += 1
        self.steps += 1
        no_trade_action = requested_action == 0 and not previous_positions and not self.positions
        info = {
            "date": date,
            "requested_action": requested_action_name,
            "action": action_name,
            "executed_action": action_name,
            "invalid_action": invalid,
            "invalid_action_reason": invalid_reason,
            "no_trade_action": no_trade_action,
            "positions": list(self.positions),
            "gross_return": gross_return,
            "cost": cost,
            "net_return_after_cost": net_return_after_cost,
            "turnover": turnover,
            "exposure": exposure,
            "concentration": concentration,
            "exposure_penalty": exposure_cost,
            "concentration_penalty": concentration_cost,
            "invalid_action_penalty": invalid_cost,
            "churn_penalty": churn_cost,
            "no_trade_hold_reward": no_trade_hold_reward,
            "drawdown_penalty": drawdown_cost,
            "current_drawdown": self.current_drawdown,
            "reward_before_drawdown_penalty": reward_before_drawdown,
            "reward": reward,
            "equity": self.equity,
            "action_mask": _action_mask_payload(mask),
            "action_mask_reasons": {name: str(value["reason"]) for name, value in details.items()},
            "fill_assumption": self.fill_assumption,
            "missing_reward_label_codes": list(missing_reward_label_codes),
            "missing_reward_label_count": len(missing_reward_label_codes),
            "reward_components": {
                "daily_nav_return": gross_return,
                "turnover_cost": cost,
                "net_return_after_cost": net_return_after_cost,
                "exposure_penalty": exposure_cost,
                "concentration_penalty": concentration_cost,
                "invalid_action_penalty": invalid_cost,
                "churn_penalty": churn_cost,
                "drawdown_penalty": drawdown_cost,
                "no_trade_hold_reward": no_trade_hold_reward,
            },
        }
        return self.state(), reward, self.done(), info


def build_observation_manifest(
    *,
    max_positions: int = 5,
    score_column: str = "score_supervised_linear_ranker",
    candidate_limit: int | None = None,
    observation_mode: str = OBSERVATION_MODE_V1,
    action_prior_mode: str = "none",
    action_prior_strength: float = 0.0,
    action_filter_mode: str = "none",
) -> dict[str, Any]:
    """Describe the D4 state contract separately from reward/action telemetry."""

    max_pos = max(1, int(max_positions))
    mode = _validate_observation_mode(observation_mode)
    observation_fields = [
        {
            "name": "position_count",
            "dtype": "int",
            "source": "current positions before action",
            "timing": "t/current/pre_action",
            "leakage_status": "causal",
            "min": 0,
            "max": max_pos,
        },
        {
            "name": "top_score_bucket",
            "dtype": "int",
            "source": f"{score_column} from the current date candidate panel",
            "timing": "t/current/pre_action",
            "leakage_status": "causal",
            "values": [-1, 0, 1],
        },
    ]
    if mode == OBSERVATION_MODE_ACTION_INDUCTION_V2:
        observation_fields.extend(
            [
                {
                    "name": "score_margin_bucket",
                    "dtype": "int",
                    "source": f"top-1 minus top-2 {score_column} within the current date candidate panel",
                    "timing": "t/current/pre_action",
                    "leakage_status": "causal",
                    "values": [0, 1, 2, 3, 4],
                },
                {
                    "name": "candidate_count_bucket",
                    "dtype": "int",
                    "source": "number of current date candidates after score sorting and candidate_limit truncation",
                    "timing": "t/current/pre_action",
                    "leakage_status": "causal",
                    "values": [0, 1, 2, 3],
                },
                {
                    "name": "recent_score_volatility_bucket",
                    "dtype": "int",
                    "source": "past-only rolling volatility of prior top D3 scores; proxy used because raw OHLCV volatility is not present in prediction artifacts",
                    "timing": "t-1/lookback/pre_action",
                    "leakage_status": "causal_past_only_no_current_reward_label",
                    "values": [0, 1, 2, 3, 4],
                },
                {
                    "name": "d3_confidence_bucket",
                    "dtype": "int",
                    "source": f"absolute current top {score_column} magnitude bucket",
                    "timing": "t/current/pre_action",
                    "leakage_status": "causal",
                    "values": [0, 1, 2, 3, 4],
                },
            ]
        )
    state_field_names = [str(field["name"]) for field in observation_fields]
    return {
        "schema_version": OBSERVATION_MANIFEST_SCHEMA_VERSION,
        "status": "PASS_RESEARCH_ONLY_STATE_CONTRACT",
        "gate": "D4_OBSERVATION_STATE_MANIFEST",
        "guardrail": "Observation/state manifest only; no profit guarantee, no live/broker/orders, no deployable model claim.",
        "model_build_allowed": False,
        "go_summary_allowed": False,
        "reward_action_telemetry_sufficient_for_d4": False,
        "observation_mode": mode,
        "observation_shape": [len(observation_fields)],
        "observation_fields": observation_fields,
        "feature_timing": {
            "candidate_scores": "D3 score columns are read from the current date candidate panel before the action.",
            "candidate_rank": "Candidates are sorted by current score descending within the same date before candidate_limit truncation.",
            "score_margin": "score_margin_bucket is derived from current same-date scores only, before reward labels are consumed.",
            "candidate_count": "candidate_count_bucket is derived from current same-date candidate availability after truncation.",
            "recent_score_volatility": "recent_score_volatility_bucket uses prior top-score history only; it does not read current or future reward labels.",
            "d3_confidence": "d3_confidence_bucket is a current-score magnitude bucket, not an outcome label.",
            "holdings": "The current positions list exists before the action for masks/accounting; the compact state exposes position_count.",
            "cash_exposure": "cash_fraction and exposure_fraction are derived from current position_count/max_positions before action.",
            "future_return_1d": "Excluded from current observation and action mask; consumed only after the action for reward accounting or post-policy diagnostics.",
        },
        "holdings_identity": {
            "code_format": "six_digit_string",
            "leading_zero_policy": "zfill(6), never int coercion",
            "tracked_before_action": True,
            "identity_use": "action masks, positions artifact, and portfolio accounting",
            "state_vector_identity_policy": "compact state keeps count only; positions artifact preserves held codes.",
        },
        "cash_exposure": {
            "max_positions": max_pos,
            "state_variables": ["position_count"],
            "derived_before_action": ["cash_fraction", "exposure_fraction"],
            "exposure_formula": "position_count / max_positions",
            "cash_formula": "1 - exposure_fraction",
            "post_action_telemetry": ["exposure", "turnover", "concentration"],
        },
        "candidate_rank_score_features": {
            "score_column": score_column,
            "candidate_limit": candidate_limit,
            "rank_order": "score descending within each date",
            "top_score_bucket": "sign(top current candidate score)",
            "score_margin_bucket": "bucket(top1_score - top2_score) for action_induction_v2; empty when no second candidate",
            "candidate_count_bucket": "0 none, 1 singleton, 2 two-to-four, 3 five-or-more candidates",
            "recent_score_volatility_bucket": "past-only top-score volatility proxy; no current/future outcome labels",
            "d3_confidence_bucket": "bucket(abs(top current candidate score))",
            "score_values_not_target_labels": True,
            "excluded_label_columns": list(FUTURE_LABEL_COLUMNS),
        },
        "action_induction_v2": {
            "enabled": mode == OBSERVATION_MODE_ACTION_INDUCTION_V2,
            "variants": [
                "state_margin_bucket_v1",
                "candidate_count_bucket_v1",
                "recent_volatility_bucket_v1_proxy_no_label",
                "d3_confidence_bucket_v1",
                "action_prior_exploration_v1" if action_prior_mode != "none" else "action_prior_exploration_disabled",
            ],
            "state_fields": state_field_names,
            "action_prior_mode": action_prior_mode,
            "action_prior_strength": float(action_prior_strength),
            "action_filter_mode": action_filter_mode,
            "trade_quality_filter_v1": action_filter_mode not in {"none", "disabled", "prior_disabled_control_v1"},
            "diagnostic_only": True,
            "promotion_status": "NO_GO_RESEARCH_ONLY_UNTIL_D5_PASS",
        },
        "trade_quality_filter": {
            "mode": action_filter_mode,
            "enabled": action_filter_mode not in {"none", "disabled", "prior_disabled_control_v1"},
            "entry_actions_filtered": ["buy", "add"],
            "decision_inputs": ["d3_confidence_bucket", "score_margin_bucket", "recent_score_volatility_bucket"],
            "future_label_policy": "future_return_1d is forbidden for filter selection and allowed only after action for reward/diagnostics.",
            "thresholds": {
                "confidence_min_bucket": 3,
                "margin_min_bucket": 3,
                "risk_volatility_max_bucket": 3,
            },
            "telemetry_artifact": "abstention_reasons.csv",
            "diagnostic_only": True,
            "promotion_status": "NO_GO_RESEARCH_ONLY_UNTIL_D5_PASS",
        },
        "horizon_alignment": {
            "rebalance_clock": "daily date step",
            "reward_label": "future_return_1d",
            "reward_horizon_days": 1,
            "fill_assumption": FILL_ASSUMPTION,
            "policy": "close-to-next-close research label only; no broker/order fill is inferred.",
        },
        "action_mask_semantics": {
            "hold": "always valid before done; represents no-trade when flat and hold/carry when invested",
            "buy": "valid only when no position exists and a new candidate is available",
            "add": "valid when a position exists, max_positions is not reached, and a new candidate is available",
            "sell": "valid when at least one position exists",
            "reduce": "valid when more than one position exists",
            "reason_fields": "action_mask_reasons records the exact valid/blocked reason per action",
        },
        "leakage_checks": [
            {
                "check": "future_return_1d_excluded_from_state",
                "status": "PASS",
                "evidence": f"state() returns declared causal fields only: {', '.join(state_field_names)}.",
            },
            {
                "check": "future_return_1d_excluded_from_action_mask",
                "status": "PASS",
                "evidence": "action_mask() reads current candidates and positions, not reward labels.",
            },
            {
                "check": "future_label_availability_not_candidate_filter",
                "status": "PASS",
                "evidence": "candidates_by_date skips missing scores only; missing future_return_1d stays eligible and is zero-filled only during post-action reward accounting.",
            },
            {
                "check": "reward_label_post_action_only",
                "status": "PASS",
                "evidence": "step() reads candidate.future_return after the action mutates positions.",
            },
            {
                "check": "leading_zero_code_identity",
                "status": "PASS",
                "evidence": "candidates_by_date stores str(code).zfill(6) and position artifacts re-zfill codes.",
            },
        ],
        "frozen_d3_comparison": {
            "required": True,
            "score_column": score_column,
            "baseline_source": "D3 prediction baseline artifacts",
            "required_baselines": list(FROZEN_D3_COMPARISON_REQUIREMENTS),
            "promotion_rule": "D4 cannot be promoted from reward/action telemetry alone; compare to frozen D3 baselines and D5 OOS gates.",
        },
    }


def validate_observation_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a strict gate report for the D4 observation/state manifest."""

    issues: list[str] = []
    missing_sections = [section for section in REQUIRED_OBSERVATION_MANIFEST_SECTIONS if not manifest.get(section)]
    if missing_sections:
        issues.append(f"missing_sections:{','.join(missing_sections)}")

    field_names = [
        str(field.get("name"))
        for field in manifest.get("observation_fields", [])
        if isinstance(field, dict)
    ]
    expected_fields = _observation_fields_for_mode(str(manifest.get("observation_mode") or OBSERVATION_MODE_V1))
    missing_fields = [field for field in expected_fields if field not in field_names]
    if missing_fields:
        issues.append(f"missing_observation_fields:{','.join(missing_fields)}")

    leaked_fields = [
        field
        for field in field_names
        if any(label in field for label in FUTURE_LABEL_COLUMNS)
    ]
    if leaked_fields:
        issues.append(f"future_label_in_observation:{','.join(leaked_fields)}")

    if manifest.get("reward_action_telemetry_sufficient_for_d4") is not False:
        issues.append("reward_action_telemetry_must_not_satisfy_d4")

    d3 = manifest.get("frozen_d3_comparison", {})
    baselines = set(d3.get("required_baselines", [])) if isinstance(d3, dict) else set()
    missing_baselines = [baseline for baseline in FROZEN_D3_COMPARISON_REQUIREMENTS if baseline not in baselines]
    if missing_baselines:
        issues.append(f"missing_frozen_d3_baselines:{','.join(missing_baselines)}")

    leakage_entries = [
        check
        for check in manifest.get("leakage_checks", [])
        if isinstance(check, dict)
    ]
    leakage_names = [str(check.get("check")) for check in leakage_entries]
    duplicate_leakage_checks = sorted({check for check in leakage_names if leakage_names.count(check) > 1})
    missing_leakage_checks = [check for check in REQUIRED_LEAKAGE_CHECKS if check not in leakage_names]
    failing_leakage_checks = [
        str(check.get("check"))
        for check in leakage_entries
        if str(check.get("check")) in REQUIRED_LEAKAGE_CHECKS and str(check.get("status")) != "PASS"
    ]
    if duplicate_leakage_checks:
        issues.append(f"duplicate_leakage_checks:{','.join(duplicate_leakage_checks)}")
    if missing_leakage_checks:
        issues.append(f"missing_leakage_checks:{','.join(missing_leakage_checks)}")
    if failing_leakage_checks:
        issues.append(f"failing_leakage_checks:{','.join(failing_leakage_checks)}")

    return {
        "schema_version": OBSERVATION_MANIFEST_SCHEMA_VERSION,
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "required_sections": list(REQUIRED_OBSERVATION_MANIFEST_SECTIONS),
        "observation_fields": field_names,
        "missing_sections": missing_sections,
        "missing_observation_fields": missing_fields,
        "future_label_fields": leaked_fields,
        "missing_frozen_d3_baselines": missing_baselines,
        "missing_leakage_checks": missing_leakage_checks,
        "failing_leakage_checks": failing_leakage_checks,
        "duplicate_leakage_checks": duplicate_leakage_checks,
        "reward_action_telemetry_sufficient_for_d4": manifest.get("reward_action_telemetry_sufficient_for_d4"),
    }

def environment_contract(
    *,
    max_positions: int = 5,
    score_column: str = "score_supervised_linear_ranker",
    candidate_limit: int | None = None,
    observation_mode: str = OBSERVATION_MODE_V1,
    action_prior_mode: str = "none",
    action_prior_strength: float = 0.0,
) -> dict[str, Any]:
    observation_manifest = build_observation_manifest(
        max_positions=max_positions,
        score_column=score_column,
        candidate_limit=candidate_limit,
        observation_mode=observation_mode,
        action_prior_mode=action_prior_mode,
        action_prior_strength=action_prior_strength,
    )
    observation_validation = validate_observation_manifest(observation_manifest)
    state_fields = _observation_fields_for_mode(observation_mode)
    return {
        "schema_version": ENV_INSPECTION_SCHEMA_VERSION,
        "status": "RESEARCH_ONLY",
        "guardrail": "Daily OHLCV portfolio RL environment evidence only; no profit guarantee, no live/broker/orders.",
        "fill_assumption": FILL_ASSUMPTION,
        "cost_round_trip_bp": ROUND_TRIP_COST_BP,
        "state": {
            "shape": [len(state_fields)],
            "fields": state_fields,
            "lookahead_policy": "state uses current candidate scores, current holdings, and optional past-only score history; future_return labels are consumed only after action for reward accounting",
        },
        "action_space": ACTION_NAMES,
        "action_mask": {
            "hold": "always valid before done; represents no-trade when flat and hold/carry when invested",
            "buy": "valid only when no position exists and a new candidate is available",
            "add": "valid when a position exists, max_positions is not reached, and a new candidate is available",
            "sell": "valid when at least one position exists",
            "reduce": "valid when more than one position exists",
            "reason_fields": "action_mask_reasons records the exact valid/blocked reason per action",
        },
        "reward_formula": "net_return_after_cost - exposure_penalty - concentration_penalty - invalid_action_penalty - churn_penalty - drawdown_penalty + no_trade_hold_reward",
        "reward_components": [
            "daily_nav_return",
            "turnover_cost",
            "net_return_after_cost",
            "exposure_penalty",
            "concentration_penalty",
            "invalid_action_penalty",
            "churn_penalty",
            "drawdown_penalty",
            "no_trade_hold_reward",
        ],
        "max_positions": max(1, int(max_positions)),
        "model_build_allowed": False,
        "observation_manifest": observation_manifest,
        "observation_manifest_validation": observation_validation,
    }


def build_env_inspection(
    candidates: dict[str, list[DailyCandidate]],
    *,
    max_positions: int = 5,
    score_column: str = "score_supervised_linear_ranker",
    candidate_limit: int | None = None,
    scripted_actions: list[int] | None = None,
    observation_mode: str = OBSERVATION_MODE_V1,
    action_prior_mode: str = "none",
    action_prior_strength: float = 0.0,
) -> dict[str, Any]:
    env = DailyPortfolioEnv(candidates, max_positions=max_positions, observation_mode=observation_mode)
    actions = scripted_actions or [1, 2, 0, 4, 3]
    manifest = {
        **environment_contract(max_positions=max_positions, score_column=score_column, candidate_limit=candidate_limit, observation_mode=observation_mode, action_prior_mode=action_prior_mode, action_prior_strength=action_prior_strength),
        "generated_at": _utc_now(),
        "date_count": len(env.dates),
        "candidate_count": sum(len(items) for items in candidates.values()),
        "candidate_dates": list(env.dates),
        "candidate_limit": candidate_limit,
    }
    reward_rows: list[dict[str, Any]] = []
    action_mask_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []
    step = 0
    while not env.done():
        mask = env.action_mask()
        state = env.state()
        state_details = env.state_details()
        current_candidates = env._current_candidates()
        top_candidate = current_candidates[0] if current_candidates else None
        position_count = int(state[0])
        exposure_fraction = position_count / env.max_positions
        cash_fraction = max(0.0, 1.0 - exposure_fraction)
        state_rows.append(
            {
                "step": step + 1,
                "date": env.dates[env.index],
                "observation_position_count": position_count,
                "observation_top_score_bucket": int(state_details["top_score_bucket"]),
                "observation_score_margin_bucket": state_details.get("score_margin_bucket", ""),
                "observation_candidate_count_bucket": state_details.get("candidate_count_bucket", ""),
                "observation_recent_score_volatility_bucket": state_details.get("recent_score_volatility_bucket", ""),
                "observation_d3_confidence_bucket": state_details.get("d3_confidence_bucket", ""),
                "observation_mode": observation_mode,
                "cash_fraction": cash_fraction,
                "exposure_fraction": exposure_fraction,
                "max_positions": env.max_positions,
                "held_codes": "|".join(str(code).zfill(6) for code in env.positions),
                "candidate_count": len(current_candidates),
                "top_candidate_code": str(top_candidate.code).zfill(6) if top_candidate else "",
                "top_candidate_rank": 1 if top_candidate else "",
                "top_candidate_score": top_candidate.score if top_candidate else "",
                "top_candidate_reward_label_available": bool(top_candidate.reward_label_available) if top_candidate else False,
                "score_column": score_column,
                "future_label_exposed": False,
            }
        )
        action = actions[step % len(actions)]
        action_mask_rows.append(
            {
                "step": step + 1,
                "date": env.dates[env.index],
                "requested_action": ACTION_NAMES.get(action, "unknown"),
                **{f"mask_{name}": valid for name, valid in _action_mask_payload(mask).items()},
                **{f"mask_reason_{name}": str(value["reason"]) for name, value in env.action_mask_details().items()},
            }
        )
        _state, _reward, _done, info = env.step(action)
        reward_rows.append(
            {
                "step": step + 1,
                "date": info["date"],
                "requested_action": info["requested_action"],
                "executed_action": info["executed_action"],
                "action": info["action"],
                "invalid_action": info["invalid_action"],
                "invalid_action_reason": info["invalid_action_reason"],
                "no_trade_action": info["no_trade_action"],
                "gross_return": info["gross_return"],
                "turnover_cost": info["cost"],
                "net_return_after_cost": info["net_return_after_cost"],
                "turnover": info["turnover"],
                "exposure": info["exposure"],
                "concentration": info["concentration"],
                "exposure_penalty": info["exposure_penalty"],
                "concentration_penalty": info["concentration_penalty"],
                "invalid_action_penalty": info["invalid_action_penalty"],
                "churn_penalty": info["churn_penalty"],
                "no_trade_hold_reward": info["no_trade_hold_reward"],
                "drawdown_penalty": info["drawdown_penalty"],
                "current_drawdown": info["current_drawdown"],
                "reward": info["reward"],
                "equity": info["equity"],
                "missing_reward_label_count": info["missing_reward_label_count"],
            }
        )
        for rank, code in enumerate(info["positions"], start=1):
            position_rows.append({"step": step + 1, "date": info["date"], "rank": rank, "code": str(code).zfill(6), "action": info["action"]})
        step += 1
    manifest["summary"] = {
        "steps": step,
        "final_equity": env.equity,
        "invalid_actions": env.invalid_actions,
        "current_drawdown": env.current_drawdown,
    }
    return {
        "env_manifest": manifest,
        "observation_manifest": manifest["observation_manifest"],
        "observation_manifest_validation": manifest["observation_manifest_validation"],
        "reward_breakdown": reward_rows,
        "action_masks": action_mask_rows,
        "positions": position_rows,
        "state_observations": state_rows,
    }


def write_env_inspection_artifacts(
    inspection: dict[str, Any],
    *,
    run_id: str | None = None,
    artifact_root: Path | str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(artifact_root or DEFAULT_ENV_INSPECTION_ROOT).resolve()
    default_root = DEFAULT_ENV_INSPECTION_ROOT.resolve()
    try:
        root.relative_to(default_root)
    except ValueError:
        if root != default_root:
            raise ValueError("Daily OHLCV env inspection artifacts must stay under webui/rl_runs/daily_ohlcv_portfolio_env")
    rid = _validate_run_id(run_id or f"env_inspection_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    out_dir = (root / rid).resolve()
    out_dir.relative_to(root)
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Env inspection artifact run_id already exists: {rid}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "env_manifest": out_dir / "env_manifest.json",
        "observation_manifest": out_dir / "observation_manifest.json",
        "reward_breakdown": out_dir / "reward_breakdown.csv",
        "action_masks": out_dir / "action_masks.csv",
        "positions": out_dir / "positions.csv",
        "state_observations": out_dir / "state_observations.csv",
    }
    manifest = {**inspection["env_manifest"], "run_id": rid, "artifact_dir": str(out_dir), "artifacts": {key: str(path) for key, path in paths.items()}}
    _write_json(paths["env_manifest"], manifest)
    _write_json(paths["observation_manifest"], {**inspection["observation_manifest"], "run_id": rid})
    _write_csv(paths["reward_breakdown"], inspection["reward_breakdown"], ["step", "date", "requested_action", "executed_action", "action", "invalid_action", "invalid_action_reason", "no_trade_action", "gross_return", "turnover_cost", "net_return_after_cost", "missing_reward_label_count", "reward", "equity"])
    _write_csv(paths["action_masks"], inspection["action_masks"], ["step", "date", "requested_action", "mask_hold", "mask_buy", "mask_add", "mask_sell", "mask_reduce", "mask_reason_hold", "mask_reason_buy", "mask_reason_add", "mask_reason_sell", "mask_reason_reduce"])
    _write_csv(paths["positions"], inspection["positions"], ["step", "date", "rank", "code", "action"])
    _write_csv(paths["state_observations"], inspection["state_observations"], ["step", "date", "observation_position_count", "observation_top_score_bucket", "observation_score_margin_bucket", "observation_candidate_count_bucket", "observation_recent_score_volatility_bucket", "observation_d3_confidence_bucket", "observation_mode", "cash_fraction", "exposure_fraction", "held_codes", "candidate_count", "top_candidate_code", "top_candidate_rank", "top_candidate_score", "top_candidate_reward_label_available", "future_label_exposed"])
    return {"run_id": rid, "artifact_dir": str(out_dir), **{f"{key}_path": str(path) for key, path in paths.items()}}

__all__ = [
    "ACTION_NAMES",
    "DEFAULT_ENV_INSPECTION_ROOT",
    "ENV_INSPECTION_SCHEMA_VERSION",
    "OBSERVATION_MANIFEST_SCHEMA_VERSION",
    "OBSERVATION_MODE_ACTION_INDUCTION_V2",
    "OBSERVATION_MODE_V1",
    "FILL_ASSUMPTION",
    "ROUND_TRIP_COST_BP",
    "ROUND_TRIP_COST_RATE",
    "DailyCandidate",
    "DailyPortfolioEnv",
    "build_env_inspection",
    "build_observation_manifest",
    "candidates_by_date",
    "environment_contract",
    "write_env_inspection_artifacts",
    "validate_observation_manifest",
]
