# STOM 2025 전체 학습 진행 체크포인트 12

작성일: 2026-05-12 21:57:41 KST
실행 모드: 읽기 전용 학습 감시 / 주기적 진행 확인
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 1. 이번 단계의 목적

이번 단계의 목적은 개발 방향을 다시 원래 목표인 **STOM 1초봉 2025 full Kronos-small 파인튜닝 진행 감시**로 되돌리는 것이다.

중요 원칙은 다음과 같다.

1. 실행 중인 장기 학습 프로세스를 중단하지 않는다.
2. DB, CUDA, PyTorch, 학습 코드, finetune 산출물은 수정하지 않는다.
3. `/api/training/status`, `/api/training/gpu`, `/api/training/artifacts`, `/api/training/history`만 읽는다.
4. checkpoint/predictor가 준비되기 전까지 예측 성과를 확정하지 않는다.
5. 각 중간 점검 결과를 문서와 commit으로 남겨 계획/현재 단계/남은 단계를 추적한다.

## 2. 현재 학습 상태

| 항목 | 현재 값 |
|---|---:|
| Run | `stom_1s_grid_pred60_2025_full_small` |
| 전체 상태 | `running` |
| 현재 stage | `tokenizer` |
| stage 상태 | `running` |
| tokenizer step | `1,847,000 / 4,701,721` |
| tokenizer 진행률 | `39.2835%` |
| 전체 both-stage 진행률 | `19.6417%` |
| samples/sec | `63.6832` |
| ETA seconds | `179,307.55` |
| 완료 예상(KST) | `2026-05-14 23:46:09 KST` |
| 최신 loss | `-0.0293` |
| 최신 progress 업데이트 | `2026-05-12T12:56:58Z` |

진행률 바:

```text
tokenizer stage        [████████░░░░░░░░░░░░] 39.28%
전체 both-stage 학습   [████░░░░░░░░░░░░░░░░] 19.64%
predictor stage        [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 3. 직전 체크포인트 대비 증가

직전 문서 `stom_2025_full_training_progress_checkpoint_11.md`의 기준 값은 다음과 같았다.

| 항목 | 체크포인트 11 | 체크포인트 12 | 증가 |
|---|---:|---:|---:|
| tokenizer step | `1,136,000` | `1,847,000` | `+711,000` |
| tokenizer 진행률 | `24.1614%` | `39.2835%` | `+15.1221%p` |
| 전체 진행률 | `12.0807%` | `19.6417%` | `+7.5610%p` |

판단:

- 학습은 멈추지 않고 유의미하게 전진했다.
- step, loss, history 모두 새 값으로 갱신되고 있다.
- 아직 tokenizer 단계이므로 predictor 기반 예측 성과는 판단하지 않는다.

## 4. GPU / 시스템 상태

| 항목 | 현재 값 |
|---|---:|
| GPU 정보 사용 가능 | `true` |
| 평균 GPU Util | `37.0%` |
| 총 VRAM 사용률 | `21.97%` |
| 전력 실측 | `nvidia-smi power draw unavailable` |

해석:

- GPU와 VRAM은 사용 중이다.
- 전력 값은 이번 응답에서 null이었지만 GPU 상태 API 자체는 정상 응답했다.
- 현재 병목은 고정적으로 GPU 100%를 채우는 형태라기보다 데이터/학습 루프 혼합 병목으로 보이며, 기존 관찰과 크게 다르지 않다.

## 5. Artifact / checkpoint / predictor 상태

| 항목 | 현재 값 |
|---|---:|
| artifact level | `waiting` |
| model weight file count | `0` |
| checkpoint file count | `0` |
| tokenizer checkpoint ready | `false` |
| predictor started | `false` |
| predictor checkpoint ready | `false` |

판단:

- tokenizer checkpoint는 아직 준비되지 않았다.
- predictor 단계는 아직 시작되지 않았다.
- 따라서 현재 단계에서 실제 예측 성과/정확도/수익률을 판단하면 안 된다.

## 6. History 근거

최신 history point:

```text
[Rank 0, Epoch 1/1, Step 1847000/4701721] LR 0.000139, Loss: -0.0293
```

history point count: `5`

판단:

- 진행 로그 tail과 history 파싱이 정상적으로 갱신되고 있다.
- 웹 대시보드가 표시할 progress 소스가 살아 있다.

## 7. 전체 계획 / 현재 단계 / 남은 단계

| 단계 | 상태 | 완료율 |
|---|---|---:|
| STOM DB -> Qlib/학습 데이터 준비 | 완료 | 100% |
| 2025 full 학습 실행 준비 | 완료 | 100% |
| 웹 학습 모니터/성과 대시보드 준비 | 완료 | 100% |
| 루트/학습/STOM 대시보드 KST/한글/테마 개선 | 완료 | 100% |
| tokenizer 학습 | 진행 중 | 39.28% |
| tokenizer checkpoint 생성 확인 | 대기 | 0% |
| predictor 학습 시작 확인 | 대기 | 0% |
| predictor checkpoint 생성 확인 | 대기 | 0% |
| predictor 완료 후 예측/실제값 비교 | 대기 | 0% |
| 성과 지표/종목별 통계/추천 점수 검증 | 대기 | 0% |

현재 전체 프로젝트 관점 진행률:

```text
준비/대시보드 개발       [████████████████████] 100%
학습 산출물 생성         [████░░░░░░░░░░░░░░░░] 19.64%
예측 성과 검증           [░░░░░░░░░░░░░░░░░░░░] 0%
```

## 8. 다음 단계

다음 단계는 계속 **주기적 학습 확인**이다.

권장 확인 주기:

- 사람이 보는 중간 점검: 30분~1시간 간격
- 웹 대시보드 자동 새로고침: 10~30초
- 중요 milestone:
  1. tokenizer 50%
  2. tokenizer 75%
  3. tokenizer 100%
  4. tokenizer checkpoint 생성
  5. predictor 시작
  6. predictor checkpoint 생성
  7. predictor 완료

## 9. 다음 권장 OMX 명령

```text
omx ralph --prompt "STOM 2025 full Kronos-small 학습을 중단하지 말고 읽기 전용으로 /api/training/status, /api/training/gpu, /api/training/artifacts, /api/training/history를 확인하여 tokenizer 진행률, ETA(KST), loss, GPU, checkpoint, predictor 전환 여부를 문서와 commit으로 남겨주세요."
```

## 10. 결론

현재는 **주기적 학습 확인 단계가 맞다.**

이번 체크포인트 기준으로 학습은 `running`이며 tokenizer 단계가 `39.2835%`, 전체 both-stage가 `19.6417%`까지 진행되었다. predictor는 아직 시작되지 않았고 checkpoint도 아직 없으므로, 다음 의사결정은 tokenizer checkpoint 생성 또는 predictor 전환이 관찰될 때 진행한다.
