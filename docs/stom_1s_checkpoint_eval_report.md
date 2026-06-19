# STOM 1초봉 checkpoint 예측/평가 보고서

작성일: 2026-05-08

## 1. 결론

`bd5d5ca` 단계에서 생성한 pred30/pred60 budgeted checkpoint를 사용해 test split holdout 구간에서 실제 예측 CSV를 생성하고, persistence/random baseline과 비교했다.

핵심 판단:

- **30초 모델**: direction accuracy 0.3704로 기존 기준 0.40보다 낮다.
- **60초 모델**: direction accuracy 0.4444로 0.40은 넘었고 persistence/random보다 높다.
- 하지만 두 모델 모두 Qlib-style Top-K net return은 음수라서, 아직 실전 추천/자동매매 신호로 쓰기에는 부족하다.
- 이번 평가는 5개 test session, 27개 window의 제한 샘플 평가다. 방향성 확인용이며 최종 성능 확정은 아니다.

## 2. 실행 명령

### 2.1 30초 checkpoint 평가

```powershell
python finetune\evaluate_stom_1s_checkpoint.py `
  --dataset-path finetune\qlib_exports\stom_1s_grid_pred30_full\processed_datasets `
  --model-path finetune\outputs\stom_1s_grid_pred30_full_budget\finetune_predictor\checkpoints\best_model `
  --output-dir webui\stom_predictions `
  --prefix stom_1s_pred30_budget_holdout_eval `
  --lookback-window 300 `
  --predict-window 30 `
  --max-symbols 20 `
  --max-asofs 1 `
  --max-sessions 5 `
  --stride 300 `
  --batch-size 4 `
  --top-k 5 `
  --device cuda:0
```

### 2.2 60초 checkpoint 평가

```powershell
python finetune\evaluate_stom_1s_checkpoint.py `
  --dataset-path finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --model-path finetune\outputs\stom_1s_grid_pred60_full_budget\finetune_predictor\checkpoints\best_model `
  --output-dir webui\stom_predictions `
  --prefix stom_1s_pred60_budget_holdout_eval `
  --lookback-window 300 `
  --predict-window 60 `
  --max-symbols 20 `
  --max-asofs 1 `
  --max-sessions 5 `
  --stride 300 `
  --batch-size 4 `
  --top-k 5 `
  --device cuda:0
```

### 2.3 Qlib-style Top-K artifact 생성

```powershell
python finetune\qlib_stom_pipeline.py score-backtest `
  --prediction-csv webui\stom_predictions\stom_1s_pred30_budget_holdout_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10

python finetune\qlib_stom_pipeline.py score-backtest `
  --prediction-csv webui\stom_predictions\stom_1s_pred60_budget_holdout_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10
```

## 3. 예측 CSV 산출물

아래 파일은 `.gitignore` 대상인 실행 산출물이다. commit에는 파일 자체가 아니라 재현 명령과 지표만 남긴다.

```text
webui/stom_predictions/stom_1s_pred30_budget_holdout_eval_kronos.csv
webui/stom_predictions/stom_1s_pred30_budget_holdout_eval_persistence.csv
webui/stom_predictions/stom_1s_pred30_budget_holdout_eval_random.csv
webui/stom_predictions/stom_1s_pred30_budget_holdout_eval_comparison.json

webui/stom_predictions/stom_1s_pred60_budget_holdout_eval_kronos.csv
webui/stom_predictions/stom_1s_pred60_budget_holdout_eval_persistence.csv
webui/stom_predictions/stom_1s_pred60_budget_holdout_eval_random.csv
webui/stom_predictions/stom_1s_pred60_budget_holdout_eval_comparison.json
```

웹 대시보드에서 확인:

```text
python webui\run.py
http://localhost:7070/stom
```

## 4. direction accuracy 비교

| horizon | mode | windows | symbols | direction accuracy | 0.40 초과 | avg actual return |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| 30초 | Kronos checkpoint | 27 | 25 | 0.3704 | 아니오 | 0.0963 |
| 30초 | persistence | 27 | 25 | 0.2222 | 아니오 | 0.0963 |
| 30초 | random | 27 | 25 | 0.1111 | 아니오 | 0.0963 |
| 60초 | Kronos checkpoint | 27 | 25 | 0.4444 | 예 | 0.1790 |
| 60초 | persistence | 27 | 25 | 0.1111 | 아니오 | 0.1790 |
| 60초 | random | 27 | 25 | 0.2963 | 아니오 | 0.1790 |

해석:

- 30초 모델은 기존 0.40 문제를 해결하지 못했다.
- 60초 모델은 제한 샘플에서 0.4444로 개선 신호가 있다.
- 그러나 27개 window만 평가했으므로 통계적으로 충분하지 않다. 더 많은 session/asof/symbol로 walk-forward 평가가 필요하다.

## 5. Top-K 성과 비교

| horizon | mode | top-k trades | top-k direction hit | top-k avg actual return |
| --- | --- | ---: | ---: | ---: |
| 30초 | Kronos checkpoint | 24 | 0.4167 | -0.0815 |
| 30초 | persistence | 24 | 0.2083 | 0.0187 |
| 30초 | random | 24 | 0.1250 | -0.0815 |
| 60초 | Kronos checkpoint | 24 | 0.5000 | -0.0917 |
| 60초 | persistence | 24 | 0.1250 | 0.0085 |
| 60초 | random | 24 | 0.2917 | -0.0666 |

Qlib-style cost 반영 Top-K 결과:

| horizon | avg gross return | avg net return | cumulative return | direction hit |
| --- | ---: | ---: | ---: | ---: |
| 30초 | -0.0956 | -0.3456 | -1.7169 | 0.4167 |
| 60초 | -0.1044 | -0.3544 | -1.7605 | 0.5000 |

해석:

- 60초 모델은 방향 hit는 개선됐지만, Top-K로 골랐을 때 실제 수익률은 아직 음수다.
- 수수료/슬리피지 25bp를 넣으면 net return은 더 나빠진다.
- 따라서 현재 checkpoint는 **연구/시각화/추가 필터 개발 대상**이며, 실전 매수 추천 모델로 바로 사용하면 안 된다.

## 6. 다음 개선 방향

1. 평가 표본 확대: `--max-sessions`, `--max-asofs`, `--max-symbols`를 늘려 최소 수백~수천 window 평가.
2. horizon 선택: 현재 제한 샘플에서는 30초보다 60초가 낫다.
3. 조건식 보완: predicted return만 쓰는 Top-K가 음수이므로 거래대금, 체결강도, 변동성, spread, 당일 상대강도 조건을 추가해야 한다.
4. 학습 강화: budgeted 20,000 sample 1 epoch보다 큰 학습 예산과 여러 seed 비교가 필요하다.
5. 대시보드 확장: 현재 CSV는 대시보드에서 실제값/예측값 차트 확인 가능하므로, 다음 단계는 평가 조건과 필터별 성과 표를 화면에 더 명확히 노출한다.
