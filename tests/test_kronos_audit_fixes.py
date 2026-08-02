"""Regression tests for the Kronos code-audit remediation.

Covers the Severity 1 and Severity 2 findings from the 2026-08-01 audit:

- 2.1 top_k/top_p filtering chaining
- 2.2 rolling-buffer shift (no torch.roll)
- 2.4 normalization std floor
- 2.8 DDP-safe compute_loss
- 3.2/3.3 heterogeneous batch padding + attention masking
- 3.4 KRONOS_DEVICE override
- 3.5 lazy time features in QlibTestDataset (no input mutation)
- 2.10/3.7 config hygiene (COMET env fallback, renamed sample counters, market profiles)

These tests run with tiny random-weight models and never download weights.
"""

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
import torch.nn.functional as functional
from model import Kronos, KronosPredictor, KronosTokenizer
from model.kronos import top_k_top_p_filtering

DEVICE = "cpu"

S1_BITS = 4
S2_BITS = 4
D_MODEL = 16


# ---------------------------------------------------------------------------
# Tiny random-weight fixtures (no HuggingFace download)
# ---------------------------------------------------------------------------
def make_tiny_tokenizer():
    return KronosTokenizer(
        d_in=6,
        d_model=D_MODEL,
        n_heads=4,
        ff_dim=32,
        n_enc_layers=2,
        n_dec_layers=2,
        ffn_dropout_p=0.0,
        attn_dropout_p=0.0,
        resid_dropout_p=0.0,
        s1_bits=S1_BITS,
        s2_bits=S2_BITS,
        beta=0.25,
        gamma0=0.01,
        gamma=0.01,
        zeta=0.01,
        group_size=8,
    )


def make_tiny_predictor_model():
    return Kronos(
        s1_bits=S1_BITS,
        s2_bits=S2_BITS,
        n_layers=1,
        d_model=D_MODEL,
        n_heads=4,
        ff_dim=32,
        ffn_dropout_p=0.0,
        attn_dropout_p=0.0,
        resid_dropout_p=0.0,
        token_dropout_p=0.0,
        learn_te=False,
    )


@pytest.fixture(scope="module")
def tiny_models():
    torch.manual_seed(0)
    tokenizer = make_tiny_tokenizer().eval()
    model = make_tiny_predictor_model().eval()
    return tokenizer, model


def make_price_df(n, seed=0):
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1.0, n))
    open_ = close - rng.normal(0, 0.1, n)
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.2, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.2, n))
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.integers(100, 1000, n).astype(float),
        "amount": rng.uniform(1e4, 1e5, n),
    })


def make_timestamps(n, start="2024-01-01"):
    return pd.Series(pd.date_range(start, periods=n, freq="5min"))


# ---------------------------------------------------------------------------
# 2.1 top_k/top_p chaining
# ---------------------------------------------------------------------------
def _reference_filter(logits, top_k, top_p, min_tokens_to_keep=1):
    out = logits.clone()
    if top_k > 0:
        k = min(max(top_k, min_tokens_to_keep), out.size(-1))
        keep = torch.topk(out, k)[0][..., -1, None]
        out = out.masked_fill(out < keep, -float("Inf"))
    if top_p < 1.0:
        sorted_logits, sorted_indices = torch.sort(out, descending=True)
        cum = torch.cumsum(functional.softmax(sorted_logits, dim=-1), dim=-1)
        remove = cum > top_p
        remove[..., 1:] = remove[..., :-1].clone()
        remove[..., 0] = 0
        inds = remove.scatter(1, sorted_indices, remove)
        out = out.masked_fill(inds, -float("Inf"))
    return out


def test_top_k_top_p_filtering_chains_both():
    torch.manual_seed(7)
    logits = torch.randn(4, 64)
    got = top_k_top_p_filtering(logits.clone(), top_k=10, top_p=0.6)
    expected = _reference_filter(logits, top_k=10, top_p=0.6)
    torch.testing.assert_close(got, expected)


def test_top_k_top_p_filtering_matches_top_k_only_when_top_p_default():
    torch.manual_seed(8)
    logits = torch.randn(3, 32)
    got = top_k_top_p_filtering(logits.clone(), top_k=3, top_p=1.0)
    expected = _reference_filter(logits, top_k=3, top_p=1.0)
    torch.testing.assert_close(got, expected)


def test_top_k_top_p_filtering_matches_top_p_only_when_top_k_default():
    torch.manual_seed(9)
    logits = torch.randn(3, 32)
    got = top_k_top_p_filtering(logits.clone(), top_k=0, top_p=0.7)
    expected = _reference_filter(logits, top_k=0, top_p=0.7)
    torch.testing.assert_close(got, expected)


