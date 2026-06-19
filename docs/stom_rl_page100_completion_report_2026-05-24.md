# STOM RL ?꾩껜/?섏씠吏蹂?100% ?꾨즺 蹂닿퀬

?묒꽦?? 2026-05-24 KST
釉뚮옖移? `feature/stom-rl-lab`
湲곗? 而ㅻ컠 ???곹깭: `5bbb3a8 STOM 媛뺥솕?숈뒿 ?대깽?몃? ?ㅼ떆媛??붾㈃?쇰줈 ?뉖떎`

## ?꾨즺 ?붿빟

?ㅼ떆媛?STOM 媛뺥솕?숈뒿 ?쒓컖??MVP瑜??ㅼ젣 DQN/PPO mini/short ?숈뒿 ?곗텧臾쇨퉴吏 ?뺤옣?덈떎. `stom_rl.sb3_smoke`濡?CUDA 湲곕컲 DQN/PPO ?숈뒿??5k? 50k ?④퀎濡??ㅽ뻾?덇퀬, ?앹꽦??live event/model/summary artifact瑜?RL API, RL Lab 吏꾪뻾瑜? performance leaderboard???곌껐?덈떎.

> ?덉쟾 寃쎄퀎: ??寃곌낵??historical replay / smoke-short training 寃利앹씠硫??ㅼ＜臾? ?먮룞留ㅻℓ, paper/live execution ?곌껐???꾨땲??

## ?꾩껜 吏꾪뻾瑜?
| ?곸뿭 | 吏꾪뻾瑜?| ?꾨즺 利앷굅 |
|---|---:|---|
| ?꾩껜 RL ?섏씠吏 ?꾨즺??| 100% | `/api/rl/progress` 湲곗? 紐⑤뱺 ?섏씠吏 criteria ?듦낵 |
| ?ㅼ젣 ?λ윭???숈뒿 吏꾪뻾 | 100% | DQN/PPO 5k mini + 50k short CUDA ?숈뒿 ?꾨즺 |
| ?ㅼ떆媛??대깽???쒓컖??| 100% | `rl_live_events.jsonl`, `/api/rl/runs/<run>/events`, RL Lab ?ㅼ떆媛?RL ??|
| Leaderboard ?곌껐 | 100% | `dqn_50k`, `ppo_50k`, `dqn_5k`, `ppo_5k`, smoke 紐⑤뜽 ?먮룞 吏묎퀎 |
| 寃利?臾몄꽌??| 100% | pytest/ruff/mypy/npm build/API smoke + 蹂?臾몄꽌 |

## ?섏씠吏蹂?吏꾪뻾瑜?
| ?섏씠吏/?곸뿭 | 吏꾪뻾瑜?| ?꾨즺 湲곗? |
|---|---:|---|
| RL Lab 媛쒖슂 | 100% | run 紐⑸줉, artifact ?좏삎, ?곸꽭 artifact 議고쉶 媛??|
| ?ㅼ떆媛?RL | 100% | live event log, DQN/PPO event, 50k short run ?뺤씤 |
| ?ㅼ젣 ?λ윭???숈뒿 | 100% | `check_env`, CUDA, DQN/PPO model zip ?뺤씤 |
| Performance Leaderboard | 100% | 13 rows, `dqn_50k`/`ppo_50k` short model 諛섏쁺 |
| Artifacts / Models | 100% | summary/csv/jsonl 諛?DQN/PPO zip ?앹꽦 |
| Docs / ?댁쁺 寃쎄퀎 | 100% | 援ы쁽 臾몄꽌 + ?꾨즺 蹂닿퀬 + read-only ?덉쟾 寃쎄퀎 |

## ?ㅼ젣 ?숈뒿 ?곗텧臾?
| run | timesteps | event count | 紐⑤뜽 | ?듭떖 寃곌낵 |
|---|---:|---:|---|---|
| `stom_1s_2025_sb3_5k` | 5,000 | 5,083 | DQN/PPO | DQN avg episode net 0.5494%, PPO 0.4040% |
| `stom_1s_2025_sb3_50k` | 50,000 | 10,000 tail summary | DQN/PPO | DQN avg episode net 1.6142%, PPO 1.5717% |

