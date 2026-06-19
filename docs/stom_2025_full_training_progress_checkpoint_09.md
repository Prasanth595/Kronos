# STOM 2025 전체 학습 진행 체크포인트 09

작성일: 2026-05-12 KST
실행 모드: `$ralph` 다음 단계 점검
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 1. 이번 단계의 목적

이번 단계는 STOM tick/1초봉 기반 2025년 전체 학습을 다시 시작하거나 수정하는 단계가 아니다. 이미 실행 중인 장기 학습 프로세스를 유지한 채, 실제 진행률이 증가하는지와 checkpoint/predictor 전환 여부를 재검증하고 문서와 commit으로 남기는 단계다.

목적을 잃지 않기 위한 기준:

1. 현재 long-running 학습 프로세스는 중단하지 않는다.
2. STOM DB/sample 데이터는 읽기 전용으로만 다룬다.
3. predictor 전환 전에는 “학습 완료 모델 성과”로 해석하지 않는다.
4. 매 점검마다 진행률, checkpoint, GPU, 대시보드 상태를 기록한다.

## 2. OMX 도구 사용 결과

AGENTS.md 지침에 따라 `omx explore`를 먼저 시도했다. 현재 Windows 환경에서는 POSIX wrapper 기반 allowlist harness 문제로 실패했다. 이어서 `omx sparkshell`도 시도했지만 현재 CLI에서 `program not found`로 실패했다.

따라서 이번 점검도 PowerShell, Python urllib, `nvidia-smi`, git 검증으로 대체했다.

```text
omx explore: Windows POSIX harness 미준비로 실패
omx sparkshell: program not found
fallback: PowerShell + Python urllib + nvidia-smi + git
```

## 3. 실시간 학습 상태

| 항목 | 값 |
|---|---:|
| 전체 status | running |
| 현재 stage | tokenizer |
| tokenizer step | 1,020,000 / 4,701,721 |
| tokenizer stage 진행률 | 21.6942% |
| 전체 2-stage 진행률 | 10.8471% |
| samples/sec | 약 67.40 |
| 추정 steps/sec | 약 16.85 |
| tokenizer ETA | 약 60.7시간 |
| 최신 loss 로그 | `[Rank 0, Epoch 1/1, Step 1020000/4701721] LR 0.000182, Loss: -0.0311` |

진행률:

```text
tokenizer 단계       [████░░░░░░░░░░░░░░░░] 21.69%
전체 both-stage 학습  [██░░░░░░░░░░░░░░░░░░] 10.85%
predictor 단계       [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 4. 이전 체크포인트 대비 증가량

이전 commit `dc4e72a`의 체크포인트 08은 `Step 922000 / 4701721`이었다.

이번 점검 기준:

```text
이전 체크포인트: 922000 step
현재 체크포인트: 1020000 step
증가량: +98000 step
tokenizer 진행률: 19.6098% -> 21.6942%
전체 진행률: 9.8049% -> 10.8471%
```

따라서 학습은 절전/장기 실행 이후에도 계속 누적 진행되고 있다.

## 5. step 증가 재검증

75초 간격으로 live API와 tokenizer CPU time을 다시 확인했다.

```text
before: Step 1019000 / 4701721, overall 10.8365%
after : Step 1020000 / 4701721, overall 10.8471%
CPU delta for tokenizer PID 70448 over 75s: +75.22 seconds
```

해석:

- step이 실제로 1,000 증가했다.
- tokenizer 프로세스 CPU time도 관측 시간과 거의 같은 폭으로 증가했다.
- 학습은 멈춘 상태가 아니라 계속 진행 중이다.

## 6. GPU/프로세스 상태

GPU 최신 관측:

```text
NVIDIA GeForce RTX 4080 SUPER, util 약 40%, VRAM 약 3241 / 16376 MiB, temp 약 42C
```

프로세스 관측:

- runner PID `3944` 생존
- tokenizer child PID `70448` 생존
- webui PID `147452`, `82776` 생존

판단:

- GPU와 CPU 모두 장기 학습에 계속 사용 중이다.
- VRAM 사용량과 온도는 안정 범위로 보인다.
- 현재 병목은 VRAM 한계보다 학습 loop/데이터 처리/모델 연산 속도 쪽으로 보는 것이 맞다.

## 7. checkpoint/predictor 상태

현재 artifact 확인 결과:

```text
checkpoint/model/predictor artifact count: 0
finetune_tokenizer/checkpoints exists: true
finetune_tokenizer/checkpoints file count: 0
```

결론:

- tokenizer checkpoint는 아직 저장되지 않았다.
- predictor progress/log/checkpoint는 아직 생성되지 않았다.
- predictor 전환 전이므로 아직 실제 예측 모델 성과를 판단할 수 없다.

## 8. 웹 대시보드 상태

HTTP 확인 결과:

- `http://127.0.0.1:5070/training?refresh_interval=10` 응답 정상, 자동 새로고침 UI 포함
- `http://127.0.0.1:5070/?refresh_interval=10` 응답 정상, 학습 요약 패널 포함
- `http://127.0.0.1:5070/stom?refresh_interval=10` 응답 정상, 학습 상태 strip 포함

사용자가 직접 확인할 URL:

```text
http://127.0.0.1:5070/training?refresh_interval=10
```

## 9. 현재 단계와 남은 단계

| 구분 | 상태 | 완료율 |
|---|---|---:|
| STOM DB -> Qlib/학습 데이터 준비 | 완료 | 100% |
| 전체 학습 실행 준비/런칭 | 완료 | 100% |
| 실시간 학습 대시보드 통합 | 완료 | 100% |
| tokenizer 학습 | 진행 중 | 21.69% |
| predictor 학습 | 대기 | 0% |
| checkpoint 기반 예측 CSV 생성 | 대기 | 0% |
| 실제값 vs 예측값 대시보드 성과 검증 | 대기 | 0% |
| trading score/filter 재검증 | 대기 | 0% |

현재는 “개발 준비” 관점에서는 거의 완료 단계지만, “학습 산출물” 관점에서는 아직 전체 both-stage 기준 약 10.85%다.

## 10. 다음 권장 OMX 명령

다음 단계도 새 학습을 시작하지 말고 현재 long-running 학습을 보존하면서 점검한다.

```text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
```
