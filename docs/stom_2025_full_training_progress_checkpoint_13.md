# STOM 2025 전체 학습 진행 체크포인트 13

작성일: 2026-05-13 09:59:16 KST
실행 모드: 읽기 전용 학습 감시 / 주기적 진행 확인
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 1. 이번 단계의 목적

이번 단계는 2026-05-13 오전 기준으로 장기 실행 중인 **STOM 1초봉 2025 full Kronos-small 파인튜닝**의 진행 상태를 다시 확인하고, 전체 계획/현재 단계/남은 단계를 commit 단위로 고정하기 위한 체크포인트다.

이번 점검에서 가장 중요한 변화는 **tokenizer 학습이 50% milestone을 통과했다는 점**이다.

중요 원칙:

1. 실행 중인 학습 프로세스를 중단/재시작하지 않는다.
2. DB, CUDA, PyTorch, 학습 코드, finetune 산출물은 수정하지 않는다.
3. `/api/training/status`, `/api/training/gpu`, `/api/training/artifacts`, `/api/training/history`만 읽는다.
4. checkpoint/predictor가 준비되기 전까지 예측 성과를 확정하지 않는다.
5. milestone마다 문서와 commit을 남겨 방향성을 잃지 않는다.

## 2. OMX 사용 및 fallback

OMX 지침에 따라 먼저 `omx explore`를 사용해 read-only 맥락 확인을 시도했다. 현재 Windows 환경에서는 POSIX sh/bash wrapper 기반 allowlist runtime이 준비되지 않아 실패했다.

```text
omx explore: Windows POSIX harness 미준비로 실패
fallback: PowerShell + Python urllib + git
```

따라서 이번 점검은 fallback 경로로 수행했지만, 수행 범위는 여전히 읽기 전용이다.

## 3. 현재 학습 상태

| 항목 | 현재 값 |
|---|---:|
| Run | `stom_1s_grid_pred60_2025_full_small` |
| 전체 상태 | `running` |
| 현재 stage | `tokenizer` |
| stage 상태 | `running` |
| tokenizer step | `2,457,000 / 4,701,721` |
| tokenizer 진행률 | `52.2575%` |
| 전체 both-stage 진행률 | `26.1287%` |
| samples/sec | `61.6811` |
| ETA seconds | `145,569.44` |
| 완료 예상(KST) | `2026-05-15 02:25:25 KST` |
| 최신 loss | `-0.0255` |
| learning rate | `0.000098` |
| 최신 progress 업데이트 | `2026-05-13T00:59:02Z` |

진행률 바:

