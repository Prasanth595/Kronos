# STOM 2025 전체 학습 진행 체크포인트 11

작성일: 2026-05-12 KST
실행 모드: `$ralph` 다음 단계 점검
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 1. 이번 단계의 목적

이번 단계는 실행 중인 STOM tick/1초봉 기반 2025년 전체 학습을 보존하면서 진행 상태를 다시 확인하는 체크포인트다. 학습을 재시작하거나 중단하지 않고, 현재 tokenizer 진행률과 checkpoint/predictor 전환 여부만 검증한다.

목표를 잃지 않기 위한 기준:

1. long-running 학습 프로세스를 중단하지 않는다.
2. STOM DB/sample 데이터는 수정하지 않는다.
3. checkpoint가 생기기 전까지 예측 성과를 말하지 않는다.
4. predictor 전환 전에는 “학습 완료 모델”로 판단하지 않는다.
5. 매 점검 결과를 문서와 commit으로 남긴다.

## 2. OMX 도구 사용 결과

AGENTS.md 지침에 따라 `omx explore`를 먼저 시도했지만, 현재 Windows 환경에서 POSIX wrapper 기반 allowlist harness가 준비되지 않아 실패했다. 이어 `omx sparkshell`도 시도했지만 현재 CLI에서 `program not found`로 실패했다.

따라서 이번 점검은 PowerShell, Python urllib, `nvidia-smi`, git 검증으로 대체했다.

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
| tokenizer step | 1,136,000 / 4,701,721 |
| tokenizer stage 진행률 | 24.1614% |
| 전체 2-stage 진행률 | 12.0807% |
| samples/sec | 약 66.24 |
| 추정 steps/sec | 약 16.56 |
| tokenizer ETA | 약 59.8시간 |
| 최신 loss 로그 | `[Rank 0, Epoch 1/1, Step 1136000/4701721] LR 0.000177, Loss: -0.0311` |

진행률:

```text
tokenizer 단계       [█████░░░░░░░░░░░░░░░] 24.16%
전체 both-stage 학습  [██░░░░░░░░░░░░░░░░░░] 12.08%
predictor 단계       [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 4. 이전 체크포인트 대비 증가량

이전 commit `28043a7`의 체크포인트 10은 `Step 1,079,000 / 4,701,721`이었다.

이번 점검 기준:

```text
이전 체크포인트: 1,079,000 step
현재 체크포인트: 1,136,000 step
증가량: +57,000 step
tokenizer 진행률: 22.9490% -> 24.1614%
전체 진행률: 11.4745% -> 12.0807%
```

따라서 학습은 checkpoint 10 이후에도 계속 누적 진행되고 있다.

## 5. step 증가 재검증

75초 간격으로 live API와 tokenizer CPU time을 다시 확인했다.

```text
before: Step 1134000 / 4701721, overall 12.0594%
after : Step 1136000 / 4701721, overall 12.0807%
CPU delta for tokenizer PID 70448 over 75s: +75.30 seconds
```

해석:

- step이 실제로 2,000 증가했다.
- tokenizer 프로세스 CPU time도 관측 시간과 거의 같은 폭으로 증가했다.
- 학습은 멈춘 상태가 아니라 계속 진행 중이다.

## 6. GPU/프로세스 상태

GPU 최신 관측:

```text
NVIDIA GeForce RTX 4080 SUPER, util 약 43%, VRAM 약 3294 / 16376 MiB, temp 약 50C
```

프로세스 관측:

- runner PID `3944` 생존
- tokenizer child PID `70448` 생존
- webui PID `147452`, `91172` 생존

판단:

- GPU와 CPU 모두 장기 학습에 계속 사용 중이다.
- VRAM 사용량은 4080 SUPER 기준 여유가 있으나, 현재 학습 속도는 약 66.2 samples/sec 수준으로 관측된다.
- 장기 학습 진행 상황을 볼 때 GPU 고부하 단일 작업이라기보다 데이터 처리와 학습 루프가 함께 병목에 영향을 주는 상태로 해석된다.

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
| tokenizer 학습 | 진행 중 | 24.16% |
| predictor 학습 | 대기 | 0% |
| checkpoint 기반 예측 CSV 생성 | 대기 | 0% |
| 실제값 vs 예측값 대시보드 성과 검증 | 대기 | 0% |
| trading score/filter 재검증 | 대기 | 0% |

현재는 “개발/대시보드 준비” 관점에서는 거의 완료 단계지만, “학습 산출물” 관점에서는 전체 both-stage 기준 약 12.08%다.

## 10. 다음 권장 OMX 명령

다음 단계도 새 학습을 시작하지 말고 현재 long-running 학습을 보존하면서 점검한다.

```text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
```
