# AI 핸드오프 — STOM tokenizer 재학습 (옵션 D) + 대시보드 모니터링

> **이 문서 하나로 다른 AI 세션이 사용자의 재학습 작업을 그대로 이어받아 진행할 수 있다.** 코드 변경, 변수 선정 근거, 명령어, 예상 시간, 위험 대응, 다음 단계까지 단일 파일에 정리됨.

**작성일**: 2026-05-19 KST
**작성자**: Claude (이전 세션)
**상태**: 코드/대시보드 준비 완료, **사용자가 학습 명령 실행 직전**
**대상 AI**: 이 문서를 받은 다음 Claude 세션
**프로젝트**: `D:\Chanil_Park\Project\Programming\Kronos`

---

## 0. 30초 컨텍스트

- **무엇을 하나**: validation OOM 으로 실패한 STOM tokenizer 학습을 옵션 D (풀 최대 활용) 변수로 재시작하고, v2 대시보드에서 실시간 모니터링.
- **왜**: 이전 학습 99.98% (step 4.7M 거의 끝) 에서 validation forward OOM → checkpoint 0개 → predictor 미시작 → STOM 예측 진단/Forecast 워크벤치 검증 불가.
- **무엇이 준비됐나**: finetune 코드에 AMP/torch.compile/persistent_workers opt-in flag 추가 (commit `dc7315a`), W9 로그 tail 위젯 추가 (commit `0563734`).
- **남은 1단계**: 사용자가 §4 명령어를 별도 PowerShell 콘솔에 붙여넣고 실행. 보정된 명령은 이전 실패 run 과 동일한 `n-train-iter=18806883`, `n-val-iter=3925397` 및 predictor 고속 설정을 포함한다. 옵션 D 성공 시 6~12시간 목표, 보수적으로 8~16시간 후 학습 종료 예상.

---

## 1. 시스템 사양 (실측 — 변수 선정 근거)

| 자원 | 값 |
|---|---|
| **CPU** | AMD Ryzen Threadripper 3990X · 32 cores / 64 logical threads |
| **GPU** | NVIDIA RTX 4080 SUPER · 16 GiB VRAM (free 12.4 GiB) · driver 591.86 |
| **System RAM** | 273 GB |
| **PyTorch** | 2.9.0 + CUDA 12.8 |
| **GPU arch** | Ada Lovelace (sm_89) — bf16 native 지원 |
| **OS** | Windows 11 |
| **Python** | C:\Python\64\Python3119\python.exe (3.11.13) |
| **Disk D:** | 1.9 TB / 528 GB free |

---

## 2. 이전 실패 진단

| 항목 | 값 |
|---|---|
| 실패 commit | `7742cb8` — "장시간 tokenizer 학습 결과를 validation OOM 전에 보존하다" |
| 마지막 step | **4,701,000 / 4,701,721** = 99.98% (train loop 거의 완료) |
| OOM 위치 | `finetune/train_tokenizer.py:196` rotary attention forward (validation 진입 직전 또는 직후) |
| 학습 시간 | 약 83시간 (2026-05-11 04:43 → 2026-05-14 15:39) |
| 체크포인트 | **0개** (pre_validation_checkpoint 코드는 line 201 에 있으나 OOM 이 그 전에 발생) |
| 안전 옵션 추가 | commit `7742cb8` 에서 `--tokenizer-val-batch-size`, `latest_train_model` 자동 저장, CUDA cache 정리, validation_failure.json 기록 |

---

## 3. 본 세션에서 추가된 작업

### 3.1 finetune 코드 — 옵션 C/D opt-in flag 도입 (commit `dc7315a`)

`finetune/config.py` 신규 attribute 5종 + KRONOS_* 환경변수 5종:
- `persistent_workers` / `prefetch_factor`
- `tokenizer_enable_amp` / `tokenizer_amp_dtype` (bf16/fp16/fp32)
- `tokenizer_enable_compile` / `tokenizer_compile_mode` / `tokenizer_compile_fullgraph`

`finetune/train_tokenizer.py` 적용:
- DataLoader 에 `persistent_workers`/`prefetch_factor` (num_workers > 0 일 때만)
- `autocast_ctx()` 컨텍스트 매니저 (AMP 비활성 시 nullcontext)
- train forward + loss 를 autocast 로 래핑
- GradScaler (fp16 일 때만 — bf16 은 불필요)
- validation forward 도 autocast 로 래핑
- 모델 생성 직후 `torch.compile()` 적용 (try/except 로 실패 시 eager fallback)

