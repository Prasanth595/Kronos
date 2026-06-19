# finetune Knowledge

## Overview

`finetune/` contains STOM/Qlib export, predictor/tokenizer training, checkpoint
evaluation, and staged full-training scripts.

## Key Files

| File | Role |
|---|---|
| `qlib_stom_pipeline.py` | Large STOM-to-Qlib pipeline. |
| `run_stom_1s_finetune.py` | Main STOM 1-second finetune runner. |
| `train_tokenizer.py` | Tokenizer training. |
| `train_predictor.py` | Predictor training. |
| `evaluate_stom_1s_checkpoint.py` | Checkpoint evaluation. |
| `preflight_stom_2025_full.py` | Full-training preflight. |
| `stom_rl_c0_feature_probe.py` | Feature probe feeding RL research. |

## Rules

- Separate source code from generated outputs/checkpoints.
- Keep CLI import paths working from repository root.
- Treat GPU/CUDA/torch failures as environment-sensitive until isolated.
- Avoid mixing training-result claims with trading-strategy claims.
- Document any data split, prediction horizon, and cost assumption in outputs.
- Do not overwrite large checkpoints or exported datasets unless explicitly asked.
- Keep stock-code strings zero-padded through export and training metadata.
- Prefer resumable/checkpointed long jobs; record command and output path in docs.

## Verification

```powershell
py -3.11 -m pytest tests/test_cli_import_paths.py tests/test_stom_1s_finetune_runner.py -q
```

Torch-heavy tests may be opt-in or environment-sensitive on Windows.

## Gotchas

- `finetune/outputs/` and nested checkpoint folders are generated artifacts.
- Qlib import paths can fail from the wrong working directory; test CLI imports
  after moving runners.
