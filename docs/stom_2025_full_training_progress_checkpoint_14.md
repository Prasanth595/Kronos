# STOM 2025 전체 학습 진행 체크포인트 14

작성일: 2026-05-13 22:17:50 KST
실행 모드: 읽기 전용 학습 감시 / predictor 고효율 전환 준비 후 상태 고정
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 1. 이번 단계의 목적

이번 단계는 현재 실행 중인 **STOM 1초봉 2025 full Kronos-small 파인튜닝**을 중단하지 않고, 최신 tokenizer 진행률과 checkpoint/predictor 상태를 다시 확인하여 전체 계획/현재 단계/남은 단계를 commit 단위로 고정하기 위한 체크포인트다.

이번 점검에서 중요한 변화는 두 가지다.

1. tokenizer 학습이 **66% 구간**까지 정상 진행되었다.
2. 직전 작업에서 predictor 단계의 GPU 효율 전환 준비가 commit `989b23b`로 완료되었다.

중요 원칙:

1. 실행 중인 학습 프로세스를 중단/재시작하지 않는다.
2. DB, CUDA, PyTorch, finetune output은 수정하지 않는다.
3. checkpoint가 생성되기 전까지 predictor 최적화 전환을 실행하지 않는다.
4. 현재 predictor 성과/정확도/수익률은 아직 판단하지 않는다.
5. 각 milestone을 문서와 commit으로 남겨 방향성을 잃지 않는다.

## 2. OMX 사용 및 fallback

이번 단계에서 OMX read-only 점검을 우선 시도했다.

```text
omx sparkshell --prompt "Read-only로 STOM 2025 full Kronos 학습 상태를 점검..."
```

결과:

```text
omx sparkshell: program not found
```

따라서 실제 검증은 fallback 경로로 수행했다.

```text
fallback: PowerShell + Python urllib + local dashboard APIs + process list + git
```

읽은 API:

- `http://127.0.0.1:5070/api/training/status`
- `http://127.0.0.1:5070/api/training/gpu`
- `http://127.0.0.1:5070/api/training/artifacts`
- `http://127.0.0.1:5070/api/training/history?limit=10`

## 3. 현재 학습 상태

| 항목 | 현재 값 |
|---|---:|
| Run | `stom_1s_grid_pred60_2025_full_small` |
| 전체 상태 | `running` |
| 현재 stage | `tokenizer` |
| stage 상태 | `running` |
| tokenizer step | `3,116,000 / 4,701,721` |
| tokenizer 진행률 | `66.2736%` |
| 전체 both-stage 진행률 | `33.1368%` |
| samples/sec | `61.2087` |
| 경과 시간 | `56.56 h` |
| tokenizer 남은 시간 | `28.79 h` |
| tokenizer 완료 예상(KST) | `2026-05-15 03:04:57 KST` |
| 현재 설정 유지 시 전체 완료 예상(KST) | `2026-05-18 16:25:56 KST` |
| 최신 loss | `-0.0305` |
| learning rate | `0.000054` |
| 최신 progress 업데이트 | `2026-05-13T13:17:17Z` |

진행률 바:

