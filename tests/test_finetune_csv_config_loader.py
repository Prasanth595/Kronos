import copy
import importlib
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def cleanup_config_loader_module():
    yield
    sys.modules.pop("finetune_csv.config_loader", None)


def load_config_loader(monkeypatch, config):
    records = {"loaded_text": None, "dump_calls": []}

    def safe_load(stream):
        records["loaded_text"] = stream.read()
        return copy.deepcopy(config)

    def dump(data, stream=None, **kwargs):
        records["dump_calls"].append(
            {
                "data": copy.deepcopy(data),
                "kwargs": kwargs,
                "used_stream": stream is not None,
            }
        )
        rendered = "rendered yaml\n"
        if stream is not None:
            stream.write(rendered)
        return rendered

    fake_yaml = types.SimpleNamespace(safe_load=safe_load, dump=dump)
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)
    sys.modules.pop("finetune_csv.config_loader", None)
    module = importlib.import_module("finetune_csv.config_loader")
    return module, records


def write_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("placeholder: true\n", encoding="utf-8")
    return config_path


def test_config_loader_resolves_dynamic_paths_and_nested_get(monkeypatch, tmp_path):
    module, _ = load_config_loader(
        monkeypatch,
        {
            "model_paths": {
                "exp_name": "alpha",
                "base_path": "/models",
                "base_save_path": "",
                "finetuned_tokenizer": "/custom/{exp_name}/tokenizer",
                "pretrained_tokenizer": "tok",
            },
            "data": {"lookback_window": 128},
        },
    )
    loader = module.ConfigLoader(str(write_config(tmp_path)))

    assert loader.get("model_paths.base_save_path") == "/models/alpha"
    assert loader.get("model_paths.finetuned_tokenizer") == "/custom/alpha/tokenizer"
    assert loader.get("data.lookback_window") == 128
    assert loader.get("data.missing", "fallback") == "fallback"
    assert loader.get("data.lookback_window.value", "fallback") == "fallback"
    assert loader.get_data_config() == {"lookback_window": 128}
    assert loader.get_training_config() == {}
    assert loader.get_model_paths()["pretrained_tokenizer"] == "tok"


def test_config_loader_keeps_paths_without_experiment_name(monkeypatch, tmp_path):
    config = {
        "model_paths": {
            "base_path": "/models",
            "base_save_path": "",
            "finetuned_tokenizer": None,
        }
    }
    module, _ = load_config_loader(monkeypatch, config)
    loader = module.ConfigLoader(str(write_config(tmp_path)))

    assert loader.config == config


def test_config_loader_missing_file_raises(monkeypatch, tmp_path):
    module, _ = load_config_loader(monkeypatch, {})

    with pytest.raises(FileNotFoundError, match="config file not found"):
        module.ConfigLoader(str(tmp_path / "missing.yaml"))


def test_update_config_deep_merges_and_save_writes_yaml(monkeypatch, tmp_path):
    module, records = load_config_loader(
        monkeypatch,
        {
            "data": {"lookback_window": 128, "clip": 5.0},
            "training": {"batch_size": 16},
            "model_paths": {"exp_name": "", "base_save_path": "/tmp/run"},
        },
    )
    config_path = write_config(tmp_path)
    loader = module.ConfigLoader(str(config_path))

    loader.update_config(
        {
            "data": {"clip": 3.5, "predict_window": 24},
            "training": {"batch_size": 32},
            "experiment": {"name": "trial"},
        }
    )
    save_path = tmp_path / "saved.yaml"
    loader.save_config(str(save_path))

    assert loader.get("data.lookback_window") == 128
    assert loader.get("data.clip") == 3.5
    assert loader.get("data.predict_window") == 24
    assert loader.get("training.batch_size") == 32
    assert loader.get_experiment_config() == {"name": "trial"}
    assert save_path.read_text(encoding="utf-8") == "rendered yaml\n"
    assert records["dump_calls"][-1]["data"] == loader.config
    assert records["dump_calls"][-1]["kwargs"]["allow_unicode"] is True


