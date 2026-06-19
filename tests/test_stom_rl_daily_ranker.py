import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl.daily_ranker import fit_direction_classifier, fit_linear_ranker, score_direction_probability, score_row  # noqa: E402


def _rows():
    return [
        {"split": "train", "eligible_for_training": True, "return_5d": -0.02, "volatility_5d": 0.01, "future_return_1d": -0.01, "future_direction_1d": 0},
        {"split": "train", "eligible_for_training": True, "return_5d": 0.01, "volatility_5d": 0.02, "future_return_1d": 0.02, "future_direction_1d": 1},
        {"split": "train", "eligible_for_training": True, "return_5d": 0.03, "volatility_5d": 0.02, "future_return_1d": 0.04, "future_direction_1d": 1},
        {"split": "test", "eligible_for_training": True, "return_5d": 99.0, "volatility_5d": 0.02, "future_return_1d": 999.0, "future_direction_1d": 1},
    ]


def test_linear_ranker_fits_train_split_only_and_scores_order():
    model = fit_linear_ranker(_rows(), feature_columns=["return_5d", "volatility_5d"], target_column="future_return_1d")
    assert model.train_row_count == 3
    assert model.target_column == "future_return_1d"
    low = score_row(model, {"return_5d": -0.02, "volatility_5d": 0.01})
    high = score_row(model, {"return_5d": 0.04, "volatility_5d": 0.02})
    assert high > low
    assert model.to_dict()["training_policy"] == "fit_train_split_only_no_oos_retuning"


def test_direction_classifier_probability_is_bounded():
    model = fit_direction_classifier(_rows(), feature_columns=["return_5d", "volatility_5d"])
    probability = score_direction_probability(model, {"return_5d": 0.02, "volatility_5d": 0.01})
    assert 0.0 < probability < 1.0
    assert model.model_kind == "supervised_direction_classifier"