def test_top_k_top_p_filtering_with_both_removes_more_than_top_k_alone():
    torch.manual_seed(10)
    logits = torch.randn(1, 16)
    both = top_k_top_p_filtering(logits.clone(), top_k=5, top_p=0.4)
    k_only = top_k_top_p_filtering(logits.clone(), top_k=5, top_p=1.0)
    kept_both = (both != -float("Inf")).sum().item()
    kept_k = (k_only != -float("Inf")).sum().item()
    assert 0 < kept_both < kept_k


# ---------------------------------------------------------------------------
# 2.4 normalization std floor
# ---------------------------------------------------------------------------
def test_floored_std_floor_applies_to_flat_columns():
    std = np.array([0.0, 1e-9, 1e-8, 0.5, 2.0])
    floored = KronosPredictor._floored_std(std)
    # Flat columns are raised to the floor; normal columns keep std + eps.
    np.testing.assert_array_equal(floored[:3], np.full(3, 1e-3))
    np.testing.assert_allclose(floored[3:], np.array([0.50001, 2.00001]))


def test_floored_std_leaves_normal_columns_untouched():
    rng = np.random.default_rng(1)
    std = rng.uniform(0.01, 5.0, 8)
    np.testing.assert_allclose(KronosPredictor._floored_std(std), std, atol=1e-4)


def test_predict_on_flat_window_is_finite(tiny_models):
    tokenizer, model = tiny_models
    n = 32
    flat = pd.DataFrame({
        "open": np.full(n, 100.0),
        "high": np.full(n, 100.0),
        "low": np.full(n, 100.0),
        "close": np.full(n, 100.0),
        "volume": np.full(n, 1000.0),
        "amount": np.full(n, 100000.0),
    })
    df = flat
    ts = make_timestamps(n)
    predictor = KronosPredictor(model, tokenizer, device=DEVICE, max_context=16)
    with torch.no_grad():
        pred = predictor.predict(
            df=df, x_timestamp=ts, y_timestamp=ts[:4], pred_len=4,
            T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False,
        )
    assert np.isfinite(pred.to_numpy()).all()


# ---------------------------------------------------------------------------
# 2.8 compute_loss exposure
# ---------------------------------------------------------------------------
def test_compute_loss_matches_head(tiny_models):
    _, model = tiny_models
    s1_targets = torch.randint(0, 2 ** S1_BITS, (2, 16))
    s2_targets = torch.randint(0, 2 ** S2_BITS, (2, 16))
    s1_logits = torch.randn(2, 16, 2 ** S1_BITS)
    s2_logits = torch.randn(2, 16, 2 ** S2_BITS)
    expected = model.head.compute_loss(s1_logits, s2_logits, s1_targets, s2_targets)
    got = model.compute_loss(s1_logits, s2_logits, s1_targets, s2_targets)
    assert len(got) == 3
    for a, b in zip(got, expected, strict=True):
        torch.testing.assert_close(a, b)


def test_compute_loss_is_finite(tiny_models):
    _, model = tiny_models
    s1_targets = torch.randint(0, 2 ** S1_BITS, (2, 8))
    s2_targets = torch.randint(0, 2 ** S2_BITS, (2, 8))
    s1_logits = torch.randn(2, 8, 2 ** S1_BITS)
    s2_logits = torch.randn(2, 8, 2 ** S2_BITS)
    loss, s1, s2 = model.compute_loss(s1_logits, s2_logits, s1_targets, s2_targets)
    assert torch.isfinite(loss) and torch.isfinite(s1) and torch.isfinite(s2)


# ---------------------------------------------------------------------------
# 3.4 device selection
# ---------------------------------------------------------------------------
def test_device_env_override(monkeypatch, tiny_models):
    tokenizer, model = tiny_models
    monkeypatch.setenv("KRONOS_DEVICE", "cpu")
    predictor = KronosPredictor(model, tokenizer, device=None, max_context=16)
    assert predictor.device == "cpu"


def test_device_accepts_torch_device(tiny_models):
    tokenizer, model = tiny_models
    predictor = KronosPredictor(model, tokenizer, device=torch.device("cpu"), max_context=16)
    assert predictor.device == "cpu"


def test_device_explicit_wins_over_env(monkeypatch, tiny_models):
    tokenizer, model = tiny_models
    monkeypatch.setenv("KRONOS_DEVICE", "cuda:0")
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=16)
    assert predictor.device == "cpu"