```text
tokenizer stage        [█████████████░░░░░░░] 66.27%
전체 both-stage 학습   [███████░░░░░░░░░░░░░] 33.14%
predictor stage        [░░░░░░░░░░░░░░░░░░░░] 0.00%
예측/성과 검증          [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 4. 직전 체크포인트 대비 증가

직전 문서 `stom_2025_full_training_progress_checkpoint_13.md`의 기준 값과 비교한다.

| 항목 | 체크포인트 13 | 체크포인트 14 | 증가 |
|---|---:|---:|---:|
| tokenizer step | `2,457,000` | `3,116,000` | `+659,000` |
| tokenizer 진행률 | `52.2575%` | `66.2736%` | `+14.0161%p` |
| 전체 진행률 | `26.1287%` | `33.1368%` | `+7.0081%p` |
| samples/sec | `61.6811` | `61.2087` | `-0.4724` |

판단:

- 학습은 계속 진행 중이며 step/history가 증가했다.
- tokenizer 50% milestone 이후 75%를 향해 정상적으로 이동 중이다.
- 속도는 거의 동일한 61 samples/sec 구간이다.
- checkpoint는 아직 없으므로 학습 중단/재시작은 여전히 금지한다.

## 5. GPU / 시스템 상태

| 항목 | 현재 값 |
|---|---:|
| GPU 정보 사용 가능 | `true` |
| 평균 GPU Util | `40.0%` |
| 총 VRAM 사용률 | `19.67%` |
| VRAM 사용량 | `3,221 / 16,376 MiB` |
| 전력 실측 | `null` |
| 전력 제한 | `320.0 W` |

해석:

- GPU는 계속 사용 중이다.
- VRAM 여유는 여전히 크다.
- 현재 tokenizer run은 `batch_size=4`, `num_workers=0`으로 이미 실행 중이므로, 지금 학습에 새 효율 설정을 소급 반영하지 않는다.
- GPU 효율 개선은 tokenizer checkpoint 이후 predictor 전환 시점에 적용한다.

## 6. Artifact / checkpoint / predictor 상태

| 항목 | 현재 값 |
|---|---:|
| artifact level | `waiting` |
| artifact label | `checkpoint 대기` |
| model weight file count | `0` |
| checkpoint file count | `0` |
| tokenizer checkpoint ready | `false` |
| predictor started | `false` |
| predictor checkpoint ready | `false` |

현재 artifact message:

```text
현재 run에서 tokenizer/predictor checkpoint 또는 model weight 파일이 아직 확인되지 않았습니다.
```

판단:

- tokenizer checkpoint가 아직 없으므로 predictor 최적화 전환은 아직 실행 대상이 아니다.
- 자동 predictor가 시작되었는지도 아직 아니다.
- 예측값/실제값 대시보드 성과 판단은 predictor checkpoint 이후로 미룬다.

## 7. 프로세스 생존 근거

확인된 학습 관련 프로세스:

| 프로세스 | PID | 의미 |
|---|---:|---|
| `run_stom_1s_finetune.py` | `3944` | 현재 both-stage 부모 프로세스 |
| `train_tokenizer.py` | `70448` | 현재 tokenizer 학습 프로세스 |
| `run_stom_server_live.py` | `15080` | 학습 상태 확인용 로컬 서버 |
| `web.main:app` | `113648`, `182288` | 웹/API 서버 |
| `webui/run.py` | `147452`, `190596` | 웹 UI 프로세스 |

판단:

- 대화 재시작 후에도 학습 프로세스는 살아 있다.
- 현재 단계에서 PC 재부팅/프로세스 종료/절전 진입은 여전히 피해야 한다.

## 8. predictor 고효율 전환 준비 상태

직전 작업에서 다음 commit으로 predictor 전환 준비를 완료했다.

```text
989b23b predictor 전환 시점에 GPU 효율 설정을 분리하게 하다
```

추가된 옵션:

- `--tokenizer-batch-size`
- `--predictor-batch-size`
- `--tokenizer-num-workers`
- `--predictor-num-workers`

준비 문서:

```text
docs/stom_predictor_max_efficiency_handoff.md
```

주의:

- 현재 이미 실행 중인 부모 프로세스에는 이 새 옵션이 소급 적용되지 않는다.
- tokenizer checkpoint 생성 후 predictor-only 고효율 실행 또는 통제된 전환이 필요하다.
- checkpoint가 생기기 전에는 전환하지 않는다.

## 9. 전체 계획 / 현재 단계 / 남은 단계

| 페이지/단계 | 상태 | 완료율 | 비고 |
|---|---|---:|---|
| 1. STOM DB 분석/학습 데이터 변환 | 완료 | 100% | 2025 pred60 학습 데이터 준비 완료 |
| 2. Kronos 공식 방식 tokenizer/predictor 파이프라인 구축 | 완료 | 100% | runner/monitor/dashboard 준비 |
| 3. 웹 학습 모니터/성과 대시보드/KST/한글/테마 | 완료 | 100% | 웹 UI 개선 완료 |
| 4. tokenizer 2025 full 학습 | 진행 중 | 66.27% | 현재 핵심 진행 단계 |
| 5. tokenizer checkpoint 생성 확인 | 대기 | 0% | 아직 checkpoint 없음 |
| 6. predictor 고효율 전환 준비 | 완료 | 100% | commit `989b23b` |
| 7. predictor 최적화 벤치마크 | 대기 | 0% | checkpoint 이후 실행 |
| 8. predictor full 학습 | 대기 | 0% | batch/workers 최적화 후보 사용 |
| 9. predictor checkpoint 생성 확인 | 대기 | 0% | 모델 사용 가능 조건 |
| 10. 실제값/예측값 대시보드 검증 | 대기 | 0% | 성과 지표/종목별 비교 |
| 11. 종목별 통계/점수화/추천 활용 검증 | 대기 | 0% | 최종 목적 |

전체 진행률 요약:

```text
준비/대시보드 개발       [████████████████████] 100%
tokenizer 학습          [█████████████░░░░░░░] 66.27%
전체 both-stage 학습    [███████░░░░░░░░░░░░░] 33.14%
predictor 최적화 준비   [████████████████████] 100%
predictor 학습          [░░░░░░░░░░░░░░░░░░░░] 0%
예측/성과 검증           [░░░░░░░░░░░░░░░░░░░░] 0%
```

## 10. 다음 단계

다음 단계는 계속 **주기적 학습 확인**이다.

우선순위:

1. tokenizer 75% 도달 확인
2. tokenizer 100% 도달 확인
3. tokenizer checkpoint 생성 확인
4. 자동 predictor 시작 여부 확인
5. checkpoint가 존재하면 predictor 고효율 전환 계획 실행

권장 확인 주기:

- 사람이 확인하는 점검: 1~2시간 간격
- 대시보드 자동 새로고침: 10~30초
- 다음 문서화 타이밍: tokenizer 75% 근처 또는 checkpoint 생성 시점

## 11. 다음 권장 OMX 명령

현재 `omx sparkshell`은 PATH에서 찾을 수 없었다. 따라서 다음 명령은 두 단계로 권장한다.

### 11.1 OMX 환경 확인

```powershell
omx doctor
```

### 11.2 학습 상태 read-only 점검 요청

```text
omx 스킬을 사용해서 STOM 2025 full Kronos 학습 상태를 read-only로 점검하고, /api/training/status, /api/training/gpu, /api/training/artifacts, /api/training/history 기준으로 tokenizer 75% 도달 여부, ETA(KST), checkpoint, predictor 시작 여부를 문서와 commit으로 남겨주세요. checkpoint가 없으면 학습은 건드리지 마세요.
```

## 12. 결론

현재 작업 방향은 유지한다. 지금은 **tokenizer 장기 학습 감시 단계**이며, predictor 고효율 전환 준비는 완료되었다. 다음 의사결정은 tokenizer checkpoint가 실제 생성된 뒤에만 진행한다. 현재 상태에서 학습 프로세스를 중단하거나 재부팅하는 것은 checkpoint가 없기 때문에 권장하지 않는다.
