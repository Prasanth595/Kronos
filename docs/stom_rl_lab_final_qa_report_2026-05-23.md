# STOM 독립 강화학습 실험실 최종 QA / 리뷰 보고서

작성일: 2026-05-23 KST  
브랜치: `feature/stom-rl-lab`  
기준 시작점: `af4c5b1` 이후 STOM 독립 강화학습 실험실 구현  
대상 goal: **G009 통합 QA / 리뷰**

---

## 1. 최종 결론

**구현 목표는 달성했다.**

Kronos를 사용하지 않고 STOM tick/back DB 기반 독립 강화학습 실험실을 구축했다.

```text
STOM read-only 데이터 적재
→ episode manifest
→ Gymnasium-style trading env
→ baseline runner
→ 5/10/15/25bp cost gate
→ 1차 contextual bandit 모델 학습/평가/저장/사용
→ /api/rl/* backend API
→ 웹 강화학습 실험실 대시보드
→ 통합 QA / code review / 보류 판단
```

다만, 현재 1차 모델은 **smoke 검증용 모델**이다. 플랫폼과 모델 사용 흐름은 검증되었지만, 실거래 자동화를 바로 켜도 된다는 의미는 아니다. 자동매매 적용은 full test split에서 비용 반영 후 baseline 대비 우위가 반복 검증될 때까지 보류해야 한다.

---

## 2. 요구사항 대응 현황

| 요구사항 | 구현/근거 | 상태 |
|---|---|---|
| Kronos 독립 RL 구현 | `stom_rl/*`, `/api/rl/*`, `RLLabTab.svelte` | 완료 |
| STOM DB read-only 사용 | SQLite URI `mode=ro`, write probe 회귀 테스트 | 완료 |
| 2025 09:00~09:30 episode manifest | 18,750 episodes / 1,638 symbols / 240 sessions | 완료 |
| train/val/test split | train 13,256 / val 2,764 / test 2,730, overlap 0 | 완료 |
| 미래 데이터 누수 방지 | observation timestamp가 action timestamp보다 앞서도록 테스트 | 완료 |
| Gymnasium-style trading env | `StomTickTradingEnv.reset/step`, action 0/1/2 | 완료 |
| baseline runner | no-trade/random/buy-and-hold/momentum/mean-reversion/volume_filter | 완료 |
| 비용 관문 | 5/10/15/25bp, slippage, MDD, rolling fold | 완료 |
| 1차 RL 모델 생성 | `contextual_bandit.py`, `model.json` 저장 | 완료 |
| 학습 모델 사용 흐름 | saved model 기반 eval/actions/trades/equity 산출물 생성 | 완료 |
| Backend API | `/api/rl/runs`, detail, trades, equity, episodes, cost-gate | 완료 |
| 웹 대시보드 | `강화학습 실험실` 탭, KPI/차트/표/해석 | 완료 |
| 최종 검증 | pytest/build/browser smoke/API smoke/code review | 완료 |

---

## 3. 실제 산출물 요약

| runtime artifact | 상태 | 핵심 내용 |
|---|---|---|
| `stom_1s_2025_episode_manifest` | 생성됨 | 18,750 episodes, split delta 0 |
| `stom_1s_2025_baselines_smoke` | 생성됨 | smoke 기준 best policy: buy_and_hold |
| `stom_1s_2025_cost_gate_smoke` | 생성됨 | 25bp 통과 정책 1개: buy_and_hold |
| `stom_1s_2025_contextual_bandit_smoke` | 생성됨 | avg episode net +1.8960%, hit rate 63.64%, MDD -2.6211% |
| 웹 대시보드 | 동작 | run 4개 탐지, cost gate/equity/trade chart 표시 |

### 성과 해석

