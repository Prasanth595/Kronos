import argparse
import sys
from pathlib import Path

import pandas as pd

# Anchor the project root on this file's location so the example can be run
# from any working directory (e.g. `python examples/prediction_example.py`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import Kronos, KronosPredictor, KronosTokenizer

REQUIRED_COLUMNS = ['open', 'high', 'low', 'close', 'volume', 'amount', 'timestamps']


def plot_prediction(kline_df, pred_df):
    import matplotlib.pyplot as plt

    pred_df.index = kline_df.index[-pred_df.shape[0]:]
    sr_close = kline_df['close']
    sr_pred_close = pred_df['close']
    sr_close.name = 'Ground Truth'
    sr_pred_close.name = "Prediction"

    sr_volume = kline_df['volume']
    sr_pred_volume = pred_df['volume']
    sr_volume.name = 'Ground Truth'
    sr_pred_volume.name = "Prediction"

    close_df = pd.concat([sr_close, sr_pred_close], axis=1)
    volume_df = pd.concat([sr_volume, sr_pred_volume], axis=1)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    ax1.plot(close_df['Ground Truth'], label='Ground Truth', color='blue', linewidth=1.5)
    ax1.plot(close_df['Prediction'], label='Prediction', color='red', linewidth=1.5)
    ax1.set_ylabel('Close Price', fontsize=14)
    ax1.legend(loc='lower left', fontsize=12)
    ax1.grid(True)

    ax2.plot(volume_df['Ground Truth'], label='Ground Truth', color='blue', linewidth=1.5)
    ax2.plot(volume_df['Prediction'], label='Prediction', color='red', linewidth=1.5)
    ax2.set_ylabel('Volume', fontsize=14)
    ax2.legend(loc='upper left', fontsize=12)
    ax2.grid(True)

    plt.tight_layout()
    plt.show()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Kronos inference on an OHLCV CSV file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("csv_path", type=Path,
                        help="Path to a CSV with columns: " + ", ".join(REQUIRED_COLUMNS))
    parser.add_argument("--lookback", type=int, default=400,
                        help="Number of historical bars to condition on.")
    parser.add_argument("--pred_len", type=int, default=120,
                        help="Number of bars to forecast.")
    parser.add_argument("--max_context", type=int, default=512,
                        help="Maximum context length fed to the model.")
    parser.add_argument("--device", type=str, default=None,
                        help="Inference device (defaults to KRONOS_DEVICE, then auto-detect).")
    parser.add_argument("--top_k", type=int, default=0,
                        help="Top-k sampling threshold (0 disables).")
    parser.add_argument("--top_p", type=float, default=0.9,
                        help="Nucleus sampling threshold.")
    parser.add_argument("--T", type=float, default=1.0,
                        help="Sampling temperature.")
    parser.add_argument("--sample_count", type=int, default=1,
                        help="Parallel samples per series (averaged).")
    parser.add_argument("--no-show", action="store_true",
                        help="Skip the matplotlib plot.")
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {args.csv_path}")

    df = pd.read_csv(args.csv_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV at {args.csv_path} is missing required columns: {missing}. "
            f"Expected columns: {REQUIRED_COLUMNS}"
        )

    df['timestamps'] = pd.to_datetime(df['timestamps'])

    if args.lookback < 1 or args.pred_len < 1:
        raise ValueError("lookback and pred_len must both be >= 1.")
    if args.lookback + args.pred_len > len(df):
        raise ValueError(
            f"lookback + pred_len ({args.lookback + args.pred_len}) exceeds the "
            f"number of rows in the CSV ({len(df)})."
        )

    # 1. Load Model and Tokenizer
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")

    # 2. Instantiate Predictor
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=args.max_context)

    # 3. Prepare Data
    lookback = args.lookback
    pred_len = args.pred_len

    x_df = df.loc[:lookback - 1, ['open', 'high', 'low', 'close', 'volume', 'amount']]
    x_timestamp = df.loc[:lookback - 1, 'timestamps']
    y_timestamp = df.loc[lookback:lookback + pred_len - 1, 'timestamps']

    # 4. Make Prediction
    pred_df = predictor.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=args.T,
        top_k=args.top_k,
        top_p=args.top_p,
        sample_count=args.sample_count,
        verbose=True
    )

    # 5. Visualize Results
    print("Forecasted Data Head:")
    print(pred_df.head())

    if not args.no_show:
        # Combine historical and forecasted data for plotting
        kline_df = df.loc[:lookback + pred_len - 1]
        plot_prediction(kline_df, pred_df)


if __name__ == '__main__':
    main()
