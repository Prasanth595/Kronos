<div align="center">
  <h2><b>Kronos: A Foundation Model for the Language of Financial Markets </b></h2>
</div>


<div align="center">

</a> 
<a href="https://huggingface.co/NeoQuasar"> 
<img src="https://img.shields.io/badge/🤗-Hugging_Face-yellow" alt="Hugging Face"> 
</a> 
<a href="https://shiyu-coder.github.io/Kronos-demo/"> <img src="https://img.shields.io/badge/🚀-Live_Demo-brightgreen" alt="Live Demo"> </a>
<a href="https://github.com/shiyu-coder/Kronos/graphs/commit-activity"> 
<img src="https://img.shields.io/github/last-commit/shiyu-coder/Kronos?color=blue" alt="Last Commit"> 
</a> 
<a href="https://github.com/shiyu-coder/Kronos/stargazers"> 
<img src="https://img.shields.io/github/stars/shiyu-coder/Kronos?color=lightblue" alt="GitHub Stars"> 
</a> 
<a href="https://github.com/shiyu-coder/Kronos/network/members"> 
<img src="https://img.shields.io/github/forks/shiyu-coder/Kronos?color=yellow" alt="GitHub Forks"> 
</a> 
<a href="./LICENSE"> 
<img src="https://img.shields.io/github/license/shiyu-coder/Kronos?color=green" alt="License"> 
</a>

</div>

<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
  <a href="https://zdoc.app/de/shiyu-coder/Kronos">Deutsch</a> | 
  <a href="https://zdoc.app/es/shiyu-coder/Kronos">Español</a> | 
  <a href="https://zdoc.app/fr/shiyu-coder/Kronos">Français</a> | 
  <a href="https://zdoc.app/ja/shiyu-coder/Kronos">日本語</a> | 
  <a href="https://zdoc.app/ko/shiyu-coder/Kronos">한국어</a> | 
  <a href="https://zdoc.app/pt/shiyu-coder/Kronos">Português</a> | 
  <a href="https://zdoc.app/ru/shiyu-coder/Kronos">Русский</a> | 
  <a href="https://zdoc.app/zh/shiyu-coder/Kronos">中文</a>
</div>

<p align="center">

<img src="./figures/logo.png" width="100">

</p>

> Kronos is the **first open-source foundation model** for financial candlesticks (K-lines), 
> trained on data from over **45 global exchanges**.


</div>

