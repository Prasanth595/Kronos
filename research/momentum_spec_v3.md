# Momentum First-Pullback — Spec v3 (laddered scale-out + ratcheting stop)

PRE-REGISTERED 2026-08-12, BEFORE any out-of-sample data was examined.
Origin: user-proposed. "Take profit at intervals, and set a new stop loss
below a previously crossed basecamp take-profit level."

Entries are UNCHANGED from v1/v2 (five pillars, first pullback, crossing
candle). Only the exit differs.

## The ladder

Basecamps, as % above the raw entry price. Each crossing sells 25% of the
original position at a resting limit:

  B1 = +5%    B2 = +10%    B3 = +20%    B4 = +35%

Any shares still held at 10:00 ET are sold at the bar open (time exit).

## The ratchet

The stop applies only to shares still held, and only moves UP:

  before B1 crossed  ->  initial stop (see variants)
  after  B1 crossed  ->  stop at entry (breakeven)
  after  B2 crossed  ->  stop at B1  (+5%)
  after  B3 crossed  ->  stop at B2 (+10%)
  after  B4 crossed  ->  stop at B3 (+20%)

## Variants tested (all pre-registered here, before OOS)

PRIMARY   v3-nostop  : no initial stop. Holds through the post-entry shakeout
                       exactly like v2 until B1 is crossed, then ratchets.
SECONDARY v3-pbstop  : initial stop at the pullback low (the v1 stop).
SECONDARY v3-dipcond : no initial stop, and the ladder is dip-conditioned -
                       if the running dip reaches 10%, remaining basecamps are
                       halved (B->B/2) to match decayed recovery odds.

The v3-pbstop variant exists to re-test the v1 stop under a laddered exit,
since the v1 evidence (stop touched first 55-68% of entries) and the v2
evidence (removing it flipped the sign) both point at the initial stop as the
load-bearing choice. Reporting all three keeps that comparison explicit.

## Fill conventions (identical to v1/v2 for comparability)

- Entry: raw crossing price + 0.5%.
- Basecamp: filled AT the limit price (resting limit, no spread paid).
- Stop: filled 1% through the stop level, then -0.5% slippage.
- Time exit: bar open - 0.5%.
- Within one 1-min bar the stop is checked BEFORE basecamp crossings, using
  the stop level in force at the start of that bar (conservative: adverse
  first, and a basecamp crossed in the same bar cannot retroactively protect
  the shares).
- Return is the position-weighted average across all tranches.

## Pre-registered pass/fail (identical battery to v2)

On 2024-08-01 .. 2025-08-01, a variant is promotable only if ALL hold:
  a. mean return/trade > 0 at 0.5%/side slippage
  b. still > 0 at 1.0%/side slippage
  c. still > 0 after excluding the top-5 symbols by summed return
  d. both OOS halves individually > 0
  e. n >= 50 entries

## Honest status of the parameters

The four basecamp levels and the 25% tranche size were NOT fitted by search.
They were chosen once, by hand, informed by the published v1 movement stats
(median winner offered ~+23% intraday; 81% of entries touched +10%; 59%
touched +20%; 23% touched +50%). That still counts as in-sample-informed,
because those statistics came from the 2025-08..2026-08 entries. The
2024-08..2025-08 window remains untouched and is the honest test.

Carried through every comparison as baselines: v1 indicator exits, v2
dip-conditioned target, and the untuned flat +10% control.
