# Stage C-0 — DB Feature Feasibility Probe (2026-05-27)

Plan: `.omx/plans/ralplan-stom-rl-deep-rl-2026-05-27.md` (§ Stage C / Stage C-0, V10, P1-5a)
Repo: `Kronos` · Branch: `feature/stom-rl-lab` · Baseline: `fca9e85` · Python 3.11 · Windows
DB: `_database/stock_tick_back.db` (29.7 GB, 2427 symbol tables)
Probe artifact (NOT committed): `.omx/artifacts/deep_rl/stageC_export/c0_probe.json`
Probe script: `finetune/stom_rl_c0_feature_probe.py` (read-only, bounded sampling)

---

## Feasibility Verdict (conclusion first)

**Stage C CAN meaningfully expand signal. All four candidate high-signal source
columns EXIST and are densely populated (≥99.8% non-null in every sampled
session). Stage B should NOT train on the current 3-symbol / current-feature
data — it should WAIT for the minimal feature expansion**, because the columns
the rules currently drop (`등락율`, `시가총액`, `고저평균대비등락율`) are real,
direct, and cheap to add. The cost-aware experiment found alpha to be
signal-limited; this probe shows richer point-in-time signal is genuinely
available in the DB, so the expansion is worth doing before any alpha claim.

**Add now (no fallback needed):** `change_rate`, `market_cap`,
`high_low_mid_change_rate`, `trade_strength_avg_n`.
**Already canonical, keep as-is:** `turnover_rate` (fully present; see nuance below).

---

## Method (bounded, no full scan)

- Reused read-only helpers: `connect_readonly` (`mode=ro`, `query_only=ON`),
  `list_stock_tables`, `_decode_table_columns`.
- **Sample:** 8 symbol tables × up to 3 distinct sessions each = **20 sessions**,
  each bounded to ≤3000 rows in the morning window (`ORDER BY index LIMIT 3000`).
- Symbol discovery bounded to a 30-table scan; all 30 carried the new columns,
  so the first 8 (`000020, 000040, 000050, 000060, 000070, 000080, 000100, 000120`)
  were used. Sessions span 2022–2025 (disjoint per symbol, grouped by
  `substr(CAST("index" AS TEXT),1,8)`).
- Coverage basis: **non-null %** for value columns; **non-zero %** additionally
  reported for columns where a literal 0 could mean "not recorded"
  (`시가총액`, `회전율`, `체결강도`).
- Threshold (plan V10): a feature with **<80% effective coverage in ANY session
  ⇒ "fallback-or-drop"**; ≥80% everywhere ⇒ "add".

### Encoding note (resolves the "mojibake" flag)
Column names are **valid UTF-8** in the DB. Raw bytes e.g.
`b'\xeb\x93\xb1\xeb\x9d\xbd\xec\x9c\xa8'` decode via UTF-8 to `등락율` (and FAIL
under cp949). The `�` seen in a Windows console is a **display-only** codepage
artifact; `_decode_table_columns` returns correct Korean Unicode strings and
Python string matching against the target names works. Confirmed empirically.

Full decoded columns of `000020` (54 cols) include, in order:
`index, 현재가, 시가, 고가, 저가, 등락율, 당일거래대금, 체결강도, 초당매수수량,
초당매도수량, 거래대금증감, 전일비, 회전율, 전일동시간비, 시가총액, …,
고저평균대비등락율, 저가대비고가등락율, …`.

---

## Per-feature results

Coverage = worst (minimum) across all 20 sampled sessions. "basis" is the
metric the threshold was applied to.

| Target feature | DB source column | Exists? | Worst-session coverage | basis | Value range (sampled) | Verdict |
|---|---|---|---|---|---|---|
| `change_rate` | `등락율` | YES | **100.0%** | non-null | −8.30 … 29.97 (%) | **add** |
| `market_cap` | `시가총액` | YES | **100.0%** | non-zero | 417 … 62,353 (units, all >0) | **add** |
| `high_low_mid_change_rate` | `고저평균대비등락율` | YES | **100.0%** | non-null | −12.72 … 7.27 (%) | **add** |
| `trade_strength_avg_n` | `체결강도` | YES | **99.84%** | non-zero | 0.0 … 500.0 | **add** |
| `turnover_rate` | `회전율` | YES | 100.0% non-null / 63.5% non-zero | non-zero | 0.0 … 19.02 (%) | **keep (already canonical)** |
| `high` (fallback source) | `고가` | YES | 100.0% | non-null | 456 … 127,500 | n/a (already source) |
| `low` (fallback source) | `저가` | YES | 100.0% | non-null | 433 … 121,000 | n/a (already source) |
| `close` (fallback source) | `현재가` | YES | 100.0% | non-null | 434 … 127,500 | n/a (already source) |