## 📰 News
*   🚩 **[2025.11.10]** Kronos has been accpeted by AAAI 2026.
*   🚩 **[2025.08.17]** We have released the scripts for fine-tuning! Check them out to adapt Kronos to your own tasks.
*   🚩 **[2025.08.02]** Our paper is now available on [arXiv](https://arxiv.org/abs/2508.02739)!

<p align="center">

## 📜 Introduction

**Kronos** is a family of decoder-only foundation models, pre-trained specifically for the "language" of financial markets—K-line sequences. Unlike general-purpose TSFMs, Kronos is designed to handle the unique, high-noise characteristics of financial data. It leverages a novel two-stage framework: 
1. A specialized tokenizer first quantizes continuous, multi-dimensional K-line data (OHLCV) into **hierarchical discrete tokens**. 
2. A large, autoregressive Transformer is then pre-trained on these tokens, enabling it to serve as a unified model for diverse quantitative tasks.

<p align="center">
    <img src="figures/overview.png" alt="" align="center" width="700px" />
</p>

## ✨ Live Demo 
We have set up a live demo to visualize Kronos's forecasting results. The webpage showcases a forecast for the **BTC/USDT** trading pair over the next 24 hours. 

**👉 [Access the Live Demo Here](https://shiyu-coder.github.io/Kronos-demo/)** 

## 📦 Model Zoo 
We release a family of pre-trained models with varying capacities to suit different computational and application needs. All models are readily accessible from the Hugging Face Hub.

| Model        | Tokenizer                                                                       | Context length | Params  | Open-source                                                               |
|--------------|---------------------------------------------------------------------------------| -------------- | ------ |---------------------------------------------------------------------------|
| Kronos-mini  | [Kronos-Tokenizer-2k](https://huggingface.co/NeoQuasar/Kronos-Tokenizer-2k)     | 2048           | 4.1M   | ✅ [NeoQuasar/Kronos-mini](https://huggingface.co/NeoQuasar/Kronos-mini)  |
| Kronos-small | [Kronos-Tokenizer-base](https://huggingface.co/NeoQuasar/Kronos-Tokenizer-base) | 512            | 24.7M  | ✅ [NeoQuasar/Kronos-small](https://huggingface.co/NeoQuasar/Kronos-small) |
| Kronos-base  | [Kronos-Tokenizer-base](https://huggingface.co/NeoQuasar/Kronos-Tokenizer-base) | 512            | 102.3M | ✅ [NeoQuasar/Kronos-base](https://huggingface.co/NeoQuasar/Kronos-base)   |
| Kronos-large | [Kronos-Tokenizer-base](https://huggingface.co/NeoQuasar/Kronos-Tokenizer-base) | 512            | 499.2M | ❌                                                                         |


## 🚀 Getting Started

### Installation

1. Install Python 3.10+, and then install the dependencies:

```shell
pip install -r requirements.txt
```

### 📈 Making Forecasts

Forecasting with Kronos is straightforward using the `KronosPredictor` class. It handles data preprocessing, normalization, prediction, and inverse normalization, allowing you to get from raw data to forecasts in just a few lines of code.

**Important Note**: The `max_context` for `Kronos-small` and `Kronos-base` is **512**. This is the maximum sequence length the model can process. For optimal performance, it is recommended that your input data length (i.e., `lookback`) does not exceed this limit. The `KronosPredictor` will automatically handle truncation for longer contexts.

Here is a step-by-step guide to making your first forecast.

#### 1. Load the Tokenizer and Model

First, load a pre-trained Kronos model and its corresponding tokenizer from the Hugging Face Hub.

```python
from model import Kronos, KronosTokenizer, KronosPredictor

# Load from Hugging Face Hub
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
```

#### 2. Instantiate the Predictor

Create an instance of `KronosPredictor`, passing the model, tokenizer, and desired device.

```python
# Initialize the predictor
predictor = KronosPredictor(model, tokenizer, max_context=512)
```

#### 3. Prepare Input Data

The `predict` method requires three main inputs:
-   `df`: A pandas DataFrame containing the historical K-line data. It must include columns `['open', 'high', 'low', 'close']`. `volume` and `amount` are optional.
-   `x_timestamp`: A pandas Series of timestamps corresponding to the historical data in `df`.
-   `y_timestamp`: A pandas Series of timestamps for the future periods you want to predict.

```python
import pandas as pd

# Load your data
df = pd.read_csv("./data/XSHG_5min_600977.csv")
df['timestamps'] = pd.to_datetime(df['timestamps'])

# Define context window and prediction length
lookback = 400
pred_len = 120

# Prepare inputs for the predictor
x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close', 'volume', 'amount']]
x_timestamp = df.loc[:lookback-1, 'timestamps']
y_timestamp = df.loc[lookback:lookback+pred_len-1, 'timestamps']
```

#### 4. Generate Forecasts 

Call the `predict` method to generate forecasts. You can control the sampling process with parameters like `T`, `top_p`, and `sample_count` for probabilistic forecasting.

```python
# Generate predictions
pred_df = predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=1.0,          # Temperature for sampling
    top_p=0.9,      # Nucleus sampling probability
    sample_count=1  # Number of forecast paths to generate and average
)

print("Forecasted Data Head:")
print(pred_df.head())
```

The `predict` method returns a pandas DataFrame containing the forecasted values for `open`, `high`, `low`, `close`, `volume`, and `amount`, indexed by the `y_timestamp` you provided.

For efficient processing of multiple time series, Kronos provides a `predict_batch` method that enables parallel prediction on multiple datasets simultaneously. This is particularly useful when you need to forecast multiple assets or time periods at once.

```python
# Prepare multiple datasets for batch prediction
df_list = [df1, df2, df3]  # List of DataFrames
x_timestamp_list = [x_ts1, x_ts2, x_ts3]  # List of historical timestamps
y_timestamp_list = [y_ts1, y_ts2, y_ts3]  # List of future timestamps

# Generate batch predictions
pred_df_list = predictor.predict_batch(
    df_list=df_list,
    x_timestamp_list=x_timestamp_list,
    y_timestamp_list=y_timestamp_list,
    pred_len=pred_len,
    T=1.0,
    top_p=0.9,
    sample_count=1,
    verbose=True
)

# pred_df_list contains prediction results in the same order as input
for i, pred_df in enumerate(pred_df_list):
    print(f"Predictions for series {i}:")
    print(pred_df.head())
```

**Important Requirements for Batch Prediction:**
- All series must have the same historical length (lookback window)
- All series must have the same prediction length (`pred_len`)
- Each DataFrame must contain the required columns: `['open', 'high', 'low', 'close']`
- `volume` and `amount` columns are optional and will be filled with zeros if missing

The `predict_batch` method leverages GPU parallelism for efficient processing and automatically handles normalization and denormalization for each series independently.

#### 5. Example and Visualization

For a complete, runnable script that includes data loading, prediction, and plotting, please see [`examples/prediction_example.py`](examples/prediction_example.py).

Running this script will generate a plot comparing the ground truth data against the model's forecast, similar to the one shown below:

<p align="center">
    <img src="figures/prediction_example.png" alt="Forecast Example" align="center" width="600px" />
</p>

Additionally, we provide a script that makes predictions without Volume and Amount data, which can be found in [`examples/prediction_wo_vol_example.py`](examples/prediction_wo_vol_example.py).


## 🔧 Finetuning on Your Own Data (A-Share Market Example)

We provide a complete pipeline for finetuning Kronos on your own datasets. As an example, we demonstrate how to use [Qlib](https://github.com/microsoft/qlib) to prepare data from the Chinese A-share market and conduct a simple backtest.

> **Disclaimer:** This pipeline is intended as a demonstration to illustrate the finetuning process. It is a simplified example and not a production-ready quantitative trading system. A robust quantitative strategy requires more sophisticated techniques, such as portfolio optimization and risk factor neutralization, to achieve stable alpha.

The finetuning process is divided into four main steps:

1.  **Configuration**: Set up paths and hyperparameters.
2.  **Data Preparation**: Process and split your data using Qlib.
3.  **Model Finetuning**: Finetune the Tokenizer and the Predictor models.
4.  **Backtesting**: Evaluate the finetuned model's performance.

### Prerequisites

1.  First, ensure you have all dependencies from `requirements.txt` installed.
2.  This pipeline relies on `qlib`. Please install it:
    ```shell
      pip install pyqlib
    ```
3.  You will need to prepare your Qlib data. Follow the [official Qlib guide](https://github.com/microsoft/qlib) to download and set up your data locally. The example scripts assume you are using daily frequency data.

### Step 1: Configure Your Experiment

All settings for data, training, and model paths are centralized in `finetune/config.py`. Before running any scripts, please **modify the following paths** according to your environment:

*   `qlib_data_path`: Path to your local Qlib data directory.
*   `dataset_path`: Directory where the processed train/validation/test pickle files will be saved.
*   `save_path`: Base directory for saving model checkpoints.
*   `backtest_result_path`: Directory for saving backtesting results.
*   `pretrained_tokenizer_path` and `pretrained_predictor_path`: Paths to the pre-trained models you want to start from (can be local paths or Hugging Face model names).

You can also adjust other parameters like `instrument`, `train_time_range`, `epochs`, and `batch_size` to fit your specific task. If you don't use [Comet.ml](https://www.comet.com/), set `use_comet = False`.

### Step 2: Prepare the Dataset

Run the data preprocessing script. This script will load raw market data from your Qlib directory, process it, split it into training, validation, and test sets, and save them as pickle files.

```shell
python finetune/qlib_data_preprocess.py
```

After running, you will find `train_data.pkl`, `val_data.pkl`, and `test_data.pkl` in the directory specified by `dataset_path` in your config.

### Step 3: Run the Finetuning

The finetuning process consists of two stages: finetuning the tokenizer and then the predictor. Both training scripts are designed for multi-GPU training using `torchrun`.

#### 3.1 Finetune the Tokenizer

This step adjusts the tokenizer to the data distribution of your specific domain.

```shell
# Replace NUM_GPUS with the number of GPUs you want to use (e.g., 2)
torchrun --standalone --nproc_per_node=NUM_GPUS finetune/train_tokenizer.py
```

The best tokenizer checkpoint will be saved to the path configured in `config.py` (derived from `save_path` and `tokenizer_save_folder_name`).

#### 3.2 Finetune the Predictor

This step finetunes the main Kronos model for the forecasting task.

```shell
# Replace NUM_GPUS with the number of GPUs you want to use (e.g., 2)
torchrun --standalone --nproc_per_node=NUM_GPUS finetune/train_predictor.py
```

The best predictor checkpoint will be saved to the path configured in `config.py`.

### Step 4: Evaluate with Backtesting

Finally, run the backtesting script to evaluate your finetuned model. This script loads the models, performs inference on the test set, generates prediction signals (e.g., forecasted price change), and runs a simple top-K strategy backtest.

```shell
# Specify the GPU for inference
python finetune/qlib_test.py --device cuda:0
```

The script will output a detailed performance analysis in your console and generate a plot showing the cumulative return curves of your strategy against the benchmark, similar to the one below:

<p align="center">
    <img src="figures/backtest_result_example.png" alt="Backtest Example" align="center" width="700px" />
</p>

### 💡 From Demo to Production: Important Considerations

*   **Raw Signals vs. Pure Alpha**: The signals generated by the model in this demo are raw predictions. In a real-world quantitative workflow, these signals would typically be fed into a portfolio optimization model. This model would apply constraints to neutralize exposure to common risk factors (e.g., market beta, style factors like size and value), thereby isolating the **"pure alpha"** and improving the strategy's robustness.
*   **Data Handling**: The provided `QlibDataset` is an example. For different data sources or formats, you will need to adapt the data loading and preprocessing logic.
*   **Strategy and Backtesting Complexity**: The simple top-K strategy used here is a basic starting point. Production-level strategies often incorporate more complex logic for portfolio construction, dynamic position sizing, and risk management (e.g., stop-loss/take-profit rules). Furthermore, a high-fidelity backtest should meticulously model transaction costs, slippage, and market impact to provide a more accurate estimate of real-world performance.

> **📝 AI-Generated Comments**: Please note that many of the code comments within the `finetune/` directory were generated by an AI assistant (Gemini 2.5 Pro) for explanatory purposes. While they aim to be helpful, they may contain inaccuracies. We recommend treating the code itself as the definitive source of logic.

## 📖 Citation

If you use Kronos in your research, we would appreciate a citation to our [paper](https://arxiv.org/abs/2508.02739):

```
@misc{shi2025kronos,
      title={Kronos: A Foundation Model for the Language of Financial Markets}, 
      author={Yu Shi and Zongliang Fu and Shuo Chen and Bohan Zhao and Wei Xu and Changshui Zhang and Jian Li},
      year={2025},
      eprint={2508.02739},
      archivePrefix={arXiv},
      primaryClass={q-fin.ST},
      url={https://arxiv.org/abs/2508.02739}, 
}
```

## 📜 License 
This project is licensed under the [MIT License](./LICENSE).











---

# Appendix: Momentum Day-Trading Backtest (Cameron First-Pullback)

Independent research appended to this fork. Not part of the upstream Kronos
model. Full detail in [`research/FINDINGS.md`](research/FINDINGS.md);
per-trade data in [`research/momentum_master_table.csv`](research/momentum_master_table.csv).

**Strategy under test.** Five-pillar small-cap momentum selection (relative
volume ≥5× 50-day average, intraday gain ≥10%, price $2–$20, float <20M,
gap/catalyst), first-pullback entry on the crossing candle, per
`research/momentum_daytrading_notes.md`.

**Data & conventions.** Alpaca SIP 1-minute bars, `adjustment=raw`, full
sessions. Two windows: 2024-08→2025-08 and 2025-08→2026-08. Universe = active
US equities (survivorship-biased; a delisted-universe probe found 2 qualifying
entries, both winners). Costs: 0.5%/side, plus 2% slip-through on stop fills
unless noted. Float pillar could not be applied historically.

## 1. Universe funnel and frequency

| Window | Candidate-days | Entries | First-pullback | Later-pullback |
|---|---|---|---|---|
| 2024-08→2025-08 | 4,792 | 109 | 21 (0.4/wk) | 88 (1.7/wk) |
| 2025-08→2026-08 | 5,005 | 182 | 32 (0.6/wk) | 150 (2.9/wk) |

Dynamic intraday qualification (a stock may qualify any time 07:00–10:00 ET,
not only at the open) expanded the candidate pool ~4× versus an open-gap scan.

## 2. Raw post-entry movement, first-pullback entries (no exit rules)

| Metric | 2024-25 (n=21) | 2025-26 (n=32) |
|---|---|---|
| MFE by 10:00, median | +26.0% | +15.5% |
| MAE by 10:00, median | -28.2% | -16.6% |
| Price at 10:00, median | -15.5% | +0.1% |
| Day close vs entry, median | -25.8% | -8.2% |
| Touched +5% / +10% / +20% / +50% | 76 / 76 / 62 / 10% | 84 / 75 / 53 / 22% |

Large two-sided movement; the median entry closes **below** the entry price.

## 3. Drawdown → recovery curve (threshold-free)

2,201 retracement episodes / 291 ticker-days. Every dip below a running high
is an event; depth grid is a reporting cut, not an event definition.

| Retrace reached | n | P(new high) event-wtd | 95% CI | day-wtd | median time to recover |
|---|---|---|---|---|---|
| ≥2% | 1,892 | 84.9% | [83.0, 86.4] | 66.6% | 1 min |
| ≥5% | 1,341 | 78.7% | [76.3, 80.7] | 58.0% | 3 min |
| ≥8% | 969 | 70.8% | [67.9, 73.3] | 49.5% | 7 min |
| ≥10% | 807 | 65.4% | [62.2, 68.4] | 45.3% | 9 min |
| ≥15% | 554 | 51.1% | [47.2, 54.6] | 32.6% | 21 min |
| ≥20% | 431 | 40.4% | [35.5, 45.1] | 25.0% | 25 min |
| ≥30% | 285 | 26.7% | [21.7, 31.6] | 17.9% | 42 min |

Smooth monotone decay, no plateau or cliff; crosses 50/50 near 15% depth.
Day-weighted runs 18–20 pts below event-weighted (each ticker-day carries at
most one terminal failure). CIs from a ticker-day cluster bootstrap.
Retracement **order** (1st/2nd/3rd) carries no measurable information once
depth is known.

## 4. Escalation ladder — P(a retracement that reached X% goes on to reach Y%)

| From \ To | ≥5% | ≥10% | ≥15% | ≥20% | ≥30% |
|---|---|---|---|---|---|
| reached 2% | 71% | 43% | 29% | 23% | 15% |
| reached 5% | — | 60% | 41% | 32% | 21% |
| reached 10% | — | — | 69% | 53% | 35% |
| reached 15% | — | — | — | 78% | 51% |
| reached 20% | — | — | — | — | 66% |

Escalation odds *rise* with depth: shallow dips usually stop, deep dips tend
to keep going.

## 5. Next-leg advance after a recovered ≥X% retracement

Next event's peak vs the recovered peak (recovered episodes only).

| X% | n | p5 | p25 | med | p75 | p90 | p99 | max | mean |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 1,021 | +0.4 | +1.7 | +3.8 | +7.3 | +13.4 | +30.7 | +61.2 | +5.7 |
| 5 | 790 | +0.5 | +2.4 | +4.8 | +9.0 | +15.7 | +32.8 | +61.2 | +7.0 |
| 8 | 516 | +0.6 | +3.3 | +7.3 | +14.0 | +19.9 | +39.2 | +61.2 | +9.5 |
| 10 | 372 | +0.6 | +4.0 | +9.1 | +16.8 | +24.6 | +42.3 | +61.2 | +11.5 |
| 15 | 169 | +0.6 | +5.8 | +13.2 | +25.0 | +37.5 | +61.3 | +69.5 | +17.4 |
| 20 | 69 | +1.1 | +6.9 | +16.1 | +34.9 | +49.5 | +97.7 | +120.9 | +23.3 |

## 6. Downside from a naive dip-buy (additional fall below the −X% price)

| Buy at | n | med | p75 | p90 | if it recovers (med) | if it fails (med) |
|---|---|---|---|---|---|---|
| −2% | 1,892 | 6.4% | 16.3% | 35.7% | **5.1%** | **36.3%** |
| −5% | 1,341 | 7.6% | 22.1% | 38.8% | 5.3% | 34.3% |
| −10% | 807 | 12.6% | 29.0% | 43.6% | 6.2% | 30.7% |
| −20% | 431 | 19.3% | 31.2% | 49.3% | 10.5% | 24.0% |

Recovering and failing episodes separate around 15–20% below the buy price.

## 7. Fixed-level policies — exhaustive grid (all negative)

Mean %/trade, buy at −X% from running high, fixed stop and take-profit,
2024-26 pooled. Best cell per rung shown; **all 156 tested combinations lost**.

| Buy rung | Best stop/TP | Mean/trade | n | Win rate |
|---|---|---|---|---|
| −2% | −3% / +2% | −3.49% | 33,136 | 26% |
| −5% | −10% / +2% | −2.32% | 9,834 | 69% |
| −10% | −10% / +2% | **−2.29%** | 4,523 | 69% |
| −20% | −3% / +3% | −2.88% | 1,516 | — |

With **zero costs and perfect fills**, the TP>stop family still loses
(−0.10% to −0.90%/trade). Reason: the 85% recovery statistic is measured with
no stop in the way; any fixed stop is tagged during the escalation that
precedes most recoveries, collapsing the realized win rate to ~13–30%.

## 8. Exit-mechanism comparison, corrected entries

| Exit | First-pullback (n=53) | All entries (n=291) |
|---|---|---|
| Indicator exits + pullback-low stop | −1.05 R | — |
| Fixed target (dip-conditioned) | — | +0.4 to +1.0% |
| Laddered scale-out + ratcheting stop | negative | negative |
| Fixed buy/stop/TP grid (§7) | negative | negative |
| Junction cycling (arm −10%, exit −10%) | — | −4.5 to −5.1% |
| **No stop; arm at +2%; trail 0.25×ATR(14,1m); flat 10:00** | **+2.42%** | **~+1.2%** |

Per-day: ~+1.0% per qualified day; 222 of ~504 trading days qualified (44%);
~+0.46% per calendar trading day. Every fixed initial stop tested (6/8/10/12/
15/20%) reduced returns monotonically versus no stop.

## 9. Caveats

- **n = 53** first-pullback trades. Approximate 95% CI on +2.42% spans roughly
  −0.5% to +5.4%. The n=291 population (~+1.2%/trade) is sturdier.
- Exit parameters (0.25×ATR, +2% arm) were tuned on data overlapping both
  windows; the structure, not those two constants, was validated out-of-sample.
- **Fill quality is the binding assumption.** At 5% slip-through most edges
  here fall by half or vanish. Only live fills can settle it.
- Survivorship bias; float pillar unapplied historically; no options exist on
  ~93% of these names; short-selling is impractical (borrow, SSR, buy-in).
- Earlier versions of this work reported a +13.96%/trade figure on n=41. That
  was an optimization subset combined with an entry-definition bug and is
  **superseded**; see `FINDINGS.md` §9g–9h for the correction record.
