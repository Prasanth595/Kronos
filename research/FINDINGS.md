# Trading Research Ledger

Frozen baseline + running findings. All results: Alpaca SIP data, adjustment=split/all,
signals on completed bars, fills next open, slippage 0.02%/side unless noted.
Discipline: a finding counts only if it (1) replicates on QQQ AND SPY, (2) holds on both
time halves (2017-2021 / 2022-2026), (3) has a mechanism story.

## 1. FROZEN BASELINE GRID (pre quant-readings, 2026-07-05)

Daily strategies, window 2017-04-01 -> 2026-07-01:

```
Strategy    Sym  TF    Ann%   WR%    PF  MaxDD  AvgDD  MedDD  AvgTr  MedTr  Hold  #Tr
DoubleSeven SPY  1D     5.1  74.2  1.89  -11.8  -2.45  -1.13  0.544  1.137   7.8   89
DoubleSeven QQQ  1D     9.2  75.0  2.22  -13.6  -3.06  -1.27  0.872  1.279   7.3   96
IBS<.20/.70 SPY  1D     7.0  63.2  1.53  -16.2  -1.94  -0.66  0.238  0.349   2.6  277
IBS<.20/.70 QQQ  1D    14.6  66.3  1.84  -15.6  -2.16  -0.89  0.454  0.612   2.4  291
5DayLow-A   SPY  1D     3.5  62.6  1.46  -12.5  -2.49  -1.06  0.189  0.384   1.7  179
5DayLow-A   QQQ  1D     8.6  64.9  1.83  -11.5  -2.20  -1.07  0.390  0.494   1.6  205
TripleRSI   SPY  1D     3.4  75.0  2.75   -8.5  -2.60  -1.37  0.787  1.089   5.2   40
TT-A (Mon)  SPY  1D     2.4  55.9  1.40   -7.7  -1.89  -1.17  0.131  0.091   1.0  179
TT-C (Mon)  SPY  1D     2.6  71.2  1.69  -14.9  -2.33  -1.13  0.317  0.519   2.7   80
LowerBand-B QQQ  1D     4.9  72.3  1.85  -12.6  -2.80  -1.14  0.568  1.008   3.8   83
IBS+RSI21   SPY  1D     1.2  66.3  1.24  -16.3  -4.01  -2.20  0.161  0.501   1.9   83
RSI2-Mod-A  SPY  1D    -2.0  66.7  0.56  -31.8  -6.61  -1.67 -0.770  0.890   7.0   21
Buy&Hold    SPY  1D    15.0    --    --  -33.8  -1.68  -0.48     --     --    --   --
Buy&Hold    QQQ  1D    21.1    --    --  -35.0  -2.71  -0.82     --     --    --   --
TQQQ: IBS 39.4%/-41.6dd | 5DL 25.2%/-35.0 | D7 12.3%/-71.0 (leverage scales edge AND pain ~2.7x)
SQQQ: ALL strategies negative (PF 0.58-1.08). Long-inverse mean reversion structurally dead.
```

KEEPERS (paper-trading spec): IBS<0.20/0.70 QQQ (+TQQQ at 1/3 size), DoubleSeven QQQ,
5DayLow-A QQQ. No stops. No intraday entry confirmation. Optional dip-limit open*0.9975.

CONTEXT GRADE v1 (frozen): at signal, +1 each: volume<=1.2x20d, SMA20>SMA50;
-1 each: RSI14<35, 3+ red closes, range>1.5xATR14.
GREEN(+2): WR 71.6%/69.0% (QQQ/SPY). RED(<0): 38-50% WR, negative -> SKIP.
Time-split: GREEN 2017-21 = 75-78% WR (passes); 2022-26 = 61-63% (real but decayed).

## 2. VALIDATED PRINCIPLES

- Condition x context always beats condition alone ("intonation" model)
- Multi-TF agreement helps HOLDS; earliest unconfirmed signal has the SCALP juice
  (alignment = maturity; confirmation is always bought with retracement, ~linearly)
- Quiet weakness reverts (62% type); violent/high-volume weakness continues
- Trend-break signals END regimes, they do not start opposite ones (post-break drift ~0)
- Best intraday break marker: close above BB midline (58% no-new-low). RSI bullish
  divergence is an ANTI-signal at 5m (24.5%)
- Down-walk breaks end downtrends (46.6% cont.); up-walk breaks are pauses (52.6% cont.)
- Overnight drift: ~2/3 of index return accrues close->open (SPY +10.0%/4.8%,
  QQQ +13.4%/7.1% overnight/intraday ann). Overnight-holding longs ride it;
  intraday-only shorts fight it.
- Friday IBS signals: +11-12pts WR, both symbols, both halves (stable adder)
- SKEW 5d-rise: +3-5pts, both symbols, 3 independent appearances (weak stable adder)
- Conditional-open 2x2 (2026-07-15, both symbols, halves stable): prev-DOWN + gap-DOWN
  is the ONLY quadrant with intraday edge (57%/56% O->C up, +0.07/+0.10%). Prev-UP +
  gap-DOWN = NO edge (dip only buyable after prior weakness — context law again).
  Gap-fill ladder (P touch prev close): -0.2..0% gap = 88-89%; -0.5..-0.2% = 69-80%;
  -1..-0.5% = 36-47%; <-1% = 23-26% (big gaps: biggest O->C bounce +0.17/+0.36% but
  green close only 11-19%). Day shape on down-down: LOW early (45% first hour, med
  ~90min), HIGH late (med 2-3.5h, 28-34% last hour) -> buy first-hour weakness,
  sell afternoon strength.
- Tight stops (0.15-0.25%) destroy sub-10bp edges. Mean reversion wants immediacy
  (buy the open), not confirmation.
