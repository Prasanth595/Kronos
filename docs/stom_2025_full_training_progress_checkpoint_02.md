# 2025년 STOM tick pred60 Kronos-small 전체 학습 중간 체크포인트 2

작성일: 2026-05-11 KST
대상 run: stom_1s_grid_pred60_2025_full_small
목적: tokenizer 장기 학습이 계속 증가 중인지 추가 확인하고, checkpoint 생성 전까지 진행 상황을 체계적으로 누적 기록한다.

## 1. 현재 단계 위치

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  두 번째 중간 progress/log/GPU 확인 완료
실제 학습 진행률:     ░░░░░░░░░░░░░░░░░░░░ 1.4888%
~~~

이번 단계도 **학습 완료가 아니라 정상 진행 여부 확인**이 완료 조건이다.

## 2. 프로세스 생존 확인

| 역할 | PID | 상태 |
|---|---:|---|
| /training webui | 147452 | 실행 중 |
| full training runner | 3944 | 실행 중 |
| tokenizer child | 70448 | 실행 중 |
| /training webui | 127412 | 실행 중 |

중요: 3944, 70448은 현재 학습의 핵심 프로세스이므로 종료하지 않는다.

## 3. 진행률 샘플 검증

| 시점 | 관측 시간 | stage | step | total steps | loss | stage % | overall % | samples/sec | ETA seconds |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1차 | 2026-05-11 15:38:15 KST | tokenizer | 132,000 | 4,701,721 | -0.0251 | 2.8075 | 1.4037 | 76.90 | 237,712 |
| 2차 | 2026-05-11 15:40:02 KST | tokenizer | 134,000 | 4,701,721 | -0.0308 | 2.8500 | 1.4250 | 76.87 | 237,700 |
| 검증 log | 2026-05-11 15:46 KST | tokenizer | 140,000 | 4,701,721 | -0.0339 | 2.9776 | 1.4888 | 76.81 | 237,574 |

해석:

- 90초 뒤 step이 132,000 → 134,000으로 증가했고, 문서 검증 직전 로그 기준 140,000 step까지 추가 증가했다.
- 이전 체크포인트의 32,000 step 대비 크게 증가했다.
- API/로그가 모두 tokenizer running 상태와 step 증가를 보여준다.
- ETA는 장기 학습 중 변동될 수 있으며, 현재 관측치는 약 66시간 전후로 표시된다.

## 4. 최근 로그 tail

~~~text
[Rank 0, Epoch 1/1, Step 129000/4701721] LR 0.000197, Loss: -0.0336
[Rank 0, Epoch 1/1, Step 130000/4701721] LR 0.000197, Loss: -0.0331
[Rank 0, Epoch 1/1, Step 131000/4701721] LR 0.000198, Loss: -0.0316
[Rank 0, Epoch 1/1, Step 132000/4701721] LR 0.000198, Loss: -0.0251
[Rank 0, Epoch 1/1, Step 133000/4701721] LR 0.000199, Loss: -0.0335
[Rank 0, Epoch 1/1, Step 134000/4701721] LR 0.000199, Loss: -0.0308
[Rank 0, Epoch 1/1, Step 135000/4701721] LR 0.000199, Loss: -0.0332
[Rank 0, Epoch 1/1, Step 136000/4701721] LR 0.000199, Loss: -0.0318
[Rank 0, Epoch 1/1, Step 137000/4701721] LR 0.000200, Loss: -0.0113
[Rank 0, Epoch 1/1, Step 138000/4701721] LR 0.000200, Loss: -0.0344
[Rank 0, Epoch 1/1, Step 139000/4701721] LR 0.000200, Loss: -0.0317
[Rank 0, Epoch 1/1, Step 140000/4701721] LR 0.000200, Loss: -0.0339
~~~

## 5. GPU 상태

최신 nvidia-smi 관측:

~~~text
NVIDIA GeForce RTX 4080 SUPER, 38, 3004, 16376, [N/A], 43
~~~

이전 2회 샘플에서는 utilization 38~46%, VRAM 3.1~3.3GB, 온도 44~50°C 수준이었다. 최신 관측도 GPU가 계속 사용 중임을 보여준다.

## 6. 현재 결론

현재 tokenizer 학습은 정상적으로 진행 중이다.

확인된 것:

- 프로세스 생존
- tokenizer running 유지
- step 증가
- loss 로그 계속 생성
- GPU 사용 지속
- /training API 정상 응답

아직 완료되지 않은 것:

- tokenizer 4,701,721 step 완료
- tokenizer validation 및 checkpoint 저장
- predictor 자동 시작
- predictor checkpoint 저장
- checkpoint 기반 예측 CSV 생성
- /stom 실제값/예측값 성과 검증

## 7. 다음 점검 기준

다음 점검에서는 아래를 확인한다.

1. step이 140,000 이후 계속 증가하는지
2. GPU utilization과 온도가 안정적인지
3. tokenizer checkpoint가 아직 생성 전인지, 또는 생성되었는지
4. predictor로 자동 전환되었는지 여부

## 8. 다음 권장 OMX 명령

~~~text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~
