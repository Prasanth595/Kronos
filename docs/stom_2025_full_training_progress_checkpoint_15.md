# STOM 2025 전체 학습 진행 체크포인트 15

작성일: 2026-05-14 06:39:31 KST
실행 모드: 읽기 전용 학습 감시 / tokenizer 75% milestone 통과 확인
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 1. 이번 단계의 목적

이번 단계는 장기 실행 중인 **STOM 1초봉 2025 full Kronos-small 파인튜닝**이 밤 사이 계속 진행되었는지 확인하고, tokenizer 75% milestone 통과 여부와 checkpoint/predictor 전환 준비 상태를 문서와 commit으로 고정하기 위한 체크포인트다.

이번 점검의 핵심 결론:

1. tokenizer 학습이 **78.7584%**까지 진행되어 **75% milestone을 통과**했다.
2. 전체 both-stage 진행률은 **39.3792%**다.
3. tokenizer checkpoint는 아직 없고 predictor도 아직 시작되지 않았다.
4. 따라서 predictor 고효율 전환은 아직 실행하지 않고, tokenizer 100% 및 checkpoint 생성을 계속 감시한다.

중요 원칙:

1. 실행 중인 학습 프로세스를 중단/재시작하지 않는다.
2. DB, CUDA, PyTorch, finetune output은 수정하지 않는다.
3. tokenizer checkpoint가 생성되기 전까지 predictor 최적화 전환을 실행하지 않는다.
4. predictor가 시작되거나 checkpoint가 생성되면 별도 전환 판단을 문서화한다.
5. 현재는 예측 성과/정확도/수익률을 판단하지 않는다.

## 2. OMX 사용 및 fallback

OMX 지침에 따라 read-only 점검 경로를 우선 시도했다.

```text
omx explore --prompt "Read-only: check current STOM 2025 full Kronos training status..."
```

결과:

```text
Error: [explore] the built-in explore harness is not ready on Windows because its allowlist runtime relies on POSIX sh/bash wrappers.
```

추가로 `omx sparkshell`도 시도했다.

```text
omx sparkshell --prompt "Read-only: summarize STOM training status..."
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
- `http://127.0.0.1:5070/api/training/history?limit=12`

## 3. 현재 학습 상태

| 항목 | 현재 값 |
|---|---:|
| Run | `stom_1s_grid_pred60_2025_full_small` |
| 전체 상태 | `running` |
| 현재 stage | `tokenizer` |
| stage 상태 | `running` |
| tokenizer step | `3,703,000 / 4,701,721` |
| tokenizer 진행률 | `78.7584%` |
| 전체 both-stage 진행률 | `39.3792%` |
| samples/sec | `63.3692` |
| 경과 시간 | `64.93 h` |
| tokenizer 남은 시간 | `17.51 h` |
| tokenizer 완료 예상(KST) | `2026-05-15 00:10:12 KST` |
| 현재 설정 유지 시 전체 완료 예상(KST) | `2026-05-18 10:36:35 KST` |
| 최신 loss | `-0.0297` |
| learning rate | `0.000023` |
| 최신 progress 업데이트 | `2026-05-13T21:39:08Z` |

진행률 바:

