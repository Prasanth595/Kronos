# STOM 강화학습 성과 모델 최종 리뷰

작성일: 2026-05-23 KST  
브랜치: `feature/stom-rl-lab`  
대상: **Kronos 비의존 STOM tick/back DB 기반 강화학습 실험실 + full test split 성과 검증 + 웹 대시보드**

---

## 1. 최종 결론

현재 플랫폼은 **연구·검증 플랫폼으로는 사용 가능**하다. 다만 현재 학습된 `contextual_bandit` 모델은 full test split 기준으로 `buy_and_hold`를 이기지 못했고 25bp cost gate도 통과하지 못했으므로 **실거래 후보가 아니라 보류/watch 상태**다.

| 질문 | 최종 답 |
|---|---|
| STOM 2025 1초봉 episode 기반 RL 실험실 구축 | 완료 |
| 전체 test split 기준 baseline 검증 | 완료 |
| contextual bandit full eval | 완료 |
| 모델별 performance leaderboard | 완료 |
| 웹 대시보드에서 성과 비교 | 완료 |
| DQN/PPO 확장 방향 | 설계 완료 |
| 현재 모델 실거래 사용 | 보류 |

---

## 2. 전체 페이지 진행률

| 페이지 | 이름 | 상태 | 주요 산출물 |
|---:|---|---|---|
| 1 | 성과 기준 재정의 | 완료 | `docs/stom_rl_performance_goal_pages_2026-05-23.md` |
| 2 | full baseline/cost gate | 완료 | `stom_rl/leaderboard.py`, baseline full artifact |
| 3 | contextual bandit full eval | 완료 | contextual bandit full test artifact |
| 4 | leaderboard artifact | 완료 | `stom_rl/performance_leaderboard.py` |
| 5 | dashboard leaderboard | 완료 | RL Lab 리더보드 탭/차트/표 |
| 6 | DQN/PPO 확장 설계 | 완료 | `docs/stom_rl_dqn_ppo_extension_design_2026-05-23.md` |
| 7 | 최종 리뷰 | 완료 | 본 문서 |

진행률: **7 / 7 = 100%**

`███████ 100%`

---

## 3. 핵심 커밋 흐름

| 커밋 | 의미 |
|---|---|
| `926e1b9` | 성과 검증 기준과 full/smoke 구분을 먼저 문서화 |
| `64e46f9` | full test split baseline leaderboard를 빠르게 계산 |
| `0d9e52c` | contextual bandit을 full test split으로 평가 |
| `fd56218` | baseline/RL 결과를 하나의 performance leaderboard로 통합 |
| `075cdd5` | 웹 대시보드에서 performance leaderboard를 비교 가능하게 통합 |
| `c62aa88` | DQN/PPO 확장 순서와 dependency 판단을 문서화 |

---

## 4. 현재 데이터와 평가 범위

| 항목 | 값 |
|---|---:|
| 데이터 기준 | STOM 2025 1초봉 episode manifest |
| 전체 episode | 18,750 |
| 종목 수 | 1,638 |
| 거래일/session | 240 |
| train episode | 13,256 |
| val episode | 2,764 |
| test episode | 2,730 |
| 원본 export row | 33,360,325 |
| 시간 범위 | 09:00~09:30 |
| lookback | 300초 |
| reward horizon | 300초 |
| 비용 기준 | 25bp |

중요: 최종 성과 판단은 smoke가 아니라 **test split 전체 2,730 episode** 기준이다.

---

## 5. 최종 리더보드 판단

25bp 비용 기준 full test split 결과:

| 순위 | 모델/정책 | 평균 episode net % | 거래 수 | MDD % | 사용 판단 |
|---:|---|---:|---:|---:|---|
| 1 | buy_and_hold | 0.5126 | 2,730 | -50.7280 | baseline |
| 2 | contextual_bandit | 0.1254 | 971 | -51.5892 | watch |
| 3 | no_trade | 0.0000 | 0 | 0.0000 | risk baseline |
| 4 | mean_reversion | -23.2925 | 170,868 | -47.7542 | 부적합 |
| 5 | volume_filter | -26.1600 | 167,923 | -49.7977 | 부적합 |
| 6 | momentum | -27.9136 | 164,944 | -62.5398 | 부적합 |
| 7 | random | -77.0568 | 806,047 | -81.8887 | 부적합 |

해석:

