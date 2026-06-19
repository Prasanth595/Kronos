# STOM Qlib 실제 실행 단계 점검 보고서

작성일: 2026-05-07

## 핵심 결론

- `pyqlib 0.9.7` 설치 후 `qlib-env-check`가 성공했다.
- pip wheel에는 `scripts/dump_bin.py`가 포함되지 않아 Microsoft Qlib source를 `.omx/external/qlib`에 clone해 사용했다.
- Qlib upstream `dump_bin.py`의 현재 인자는 `--csv_path`가 아니라 `--data_path`이므로 파이프라인 코드를 수정했다.
- STOM DB 읽기 전용 파일럿 export는 1초봉/1분봉 모두 성공했다.
- `dump_bin --execute`는 1초봉/1분봉 모두 성공했다.
- pyqlib provider smoke는 1분봉에서 성공했고, 1초봉은 pyqlib `Freq` parser가 지원하지 않는 제약을 확인했다.

## 실행 환경 점검

```powershell
python finetune\qlib_stom_pipeline.py qlib-env-check
```

요약:

```json
{
  "qlib_installed": true,
  "qlib_version": "0.9.7",
  "dump_bin_script_found": true,
  "dump_bin_script": "D:\\Chanil_Park\\Project\\Programming\\Kronos\\.omx\\external\\qlib\\scripts\\dump_bin.py"
}
```

추가 검증:

```powershell
python -m pip check
```

결과:

```text
No broken requirements found.
```

## 1초봉 파일럿

명령:

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_stage_pyqlib_pilot `
  --max-tables 2 `
  --lookback-window 30 `
  --predict-window 5 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1s `
  --max-groups 4 `
  --train-ratio 0.5 `
  --val-ratio 0.25 `
  --test-ratio 0.25
```

결과:

| 항목 | 값 |
| --- | --- |
| selected tables | 2 |
| exported groups | 4 |
| exported rows | 4,792 |
| train rows | 1,971 |
| val rows | 1,292 |
| test rows | 1,529 |
| 주요 warning | `종가 column not found; using 현재가 as close.` |

`dump_bin --execute --freq 1s` 결과는 성공이다. 다만 provider smoke:

```powershell
python finetune\qlib_stom_pipeline.py provider-smoke `
  --provider-uri finetune\qlib_exports\stom_1s_stage_pyqlib_pilot\qlib_bin `
  --region cn `
  --freq 1s
```

결과는 의도적으로 실패 처리된다.

```text
pyqlib provider does not support second-level freq such as '1s'.
```

판단: 1초봉은 Qlib provider보다 Kronos `processed_datasets/*.pkl` fine-tuning 경로를 우선 사용한다.

## 1분봉 파일럿

명령:

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1min_stage_pyqlib_pilot `
  --max-tables 2 `
  --lookback-window 20 `
  --predict-window 5 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1min `
  --max-groups 4 `
  --train-ratio 0.5 `
  --val-ratio 0.25 `
  --test-ratio 0.25
```

결과:

| 항목 | 값 |
| --- | --- |
| selected tables | 2 |
| exported groups | 4 |
| exported rows | 112 |
| train rows | 57 |
| val rows | 28 |
| test rows | 27 |
| 주요 warning | `종가 column not found; using 현재가 as close.` |

실제 변환:

```powershell
python finetune\qlib_stom_pipeline.py dump-bin `
  --export-report finetune\qlib_exports\stom_1min_stage_pyqlib_pilot\stom_qlib_export_report.json `
  --qlib-dir finetune\qlib_exports\stom_1min_stage_pyqlib_pilot\qlib_bin `
  --dump-bin-script .omx\external\qlib\scripts\dump_bin.py `
  --freq 1min `
  --execute
```

결과: `returncode: 0`, `status: ok`.

Provider smoke:

```powershell
python finetune\qlib_stom_pipeline.py provider-smoke `
  --provider-uri finetune\qlib_exports\stom_1min_stage_pyqlib_pilot\qlib_bin `
  --region cn `
  --freq 1min
```

결과:

```json
{
  "mode": "qlib_provider_smoke",
  "freq": "1min",
  "calendar_count": 112,
  "calendar_sample": [
    "2022-12-12 09:00:00",
    "2022-12-12 09:01:00",
    "2022-12-12 09:02:00",
    "2022-12-12 09:03:00",
    "2022-12-12 09:04:00"
  ]
}
```

## 다음 개발 판단

1. 1분봉 Qlib provider 경로는 실제 사용 가능 상태로 본다.
2. 1초봉 Qlib `.bin`은 생성 가능하지만 pyqlib provider 로딩은 공식 freq 제약 때문에 보류한다.
3. 1초봉 Kronos 학습은 `processed_datasets/train_data.pkl`, `val_data.pkl`, `test_data.pkl`을 직접 사용하는 기존 `finetune/train_predictor.py` 경로가 맞다.
4. 다음 단계는 1분봉 Qlib provider에서 feature load/backtest를 안정화하거나, 1초봉 Kronos 학습 자동 실행/재개/로그 대시보드 연결로 진행한다.
