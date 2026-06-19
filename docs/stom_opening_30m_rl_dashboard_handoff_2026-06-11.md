# STOM 시초 30분 RL/호가/대시보드 핸드오프 — 2026-06-11

## 0. 목적

이 문서는 2026-06-01 이후 진행된 STOM 시초 30분 tick/orderbook/orderbook-imbalance 기반 연구와 공식 대시보드 리모델링 작업을 다음 작업자가 바로 이어받기 위한 핸드오프 문서다.

핵심 목표는 다음이다.

```text
시초 30분 tick/orderbook 기반 연구 검증 시스템을 구축하고,
RULE baseline(ts_imb), PPO/DQN/orderbook RL 후보, participant proxy,
호가 imbalance, 과열/윗꼬리 feature를 OOS, negative control,
feature ablation으로 검증한 뒤,
공식 대시보드에서 누적 수익곡선, 시간별 거래, 성과 이력,
실패 원인, GO/NO-GO 판정을 확인할 수 있게 만든다.
```

범위는 **연구 검증 시스템**이다. 실거래, broker 연동, 수익 보장, live-ready 주장은 제외한다.

---

## 1. 현재 결론 요약

| 항목 | 현재 판단 |
|---|---|
| 시스템 개발 방향 | 맞다. 대시보드는 연구 이력/성과/실패를 노출하는 evidence viewer로 가야 한다. |
| 대시보드 리모델링 | 상당 부분 진행됨. 공식 대시보드 방향으로 통합 중이며 RL/Rule evidence를 보여주는 기반이 있다. |
| 강화학습 연구 | 가능하지만 아직 수익 모델은 아니다. PPO/DQN/orderbook RL은 research-only 후보로 유지해야 한다. |
| 가장 중요한 기준선 | `ts_imb` 시초 30분 RULE baseline. 절대 RL로 부르면 안 된다. |
| 최신 실험 verdict | `NO-GO_CONTROL` |
| 비용 가정 | `23bp` round trip |
| 실거래 준비도 | 0%. 현재는 local backtest/research/dashboard evidence 전용이다. |

---

## 2. 반드시 지켜야 할 연구/표현 규칙

| 규칙 | 이유 |
|---|---|
| `ts_imb`는 RULE baseline이다. RL이 아니다. | 수익곡선이 rule에서 나온 경우 RL 성과로 오해하면 안 된다. |
| `NO-GO_CONTROL`을 숨기지 않는다. | 실패를 숨기면 다음 실험이 과최적화된다. |
| 비용은 기본 `23bp`로 명시한다. | 초단타/시초 전략에서는 비용이 성과를 크게 바꾼다. |
| dashboard는 read-only evidence viewer다. | 실거래/주문/브로커 기능을 넣으면 연구 검증 경계가 무너진다. |
| leading-zero 종목코드를 보존한다. | `000250` 같은 코드를 int로 바꾸면 데이터가 깨진다. |
| OOS, negative control, no-trade/RULE baseline 비교 없이 alpha를 주장하지 않는다. | 과최적화/우연 성과를 걸러내기 위함이다. |
| 호가/orderbook RL은 research-only다. | 현재 성과 검증이 충분하지 않다. |

---

## 3. 지금까지 구축된 주요 축

### 3.1 공식 대시보드 리모델링

| 구성 | 상태 | 메모 |
|---|---|---|
| Flask backend | 진행됨 | `webui/app.py`, `webui/rl_dashboard*.py` 계열 |
| Svelte dashboard | 진행됨 | `webui/v2_src/**`; 내부 경로는 v2지만 사용자-facing 표현은 공식 대시보드 방향 |
| RL/Trading 탭 | 진행됨 | `webui/v2_src/src/tabs/RLTradingTab.svelte`, `rlTrading/` components |
| Rule/RL 라벨 분리 | 개선됨 | `opening_30m_rule_filter`는 RL experiment가 아니라 RULE/meta-label evidence로 표시해야 함 |
| table/API loader | 진행됨 | `rule_filter_controls`, `rule_filter_ablations`, `rule_filter_proxy_availability`, `rule_filter_orderbook_persistence` 확인됨 |
| dist build | 생성됨 | `webui/static/v2/dist/**`는 generated/optional commit group으로 분리 |

### 3.2 시초 30분 RULE/RL 연구

