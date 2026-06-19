# STOM 학습 유지 상태의 웹 대시보드 병렬 개선 계획

작성일: 2026-05-12 KST
실행 모드: `$ralplan` 안전 계획 단계
대상 repo: `D:\Chanil_Park\Project\Programming\Kronos`

## 1. 목표

현재 실행 중인 STOM 2025 pred60 Kronos-small 전체 학습을 중단하지 않고 유지하면서, 사용자가 웹에서 학습 상태와 향후 예측 성과를 더 쉽게 확인할 수 있도록 대시보드/프론트엔드 통합을 단계적으로 개선한다.

핵심 목표:

1. 학습 프로세스는 계속 `running` 상태로 유지한다.
2. `/training`, `/`, `/stom`의 학습 상태 표시를 공통 UI/공통 기준으로 정리한다.
3. checkpoint/predictor 전환 전에는 성과 지표를 표시하지 않고 “아직 학습 중”임을 명확히 보여준다.
4. 진행률 히스토리, ETA, GPU, checkpoint, predictor 상태를 웹에서 읽기 쉽게 표시한다.
5. 모든 변경은 테스트 후 Lore commit으로 남긴다.

## 2. 현재 live 학습 기준선

계획 작성 시점의 live API 관측:

| 항목 | 값 |
|---|---:|
| status | running |
| stage | tokenizer |
| step | 1,168,000 / 4,701,721 |
| tokenizer 진행률 | 24.8420% |
| 전체 both-stage 진행률 | 12.4210% |
| checkpoint/predictor | 아직 전 |

```text
학습 산출물 기준 전체 진행률  [██░░░░░░░░░░░░░░░░░░] 12.42%
tokenizer 진행률             [█████░░░░░░░░░░░░░░░] 24.84%
predictor 진행률             [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 3. RALPLAN-DR 요약

### 원칙

1. **학습 불간섭**: running 학습 프로세스, CUDA/PyTorch 환경, `finetune/outputs` 현재 run은 수정하지 않는다.
2. **읽기 전용 관측 우선**: API/대시보드는 progress/log/artifact를 읽기만 한다.
3. **완료 전 성과 오해 방지**: checkpoint/predictor 전에는 예측 정확도·수익률을 표시하지 않는다.
4. **작은 commit 단위**: 공통 UI, API, 차트, 검증을 분리해 되돌리기 쉽게 만든다.
5. **테스트 우선 보호**: route/template/API 테스트를 갱신하고 live HTTP 확인을 병행한다.

### 결정 동인

1. 사용자가 CMD가 아닌 웹에서 학습 진행률/시간/장비 상태를 보고 싶어 한다.
2. 학습이 장시간 진행 중이므로 환경 변경이나 무거운 병렬 작업은 위험하다.
3. 향후 predictor 완료 후 실제값 vs 예측값 비교 대시보드로 자연스럽게 연결되어야 한다.

### 선택지 비교

| 선택지 | 장점 | 단점 | 판단 |
|---|---|---|---|
| A. 모니터링만 계속 | 안전함 | UI 성숙도 개선이 느림 | 단기 유지에는 가능하지만 사용자 목표에 부족 |
| B. 읽기 전용 웹 개선 병행 | 학습 방해 없이 UX 개선 가능 | 작업 범위 관리 필요 | 채택 |
| C. 학습 코드/환경까지 동시 개선 | 근본 성능 개선 가능성 | running 학습 중단/재현성 손상 위험 | 현재 단계에서는 기각 |

### ADR

- Decision: **B. 읽기 전용 웹 개선 병행**을 채택한다.
- Drivers: 학습 유지, 웹 가시성 향상, 향후 성과 대시보드 연결.
- Alternatives rejected: 학습 코드/환경 동시 변경은 running 학습 안정성을 해칠 수 있어 기각.
- Consequences: 우선 웹/API/문서 중심으로 개선하며, 학습 완료 후 predictor 성과 검증 기능을 확장한다.
- Follow-ups: checkpoint 생성 후 예측 CSV/실제값 비교 화면을 활성화한다.

## 4. 단계별 실행 계획

| 단계 | 목적 | 주요 파일 | 검증 | commit 기준 |
|---|---|---|---|---|
| 0. live 학습 보호 | 현재 학습 상태 기준선 고정 | docs | live API, git clean | 계획 commit |
| 1. 공통 학습 상태 표시 정리 | `/`, `/stom`, `/training` 중복 표시 기준 정리 | `webui/app.py`, templates | pytest route/API | 공통 표시 commit |
| 2. read-only artifacts API | checkpoint/predictor 준비 여부를 별도 API로 노출 | `webui/app.py`, tests | artifact count test | API commit |
| 3. 진행률 히스토리 표시 | progress JSON/log 기반 간단 히스토리 카드/차트 | `training_dashboard.html` | template + live HTTP | UI commit |
| 4. GPU/ETA/속도 카드 개선 | 장비/속도/예상시간을 더 명확히 표시 | training page + common widget | live HTTP + escaping 확인 | UI commit |
| 5. `/stom` 성과 준비 상태 연결 | predictor 전에는 “성과 대기” 명확화 | `stom_dashboard.html` | route test | 통합 commit |
| 6. 최종 code-review 문서 | 변경 범위/위험/검증 기록 | docs | pytest + git diff check | review commit |

## 5. 명시적 금지 사항

다음은 현재 학습이 완료되기 전까지 하지 않는다.

```text
CUDA/PyTorch 재설치
requirements 대규모 변경
현재 run 폴더 삭제/정리/이동
finetune/train_tokenizer.py 수정
finetune/run_stom_1s_finetune.py 수정
STOM DB/sample data 수정
python 프로세스 일괄 종료
무거운 전체 백테스트 병렬 실행
```

## 6. 테스트 계획

필수 테스트:

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
```

