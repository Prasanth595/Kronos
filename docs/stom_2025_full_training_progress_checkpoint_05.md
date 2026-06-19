# 2025년 STOM tick pred60 Kronos-small 전체 학습 중간 체크포인트 5

작성일: 2026-05-11 KST
대상 run: stom_1s_grid_pred60_2025_full_small
목적: 다섯 번째 중간 점검으로 장기 tokenizer 학습이 계속 증가하는지, checkpoint 또는 predictor 전환이 발생했는지 확인한다.

## 1. 전체 계획과 현재 위치

| 페이지/단계 | 목표 | 상태 | 완료율 |
|---|---|---|---:|
| 1. STOM tick DB 이해와 1초봉/QLib 변환 | 전체 데이터 학습 가능한 형태 준비 | 완료 | 100% |
| 2. Kronos 공식 가이드 준수 파인튜닝 파이프라인 | full sequential 학습 실행 가능 | 완료 | 100% |
| 3. 웹 학습 모니터링 | /training에서 progress/log/GPU 확인 | 완료 | 100% |
| 4. 2025년 전체 tokenizer 학습 | 전체 데이터 tokenizer 학습 진행 | 진행 중 | 14.1225% |
| 5. predictor 학습 자동 전환 | tokenizer 완료 후 predictor 시작 | 대기 | 0% |
| 6. checkpoint 기반 예측 생성 | 학습 모델로 예측 CSV 생성 | 대기 | 0% |
| 7. 실제값 vs 예측값 대시보드 성과 검증 | 종목별/전체 통계와 그래프 확인 | 대기 | 0% |

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  다섯 번째 progress/log/GPU/checkpoint 확인 완료
실제 학습 진행률:     █░░░░░░░░░░░░░░░░░░░ 7.0612%
~~~

이번 단계의 완료 조건은 학습 완료가 아니라 **장기 학습 정상 진행, checkpoint 미생성/전환 전 상태, 다음 점검 기준**을 정확히 남기는 것이다.

## 2. 프로세스 생존 확인

| 역할 | PID | 상태 |
|---|---:|---|
| /training webui | 147452 | 실행 중 |
| full training runner | 3944 | 실행 중 |
| tokenizer child | 70448 | 실행 중 |
| /training webui | 108252 | 실행 중 |

중요: full training runner와 tokenizer child는 현재 학습의 핵심 프로세스이므로 종료하지 않는다.

## 3. 진행률 샘플 검증

| 구분 | 관측 시간 | stage | step | total steps | loss | LR | stage % | overall % | samples/sec | ETA |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 이전 commit 최종 관측 | 2026-05-11 20:19 KST | tokenizer | 463,000 | 4,701,721 | -0.0180 | 0.000198 | 9.8475 | 4.9237 | 77.97 | 217,449s |
| 이번 1차 샘플 | 2026-05-11 23:43 KST | tokenizer | 662,000 | 4,701,721 | -0.0297 | 0.000194 | 14.0800 | 7.0400 | 73.49 | 219,874s |
| 이번 2차 샘플 | 2026-05-11 23:45 KST | tokenizer | 663,000 | 4,701,721 | -0.0298 | 0.000194 | 14.1012 | 7.0506 | 73.46 | 219,916s |
| 문서 작성 직전 | 2026-05-11 23:46 KST | tokenizer | 664,000 | 4,701,721 | -0.0324 | 0.000194 | 14.1225 | 7.0612 | 73.42 | 219,970s |

해석:

- 이전 checkpoint 463,000 step에서 이번 점검 664,000 step까지 증가했다.
- 짧은 간격 재샘플에서 662,000 → 663,000 step 증가를 확인했다.
- samples/sec는 약 73.42 수준이다.
- ETA는 약 61.1 시간으로 표시되지만 장기 학습 중 속도 변화에 따라 달라질 수 있다.
- tokenizer는 아직 stage 1/2이며 predictor는 아직 시작되지 않았다.

## 4. checkpoint 및 predictor 전환 확인

| 항목 | 결과 |
|---|---|
| tokenizer progress status | running |
| train stage | tokenizer |
| requested train stage | both |
| checkpoint/model/predictor file count | 0 |
| checkpoint/model/predictor search result | NO_CHECKPOINT_OR_PREDICTOR_FILE_FOUND |

결론: 현재 시점에는 tokenizer checkpoint 또는 predictor 관련 파일이 아직 생성되지 않았다. 따라서 predictor 전환도 아직 전이다.

## 5. 최근 로그 tail

~~~text
[Rank 0, Epoch 1/1, Step 653000/4701721] LR 0.000194, Loss: -0.0289
[Rank 0, Epoch 1/1, Step 654000/4701721] LR 0.000194, Loss: 0.0012
[Rank 0, Epoch 1/1, Step 655000/4701721] LR 0.000194, Loss: -0.0311
[Rank 0, Epoch 1/1, Step 656000/4701721] LR 0.000194, Loss: -0.0319
[Rank 0, Epoch 1/1, Step 657000/4701721] LR 0.000194, Loss: -0.0271
[Rank 0, Epoch 1/1, Step 658000/4701721] LR 0.000194, Loss: -0.0297
[Rank 0, Epoch 1/1, Step 659000/4701721] LR 0.000194, Loss: -0.0219
[Rank 0, Epoch 1/1, Step 660000/4701721] LR 0.000194, Loss: -0.0288
[Rank 0, Epoch 1/1, Step 661000/4701721] LR 0.000194, Loss: -0.0313
[Rank 0, Epoch 1/1, Step 662000/4701721] LR 0.000194, Loss: -0.0297
[Rank 0, Epoch 1/1, Step 663000/4701721] LR 0.000194, Loss: -0.0298
[Rank 0, Epoch 1/1, Step 664000/4701721] LR 0.000194, Loss: -0.0324
~~~

## 6. GPU 상태

최신 nvidia-smi 관측:

~~~text
NVIDIA GeForce RTX 4080 SUPER, 38, 3179, 16376, [N/A], 42
~~~

GPU는 계속 사용 중이며, VRAM 사용량과 온도는 장기 실행 기준 안정 범위로 관측된다.

## 7. 현재 결론

현재 tokenizer 학습은 정상 진행 중이다.

확인된 것:

- runner/tokenizer 프로세스 생존
- tokenizer running 유지
- step 증가 지속
- loss 로그 생성 지속
- GPU 사용 지속
- checkpoint/model/predictor 파일은 아직 미생성
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

1. step이 664,000 이후 계속 증가하는지
2. checkpoint/model 파일이 생성되었는지
3. predictor.progress.json 또는 predictor 로그가 생겼는지
4. GPU 사용률과 온도가 안정적인지
5. /training 대시보드가 계속 최신 상태를 표시하는지

## 9. 다음 권장 OMX 명령

~~~text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~