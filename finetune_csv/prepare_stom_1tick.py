"""Command-line wrapper for STOM 1tick DB inspection/export.

Examples:
    python finetune_csv/prepare_stom_1tick.py inspect --db _database/stock_tick_back.db
    python finetune_csv/prepare_stom_1tick.py export --db _database/stock_tick_back.db --output finetune_csv/data/stom_1tick_kline.csv
"""

from stom_tick_dataset import main


if __name__ == "__main__":
    raise SystemExit(main())
