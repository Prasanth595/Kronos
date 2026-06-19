# STOM ① Skip-Gate 구현 결과 — 2026-06-01

## 결론

`skip-gate` 구현과 synthetic control 검증, full-universe 실행을 완료했다.

**Full-universe verdict: `NO-GO`.**

primary split에서 skipped slice의 realized net은 음수였고 incremental mean도 소폭 양수였지만, 사전등록 기준을 모두 통과하지 못했다. 특히 DSR이 0에 가까워 다중시도/외부 Sharpe dispersion 보정 후 유의하지 않다.

> 구현 완료 / 단위·타깃 테스트 통과 / DB smoke 통과 / full-data verdict NO-GO

## 정직성 가드

- 이 모듈은 **RULE 전략 위의 entry skip-gate**이며 강화학습/RL 알파가 아니다.
- SL label을 거래 판정으로 쓰지 않는다.
- 판정 target은 `23bp + marketable fill` 비용차감 realized net이다.
- full-data 결과 없이는 실거래 준비 완료, 수익 보장, 알파 확정이라고 말하지 않는다.

## 구현 파일

| 파일 | 내용 |
|---|---|
| `stom_rl/skip_gate.py` | skip-gate 순수 평가 함수, DB extractor, CLI |
| `tests/test_stom_rl_skip_gate.py` | positive/negative/drift-trap/accounting controls |
| `docs/stom_skip_gate_prereg_2026-06-01.md` | 사전등록 |

## 핵심 설계

| 항목 | 내용 |
|---|---|
| baseline | 모든 `ts_imb` trade 진입 |
| policy | predicted net 하위 fraction skip |
| skip grid | `[0.10, 0.20, 0.30, 0.40]` |
| train/test | date-purged walk-forward |
| primary boundary | `0.7` |
| robustness | 5 boundaries `[0.5, 0.6, 0.7, 0.8, 0.9]` |
| GO 조건 | CI>0, DSR≥0.95, skipped net<0, 3/5 boundary positive, negative control NO-GO |

추가 구현 가드:

- `apply_negative_control_gate(...)`가 feature-shuffle negative control을 hard blocker로 적용한다.
- primary가 GO여도 negative control이 `NO-GO`가 아니면 최종 verdict는 `NO-GO`로 강등된다.

## 검증 증거

### 1. 신규 단위 테스트

```powershell
py -3.11 -m pytest tests/test_stom_rl_skip_gate.py -q
```

결과:

```text
9 passed
```

### 2. 타깃 회귀 테스트

```powershell
py -3.11 -m pytest tests/test_stom_rl_skip_gate.py tests/test_stom_rl_sl_predictor.py tests/test_stom_rl_marketable_fill.py tests/test_stom_rl_timing_gate.py -q
```

결과:

```text
28 passed
```

### 3. DB smoke extraction

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.skip_gate --db-path _database/stock_tick_back.db --max-symbols 5 --output-dir .omx/artifacts/skip_gate_smoke --n-bootstrap 100
```

결과:

```text
instances=6 mean_net=0.8229% negative_rate=0.500
too few samples for the pre-registered gate; wrote INCONCLUSIVE summary
wrote -> .omx\artifacts\skip_gate_smoke\summary.json
```

Smoke artifact:

```text
.omx/artifacts/skip_gate_smoke/summary.json
```

### 4. max-symbols 100 smoke after extractor optimization

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.skip_gate --db-path _database/stock_tick_back.db --max-symbols 100 --output-dir .omx/artifacts/skip_gate_smoke100 --n-bootstrap 100
```

결과:

```text
instances=204 mean_net=0.5039% negative_rate=0.632
ridge inc=-0.1166% CI95=[-0.5476,0.2048] DSR=0.022 skipped_net=0.3720% pos_bounds=0 -> no
gbm   inc=-0.3756% CI95=[-0.8082,0.0467] DSR=0.002 skipped_net=0.9321% pos_bounds=0 -> no
negative control verdict: NO-GO
VERDICT: NO-GO
```

### 5. Full-universe execution

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.skip_gate --db-path _database/stock_tick_back.db --output-dir .omx/artifacts/skip_gate --n-bootstrap 1000
```

결과:

```text
instances=5173 mean_net=0.4197% negative_rate=0.645
ridge inc=0.0534% CI95=[-0.0126,0.1203] DSR=0.000 skipped_net=-0.1780% pos_bounds=5 -> no
gbm   inc=0.0727% CI95=[0.0015,0.1525] DSR=0.000 skipped_net=-0.1815% pos_bounds=5 -> no
negative control verdict: NO-GO
VERDICT: NO-GO
wrote -> .omx\artifacts\skip_gate\summary.json
```

Summary artifact:

```text
.omx/artifacts/skip_gate/summary.json
```

해석:

- `ridge`: skipped net은 음수지만 CI가 0을 넘지 못하고 DSR이 실패.
- `gbm`: CI는 간신히 0 초과지만 DSR이 실패.
- negative control은 `NO-GO`로 정상 통과.
- 결론은 사전등록 기준상 **NO-GO**.

### 6. 전체 게이트 스위트

```powershell
py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_gap_up_dashboard_publish.py tests/test_stom_rl_gap_up_risk_sizing.py tests/test_stom_rl_exit_oracle.py tests/test_stom_rl_exit_baselines.py tests/test_stom_rl_liquidity_model.py tests/test_stom_rl_paper_sim.py tests/test_stom_rl_sl_predictor.py tests/test_stom_rl_liquidity_recon.py tests/test_stom_rl_condition_screener.py tests/test_stom_rl_marketable_fill.py tests/test_stom_rl_timing_gate.py tests/test_stom_rl_predictability_probe.py tests/test_stom_rl_full_universe.py tests/test_stom_rl_skip_gate.py -q
```

결과:

```text
233 passed
```

### 7. Architect verification

1차 검토는 negative control hard blocker 누락으로 `REJECT`.

수정:

- `apply_negative_control_gate(...)` 추가
- CLI에서 shuffled negative control을 적용해 최종 verdict를 강등 가능하게 변경
- negative control blocker/pass-through 테스트 2개 추가

재검토 결과:

```text
APPROVE — concrete remaining issues: none found.
```

## 다음 결정

① skip-gate는 full-universe 기준 **NO-GO로 닫는다.**

다음 후보는 문서 `docs/stom_rl_resume_handoff_2026-06-01.md`의 결정 트리에 따라:

1. ④ 상태조건 청산 검정
2. 또는 별도 주제로 “강한 거래대금/거래량 + 눌림 후 재상승” 룰/지도학습 게이트 사전등록

둘 중 하나를 새 계획으로 진행한다.
