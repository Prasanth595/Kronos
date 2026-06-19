# STOM 강화학습 현재 브랜치 핸드오프 문서

작성일: 2026-05-24

대상 저장소: `D:\Chanil_Park\Project\Programming\Kronos`

현재 브랜치: `feature/stom-rl-lab`

이 문서 작성 직전 개발 HEAD: `a5b92a6 5070 대시보드가 강화학습 화면으로 바로 열리게 하다`

운영/확인 포트: `5070`

핵심 화면: `http://127.0.0.1:5070/rl`

이 문서는 새 Codex/OMX 대화를 만들어도 현재 브랜치 작업을 이어받을 수 있도록, 현재까지 완료된 내용, 검증 증거, 남은 위험, 다음 개발 순서, 추천 명령어를 한 곳에 모은 핸드오프 문서다.

---

## 1. 가장 중요한 결론

| 구분 | 현재 상태 |
|---|---|
| RL 플랫폼 페이지 진행률 | 100% |
| 웹 RL Lab 직접 진입 | `http://127.0.0.1:5070/rl` 정상 |
| `/api/rl/progress` | `overall_progress_pct=100`, `status=complete` |
| Gymnasium / Stable-Baselines3 연결 | 완료 |
| `StomTickTradingEnv` Gymnasium adapter | 완료 |
| `check_env` | 통과 |
| DQN smoke / short 학습 | 완료 |
| PPO smoke / short 학습 | 완료 |
| 50k DQN/PPO 학습 | 완료, leaderboard 반영 |
| Performance leaderboard | 완료, `dqn_50k` 1위 |
| 실전 모델 여부 | 아직 아님. 현재는 **실전 후보 모델** |
| 다음 핵심 | 학습량 확대보다 먼저 **저장 모델 eval-only / 평가 episode 확대 / walk-forward 검증** |

현재 웹과 RL 산출물 연결은 완료되어 있다. 다만 50k 모델의 평가 episode가 5개라서, 실거래 투입 전에는 더 긴 out-of-sample 평가와 walk-forward 검증이 필요하다.

---

## 2. 현재 브랜치와 최근 커밋 흐름

현재 브랜치:

```text
feature/stom-rl-lab
```

최근 주요 커밋:

| 커밋 | 의미 |
|---|---|
| `a5b92a6` | 5070에서 `/rl` 직접 진입, repo-root 기준 artifact 탐색, 최신 v2 dist 연결 수정 |
| `f362b65` | RL 페이지 완료율을 실제 학습 결과 기준 100%로 닫음 |
| `5bbb3a8` | STOM 강화학습 이벤트를 실시간 화면으로 연결 |
| `097e331` | STOM 실시간 강화학습 화면 계획 고정 |
| `58fbb9e` | SB3 smoke 학습 경로를 실제 검증 루프로 연결 |
| `dcd6dbc` | 강화학습 성과 모델 검증 기준 마무리 |
| `075cdd5` / `fd56218` | 성과 leaderboard를 웹에서 비교 가능하게 연결 |
| `0d9e52c` | contextual bandit full test 결과를 기준선과 비교 |

주의:

- `webui/rl_runs/*`는 런타임 산출물이며 대용량/재생성 가능 성격이다.
- 현재 git status에는 `.omc/*`, `template/`, `webui/stom_predictions/` 같은 untracked가 남아 있을 수 있다.
- 위 untracked는 이번 RL handoff 문서와 직접 관련 없는 사용자/런타임 파일로 취급하고, 임의로 삭제하거나 커밋하지 않는다.

---

## 3. 현재 웹 대시보드 상태

### 3.1 확인 URL

| 목적 | URL |
|---|---|
| 강화학습 실험실 직접 진입 | `http://127.0.0.1:5070/rl` |
| v2 통합 대시보드 | `http://127.0.0.1:5070/` |
| legacy v1 index | `http://127.0.0.1:5070/v1/` |
| legacy v1 training | `http://127.0.0.1:5070/v1/training` |
| legacy v1 STOM | `http://127.0.0.1:5070/v1/stom` |

`v2`는 새로 임의 생성한 프론트엔드가 아니라 기존 통합 대시보드의 정식 SPA 모드다. 기존 legacy 화면은 `/v1/*`로 보존되어 있다.

### 3.2 포트 정리

| 포트 | 상태 / 의미 |
|---:|---|
| 5070 | 현재 운영/확인 기준 포트 |
| 7070 | AnyDesk가 점유하는 경우가 있어 사용하지 않는 것이 안전 |
| 7072 | 이전 임시 확인 서버. 최종 안내 기준 아님 |

