
import json
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
WEBUI_DIR = REPO_ROOT / "webui"
if str(WEBUI_DIR) not in sys.path:
    sys.path.insert(0, str(WEBUI_DIR))

import training_monitor  # noqa: E402


def _write_progress(run_dir: Path, stage: str = "predictor") -> None:
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout = logs / f"{stage}.stdout.log"
    stdout.write_text("line 1\nline 2\n", encoding="utf-8")
    progress = {
        "schema_version": 1,
        "created_at": "2026-05-11T00:00:00Z",
        "updated_at": "2026-05-11T00:01:00Z",
        "status": "running",
        "run_name": run_dir.name,
        "horizon": 60,
        "mode": "full",
        "train_stage": stage,
        "stage": {"index": 2, "count": 2, "name": stage, "percent": 25.0, "overall_percent": 62.5},
        "progress": {"epoch": 1, "epochs": 1, "step": 25, "total_steps": 100},
        "metrics": {"last_loss": 0.5, "last_validation_loss": None, "best_val_loss": None},
        "timing": {"elapsed_seconds": 10, "eta_seconds": 30, "samples_per_second": 10.0},
        "paths": {"stdout_log": str(stdout), "stderr_log": str(logs / f"{stage}.stderr.log")},
        "last_line": "latest",
    }
    (logs / f"{stage}.progress.json").write_text(json.dumps(progress), encoding="utf-8")


