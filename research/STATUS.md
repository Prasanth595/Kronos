# Momentum Strategy — Status (2026-08-13)

State of the small-cap gapper momentum program, source (Ross Cameron
first-pullback, momentum_daytrading_notes.md) through the deployed v5 system.
Full detail: spec files (momentum_spec_v1..v5.md), results markdowns, and the
two forward logs.

---

## 1. The strategy as deployed (spec v5)

**Universe scan (daily):** top gainers with relative volume >= 5x the 50-day
average, price $2-$20, gap/gain >= 10%, float < 20M shares (SEC-sourced),
common stock only.

**Entry (unchanged from source):** wait for the squeeze, then the first valid
pullback — no >50% retrace, no heavy volume on red candles, no VWAP break,
no 9EMA break. Enter on the crossing candle (first candle to break the prior
candle's high). Window 7:00-9:45 ET.

**Selection filter (v4/v5 addition, both required at entry):**
- Pullback width (entry - pullback low) >= 8% of entry
- Entry price < $8.30

**Exit system (v5 — the load-bearing discovery):**
- **NO initial stop.** Fixed stops at 6/8/10/12/15/20% all reduced returns
  monotonically; these stocks dip below entry and recover (see §3).
- **Arm at +2%:** when price first touches +2% above entry, a trailing stop
  activates. Arming this early converts would-be catastrophic losses into
  scratches (v4 armed at +4%; its worst trades were -36.3%/-27.8%).
- **Trail 0.25 x ATR(14, 1-min)** below the running high, ratchet-up only.
  Median realised stop distance 1.84% of price.
- **Flat 10:00 ET** regardless. Upside is a morning phenomenon (highs
  exhausted by ~10:33 even unmanaged); downside has all day.

## 2. Evidence

Two windows, entries identical across all exit tests:
- IS: 2025-08-11 .. 2026-08-08 (n=99 entries)
- OOS: 2024-08-01 .. 2025-08-01 (n=71 entries, untouched until specs frozen)

**Entry engine replicates:** v1 indicator-exit expectancy -0.105 R/trade in
BOTH windows (to three decimals). The pattern and its cost problem are stable.

**v2 (dip-conditioned take-profit, no stop)** — passed all five
pre-registered OOS criteria: IS +5.23%/trade -> OOS +3.61% (WR 75%, 1%/side
still +2.99%, ex-top-5 +2.41%, both halves positive). Perturbation test:
every variant keeping the dip-conditioning stays positive; every variant
removing it collapses to ~0. The conditioning is load-bearing, not the
specific breakpoints.

**v5 (deployed):**

| window | n | WR | mean/trade | median | worst | best |
|---|---|---|---|---|---|---|
| IS | 20 | 90% | +11.03% | +6.8% | -2.7% | +66.4% |
| OOS | 21 | 90% | +16.75% | +8.1% | -1.2% | +125.6% |
| pooled | 41 | 90% | +13.96% | +7.9% | -2.7% | +125.6% |

~20 trades/yr. 4 losers of 41, average loss -1.8%.

**Survivorship probe:** rescanned the DELISTED universe (19,198 inactive
symbols) over the OOS window — 2 valid entries, both winners (+14.4% each).
The feared population of catastrophic no-stop losses in delisted pumps is
not supported by what is measurable (n=2, noted).

## 3. The forensics that produced the exit system

- Median winner had ~6-7R of favorable movement available intraday
  (median MFE +23.5% in-window vs ~3.5% median pullback depth).
- The typical path dips 3-6% below entry BEFORE the run: 75% of eventual
  +10% winners went red >= 2% first; half went >= 5% red first.
- The pullback low was touched before +2R in 63% of races -> three
  independent measurements agree: **a stop at the pullback low is the single
  most damaging choice on this pattern.**
- Recovery decays smoothly with dip depth (of -5% dippers, 69% later
  exceeded +10%; of -20% dippers, 43%) — the mechanism behind
  dip-conditioned and trailing exits.
- Laddered scale-outs (v3) rejected OOS: the breakeven ratchet fires during
  the shakeout and scratches would-be winners.

## 4. Forward paper logs (the honest sample)

| Log | Nights | Trades | So far |
|---|---|---|---|
| v5 deployed (momentum_v5_log.json) | 1 | 0 qualified, 3 skips logged | awaiting first qualified entry |
| v1 baseline (momentum_paper_log.json) | 3 | 4 | 1 win, sum R -2.43 |

Skipped entries are logged in full so the width/price filter keeps being
measured forward. Same-stock exit contrast on 8/13: v1's pullback stop took
CURI -4.5%; the v5 trail took -0.46%.

## 5. Open questions (what the forward log exists to answer)

1. **Real fill quality** — the deployed numbers assume 0.5% entry slip and
   2% slip-through on the trail stop. Double-digit means survive up to ~3%
   through; at 10% through the pool falls to +4.7%/trade. This is THE number
   to measure. At ~20 trades/yr, patience required.
2. **Tail risk** — no initial stop means a halt or gap through the trail is
   uncapped in principle. Worst observed: -2.7% (v5, n=41). Size positions
   assuming a full-loss tail is possible.
3. **v5 fine parameters** — structure (wide-pullback filter, no stop, ATR
   trail) was selected IS with OOS held out; the final k=0.25 / arm +2% were
   chosen looking at both windows. Response is monotone and same-signed in
   both windows (trend, not spike), and k=0.25 is the tightest defensibly
   executable point, not the grid optimum.
4. **Float pillar** — applied live (FMP/SEC) but untestable historically;
   floats backfilled nightly when the source is reachable.

## 6. Nightly procedure (post-close, ~21:05 UTC)

1. Run momentum_live.py (v5) and momentum_paper.py (v1 baseline).
2. Backfill floats for new candidates; flag float > 20M.
3. Key-fragment scan; commit logs; push.

Keys live only in environment variables, never in files. Repo:
harrisonm23-byte/Quant_research_and_kronos, branch
claude/continue-previous-work-vvwws6.