`finetune/run_stom_1s_finetune.py` CLI args 7종 추가:
- `--persistent-workers` / `--prefetch-factor`
- `--tokenizer-amp` / `--tokenizer-amp-dtype`
- `--tokenizer-compile` / `--tokenizer-compile-mode` / `--tokenizer-compile-fullgraph`
- 옵션 활성 시 자동 env 전파 (KRONOS_* 환경변수)

**모든 옵션은 opt-in (default False) — 기존 학습 명령은 영향 없음.**

### 3.2 대시보드 — W9 로그 tail 위젯 (commit `0563734`)

`webui/v2_src/src/widgets/W9_LogTail.svelte` 신규:
- `/api/training/logs?stage=<>&lines=N` 폴링 (10초 주기)
- 색상 분기: **Loss=시안**, **LR=주황**, **sps/checkpoint=초록**, **step=흰**, **compile=시안진**, **AMP=초록**, **error/OOM=빨강**
- 10/20/50 tail 토글
- Live Training 탭 하단 (W5 GPU 다음) 자동 노출
- 신규 API endpoint 0건 (기존 `/api/training/logs` 활용)

### 3.3 테스트 갱신
`tests/test_training_monitor.py` P6 cutover 경로 갱신 (`/training` → `/v1/training`).

### 3.4 runbook 갱신
`docs/retrain_stom_1s_grid_pred60_2025_full_small.md` §2.1 옵션 D 명령어 + §2.1a 대시보드 검증 흐름 + §2.1b 폴백 옵션 추가.

---

## 4. 학습 시작 명령 (사용자가 별도 PowerShell 콘솔에 붙여넣기)

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos

# 1. 실패 run archive (기존 logs 보존)
Rename-Item -Path 'finetune\outputs\stom_1s_grid_pred60_2025_full_small' -NewName 'stom_1s_grid_pred60_2025_full_small_failed_OOM_20260514'

# 2. validation OOM 회피 (필수)
$env:KRONOS_TOKENIZER_VAL_BATCH_SIZE = "1"

# 3. 옵션 D 풀 최대 활용 학습 시작
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 --mode full --train-stage both `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_2025_full_small `
  --dataset-sample-mode full_sequential `
  --n-train-iter 18806883 `
  --n-val-iter 3925397 `
  --tokenizer-batch-size 64 `
  --tokenizer-val-batch-size 1 `
  --predictor-batch-size 16 `
  --predictor-num-workers 2 `
  --epochs 1 `
  --num-workers 12 `
  --persistent-workers `
  --prefetch-factor 6 `
  --tokenizer-amp `
  --tokenizer-amp-dtype bf16 `
  --tokenizer-compile `
  --tokenizer-compile-mode max-autotune
```

### 4.1 변수 선정 근거

| 변수 | 값 | 근거 |
|---|---:|---|
| `--tokenizer-batch-size` | **64** | AMP bf16 으로 VRAM ~12 GiB (4 GiB 안전 마진) |
| `--num-workers` | **12** | 64-core 중 19% 활용 — 데이터 로딩 충분 |
| `--prefetch-factor` | **6** | RAM 273 GB 이라 부담 0 |
| `--persistent-workers` | ✅ | DataLoader 재초기화 비용 ↓ |
| `--tokenizer-amp-dtype` | **bf16** | 4080 SUPER native + GradScaler 불필요 |
| `--tokenizer-compile-mode` | **max-autotune** | 6~12시간 목표 학습이라 컴파일 오버헤드 (~120s) ROI 충분 |
| `--tokenizer-val-batch-size` | **1** | validation OOM 회피 (env 강제) |

---

## 5. 예상 타임라인 (옵션 D)

| 구간 | 시간 | 누적 |
|---|---:|---:|
| 명령 실행 → 첫 step 진입 | ~30s | 30s |
| **torch.compile max-autotune 1st epoch** | ~60~180s | ~3분 |
| tokenizer train loop (약 294k step, batch 64, train 18,806,883 samples) | ~5~10h | ~5~10h |
| tokenizer validation (batch=1, val 3,925,397 samples) | ~30~120min | ~6~12h |
| predictor train loop | ~1~4h (batch 16 + num_workers 2) | ~7~16h |
| predictor validation | ~10~30min | ~7~16h |
| **총 예상** | | **6~12h 목표 / 8~16h 보수** |

기존 83h 대비 **약 5~14x faster 목표**. 실제 ETA는 첫 5~10분 sps 실측으로 재계산한다.

---

## 6. 대시보드 모니터링 흐름

### 6.1 학습 시작 직후 즉시 확인 (브라우저)

`http://127.0.0.1:5070/` → 좌측 NAV "실시간 학습" 탭 → 하단으로 스크롤 → **W9 학습 로그 tail** 카드:

