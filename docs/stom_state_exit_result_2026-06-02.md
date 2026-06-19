# STOM ④ State-Conditioned Early-Exit Gate 결과 — 2026-06-02

## 결론

`ts_imb` 시초 갭상승 규칙 진입 후 **30초 시점에 아직 열려 있는 거래**에 대해
“지금 시장가 청산”이 “기존 TP5/SL1/09:25까지 계속 보유”보다 나은지를 검증했다.

**Full-universe verdict: `NO-GO`.**

핵심 이유는 primary 모델(`gbm`)에서 선택된 조기청산 정책이 baseline보다 오히려 낮은 평균 수익을 냈고,
CI/DSR/positive-boundary 조건을 모두 통과하지 못했기 때문이다. 5개 deterministic shuffled-feature
negative control은 모두 `NO-GO`로 정상 통과했지만, primary 자체가 GO 조건을 만족하지 못했다.

> 구현 완료 / synthetic 회계·누수 테스트 통과 / DB smoke 통과 / full-data verdict NO-GO

## 중요한 해석 경계

- 이 실험은 **강화학습(RL)이 아니라 RULE/supervised risk-control gate**이다.
- 목표는 방향 예측이 아니라, 이미 진입한 `ts_imb` 거래 중 30초 이후 계속 보유할지 조기청산할지를 평가하는 것이다.
- target은 `early_exit_now_net_pct - baseline_continue_net_pct`이며, 23bp 비용과 marketable fill을 반영했다.
- 30초 전에 이미 TP/SL/시간 조건으로 닫힌 거래는 원거래 분모에 포함하되 incremental delta는 0으로 처리했다.
- 최종 GO는 primary `gbm`만 가능하며, `ridge`는 diagnostic-only로 유지했다.

## 구현 파일

| 파일 | 내용 |
|---|---|
| `stom_rl/state_exit_gate.py` | 30초 state-conditioned early-exit gate, DB extractor, CLI, negative controls |
| `tests/test_stom_rl_state_exit_gate.py` | 합성 데이터 회계/누수/게이트/negative-control 회귀 테스트 |
| `docs/stom_state_exit_result_2026-06-02.md` | 본 결과 문서 |

## 사전등록 기준 요약

| 항목 | 값 |
|---|---|
| checkpoint | 30초 |
| baseline | 기존 TP5/SL1/09:25 계속 보유 |
| candidate action | 30초 시장가 조기청산 |
| primary model | `gbm` |
| diagnostic model | `ridge` |
| primary boundary | `0.7` |
| robustness boundaries | `[0.5, 0.6, 0.7, 0.8, 0.9]` |
| exit fraction grid | `[0.10, 0.20, 0.30, 0.40]` |
| negative controls | deterministic shuffled-feature 5개, 모두 NO-GO 필요 |

## Full-universe 실행

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.state_exit_gate --db-path _database/stock_tick_back.db --output-dir .omx/artifacts/state_exit --n-bootstrap 1000 --n-negative-shuffles 5
```

결과:

```text
instances=5173 eligible=4123 eligible_rate=0.797 baseline_mean=0.4197% eligible_delta_mean=-0.5105%
-- primary boundary 0.7 --
   ridge inc=-0.0031% CI95=[-0.0488,0.0439] DSR=0.000 delta=-0.0194% exits=310 pos_bounds=1 -> no diagnostic
   gbm   inc=-0.0175% CI95=[-0.0842,0.0492] DSR=0.000 delta=-0.0546% exits=619 pos_bounds=0 -> no
