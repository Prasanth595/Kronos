# API 레퍼런스

총 **26개 read-only 엔드포인트** (24개 기존 + 2개 docs 신규). 모든 응답은 JSON.

## 학습 모니터링 (`/api/training/*`)

### `GET /api/training/status`
실시간 학습 상태 — v2 SPA 가 5초마다 폴링.

**응답 핵심 필드**:
```json
{
  "status": "running" | "completed" | "failed" | "idle",
  "latest_stage": {
    "train_stage": "tokenizer" | "predictor",
    "step": 3833000,
    "total_steps": 4701721,
    "overall_percent": 40.76,
    "stage_percent": 81.52,
    "eta_seconds": 54545,
    "samples_per_second": 63.71,
    "updated_at": "2026-05-13T23:34:31Z"
  },
  "readiness": {
    "level": "waiting" | "training" | "ready",
    "label": "성과 대기: tokenizer 학습 중",
    "message": "..."
  },
  "stages": [ ... ]
}
```

### `GET /api/training/history?limit=N`
손실 히스토리 + 메트릭. v2 SPA W3 손실 곡선이 사용.

**응답 핵심**: `points[{step, loss, learning_rate, epoch}]`, `latest_point`, `latest_progress`, `run_name`, `stage`.

### `GET /api/training/artifacts`
checkpoint/model_weight 파일 카운트와 예측기 진행 상태.

**응답 핵심**:
```json
{
  "checkpoint_file_count": 0,
  "model_weight_file_count": 0,
  "predictor_started": false,
  "checkpoint_ready": false,
  "label": "checkpoint 대기",
  "message": "...",
  "recent_checkpoint_files": [],
  "recent_model_weight_files": [],
  "stages": { "tokenizer": {...}, "predictor": {...} }
}
```

### `GET /api/training/gpu`
nvidia-smi 실측 — v2 SPA 5초 폴링.

**응답 핵심**:
```json
{
  "gpus": [{
    "name": "NVIDIA GeForce RTX 4080 SUPER",
    "utilization_gpu_percent": 40.0,
    "temperature_c": 50.0,
    "memory_used_mib": 3219,
    "memory_total_mib": 16376,
    "memory_used_percent": 19.7,
    "power_limit_watts": 320,
    "power_draw_watts": null,
    "power_draw_available": false
  }],
  "total_memory_used_percent": 19.7,
  "generated_at": "...",
  "available": true
}
```

### `GET /api/training/runs`
finetune/outputs/ 의 모든 run 목록.

**응답**: `{runs: [{name, path, overall_percent, status, stage_count, updated_at, updated_at_epoch}]}`

### `GET /api/training/logs?stage=tokenizer&tail=N`
학습 stdout 마지막 N줄.

## STOM 진단 (`/api/stom/*`)

### `GET /api/stom/summary`
STOM SQLite DB 요약.

**응답**: `compatible_stock_table_count`, `db_size_bytes`, `eligible_group_count`, `estimated_samples`, `table_count`, `total_rows_stock_groups`, `warnings[]`.

### `GET /api/stom/prediction-files`
예측 결과 CSV 파일 목록.

### `GET /api/stom/qlib-backtests`
QLib 백테스트 결과 JSON 파일 목록.

### `GET /api/stom/filter-reports`
필터 리포트 (filter_search 등) 파일 목록.

### `GET /api/stom/prediction?file=<path>`
특정 예측 파일 내용.

### `GET /api/stom/diagnostics?file=<path>`
진단 지표 (MAE/RMSE/MAPE 등). v2 SPA STOM 탭의 우측 패널이 사용.

### `GET /api/stom/recommendations?date=YYYY-MM-DD`
특정 날짜의 top-k 추천 종목.

### `GET /api/stom/backtest-report?file=<path>`
백테스트 상세 (P&L, drawdown 등).

### `GET /api/stom/recommendation-export`
추천 결과 CSV 다운로드.

## 예측 모델 (`/api/*`)

### `GET /api/available-models`
사용 가능한 사전학습 모델 카탈로그.

**응답**:
```json
{
  "model_available": true,
  "model_import_error": null,
  "models": {
    "kronos-base": { "name": "Kronos-base", "context_length": 512, "params": "102.3M", ... },
    "kronos-mini": { ... },
    "kronos-tiny": { ... }
  }
}
```

### `GET /api/data-files`
사용 가능한 데이터 파일 목록.

### `POST /api/load-model`
모델을 메모리에 로드.

**요청 body**: `{model_key: string, device: "cpu" | "cuda"}`

### `POST /api/load-data`
데이터 파일을 메모리에 로드.

**요청 body**: `{file_path: string}`

### `POST /api/predict`
예측 실행.

**요청 body**:
```json
{
  "lookback": 400,
  "pred_len": 120,
  "temperature": 1.0,
  "top_p": 0.9,
  "n_samples": 1,
  "seed": 42 | null,
  "device": "cpu" | "cuda"
}
```

### `GET /api/model-status`
현재 로드된 모델 상태.

## 문서 (`/api/docs/*`) — 신규

### `GET /api/docs/list`
docs/wiki/ 의 마크다운 파일 목록.

**응답**:
```json
{
  "available": true,
  "docs": [
    {"slug": "00-index", "name": "00-index.md", "title": "Kronos Wiki — 통합 지식 베이스", "size_bytes": 1234, "modified_at": 1778000000, "order": 0},
    ...
  ],
  "root": "D:\\...\\docs\\wiki"
}
```

### `GET /api/docs/read?slug=<name>`
특정 마크다운 파일 내용.

**응답**: `{slug, name, content, size_bytes, modified_at}`

**보안**: path traversal 방지 — `..`, `/`, `\`, `:` 차단 + abspath 가 docs/wiki/ 외부면 거부.

## 공통 규칙

- 모든 엔드포인트는 **read-only**: GET, POST 는 데이터 가공/예측 트리거 (서버 상태 영구 변경 0)
- 학습 데이터/모델 파일을 수정/삭제하는 엔드포인트는 **없음**
- 에러 시: `{error: string}` + HTTP 400/404/500
- 응답 시간: 보통 < 100ms (history 큰 N 제외)

## 관련 문서

- [02-architecture](02-architecture) — 데이터 흐름
- [10-dashboard-guide](10-dashboard-guide) — 어떤 탭이 어떤 API 를 쓰는지