- contextual bandit smoke는 비용 반영 후 양의 수익률을 보였고 smoke cost gate를 통과했다.
- 그러나 같은 smoke 조건에서 buy-and-hold가 더 우수했다.
- 따라서 현재 모델은 “학습·저장·사용·시각화가 가능하다”를 증명하지만, “실거래 자동화에 충분하다”를 증명하지 않는다.

---

## 4. 검증 증거

### 4.1 전체 Python 테스트

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests -q
```

결과:

```text
92 passed, 2 skipped, 2 warnings
```

비고:

- Windows 환경에서 Torch DLL 초기화가 실패하는 테스트는 `KRONOS_RUN_TORCH_TESTS=1` opt-in으로 분리했다.
- 기존 테스트 의도는 이미 optional Torch dependency였고, 현재 워크스테이션에서는 Torch import가 프로세스에 fatal trace를 남기므로 검증된 PyTorch 환경에서만 실행되게 했다.
- Windows 외 환경에서는 별도 subprocess preflight 후 Torch 초기화 가능 여부를 확인한다.
- 이 guard는 production fallback이 아니라 테스트 환경 optional dependency 처리다.

### 4.2 Frontend build

```powershell
cd webui\v2_src
npm run build
```

결과:

```text
svelte-check 0 errors
기존 경고 4개 유지
vite build OK
```

### 4.3 Python compile

```powershell
C:\Python\64\Python3119\python.exe -m py_compile `
  stom_rl\__init__.py `
  stom_rl\episode_manifest.py `
  stom_rl\trading_env.py `
  stom_rl\baselines.py `
  stom_rl\cost_gate.py `
  stom_rl\contextual_bandit.py `
  webui\rl_dashboard.py `
  webui\app.py
```

결과: 통과

### 4.4 Browser smoke

검증 방식:

- Flask test server를 `http://127.0.0.1:5070/`로 실행
- Playwright headless Chromium으로 접속
- `강화학습 실험실` 탭 클릭
- RL tab marker, cost gate table, run item, contextual bandit 표시 확인

결과:

```text
OK
screenshot: .omx/tmp/rl-lab-g009-final-smoke.png
```

### 4.5 API smoke

| endpoint | 결과 |
|---|---|
| `/api/rl/runs?limit=10` | 200 |
| contextual bandit detail | 200 |
| contextual bandit trades | 200, rows 반환 |
| contextual bandit equity | 200, rows 반환 |
| contextual bandit episodes | 200, rows 반환 |
| cost-gate compact endpoint | 200 |
| path traversal probe | 400으로 차단 |

---

## 5. AI Slop Cleaner 점검

### 5.1 점검 범위

| 범위 | 내용 |
|---|---|
| `stom_rl/*` | episode manifest, env, baseline, cost gate, contextual bandit |
| `webui/rl_dashboard.py` | RL artifact API helper |
| `webui/app.py` | `/api/rl/*` route wiring |
| `webui/v2_src/src/tabs/RLLabTab.svelte` | 웹 대시보드 |
| `webui/v2_src/src/lib/api.ts` | RL API wrapper |
| `tests/*stom_rl*` | 회귀/스모크 테스트 |
| 문서 | goal pages, plan, final QA report |

### 5.2 동작 잠금

정리 전후 동작 검증은 다음으로 잠갔다.

- 전체 pytest: `92 passed, 2 skipped, 2 warnings`
- frontend build: OK
- py_compile: OK
- browser smoke: OK
- API smoke: OK

### 5.3 fallback/마스킹 점검

| 발견 | 판단 |
|---|---|
| Windows Torch opt-in + subprocess preflight in tests | Windows Torch DLL 초기화 실패를 optional dependency skip으로 처리. production masking 아님 |
| production code fallback-like branch | 치명적인 오류 은폐 fallback 없음 |
| API path traversal 처리 | 400으로 차단되어 안전 |
| read-only DB | write probe로 보호 |

### 5.4 구조 점검

