import os


def _env_int(name, default):
    value = os.getenv(name)
    return default if value in (None, "") else int(value)


def _env_float(name, default):
    value = os.getenv(name)
    return default if value in (None, "") else float(value)


def _env_bool(name, default):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.lower() not in {"0", "false", "no", "off"}

class Config:
    """
    Configuration class for the entire project.
    """

    def __init__(self):
        # =================================================================
        # Data & Feature Parameters
        # =================================================================
        # TODO: Update this path to your Qlib data directory.
        self.qlib_data_path = os.getenv("KRONOS_QLIB_DATA_PATH", "~/.qlib/qlib_data/cn_data")
        self.instrument = os.getenv("KRONOS_QLIB_INSTRUMENT", 'csi300')

        # Overall time range for data loading from Qlib.
        self.dataset_begin_time = os.getenv("KRONOS_DATASET_BEGIN_TIME", "2011-01-01")
        self.dataset_end_time = os.getenv("KRONOS_DATASET_END_TIME", '2025-06-05')

        # Sliding window parameters for creating samples.
        self.lookback_window = _env_int("KRONOS_LOOKBACK_WINDOW", 90)  # Number of past time steps for input.
        self.predict_window = _env_int("KRONOS_PREDICT_WINDOW", 10)  # Number of future time steps for prediction.
        self.max_context = _env_int("KRONOS_MAX_CONTEXT", 512)  # Maximum context length for the model.

        # Features to be used from the raw data.
        self.feature_list = ['open', 'high', 'low', 'close', 'vol', 'amt']
        # Time-based features to be generated.
        self.time_feature_list = ['minute', 'hour', 'weekday', 'day', 'month']

        # =================================================================
        # Dataset Splitting & Paths
        # =================================================================
        # Note: The validation/test set starts earlier than the training/validation set ends
        # to account for the `lookback_window`.
        self.train_time_range = [
            os.getenv("KRONOS_TRAIN_START", "2011-01-01"),
            os.getenv("KRONOS_TRAIN_END", "2022-12-31"),
        ]
        self.val_time_range = [
            os.getenv("KRONOS_VAL_START", "2022-09-01"),
            os.getenv("KRONOS_VAL_END", "2024-06-30"),
        ]
        self.test_time_range = [
            os.getenv("KRONOS_TEST_START", "2024-04-01"),
            os.getenv("KRONOS_TEST_END", "2025-06-05"),
        ]
        self.backtest_time_range = [
            os.getenv("KRONOS_BACKTEST_START", "2024-07-01"),
            os.getenv("KRONOS_BACKTEST_END", "2025-06-05"),
        ]

        # TODO: Directory to save the processed, pickled datasets.
        self.dataset_path = os.getenv("KRONOS_DATASET_PATH", "./data/processed_datasets")

        # =================================================================
        # Training Hyperparameters
        # =================================================================
        self.clip = _env_float("KRONOS_CLIP", 5.0)  # Clipping value for normalized data to prevent outliers.

        self.epochs = _env_int("KRONOS_EPOCHS", 30)
        self.log_interval = _env_int("KRONOS_LOG_INTERVAL", 100)  # Log training status every N batches.
        self.batch_size = _env_int("KRONOS_BATCH_SIZE", 50)  # Batch size per GPU.
        self.tokenizer_validation_batch_size = _env_int(
            "KRONOS_TOKENIZER_VAL_BATCH_SIZE",
            self.batch_size,
        )
        self.num_workers = _env_int("KRONOS_NUM_WORKERS", 2)
        self.dataset_sample_mode = os.getenv("KRONOS_DATASET_SAMPLE_MODE", "sample_random")

        # =================================================================
        # GPU 최대 활용 최적화 (모두 opt-in — default 는 기존 동작 유지)
        # =================================================================
        # DataLoader: persistent_workers 와 prefetch_factor 는 num_workers > 0 일 때만 효과.
        self.persistent_workers = _env_bool("KRONOS_PERSISTENT_WORKERS", False)
        self.prefetch_factor = _env_int("KRONOS_PREFETCH_FACTOR", 2)

        # Mixed precision (AMP): bf16 권장 (4080 SUPER 가속 + GradScaler 불필요).
        # KRONOS_TOKENIZER_AMP=1 + KRONOS_TOKENIZER_AMP_DTYPE=bf16 으로 활성화.
        self.tokenizer_enable_amp = _env_bool("KRONOS_TOKENIZER_AMP", False)
        self.tokenizer_amp_dtype = os.getenv("KRONOS_TOKENIZER_AMP_DTYPE", "bf16")  # bf16 / fp16 / fp32

        # torch.compile: rotary attention 등 비표준 연산이 trace 실패할 수 있어 opt-in.
        # 활성화 시 첫 epoch 컴파일 오버헤드 발생 — 학습 길수록 ROI 큼.
        self.tokenizer_enable_compile = _env_bool("KRONOS_TOKENIZER_COMPILE", False)
        self.tokenizer_compile_mode = os.getenv("KRONOS_TOKENIZER_COMPILE_MODE", "reduce-overhead")
        self.tokenizer_compile_fullgraph = _env_bool("KRONOS_TOKENIZER_COMPILE_FULLGRAPH", False)

        # Number of samples to draw for one "epoch" of training/validation.
        # This is useful for large datasets where a true epoch is too long.
        self.n_train_iter = _env_int("KRONOS_N_TRAIN_ITER", 2000 * self.batch_size)
        self.n_val_iter = _env_int("KRONOS_N_VAL_ITER", 400 * self.batch_size)

        # Learning rates for different model components.
        self.tokenizer_learning_rate = _env_float("KRONOS_TOKENIZER_LR", 2e-4)
        self.predictor_learning_rate = _env_float("KRONOS_PREDICTOR_LR", 4e-5)

        # Gradient accumulation to simulate a larger batch size.
        self.accumulation_steps = _env_int("KRONOS_ACCUMULATION_STEPS", 1)

        # Tokenizer long-run safety. STOM full-window runs can spend days in
        # training before validation starts, so preserve the trained weights
        # before validation and release CUDA cache aggressively.
        self.tokenizer_save_pre_validation_checkpoint = _env_bool(
            "KRONOS_TOKENIZER_SAVE_PRE_VAL_CHECKPOINT",
            True,
        )
        self.tokenizer_pre_validation_checkpoint_name = os.getenv(
            "KRONOS_TOKENIZER_PRE_VAL_CHECKPOINT_NAME",
            "latest_train_model",
        )
        self.tokenizer_empty_cache_before_validation = _env_bool(
            "KRONOS_TOKENIZER_EMPTY_CACHE_BEFORE_VAL",
            True,
        )
        self.tokenizer_validation_log_interval = _env_int(
            "KRONOS_TOKENIZER_VAL_LOG_INTERVAL",
            max(1, self.log_interval),
        )
        # 0 means "validate the full validation set". Non-zero values are a
        # recovery/smoke-test guardrail for very large STOM validation pools.
        self.tokenizer_validation_max_steps = _env_int("KRONOS_TOKENIZER_VAL_MAX_STEPS", 0)

        # AdamW optimizer parameters.
        self.adam_beta1 = 0.9
        self.adam_beta2 = 0.95
        self.adam_weight_decay = 0.1

        # Miscellaneous
        self.seed = _env_int("KRONOS_SEED", 100)  # Global random seed for reproducibility.

        # =================================================================
        # Experiment Logging & Saving
        # =================================================================
        self.use_comet = _env_bool("KRONOS_USE_COMET", True) # Set to False if you don't want to use Comet ML
        self.comet_config = {
            # It is highly recommended to load secrets from environment variables
            # for security purposes. Example: os.getenv("COMET_API_KEY")
            "api_key": "YOUR_COMET_API_KEY",
            "project_name": "Kronos-Finetune-Demo",
            "workspace": "your_comet_workspace" # TODO: Change to your Comet ML workspace name
        }
        self.comet_tag = 'finetune_demo'
        self.comet_name = 'finetune_demo'

        # Base directory for saving model checkpoints and results.
        # Using a general 'outputs' directory is a common practice.
        self.save_path = os.getenv("KRONOS_SAVE_PATH", "./outputs/models")
        self.tokenizer_save_folder_name = os.getenv("KRONOS_TOKENIZER_SAVE_FOLDER", 'finetune_tokenizer_demo')
        self.predictor_save_folder_name = os.getenv("KRONOS_PREDICTOR_SAVE_FOLDER", 'finetune_predictor_demo')
        self.backtest_save_folder_name = os.getenv("KRONOS_BACKTEST_SAVE_FOLDER", 'finetune_backtest_demo')

        # Path for backtesting results.
        self.backtest_result_path = os.getenv("KRONOS_BACKTEST_RESULT_PATH", "./outputs/backtest_results")

        # =================================================================
        # Model & Checkpoint Paths
        # =================================================================
        # TODO: Update these paths to your pretrained model locations.
        # These can be local paths or Hugging Face Hub model identifiers.
        self.pretrained_tokenizer_path = os.getenv("KRONOS_PRETRAINED_TOKENIZER_PATH", "path/to/your/Kronos-Tokenizer-base")
        self.pretrained_predictor_path = os.getenv("KRONOS_PRETRAINED_PREDICTOR_PATH", "path/to/your/Kronos-small")

        # Paths to the fine-tuned models, derived from the save_path.
        # These will be generated automatically during training.
        self.finetuned_tokenizer_path = os.getenv(
            "KRONOS_FINETUNED_TOKENIZER_PATH",
            f"{self.save_path}/{self.tokenizer_save_folder_name}/checkpoints/best_model",
        )
        self.finetuned_predictor_path = os.getenv(
            "KRONOS_FINETUNED_PREDICTOR_PATH",
            f"{self.save_path}/{self.predictor_save_folder_name}/checkpoints/best_model",
        )

        # =================================================================
        # Backtesting Parameters
        # =================================================================
        self.backtest_n_symbol_hold = 50  # Number of symbols to hold in the portfolio.
        self.backtest_n_symbol_drop = 5  # Number of symbols to drop from the pool.
        self.backtest_hold_thresh = 5  # Minimum holding period for a stock.
        self.inference_T = 0.6
        self.inference_top_p = 0.9
        self.inference_top_k = 0
        self.inference_sample_count = 5
        self.backtest_batch_size = 1000
        self.backtest_benchmark = self._set_benchmark(self.instrument)

    def _set_benchmark(self, instrument):
        explicit = os.getenv("KRONOS_BACKTEST_BENCHMARK")
        if explicit:
            return explicit
        dt_benchmark = {
            'csi800': "SH000906",
            'csi1000': "SH000852",
            'csi300': "SH000300",
        }
        if instrument in dt_benchmark:
            return dt_benchmark[instrument]
        return instrument
