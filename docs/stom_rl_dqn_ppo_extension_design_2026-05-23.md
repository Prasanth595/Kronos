# STOM 강화학습 DQN/PPO 확장 설계

작성일: 2026-05-23 KST  
브랜치: `feature/stom-rl-lab`  
목적: **현재 STOM tick/back 1초봉 강화학습 실험실을 DQN/PPO 계열로 확장할 수 있는지 판단하고, 새 의존성 추가 전 필요한 계약·리스크·구현 순서를 고정한다.**

---

## 1. 결론 요약

현재 STOM 강화학습 환경은 DQN/PPO 확장이 **가능한 구조**다. 하지만 바로 `stable-baselines3`를 붙여 장시간 학습을 시작하기보다는, 먼저 Gymnasium 호환 adapter를 추가하고 작은 smoke 학습이 `check_env`와 cost-gate 검증을 통과하는지 확인해야 한다.

| 질문 | 판단 |
|---|---|
| DQN 적용 가능성 | 가능. action이 `hold/buy/sell` 3개 discrete라 DQN 후보가 맞다. |
| PPO 적용 가능성 | 가능. discrete action에도 적용 가능하지만 on-policy라 sample 비용이 더 크다. |
| 지금 바로 새 dependency 추가 | 보류. 사용자가 명시 승인하기 전까지 추가하지 않는다. |
| 현재 `StomTickTradingEnv` 그대로 SB3 사용 | 불완전. Gymnasium 스타일 반환값은 있으나 실제 `gymnasium.Env` 상속/space가 아니다. |
| 우선순위 | 1) Gymnasium adapter 2) DQN smoke 3) full train/val 4) PPO 비교 |

---

## 2. 공식 가이드 기준

P006 설계는 다음 공식 문서를 기준으로 했다.

| 자료 | 설계에 반영한 내용 |
|---|---|
| Gymnasium Env API: https://gymnasium.farama.org/api/env/ | `reset()`은 `(observation, info)`, `step()`은 `(observation, reward, terminated, truncated, info)` 형태여야 한다. |
| Stable-Baselines3 custom env: https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html | custom env는 Gymnasium interface와 `check_env` 검증이 필요하다. |
| Stable-Baselines3 DQN docs: https://stable-baselines3.readthedocs.io/en/v2.7.0/modules/dqn.html | DQN은 discrete action 학습 후보이며 `MlpPolicy`, `MultiInputPolicy` 등 정책을 선택한다. |
| Stable-Baselines3 custom policy docs: https://stable-baselines3.readthedocs.io/en/master/guide/custom_policy.html | 2D 시계열 observation을 그대로 쓸지, flatten/feature extractor를 둘지 결정해야 한다. |

---

## 3. 현재 코드의 준비 상태

현재 핵심 파일은 `stom_rl/trading_env.py`다.

| 항목 | 현재 상태 | DQN/PPO 관점 |
|---|---|---|
| `reset()` 반환 | `(observation, info)` | Gymnasium 스타일과 일치 |
| `step()` 반환 | `(observation, reward, terminated, truncated, info)` | Gymnasium 스타일과 일치 |
| action | `0 hold`, `1 buy`, `2 sell` | DQN/PPO 둘 다 가능 |
| observation shape | `(lookback_window, 9)` | SB3 MLP는 flatten 처리 필요 |
| observation columns | OHLCV/amount + position/unrealized/time | 최소 상태는 있음 |
| space | 자체 `BoxSpace`, `DiscreteSpace` | SB3에는 실제 `gymnasium.spaces` 필요 |
| env base class | 일반 class | SB3에는 `gymnasium.Env` adapter 필요 |
| reward mode | `horizon`, `mark_to_market` | DQN/PPO에는 `mark_to_market` 우선 검토 |
| dependency | `gymnasium`, `stable-baselines3` 없음 | 새 dependency 승인 전 문서화 단계 유지 |

---

## 4. 왜 contextual bandit만으로 부족했는가

현재 full test split 리더보드에서 contextual bandit은 no-trade보다 낫지만 buy-and-hold를 이기지 못했다.

| 모델/정책 | 평균 episode net % | MDD % | 판단 |
|---|---:|---:|---|
| buy_and_hold | 0.5126 | -50.7280 | 현재 최강 baseline |
| contextual_bandit | 0.1254 | -51.5892 | watch, 실거래 후보 아님 |
| no_trade | 0.0000 | 0.0000 | 리스크 기준선 |