# ---------------------------------------------------------------------------
# 2.2/3.2/3.3 end-to-end inference with tiny models
# ---------------------------------------------------------------------------
def test_autoregressive_inference_smoke(tiny_models):
    tokenizer, model = tiny_models
    predictor = KronosPredictor(model, tokenizer, device=DEVICE, max_context=16)
    df = make_price_df(64)
    ts = make_timestamps(64)
    with torch.no_grad():
        pred = predictor.predict(
            df=df, x_timestamp=ts, y_timestamp=ts[:4], pred_len=4,
            T=1.0, top_k=0, top_p=0.9, sample_count=2, verbose=False,
        )
    assert pred.shape == (4, 6)
    assert np.isfinite(pred.to_numpy()).all()


def test_autoregressive_inference_exercises_shift_branch(tiny_models):
    """seq_len > max_context forces the rolling-buffer shift path (2.2)."""
    tokenizer, model = tiny_models
    predictor = KronosPredictor(model, tokenizer, device=DEVICE, max_context=8)
    df = make_price_df(64)
    ts = make_timestamps(64)
    with torch.no_grad():
        pred = predictor.predict(
            df=df, x_timestamp=ts, y_timestamp=ts[:3], pred_len=3,
            T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False,
        )
    assert pred.shape == (3, 6)
    assert np.isfinite(pred.to_numpy()).all()


def test_predict_batch_heterogeneous_lengths(tiny_models):
    tokenizer, model = tiny_models
    predictor = KronosPredictor(model, tokenizer, device=DEVICE, max_context=16)

    df_long = make_price_df(64)
    df_short = make_price_df(40, seed=1)
    ts_long = make_timestamps(64)
    ts_short = make_timestamps(40, start="2024-02-01")

    with torch.no_grad():
        preds = predictor.predict_batch(
            df_list=[df_long, df_short],
            x_timestamp_list=[ts_long, ts_short],
            y_timestamp_list=[ts_long[:4], ts_short[:4]],
            pred_len=4,
            T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False,
        )
    assert len(preds) == 2
    assert preds[0].shape == (4, 6)
    assert preds[1].shape == (4, 6)
    assert np.isfinite(preds[0].to_numpy()).all()
    assert np.isfinite(preds[1].to_numpy()).all()


def test_predict_batch_single_length_matches_old_contract(tiny_models):
    """Equal-length batches must still work without padding (backward compat)."""
    tokenizer, model = tiny_models
    predictor = KronosPredictor(model, tokenizer, device=DEVICE, max_context=16)
    df_a = make_price_df(48)
    df_b = make_price_df(48, seed=2)
    ts_a = make_timestamps(48)
    ts_b = make_timestamps(48, start="2024-03-01")
    with torch.no_grad():
        preds = predictor.predict_batch(
            df_list=[df_a, df_b],
            x_timestamp_list=[ts_a, ts_b],
            y_timestamp_list=[ts_a[:4], ts_b[:4]],
            pred_len=4,
            T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False,
        )
    assert len(preds) == 2
    assert all(p.shape == (4, 6) for p in preds)


def test_predict_batch_rejects_mismatched_pred_len(tiny_models):
    tokenizer, model = tiny_models
    predictor = KronosPredictor(model, tokenizer, device=DEVICE, max_context=16)
    df_a = make_price_df(48)
    df_b = make_price_df(48, seed=2)
    ts_a = make_timestamps(48)
    ts_b = make_timestamps(48, start="2024-03-01")
    with pytest.raises(ValueError, match="pred_len=4"):
        predictor.predict_batch(
            df_list=[df_a, df_b],
            x_timestamp_list=[ts_a, ts_b],
            y_timestamp_list=[ts_a[:4], ts_b[:6]],
            pred_len=4,
        )