def test_training_monitor_lists_status_and_tails_logs(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    run_dir = output_root / "unit_run"
    _write_progress(run_dir)
    monkeypatch.setattr(training_monitor, "OUTPUT_ROOTS", [output_root])

    runs = training_monitor.list_training_runs()
    status = training_monitor.load_training_status("unit_run")
    tail = training_monitor.tail_training_log("unit_run", stage="predictor", lines=1)

    assert runs[0]["name"] == "unit_run"
    assert runs[0]["status"] == "running"
    assert status["overall_percent"] == 62.5
    assert status["latest_stage"]["train_stage"] == "predictor"
    assert tail["lines"] == ["line 2"]


def test_training_monitor_inspects_checkpoint_artifacts(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    run_dir = output_root / "unit_run"
    _write_progress(run_dir, stage="tokenizer")
    tokenizer_model = run_dir / "finetune_tokenizer" / "checkpoints" / "best_model" / "model.safetensors"
    tokenizer_model.parent.mkdir(parents=True)
    tokenizer_model.write_text("tokenizer", encoding="utf-8")
    predictor_model = run_dir / "finetune_predictor" / "checkpoints" / "best_model" / "pytorch_model.bin"
    predictor_model.parent.mkdir(parents=True)
    predictor_model.write_text("predictor", encoding="utf-8")
    monkeypatch.setattr(training_monitor, "OUTPUT_ROOTS", [output_root])

    artifacts = training_monitor.inspect_training_artifacts("unit_run")

    assert artifacts["model_weight_file_count"] == 2
    assert artifacts["checkpoint_file_count"] == 2
    assert artifacts["tokenizer_checkpoint_ready"] is True
    assert artifacts["predictor_checkpoint_ready"] is True
    assert artifacts["level"] == "ready"
    assert artifacts["stages"]["tokenizer"]["checkpoint_file_count"] == 1
    assert artifacts["stages"]["predictor"]["checkpoint_file_count"] == 1


def test_training_monitor_parses_progress_history(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    run_dir = output_root / "unit_run"
    _write_progress(run_dir, stage="tokenizer")
    stdout = run_dir / "logs" / "tokenizer.stdout.log"
    stdout.write_text(
        "\n".join(
            [
                "[Rank 0, Epoch 1/1, Step 100/1000] LR 0.000200, Loss: -0.0100",
                "noise line",
                "[Rank 0, Epoch 1/1, Step 200/1000] LR 0.000190, Loss: -0.0200",
                "[Rank 0, Epoch 1/1, Step 300/1000] LR 0.000180, Loss: -0.0300",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(training_monitor, "OUTPUT_ROOTS", [output_root])

    history = training_monitor.load_training_history("unit_run", stage="tokenizer", limit=2)

    assert history["stage"] == "tokenizer"
    assert history["point_count"] == 2
    assert [point["step"] for point in history["points"]] == [200, 300]
    assert history["latest_point"]["loss"] == -0.03
    assert history["latest_point"]["stage_percent"] == 30.0


def test_training_monitor_history_does_not_fallback_for_requested_empty_stage(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    run_dir = output_root / "unit_run"
    _write_progress(run_dir, stage="tokenizer")
    _write_progress(run_dir, stage="predictor")
    (run_dir / "logs" / "predictor.stdout.log").unlink()
    (run_dir / "logs" / "tokenizer.stdout.log").write_text(
        "[Rank 0, Epoch 1/1, Step 100/1000] LR 0.000200, Loss: -0.0100",
        encoding="utf-8",
    )
    monkeypatch.setattr(training_monitor, "OUTPUT_ROOTS", [output_root])

    history = training_monitor.load_training_history("unit_run", stage="predictor", limit=5)

    assert history["stage"] == "predictor"
    assert history["point_count"] == 0
    assert "no stdout log" in history["error"]


def test_training_monitor_rejects_path_traversal(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    monkeypatch.setattr(training_monitor, "OUTPUT_ROOTS", [output_root])

    try:
        training_monitor.resolve_run_dir("..\\secret")
    except ValueError as exc:
        assert "direct" in str(exc)
    else:
        raise AssertionError("path traversal run name was accepted")


def test_query_gpu_status_parses_nvidia_smi(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "0, NVIDIA GeForce RTX 4080 SUPER, 75, 9000, 16376, 250.5, 320.0, 61\n"
        stderr = ""

    monkeypatch.setattr(training_monitor.subprocess, "run", lambda *args, **kwargs: Completed())

    status = training_monitor.query_gpu_status()

    assert status["available"] is True
    assert status["gpus"][0]["name"] == "NVIDIA GeForce RTX 4080 SUPER"
    assert status["gpus"][0]["utilization_gpu_percent"] == 75.0
    assert status["gpus"][0]["memory_used_percent"] == 54.96
    assert status["gpus"][0]["power_draw_available"] is True
    assert status["total_power_draw_watts"] == 250.5
    assert status["total_power_limit_watts"] == 320.0
    assert status["average_utilization_gpu_percent"] == 75.0
    assert status["total_memory_used_percent"] == 54.96


def test_query_gpu_status_reports_power_limit_when_power_draw_is_missing(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "0, NVIDIA GeForce RTX 4080 SUPER, 43, 3328, 16376, [Not Supported], 320.0, 49\n"
        stderr = ""

    monkeypatch.setattr(training_monitor.subprocess, "run", lambda *args, **kwargs: Completed())

    status = training_monitor.query_gpu_status()

    assert status["available"] is True
    assert status["power_draw_available"] is False
    assert status["total_power_draw_watts"] is None
    assert status["total_power_limit_watts"] == 320.0
    assert status["gpus"][0]["power_draw_available"] is False


def test_query_system_status_uses_optional_psutil(monkeypatch):
    class FakePsutil:
        @staticmethod
        def cpu_percent(interval=0.1):
            return 42.5

        @staticmethod
        def virtual_memory():
            return SimpleNamespace(percent=61.2, total=128 * 1024**3, available=48 * 1024**3)

        @staticmethod
        def sensors_temperatures(fahrenheit=False):
            return {"k10temp": [SimpleNamespace(current=63.4, label="Tctl")]}

    monkeypatch.setattr(training_monitor, "_psutil", FakePsutil)
    monkeypatch.setitem(training_monitor._SYSTEM_STATUS_CACHE, "payload", None)
    monkeypatch.setitem(training_monitor._SYSTEM_STATUS_CACHE, "expires_at", 0.0)

    status = training_monitor.query_system_status(cache_seconds=0)

    assert status["available"] is True
    assert status["cpu"]["utilization_percent"] == 42.5
    assert status["cpu"]["temperature_c"] == 63.4
    assert status["cpu"]["temperature_percent"] == 66.74
    assert status["memory"]["used_percent"] == 61.2


def test_training_dashboard_routes_register(monkeypatch):
    import app as webapp  # noqa: E402

    monkeypatch.setattr(webapp, "list_training_runs", lambda limit=50: [])
    monkeypatch.setattr(
        webapp,
        "load_training_status",
        lambda run_name=None: {
            "run_name": "unit",
            "status": "running",
            "latest_stage": {"train_stage": "tokenizer", "status": "running"},
            "stages": [{"train_stage": "tokenizer", "status": "running"}],
        },
    )
    monkeypatch.setattr(webapp, "tail_training_log", lambda run_name=None, stage=None, lines=200: {"lines": [], "text": ""})
    monkeypatch.setattr(webapp, "query_gpu_status", lambda: {"available": False, "gpus": []})
    monkeypatch.setattr(webapp, "query_system_status", lambda: {"available": True, "cpu": {"utilization_percent": 10}})
    monkeypatch.setattr(
        webapp,
        "load_training_history",
        lambda run_name=None, stage=None, limit=40: {
            "run_name": "unit",
            "stage": "tokenizer",
            "point_count": 1,
            "points": [{"step": 1, "total_steps": 10, "stage_percent": 10.0, "overall_percent": 5.0, "learning_rate": 0.1, "loss": 0.2}],
            "latest_point": {"step": 1, "total_steps": 10},
            "latest_progress": {"updated_at": "2026-05-11T00:01:00Z"},
        },
    )
    monkeypatch.setattr(
        webapp,
        "inspect_training_artifacts",
        lambda run_name=None, limit=50: {
            "run_name": "unit",
            "level": "waiting",
            "label": "checkpoint 대기",
            "message": "checkpoint 없음",
            "model_weight_file_count": 0,
            "checkpoint_file_count": 0,
            "predictor_started": False,
            "stages": {
                "tokenizer": {"checkpoint_ready": False, "checkpoint_file_count": 0},
                "predictor": {"checkpoint_ready": False, "checkpoint_file_count": 0},
            },
            "recent_checkpoint_files": [],
            "recent_model_weight_files": [],
        },
    )

    client = webapp.app.test_client()

    # P6 cutover 이후 v1 markup 검증은 /v1/* prefix 로 이동
    training_html = client.get("/v1/training").get_data(as_text=True)
    index_html = client.get("/v1/").get_data(as_text=True)
    stom_html = client.get("/v1/stom").get_data(as_text=True)

    assert "autoRefreshEnabled" in training_html
    assert "refreshIntervalSeconds" in training_html
    assert "trainingReadinessCard" in training_html
    assert "trainingArtifactCard" in training_html
    assert "runtimeSummaryCard" in training_html
    assert "gpuSummaryMetrics" in training_html
    assert "historyRows" in training_html
    assert "formatKstDateTime" in training_html
    assert "formatKstEtaTarget" in training_html
    assert "Finish time(KST)" in training_html
    assert "trainingInlinePanel" in index_html
    assert "Kronos 금융 예측 웹 UI" in index_html
    assert "제어 패널" in index_html
    assert "대시보드 메뉴" in index_html
    assert 'class="active"' in index_html
    assert "trainingInlineReadiness" in index_html
    assert "trainingInlineFinish" in index_html
    assert "formatKstDateTime" in index_html
    assert "stomTrainingStrip" in stom_html
    assert "stomTrainingReadiness" in stom_html
    assert "stomTrainingFinish" in stom_html
    assert "stomKstGate" in stom_html
    assert "stomTrainingArtifacts" in stom_html
    assert "stomPerformanceGate" in stom_html
    assert "stomPredictorGate" in stom_html
    assert "stomCheckpointGate" in stom_html
    assert "stomRuntimeGate" in stom_html
    assert client.get("/api/training/runs").get_json() == {"runs": []}
    status_json = client.get("/api/training/status").get_json()
    assert status_json["run_name"] == "unit"
    assert status_json["readiness"]["performance_ready"] is False
    assert "토크나이저" in status_json["readiness"]["message"]
    artifact_json = client.get("/api/training/artifacts").get_json()
    assert artifact_json["label"] == "checkpoint 대기"
    assert artifact_json["model_weight_file_count"] == 0
    assert client.get("/api/training/history").get_json()["point_count"] == 1
    assert client.get("/api/training/logs").get_json()["text"] == ""
    assert client.get("/api/training/gpu").get_json()["available"] is False
    assert client.get("/api/training/system").get_json()["cpu"]["utilization_percent"] == 10


def test_training_readiness_policy_marks_predictor_states():
    import app as webapp  # noqa: E402

    tokenizer_payload = {
        "status": "running",
        "latest_stage": {"train_stage": "tokenizer", "status": "running"},
        "stages": [{"train_stage": "tokenizer", "status": "running"}],
    }
    predictor_payload = {
        "status": "running",
        "latest_stage": {"train_stage": "predictor", "status": "running"},
        "stages": [{"train_stage": "predictor", "status": "running", "stage_percent": 50}],
    }
    complete_payload = {
        "status": "completed",
        "latest_stage": {"train_stage": "predictor", "status": "completed"},
        "stages": [{"train_stage": "predictor", "status": "completed", "stage_percent": 100}],
    }
    ok_completed_phase_payload = {
        "status": "ok",
        "latest_stage": {"train_stage": "predictor", "status": "ok", "phase": "completed"},
        "stages": [{"train_stage": "predictor", "status": "ok", "phase": "completed", "stage_percent": 99.9974}],
    }

    tokenizer = webapp.build_training_readiness(tokenizer_payload)
    predictor = webapp.build_training_readiness(predictor_payload)
    complete = webapp.build_training_readiness(complete_payload)
    ok_completed_phase = webapp.build_training_readiness(ok_completed_phase_payload)

    assert tokenizer["level"] == "waiting"
    assert tokenizer["performance_ready"] is False
    assert predictor["level"] == "training"
    assert predictor["predictor_started"] is True
    assert predictor["performance_ready"] is False
    assert complete["level"] == "ready"
    assert complete["performance_ready"] is True
    assert ok_completed_phase["level"] == "ready"
    assert ok_completed_phase["performance_ready"] is True


def test_training_dashboard_refresh_interval_is_configurable_and_clamped(monkeypatch):
    import app as webapp  # noqa: E402

    monkeypatch.setattr(webapp, "list_training_runs", lambda limit=50: [])
    monkeypatch.setattr(webapp, "load_training_status", lambda run_name=None: {"run_name": "unit", "stages": []})
    monkeypatch.setattr(webapp, "tail_training_log", lambda run_name=None, stage=None, lines=200: {"lines": [], "text": ""})
    monkeypatch.setattr(webapp, "query_gpu_status", lambda: {"available": False, "gpus": []})
    monkeypatch.setattr(webapp, "query_system_status", lambda: {"available": False, "cpu": {}})

    client = webapp.app.test_client()

    # P6 cutover: v1 refresh_interval 동작은 /v1/* 에서만 검증 (`/` 는 v2 SPA)
    too_fast = client.get("/v1/training?refresh_interval=1").get_data(as_text=True)
    custom = client.get("/v1/training?refresh_interval=17").get_data(as_text=True)
    too_slow = client.get("/v1/training?refresh_interval=99999").get_data(as_text=True)
    index_custom = client.get("/v1/?refresh_interval=11").get_data(as_text=True)
    stom_custom = client.get("/v1/stom?refresh_interval=13").get_data(as_text=True)

    assert 'data-default-refresh-seconds="2"' in too_fast
    assert 'value="17"' in custom
    assert 'data-default-refresh-seconds="3600"' in too_slow
    assert 'data-default-refresh-seconds="11"' in index_custom
    assert 'data-default-refresh-seconds="13"' in stom_custom
