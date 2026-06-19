# STOM/Kronos 개발 방향성 재검토 — 2026-06-03

## 결론

현재 저장소의 개발 방향은 두 축으로 분리해야 한다.

1. **메인라인:** `ts_imb` 시초 갭상승 RULE 전략의 검증, 사이징, 리스크 관리, read-only forward/paper 준비.
2. **실험라인:** orderbook/RL 모델은 대시보드와 함께 “모델을 검증하고 탈락시키는 실험 장치”로 유지.

즉, 지금까지 만든 RL 인프라와 대시보드는 버릴 필요가 없지만, 수익성 주장을 맡길 축은 아니다. RL은 아직 `NO-GO`이며, 좋은 차트를 만들기보다 baseline 대비 실패/개선 여부를 명확히 보여주는 방향이 맞다.

## 근거 요약

| 영역 | 현재 증거 | 판정 |
|---|---|---|
| `ts_imb` gap-up RULE | 과거 문서에서 비용/체결 stress 후에도 가장 강한 baseline으로 기록 | 계속 진행 |
| PPO/opening candidate | 500 episode OOS에서 cost gate 실패, `NO-GO_USABLE_MODEL` | 사용 모델 아님 |
| skip-gate | full-universe `NO-GO`, negative control hard blocker 포함 | 중단/보류 |
| state-exit gate | full-universe `NO-GO`, primary 자체가 GO 조건 실패 | 중단/보류 |
| free-action DQN/orderbook RL | 과매매/invalid-action/비용 문제로 baseline 열세 | 중단 |
| constrained skip/enter/exit RL | free-action 대비 개선됐지만 아직 baseline 미달 | 연구용 유지 |
| dashboard | API/시각화는 상당히 구현됨. 단, split/seed/cost/baseline 비교가 더 강해야 함 | 계속 개선 |

## 디렉터리별 스코어

| 디렉터리 | 관찰 | AGENTS 필요성 | 방향성 리스크 |
|---|---:|---:|---|
| `stom_rl/` | 약 45개 코드 파일, 약 19.7k LOC, 전략 핵심 | 매우 높음 | RL/RULE 용어 혼동, NO-GO 재튜닝 |
| `webui/` | 약 42개 코드 파일, 약 13.0k LOC, 대시보드/API 핵심 | 높음 | 차트가 성과를 과장할 위험 |
| `webui/v2_src/` | Svelte/Vite 별도 프런트엔드 | 높음 | dist/source 불일치, 거대 탭 유지보수 |
| `finetune/` | STOM/Qlib/훈련 파이프라인 | 중간~높음 | 산출물과 소스 혼재, 환경 민감성 |
| `tests/` | 약 63개 테스트 파일, 약 12.4k LOC | 높음 | 전체 테스트만으로 원인 분리 어려움 |
| `model/` | 작지만 핵심 모델 API | 낮음~중간 | 현 작업 축에서는 상대적으로 안정 |

## 유지할 것

- `ts_imb` RULE baseline을 기준점으로 삼는 평가 체계.
- 23bp 비용과 marketable-fill 계정.
- negative/shuffle control, OOS split, drawdown/cost gate.
- RL 대시보드의 regular route `/rl`.
- orderbook readiness와 action 로그/episode 로그.
- `NO-GO`를 숨기지 않는 문서화 방식.

## 줄이거나 멈출 것

- 자유 action DQN/PPO를 계속 돌려 “좋은 곡선”을 기대하는 방향.
- forced-entry exit-only RL을 주력으로 삼는 방향.
- skip-gate/state-exit gate를 결과를 본 뒤 재튜닝하는 방향.
- dashboard에서 누적 수익 곡선만 강조하고 baseline/비용/실패 사유를 약하게 보이는 방향.
- 실거래 준비 완료, 수익 보장, 라이브 주문 가능 표현.

## 다음 개발 우선순위