| 항목 | 판단 |
|---|---|
| `RLLabTab.svelte` 크기 | 현재는 단일 탭 맥락상 허용. 더 커지면 chart/table 하위 컴포넌트 분리 권장 |
| baseline/cost gate/model runner | 책임 분리 양호 |
| API helper | run directory direct child 제한으로 안전 |
| 테스트 범위 | manifest/env/baseline/cost gate/model/API/UI smoke 포함 |

---

## 6. Code Review 결과

권고: **APPROVE**  
Architect status: **CLEAR**

| 등급 | 결과 |
|---|---|
| Critical | 없음 |
| High | 없음 |
| Medium | 없음 |
| Low | 3개 후속 권장 |

### Low 후속 권장

| 항목 | 권장 |
|---|---|
| `RLLabTab.svelte` | 기능이 더 늘어나면 KPI/CostGate/TradeTable 컴포넌트로 분리 |
| 기존 Svelte 경고 | Forecast/DocsTab의 기존 unused/export warning은 별도 정리 |
| Torch 환경 | Windows 로컬에서 Torch DLL 실패가 반복되므로 `KRONOS_RUN_TORCH_TESTS=1`은 CUDA/PyTorch 재설치 또는 별도 venv 확인 후 사용 |

### 보안/안전 판단

- STOM DB는 read-only로 접근한다.
- RL API는 artifact 조회 전용이며 학습 실행/삭제 같은 상태 변경 endpoint가 없다.
- run/policy path traversal은 차단된다.
- secret/token 노출 없음.

---

## 7. 자동매매 적용 판단

| 질문 | 판단 |
|---|---|
| 지금 만든 모델을 실거래에 바로 써도 되는가? | 아니오 |
| 이유 | smoke 성과이며 full test split과 비용/슬리피지/거래제약 검증이 아직 부족 |
| 플랫폼은 사용할 수 있는가? | 예. 학습, 저장, 평가, 시각화 흐름은 갖춰짐 |
| 다음에 해야 할 일 | full test split leaderboard와 비용 관문 반복 검증 |

자동매매 전환 조건은 다음을 만족해야 한다.

1. full test split에서 no-trade/random/buy-and-hold/momentum 대비 우위
2. 25bp 이상 비용에서 양의 기대값 유지
3. 종목/일자별 성과 편중이 과하지 않음
4. rolling validation에서 성과 붕괴 없음
5. 거래 횟수와 turnover가 현실적인 수준

---

## 8. 다음 권장 단계

| 우선순위 | 작업 | 목적 |
|---|---|---|
| 1 | full test split baseline/cost gate 실행 | smoke가 아닌 전체 검증 기준 확보 |
| 2 | contextual bandit full train/eval | 1차 모델이 전체에서도 유효한지 확인 |
| 3 | DQN/PPO/SB3 후보 비교 | action sequence 학습 가능성 검토 |
| 4 | transaction model 보강 | 호가/체결/슬리피지 현실성 개선 |
| 5 | leaderboard 운영 | 모델별 성과를 웹에서 비교 |

추천 OMX 명령:

```powershell
omx ultragoal create --brief "STOM RL full test split leaderboard와 contextual bandit 전체 학습/평가를 구현하고 웹 대시보드에 모델별 성과 비교를 추가한다."
```

---

## 9. 최종 상태

| 페이지 | 상태 | 완료율 |
|---|---|---:|
| 1. 설계와 기준 고정 | 완료 | 100% |
| 2. DB loader / episode manifest | 완료 | 100% |
| 3. StomTickTradingEnv | 완료 | 100% |
| 4. Baseline runner | 완료 | 100% |
| 5. Reward / cost gate | 완료 | 100% |
| 6. 1차 RL 모델 | 완료 | 100% |
| 7. Backend API | 완료 | 100% |
| 8. 웹 대시보드 | 완료 | 100% |
| 9. 통합 QA / 리뷰 | 완료 | 100% |

전체 진행률: **100%**