| 시점 | 보이는 줄 (색상) |
|---|---|
| 1분 | `[Rank 0] BATCHSIZE (per GPU): 64` |
| 1분 | `[Rank 0] AMP enabled — dtype=bf16 scaler=False` (초록) |
| 1분 | `[Rank 0] torch.compile enabled — mode=max-autotune fullgraph=False` (시안) |
| 3분 후 | `[Rank 0, Epoch 1/1, Step N/294000] LR 0.00X (주황), Loss: -0.XX (시안)` |
| 학습 중 | `samples/s=500~700 (초록)` |
| OOM 발생 시 | `out of memory / Traceback (빨강 강조)` |
| checkpoint 저장 시 | `checkpoint saved / pre-validation epoch 1 (초록)` |

### 6.2 옵션 D 작동 신호 — 메트릭 카드

- **현재 손실**: 시안 색상 (정상)
- **학습 속도**: **500~700 samples/s** (이전 옵션 C 의 5배+, 기존 batch 4 의 10배+)
- **학습률 (LR)**: 주황 색상, scheduled
- **현재 Epoch**: 1/1

### 6.3 GPU 트렌드 (W5)
- util 90%+ 도달 → 자원 풀가동 신호
- VRAM ~12 GiB / 16 GiB ~ 75% → 옵션 D batch 64 정상
- 온도 ~60~70°C (학습 부하 적정)

### 6.4 ETA (W2/W4)
- 학습 시작 5~10분 후 **6~12시간 목표 / 8~16시간 보수** 범위 표시 → 옵션 D 작동
- KST 완료 예상 시각 자동 표시

---

## 7. 위험 + 대응

| 위험 | 신호 | 대응 |
|---|---|---|
| batch 64 → train OOM | W9 에 빨간 `out of memory` | 즉시 학습 중단 → §7.1 옵션 폴백 |
| torch.compile max-autotune 실패 | W9 에 주황 `torch.compile failed` | 자동 eager fallback (학습 계속) — 또는 §7.2 |
| compile 컴파일 너무 오래 (~5분+) | W9 에 step 증가 안 함 | `--tokenizer-compile-mode reduce-overhead` 로 변경 |
| validation OOM 재발 | tokenizer.stdout.log 에 OOM | pre_validation `latest_train_model` weights 자동 보존됨 — 별도 PR 로 복구 |
| GPU 다른 프로세스 점유 | nvidia-smi 에 다른 PID | 해당 프로세스 종료 후 재시작 |

### 7.1 옵션 D OOM 시 폴백 (runbook §2.1b)
```powershell
# 옵션 B 수준 (안전)
... --tokenizer-batch-size 16 --num-workers 4 --persistent-workers --tokenizer-amp --tokenizer-amp-dtype bf16
# torch.compile 제거, batch 4분의 1
```

### 7.2 max-autotune 실패 시
```powershell
... --tokenizer-compile-mode reduce-overhead   # max-autotune → reduce-overhead
```

---

## 8. 학습 종료 후 다음 단계

학습이 성공적으로 끝나면 (`/api/training/status` 가 `status=completed` + `readiness.predictor_complete=true`):

1. **v2 대시보드 자동 갱신** — 모든 탭이 새 predictor 데이터로 채워짐
2. **예측 워크벤치 탭** — 새 모델로 실제 예측 실행 가능
3. **예측 진단 (STOM) 탭** — 새 prediction CSV 가 file 목록에 자동 노출
4. **아티팩트 & 모델 탭** — checkpoint/weight 카운트 정상 표시
5. **P5 정식 quality gate** — Lighthouse a11y/perf 측정 (docs/session-wrap-followups-2026-05-18.md §2 참조)

---

## 9. 핵심 commit 추적 (시간순)

| Commit | 설명 |
|---|---|
| `7742cb8` | 이전 OOM 실패 + 안전 옵션 추가 (--tokenizer-val-batch-size 등) |
| `908766c` | 재학습 runbook 정식 docs 고정 |
| `dc7315a` | tokenizer 재학습 풀 최적화 — torch.compile + bf16 AMP + persistent workers 옵션 도입 |
| `0563734` | **옵션 D 풀 활용 + W9 로그 tail 카드로 대시보드 가시성 완성** ← 본 세션 핵심 |

---

## 10. 다른 AI 가 작업 이어가기 (재진입 절차)

### 10.1 새 AI 세션 시작 시 첫 명령

