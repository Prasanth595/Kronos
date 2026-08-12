# Momentum — Spec v5: DEPLOYED exit system (2026-08-12)

Supersedes v1-v4. Entries unchanged (five pillars, intraday qualification,
first-pullback pattern, crossing candle — momentum_faithful.py).

## The system

SELECT (both, measured at the entry bar):
  - PULLBACK WIDTH  (entry - pullback_low) / entry  >= 8%
  - PRICE           entry < $8.30

ENTER  crossing candle, market. Assume +0.5% slippage.

STOP   NONE at entry. Fixed initial stops were tested at 6/8/10/12/15/20%
       and every level reduced returns monotonically. These stocks dip below
       the entry and then recover; a hard stop sells the dip.

ARM    when price touches +2% above entry, a trailing stop activates.

TRAIL  0.25 x ATR(14, 1-min) below the running high. Ratchets up only.
       Median realised stop distance 1.84% of price (p10 1.10%, p90 3.27%).

FLAT   10:00 ET at the bar open.

## Performance

  window   n   WR    mean    p10    p25    med    p75    p90     max    min
  IS      20  90% +11.03   -0.0   +2.3   +6.8  +12.4  +18.1   +66.4   -2.7
  OOS     21  90% +16.75   +0.4   +2.6   +8.1  +18.6  +27.5  +125.6   -1.2
  POOL    41  90% +13.96   +0.2   +2.6   +7.9  +15.2  +27.5  +125.6   -2.7

  4 losers of 41, average loss -1.8%, worst -2.7%.
  37 winners, average +15.7%. ~20 trades/year.

## Why arming at +2% is the load-bearing change vs v4

v4 armed at +4% and trailed 0.75 ATR; its worst trades were -36.3% and -27.8%.
Those were trades that dipped hard and NEVER reached the +4% arm, so nothing
was protecting them and they rode to the 10:00 exit. Arming at +2% means
essentially every entry arms before it can collapse, converting the left tail
from catastrophic losses into scratches. That single change is what took the
worst case from -36.3% to -2.7% while leaving the upside untouched
(max +125.6%).

## Fill sensitivity — the one real caveat

"thru" = extra % the fill slips beyond the stop level.

  thru      IS      OOS     POOL
    0%  +13.30   +19.13   +16.29
    2%  +11.03   +16.75   +13.96     <- deployed assumption
    5%   +7.63   +13.18   +10.47
   10%   +1.97    +7.22    +4.66
   15%   -3.70    +1.26    -1.16
  1.0% entry slip + 2% thru: POOL +12.83

Double digits in BOTH windows holds while slip-through stays under ~3%.
At 5% the pool is still +10.47 but IS falls to single digits. This is the
number the forward log exists to measure.

## Honest notes on how this was found

- The STRUCTURE (wide-pullback + cheap filter, no initial stop, ATR trail)
  was selected on IS with OOS held out, and verified OOS.
- The final parameters (k=0.25, arm +2%) were chosen while looking at BOTH
  windows. That is not a clean out-of-sample test of those two numbers.
  Mitigating evidence: the response is monotone and same-signed in both
  windows across the whole sweep, i.e. a trend, not a spike —
     k      0.10   0.15   0.25   0.40   0.50   0.75   1.00
     IS   +12.57 +12.06 +11.03  +9.49  +8.46  +5.89  +4.48
     OOS  +18.34 +17.81 +16.75 +15.27 +14.21 +11.66  +9.24
- Tighter k keeps improving, which is exactly what an unrealistic-fill
  artifact looks like. k=0.10 implies a 0.73% stop distance, inside the
  spread on many $2-8 names. k=0.25 (1.84% median distance) is the tightest
  point that is defensibly executable, so that is the deployed value rather
  than the grid optimum.
- n=41 over two years (~20/yr). Small.
- No stop means a halt or a gap through the trail is uncapped in principle;
  none of the 41 produced a loss worse than -2.7%, but size for a tail.