```text
tokenizer stage        [████████████████░░░░] 78.76%
전체 both-stage 학습   [████████░░░░░░░░░░░░] 39.38%
predictor stage        [░░░░░░░░░░░░░░░░░░░░] 0.00%
예측/성과 검증          [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 4. 직전 체크포인트 대비 증가

직전 문서 `stom_2025_full_training_progress_checkpoint_14.md` 기준 값과 비교한다.

| 항목 | 체크포인트 14 | 체크포인트 15 | 증가 |
|---|---:|---:|---:|
| tokenizer step | `3,116,000` | `3,703,000` | `+587,000` |
| tokenizer 진행률 | `66.2736%` | `78.7584%` | `+12.4848%p` |
| 전체 진행률 | `33.1368%` | `39.3792%` | `+6.2424%p` |
| samples/sec | `61.2087` | `63.3692` | `+2.1605` |

판단:

- 학습은 정상적으로 계속 진행 중이다.
- tokenizer 75% milestone은 완료로 기록한다.
- samples/sec는 이전보다 소폭 개선되어 63 samples/sec 구간이다.
- tokenizer 남은 시간이 약 17.5시간으로 감소했다.
- checkpoint는 아직 없으므로 predictor 최적화 전환은 아직 실행하지 않는다.

## 5. GPU / 시스템 상태

| 항목 | 현재 값 |
|---|---:|
| GPU 정보 사용 가능 | `true` |
| 평균 GPU Util | `34.0%` |
| 총 VRAM 사용률 | `18.94%` |
| VRAM 사용량 | `3,101 / 16,376 MiB` |
| 전력 실측 | `null` |
| 전력 제한 | `320.0 W` |

해석:

- GPU는 계속 사용 중이다.
- VRAM 여유는 크지만 현재 tokenizer 프로세스는 이미 `batch_size=4`, `num_workers=0`으로 시작되어 있어 실행 중 변경하지 않는다.
- GPU 효율 개선은 tokenizer checkpoint 이후 predictor 단계에서 적용한다.

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

stage별 artifact 판단:

| stage | folder | checkpoint dir | checkpoint ready | progress |
|---|---|---|---:|---:|
| tokenizer | 있음 | `finetune_tokenizer/checkpoints` 있음 | `false` | 있음 |
| predictor | 없음 | 없음 | `false` | 없음 |

현재 artifact message:

```text
현재 run에서 tokenizer/predictor checkpoint 또는 model weight 파일이 아직 확인되지 않았습니다.
```

판단:

- tokenizer checkpoint가 아직 없으므로 현재까지 진행분은 프로세스 종료/재부팅에 취약하다.
- predictor는 아직 시작되지 않았다.
- predictor 고효율 전환 준비는 완료되어 있으나 실행 조건은 아직 충족되지 않았다.

## 7. 프로세스 생존 근거

확인된 학습 관련 프로세스:

| 프로세스 | PID | 의미 |
|---|---:|---|
| `run_stom_1s_finetune.py` | `3944` | 현재 both-stage 부모 프로세스 |
| `train_tokenizer.py` | `70448` | 현재 tokenizer 학습 프로세스 |
| `run_stom_server_live.py` | `15080` | 학습 상태 확인용 로컬 서버 |
| `web.main:app` | `113648` | 웹/API 서버 |
| `webui/run.py` | `147452`, `190596` | 웹 UI 프로세스 |

판단:

- 학습은 살아 있다.
- 대화 재시작과 무관하게 별도 Python 학습 프로세스가 계속 실행 중이다.
- checkpoint가 없으므로 PC 재부팅/학습 프로세스 종료/절전 진입은 계속 피한다.

## 8. predictor 고효율 전환 준비 상태

이미 다음 commit으로 predictor 전환 준비를 완료했다.

```text
989b23b predictor 전환 시점에 GPU 효율 설정을 분리하게 하다
```

준비된 옵션:

- `--tokenizer-batch-size`
- `--predictor-batch-size`
- `--tokenizer-num-workers`
- `--predictor-num-workers`

준비 문서:

```text
docs/stom_predictor_max_efficiency_handoff.md
```

현재 판단:

- tokenizer checkpoint가 아직 없으므로 실제 predictor 최적화 실행은 보류한다.
- tokenizer 100% 이후 validation/checkpoint 저장이 끝나면 predictor 자동 시작 여부를 즉시 확인한다.
- checkpoint가 존재할 때만 predictor-only 고효율 벤치마크 또는 전환을 고려한다.

## 9. 전체 계획 / 현재 단계 / 남은 단계

| 페이지/단계 | 상태 | 완료율 | 비고 |
|---|---|---:|---|
| 1. STOM DB 분석/학습 데이터 변환 | 완료 | 100% | 2025 pred60 학습 데이터 준비 완료 |
| 2. Kronos 공식 방식 tokenizer/predictor 파이프라인 구축 | 완료 | 100% | runner/monitor/dashboard 준비 |
| 3. 웹 학습 모니터/성과 대시보드/KST/한글/테마 | 완료 | 100% | 웹 UI 개선 완료 |
| 4. tokenizer 50% milestone | 완료 | 100% | checkpoint 13 |
| 5. tokenizer 75% milestone | 완료 | 100% | 이번 checkpoint 15 |
| 6. tokenizer 2025 full 학습 | 진행 중 | 78.76% | 현재 핵심 진행 단계 |
| 7. tokenizer checkpoint 생성 확인 | 대기 | 0% | 아직 checkpoint 없음 |
| 8. predictor 고효율 전환 준비 | 완료 | 100% | commit `989b23b` |
| 9. predictor 최적화 벤치마크 | 대기 | 0% | checkpoint 이후 실행 |
| 10. predictor full 학습 | 대기 | 0% | batch/workers 최적화 후보 사용 |
| 11. predictor checkpoint 생성 확인 | 대기 | 0% | 모델 사용 가능 조건 |
| 12. 실제값/예측값 대시보드 검증 | 대기 | 0% | 성과 지표/종목별 비교 |
| 13. 종목별 통계/점수화/추천 활용 검증 | 대기 | 0% | 최종 목적 |

전체 진행률 요약:

```text
준비/대시보드 개발       [████████████████████] 100%
tokenizer 학습          [████████████████░░░░] 78.76%
전체 both-stage 학습    [████████░░░░░░░░░░░░] 39.38%
predictor 최적화 준비   [████████████████████] 100%
predictor 학습          [░░░░░░░░░░░░░░░░░░░░] 0%
예측/성과 검증           [░░░░░░░░░░░░░░░░░░░░] 0%
```

## 10. 다음 단계

다음 단계는 **tokenizer 100% 및 checkpoint 생성 감시**다.

우선순위:

1. tokenizer 90% 근처 진행 확인
2. tokenizer 100% 도달 확인
3. validation 진행 여부 확인
4. tokenizer checkpoint 생성 확인
5. 자동 predictor 시작 여부 확인
6. checkpoint 존재 시 predictor 고효율 전환/벤치마크 판단

권장 확인 주기:

- 사람이 확인하는 점검: 1~2시간 간격
- 90% 이후 확인: 30~60분 간격 권장
- 다음 문서화 타이밍: tokenizer 90% 근처 또는 checkpoint 생성 시점

## 11. 다음 권장 OMX 명령

현재 `omx explore`와 `omx sparkshell`은 이 Windows 환경에서 바로 사용할 수 없었다. 따라서 먼저 OMX 상태 확인을 권장한다.

```powershell
omx doctor
```

다음 Codex 요청 문구:

```text
$ralph STOM 2025 full Kronos 학습 상태를 read-only로 점검하고, tokenizer 90% 또는 100% 도달 여부, ETA(KST), checkpoint 생성 여부, predictor 시작 여부를 문서와 commit으로 남겨주세요. checkpoint가 없으면 학습은 절대 건드리지 마세요.
```

## 12. 결론

현재 작업 방향은 올바르다. tokenizer는 75% milestone을 통과했고, predictor 최적화 전환 준비도 이미 끝나 있다. 그러나 checkpoint가 아직 없으므로 지금은 여전히 **학습 감시 단계**다. 다음 의사결정은 tokenizer 100% 이후 checkpoint 생성 또는 predictor 자동 시작이 관찰될 때 진행한다.