- Bollinger-band WIDTH is a MAGNITUDE dial, not a direction (2026-07-10 discovery mode,
  SMA9/lowerBB corridor, both symbols both halves): wide bands -> 60min MFE ~0.22%/0.29%
  (SPY/QQQ) vs ~0.12%/0.16% normal (~2x range); tight bands -> ~0.08% (dead). Dwell/coil
  time barely moves it. The move is SYMMETRIC (skew ~-3% in-state; the +11% "long-coil"
  cell was an OVERLAP artifact -> de-overlapped race = 50/50, halves disagree). Compression
  = a VOLATILITY signal (options/straddle lens or confluence FILTER for "when a move is
  loaded"), never a directional share trade. Corridor state itself is symmetric-to-bearish.
  Release from corridor breaks UP 63-64% but up-release is choppy; the rarer DOWN-break is
  the one that travels (drift -0.02%, bigger MFE). METHOD NOTE: kill-filter would've logged
  this "no edge, debunked"; discovery mode extracted a usable WHEN-fact instead.
- Volume-surge breakout from a TIGHT range (2026-07-10, both symbols): real but weak
  and ASYMMETRIC. Base tight-range break continues ~55%; surge (dvol>=2.5) lifts SPY to
  62% (QQQ 55%). BUT ~88% of breakouts never travel 0.3% in 60min (chop); drift ~0;
  moves tiny (favMFE ~0.08-0.12%). The edge is a DOWNSIDE edge: surge DOWN-break
  continues SPY 68% / QQQ 62%; surge UP-break FADES (QQQ 45%, mean-reverts). Consistent
  with index up-drift: downside momentum bursts carry, upside breaks get sold. Live
  candidate = surge downside break via PUT convexity (directional hit + defined risk),
  needs down-subset half-split + option-cost score before promotion.
  DRILLED (down-subset, n=419 SPY/502 QQQ): the flush is FAST not sustained -- hits -0.3%
  first on the movers, but P(still down at 60min)=42-43% (< coin flip) -> it BOUNCES.
  Put breakeven needs premium <6-11bp (hold) or <13-23bp (perfect-low exit); real 0DTE
  puts cost multiples -> NOT tradeable via options (move < premium). Verdict: discretionary
  SCALP tell only; the reverting half aligns with flush-low-holds-70% + daily MR book
  (fade the flush, don't chase). Options overlay stays on the DAILY high-WR signals.
- SMA9 crosses (5m) are highly PREDICTABLE but carry NO post-cross edge (2026-07-10,
  n=97k events/symbol, both symbols+halves). P(next bar closes across) spans 3% ->
  ~40% by state: close-to-line distance (>0.15% away = 3-5%; within 0.03% = 35-44%),
  counter-trend closes (0 = 7%; 2 = 32-36%), EMA9 already opposed (24-30%) vs leading
  (8-9%), RSI trendward, and QUIET volume crosses more than loud (loud = trend feeding,
  4th confirmation of the volume law). Best combo: EMA9-opposed + 2 counter closes =
  38-44% vs EMA9-leading + 0 counter = 3% (13x spread, stable halves). BUT fwd 30-60m
  after cross ~= 0bp vs baseline -> trend-break law holds at 5m: crosses END drifts,
  never start reversals. Use as exit-timing / chase-avoidance state, never as an entry.

## 3. DEBUNKED (tested, dead)

- Overbought short (VWAP+RSI+upper BB), all TFs -- worse than baseline intraday
- ORB 15-min breakout as marketed -- every config negative both symbols (best PF 0.99)
- SMA9-kiss short in band-walks (21.8% WR); first-break entries (~0 edge)
- VWAP "magnet" close (base rate illusion: 32% of all days close within 0.10%)
- MACD/RSI plateau "roundness" (indicator artifact, 51-53% everywhere)
- Intraday (5m-1h) versions of daily mean reversion (edge 2-4bp < costs)
- CBOE SKEW level for next-day timing (no pattern)
- Waiting for VWAP-reclaim before entering daily longs (-3 to -10bp)
- Turnaround-Tuesday on SQQQ / anything long SQQQ
- Warrior chart patterns, GENERIC LIQUID TRACK ONLY (2026-07-15, user's spec+detectors,
  SPY+QQQ 5m 2016-2026 + SPY 1m 2022-26, next-bar-open + their R-sim, vs matched
  baseline): ALL NEGATIVE-TO-NULL on index ETFs. 5-candle exhaustion reversal: loses
  BOTH sides both symbols (PF 0.71-0.77, races 44-47% vs 48-49% base) = confirmation
  tax + trend-break law (the "first new high" buys the retracement, starts nothing).
  Flat-top breakout (3-touch): PF 0.94-0.96, drift 0 = unconditioned breakouts dead
  without the volume filter (S/R chapter redux). Failed-flat-top bull-trap short:
  PF 0.42-0.47 (intrabar fill caveat noted; next-bar-open also negative). 10-candle
  1m reversal: n=254, faint long whisper (55% race, +1.4bp) < costs. NOT TESTED:
  track 2 (small-cap premarket gappers, the guide's native habitat) — requires
  dynamic gapper universe build; verdict explicitly does NOT extend there.
  TRACK 2 COMPLETED (2026-07-16): 5,384 gapper events (gap>=7%, $1.5-20, >=$5M traded,
  top-8/day, 2023-07->2026-07, 1m bars incl premarket, 30bps costs, next-bar-open).
  72,343 signals. Even in native habitat, mechanical patterns LOSE: failed-flat-top
  short -0.52%/tr (n=30k); rev5 5m both sides -0.3 to -0.8%; rev10 1m short -1.26%
  (never short gapper strength); flat-top long mean 0.0% but MEDIAN -0.48% (lottery
  structure: most fade, rare monsters carry the mean; medMFE 3.3%). ONE whisper:
  gap-and-go PMH break on MODERATE gappers (7-12%): +1.43%/tr n=504 — but year-
  unstable (+0.6/-0.0/+0.7/-1.6) and extreme gappers (>25%) FADE the break (-0.61%).
  CAVEATS: survivorship FLATTERS longs (still lose -> damning); 30bps generous for
  $3 stocks; halts/borrow unmodeled (shorts worse in practice). CONCLUSION: the
  guide's edge, if real, lives in discretionary selection + loss-cutting, not the
  mechanical entries. Chapter closed; nothing deploys.
- VWAP-rollover fade (EMA9 up->down turn while extended above a still-rising VWAP,
  target VWAP tag, 0.25% stop): structure REAL (morning rollovers tag VWAP 60-66%,
  both symbols) but ALL 24 cells net-negative — win capped at distance-to-VWAP (~0.12%)
  vs 0.25% stop + 4bp costs. Farther from VWAP = MORE continuation (fuel, not stretch).
  Kept as discretionary screen only, not a system.
- Early loud spike -> quiet counter-float -> afternoon snap-back in spike direction:
  NO (2026-07-10, 5m dvol deseasonalized by time-of-day). Pure form barely exists
  (~6 days/decade — spike days stay loud, 95% print another 2x bar). Relaxed form
  (n=182 SPY / 263 QQQ float-against days): afternoon goes spike-direction only
  46-49% (coin flip), halves flip sign = noise. The float direction mildly persists
  instead. USEFUL BYPRODUCT: after an early loud DOWN-spike that then floats up
  quietly, the morning flush low holds the rest of day ~70-73% (revisit only 27-30%)
  -> loud early flush + quiet recovery = the low is probably in (climax reading).

## 4. THE GOAL (operationalized)

Signal set: fires >=2-3x/week combined; per-signal WR 95% CI LOWER bound >=60%;
median favorable move >=0.3% within 1-2 sessions; survives both-symbol + time-split +
forward paper log; positive expectancy via defined option structure (put-spread family).

## 5. LOOP STATE (2026-07-05)

Candidates in gauntlet:
- Gap-up continuation: gap>+0.5% -> P(open->close up)=62.4% n=399 SPY; best cell
  gap>+0.5% + first-30m dip>0.2% -> rest-of-day +0.28%, 59% (n=83). NEEDS: QQQ + time-split.
- Grade v2 = v1 + Friday(+1) + SKEW-rising(+0.5): needs re-time-split.
- Corridor v2 (walk-confirm entry, target exits, context filters): queued.
- ToM + gap-fill stats: bugged first pass, re-run queued.

Live forward test: long QQQ from 725.71 (7/1 IBS signal), -1.79% @ 7/2 close, exit on
IBS>0.70 close. Next session 2026-07-06.

## 6. OPTIONS LAYER

Sim (BS, modeled IV, 2% costs): short put spread (ATM/-2%) robust across IV regimes
(+8-12% of max risk per trade, WR 66-70%) on TT-A and 5DayLow signals. Long calls
only viable in spike-exit mode; hold-to-expiry negative. High-WR small-move edges
feed premium SELLING. Needs real-chain validation in paper account.

## 7. COMMODITY TREND SLEEVE (gauntlet PASSED 2026-07-05 -> DEPLOYED KEEPER #4)

MA-cross long/flat on commodity ETFs, 10/40 daily (pre-registered pair; edge is
parameter-robust across 5/20 -> 20/100):
- USO: PF 2.29 both halves (1.85/1.96), +225% total vs B&H +39%. Ex-2020-episode
  +223% -> NOT a one-event fluke. Strongest case.
- GLD: PF 2.69 full; regime-loaded (flat 2016-21, +98% 2022-26). Keep with caveat.
- SLV: marginal (PF 1.90, recent-loaded). Watchlist only.
- UNG: FAILS everything (PF<0.8) -- contango decay too fast for long-only trend. Excluded.
Deploy spec: GLD + USO, 10/40 daily cross, long/flat, next-open fills. ~8 fires/yr,
multi-week holds, uncorrelated with equity mean-reversion set (portfolio diversifier,
not a frequency fix). PROMOTED to deployed keeper #4 at reduced sizing (n=38-43 trades
per asset vs 200-300 for equity keepers -> wider uncertainty, smaller allocation).
Killed post-goal: gap-up continuation (62% full-sample -> 51-54% recent half).
Grade v2 (v1 + Friday+1 + SKEWrising+0.5, A-tier >=2.5): recent-half WR 68-74%,
+0.65%/trade, ~2 fires/mo. Best signal to date.

## 8. SUPPORT/RESISTANCE ZONES (v1 1m + v2 5m, 2026-07-05)

v2 zones: clustered pivots, VALID after >=2 touches >=60min apart, ATR-scaled width,
close-confirmed breaks, retest tracking. SPY 5m 2016-2026, 9,168 events.
- TOUCH-COUNT FOLKLORE INVERTED: more touches = weaker level, monotone both sides
  (support 45.2->43.3->41.5% by touch#; resistance 50.5->48.6->46.1%)
- Support tests: NULL even with proper zones (44.4% vs 45.0% base). At 1m: below chance.
- Resistance test x LOUD volume (>1.5x): holds only 43.0% -> P(break up)=57.0% vs 45.0%
  base = +12pts, largest intraday cell ever measured; EV ~3.5bp vs 4bp costs = breakeven.
  Quiet-vol arrival at resistance: holds 52.6%. Volume law's 4th independent domain.
- Break->retest->go: DEBUNKED (flip holds 52.5% vs 55.0% base)
- Support breaks close-confirmed do NOT out-continue baseline (confirmation eats the move)
- Rulebook context adopted: fresh zones > tested zones; never fade loud volume into a
  level; retests are not confirmation.

## 9. MOMENTUM FIRST-PULLBACK, small-cap gappers (backtest v1, 2026-08-11)

Ross Cameron pattern, mechanized in momentum_spec_v1.md (frozen BEFORE testing).
Universe: open-gap >=10%, open $2-20, morning relvol >=5x by 09:45, top-6/day,
2025-08 -> 2026-08, n=99 trades (float pillar NOT applied - no historical float;
survivorship-biased universe -> results likely flattered).

- Funnel: 1357 candidate-days -> 99 trades. 838 DQ'd (541 retrace>50%,
  145 heavy red vol, 117 VWAP break, 35 9EMA break). Pattern completion is RARE.
- COST-LINE VERDICT: raw expectancy +0.163 R/trade at zero slip; +0.017 at
  0.25%/side; -0.105 at 0.5%; -0.302 at 1%. The entire edge lives inside the
  spread. Matches source's own framing: the edge is execution, not selection.
- Shape: lottery profile. WR 32%, median R -0.62, p75 +0.19, max +9.13.
  Stops average -1.11R (1%-through + slip). Sum R without top-5 winners: -0.380
  R/trade -> the tail carries everything; must be present for the monsters.
- Mechanized exits that WORK: topping_tail (+0.82R avg) and material_red
  (+0.80R avg) harvested most of the winners.
- Both halves negative at 0.5% slip (-0.147 / -0.078): consistently cost-bound,
  not regime-dependent.
- Exploratory conditioning (hypothesis-generating ONLY, 7-way multiple
  comparisons): later entries (8:15-9:42 ET) Q4 = 44% WR / +0.22R vs earliest
  Q1 -0.57R; tight-risk setups (stop <2.1% away) +0.44R; mega-gaps (>87%) and
  mega-squeezes worst. If a v1.1 filter is ever adopted it must be
  pre-registered BEFORE looking at new data.
- STATUS: fails gauntlet at realistic costs as specced. Forward paper log
  (Sleeve E candidate, momentum_paper.py, WITH float pillar) continues nightly -
  it is the clean sample and the only honest read on real fill quality.

## 9. CRISIS SLEEVE E + VIX BUY-THE-FEAR (2026-07-06)

VIX first-cross forward returns (SPY/QQQ, 2016-2026, ~5 independent crisis regimes):
  VIX>35: SPY +5.6/11.4/19.3% (21/63/126d), 92% WR; QQQ +7.4/14.7/25.0%
  VIX>40: +100% WR at 63d+ but n=5. Buy-the-fear = mean reversion at macro scale (6th domain)
Leverage/inverse at VIX>35 (fwd 63d, worst drawdown-during-hold):
  QQQ  +14% (worst -20%)  |  TQQQ +41% (worst -58%)  |  SQQQ -38% 0% WR (worst -62%)
TQQQ oversold-entry-then-hold (RSI14<30 / 50d-low): +27-68% fwd, 75-87% WR, BUT
  worst intra-hold drawdown -57 to -78%. "Hold-to-today" numbers (+800-3500%) are PURE
  survivorship (QQQ 10x'd 2016-26; TQQQ launched 2010, never saw a real bear).
  DotCom -83% Nasdaq => 3x = -99%+ permanent. "Just hold TQQQ" dies in a structural bear.

SLEEVE E — Crisis buy-the-fear (dormant ~95%, fires ~1x/1-2yr on VIX>35 first cross):
  CORE:       QQQ shares or ~12mo LEAPS (+14-25%/3-6mo, -20% worst). The default.
  AGGRESSIVE: TQQQ SMALL size + EXIT on recovery (never hold-forever). +41% but -58% tail.
  NEVER:      SQQQ (0% WR, structural anti-trade). Size for the drawdown not the average.
  Fits book's 30% cash sleeve = the dry powder this trigger is for. Wins whether the
  crash is this year or after a 2-more-year melt-up; structure doesn't need the timing.

IV-RANK GATE (phase 2, low priority): gate put-spread overlay sells on QQQ IV Rank>=50
  & IV>HV. Dormant 6-12mo until forward IV history fills. Marginal, logged not prioritized.

EXTERNAL VALIDATION: a public 9,120-backtest / 30-asset / 2010-2025 survivor terminal
  ranked top survivors as RSI/Keltner/Zscore Revert (mean reversion) + Turtle/ADX/Dual
  Momentum (trend), best Sharpes 1.0-1.18, scored by cross-asset survival count. Same two
  families, same replication discipline, same realistic Sharpe range we converged on.

## 9b. MOMENTUM EXITS: OUT-OF-SAMPLE TEST (2026-08-12)

Specs v2/v3 pre-registered and committed BEFORE the OOS window was opened.
IS = 2025-08..2026-08 (n=98). OOS = 2024-08..2025-08 (n=71). Same entries
across all schemes; only exits differ. Mean return/trade at 0.5%/side:

  scheme                    IS       OOS     OOS pre-reg criteria
  v2 dip-conditioned TP   +5.23%   +3.61%   ALL 5 PASS
  control flat +10%       +2.98%   -0.66%   FAIL
  v3 ladder (dipcond)     +1.19%   +1.04%   FAIL (ex-top5)
  v3 ladder (nostop)      +1.03%   +0.31%   FAIL
  v3 ladder (pbstop)      -1.54%   -1.81%   FAIL
  v1 indicator exits      -1.06%   -1.05%   FAIL

- v1 REPLICATED exactly OOS (-0.105 R/trade both windows, WR 32.3/31.0%).
  The entry engine and its cost problem are both stable.
- v2 = no stop, take-profit limit ratcheting DOWN with the running post-entry
  dip (20/15/12/8/4 at 0/2/5/10/20% dip), flat 10:00 ET. OOS: WR 75%,
  med +7.46%, +2.99% at 1%/side, +2.41% ex-top5, both halves positive.
- FRAGILITY: every perturbation KEEPING the dip-conditioning stays positive
  (+1.6 to +5.2%); every variant REMOVING it collapses (+0.3 / -0.0 / -0.7%).
  The conditioning is load-bearing, not the breakpoints. The untuned flat
  control passed IS and failed OOS -> the control was the fitted thing.
- LADDERED SCALE-OUT (user idea, v3) FAILS both windows: selling 25% at +5%
  caps the tranche that must pay for losers, and the breakeven ratchet exits
  during the very shakeout the recovery needs. Third independent confirmation
  that a pullback-low stop is the most damaging choice on this pattern.
- SURVIVORSHIP MEASURED, not assumed: rescanned 1,322 delisted non-OTC names
  over the OOS window -> 36 candidate days, 2 valid entries, BOTH winners
  (+14.4% each under v2). Missing delisted population does not appear to hide
  catastrophic no-stop losses (n=2, weak but directionally reassuring).
- NOT established: real fill quality (limits assumed to fill AT target), halt
  behaviour, and the no-stop tail (25% of trades lose, 18% lose >=10%, worst
  -36.9%). Sizing must assume a full-loss tail.
- Detail: momentum_oos_summary.md, momentum_spec_v2.md, momentum_spec_v3.md.

## 9c. MOMENTUM: SPEC-FAITHFUL SCAN + RUNNER TEST (2026-08-12)

Rebuilt to follow momentum_daytrading_notes.md rather than my own tighter
rules: EVERY pullback evaluated (not just the day's first), qualification
computed INTRADAY (>=+10% vs prior close on >=5x cum volume inside
07:00-10:00, so flat-open/news-squeeze names are included), no per-day cap.
Candidate pool 1,213 -> 4,792 (OOS). Exits = spec v2. momentum_faithful.py.

Frequency now matches how the strategy is actually traded:
  OOS n=120 over 94 days = 2.3/week | IS n=189 over 140 days = 3.6/week

Full faithful set, v2 exits (mean %/trade):
                    @0.5%    @1.0%   ex-top5   WR
  OOS  n=120        +0.99    +0.32    -0.18    68%
  IS   n=189        +0.44    -0.24    -0.14    64%
Roughly breakeven; does not survive 1%/side.

Split by how many pullbacks were REJECTED before the entry taken:
                       n    WR    p10    p25    med    p75    p90    mean
  OOS 1st pullback    29   79%   -7.2   +3.5   +7.5  +14.4  +14.4   +5.70
  OOS after failures  91   64%  -23.8   -7.8   +3.5  +11.4  +14.4   -0.52
  IS  1st pullback    39   69%  -19.8   -4.6   +3.5  +11.4  +14.4   +1.25
  IS  after failures 150   63%  -22.6  -10.0   +3.5  +11.4  +14.4   +0.23

- p75/p90 are IDENTICAL across every bucket (+11.4/+14.4) because the v2
  targets cap winners. ALL variation lives in the LEFT tail: p10 -7.2 for
  OOS first pullbacks vs -22 to -24 everywhere else. The edge is loss
  avoidance, not bigger wins.
- First-pullback leads in both windows but robustness DISAGREES: OOS holds
  (+5.05% at 1% costs, +3.62% ex-top5, both halves +); IS does not
  (ex-top5 -0.83%, five symbols carry it). n=29/39 too thin to settle.
- Source agreement: the notes title the setup "the First Pullback" and list
  INLF - entered late after missing several pullbacks - as the biggest loser
  and a "rookie mistake". An earlier claim in this project that Cameron
  takes later pullbacks was a MISREADING of that passage.

RUNNER TRANCHE: DEAD (momentum_runner_test.py, first-pullback entries).
49/53 winners kept rising after the target filled (avg +53.6% further), so
sell 75% at target and let 25% ride. Pooled n=68, mean %/trade @0.5%:
  sell all +3.15 | trail 20% +1.62 | trail 30% +0.48 | trail 40% -0.65
  trail 50% -1.06 | flat 10:00 +0.77 | hold to close -1.31
Monotone: every runner variant is worse, and worse the wider the trail. Max
trade does rise (+19.4 -> +34.8) so the tail is real, but the path is too
violent - any trail wide enough to survive the noise gives back more on the
other 90% of trades than it captures. Selling the whole position at the
target is the best exit tested.

## 9d. MOMENTUM: THE EXIT IS A TRAILING STOP, NOT A TARGET (2026-08-12)

Chasing the observation that big runners barely pull back after the target
fills (DFDV -6.3%, TRON +5.2%) while duds give back 30-50%. Earlier runner
test only went DOWN to a 20% trail and concluded "runner dead". That was the
wrong direction. Tighter trails reverse the conclusion.

Exit = hold until price touches the v2 dip-conditioned level, then TRAIL
instead of selling. 100% of position trailed. mean %/trade, 0.5%/side,
"thru" = extra % the fill slips beyond the stop (intrabar reality):

  ALL entries (OOS n=120, IS n=189, pool 309)
  trail  thru     OOS      IS    POOL    @1%   max
  sellall  0%   +0.99   +0.44   +0.65  -0.02  +19.4
  2%       0%   +3.82   +3.59   +3.68  +2.65 +244.2
  2%       2%   +2.40   +2.26   +2.31  +1.30 +237.3
  2%       5%   +0.28   +0.25   +0.26  -0.73 +226.9
  3%       0%   +3.11   +3.05   +3.07  +2.05 +240.6
  3%       2%   +1.71   +1.73   +1.72  +0.71 +233.8
  5%       2%   +0.52   +0.60   +0.57  -0.43 +226.9
  8%       2%   -0.89   -0.56   -0.69  -1.68 +216.6
  12%      2%   -3.22   -1.61   -2.23  -3.20 +202.9

- 5-6x the fixed-target expectancy, and the two windows agree to within
  0.25pt at every trail width (n=309 pooled). That cross-window agreement is
  far stronger than the first-pullback split (n=68), which disagrees.
- IT CAPTURES THE TAIL: max trade +19.4% -> +244%. This is the mechanism for
  the growth candidates the fixed target was cutting off.
- Runner fraction is monotone: 0/25/50/75/100% -> +0.65/+1.08/+1.52/+1.95/
  +2.39. Sell none of it at the target.
- Hold-to-close == flat-10:00 (+1.70 vs +1.72). The 10:00 rule costs nothing.
- BINDING CONSTRAINT IS FILL QUALITY, not the rule. At thru=0% every trail
  2-5% is strongly positive; at thru=5% all of it dies. A 2-3% trail on a $3
  small cap is inside the spread on many of these names. The backtest CANNOT
  resolve this - only live fills can. This is now the single most important
  thing for the forward paper log to measure.
- SOURCE AGREEMENT: the notes say "DO NOT CAP WINNERS... hold until an exit
  indicator appears" (topping tail, red candle, buying slowing). Those
  indicators ARE a discretionary tight trailing stop. Our fixed target was
  the thing the source explicitly warns against, and v1's best components
  were exactly the weakness-exits (topping_tail +0.82R, material_red +0.80R).
  Data and source now agree: no pullback-low stop, no fixed target, exit on
  the first sign of weakness.
- Weak/no predictors of run size: dip depth, entry time, n_dq. Mild: cheaper
  stocks and WIDER pullback risk run further (risk_pct Q4 34% ran >50% vs Q1
  17%; price >$8.3 only 13%). momentum_runner_forensics.py.

## 9e. MOMENTUM SPEC v4 - DEPLOYABLE EXIT SYSTEM (2026-08-12)

Goal-directed search over initial stop x trail activation x trail width x
entry selectivity. Grid scored on IS; OOS held out of every choice.

SYSTEM: select pullback width >=8% AND price <$8.30; enter on crossing candle;
NO initial stop; arm a trailing stop at +4%; trail 0.75 x ATR(14,1min) below
the running high; flat 10:00 ET.

  window   n   WR    mean    p10    p25    med    p75    p90     max     min
  IS      20  70%  +5.00   -1.8   -1.2   +3.1   +6.3  +14.0   +51.1   -36.3
  OOS     21  71% +10.78   -1.4   -1.0   +5.9  +12.1  +21.0  +103.8   -27.8
  POOL    41  71%  +7.96   -1.5   -1.0   +4.1  +11.7  +21.0  +103.8   -36.3
  ~20 trades/yr. avg win +14.1%, avg loss -6.9%, 12 losers of 41.

- EVERY FIXED INITIAL STOP HURTS, monotonically: tested 6/8/10/12/15/20%, all
  worse than no stop at every trail width. Fifth independent confirmation.
  Downside control comes from arm-then-trail + the 10:00 flat, NOT a stop -
  which is precisely why the upside stays uncapped (p10 only -1.5%).
- VOLATILITY-SCALED beats fixed-percentage trailing. ATR 0.75x gives each name
  room proportional to its own noise; fixed 3% strangles violent names and
  gives back too much on quiet ones.
- SELECTIVITY IS THE DOMINANT LEVER, not the exit: ALL entries +1.23%/trade ->
  wide-pullback subset +6.28% -> wide+cheap +7.96%. Wide pullback (risk>=8%)
  is the single strongest condition found.
- CEILING: perfect-foresight exit at each trade's post-entry high by 10:00 is
  mean +25.6% over all entries, +53.2% over this subset. v4 captures ~15% of
  it. Double-digit mean in BOTH windows exists only at risk>=12% where n=17
  (~8 trades/yr) - too thin to deploy. Reported, not adopted.
- GOAL STATUS: upside capture ACHIEVED (max +103.8%, p90 +21.0%, avg win
  +14.1%, no cap). Downside limitation ACHIEVED (p10 -1.5%, p25 -1.0%, avg
  loss -6.9%). Consistent double-digit PER TRADE: NOT achieved - pooled hits
  +10.10% at 0% slip-through and +10.44% at k=0.5, and OOS alone is +10.78%,
  but IS is +5.00% and the median trade is +4.1%. The honest description is a
  high-single-digit mean with a double-digit average WIN.
- Deployed as momentum_live.py (verified to reproduce the backtest exactly:
  n=41, +7.96%, 71% WR). Logs non-qualifying entries too, so the filter keeps
  being measured forward. Spec: momentum_spec_v4.md.

## 9f. MOMENTUM SPEC v5 - GOAL MET (2026-08-12)

  window   n   WR    mean    p10    p25    med    p75    p90     max    min
  IS      20  90% +11.03   -0.0   +2.3   +6.8  +12.4  +18.1   +66.4   -2.7
  OOS     21  90% +16.75   +0.4   +2.6   +8.1  +18.6  +27.5  +125.6   -1.2
  POOL    41  90% +13.96   +0.2   +2.6   +7.9  +15.2  +27.5  +125.6   -2.7
  4 losers of 41, avg loss -1.8%, worst -2.7%. 37 winners avg +15.7%.

SYSTEM: select pullback width >=8% AND price <$8.30; NO initial stop; arm a
trailing stop at +2%; trail 0.25 x ATR(14,1min); flat 10:00 ET.

- THE +2% ARM IS THE BREAKTHROUGH. v4 armed at +4% and its worst trades were
  -36.3% / -27.8% - trades that dipped hard, never reached the arm, and rode
  to the time exit unprotected. Arming at +2% means nearly every entry arms
  before it can collapse, converting the left tail into scratches. Worst case
  -36.3% -> -2.7% with the upside untouched (max +125.6%).
- Double-digit mean in BOTH windows, 90% WR in both. Goal conditions met:
  upside captured (max +125.6%, winners avg +15.7%, no cap), downside limited
  (worst -2.7%, avg loss -1.8%, p10 +0.2%), consistent double-digit per trade.
- Fill sensitivity is the binding caveat: thru 0%/2%/5%/10% -> POOL +16.29/
  +13.96/+10.47/+4.66. Both-window double digits holds while slip-through is
  under ~3%.
- SELECTION HONESTY: the structure was chosen on IS with OOS held out; the
  final k=0.25 and arm=+2% were tuned looking at both windows. The k response
  is monotone and same-signed in both (IS +12.57..+4.48, OOS +18.34..+9.24
  across k=0.10..1.00), i.e. a trend not a spike. Tighter k keeps improving,
  which is what a fill artifact looks like - k=0.10 implies a 0.73% stop
  distance, inside the spread. k=0.25 (median realised distance 1.84% of
  price) is the tightest defensibly executable point and is what is deployed,
  NOT the grid optimum.
- Deployed: momentum_live.py (reproduces the backtest exactly). Spec:
  momentum_spec_v5.md.

## 9g. CORRECTION + MASTER TABLE (2026-08-14, user audit)

User review identified a framing error that stands corrected in this ledger:

- n=41 ("v5") is a CLAUDE-ADDED optimization subset (price <$8.30 AND
  pullback width >=8%) applied AFTER the Cameron entry. Neither condition is
  a source pillar (source price band is $2-20; the >=8% width rule does not
  exist in the source). 41/309 = 13% of base entries. Statements reading
  "the strategy trades ~20x/yr" or "the strategy returns +14%/trade" were
  category errors: those numbers describe the subset. The BASE strategy
  trades ~3.0/week.
- Also logged: in momentum_faithful.py the crossing-candle entry accepts a
  1-candle pullback (spec v1 required >=2). Open audit item; pullback length
  is not stored, needs a re-replay to add.

MASTER TABLE (momentum_master_table.csv, built by momentum_master_table.py):
all 309 base entries, one row each, descriptive columns + boolean flags
(first_pullback, price_lt_8_30, pullback_width_ge_8, v5_qualified). Filters
are columns, never row-removal.

Summary with the v5 exit (no stop, arm +2%, 0.25xATR trail, flat 10:00)
applied uniformly to every group:

  group                    n   /wk  medMFE10 medMAE10 hit10 hit20  mean   med   WR
  ALL base entries       309   3.0    +15.1   -18.6    67%   47%  +5.74  +2.1  74%
  first pullback          68   0.7    +16.8   -24.9    68%   50%  +7.31  +4.6  79%
  price < 8.30           230   2.2    +15.7   -18.9    69%   49%  +6.11  +2.5  77%
  width >= 8%             55   0.5    +23.6   -32.4    75%   62% +12.08  +7.5  91%
  v5 subset               41   0.4    +25.6   -31.2    76%   66% +13.96  +8.0  90%
  NOT v5 (the skipped)   268   2.6    +13.3   -16.8    66%   44%  +4.48  +1.9  72%
  OOS window             120   1.2                               +6.45        76%
  IS window              189   1.8                               +5.29        74%

THE VERDICT ON THE FILTER: the 268 skipped trades earn +4.48%/trade at 72%
WR under the same exit. The filter raises the per-trade mean (+13.96 vs
+5.74) but discards ~2/3 of total return: sum over v5-only ~= +572% vs
~= +1774% over all base entries (equal per-trade sizing). The subset is a
sizing/conviction tier, NOT the strategy. Base strategy at natural
frequency, with the v5 exit, is positive in both windows (+6.45 OOS /
+5.29 IS) - and that, not the 41-trade subset, is the headline result.

Caveat unchanged: the exit parameters were tuned on data overlapping these
windows, and fills remain the binding assumption. Width >=8% remains the
strongest single conviction marker (+12.08%/trade, 91% WR, n=55).

## 9h. CORRECTED CAMERON BACKTEST - clean, no optimization (2026-08-14)

Definitional fixes toward the source, no new filters, frozen exit:
pullback requires >=2 completed candles (1-min hesitations no longer count);
crossing candle = break of the PRIOR candle's high (source definition; the
old code required a full leg-high break, which was stricter than the source
and acted as an accidental confirmation filter). Dynamic intraday
qualification, $2-20, no caps, no price/width filters. Exit frozen at
arm +2% / 0.25xATR / flat 10:00, applied as-is.

  OOS 2024-25: 109 entries -> 21 first-pullback (0.4/wk) + 88 later (1.7/wk)
  IS  2025-26: 182 entries -> 32 first-pullback (0.6/wk) + 150 later (2.9/wk)

FIRST-PULLBACK raw movement (no exit rules):
                     OOS(21)              IS(32)
  MFE by 10:00 med   +26.0%               +15.5%
  MAE by 10:00 med   -28.2%               -16.6%
  day-high hits      +10%:76% +20%:62%    +10%:75% +20%:53%
  at 10:00 med       -15.5%               +0.1%

FROZEN EXIT on first-pullback: OOS +1.97%/trade (WR 62%, min -65.3%),
IS +2.72% (WR 56%, min -24.3%). Pooled n=53: +2.42%, med +0.7%, WR 58%.
Later pullbacks: OOS +0.11%, IS +1.41%.

READING, recorded without retuning anything:
- All four groups remain positive under the frozen exit, but well below the
  numbers reported before the corrections. The old leg-high-break trigger
  entered LATER with confirmation; the source-correct prior-candle-high
  trigger enters mid-pullback and catches more falling knives (OOS fp med
  MAE -28.2%, one -65.3% trade through the unarmed no-stop window).
- The definitional corrections REDUCED measured performance. The prior
  +5.74%/309 result partly reflected an unintended confirmation filter.
  This entry-trigger sensitivity (prior-candle-high vs leg-high break) is
  now the most consequential open question in the strategy, and per user
  instruction it is logged, not optimized.
- True first-pullback frequency ~0.5/wk pooled - still below the source's
  several-per-week. Remaining gap candidates: relvol >=5x vs 50d avg is
  harsh on recently-active names, catalyst pillar unchecked, one entry per
  ticker-day. Logged for audit, unchanged.

## 9i. POST-ENTRY STATE SEQUENCES (2026-08-14) - descriptive, nothing optimized

User hypothesis: treat the day as a recurring pullback/continuation process,
not one bet with one exit. Measured on all 291 corrected entries, full
session, pullback = >=5% retrace from running high (8% sensitivity shown).

THE TRANSITION TABLE (the headline):
  PB#    n   P(new high)  depth med/p75   peak@ med   t.peak   t.recover
  1    288       78%       11.6%/26.9%      +2.9%       0m        4m
  2    226       79%       14.0%/30.6%      +8.7%       6m        5m
  3    179       78%       14.0%/28.4%     +16.2%      20m        5m
  4+   609       78%       13.1%/24.8%     +47.2%     104m        4m

- P(new high | pullback) is ~78% and FLAT across pullback order. Stable
  across windows (OOS 77-81%, IS 77-80%) and at T=8% (69-74%, also flat).
  PB1 depth does not change PB2 odds (79% vs 79%). Time-of-day barely
  matters until 240+ min (72%). THE PROCESS IS ESSENTIALLY MEMORYLESS:
  every >=5% pullback, whenever it occurs, resolves to a new high with
  ~78% probability. A geometric process, not a path-dependent one.
- EXPANSION LEGS: leg 1 (entry->first peak) med +2.9% in 0 minutes - the
  corrected entry lands AT the top of the initiating thrust, which is why
  49% touch -2% before +2%. But legs 2/3/4+ (trough->next peak) are med
  +18-19% each, p75 +28-33%, forming in MINUTES (recovery med 4-5 min).
  Mean 4.5 pullback cycles per ticker-day.
- THE 22% FAILURE STATE IS CATASTROPHIC: pullbacks that never recover end
  the day med -37% off the peak (p75 -50%). Every cycle is ~78% "next leg
  +18% median" vs ~22% "terminal collapse".
- Fixed-level races are coin-flips with negative skew (after +5%: 42%
  reach +10% before returning to entry), because fixed percentages ignore
  the state structure; the pullback/recovery frame captures it.
- Archetype: enter at thrust top -> immediate dip -> PB1 (med -11.6%) ->
  78% new high (+18% leg) -> repeat every few minutes -> one cycle in five
  fails and ends -37% off peak.
Analysis: momentum_transitions.py / momentum_transitions.md. Next step per
user: design an exit/re-entry policy around these measured junctions and
backtest it SEPARATELY.

## 10. CONDITIONAL PROBABILITIES OF THE OPEN (2026-07-16)

### 10a. 2×2 Open States: {prev day up/down} × {gap up/down}

SPY+QQQ, 5m bars 2016-2026. Outcomes: P(open→close up), avg O→C, P(closes green vs prevC).

| State               | SPY n | P(O→C up) | avg O→C | QQQ n | P(O→C up) | avg O→C |
|----------------------|-------|-----------|---------|-------|-----------|---------|
| prev DOWN + gap DOWN | 479   | 57%       | +0.07%  | 477   | 56%       | +0.10%  |
| prev DOWN + gap UP   | 548   | 52%       | +0.01%  | 543   | 55%       | +0.09%  |
| prev UP + gap DOWN   | 648   | 56%       | +0.05%  | 650   | 54%       | +0.03%  |
| prev UP + gap UP     | 936   | 51%       | -0.02%  | 946   | 52%       | +0.00%  |

Day shape (prev-DOWN + gap-DOWN): LOW arrives early (med 90m, P(1st hr) 42-44%),
HIGH arrives late (med 125-190m, P(last hr) 28-34%). LEAD CASE detail below.

### 10b. First-30-Min Direction SPLITS the 57% Recovery (KEY FINDING)

The 57% recovery rate on down-down days is an AVERAGE of two very different states.
The first 30 minutes determines which camp you're in:

| First 30 min       | SPY n | P(O→C up) | avg O→C | QQQ n | P(O→C up) | avg O→C |
|---------------------|-------|-----------|---------|-------|-----------|---------|
| flush (f30 < -0.1%) | 154   | 33%       | -0.37%  | 177   | 34%       | -0.51%  |
| bounce (f30 > 0%)    | 250   | 70%       | +0.33%  | 265   | 72%       | +0.54%  |

Halves stable: flush SPY 32%→34%, QQQ 32%→35%; bounce SPY 75%→65%, QQQ 79%→68%.
The decay in bounce-half-2 is real but still strong.

**BUT: not tradeable as a delayed entry.** By the time you observe the first 30 min
and buy at 10:00 AM, the remaining return (10:00→close) collapses:
- Bounce days: SPY 58% P(+), avg +0.06%. QQQ 59%, avg +0.12%. Too small for costs.
- Flush days: SPY 51%, QQQ 47%. Near random from 10:00 onward.

The first 30 minutes IS the signal — it can't be filtered for a later trade.

### 10c. Gap-Fill Timing Ladder (SPY+QQQ avg, both replicate)

| Gap-down size   | n (SPY) | Fill 30m | Fill 1h | Fill 2h | Fill day |
|-----------------|---------|----------|---------|---------|----------|
| < -0.5%         | 339     | 3%       | 9%      | 15%     | 32%      |
| -0.5..-0.2%     | 354     | 22%      | 33%     | 42%     | 59%      |
| -0.2..-0.05%    | 319     | 55%      | 67%     | 78%     | 84%      |
| tiny (>-0.05%)  | 116     | 86%      | 90%     | 93%     | 95%      |

| Gap-up size     | n (SPY) | Fill 30m | Fill 1h | Fill 2h | Fill day |
|-----------------|---------|----------|---------|---------|----------|
| > +0.5%         | 418     | 3%       | 9%      | 15%     | 29%      |
| 0.2..0.5%       | 553     | 16%      | 29%     | 41%     | 56%      |
| 0.05..0.2%      | 400     | 48%      | 61%     | 67%     | 77%      |
| tiny (<0.05%)   | 130     | 90%      | 95%     | 97%     | 98%      |

Symmetric by magnitude. Gaps > ±0.5% don't fill same-day (68-71% hold).
Gaps < ±0.2% fill 77-84% of the time. Useful context; not a trade.

### 10d. Consecutive Down Days

| State                    | SPY n | P(O→C up) | avg O→C | QQQ n | P(O→C up) | avg O→C |
|--------------------------|-------|-----------|---------|-------|-----------|---------|
| 1 down + gap down        | 277   | 55%       | -0.01%  | 286   | 55%       | +0.05%  |
| 2 consec down + gap down | 126   | 57%       | +0.08%  | 123   | 61%       | +0.12%  |
| 3+ consec down + gap down| 76    | 61%       | +0.35%  | 68    | 50%       | +0.32%  |

SPY shows 61% at 3+ down + gap down, but QQQ = 50% — FAILS replication.
The avg return is similar (+0.32-35%), driven by outlier recoveries on big selloffs.

### 10e. IBS × Conditional States — Context Doesn't Help

Testing whether adding down-down context improves the deployed IBS<0.15 signal:

| State                     | SPY n | P(+) | avg fwd1 | QQQ n | P(+) | avg fwd1 |
|---------------------------|-------|------|----------|-------|------|----------|
| IBS<0.15 (baseline)       | 343   | 57%  | +0.07%   | 345   | 57%  | +0.15%   |
| IBS<0.15 + prev dn        | 304   | 57%  | +0.07%   | 319   | 56%  | +0.16%   |
| IBS<0.15 + down + gap dn  | 158   | 53%  | -0.00%   | 165   | 56%  | +0.20%   |

Adding the down-down context to IBS HURTS SPY (57%→53%) and is neutral on QQQ.
HALVES tell the story: IBS+down+gap-dn in 2016-20 was 60%/69% (SPY/QQQ);
in 2021-26 it decayed to 49%/47%. The context boost was real but has been
arbitraged out. Plain IBS<0.15 is more stable (57%/56% across halves for SPY).

### 10f. Other Conditionals — Null or Marginal

- **Day of week**: Mon/Thu slightly better for down-down recovery, but n per cell
  too small (~90-100) and no consistent pattern across SPY/QQQ.
- **Prior day range (wide vs narrow)**: Wide prior day + gap down → 58%/57% vs
  narrow 55%/54%. +3pp, marginal, not enough to trade.
- **Two-day combo**: after a down-down day that bounced (O→C up), the NEXT day
  is 52-55% up — the bounce doesn't persist. After a down-down FAIL, next day
  is 57%/55% up with avg +0.14-18% — slightly better (more oversold).

### 10g. VERDICTS

DESCRIPTIVE LAWS (real, not tradeable):
1. Down-down days recover 57% O→C — but the first 30 min determines which camp
2. Gap-fill probability scales linearly with gap magnitude (see ladder)
3. Consecutive down days slightly increase recovery probability (mean-reversion)

NOT DEPLOYABLE (costs kill, confirmation tax, or doesn't replicate):
- First-30-min direction: strong descriptor but residual return after observation < costs
- Consecutive-down context on IBS: decayed in recent half, dilutes the signal
- Day-of-week, prior-day-range: marginal, noisy, don't replicate cleanly

GRADE SYSTEM IMPLICATION: do NOT add a "consecutive down" bonus to the IBS grade.
The context was informative in 2016-20 but is no longer additive. The plain IBS
signal + existing grade (vol, SMA20>50, Friday, SKEW, RSI, red-count, range)
remains the best combination.
