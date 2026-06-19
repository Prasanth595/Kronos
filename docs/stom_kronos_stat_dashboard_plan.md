# STOM official 200k 종목별/전체 통계 대시보드 계획

작성일: 2026-05-10

## 추천 방식 기록

이번 작업은 이전에 추천한 가장 성숙한 방식으로 진행한다.

```text
1. deep-interview 성격의 요구사항 정리
2. autopilot 방식의 계획 -> 구현 -> 검증 -> 코드 리뷰
3. 단계별 한글 commit
```

## 현재까지 완료된 상위 계획

| 큰 단계 | 상태 | 설명 |
| --- | --- | --- |
| Kronos 공식 200k 학습 | 완료 | tokenizer 200k + predictor 200k 완료 |
| holdout 예측/그래프 CSV | 완료 | official200k walk-forward CSV 생성 |
| cost gate 보고서 | 완료 | 25bp gate 실패, 확대 보류 |
| 통계 대시보드 고도화 | 진행 중 | 이번 작업 |

## 이번 작업의 목표

기존 `/stom` 대시보드는 개별 window 실제값/예측값, Top-K, Qlib/filter artifact 중심이다. 이번에는 사용자가 바로 모델 품질을 이해할 수 있도록 다음을 추가한다.

1. 전체 요약 metric 확장
2. 종목별 MAE / RMSE / MAPE / 방향 정확도 순위
3. 종목별 평균 예측 등락률과 실제 등락률
4. 오차 분포 histogram
5. pred_return vs actual_return scatter
6. 종목별 MAPE/방향 정확도 heatmap
7. 전체 데이터 기준 best/worst symbol 테이블
8. 대시보드 API와 frontend UI 추가

## 개발 계획

| 단계 | 내용 | 상태 |
| --- | --- | --- |
| A | 요구사항/계획 문서화 | 진행 중 |
| B | backend 통계 계산 함수와 chart JSON 추가 | 예정 |
| C | Flask API `/api/stom/diagnostics` 추가 | 예정 |
| D | `/stom` frontend 통계 섹션 추가 | 예정 |
| E | 단위/API 테스트 추가 | 예정 |
| F | code-review/검증/최종 보고 | 예정 |

## 완료 기준

- 선택한 예측 CSV로 종목별 통계 API가 동작한다.
- dashboard에서 버튼 클릭으로 전체 통계, 표, histogram/scatter/heatmap이 표시된다.
- 테스트가 통과한다.
- 공식 200k CSV 기준 API smoke가 성공한다.

## 진행 기록 - frontend/API 연결 완료

- `/api/stom/diagnostics` backend API 추가 완료.
- `/stom` 화면에 `Model Diagnostics: 전체/종목별 통계` 섹션 추가 완료.
- 표시 항목:
  - 전체 rows/windows/symbols/sessions/periods
  - MAE/RMSE/MAPE/direction accuracy
  - 종목별 summary table
  - best/worst symbol table
  - 전체 오차 histogram
  - pred_return vs actual_return scatter
  - symbol metric heatmap
- official 200k CSV smoke:
  - symbols = 334
  - symbol_metric_count = 334
  - max_symbols=20 결과 20개 row 반환
  - chart keys = error_distribution, return_scatter, symbol_heatmap

## 최종 검증 기록

- `git diff --check` 통과.
- 관련 테스트 16개 통과, Plotly FutureWarning 2개만 존재.
- compileall 통과.
- `/stom` page status=200, `Model Diagnostics` 포함 확인.
- official 200k diagnostics API status=200.
- official 200k 기준 symbols=334, symbol_metric_count=334, max_symbols=20 반환 확인.
