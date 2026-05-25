import pytest

from finetune.config import Config


def test_config_sets_default_paths_and_benchmark():
    config = Config()

    assert config.backtest_benchmark == "SH000300"
    assert config.finetuned_tokenizer_path == "./outputs/models/finetune_tokenizer_demo/checkpoints/best_model"
    assert config.finetuned_predictor_path == "./outputs/models/finetune_predictor_demo/checkpoints/best_model"
    assert config.n_train_iter == 2000 * config.batch_size
    assert config.n_val_iter == 400 * config.batch_size


@pytest.mark.parametrize(
    ("instrument", "expected"),
    [
        ("csi800", "SH000906"),
        ("csi1000", "SH000852"),
        ("csi300", "SH000300"),
    ],
)
def test_set_benchmark_supports_known_instruments(instrument, expected):
    config = Config()

    assert config._set_benchmark(instrument) == expected


def test_set_benchmark_rejects_unknown_instrument():
    config = Config()

    with pytest.raises(ValueError, match="Benchmark not defined for instrument: unknown"):
        config._set_benchmark("unknown")
