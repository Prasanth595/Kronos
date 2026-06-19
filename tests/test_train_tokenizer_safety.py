import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_DIR = PROJECT_ROOT / "finetune"
if str(FINETUNE_DIR) not in sys.path:
    sys.path.insert(0, str(FINETUNE_DIR))

from tokenizer_safety import (  # noqa: E402
    is_cuda_oom_error,
    resolve_tokenizer_validation_batch_size,
    save_tokenizer_checkpoint,
    write_tokenizer_validation_failure,
)


class DummyTokenizer:
    def save_pretrained(self, save_path):
        path = Path(save_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "model.safetensors").write_text("dummy", encoding="utf-8")


def test_resolve_tokenizer_validation_batch_size_uses_safe_positive_value():
    assert resolve_tokenizer_validation_batch_size({"batch_size": 4}) == 4
    assert resolve_tokenizer_validation_batch_size({"batch_size": 4, "tokenizer_validation_batch_size": 1}) == 1
    assert resolve_tokenizer_validation_batch_size({"batch_size": 4, "tokenizer_validation_batch_size": 0}) == 1


def test_tokenizer_checkpoint_before_validation_is_written_by_rank_zero(tmp_path):
    saved = save_tokenizer_checkpoint(
        DummyTokenizer(),
        str(tmp_path),
        "latest_train_model",
        rank=0,
        reason="unit test",
    )

    assert saved == str(tmp_path / "checkpoints" / "latest_train_model")
    assert (tmp_path / "checkpoints" / "latest_train_model" / "model.safetensors").exists()


def test_validation_failure_artifact_records_cuda_oom_context(tmp_path):
    exc = RuntimeError("CUDA error: out of memory")

    saved = write_tokenizer_validation_failure(
        str(tmp_path),
        epoch_idx=0,
        exc=exc,
        pre_validation_checkpoint=str(tmp_path / "checkpoints" / "latest_train_model"),
        rank=0,
    )
    payload = json.loads(Path(saved).read_text(encoding="utf-8"))

    assert is_cuda_oom_error(exc) is True
    assert payload["stage"] == "tokenizer_validation"
    assert payload["epoch"] == 1
    assert payload["is_cuda_oom"] is True
    assert payload["pre_validation_checkpoint"].endswith("latest_train_model")