negative controls: ['NO-GO', 'NO-GO', 'NO-GO', 'NO-GO', 'NO-GO']
VERDICT: NO-GO
wrote -> .omx\artifacts\state_exit\summary.json
```

핵심 수치:

| 항목 | ridge diagnostic | gbm primary |
|---|---:|---:|
| selected exit fraction | 0.20 | 0.40 |
| policy exits | 310 | 619 |
| incremental mean / original trade | -0.0031% | -0.0175% |
| CI95 | [-0.0488, 0.0439] | [-0.0842, 0.0492] |
| DSR | ~0.000 | ~0.000 |
| exited delta mean | -0.0194% | -0.0546% |
| positive boundary count | 1 | 0 |
| model GO | False | False |

## Smoke 실행

### 20종목 smoke

```powershell
py -3.11 -X utf8 -m stom_rl.state_exit_gate --db-path _database/stock_tick_back.db --max-symbols 20 --output-dir .omx/artifacts/state_exit_smoke --n-bootstrap 100 --n-negative-shuffles 5
```

```text
instances=48 eligible=44 eligible_rate=0.917 baseline_mean=-0.2044% eligible_delta_mean=0.1627%
VERDICT: INCONCLUSIVE
```

표본 부족으로 모델 gate 전까지의 추출/저장 경로만 확인했다.

### 100종목 smoke

```powershell
py -3.11 -X utf8 -m stom_rl.state_exit_gate --db-path _database/stock_tick_back.db --max-symbols 100 --output-dir .omx/artifacts/state_exit_smoke_100 --n-bootstrap 100 --n-negative-shuffles 5
```

```text
instances=204 eligible=175 eligible_rate=0.858 baseline_mean=0.5039% eligible_delta_mean=-0.5847%
ridge inc=-0.0776% CI95=[-0.4607,0.2782] DSR=0.054 delta=-0.2364% exits=22 pos_bounds=1 -> no diagnostic
gbm   inc=-0.1126% CI95=[-0.5100,0.1968] DSR=0.037 delta=-0.3431% exits=22 pos_bounds=0 -> no
negative controls: ['INCONCLUSIVE', 'INCONCLUSIVE', 'INCONCLUSIVE', 'INCONCLUSIVE', 'INCONCLUSIVE']
VERDICT: INCONCLUSIVE
```

100종목도 사전등록 최소 count에는 부족하지만 모델/negative-control 경로는 실행됐다.

## 테스트/검증

### 신규 단독 테스트

```powershell
py -3.11 -m pytest tests/test_stom_rl_state_exit_gate.py -q
```

```text
12 passed
```

검증 내용:

- top-fraction ranking
- eligible-only prediction mapping
- 전체 원거래 분모 회계
- train-only exit fraction 선택
- planted positive edge GO
- noise NO-GO
- primary count 부족 시 INCONCLUSIVE
- negative-control hard blocker
- 30초 전 종료 거래 incremental=0
- 30초 checkpoint 조기청산 수익 계산
- checkpoint 이후 row 변경 시 feature 불변

### 관련 회귀 묶음

```powershell
py -3.11 -m pytest tests/test_stom_rl_state_exit_gate.py tests/test_stom_rl_sl_predictor.py tests/test_stom_rl_marketable_fill.py tests/test_stom_rl_exit_baselines.py tests/test_stom_rl_skip_gate.py -q
```

```text
59 passed
```

### `tests/` 전체

```powershell
py -3.11 -m pytest tests -q
```

```text
471 passed, 2 skipped, 351 warnings
```

### 전체 repo pytest 시도

```powershell
py -3.11 -m pytest -q
```

결과: `finetune/qlib_test.py` collection 중 `torch` DLL 로딩 오류로 중단.

```text
OSError: [WinError 1114] DLL 초기화 루틴을 실행할 수 없습니다.
Error loading ... torch\lib\c10.dll
```

이는 이번 변경 파일의 테스트 실패가 아니라 로컬 torch 환경 collection 문제로 보인다.

## 다음 결정

④ state-conditioned early-exit gate는 full-universe 기준 **NO-GO로 닫는다.**

현재까지의 실험 흐름상:

1. entry skip-gate: NO-GO
2. PPO/RL candidate: NO-GO_USABLE_MODEL
3. 30초 state-conditioned early-exit gate: NO-GO

다음 단계는 새 모델을 더 복잡하게 만드는 것보다, 먼저 STOM `ts_imb` edge를 훼손하지 않는 **운영 리스크 제어** 또는 **체결/유동성 기반 필터**를 작은 사전등록 실험으로 분리하는 것이 더 안전하다.