```text
tokenizer stage        [██████████░░░░░░░░░░] 52.26%
전체 both-stage 학습   [█████░░░░░░░░░░░░░░░] 26.13%
predictor stage        [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 4. 직전 체크포인트 대비 증가

직전 문서 `stom_2025_full_training_progress_checkpoint_12.md`의 기준 값은 다음과 같았다.

| 항목 | 체크포인트 12 | 체크포인트 13 | 증가 |
|---|---:|---:|---:|
| tokenizer step | `1,847,000` | `2,457,000` | `+610,000` |
| tokenizer 진행률 | `39.2835%` | `52.2575%` | `+12.9740%p` |
| 전체 진행률 | `19.6417%` | `26.1287%` | `+6.4870%p` |
| samples/sec | `63.6832` | `61.6811` | `-2.0021` |

판단:

- 학습은 밤 사이 계속 진행되었다.
- tokenizer 50% milestone을 통과했다.
- 속도는 소폭 낮아졌지만 여전히 60 samples/sec 수준으로 진행 중이다.
- checkpoint는 아직 없으므로 결과 성과 판단은 여전히 보류한다.

## 5. GPU / 시스템 상태

| 항목 | 현재 값 |
|---|---:|
| GPU 정보 사용 가능 | `true` |
| 평균 GPU Util | `36.0%` |
| 총 VRAM 사용률 | `21.66%` |
| VRAM 사용량 | `3,547 / 16,376 MiB` |
| 전력 실측 | `nvidia-smi power draw unavailable` |
| 전력 제한 | `320.0 W` |
| GPU 상태 생성 시각 | `2026-05-13T00:59:15Z` |

해석:

- GPU는 계속 사용 중이다.
- VRAM 사용량은 약 3.5GB로 안정적이다.
- GPU util은 36% 수준으로, 기존 관찰처럼 GPU 100% 고정형 학습은 아니다.
- 학습이 멈춘 상태는 아니며 step/history가 함께 증가하고 있다.

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
| latest artifact updated at | `null` |

현재 artifact message:

```text
현재 run에서 tokenizer/predictor checkpoint 또는 model weight 파일이 아직 확인되지 않았습니다.
```

판단:

- tokenizer checkpoint는 아직 생성되지 않았다.
- predictor는 아직 시작되지 않았다.
- 예측/실제값 비교 또는 정확도 평가는 아직 수행 대상이 아니다.

## 7. History 근거

최신 history point:

```text
[Rank 0, Epoch 1/1, Step 2457000/4701721] LR 0.000098, Loss: -0.0255
```

history point count: `8`

판단:

- progress log 파싱이 정상이다.
- step과 loss가 갱신되고 있으므로 학습은 살아 있다.
- 웹 대시보드가 읽는 history 소스도 정상이다.

## 8. 전체 계획 / 현재 단계 / 남은 단계

| 단계 | 상태 | 완료율 |
|---|---|---:|
| STOM DB -> Qlib/학습 데이터 준비 | 완료 | 100% |
| 2025 full 학습 실행 준비 | 완료 | 100% |
| 웹 학습 모니터/성과 대시보드 준비 | 완료 | 100% |
| 루트/학습/STOM 대시보드 KST/한글/테마 개선 | 완료 | 100% |
| tokenizer 학습 | 진행 중 | 52.26% |
| tokenizer 50% milestone | 완료 | 100% |
| tokenizer 75% milestone | 대기 | 0% |
| tokenizer checkpoint 생성 확인 | 대기 | 0% |
| predictor 학습 시작 확인 | 대기 | 0% |
| predictor checkpoint 생성 확인 | 대기 | 0% |
| predictor 완료 후 예측/실제값 비교 | 대기 | 0% |
| 성과 지표/종목별 통계/추천 점수 검증 | 대기 | 0% |

현재 전체 프로젝트 관점 진행률:

```text
준비/대시보드 개발       [████████████████████] 100%
tokenizer 학습          [██████████░░░░░░░░░░] 52.26%
학습 산출물 생성         [█████░░░░░░░░░░░░░░░] 26.13%
예측 성과 검증           [░░░░░░░░░░░░░░░░░░░░] 0%
```

## 9. 다음 단계

다음 단계는 계속 **주기적 학습 확인**이다.

다음 우선 milestone:

1. tokenizer 75% 도달 여부 확인
2. tokenizer 100% 도달 여부 확인
3. tokenizer checkpoint 생성 여부 확인
4. predictor 단계 시작 여부 확인

권장 확인 주기:

- 사람이 확인하는 점검: 1~2시간 간격
- 대시보드 자동 새로고침: 10~30초
- 다음 문서화 타이밍: tokenizer 75% 근처 또는 checkpoint 생성 시점

## 10. 다음 권장 OMX 명령

```text
omx ralph --prompt "STOM 2025 full Kronos-small 학습을 중단하지 말고 읽기 전용으로 /api/training/status, /api/training/gpu, /api/training/artifacts, /api/training/history를 확인하여 tokenizer 75% 도달 여부, ETA(KST), loss, GPU, checkpoint, predictor 전환 여부를 문서와 commit으로 남겨주세요."
```

## 11. 결론

현재는 **주기적 학습 확인 단계가 계속 맞다.**

이번 체크포인트 기준으로 학습은 `running`이며 tokenizer 단계가 `52.2575%`, 전체 both-stage가 `26.1287%`까지 진행되었다. tokenizer 50% milestone은 통과했지만 checkpoint와 predictor는 아직 준비되지 않았다. 따라서 다음 의사결정은 tokenizer 75% 또는 checkpoint 생성/ predictor 전환이 관찰될 때 진행한다.