| 연구 | 파일/영역 | 현재 의미 |
|---|---|---|
| RULE baseline | `ts_imb` 계열, rule-filter artifacts | 가장 중요한 비교 기준선 |
| Rule-filter | `stom_rl/opening_30m_rule_filter_*.py` | OOS, control, ablation, gate, lifecycle 관리 |
| PPO/DQN 후보 | `stom_rl/opening_30m_rl_*`, SB3/orderbook files | research-only 후보. baseline을 이겨야 승격 가능 |
| Orderbook RL | `stom_rl/orderbook_rl_env.py`, `orderbook_sb3_*` | 호가/imbalance 상태공간 실험 기반 |
| Participant proxy | `participant_pressure_*`, market participant studies | 외국인/기관/프로그램 직접 식별 대신 proxy feature 연구 |
| 과열/윗꼬리 feature | rule-filter/participant proxy와 결합 대상 | 거래대금 폭증 후 지속성/고점 형성 가설 검증 필요 |

---

## 4. 최신 검증/성과 상태

가장 최근 커밋 위생/검증 작업에서 확인된 핵심 증거는 다음 위치에 있다.

| 증거 | 경로 |
|---|---|
| 최종 상태 요약 | `.omo/evidence/commit-hygiene-jun1/final-status.md` |
| 커밋 그룹 문서 | `.omo/evidence/commit-hygiene-jun1/commit-groups.md` |
| staging inventory | `.omo/evidence/commit-hygiene-jun1/staging-inventory.md` |
| docs encoding report | `.omo/evidence/commit-hygiene-jun1/docs-encoding-report.md` |
| LOC report | `.omo/evidence/commit-hygiene-jun1/loc-report.md` |
| dashboard loader/API evidence | `.omo/evidence/commit-hygiene-jun1/f3-dashboard-loader.md` |

검증 결과 요약:

| 검증 | 결과 |
|---|---|
| Rule-filter policy/CLI/dashboard tests | 17 passed |
| Dashboard API/source/route/dist tests | 25 passed |
| Orderbook env/SB3/persistence tests | 16 passed |
| Dashboard table regression tests | 18 passed |
| Svelte build/check | 0 errors, 4 warnings |
| Dashboard loader/API tables | 4/4 tables 200 OK |
| staged generated scan | staged files 0개 |
| `git diff --cached --check` | PASS, no staged files |

중요: 위 검증은 연구/대시보드 시스템 검증이다. **수익 가능 모델 검증 통과가 아니다.** 최신 trading verdict는 여전히 `NO-GO_CONTROL`이다.

---

## 5. 현재 dirty worktree 상태와 커밋 전략

현재 worktree에는 대량의 source/docs/tests/generated 변경이 섞여 있다. 무조건 bulk commit하면 안 된다.

권장 commit group은 다음 순서다.

| 순서 | 그룹 | 설명 |
|---:|---|---|
| 1 | guardrails/knowledge | `AGENTS.md` 계열 규칙 문서 |
| 2 | dashboard source/tests | 공식 대시보드와 evidence viewer 코드/테스트 |
| 3 | STOM research source/tests | opening 30m RL/rule/orderbook/participant proxy 연구 코드와 테스트 |
| 4 | research docs | readable docs만 포함. mojibake 문서는 제외 |
| 5 | optional dist | `webui/static/v2/dist/**`만 별도. deployment 필요 시에만 |

현재 이 핸드오프 커밋은 **문서 단독 커밋**으로 남긴다. 기존 대량 변경은 의도적으로 stage하지 않는다.

---

## 6. 알려진 위험/미완료 항목

| 항목 | 상태 | 다음 조치 |
|---|---|---|
| 실제 수익 모델 | 미완료 | baseline 대비 OOS/negative control/ablation 통과 필요 |
| `NO-GO_CONTROL` | 유지 | 숨기지 말고 실패 원인 분석 대상으로 관리 |
| 대형 Python 파일 | 8개 이상 250 pure LOC 초과 | split 또는 legacy-large rationale 필요 |
| 깨진 한글 문서 | 3개 hold-out | 복구 전 commit 제외 |
| generated/session/cache | 많음 | `.omo`, `.omc`, `.codegraph`, `webui/rl_runs`, `webui/stom_predictions`는 기본 제외 |
| dist assets | 생성물 | source commit과 섞지 말고 optional dist commit으로 분리 |
| 대시보드 시각화 | 개선 필요 | 누적 수익곡선, 시간별 거래, 실패 원인, feature ablation 비교 강화 |
| RL 성과 | 낮음/불확실 | PPO/DQN/orderbook RL은 RULE baseline을 이길 때까지 research-only |

---

## 7. 다음 작업자가 바로 볼 파일

