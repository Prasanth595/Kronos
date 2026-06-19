# STOM 2025 전체 학습 진행 체크포인트 08

작성일: 2026-05-12 KST
실행 모드: `$ralph` 다음 단계 점검
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 1. 이번 단계의 목적

이번 단계는 새 학습을 다시 시작하는 것이 아니라, 이미 실행 중인 STOM 1초봉/tick 기반 2025년 전체 학습이 절전 이후에도 실제로 계속 진행 중인지 검증하고 그 상태를 문서와 commit으로 고정하는 단계다.

핵심 목표:

1. tokenizer 단계가 살아 있는지 확인
2. step이 실제로 증가하는지 확인
3. GPU/프로세스가 계속 사용 중인지 확인
4. checkpoint 또는 predictor 전환이 발생했는지 확인
5. `/training`, `/`, `/stom` 웹 대시보드가 학습 상태 자동 갱신 UI를 제공하는지 확인

## 2. OMX 도구 사용 결과

`omx explore`는 Windows 환경에서 POSIX sh/bash wrapper 의존성 때문에 실패했다. `omx sparkshell`은 현재 설치된 OMX CLI에서 프로그램을 찾지 못했다. 따라서 이번 검증은 AGENTS.md 지침에 따라 PowerShell/Python 기반의 읽기 전용 확인으로 대체했다.

```text
omx explore: Windows allowlist runtime POSIX harness 미준비로 실패
omx sparkshell: program not found
fallback: PowerShell + Python urllib + nvidia-smi
```

## 3. 실시간 학습 상태

| 항목 | 값 |
|---|---:|
| 전체 status | running |
| 현재 stage | tokenizer |
| tokenizer step | 920000 / 4701721 |
| tokenizer stage 진행률 | 19.5673% |
| 전체 2-stage 진행률 | 9.7837% |
| 최신 loss 로그 | `[Rank 0, Epoch 1/1, Step 920000/4701721] LR 0.000186, Loss: -0.0307` |

진행률:

```text
tokenizer 단계       [████░░░░░░░░░░░░░░░░] 19.57%
전체 both-stage 학습  [██░░░░░░░░░░░░░░░░░░] 9.78%
predictor 단계       [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

중요한 해석:

- 전체 학습은 `tokenizer -> predictor` 2단계로 계산된다.
- 현재 `overall_percent`가 약 9.78%인 이유는 tokenizer 단계가 약 19.57% 진행됐고 predictor 단계가 아직 0%이기 때문이다.
- 아직 predictor 전환 전이므로 현재 대시보드의 예측 성과는 “학습 완료 모델 성과”가 아니다.

## 4. step 증가 검증

70초 간격 검증에서 아래 변화가 확인됐다.

```text
before: Step 918000 / 4701721, overall 9.7624%
after : Step 919000 / 4701721, overall 9.7730%
CPU delta for tokenizer PID 70448 over 70s: +70.30 seconds
```

추가 상태 문서 작성 시점에는 API가 `Step 920000 / 4701721`까지 갱신됐다. 따라서 현재 학습은 멈춘 상태가 아니라 진행 중이다. 단, 로그는 `--log-interval 1000` 기준이라 20초 관측에서는 변화가 보이지 않을 수 있다.

## 5. GPU/프로세스 상태

GPU 최신 관측:

```text
NVIDIA GeForce RTX 4080 SUPER, util 약 42%, VRAM 약 3130 / 16376 MiB, temp 약 42C
```

프로세스 관측:

- runner PID `3944` 생존
- tokenizer child PID `70448` 생존
- webui PID `147452`, `82776` 생존

판단:

- GPU는 RTX 4080 SUPER를 계속 사용 중이다.
- VRAM 사용량과 온도는 장기 실행 기준 안정 범위로 관측된다.
- 70초 동안 tokenizer CPU time도 증가했으므로 프로세스는 대기 상태가 아니라 실제 연산 중이다.

## 6. checkpoint/predictor 상태

현재 model weight/checkpoint/predictor 관련 weight 파일 수:

```text
0
```

확인 결과:

- `finetune_tokenizer/checkpoints` 디렉터리는 존재하지만 아직 저장된 weight 파일은 없다.
- predictor progress/log/checkpoint도 아직 생성되지 않았다.
- 따라서 학습 완료 모델로 예측을 평가하는 단계는 아직 시작 전이다.

## 7. 웹 대시보드 상태

HTTP 확인 결과:

- `http://127.0.0.1:5070/training?refresh_interval=10` 응답 정상, 자동 새로고침 UI 포함
- `http://127.0.0.1:5070/?refresh_interval=10` 응답 정상, 학습 요약 패널 포함
- `http://127.0.0.1:5070/stom?refresh_interval=10` 응답 정상, 학습 상태 strip 포함

사용자가 직접 확인할 URL:

```text
http://127.0.0.1:5070/training?refresh_interval=10
```

## 8. 현재 단계와 남은 단계

| 구분 | 상태 | 완료율 |
|---|---|---:|
| STOM DB -> Qlib/학습 데이터 준비 | 완료 | 100% |
| 전체 학습 실행 준비/런칭 | 완료 | 100% |
| 실시간 학습 대시보드 통합 | 완료 | 100% |
| tokenizer 학습 | 진행 중 | 19.57% |
| predictor 학습 | 대기 | 0% |
| checkpoint 기반 예측 CSV 생성 | 대기 | 0% |
| 실제값 vs 예측값 대시보드 성과 검증 | 대기 | 0% |
| trading score/filter 재검증 | 대기 | 0% |

전체 프로젝트 관리 진행률은 개발/대시보드 기준으로는 약 97%지만, 실제 학습 산출물 기준으로는 아직 tokenizer 약 19.57% / 전체 both-stage 약 9.78% 단계다.

## 9. 다음 권장 OMX 명령

다음 단계도 새 학습을 시작하지 말고 현재 long-running 학습을 건드리지 않는 점검으로 진행한다.

```text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
```