부족한 이유:

1. contextual bandit은 한 시점의 feature로 “살지 말지”를 판단한다.
2. position 상태, 연속 의사결정, 청산 타이밍, drawdown 제어를 충분히 학습하지 못한다.
3. 25bp 비용 후 target 분포 자체가 음수로 치우쳐 있다.
4. 평균 수익은 양수지만 MDD가 buy-and-hold보다 나빠 cost gate를 통과하지 못했다.

DQN/PPO를 검토하는 이유는 **한 번의 예측 점수**가 아니라 **상태→행동→보상 누적**을 학습하기 위해서다.

---

## 5. DQN/PPO 적용 전 필요한 adapter

현재 환경을 직접 바꾸기보다, 기존 read-only 환경을 감싸는 adapter를 추가하는 것이 안전하다.

예상 파일:

```text
stom_rl/gym_adapter.py
tests/test_stom_rl_gym_adapter.py
```

adapter 책임:

| 책임 | 설명 |
|---|---|
| `gymnasium.Env` 상속 | SB3가 custom env로 인식하게 함 |
| `gymnasium.spaces.Discrete(3)` | action space를 실제 Gymnasium space로 제공 |
| `gymnasium.spaces.Box` | observation space를 실제 Gymnasium Box로 제공 |
| dtype 고정 | `np.float32` 유지 |
| reset/step 위임 | 기존 `StomTickTradingEnv` 계약 유지 |
| `check_env` 통과 | SB3 학습 전 필수 smoke 검증 |

dependency를 추가하지 않는 현재 단계에서는 adapter 코드를 바로 넣지 않는다. 다음 구현 단계에서 사용자가 새 dependency 추가를 승인하면 위 파일부터 만든다.

---

## 6. Observation 설계

현재 observation은 `(300, 9)`이다.

| 방식 | 장점 | 단점 | 판단 |
|---|---|---|---|
| flatten + MlpPolicy | 가장 단순, DQN/PPO smoke 빠름 | 시계열 구조를 직접 학습하기 어려움 | 1차 smoke 후보 |
| Dict observation + MultiInputPolicy | 가격/포지션/시간 feature 분리 가능 | 구현 복잡도 증가 | 2차 후보 |
| custom CNN/Transformer extractor | 1초봉 시계열 구조 반영 가능 | 과최적화·학습 비용 증가 | 성과 확인 후 후보 |

초기 DQN/PPO는 과도한 모델보다 **flatten MLP + 강한 검증**이 낫다. 현재 문제는 모델 복잡도보다 비용 후 일반화와 리스크 관리가 더 중요하다.

---

## 7. Reward 설계

DQN/PPO에는 `reward_mode=mark_to_market`을 우선 검토한다.

| reward mode | 장점 | 위험 |
|---|---|---|
| `horizon` | 300초 후 수익 목표와 직접 연결 | 매 step마다 미래 horizon 보상이 겹쳐 과도한 dense target이 될 수 있음 |
| `mark_to_market` | 실제 보유 상태 변화와 비용을 순차 반영 | 초기 학습이 느릴 수 있음 |
| realized PnL only | 실제 매매 손익에 가장 가까움 | sparse reward라 학습 난이도 상승 |

권장 순서:

1. DQN smoke: `mark_to_market`
2. 비교 실험: `horizon` vs `mark_to_market`
3. 최종 판단: full test leaderboard와 cost gate 기준

---

## 8. Action 설계

현재 action은 `hold/buy/sell`이다. invalid action은 penalty를 받는다.

문제:

- 이미 보유 중인데 `buy`
- 미보유 중인데 `sell`
- 잦은 buy/sell 반복으로 비용 폭증

개선 후보:

| 후보 | 설명 | 적용 시점 |
|---|---|---|
| invalid penalty 유지 | 현재 구조 유지 | DQN smoke |
| target position action | `flat/long` 2개 action으로 단순화 | invalid action이 많으면 적용 |
| action masking | 불가능 action 차단 | SB3 기본 DQN/PPO에는 직접 지원 약함 |
| sb3-contrib MaskablePPO | action mask 지원 | 새 dependency 리스크 검토 후 |

초기에는 현재 3-action을 유지하되, invalid action rate를 leaderboard에 추가해 판단한다.

---

## 9. 학습/평가 프로토콜