| 목적 | 파일 |
|---|---|
| 현재 방향성 | `AGENTS.md`, `docs/AGENTS.md`, `stom_rl/AGENTS.md`, `webui/AGENTS.md` |
| 대시보드 backend | `webui/rl_dashboard.py`, `webui/rl_dashboard_opening_tables.py`, `webui/app.py` |
| 대시보드 frontend | `webui/v2_src/src/tabs/RLTradingTab.svelte`, `webui/v2_src/src/tabs/rlTrading/*` |
| Rule-filter CLI | `stom_rl/opening_30m_rule_filter_cli.py` |
| Rule-filter policy/gate | `stom_rl/opening_30m_rule_filter_policy.py`, `stom_rl/opening_30m_rule_filter_gate.py` |
| Orderbook RL | `stom_rl/orderbook_rl_env.py`, `stom_rl/orderbook_sb3_adapter.py`, `stom_rl/orderbook_sb3_smoke.py` |
| Participant proxy | `stom_rl/participant_pressure_contract.py`, `stom_rl/participant_pressure_features.py`, `stom_rl/market_participant_studies.py` |
| 핵심 tests | `tests/test_stom_rl_opening_rule_filter_*.py`, `tests/test_stom_rl_dashboard_*.py`, `tests/test_stom_rl_orderbook_*.py` |

---

## 8. 다음 권장 실행 순서

### Step 1. worktree 정리/commit 실행 계획 확정

먼저 `.omo/evidence/commit-hygiene-jun1/commit-groups.md`를 기준으로 실제 commit을 나눈다.

추천 명령:

```text
$ulw-plan commit-groups.md 기준으로 generated/session/cache 제외, mojibake docs 제외, 대형 Python 파일 정책을 반영하여 안전한 실제 commit 실행 계획 수립
```

### Step 2. 대시보드 연구 UI 완성

누적 수익곡선, 시간별 거래, feature ablation, negative control, 실패 원인을 한 화면에서 비교할 수 있게 만든다.

추천 명령:

```text
$ulw-loop 공식 대시보드 RL/Trading 탭을 연구 검증 화면으로 완성. 누적 수익곡선, 시간별 거래, OOS split, negative control, feature ablation, rule/RL 구분, 실패 원인, GO/NO-GO 판정을 확인할 수 있게 개선
```

### Step 3. 모델 연구 루프 지속

RULE baseline을 먼저 고정하고 RL은 baseline을 이길 때만 승격한다.

추천 명령:

```text
$ulw-loop 시초 30분 tick/orderbook/orderbook-imbalance 기반 STOM 강화학습 연구를 계속 진행. RULE baseline(ts_imb), PPO/DQN/orderbook RL 후보, participant proxy, 호가 imbalance, 과열/윗꼬리 feature를 OOS, negative control, feature ablation으로 검증하고 GO/NO-GO 판정을 누적 기록
```

---

## 9. 바로 실행할 검증 명령

```powershell
py -3.11 -m pytest tests/test_stom_rl_opening_rule_filter_policy.py tests/test_stom_rl_opening_rule_filter_cli.py tests/test_stom_rl_opening_rule_filter_dashboard.py -q
py -3.11 -m pytest tests/test_stom_rl_dashboard_api.py tests/test_stom_rl_dashboard_tab.py tests/test_v2_route.py tests/test_v2_dist_marker.py -q
py -3.11 -m pytest tests/test_stom_rl_orderbook_env.py tests/test_stom_rl_orderbook_sb3.py tests/test_stom_rl_orderbook_persistence.py -q
cd webui/v2_src
npm run build
npm run check --if-present
cd ../..
git diff --check
git diff --cached --check
```

---

## 10. 최종 목표 정의

최종 목표는 다음 세 가지를 동시에 만족하는 것이다.

| 목표 | 판정 기준 |
|---|---|
| 연구 시스템 | 실험 이력, feature, baseline, control, OOS, 실패 원인을 재현 가능하게 기록한다. |
| 대시보드 | 누적 수익곡선/시간별 거래/성과 이력/feature ablation/GO-NO-GO를 read-only로 확인한다. |
| 모델 후보 | RULE baseline, no-trade, negative control보다 OOS에서 우월해야 하며 비용 `23bp`와 drawdown gate를 통과해야 한다. |

그 전까지 모든 PPO/DQN/orderbook RL 결과는 다음으로만 표현한다.

```text
RL experiment / research-only / not live-ready / not a profit model
```

---

## 11. 다음 세션 시작 문구

다음 세션에서는 아래 문구로 시작하면 된다.

```text
docs/stom_opening_30m_rl_dashboard_handoff_2026-06-11.md와 .omo/evidence/commit-hygiene-jun1/commit-groups.md를 먼저 읽고, generated/session/cache를 제외한 안전한 commit group 실행 또는 공식 대시보드 RL/Trading 연구 검증 화면 완성을 이어서 진행해주세요. ts_imb는 RULE baseline이고 최신 verdict는 NO-GO_CONTROL, cost는 23bp입니다. 실거래/수익보장/broker 연동은 제외합니다.
```
