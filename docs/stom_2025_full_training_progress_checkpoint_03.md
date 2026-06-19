# 2025년 STOM tick pred60 Kronos-small 전체 학습 중간 체크포인트 3

작성일: 2026-05-11 KST
대상 run: stom_1s_grid_pred60_2025_full_small
목적: 세 번째 중간 점검으로 tokenizer 장기 학습이 계속 증가하는지, checkpoint 또는 predictor 전환이 발생했는지 확인한다.

## 1. 현재 단계 위치

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  세 번째 progress/log/GPU/checkpoint 확인 완료
실제 학습 진행률:     ░░░░░░░░░░░░░░░░░░░░ 1.7759%
~~~

이번 단계의 완료 조건은 학습 완료가 아니라 장기 학습의 정상 진행, checkpoint 미생성/전환 전 상태의 정확한 기록이다.

## 2. 프로세스 생존 확인

| 역할 | PID | 상태 |
|---|---:|---|
| /training webui | 147452 | 실행 중 |
| full training runner | 3944 | 실행 중 |
| tokenizer child | 70448 | 실행 중 |
| /training webui | 108252 | 실행 중 |

중요: full training runner와 tokenizer child는 현재 학습의 핵심 프로세스이므로 종료하지 않는다.

## 3. 진행률 샘플 검증

| 구분 | 관측 시간 | stage | step | total steps | loss | stage % | overall % | samples/sec | ETA seconds |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 이전 commit 후 최종 관측 | 2026-05-11 15:47 KST | tokenizer | 142,000 | 4,701,721 | -0.0293 | 3.0202 | 1.5101 | 76.76 | 237,596 |
| 이번 1차 샘플 | 2026-05-11 16:06 KST | tokenizer | 164,000 | 4,701,721 | -0.0329 | 3.4881 | 1.7440 | 76.54 | 237,151 |
| 이번 2차 샘플 | 2026-05-11 16:07 KST | tokenizer | 165,000 | 4,701,721 | -0.0339 | 3.5094 | 1.7547 | 76.52 | 237,147 |
| 문서 작성 직전 | 2026-05-11 16:08 KST | tokenizer | 167,000 | 4,701,721 | -0.0269 | 3.5519 | 1.7759 | 76.5 | 237,116 |

해석:

- 이전 commit 후 142,000 step에서 이번 점검 167,000 step까지 증가했다.
- 70초 간격 재샘플에서 164,000 → 165,000 step 증가를 확인했다.
- samples/sec는 약 76.5 수준으로 이전 관측과 유사하다.
- tokenizer는 아직 stage 1/2이며 predictor는 아직 시작되지 않았다.

## 4. checkpoint 및 predictor 전환 확인

| 항목 | 결과 |
|---|---|
| tokenizer progress status | running |
| train stage | tokenizer |
| requested train stage | both |
| checkpoint/model file count | 0 |
| checkpoint/model search result | NO_CHECKPOINT_OR_MODEL_FILE_FOUND |

결론: 현재 시점에는 tokenizer checkpoint 또는 predictor model checkpoint가 아직 생성되지 않았다. 따라서 predictor 전환도 아직 전이다.

## 5. 최근 로그 tail

~~~text
[Rank 0, Epoch 1/1, Step 156000/4701721] LR 0.000200, Loss: -0.0328
[Rank 0, Epoch 1/1, Step 157000/4701721] LR 0.000200, Loss: -0.0314
[Rank 0, Epoch 1/1, Step 158000/4701721] LR 0.000200, Loss: -0.0319
[Rank 0, Epoch 1/1, Step 159000/4701721] LR 0.000200, Loss: -0.0228
[Rank 0, Epoch 1/1, Step 160000/4701721] LR 0.000200, Loss: -0.0317
[Rank 0, Epoch 1/1, Step 161000/4701721] LR 0.000200, Loss: -0.0320
[Rank 0, Epoch 1/1, Step 162000/4701721] LR 0.000200, Loss: -0.0336
[Rank 0, Epoch 1/1, Step 163000/4701721] LR 0.000200, Loss: -0.0322
[Rank 0, Epoch 1/1, Step 164000/4701721] LR 0.000200, Loss: -0.0329
[Rank 0, Epoch 1/1, Step 165000/4701721] LR 0.000200, Loss: -0.0339
[Rank 0, Epoch 1/1, Step 166000/4701721] LR 0.000200, Loss: -0.0322
[Rank 0, Epoch 1/1, Step 167000/4701721] LR 0.000200, Loss: -0.0269
~~~

## 6. GPU 상태

최신 nvidia-smi 관측:

~~~text
NVIDIA GeForce RTX 4080 SUPER, 39, 2995, 16376, [N/A], 44
~~~

GPU는 계속 사용 중이며 VRAM 사용량과 온도는 장기 실행 기준 안정 범위로 관측된다.

## 7. 현재 결론

현재 tokenizer 학습은 정상 진행 중이다.

확인된 것:

- runner/tokenizer 프로세스 생존
- tokenizer running 유지
- step 증가 지속
- loss 로그 생성 지속
- GPU 사용 지속
- checkpoint/model 파일은 아직 미생성
- predictor 전환 전

아직 완료되지 않은 것:

- tokenizer 4,701,721 step 완료
- tokenizer validation 및 checkpoint 저장
- predictor 자동 시작
- predictor checkpoint 저장
- checkpoint 기반 예측 CSV 생성
- /stom 실제값/예측값 성과 검증

## 8. 다음 점검 기준

다음 점검에서는 아래를 확인한다.

1. step이 167,000 이후 계속 증가하는지
2. checkpoint/model 파일이 생성되었는지
3. predictor.progress.json 또는 predictor 로그가 생겼는지
4. GPU 사용률과 온도가 안정적인지
5. /training 대시보드가 계속 최신 상태를 표시하는지

## 9. 다음 권장 OMX 명령

~~~text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~