필수 live 확인:

```text
http://127.0.0.1:5070/training?refresh_interval=10
http://127.0.0.1:5070/?refresh_interval=10
http://127.0.0.1:5070/stom?refresh_interval=10
```

각 단계 공통 검증:

```powershell
git diff --check
git status --short --branch
```

## 7. 사용 가능한 실행 역할/OMX 경로

- `$ralplan`: 계획/범위/위험 정리. 지금 단계.
- `$ralph`: 단일 소유자가 공통 UI/API를 순차 구현하고 검증.
- `$code-review`: 구현 후 변경사항 검토.
- `$ultraqa`: route/API/live dashboard 반복 검증이 필요할 때.

권장 실행은 `$ralph`다. 이유는 현재 변경이 학습 프로세스와 분리된 웹/UI/API 개선이며, 파일 충돌을 줄이는 것이 안전하기 때문이다.

## 8. 현재/남은 단계 progress

```text
안전 계획 수립                  [████████████████████] 100%
학습 모니터링 체계              [████████████████████] 100%
웹 기본 통합                    [███████████████████░] 95%
프론트엔드 고도화               [████████░░░░░░░░░░░░] 40%
read-only artifacts API          [░░░░░░░░░░░░░░░░░░░░] 0%
진행률 히스토리 시각화           [░░░░░░░░░░░░░░░░░░░░] 0%
학습 산출물 전체 진행률          [██░░░░░░░░░░░░░░░░░░] 12.42%
```

## 9. 다음 권장 OMX 명령

```text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획에 따라 1단계만 구현하세요. 목표는 /training, /, /stom의 학습 상태 UI를 공통 기준으로 정리하고 checkpoint/predictor 전환 전 성과 오해를 막는 표시를 추가하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고, live HTTP 확인 후 Lore commit으로 남기세요.
```

---

## 10. 2026-05-12 실행 갱신: 3단계 완료

3단계 `진행률 히스토리 표시`를 완료했습니다.

- `/api/training/history`가 최근 stdout step을 읽기 전용으로 파싱합니다.
- `/training` 화면에 최근 step, stage %, overall %, LR, loss 테이블을 표시합니다.
- 아직 시작되지 않은 predictor 단계를 명시 선택하면 tokenizer 로그를 잘못 보여주지 않고 `no stdout log found for this run` 상태를 반환합니다.
- 현재 실행 중인 학습은 중단하지 않았습니다.

검증:

