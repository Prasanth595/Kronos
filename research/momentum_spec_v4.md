# Momentum — Spec v4: the deployable exit system (2026-08-12)

Supersedes v1/v2/v3 exits. Entries unchanged (five pillars, first-pullback
pattern, crossing candle, per momentum_daytrading_notes.md and the faithful
scan in momentum_faithful.py).

## The system

SELECT (both required, measured at the entry bar):
  - PULLBACK WIDTH: (entry - pullback_low) / entry >= 8%
  - PRICE: entry price < $8.30

ENTER: crossing candle, market, assume +0.5% slippage.

STOP: NONE at entry. This is not an oversight - a fixed initial stop was
  tested at 6/8/10/12/15/20% and EVERY level reduced returns monotonically
  (momentum_exit_system_results.md). These stocks dip below the entry and
  then recover; a hard stop sells the dip.

ARM: when price touches +4% above entry, a trailing stop activates.

TRAIL: 0.75 x ATR(14, 1-min) below the running high. Ratchets up only.
  Volatility-scaled, not a fixed percentage - a quiet $3 name and a violent
  $7 name get different room, which is the point.

TIME EXIT: flat at 10:00 ET, at the bar open. Hold-to-close is equivalent
  (+7.14 vs +7.96) and adds tail risk, so 10:00 stands.

## Measured performance

Selection was done on IS; OOS was held out of every choice above.

  window   n   WR    mean    p10    p25    med    p75    p90     max     min
  IS      20  70%  +5.00   -1.8   -1.2   +3.1   +6.3  +14.0   +51.1   -36.3
  OOS     21  71% +10.78   -1.4   -1.0   +5.9  +12.1  +21.0  +103.8   -27.8
  POOL    41  71%  +7.96   -1.5   -1.0   +4.1  +11.7  +21.0  +103.8   -36.3

  ~20 trades/year. 12 losers of 41. Average win +14.1%, average loss -6.9%.

Robustness (POOL mean %/trade):
  0% slip-through +10.10 | 2% +7.96 | 5% +4.76
  1% entry slip + 2% through +6.89 | + 5% through +3.72
  arm at +2% +8.85 | arm at +8% +5.13
  trail k=0.5 +10.44 | k=0.75 +7.96 | k=1.0 +6.40
  hold to close +7.14
Positive in both windows under every variant tested.

## Against the goal

ACHIEVED - capture the high-daily-return names: max trade +103.8%, p90 +21.0%,
  average win +14.1%. The fixed-target exit capped these at +19.4%; the
  volatility trail does not cap them at all.
ACHIEVED - limit downside without limiting upside: p10 -1.5%, p25 -1.0%,
  average loss -6.9%, and this WITHOUT an initial stop. Downside control
  comes from the arm-then-trail structure plus the 10:00 flat, which is what
  let the upside stay uncapped.
PARTIALLY ACHIEVED - consistent double-digit returns per trade. Pooled mean
  reaches +10.10% at 0% slip-through and +10.44% at trail k=0.5, and OOS
  alone is +10.78%. But the IS window is +5.00%, so double digits is NOT
  consistent across both windows. Median trade is +4.1%, not double digit.
  Honest statement: this system produces a high-single-digit mean with a
  double-digit average WIN, not a double-digit median trade.

## What the price action actually offers (the ceiling)

Perfect-foresight exit at each trade's post-entry high, by 10:00:
  all entries  mean +25.6%, median +14.0%
  this subset  mean +53.2%
v4 captures ~15% of the perfect-foresight ceiling on the selected subset.
Configurations reaching a double-digit mean in BOTH windows exist only at
risk_pct >= 12%, where n=17 pooled (~8 trades/year) - too thin to deploy.
That is the honest frontier: more selectivity buys a higher mean and costs
sample size, and beyond risk>=8% the sample stops supporting the claim.

## Risks

- NO STOP. Worst trade -36.3%. Two of 41 lost more than 25%, both gap-throughs
  inside a single minute bar. Size assuming a full-loss tail.
- FILL QUALITY IS THE BINDING CONSTRAINT. At 5% slip-through the mean falls to
  +4.76%. An ATR trail on a $3 small cap can sit inside the spread. Only live
  fills settle this.
- n=41 over two years. Both windows agree in sign and the effect is monotone
  in selectivity, but this is a small sample and the selection grid was
  searched, so some optimism is baked in.
- Survivorship: the delisted-universe probe found 2 entries, both winners, so
  no evidence of a hidden disaster population - but n=2.
