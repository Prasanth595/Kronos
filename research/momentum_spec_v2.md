# Momentum First-Pullback — Spec v2 (dip-conditioned take-profit)

PRE-REGISTERED 2026-08-12, BEFORE any out-of-sample data was examined.
Origin: user-proposed exit scheme, designed after reading the v1 recovery matrix
(2025-08..2026-08 sample). That makes the v1 window IN-SAMPLE for this spec.
The out-of-sample test window is 2024-08-01 .. 2025-08-01 and has NOT been
looked at in any form prior to this file being written.

## What is unchanged from v1

Universe, five pillars, first-pullback detection, the four pullback
disqualifiers, and the crossing-candle ENTRY are all exactly as in
momentum_spec_v1.md. Only the exit changes.

## What changes: the exit

v1 exits: stop at pullback low + six mechanized indicators. Median stop sat
~3.5% below entry and was touched first in 55-68% of entries.

v2 exits:
1. NO STOP AT THE PULLBACK LOW. The position is held through the post-entry
   shakeout. This is the load-bearing change and the main risk.
2. TAKE-PROFIT is a resting limit at a % above the raw entry price, which
   RATCHETS DOWN as the running post-entry dip deepens:

   running dip below entry   ->   take-profit target
   ------------------------------------------------
   none yet (0%)             ->   +20%
   >= 2%                     ->   +15%
   >= 5%                     ->   +12%
   >= 10%                    ->    +8%
   >= 20%                    ->    +4%

   The target only ever moves DOWN, never back up. Rationale (from the v1
   recovery matrix): recovery probability decays with dip depth, so the
   profit bar is lowered to match what the survivors actually deliver.
3. TIME EXIT: flat at 10:00 ET at the bar open. No overnight, no afternoon.

## Fill conventions (identical to v1 so results are comparable)

- Entry: raw crossing price + 0.5% (market order into momentum).
- Take-profit: filled AT the limit price (resting limit, no spread paid).
- Time exit: bar open - 0.5%.
- Within a single 1-min bar, the dip adjustment is applied BEFORE the target
  check (conservative: a same-bar dip can only lower the fill).

## Pre-registered pass/fail for the out-of-sample window

Declared BEFORE seeing OOS results. v2 is promoted to the nightly forward log
only if ALL of the following hold on 2024-08-01..2025-08-01:
  a. mean return/trade > 0 at 0.5%/side slippage
  b. still > 0 at 1.0%/side slippage
  c. still > 0 after excluding the top-5 symbols by summed return
  d. both OOS halves individually > 0
  e. n >= 50 entries
Anything less is recorded as-is and v2 stays out of the book.

## Known risks, stated up front

- NO-STOP EXPOSURE. Worst in-sample trade was -38.9% (10:00 flat). A halt that
  reopens far lower, or an offering priced overnight, is uncapped by this spec
  intraday. Position sizing must assume a full-loss tail.
- SURVIVORSHIP BIAS CUTS DEEPEST HERE. The backtest universe is today's active
  tickers; pumps that delisted are absent, and a no-stop scheme is maximally
  exposed to exactly that missing population. The forward paper log is the
  only unbiased read.
- The schedule's five breakpoints were chosen by eye on in-sample data. The
  flat +10% control (no tuning) is carried through every test as the honest
  baseline: if v2 only beats the control in-sample, the breakpoints are fitted.
