# Operation Status — 2026-08-13

One-page state of the world: the paper book, the momentum program, what is
proven, what is pending. Details live in FINDINGS.md (ledger), the spec files,
and the results markdowns referenced below.

---

## 1. The paper book (AGG-MAX, started 2026-07-02)

Weights locked 2026-07-13: **A** 55% equity mean-reversion (QQQ signals,
TQQQ execution) | **B** 10% GLD/USO 10/40 trend | **C** 20% crypto down-spike
| **D** 15% cash/crisis.

**Sleeve A — 3 closed trades, 0 open:**

| # | Symbol | Dates | Return | Worst mark |
|---|--------|-------|--------|------------|
| 1 | QQQ  | 7/02 - 7/09 | -1.04% | -2.24% |
| 2 | TQQQ | 7/14 - 7/22 | -7.43% | -10.2% |
| 3 | TQQQ | 7/27 - 7/31 | -0.51% | -12.6% |

Sleeve A compounded: **-8.83%**. Weighted book: **-4.86%**.
All three trades entered during the July QQQ selloff (726 -> 662, -8.8%);
the IBS>0.70 exit caught the bounce each time (trade 3 recovered from
-12.6% worst mark to -0.51%).

**Regime gate:** four QQQ IBS signals since 8/5 graded YELLOW (grade 1) and
were skipped — all missing the same point: SMA20 < SMA50 (701 vs 713 as of
8/12, gap narrowing). When the cross flips, identical signals grade GREEN.

Sleeves B and C: no trades executed to date (signal scans not yet wired into
the nightly loop — open item #4).

## 2. Momentum program (small-cap gappers, Ross Cameron first-pullback)

Timeline: source notes -> frozen mechanical spec v1 -> 1-yr backtest ->
movement/recovery forensics -> dip-conditioned exit idea (v2) -> true
out-of-sample test -> exit-system iteration (v3 rejected, v4 -> v5) ->
**v5 deployed to the nightly forward log**.

### What each stage established

- **v1 backtest** (n=99, 2025-08..2026-08): entry engine is real but
  cost-bound with indicator exits (+0.163 R/trade at zero slip, -0.105 at
  0.5%/side). Replicated OOS to three decimals (n=71, 2024-08..2025-08).
- **Movement forensics**: median winner has ~6-7R available; the typical
  path dips 3-6% below entry BEFORE the run; the pullback-low stop is
  touched first in 55-68% of races. Three independent measurements agree:
  a stop at the pullback low is the single most damaging choice on this
  pattern.
- **Recovery matrix**: recovery probability decays smoothly with dip depth
  (e.g. of entries that dipped -5%, 69% later exceeded +10%). This is the
  mechanism behind the v2/v5 exits.
- **v2 dip-conditioned take-profit** (no stop, TP ratchets down as the dip
  deepens): IS +5.23%/trade -> OOS +3.61%, all five pre-registered criteria
  met. Perturbation test: every variant KEEPING the conditioning stays
  positive; removing it collapses to ~0. The conditioning is load-bearing,
  not the breakpoints. Survivorship probe on the delisted universe came
  back clean (n=2, both winners).
- **v3 laddered scale-out**: rejected on OOS (breakeven ratchet fires during
  the shakeout; median trade becomes a scratch).
- **v5 (deployed)**: entries unchanged; select pullback width >= 8% AND
  price < $8.30; NO initial stop; trail arms at +2%, then 0.25 x ATR(14,1m)
  below the running high; flat 10:00 ET.
  Pooled IS+OOS: **n=41, WR 90%, mean +13.96%/trade, worst -2.7%,
  max +125.6%, ~20 trades/yr.** Fill sensitivity is the one real caveat:
  double digits holds while stop slip-through stays under ~3%; at 10%
  through, pool falls to +4.7%.

### Forward paper logs (the honest sample — real fill answer pending)

| Log | Nights | Trades | Result so far |
|---|---|---|---|
| v1 (baseline, momentum_paper_log.json) | 3 | 4 | 1 win, sum R -2.43 |
| v5 (deployed, momentum_v5_log.json) | 1 | 0 qualified (3 skips logged) | awaiting first qualified entry |

v5 skips are logged with full detail so the width/price filter keeps being
measured forward. 8/13 example of the exit difference on the same stock:
v1's pullback stop took CURI -4.5%; the v5 trail took -0.46%.

## 3. Established vs pending

**Established** (both time windows, pre-registered criteria, mechanism story):
- The five-pillar + first-pullback entry finds real, enormous movement
  (median winner MFE ~24% intraday).
- Exits, not selection, determine profitability on this pattern.
- Dip-conditioned/trailing exits that hold through the shakeout capture it;
  pullback-low stops and fixed near targets give it back.

**Pending / not established:**
1. **Real fill quality** — every backtest number assumes limit fills at the
   level and 0.5% entry slip; the forward log exists to measure this.
   ~20 trades/yr means patience.
2. **Halt/gap tail** — no stop means uncapped in principle; worst observed
   -2.7% (v5) / -36.9% (v2), size for a full-loss tail.
3. **v5 fine parameters** (k=0.25, arm +2%) were chosen looking at both
   windows; the structure was OOS-clean but those two numbers are not.
4. **Sleeves B & C** still need their signal scans wired into the nightly
   tracker loop.
5. **Float pillar** applied live (SEC-sourced via FMP) but not testable
   historically; 2 of 4 v1 forward trades were on floats > 20M (flagged).

## 4. Nightly operating procedure (post-close, ~21:05 UTC)

1. Sleeve A: mark positions, IBS/5DayLow scan on QQQ+SPY, grade any signal.
2. Momentum: run v5 (momentum_live.py) and v1 (momentum_paper.py) scans;
   backfill floats for new candidates when FMP is reachable.
3. Update book_state.json / logs; key-fragment scan; commit and push.

Keys live only in environment variables, never in files. Repo:
harrisonm23-byte/Quant_research_and_kronos, branch
claude/continue-previous-work-vvwws6.
