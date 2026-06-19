# PPO 100k 전체 test split(2,730 episode) 정직 재평가

- 작성일: **2026-05-31 KST** / 브랜치: `feature/stom-rl-lab`
- 대상: 저장된 SB3 PPO 100k 모델(`webui/rl_runs/stom_1s_2025_sb3_ppo_100k/ppo_model.zip`) — **RULE strategy lab, the model is on trial. NOT a profit claim.**
- 구현: `.omx/ppo_full_eval.py`(production `_evaluate_model`/`_summarize_model` 재사용, checkpoint-resumable) / 산출물 `.omx/artifacts/ppo_full_eval/summary.json`
- 동기: 리더보드의 PPO 100k "buy-and-hold 통과(+1.03%)"가 **20~100 episode 소표본** 평가였음. 전체 2,730으로 정직하게 재평가.

---

## 0. 한 줄 결론

**소표본 환상 확정.** PPO 100k의 평균 수익은 표본을 100→2,730 episode로 늘리자 **+1.016% → +0.165%/episode로 84% 붕괴**했고, **buy-and-hold(+0.513%)에 진다(beats_bh=False), cost gate 미통과, episode 중앙값은 −0.276%(음수)**. 즉 트레이드 과반이 손실이고 평균은 소수 대박이 겨우 양수로 끌어올린 것. **이 PPO 모델은 검증된 수익 모델이 아니다.**

> 검증: 동일 드라이버가 첫 100 episode에서 기존 eval100(+1.0161952713615299)을 **소수점까지 재현** → 드라이버는 정확하고, 차이는 순전히 표본 크기.

---

## 1. 표본이 커질수록 무너지는 곡선 (결정론적)

| 누적 episode | avg net %/ep | episode median % |
|---:|---:|---:|
| 100 | **+1.016** | +0.681 |
| 200 | +0.596 | +0.412 |
| 300 | +0.426 | +0.300 |
| 500 | +0.310 | +0.187 |
| 700 | +0.121 | −0.035 |
| 1,000 | +0.127 | −0.204 |
| 1,500 | +0.172 | −0.267 |
| 2,000 | ~+0.17 | ~−0.26 |
| **2,730 (전체)** | **+0.165** | **−0.276** |

→ 100 episode의 +1.0%는 운 좋은 초기 구간일 뿐, 표본이 커지자 **+0.165%로 수렴**. median은 +0.68%에서 **−0.28%로 추락** — 분포가 "대부분 소액 손실 + 소수 대박"임을 드러냄.

---

## 2. 전체 2,730 episode 실측 (확정)

| 지표 | 값 |
|---|---:|
| episode_count | 2,730 |
| **avg_episode_net_return_pct** | **+0.1652%** |
| median_episode_net_return_pct | **−0.2763%** |
| avg_trade_net_return_pct | +0.1029% |
| hit_rate (수익 트레이드 비율) | **31.4%** |
| trades_per_episode | 1.556 (총 4,249 트레이드) |
| max_drawdown_pct | **−74.32%** |
| passes_cost_gate | **False** |
| beats_buy_and_hold | **False** |
| beats_no_trade | True (간신히) |
| cost_bps | 25 |

---

## 3. baseline 비교 (전체 test split, 25bp, 동일 조건)

| 정책 | avg net %/ep | beats BH | cost gate | 평가 |
|---|---:|---|---|---|
| **PPO 100k (full, 본 문서)** | **+0.165** | ❌ | ❌ | watch |
| buy_and_hold | +0.513 | — | ❌ | baseline (최강) |
| contextual_bandit (full) | +0.125 | ❌ | ❌ | watch |
| no_trade | 0.000 | ❌ | — | baseline |
| momentum/mean_reversion/random | 음수 | ❌ | ❌ | baseline |

→ PPO 100k(+0.165%)는 contextual bandit(+0.125%)과 **사실상 동급**이고, **buy-and-hold(+0.513%)의 약 1/3**. 즉 학습된 RL 모델이 "아무것도 안 하고 들고 있기"보다 못함. (리더보드의 dqn_50k +1.61%·ppo_100k +1.03% 등 "buy-and-hold 통과" 행은 전부 N=5~100 소표본이라 동일한 환상으로 추정 — 정직한 평가는 전체 표본 필요.)

---

## 4. 핵심 함의

1. **"모델이 있다 ≠ 수익이 난다."** PPO/DQN zip은 디스크에 실재하고 로드·실행되지만, 전체 표본에선 buy-and-hold도 못 이긴다. 리더보드의 표면적 우위는 소표본 아티팩트.
2. **median 음수(−0.276%)·hit 31%**: 전형적 모멘텀 추격 실패 — 대부분 손절, 가끔 큰 승. MDD −74%는 배포 불가 수준.
3. **다른 게이트들과 정합**: shuffle(선택 무알파)·P1b(타이밍 NO-GO)·SL게이트(방향 아닌 리스크만 예측)에 이어, **학습된 정책의 실수익도 baseline 미달**. 일관된 결론 — 이 데이터에서 RL은 방향성 수익을 못 낸다.

---

## 5. 정직성 캐비엇

1. 본 평가는 `mark_to_market` 환경의 buy/hold/sell 단일종목 정책 재생. 25bp 비용 반영, 슬리피지 0(낙관). 실거래는 더 나쁠 수 있음.
2. compounded_return +901%는 **비복리 가정의 산술적 누적**이지 실현 수익이 아님 — avg_episode +0.165%가 정직한 1회 기대.
3. triggered-subset DB, L2 없음, 라이브 포워드 없음. **수익 보장 아님.**
4. 드라이버는 production 함수(`_evaluate_model`/`_summarize_model`) 그대로 재사용 + 첫 청크가 eval100 재현 → 수치 신뢰 가능. RULE not RL.

---

## 6. 재현

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 .omx/ppo_full_eval.py 0   # checkpoint-resumable, summary.json 갱신
```
산출: `.omx/artifacts/ppo_full_eval/summary.json`. 핵심(2026-05-31): N=2,730, avg +0.1652%, median −0.2763%, hit 31.4%, MDD −74.3%, passes_cost_gate False, beats_buy_and_hold False.

---

## 7. 트랙 갱신

| 항목 | 상태 |
|---|---|
| **PPO 100k 전체 재평가** | ✅ **완료 — +0.165%/ep, buy-and-hold 미달, cost gate 미통과 (소표본 +1.0% 환상 확정)** |
| 학습된 RL 모델 일반 결론 | ❌ 전체 표본서 baseline 미달 — 검증된 수익 모델 없음 |
| RULE 전략 | ✅ 별개 트랙(타 문서); 본 문서는 RL 모델 정직 평가 |
