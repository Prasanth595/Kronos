# 2025년 STOM tick pred60 Kronos-small 전체 학습 중간 체크포인트

작성일: 2026-05-11 KST  
대상 run: `stom_1s_grid_pred60_2025_full_small`  
목적: 장기 학습이 실제로 계속 진행 중인지 tokenizer progress/log/GPU를 확인하고, 방향성을 잃지 않도록 현재 단계와 남은 단계를 기록한다.

## 1. 현재 단계 위치

```text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 단계 완료율:     ████████████████████ 100%  중간 진행 점검 완료
실제 학습 진행률:     ░░░░░░░░░░░░░░░░░░░░ 0.3190%
```

이번 단계의 완료 조건은 **학습 완료가 아니라 중간 진행이 계속 증가하는지 검증하는 것**이다.

## 2. 프로세스 생존 확인

| 역할 | PID | 상태 |
|---|---:|---|
| `/training` webui parent | 147452 | 실행 중 |
| `/training` webui child/reloader | 101468 | 실행 중 |
| full training runner | 3944 | 실행 중 |
| tokenizer child | 70448 | 실행 중 |

중요: 위 학습 프로세스, 특히 `3944`, `70448`은 임의 종료하지 않는다.

## 3. 진행률 2회 샘플 검증

두 시점에서 `/api/training/status`와 tokenizer log를 확인했다.

| 시점 | stage | step | total steps | loss | stage % | overall % | samples/sec | ETA seconds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1차 | tokenizer | 28,000 | 4,701,721 | -0.0274 | 0.5955 | 0.2978 | 72.33 | 258,484 |
| 2차 | tokenizer | 30,000 | 4,701,721 | -0.0316 | 0.6381 | 0.3190 | 72.63 | 257,301 |

해석:

- 90초 뒤 step이 28,000 → 30,000으로 증가했다. 문서 검증 직전 추가 API 확인에서는 step 31,000까지 증가했다.
- loss 로그가 계속 생성되고 있다.
- `/training` API와 stdout log가 동일한 진행 상태를 표시한다.
- 현재 기준 tokenizer 단계는 정상 진행 중이다.

## 4. 최근 로그 tail

```text
[Rank 0, Epoch 1/1, Step 19000/4701721] LR 0.000028, Loss: -0.0302
[Rank 0, Epoch 1/1, Step 20000/4701721] LR 0.000029, Loss: -0.0299
[Rank 0, Epoch 1/1, Step 21000/4701721] LR 0.000030, Loss: -0.0311
[Rank 0, Epoch 1/1, Step 22000/4701721] LR 0.000031, Loss: -0.0294
[Rank 0, Epoch 1/1, Step 23000/4701721] LR 0.000032, Loss: -0.0285
[Rank 0, Epoch 1/1, Step 24000/4701721] LR 0.000033, Loss: -0.0224
[Rank 0, Epoch 1/1, Step 25000/4701721] LR 0.000034, Loss: -0.0298
[Rank 0, Epoch 1/1, Step 26000/4701721] LR 0.000035, Loss: -0.0318
[Rank 0, Epoch 1/1, Step 27000/4701721] LR 0.000036, Loss: -0.0319
[Rank 0, Epoch 1/1, Step 28000/4701721] LR 0.000037, Loss: -0.0274
[Rank 0, Epoch 1/1, Step 29000/4701721] LR 0.000038, Loss: -0.0329
[Rank 0, Epoch 1/1, Step 30000/4701721] LR 0.000039, Loss: -0.0316
```

## 5. GPU 상태

| 항목 | 값 |
|---|---:|
| GPU | NVIDIA GeForce RTX 4080 SUPER |
| utilization | 약 35~37% |
| VRAM | 약 3,121~3,128 MiB / 16,376 MiB |
| power.draw | `[N/A]`로 미제공 |
| 온도 | 약 44~46°C |

해석:

- GPU는 사용 중이며 온도는 안정 범위로 보인다.
- VRAM 사용량은 약 3.1GB로 4080 SUPER 16GB 한도 내다.
- `power.draw`는 이 환경의 `nvidia-smi`가 `[N/A]`를 반환하므로 웹에서도 `-`로 표시되는 것이 정상이다.

## 6. 현재 결론

현재 학습은 정상 진행 중이다.

확인된 것:

- 프로세스 생존
- tokenizer running 상태
- step 증가
- loss 로그 생성
- GPU 사용
- `/training` API 갱신

아직 완료되지 않은 것:

- tokenizer 전체 4,701,721 step 완료
- tokenizer validation
- tokenizer checkpoint 저장
- predictor 자동 시작
- predictor checkpoint 저장
- 최종 예측 CSV 생성
- `/stom` 실제값/예측값 성과 검증

## 7. 다음 점검 권장 기준

다음 점검은 아래 중 하나를 기준으로 수행한다.

1. 약 30분~1시간 뒤 step이 계속 증가하는지 확인
2. 1% 단위 진행률 도달 시점 기록
3. GPU 사용률/온도 이상 징후 확인
4. tokenizer checkpoint 생성 전까지 중간 상태를 반복 기록

## 8. 다음 권장 OMX 명령

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 progress/log/GPU를 다시 점검하고, step 증가와 이상 여부를 문서화한 뒤 checkpoint 생성 전까지 중간 commit으로 남기세요.
```