def test_save_config_defaults_to_original_path_and_prints_config(monkeypatch, tmp_path, capsys):
    module, records = load_config_loader(
        monkeypatch,
        {
            "data": {"lookback_window": 128},
            "model_paths": {"exp_name": "", "base_save_path": "/tmp/run"},
        },
    )
    config_path = write_config(tmp_path)
    loader = module.ConfigLoader(str(config_path))

    loader.save_config()
    loader.print_config()

    assert config_path.read_text(encoding="utf-8") == "rendered yaml\n"
    assert records["dump_calls"][0]["used_stream"] is True
    assert records["dump_calls"][1]["used_stream"] is False
    output = capsys.readouterr().out
    assert "Current configuration:" in output
    assert output.count("=" * 50) == 3


def test_custom_finetune_config_defaults_legacy_epochs_and_outputs(monkeypatch, tmp_path):
    module, _ = load_config_loader(
        monkeypatch,
        {
            "data": {
                "data_path": "data.csv",
                "lookback_window": 64,
                "predict_window": 12,
                "train_ratio": 0.7,
                "val_ratio": 0.2,
                "test_ratio": 0.1,
            },
            "training": {
                "epochs": 9,
                "batch_size": 8,
                "tokenizer_learning_rate": 0.001,
                "predictor_learning_rate": 0.002,
            },
            "model_paths": {
                "exp_name": "exp42",
                "base_path": "/base",
                "base_save_path": "",
                "pretrained_tokenizer": "pre_tok",
                "pretrained_predictor": "pre_pred",
                "tokenizer_save_name": "tok_out",
                "basemodel_save_name": "base_out",
                "finetuned_tokenizer": "",
            },
            "experiment": {
                "pre_trained": False,
                "train_tokenizer": False,
                "train_basemodel": True,
                "skip_existing": True,
            },
            "device": {"use_cuda": False, "device_id": 2},
            "distributed": {"use_ddp": True, "backend": "gloo"},
        },
    )
    config = module.CustomFinetuneConfig(str(write_config(tmp_path)))

    assert config.tokenizer_epochs == 9
    assert config.basemodel_epochs == 9
    assert config.base_save_path == "/base/exp42"
    assert config.tokenizer_save_path == "/base/exp42/tok_out"
    assert config.basemodel_save_path == "/base/exp42/base_out"
    assert config.tokenizer_best_model_path == "/base/exp42/tok_out/best_model"
    assert config.basemodel_best_model_path == "/base/exp42/base_out/best_model"
    assert config.pre_trained_tokenizer is False
    assert config.pre_trained_predictor is False
    assert config.use_cuda is False
    assert config.use_ddp is True

    tokenizer_config = config.get_tokenizer_config()
    basemodel_config = config.get_basemodel_config()
    assert tokenizer_config["epochs"] == 9
    assert tokenizer_config["learning_rate"] == 0.001
    assert tokenizer_config["save_path"] == "/base/exp42/tok_out"
    assert basemodel_config["epochs"] == 9
    assert basemodel_config["pretrained_tokenizer_path"] == "/base/exp42/tokenizer/best_model"
    assert basemodel_config["pretrained_predictor_path"] == "pre_pred"


def test_custom_finetune_config_prints_summary(monkeypatch, tmp_path, capsys):
    module, _ = load_config_loader(
        monkeypatch,
        {
            "data": {"data_path": "data.csv"},
            "training": {},
            "model_paths": {
                "exp_name": "summary",
                "base_path": "/base",
                "base_save_path": "",
                "finetuned_tokenizer": "",
            },
            "experiment": {},
        },
    )
    config = module.CustomFinetuneConfig(str(write_config(tmp_path)))

    config.print_config_summary()

    output = capsys.readouterr().out
    assert "Kronos finetuning configuration summary" in output
    assert "Experiment name: summary" in output
    assert "Tokenizer save path: /base/summary/tokenizer" in output
    assert "Basemodel save path: /base/summary/basemodel" in output


def test_custom_finetune_config_uses_default_config_path(monkeypatch):
    module, _ = load_config_loader(monkeypatch, {})

    class FakeLoader:
        def __init__(self, config_path):
            self.config_path = config_path

        def get_data_config(self):
            return {}

        def get_training_config(self):
            return {}

        def get_model_paths(self):
            return {"base_save_path": "/tmp/default"}

        def get_experiment_config(self):
            return {}

        def get_device_config(self):
            return {}

        def get_distributed_config(self):
            return {}

    monkeypatch.setattr(module, "ConfigLoader", FakeLoader)

    config = module.CustomFinetuneConfig()

    assert config.loader.config_path.endswith("finetune_csv/config.yaml")
    assert config.tokenizer_save_path == "/tmp/default/tokenizer"
