import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "finetune_csv"))

from config_loader import CustomFinetuneConfig  # noqa: E402
from stom_tick_dataset import GroupedKlineDataset, export_stom_tick_db_to_csv  # noqa: E402


def _create_single_table_db(path: Path, rows_per_session: int = 8):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            '''
            CREATE TABLE "005930" (
                "index" INTEGER,
                "현재가" REAL,
                "시가" REAL,
                "고가" REAL,
                "저가" REAL,
                "초당매수수량" REAL,
                "초당매도수량" REAL,
                "초당거래대금" REAL
            )
            '''
        )
        for day in [datetime(2026, 1, 2, 9, 0, 0), datetime(2026, 1, 3, 9, 0, 0)]:
            for i in range(rows_per_session):
                ts = int((day + timedelta(seconds=i)).strftime("%Y%m%d%H%M%S"))
                price = 70000 + i
                volume = (i + 1) + (i + 2)
                conn.execute(
                    'INSERT INTO "005930" VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (ts, price, 70000, price + 10, 69900, i + 1, i + 2, price * volume),
                )
        conn.commit()
    finally:
        conn.close()


def test_prepare_stom_1tick_inspect_cli_outputs_json(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    json_path = tmp_path / "inspect.json"
    _create_single_table_db(db_path)

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "finetune_csv" / "prepare_stom_1tick.py"),
            "inspect",
            "--db",
            str(db_path),
            "--lookback-window",
            "3",
            "--predict-window",
            "2",
            "--price-mode",
            "close_only",
            "--json-output",
            str(json_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["trainable"] is True
    assert json.loads(json_path.read_text(encoding="utf-8"))["eligible_group_count"] == 2


def test_config_can_build_grouped_dataset_for_training(tmp_path):
    db_path = tmp_path / "stock_tick_back.db"
    csv_path = tmp_path / "stom_1tick_kline.csv"
    config_path = tmp_path / "config.yaml"
    _create_single_table_db(db_path)
    export_stom_tick_db_to_csv(
        db_path,
        csv_path,
        max_tables=0,
        lookback_window=3,
        predict_window=2,
        price_mode="close_only",
    )

    config_path.write_text(
        f"""
data:
  data_path: "{csv_path.as_posix()}"
  dataset_type: "stom_tick"
  group_columns: ["symbol", "session"]
  lookback_window: 3
  predict_window: 2
  max_context: 16
  clip: 5.0
  sample_stride: 1
  max_samples: null
  normalize_using: "lookback"
  train_ratio: 0.5
  val_ratio: 0.5
  test_ratio: 0.0
training:
  tokenizer_epochs: 0
  basemodel_epochs: 1
  batch_size: 2
  log_interval: 1
  num_workers: 0
  seed: 42
model_paths:
  pretrained_tokenizer: "NeoQuasar/Kronos-Tokenizer-base"
  pretrained_predictor: "NeoQuasar/Kronos-small"
  exp_name: "test_stom"
  base_path: "{(tmp_path / 'finetuned').as_posix()}"
  base_save_path: ""
  finetuned_tokenizer: ""
experiment:
  name: "test"
  train_tokenizer: false
  train_basemodel: true
device:
  use_cuda: false
  device_id: 0
distributed:
  use_ddp: false
""",
        encoding="utf-8",
    )

    config = CustomFinetuneConfig(str(config_path))
    dataset = GroupedKlineDataset(
        config.data_path,
        data_type="train",
        lookback_window=config.lookback_window,
        predict_window=config.predict_window,
        clip=config.clip,
        seed=config.seed,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
        group_columns=config.group_columns,
        sample_stride=config.sample_stride,
        max_samples=config.max_samples,
        normalize_using=config.normalize_using,
    )

    assert config.dataset_type == "stom_tick"
    assert isinstance(dataset, GroupedKlineDataset)
    assert len(dataset) == 3