```text
pytest tests\test_training_monitor.py tests\test_training_progress.py -q: 12 passed
compileall webui: 통과
live /api/training/history: point_count 5, latest_point.step 1,320,000
live /training?refresh_interval=10: historyRows/historySummary 확인
```

다음 단계는 4단계 `GPU/ETA/속도 카드 개선`입니다.

---

## 11. 2026-05-12 실행 갱신: 4단계 완료

4단계 `GPU/ETA/속도 카드 개선`을 완료했습니다.

- `/training`에 `학습 속도 / ETA` 카드가 추가되었습니다.
- `samples/sec`, 경과 시간, 남은 시간, 예상 완료 시각, 최근 loss를 한눈에 볼 수 있습니다.
- GPU summary가 평균 Util, 총 VRAM 사용률, 총 전력 제한, power draw 실측 가능 여부를 반환합니다.
- 현재 워크스테이션처럼 power draw가 실측되지 않는 경우 `실측 불가`로 표시해 전력 수치를 과장하지 않습니다.
- 현재 실행 중인 학습은 중단하지 않았습니다.

검증:

```text
pytest tests\test_training_monitor.py tests\test_training_progress.py -q: 13 passed
compileall webui: 통과
live /api/training/gpu: available true, avg util 39.0%, VRAM 19.61%, power limit 320W
live /training?refresh_interval=10: runtimeSummaryCard/gpuSummaryMetrics 확인
```

다음 단계는 5단계 `/stom 성과 준비 상태 연결`입니다.


---

## 12. 2026-05-12 ?? ??: 5?? ??

5?? `/stom ?? ?? ?? ??`? ??????.

- `/stom` ??? `?? ?? Gate`, `Predictor`, `Checkpoint`, `?? / ETA` ??? ??????.
- predictor/checkpoint ?? ??? `LOCKED: predictor/checkpoint ?? ? ?? ?? ??`? ??? ?????.
- `/api/training/status` readiness? `/api/training/artifacts` checkpoint ??? `/stom` ?? ??? ??????.
- ?? ?? ?? ??? ???? ?????.

??:

```text
pytest tests\test_training_monitor.py tests\test_training_progress.py -q: 13 passed
compileall webui: ??
live /stom?refresh_interval=10: stomPerformanceGate/stomPredictorGate/stomCheckpointGate/stomRuntimeGate ??
live /api/training/status: tokenizer running, overall 14.7074%
live /api/training/artifacts: checkpoint 0?, predictor_started false
```

?? ??? 6?? `?? code-review ??`???.


---

## 13. 2026-05-12 ?? ??: 6?? ?? code-review ??

6?? `?? code-review ??`? ??????.

?? ??:

```text
Recommendation: APPROVE
Architectural Status: CLEAR
CRITICAL/HIGH/MEDIUM: 0
LOW follow-up: 3
```

?? ??:

- 1?? ?? readiness UI/API
- 2?? read-only artifacts API
- 3?? ??? ????
- 4?? GPU/ETA/?? ??
- 5?? /stom ?? ?? ?? gate

??:

```text
pytest tests\test_training_monitor.py tests\test_training_progress.py -q: 13 passed
compileall webui: ??
git diff --check aed6967..HEAD: ??
live /training, /stom, / marker ??
live /api/training/status/history/artifacts/gpu ??
```

?? ?? ??:

1. `/stom` ?? artifact table innerHTML sanitize pass
2. ?? ???? JS ?? ?? ??
3. ?? ?? refresh interval ?? ? GPU status cache TTL ??

?? ???? ??? 1~6??? ?????.


---

## 14. 2026-05-12 ?? ??: ?? ?? ???? ?????

?? code-review ?? ?? ??? ?? STOM full training ??? read-only? ???????.

??:

```text
?? ??: tokenizer running
step: 1,442,000 / 4,701,721
tokenizer ???: 30.6696%
?? both-stage ???: 15.3348%
predictor_started: false
checkpoint/model weight: 0?
?? ?? ??: ?? ??
```

??? ??? ?? ?? ??? ??? **???? ?? ??**???.

?? ?? ??:

1. predictor stage ?? ??
2. predictor checkpoint/model weight ?? ??
3. /training ? /stom gate? predictor training/ready ??? ????? ??
4. ? ?? ??? vs ??? ?? ???? ?? ??
