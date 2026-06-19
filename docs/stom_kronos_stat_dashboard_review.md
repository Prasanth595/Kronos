# STOM 통계 대시보드 Code Review

작성일: 2026-05-10
범위: `a488b0e..HEAD` 중 이번 통계 대시보드 관련 변경

## Verdict

```text
Recommendation: APPROVE
Architectural status: CLEAR
```

## 검토 파일

- `docs/stom_kronos_stat_dashboard_plan.md`
- `webui/stom_dashboard.py`
- `webui/app.py`
- `webui/templates/stom_dashboard.html`
- `tests/test_stom_dashboard_helpers.py`

## 확인한 품질 항목

| 항목 | 결과 |
| --- | --- |
| API 경로 안전성 | 기존 `_safe_path_in_dirs` / `load_prediction_frame` 경로 검증 재사용 |
| 큰 CSV 처리 | 서버에서 pandas 집계 후 제한된 symbol rows 반환 |
| Chart payload | Plotly JSON 3종 반환 |
| XSS 표면 | 새 diagnostics table의 symbol 출력은 `escapeHtml` 적용 |
| 테스트 | helper/API/official CSV smoke 통과 |
| 범위 관리 | 새 학습, DB 변경, 외부 연동 없음 |

## 검증 명령

```powershell
git diff --check
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_dashboard_helpers.py tests\test_stom_qlib_pipeline.py tests\test_stom_filter_gate.py -q
C:\Python\64\Python3119\python.exe -m compileall webui\app.py webui\stom_dashboard.py tests\test_stom_dashboard_helpers.py finetune\search_stom_1s_filters.py
```

결과:

```text
16 passed, 2 warnings
compileall success
official200k diagnostics smoke status=200
symbols=334
symbol_metric_count=334
summary_rows=20
chart_keys=error_distribution, return_scatter, symbol_heatmap
```

## 남은 주의점

- 기존 대시보드 일부 다른 table은 여전히 innerHTML 기반이며, 이번 변경 범위에서는 새 diagnostics 출력만 escape 처리했다.
- Plotly warning은 upstream pandas/plotly FutureWarning이며 기능 실패가 아니다.
- 공식 200k 결과는 cost gate 실패 상태이므로 이 화면은 분석용이지 매매 승인 화면이 아니다.