### 3.3 서버 실행 명령

PowerShell:

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos

$env:KRONOS_WEBUI_PORT = "5070"
$env:KRONOS_V2_DIST = "1"
$env:KRONOS_WEBUI_OPEN_BROWSER = "0"

py -3.11 webui\run.py
```

브라우저 열기:

```powershell
Start-Process "http://127.0.0.1:5070/rl"
```

API 확인:

```powershell
Invoke-RestMethod "http://127.0.0.1:5070/api/rl/progress" |
  ConvertTo-Json -Depth 8
```

기대값:

```text
overall_progress_pct = 100
status = complete
latest_sb3_run = stom_1s_2025_sb3_50k
max_sb3_training_timesteps = 50000
```

---

## 4. 페이지별 완료 상태

`/api/rl/progress` 기준 현재 완료 상태:

| 페이지 | 진행률 | 상태 | 주요 증거 |
|---|---:|---|---|
| RL Lab 개요 | 100% | complete | 10개 run 탐지, 상세 artifact 조회 가능 |
| 실시간 RL | 100% | complete | `rl_live_events.jsonl`, DQN/PPO event, 50k run |
| 실제 딥러닝 학습 | 100% | complete | `check_env`, CUDA 학습, DQN/PPO 모델 zip |
| Performance Leaderboard | 100% | complete | 13개 모델 row, DQN/PPO 50k 반영 |
| Artifacts / Models | 100% | complete | `dqn_model.zip`, `ppo_model.zip`, summary/csv/jsonl |
| Docs / 운영 경계 | 100% | complete | 구현 문서, 완료 보고 문서, 실주문 분리 |

현재 화면상에서 강화학습이 특별히 안 보인다면 `/` 기본 탭이 아니라 `/rl`로 직접 들어가야 한다.

---

## 5. 현재 RL 산출물과 모델 성과

현재 performance leaderboard summary:

| 항목 | 값 |
|---|---|
| row count | 13 |
| best policy | `stable_baselines3_dqn` |
| best RL model | `dqn_50k` |
| max SB3 training timesteps | 50,000 |
| 비용 기준 | cost `25bp`, slippage `0bp` |
| buy-and-hold 평균 episode 순수익 | `+0.5126%` |
| no-trade 평균 episode 순수익 | `0.0%` |
| buy-and-hold 초과 RL 모델 | `dqn_50k`, `ppo_50k`, `dqn_5k` |
| cost gate 통과 RL 모델 | `dqn_50k`, `ppo_50k`, `dqn_5k`, `ppo_5k` |

### 5.1 Leaderboard 상위 모델

| 순위 | 모델 | 학습량 | 평가 episode | 평균 episode 순수익 | 복리 수익 | Hit rate | Max DD | 판단 |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `dqn_50k` | 50,000 | 5 | `+1.6142%` | `+8.2825%` | 80.0% | `-5.1209%` | candidate |
| 2 | `ppo_50k` | 50,000 | 5 | `+1.5717%` | `+8.0648%` | 80.0% | `-5.1209%` | candidate |
| 3 | `dqn_5k` | 5,000 | 3 | `+0.5494%` | `+1.6558%` | 75.0% | `-3.2991%` | candidate |
| 4 | `buy_and_hold` | baseline | 2730 | `+0.5126%` | 매우 큼 | 49.3% | `-50.7280%` | baseline |
| 5 | `ppo_5k` | 5,000 | 3 | `+0.4040%` | `+1.2028%` | 66.7% | `-2.2514%` | watch |
| 6 | `contextual_bandit` | full test | 2730 | `+0.1254%` | `+1410.0169%` | 48.0% | `-51.5892%` | watch |
| 7 | `no_trade` | baseline | 2730 | `0.0%` | `0.0%` | 0.0% | `0.0%` | baseline |

해석:

- 현재 수치상 1위는 `dqn_50k`다.
- `ppo_50k`도 유사한 성과다.
- 하지만 50k DQN/PPO는 평가 episode가 5개뿐이라 실전 확정 근거로 부족하다.
- 따라서 현재 단계의 올바른 표현은 **실전 모델 구축 완료**가 아니라 **실전 후보 모델 구축 및 대시보드 연결 완료**다.

---

## 6. `k`의 의미와 현재 학습 단계

| 표기 | 의미 |
|---|---|
| `5k` | 5,000 environment timesteps |
| `50k` | 50,000 environment timesteps |
| `100k` | 100,000 environment timesteps |
| `500k` | 500,000 environment timesteps |
| `1M` | 1,000,000 environment timesteps |

`k`는 금액이나 캔들 개수가 아니라 강화학습 environment step 수다. 한 step은 대략 `상태 관측 -> action 선택 -> reward 계산 -> 다음 상태 이동` 1회다.

현재 위치:

| 구분 | 현재 상태 |
|---|---|
| smoke 학습 | 완료 |
| 5k 미니 학습 | 완료 |
| 50k short 학습 | 완료 |
| 100k 학습 | 미실행 |
| 500k 학습 | 미실행 |
| 1M 학습 | 미실행 |
| multi-seed 검증 | 미실행 |
| walk-forward 검증 | 미실행 |
| paper trading/replay | 미실행 |

---

## 7. 현재 구현 파일 지도

| 영역 | 파일 / 위치 | 역할 |
|---|---|---|
| STOM RL core | `stom_rl/trading_env.py` | 순수 STOM tick trading env |
| Gymnasium/SB3 adapter | `stom_rl/sb3_adapter.py` | `StomTickTradingGymEnv`, `make_sb3_env` |
| SB3 학습 | `stom_rl/sb3_smoke.py` | `check_env`, DQN/PPO 학습, 모델 저장, live event 기록 |
| 실시간 이벤트 | `stom_rl/rl_events.py` | `RlLiveEvent`, JSONL writer/reader/summary |
| 기준선 | `stom_rl/baselines.py`, `stom_rl/leaderboard.py` | no-trade, buy-and-hold, random 등 baseline |
| contextual bandit | `stom_rl/contextual_bandit.py` | contextual bandit 학습/평가 |
| 성과 통합 | `stom_rl/performance_leaderboard.py` | baseline, bandit, SB3 결과 통합 leaderboard |
| RL API helper | `webui/rl_dashboard.py` | `webui/rl_runs` artifact read-only loader, progress 계산 |
| Flask routes | `webui/app.py` | `/api/rl/*` route wiring |
| v2 route alias | `webui/v2/__init__.py` | `/`, `/training`, `/dashboard`, `/rl`, `/rl-lab` shell 서빙 |
| v2 app route tab | `webui/v2_src/src/App.svelte` | `/rl` 진입 시 `rl-lab` 탭 선택 |
| RL Lab UI | `webui/v2_src/src/tabs/RLLabTab.svelte` | run 선택, live event, leaderboard, artifacts 표시 |
| v2 build output | `webui/static/v2/dist/*` | `KRONOS_V2_DIST=1`에서 서빙되는 SPA 산출물 |

---

## 8. 이미 검증한 명령

최근 검증된 명령:

```powershell
py -3.11 -m pytest tests\test_stom_rl_dashboard_api.py -q
```

결과: `3 passed`

```powershell
py -3.11 -m ruff check webui\rl_dashboard.py webui\v2\__init__.py
```

결과: `All checks passed!`

```powershell
cd webui\v2_src
npm run build
```

결과: `0 errors`, 기존 warning 4개 유지

HTTP 확인:

```powershell
Invoke-RestMethod "http://127.0.0.1:5070/api/rl/progress"
Invoke-WebRequest "http://127.0.0.1:5070/"
Invoke-WebRequest "http://127.0.0.1:5070/rl"
```

확인값:

```text
/api/rl/progress -> overall_progress_pct=100, status=complete
/                -> 200, 최신 dist bundle index-D0ThkgbJ.js
/rl              -> 200, 최신 dist bundle index-D0ThkgbJ.js
```

---

## 9. 다음 개발 목표: 실전 후보 검증 단계

가장 중요한 다음 단계는 더 긴 학습을 바로 돌리는 것보다 **저장된 50k 모델을 더 많은 episode로 eval-only 재평가**하는 것이다.

### 9.1 추천 순서

| 순서 | 작업 | 이유 | 완료 기준 |
|---:|---|---|---|
| 1 | `sb3_eval` 또는 eval-only 모드 추가 | 현재 50k 평가는 episode 5개라 근거 부족 | 저장된 zip 모델을 재학습 없이 50/100/500 episode 평가 |
| 2 | 50k DQN/PPO full eval | 성능이 우연인지 확인 | leaderboard에 eval-only row 반영 |
| 3 | 100k DQN/PPO 학습 | 짧은 확장으로 성능 추세 확인 | 모델 zip, summary, live events 생성 |
| 4 | 250k/500k multi-seed 학습 | 안정성 확인 | seed별 평균/분산 표시 |
| 5 | walk-forward split | 과최적화 방지 | 월별 또는 기간별 train/test 분리 결과 |
| 6 | RL Lab UI에서 training/eval 분리 | 화면 해석 혼동 방지 | 학습 run과 평가 run을 별도 badge/table로 표시 |
| 7 | paper trading/replay | 실시간처럼 보되 실주문 없음 | live replay 화면, risk gate 표시 |
| 8 | 위험관리 gate | 실전 전 필수 | Max DD, 연속손실, 거래횟수, 비용 민감도 기준 |

### 9.2 다음 단계 진행률 정의

| 단계 | 현재 진행률 | 100% 기준 |
|---|---:|---|
| 저장 모델 eval-only | 0% | `dqn_model.zip`, `ppo_model.zip`을 재학습 없이 평가하는 CLI/API/테스트 |
| 50k full eval | 0% | 평가 episode 100개 이상, leaderboard 반영 |
| 100k 학습 | 0% | DQN/PPO 100k run, summary/event/model 파일 생성 |
| 500k 학습 | 0% | DQN/PPO 500k run, seed 2개 이상 |
| walk-forward | 0% | 기간 분할, 결과 표, dashboard 표시 |
| 실전 risk gate | 20% | cost gate는 있으나 실전 DD/연속손실/거래빈도 gate 필요 |
| paper replay | 0% | 실시간 replay UI와 read-only execution simulation |

---

## 10. 추천 실행 명령

### 10.1 현재 상태 재확인

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos

git branch --show-current
git log --oneline -5
git status --short
```

### 10.2 의존성 확인

PowerShell:

```powershell
py -3.11 -c "import torch, gymnasium, stable_baselines3; print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); print('gymnasium', gymnasium.__version__); print('stable_baselines3', stable_baselines3.__version__)"
```

### 10.3 100k DQN 학습

```powershell
py -3.11 -m stom_rl.sb3_smoke `
  --output-dir webui\rl_runs\stom_1s_2025_sb3_dqn_100k `
  --algorithms dqn `
  --total-timesteps 100000 `
  --max-eval-episodes 20 `
  --max-eval-steps-per-episode 2048 `
  --device cuda `
  --live-event-sample-interval 50
```

### 10.4 100k PPO 학습

```powershell
py -3.11 -m stom_rl.sb3_smoke `
  --output-dir webui\rl_runs\stom_1s_2025_sb3_ppo_100k `
  --algorithms ppo `
  --total-timesteps 100000 `
  --max-eval-episodes 20 `
  --max-eval-steps-per-episode 2048 `
  --device cuda `
  --live-event-sample-interval 50
```

### 10.5 Leaderboard 갱신

```powershell
py -3.11 -m stom_rl.performance_leaderboard --sb3-smoke-reports auto
```

### 10.6 대시보드 새로 확인

```powershell
Invoke-RestMethod "http://127.0.0.1:5070/api/rl/progress" |
  ConvertTo-Json -Depth 8

Start-Process "http://127.0.0.1:5070/rl"
```

### 10.7 테스트 묶음

```powershell
py -3.11 -m pytest `
  tests\test_stom_rl_sb3_adapter.py `
  tests\test_stom_rl_dashboard_api.py `
  tests\test_stom_rl_dashboard_tab.py `
  tests\test_stom_rl_performance_leaderboard.py `
  -q

py -3.11 -m ruff check stom_rl webui\rl_dashboard.py webui\v2\__init__.py
```

프론트 수정 후:

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src
npm run build
```

---

## 11. 예상 학습 시간

현재 실측 기준:

| 모델 | 50k 실측 | 100k 예상 | 500k 예상 | 1M 예상 |
|---|---:|---:|---:|---:|
| DQN | 약 5.1분 | 약 10~15분 | 약 50~70분 | 약 1.7~2.3시간 |
| PPO | 약 6.0분 | 약 12~18분 | 약 60~85분 | 약 2~2.8시간 |
| DQN+PPO 합산 | 약 11분 | 약 25~35분 | 약 2~2.5시간 | 약 4~5시간 |

실전 후보까지 추천 기준:

| 수준 | 추천 실행 |
|---|---|
| 빠른 확인 | 100k, seed 1개 |
| 후보 비교 | 250k~500k, seed 3개 |
| 실전 후보 | 1M, seed 3~5개 |
| 운영 전 검증 | walk-forward + paper replay + risk gate |

---

## 12. OMX 사용 추천

현재 사용자가 일반 git commit 방식을 선호했으므로, `ultragoal checkpoint`는 사용하지 않는 것이 안전하다. 계획/검증에는 OMX skill을 사용할 수 있지만 최종 마무리는 일반 git commit으로 한다.

추천 흐름:

```text
$ralplan STOM RL 50k 후보 모델을 실전 후보로 승격하기 위한 eval-only, 100k/500k 학습, walk-forward, dashboard 표시 계획 작성
```

```text
$team sb3_eval 추가, leaderboard 확장, RL Lab 화면 개선, 테스트/문서화를 병렬 진행
```

```text
$ultraqa http://127.0.0.1:5070/rl RL Lab 대시보드와 /api/rl/* 표시 검증
```

```text
$code-review STOM RL 실전 후보 학습/평가/대시보드 변경분 리뷰
```

Windows 현재 환경에서는 `omx explore`가 POSIX shell allowlist harness 문제로 실패할 수 있다. 그 경우 `rg`, `Get-ChildItem`, `pytest`, `ruff`, `npm run build` 같은 일반 PowerShell 명령으로 진행한다.

---

## 13. 다음 대화 시작용 프롬프트

새 대화에서 아래 프롬프트를 그대로 붙여넣으면 이어서 진행하기 쉽다.

```text
D:\Chanil_Park\Project\Programming\Kronos 에서 이어서 진행합니다.
현재 브랜치는 feature/stom-rl-lab 입니다.
먼저 docs/stom_rl_current_branch_handoff_2026-05-24.md 를 읽고 이어서 작업해주세요.

중요 조건:
- ultragoal checkpoint는 사용하지 말고 일반 git commit으로 마무리합니다.
- 운영/확인 포트는 5070입니다.
- 강화학습 화면은 http://127.0.0.1:5070/rl 기준입니다.
- 7070은 AnyDesk 점유 가능성이 있어 사용하지 않습니다.
- 7072는 임시 서버였으므로 최종 기준으로 안내하지 않습니다.

현재 완료 상태:
- RL Lab 페이지 진행률 100%
- /api/rl/progress overall_progress_pct=100, status=complete
- Gymnasium/SB3 연결 완료
- StomTickTradingEnv adapter 완료
- check_env 통과
- DQN/PPO smoke, 5k, 50k 학습 완료
- performance leaderboard 연결 완료
- 현재 best model은 dqn_50k 이지만 평가 episode가 5개라 실전 확정 모델은 아닙니다.

다음 목표:
1. 저장된 DQN/PPO 50k 모델을 재학습 없이 full eval 하는 sb3_eval 또는 eval-only 모드 추가
2. 평가 episode 50/100/500개로 확대
3. eval-only 결과를 performance leaderboard와 RL Lab에 training 결과와 분리 표시
4. 이후 DQN/PPO 100k -> 500k -> 1M multi-seed 학습 계획/구현
5. walk-forward 검증과 paper replay/risk gate까지 확장
6. 테스트 후 한국어 Lore commit
```

---

## 14. 위험과 주의사항

| 위험 | 설명 | 대응 |
|---|---|---|
| 평가 표본 부족 | 50k DQN/PPO는 episode 5개 평가라 실전 근거 부족 | eval-only full evaluation 먼저 구현 |
| leaderboard 해석 혼동 | 학습 run 결과와 eval-only 결과가 섞이면 오해 가능 | run category/badge 분리 |
| 과최적화 | 동일 split 반복 학습/평가 가능성 | walk-forward split 추가 |
| 실주문 오해 | 현재 RL Lab은 read-only historical replay/smoke-short training | paper replay와 실주문 분리 문구 유지 |
| 포트 혼동 | 7070/7072 혼동 이력 | 5070 `/rl`만 최종 기준으로 안내 |
| Windows OMX explore | `omx explore` harness 실패 가능 | PowerShell/rg/pytest로 대체 |

---

## 15. 완료 정의

다음 큰 단계인 “실전 후보 검증 모델” 완료 기준:

- 저장된 `dqn_model.zip`, `ppo_model.zip`을 재학습 없이 평가 가능
- 평가 episode 100개 이상 결과 생성
- `dqn_50k`, `ppo_50k`가 eval-only 결과에서도 buy-and-hold/no-trade 기준을 안정적으로 초과하는지 확인
- leaderboard가 training 결과와 eval-only 결과를 분리 표시
- `/rl`에서 선택 run의 학습/평가/실시간 이벤트를 명확히 볼 수 있음
- `pytest`, `ruff`, 필요 시 `npm run build` 통과
- 한국어 Lore commit 완료