| 우선순위 | 작업 | 목적 | 완료 기준 |
|---:|---|---|---|
| 1 | 메인라인/실험라인 라벨 정리 | RULE 전략과 RL 실험 혼동 제거 | docs/dashboard/run metadata에 `rule`/`rl_experiment` 구분 |
| 2 | 대시보드 비교 강화 | 모델 성과를 정직하게 판정 | model vs `ts_imb` baseline vs no-trade, split/seed/cost 배지 |
| 3 | `ts_imb` RULE 사이징/리스크 설계 | 실제 운영 전 필요한 통제 설계 | 일손실한도, 동시보유, 유동성 상한, 중단조건 문서/테스트 |
| 4 | RL은 constrained skip/enter/exit + baseline-relative reward만 유지 | invalid-action/과매매를 줄인 공정 비교 | rolling OOS에서 baseline delta와 NO-GO 사유 산출 |
| 5 | 산출물/소스 정리 | 재현성/리뷰 가능성 개선 | generated artifact와 source 파일 명확히 분리 |

## RL을 계속한다면 조건

RL은 가능하지만, 다음 조건 없이는 “쓸 수 있는 모델”로 부르면 안 된다.

- action space는 자유 매수/매도 반복이 아니라 제한형이어야 한다.
- reward는 절대 수익보다 baseline-relative 형태가 우선이다.
- `ts_imb`, no-trade, random/negative control과 같은 비교군이 필요하다.
- OOS rolling split과 비용/드로우다운 gate를 통과해야 한다.
- invalid action rate, action remap rate, turnover/trade count를 같이 공개해야 한다.

## 대시보드 다음 개선안

- run header에 `artifact_type`, `evaluation_mode`, `split`, `seed`, `cost_bps`, `horizon`, `baseline` 표시.
- KPI에 `baseline_delta`, `max_drawdown`, `trade_count`, `turnover`, `cost_gate`를 고정.
- smoke/full/walk-forward를 색상/배지로 구분.
- 실패 사유 패널 추가: cost gate fail, baseline underperform, invalid action, overtrade, low sample.
- 누적 수익 차트에는 model line, baseline line, no-trade line, episode boundary를 같이 표시.

## 추천 OMX 명령

```text
$ralph ts_imb RULE 전략의 사이징/리스크 설계를 구현하고 read-only forward 준비 상태를 대시보드에 표시해줘
```

또는 RL 실험을 계속할 경우:

```text
$ralph RL은 실험 분기로 격리하고 skip/enter/exit 제한형 모델에 baseline-relative reward, rolling OOS, model-vs-baseline dashboard comparison을 추가해줘
```

## 검증 메모

- 병렬 탐색 에이전트로 구조, RL 방향, dashboard, 테스트/빌드, 문서/핸드오프, anti-pattern을 점검했다.
- `git status` 기준 현재 브랜치는 `feature/stom-rl-lab`, 관찰 commit은 `943222b`.
- CodeGraph MCP 호출은 transport closed로 실패해 shell/agent/doc/artifact 기반으로 검토했다.
- 이 문서는 수익성 보증이 아니라 현재 코드/문서/실험 결과를 기준으로 한 개발 방향 판단이다.

## 2차 init-deep 재검토 메모

- 기존 AGENTS 계층은 유지한다: 루트, `stom_rl/`, `webui/`, `webui/v2_src/`, `finetune/`, `tests/`.
- `docs/`는 의사결정 장부 역할이 커서 별도 `docs/AGENTS.md`를 추가했다.
- AGENTS 파일은 도구/콘솔 인코딩 문제를 줄이기 위해 ASCII 중심 문구로 정리했다.
- 프런트엔드 지침에 Node 20/22, npm 9+ 조건을 명시했다.
- 현재 방향성 결론은 변하지 않았다: 수익 축은 `ts_imb` RULE, RL은 검증/반증용 실험 레이어다.
- 추가 위험: `RLTradingTab.svelte`의 `RL TRADING`, `DQN/PPO RL 모델` 같은 문구는 사용자가 “수익성 있는 RL 모델”로 오해할 수 있으므로 다음 UI 개선 때 실험/검증 라벨을 더 강하게 붙여야 한다.