?앹꽦 ?뚯씪 ?덉떆:

```text
webui/rl_runs/stom_1s_2025_sb3_50k/dqn_model.zip
webui/rl_runs/stom_1s_2025_sb3_50k/ppo_model.zip
webui/rl_runs/stom_1s_2025_sb3_50k/rl_live_events.jsonl
webui/rl_runs/stom_1s_2025_sb3_50k/rl_live_summary.json
webui/rl_runs/stom_1s_2025_sb3_50k/sb3_smoke_summary.json
```

## Leaderboard 寃곌낵

`stom_rl.performance_leaderboard`???댁젣 湲곕낯媛믪쑝濡?`webui/rl_runs/stom_1s_2025_sb3*/sb3_smoke_summary.json`瑜??먮룞 ?먯깋?쒕떎.

| ?쒖쐞沅?| 紐⑤뜽 | run | timesteps | ?곹깭 |
|---:|---|---|---:|---|
| 1 | `dqn_50k` | `stom_1s_2025_sb3_50k` | 50,000 | candidate |
| 2 | `ppo_50k` | `stom_1s_2025_sb3_50k` | 50,000 | candidate |
| 3 | `dqn_5k` | `stom_1s_2025_sb3_5k` | 5,000 | candidate |
| 5 | `ppo_5k` | `stom_1s_2025_sb3_5k` | 5,000 | watch |

## 異붽???API

```text
GET /api/rl/progress
```

諛섑솚 紐⑹쟻:

- ?꾩껜 吏꾪뻾瑜?`overall_progress_pct`
- ?섏씠吏蹂?吏꾪뻾瑜?`pages[].progress_pct`
- ?섏씠吏蹂??꾨즺 criteria/evidence
- 理쒖떊 SB3 run, 理쒕? timesteps, leaderboard 紐⑤뜽 利앷굅

## 寃利?紐낅졊

```powershell
py -3.11 -m stom_rl.sb3_smoke --output-dir webui\rl_runs\stom_1s_2025_sb3_5k --total-timesteps 5000 --max-eval-episodes 3 --max-eval-steps-per-episode 512 --device cuda --live-event-sample-interval 5
py -3.11 -m stom_rl.sb3_smoke --output-dir webui\rl_runs\stom_1s_2025_sb3_50k --total-timesteps 50000 --max-eval-episodes 5 --max-eval-steps-per-episode 1024 --device cuda --live-event-sample-interval 50
py -3.11 -m stom_rl.performance_leaderboard
py -3.11 -m pytest tests -q
py -3.11 -m ruff check stom_rl\performance_leaderboard.py webui\rl_dashboard.py webui\app.py tests\test_stom_rl_performance_leaderboard.py
py -3.11 -m mypy stom_rl\performance_leaderboard.py webui\rl_dashboard.py --ignore-missing-imports
cd webui\v2_src; npm run build
```

## ?⑥? 由ъ뒪??
| 由ъ뒪??| ?곹깭 | ?ㅼ쓬 ?④퀎 |
|---|---|---|
| ?μ떆媛?200k~1M ?숈뒿 | 蹂대쪟 | 50k ?덉젙????蹂꾨룄 long-run goal |
| ?ㅼ떆媛?push streaming | 蹂대쪟 | JSONL polling ?덉젙????SSE/WebSocket 寃??|
| ?ㅼ＜臾?paper trading | ?쒖쇅 | 蹂꾨룄 ?덉쟾 ?뱀씤/由ъ뒪??寃뚯씠???꾩슂 |
| browser-use ?쒓컖 罹≪쿂 | ?꾧뎄 媛?⑹꽦 ?섏〈 | in-app browser tool ?몄텧 ??異붽? 罹≪쿂 |