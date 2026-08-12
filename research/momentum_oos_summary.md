# Momentum first-pullback — out-of-sample test of exit schemes (2026-08-12)

Specs v2 and v3 were written and committed BEFORE the out-of-sample window was
touched (commits 4d72621, bc9f889). Pass/fail criteria were declared in those
files in advance.

- IN-SAMPLE  (IS):  2025-08-11 .. 2026-08-08, n=98 entries
- OUT-OF-SAMPLE (OOS): 2024-08-01 .. 2025-08-01, n=71 entries
- Entries are IDENTICAL across all exit schemes (v1 entry logic untouched).

## 1. v1 entry logic replicates out-of-sample

                    IS            OOS
  trades            99            71
  win rate          32.3%         31.0%
  expectancy       -0.105 R      -0.105 R
  funnel           7% of cands   6% of cands

The v1 indicator-exit result reproduced to three decimals on data it had never
seen. The entry engine and the cost problem are both stable and real.

## 2. Exit-scheme comparison (mean return per trade, 0.5%/side)

  scheme                     IS        OOS      OOS criteria
  ------------------------------------------------------------
  v2 dip-conditioned TP    +5.23%    +3.61%    ALL 5 PASS
  control flat +10%        +2.98%    -0.66%    FAIL (a,b,c,d)
  v3-dipcond ladder        +1.19%    +1.04%    FAIL (c)
  v3-nostop ladder         +1.03%    +0.31%    FAIL (b,c)
  v3-pbstop ladder         -1.54%    -1.81%    FAIL (a,b,c,d)
  v1 indicator exits       -1.06%    -1.05%    FAIL

v2 OOS detail: n=71, WR 75%, mean +3.61%, median +7.46%, p25 +1.08%,
worst -36.9%. At 1.0%/side: +2.99%. Excluding top-5 symbols: +2.41%.
H1 +5.39%, H2 +2.07%. All five pre-registered criteria met.

## 3. The laddered scale-out (v3) does not work here

Selling 25% at +5% caps the tranche that has to pay for the losers, and the
breakeven ratchet after B1 converts many would-be winners into ~-0.4% scratches
(v3 median return IS +4.94%, OOS -0.37%). The ratchet also fires exactly during
the deep post-entry shakeout the movement study documented, so it exits before
the recovery it was waiting for. Both windows agree.

v3-pbstop is the worst scheme tested in both windows. That is the third
independent measurement pointing at the same conclusion: on this pattern, a
stop at the pullback low is the single most damaging choice.

## 4. The conditioning, not the numbers, is load-bearing

Perturbing the v2 schedule on OOS data (mean %/trade, 0.5%/side):

  frozen  20/15/12/8/4   +3.61
  shift -4               +3.66      shift +2               +3.24
  shift -2               +3.71      shift +4               +3.37
  steeper 30/20/12/6/2   +5.18      flatter 14/12/10/8/6   +1.55
  REMOVE conditioning (flat 12)  +0.32
  REMOVE conditioning (flat 8)   -0.01
  REMOVE conditioning (flat 10)  -0.66

Every perturbation that KEEPS the dip-conditioning stays positive; every
variant that REMOVES it collapses to zero. The specific breakpoints are not
what is producing the result, which is the opposite of what a curve-fit looks
like. The flat +10% control passed IS and failed OOS - i.e. the control was
the fitted thing, and the conditioning is what survived.

Mechanism: lowering the profit bar after a dip converts "dipped, partially
recovered" trades into small wins instead of letting them ride to a large
time-exit loss. It is a direct application of the recovery matrix (recovery
probability decays with dip depth).

## 5. Survivorship check — measured, not assumed

The universe is Alpaca ACTIVE assets, so pumps that later delisted are absent.
A no-stop scheme is maximally exposed to that. Measured directly by rescanning
the DELISTED universe over the same OOS window:

  inactive US equities                     19,198
  non-OTC, clean symbols                    1,322
  five-pillar candidate days                   36
  valid first-pullback entries                  2
  v2 result on those entries      GV +14.4%, NCI +14.4%  (mean +14.4%)

Both delisted entries were WINNERS. Including them would have raised the OOS
mean, not lowered it. n=2 is too small to be conclusive, but the specific fear
- that the missing population is full of catastrophic no-stop losses - is not
supported by what is measurable.

## 6. Status and what is NOT established

v2 meets every pre-registered bar on unseen data, with a mechanism story, a
fragility test that points the right way, and a survivorship probe that came
back clean. That is the strongest evidence any candidate in this project has
produced.

Still not established:
- Real fill quality. Every number assumes a resting limit fills AT the target
  and entries pay 0.5%. Forward paper log is the only honest read.
- 25% of trades lose, 18% lose >=10%, and the worst was -36.9% with NO stop.
  Position sizing must assume a full-loss tail.
- Halt behaviour is not modelled beyond the bar data.
- Two windows, n=169 combined, one pattern, one asset class.

Next: run v2 exits in the nightly forward log alongside v1 so live fills
accumulate against both.