| 단계 | split | 목적 | 통과 기준 |
|---|---|---|---|
| smoke | train 소량 | 코드 계약 검증 | 학습 완료, artifact 생성 |
| validation | val 전체 또는 대표 stride | hyperparameter 선택 | no-trade 초과, 비용 후 양수 |
| final | test 전체 | 최종 판단 | buy-and-hold 초과 또는 cost gate 통과 |

절대 하지 말아야 할 것:

1. test split으로 hyperparameter를 반복 튜닝
2. 비용 없는 수익률만 보고 성공 판단
3. trade count/MDD 없이 평균 수익만 보고 채택
4. seed 1개만 보고 결론 확정

---

## 10. DQN 우선 실험안

DQN을 PPO보다 먼저 권장한다.

| 이유 | 설명 |
|---|---|
| action이 discrete | DQN의 기본 적용 대상 |
| off-policy | replay buffer로 sample 효율 기대 |
| smoke 비용 | PPO보다 짧은 실험이 가능 |
| 비교 용이 | buy/hold/sell Q-value 정책 해석 가능 |

예상 1차 파라미터:

| 항목 | 값 |
|---|---|
| policy | `MlpPolicy` |
| reward mode | `mark_to_market` |
| train split | train |
| eval split | val → test |
| total timesteps smoke | 50k 이하 |
| full 후보 | 500k~2M timesteps |
| seed | 최소 3개 |
| artifact | model zip, eval summary, leaderboard row |

---

## 11. PPO 후순위 실험안

PPO는 다음 조건을 만족하면 진행한다.

1. DQN smoke가 정상적으로 학습된다.
2. DQN이 no-trade는 이기지만 buy-and-hold를 못 이긴다.
3. action 분포가 불안정하거나 Q-learning이 과최적화된다.

예상 1차 파라미터:

| 항목 | 값 |
|---|---|
| policy | `MlpPolicy` |
| n_steps | 512~2048 |
| batch_size | 64~256 |
| gamma | 0.99 |
| learning_rate | 3e-4 근처 |
| eval | validation cost gate 우선 |

PPO는 sample 비용이 크므로 full test 판단 전 validation에서 먼저 걸러야 한다.

---

## 12. 새 dependency 판단

현재 `requirements.txt`에는 `gymnasium`, `stable-baselines3`가 없다.

| 선택지 | 장점 | 단점 | 판단 |
|---|---|---|---|
| dependency 추가 보류 | 현재 repo 안정성 유지 | DQN/PPO 실제 학습은 못 함 | 현재 P006 결론 |
| `gymnasium`만 추가 | env 계약 검증 가능 | SB3 학습은 못 함 | adapter 단계 후보 |
| `stable-baselines3` 추가 | DQN/PPO 즉시 사용 | 의존성/설치/버전 리스크 | 사용자 승인 후 |
| 자체 DQN 구현 | 의존성 최소화 | 검증된 RL 구현을 다시 만드는 리스크 | 비권장 |

권장:

1. 다음 구현 단계에서 사용자가 승인하면 `gymnasium`과 `stable-baselines3`를 명시적으로 추가한다.
2. 먼저 `check_env`와 DQN smoke만 실행한다.
3. smoke가 안정되면 full validation/test로 확장한다.

---

## 13. 대시보드 확장 계획

DQN/PPO가 추가되면 기존 `performance_leaderboard` schema를 그대로 확장한다.

추가 row 예:

```json
{
  "source": "rl_model",
  "model": "dqn",
  "split": "test",
  "cost_bps": 25,
  "avg_episode_net_return_pct": 0.0,
  "max_drawdown_pct": 0.0,
  "passes_cost_gate": false,
  "beats_buy_and_hold": false,
  "usability": "watch"
}
```

웹은 이미 `performance_leaderboard` artifact를 읽으므로, DQN/PPO 결과 생성기만 같은 schema로 내보내면 대시보드 추가 수정은 최소화된다.

---

## 14. 최종 P006 판단

| 항목 | 판단 |
|---|---|
| DQN/PPO 확장 | 가능 |
| 당장 실거래 개선 보장 | 불가 |
| 새 dependency 즉시 추가 | 보류 |
| 다음 구현 우선순위 | Gymnasium adapter + check_env + DQN smoke |
| 성공 기준 | full test split에서 buy-and-hold 초과 또는 cost gate 통과 |

P006의 결론은 “DQN/PPO로 갈 수 있다”가 아니라, **어떤 순서와 검증 기준으로 가야 실패를 줄일 수 있는지 고정했다**는 것이다.