1. contextual bandit은 no-trade보다 낫다.
2. contextual bandit은 과도한 단순 매매 전략보다 낫다.
3. 그러나 buy-and-hold보다 낮다.
4. MDD도 buy-and-hold보다 더 나쁘다.
5. 따라서 실거래 후보가 아니라 연구용 watch 모델이다.

---

## 6. 웹 대시보드 상태

현재 웹 강화학습 실험실은 다음을 표시한다.

| 기능 | 상태 |
|---|---|
| RL run 목록 | 동작 |
| performance leaderboard artifact 감지 | 동작 |
| 리더보드 차트 | 동작 |
| 리더보드 표 | 동작 |
| cost gate 표 | 동작 |
| trades/equity artifact | 해당 run에 존재할 때 표시 |
| Korean UI | 기존 v2 테마와 통합 |

검증 endpoint:

```text
GET / -> 200
GET /api/rl/runs?limit=10 -> 200
GET /api/rl/runs/stom_1s_2025_performance_leaderboard_full_test -> 200
GET /api/rl/runs/stom_1s_2025_performance_leaderboard_full_test/table/leaderboard?limit=7 -> 200
GET /api/training/status -> 200
```

---

## 7. 최종 QA 결과

### 7.1 Python 테스트

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests -q
```

결과:

```text
94 passed, 2 skipped, 2 warnings in 73.39s
```

경고는 Plotly datetime future warning 2개이며 이번 강화학습 변경의 실패는 아니다.

### 7.2 프론트 빌드

```powershell
npm run build
```

결과:

```text
svelte-check found 0 errors and 4 warnings
vite build completed
```

경고 4개는 기존 `ForecastWorkbenchTab.svelte`, `DocsTab.svelte` 접근성/CSS warning이다. 이번 RL Lab 변경으로 새 error는 발생하지 않았다.

### 7.3 API smoke

Flask test client 기준 핵심 endpoint가 모두 200을 반환했다.

브라우저 UI는 build artifact와 API smoke까지 확인했다. 현재 세션에서 별도 browser-use tool이 노출되지 않아 실제 클릭 자동화는 수행하지 못했지만, 웹 페이지 HTML과 RL API는 정상 응답했다.

---

## 8. 남은 리스크

| 리스크 | 설명 | 대응 |
|---|---|---|
| 현재 모델 성과 부족 | contextual bandit이 buy-and-hold 미달 | DQN/PPO 후보 검토 |
| MDD 큼 | buy-and-hold와 contextual bandit 모두 -50% 수준 | reward에 drawdown/risk penalty 반영 필요 |
| 비용 민감도 | 25bp 비용에서 대부분 단순 정책 붕괴 | trade count 제한/target position action 검토 |
| dependency 미추가 | DQN/PPO 실제 학습은 아직 미구현 | 사용자 승인 후 Gymnasium/SB3 추가 |
| test split 반복 튜닝 위험 | test 결과로 계속 튜닝하면 과최적화 | train/val/test discipline 유지 |

---

## 9. 다음 권장 작업

현재 목표는 7페이지 기준으로 완료되었다. 다음 개발을 이어간다면 새 목표로 진행하는 것이 좋다.

권장 명령:

```powershell
omx ultragoal complete-goals
```

다만 현재 Codex thread는 이전 완료 legacy goal 때문에 OMX ultragoal checkpoint가 blocked reconciliation을 반복한다. 안정적인 다음 방식은 다음 중 하나다.

1. **새 Codex thread에서 같은 repo/worktree를 열고 새 goal로 시작**
2. 또는 현재 브랜치에서 git commit 기준으로 계속 진행

다음 실제 구현 후보:

```text
P008 Gymnasium adapter + check_env
P009 DQN smoke 학습
P010 DQN validation/full test leaderboard 통합
P011 PPO 비교 실험
P012 risk-aware reward와 target-position action 개선
```

---

## 10. 최종 사용 판단

| 용도 | 판단 |
|---|---|
| 연구/검증 대시보드 | 사용 가능 |
| STOM tick/back 데이터 기반 RL 실험 | 사용 가능 |
| 모델 성과 비교/기록 | 사용 가능 |
| 자동매매 실거래 후보 | 현재는 보류 |
| 다음 모델 개발 기반 | 사용 가능 |

최종 결론:

**플랫폼 구축 목표는 달성했다. 모델 수익성 목표는 아직 달성하지 못했다.**  
따라서 다음 단계는 플랫폼 개발이 아니라, Gymnasium/SB3 기반 DQN smoke와 validation 중심의 모델 고도화다.
