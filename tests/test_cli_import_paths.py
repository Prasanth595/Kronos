import subprocess
import sys


def test_train_sequential_direct_script_help_imports_project_model():
    result = subprocess.run(
        [
            sys.executable,
            "finetune_csv/train_sequential.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0
    assert "Kronos Model Sequential Fine-tuning Training" in result.stdout