# ---------------------------------------------------------------------------
# 3.5 QlibTestDataset lazy time features (stubbed qlib/matplotlib imports)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qlib_test_module():
    stubs = {}
    for mod_name in [
        "qlib", "qlib.config", "qlib.backtest", "qlib.backtest.backtest",
        "qlib.backtest.executor", "qlib.contrib", "qlib.contrib.evaluate",
        "qlib.contrib.strategy", "qlib.utils", "qlib.utils.time",
        "matplotlib", "matplotlib.pyplot",
    ]:
        stubs[mod_name] = types.ModuleType(mod_name)
        sys.modules[mod_name] = stubs[mod_name]
    stubs["qlib.config"].REG_CN = "cn"
    stubs["qlib.config"].REG_US = "us"
    for m in stubs.values():
        m.__getattr__ = lambda name: types.SimpleNamespace()

    root = str(Path(__file__).resolve().parents[1])
    finetune = str(Path(__file__).resolve().parents[1] / "finetune")
    for p in (root, finetune):
        if p not in sys.path:
            sys.path.insert(0, p)

    spec = importlib.util.spec_from_file_location(
        "qlib_test_stub", str(Path(finetune) / "qlib_test.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module

    # Restore sys.modules so real qlib/matplotlib imports are unaffected later.
    for name in stubs:
        sys.modules.pop(name, None)
    for p in (root, finetune):
        if p in sys.path:
            sys.path.remove(p)


def _sample_config(**overrides):
    cfg = types.SimpleNamespace()
    cfg.lookback_window = 10
    cfg.predict_window = 3
    cfg.clip = 5.0
    cfg.feature_list = ["open", "high", "low", "close", "vol", "amt"]
    cfg.time_feature_list = ["minute", "hour", "weekday", "day", "month"]
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _synthetic_series_data(n=50):
    idx = pd.DatetimeIndex(pd.date_range("2024-01-01", periods=n, freq="D"), name="datetime")
    df = pd.DataFrame({
        "open": np.linspace(1, 2, n),
        "high": np.linspace(1.1, 2.1, n),
        "low": np.linspace(0.9, 1.9, n),
        "close": np.linspace(1.05, 2.05, n),
        "vol": np.full(n, 100.0),
        "amt": np.full(n, 1000.0),
    }, index=idx)
    return df


def test_qlib_dataset_does_not_mutate_input(qlib_test_module):
    dataset_cls = qlib_test_module.QlibTestDataset
    data = {"A": _synthetic_series_data(), "B": _synthetic_series_data(60)}
    original_cols = {k: list(v.columns) for k, v in data.items()}

    ds = dataset_cls(data=data, config=_sample_config())
    # Force feature computation for both symbols.
    for i in range(len(ds)):
        ds[i]

    for k, cols in original_cols.items():
        assert list(data[k].columns) == cols
        assert "minute" not in data[k].columns


def test_qlib_dataset_getitem_shapes(qlib_test_module):
    dataset_cls = qlib_test_module.QlibTestDataset
    cfg = _sample_config()
    data = {"A": _synthetic_series_data()}
    ds = dataset_cls(data=data, config=cfg)
    x, x_stamp, y_stamp, symbol, timestamp = ds[0]
    assert x.shape == (cfg.lookback_window, len(cfg.feature_list))
    assert x_stamp.shape == (cfg.lookback_window, len(cfg.time_feature_list))
    assert y_stamp.shape == (cfg.predict_window, len(cfg.time_feature_list))
    assert symbol == "A"
    assert np.isfinite(x.numpy()).all()


def test_qlib_dataset_flat_window_normalization(qlib_test_module):
    dataset_cls = qlib_test_module.QlibTestDataset
    data = {"A": _synthetic_series_data()}
    ds = dataset_cls(data=data, config=_sample_config())
    x, _, _, _, _ = ds[len(data["A"]) - ds.window_size]  # last valid window
    assert np.isfinite(x.numpy()).all()


# ---------------------------------------------------------------------------
# Config hygiene (2.10, 3.7, 2.5) - loaded standalone
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def config_module():
    path = str(Path(__file__).resolve().parents[1] / "finetune" / "config.py")
    spec = importlib.util.spec_from_file_location("kronos_config_standalone", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_config_uses_comet_env_fallback(monkeypatch, config_module):
    monkeypatch.delenv("COMET_API_KEY", raising=False)
    monkeypatch.delenv("COMET_WORKSPACE", raising=False)
    cfg = config_module.Config()
    assert cfg.comet_config["api_key"] == ""


def test_config_reads_comet_env(monkeypatch, config_module):
    monkeypatch.setenv("COMET_API_KEY", "secret-key")
    cfg = config_module.Config()
    assert cfg.comet_config["api_key"] == "secret-key"


def test_config_sample_counters_renamed(config_module):
    cfg = config_module.Config()
    assert hasattr(cfg, "n_train_samples_per_epoch")
    assert hasattr(cfg, "n_val_samples_per_epoch")
    assert not hasattr(cfg, "n_train_iter")


def test_config_market_profiles(config_module):
    cfg = config_module.Config()
    cn = cfg._set_exchange_kwargs("cn", "day")
    assert cn["limit_threshold"] == 0.095
    assert cn["deal_price"] == "open"
    generic = cfg._set_exchange_kwargs("generic", "1min")
    assert generic["freq"] == "1min"
    assert generic["limit_threshold"] is None
    assert generic["deal_price"] == "close"
    with pytest.raises(ValueError):
        cfg._set_exchange_kwargs("nope", "day")


def test_config_default_backtest_params(config_module):
    cfg = config_module.Config()
    assert cfg.backtest_exchange_kwargs["freq"] == cfg.backtest_freq
    assert cfg.inference_num_workers <= 8
    assert cfg.qlib_region == "cn"