```powershell
# 1. 본 핸드오프 문서 읽기 (필수)
# (Read tool 사용)
# D:\Chanil_Park\Project\Programming\Kronos\docs\ai_handoff_retrain_option_d_2026-05-19.md

# 2. git 히스토리 확인 — 본 세션 마지막 commit 도달했는지
cd D:\Chanil_Park\Project\Programming\Kronos
git log --oneline -5
# 마지막 commit 이 0563734 (옵션 D + W9) 인지 확인

# 3. 작업 디렉터리 클린 상태 확인
git status --short

# 4. 학습 진행 상태 확인 (Flask 가 떠있는지)
curl -s -o NUL -w "HTTP=%{http_code}\n" http://127.0.0.1:5070/

# 5. Flask 가 죽었으면 재시작
$env:KRONOS_WEBUI_PORT = "5070"
$env:KRONOS_WEBUI_OPEN_BROWSER = "0"
$env:KRONOS_V2_DIST = "1"
C:\Python\64\Python3119\python.exe webui\run.py
# (별도 콘솔에서 실행 — 백그라운드 유지)

# 6. 학습 진행 상태 (API 직접 호출)
curl -s http://127.0.0.1:5070/api/training/status | python -m json.tool
```

### 10.2 학습이 아직 시작 안 됐다면

본 문서 §4 명령어를 사용자에게 안내. 사용자가 별도 PowerShell 콘솔에 붙여넣고 실행.

### 10.3 학습이 진행 중이라면

- W9 로그 tail 카드 확인 → AMP/compile 활성 정상인지 검증
- 메트릭 카드의 sps 가 500+ 인지 확인 → 옵션 D 작동 신호
- ETA 6~12시간 목표 또는 8~16시간 보수 범위 표시 확인
- 사용자에게 진행률 보고

### 10.4 학습이 실패했다면 (OOM 등)

- `finetune/outputs/stom_1s_grid_pred60_2025_full_small/logs/tokenizer.stdout.log` tail 확인
- §7.1 옵션 B 폴백 명령 제시 (batch 16, no compile)
- 또는 §7.2 compile mode reduce-overhead 변경

### 10.5 학습이 성공했다면

- §8 다음 단계 진행 (예측 워크벤치 검증 → STOM 진단 → P5 quality gate)
- 별도 PR 로 P3.5 (Forecast Candlestick), P4.5 (STOM Plotly heatmap) 진행 — `docs/session-wrap-followups-2026-05-18.md` 참조

---

## 11. 주요 참조 문서 색인

| 파일 | 용도 |
|---|---|
| `docs/ai_handoff_retrain_option_d_2026-05-19.md` | **본 문서** (AI 핸드오프) |
| `docs/retrain_stom_1s_grid_pred60_2025_full_small.md` | 재학습 runbook (옵션 D 명령 + 모니터링 + 폴백) |
| `docs/claude_designer_handoff.md` | v2 SPA 디자이너 핸드오프 (전체 8 탭 구조) |
| `docs/kronos_dashboard_overhaul_plan.md` | P0~P6 ralplan 합의 마스터 플랜 |
| `docs/session-wrap-followups-2026-05-18.md` | 11개 후속 작업 우선순위 |
| `.omc/skill-candidates.md` | 6 재사용 패턴 (skillify 후보) |
| `webui/v2_src/README.md` | v2 SPA 빌드/배포/디렉터리 |

---

## 12. 절대 금지 사항 (Hard Constraints)

| 영역 | 이유 |
|---|---|
| `webui/app.py` 의 `/api/*` 엔드포인트 수정 | 모든 v2 탭 + v1 화면이 공유 |
| `webui/templates/{index,training_dashboard,stom_dashboard}.html` | v1 archive (6개월 보존) |
| `finetune/` 외 학습 코드, `_database/` | 데이터/모델 무결성 |
| 신규 `/api/*` endpoint 추가 | 기존 24 개만 사용 |
| predictor 미완료 상태에서 정확도/수익률 ready 표시 | readiness gate 정책 |
| KRONOS_TOKENIZER_VAL_BATCH_SIZE=1 해제 | validation OOM 회피 정책 (commit 7742cb8 Directive) |

---

## 13. 한 줄 미션 (다음 AI 에게)

> **"사용자가 §4 명령으로 옵션 D 학습을 시작했는지 확인하고, W9 로그 tail + 메트릭 카드의 sps/ETA 로 옵션 D 작동을 검증한 뒤, 6~12시간 목표 또는 보수 8~16시간 후 학습이 끝나면 §8 다음 단계 (예측 검증 + STOM 진단 + P5 gate) 로 자연스럽게 이어가라. OOM/compile 실패 시 §7 폴백 명령 제시."**

---

*작성: Claude (현 세션, 2026-05-19 KST)*
*다음 세션은 본 문서를 first read 로 진입할 것*
*세션 종료 후에도 본 문서 + commit 히스토리만 살아있으면 작업 100% 복원 가능*
