# P1.5 GO/NOGO 예외 처리 기록

**작성일**: 2026-05-15 KST
**상태**: 학습 실패 종료 후 P1.5 진행 결정

---

## 배경

`docs/kronos_dashboard_p1_5_build_checklist.md` §1의 GO/NOGO 7개 조건은 **predictor 학습이 정상 완료된 경우**를 가정한다. 그러나 본 학습 run (`stom_1s_grid_pred60_2025_full_small`)은 tokenizer 약 75% 시점에서 validation OOM으로 중단됐다 (commit `7742cb8`). 따라서 일부 조건은 NOGO 상태다.

## GO/NOGO 실측 상태

| # | 조건 | 기대값 | 실측값 | 판정 | 영향 |
|---|---|---|---|---|---|
| 1 | predictor 학습 완료 | `train_stage=predictor, status=completed` | tokenizer ~75%, stopped | NOGO | P3 Forecast Workbench 모델 검증 불가 |
| 2 | readiness.predictor_complete | `true` | `false` (waiting) | NOGO | UI에서 readiness gate `waiting` 유지 |
| 3 | checkpoint 파일 ≥ 1 | `≥ 1` | `0` | NOGO | predictor 미시작 |
| 4 | model_weight 파일 ≥ 1 | `≥ 1` | `0` | NOGO | predictor 미시작 |
| 5 | 학습 프로세스 종료 | 0개 | 0개 | **GO** | OOM crash로 프로세스 자연 종료 |
| 6 | GPU VRAM 해제 | `< 5%` | (Flask 다운 상태라 미측정, 그러나 학습 종료로 해방) | **사실상 GO** | 디스크 경합 0 |
| 7 | 디스크 I/O 안정 | `< 5%` | (Flask 다운 상태라 미측정, 학습 프로세스 0개) | **사실상 GO** | npm install 안전 |

## 의사결정

**P1.5 진행 허가** — 다음 근거로 GO/NOGO 체크리스트의 **실질 목적(B-1: 학습 자원 보호)**이 충족됐다고 판단:

1. **B-1 (학습 디스크 fsync 보호)**: 학습 프로세스가 종료되어 진행 중인 학습이 없다. npm install이 디스크 경합을 일으킬 학습이 존재하지 않으므로 B-1의 실질적 위험이 0이다.
2. **재학습 가능성**: 향후 OOM 원인을 수정 후 재학습할 수 있다. 그 시점 전에 P1.5 빌드 산출물(`webui/static/v2/dist/`)을 commit해 두면, **재학습 중에는 npm 명령 0건**으로 P1.5 dist 모드 운영 가능 (KRONOS_V2_DIST=1 toggle만 사용).
3. **predictor 의존 기능 보류**: P3 Forecast Workbench의 SEED=42 결정성 검증은 본 PR 범위 밖. P3는 별도 PR로 predictor 성공 학습 이후 진행.

## 본 PR 범위

- ✅ Vite + Svelte + TypeScript + Tailwind 빌드 파이프라인 구축
- ✅ Svelte 컴포넌트 18개 작성 (design_spec §4 트리)
- ✅ theme.ts 디자인 토큰 owner 파일
- ✅ ECharts eager + Plotly dynamic import 구조
- ✅ Vite 빌드 산출물 commit (`webui/static/v2/dist/`)
- ✅ KRONOS_V2_DIST=1 toggle 검증
- ✅ SSR meta marker 보존 검증 (B-2)
- ✅ pytest 갱신

## 본 PR 범위 외 (별도 PR)

- P3 Forecast Workbench `/api/predict` 실제 검증 (predictor 학습 성공 후)
- P5 Lighthouse a11y/perf 측정 (P2~P4 완료 후)
- P6 Cutover (`KRONOS_V2_ENABLED=1`, v1 archive)

## Rollback 안전망

- `KRONOS_V2_DIST=0` (기본): P1 SSR Jinja shell이 그대로 서빙됨
- `KRONOS_V2_DIST=1`: P1.5 dist 모드 활성화
- 두 모드 모두 동일한 `kronos-v2-shell` SSR meta marker 노출 → grep 검증 동일 통과

---

**결론**: 학습 실패는 P1.5 진행을 막지 않는다. 오히려 학습이 진행 중이지 않은 지금이 npm install 가장 안전한 윈도다. 본 PR로 P1.5 인프라를 확정해 재학습 시점에도 안전 운영 보장.