Worst sessions, for the record:
- `등락율`, `시가총액`, `고저평균대비등락율`, OHLC: 100% in all 20 sessions.
- `체결강도`: worst = `000060 / 20221108` at 99.84% non-zero (1 zero-strength bar
  in a 625-row thin session).
- `회전율`: worst = `000120 / 20220504` at **63.5% non-zero but 100% non-null**.

---

## `turnover_rate` (회전율) — the only sub-80% number, and why it is NOT a gap

`회전율` is **100% non-null in EVERY sampled session** — the column is fully
recorded. The 63.5% figure is *non-zero* coverage in one early, low-liquidity
592-row morning session (`000120 / 20220504`): the zeros there are **genuine
low/zero-turnover bars, not missing data**. Across the other 19 sessions
non-zero coverage is 0.988–1.000. So under the plan's literal rule
("non-zero where 0 means missing") turnover *trips* the flag, but the honest
data reading is that the column is fully populated and the zeros carry real
information. `turnover_rate` is **already canonical** (`STOM_RL_CANONICAL_FEATURES`,
`finetune/qlib_stom_pipeline.py:68`) and should be kept as-is — no fallback,
no drop. No new column needs to be added for it.

---

## Value sanity

- `등락율` (change_rate): −8.30% … +29.97% — plausible intraday %; +29.97 ≈ the
  +30% daily upper limit. PASS.
- `시가총액` (market_cap): 417 … 62,353, all strictly positive. PASS.
- `고저평균대비등락율` (high_low_mid): −12.72% … +7.27%, centered near 0 — matches
  a `(close − (high+low)/2) / ((high+low)/2)` deviation measure. PASS. (Direct DB
  column exists, so the computed-from-OHLC fallback in the plan is unnecessary.)
- `체결강도` (trade_strength): 0.0 … 500.0 — exactly the documented [0, 500] band. PASS.
- `회전율` (turnover): 0.0 … 19.02% — plausible. PASS.
- OHLC `고가`/`저가`/`현재가`: positive, high ≥ low ordering consistent. PASS.

---

## Stage-C wiring implication (for the implementer, not done here)

The candidates map cleanly onto direct DB columns — **no fallback formulas are
needed for any "add" feature** (the plan's trailing-return fallback for `등락율`
and the OHLC-computed fallback for `고저평균대비등락율` are confirmed
unnecessary; direct columns exist and are dense):

| New canonical feature | Direct DB source | Causality |
|---|---|---|
| `change_rate` | `등락율` | point-in-time (same-bar % change), no forward |
| `market_cap` | `시가총액` | slowly-varying, numeric-fill-0 acceptable, no forward |
| `high_low_mid_change_rate` | `고저평균대비등락율` | same-bar derived, no forward |
| `trade_strength_avg_n` | `체결강도` (already a source) | **trailing N-bar mean, window ≤ T only (no look-ahead)** |

Only `trade_strength_avg_n` requires a derived computation; it MUST be a trailing
(causal) rolling mean over bars ≤ current bar, per the plan's leakage guard
(V11 / per-feature causality test in Stage C). The three direct columns
(`등락율`, `시가총액`, `고저평균대비등락율`) need to be added to
`STOM_RL_SOURCE_COLUMNS` (`finetune/qlib_stom_pipeline.py:208-223`), then mapped
in `STOM_RL_FEATURE_MAPPING` and appended to `STOM_RL_CANONICAL_FEATURES`.

---

## Gate decision

- **V10 (C-0 probe) — PASS.** Every candidate has a verified source with
  per-session coverage reported; no feature relies on an unverified assumption.
- **P1-5a (Stage B data choice) — DECISION: WAIT for minimal expansion.** Add the
  three direct columns + the trailing `trade_strength_avg_n` to `export-stom-rl`,
  then train Stage B on the expanded feature set. The signal the rules currently
  drop is real and cheap; training on current features would knowingly leave
  available signal on the table given the established signal-limited alpha.

## Constraints honored
- Read-only (`mode=ro`, `query_only=ON`); bounded sampling only (8 symbols × ≤3
  sessions × ≤3000 rows); no full-DB scan; no `eval/exec/__`; causal-only framing
  for the one derived feature.
