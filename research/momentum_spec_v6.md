# Momentum — Spec v6: junction-process policy (FROZEN 2026-08-15)

Frozen BEFORE any code for it runs and BEFORE the blind window is opened.
Reframe: the corrected Cameron setup QUALIFIES a ticker-day; positions are
taken at measured junctions (retracements from the running high), not held
from the crossing candle.

## Rules

QUALIFY  Corrected Cameron scan (five pillars, intraday qualification
         07:00-10:00, $2-20, >=2-candle pullback, prior-candle-high crossing
         per momentum_faithful.py). The moment the first valid crossing
         fires is the qualification event. No position is taken there.
         Junction tracking begins at that bar; the running high starts at
         that bar's high.

JUNCTION When flat: price retraces >=10% from the running high, the ticker
         is ARMED. (Recovery curve: 65% recover; median payoff from -10%
         +19.8%; ~2.8 such junctions/day.)

ENTER    While armed: the first 1-min bar whose high breaks the PRIOR bar's
         high. Fill at prior bar's high + $0.01, +0.5% slippage. This is a
         confirmation entry: the bottom finds us; we never buy a falling
         knife. Max 4 entries per ticker-day.

SIZE     1.0 unit base. 0.5 unit if the just-completed junction reached
         >=20% depth (depth clustering: P(next >=20% | current >=20%) = 39%).

EXIT     In position: when price retraces >=10% from the post-entry running
         high, sell at that crossing. Fill = crossing price, 2% slip-through,
         -0.5% slippage. Then the ticker re-arms (the ongoing retracement
         counts toward the next junction) and may re-enter on confirmation.

ABANDON  Any retracement (flat or in position) reaching >=25% from its
         running high: if in position, exit at the -25% crossing (2% thru,
         -0.5% slip); either way the ticker is DONE for the day.
         (Recovery odds <=33% beyond 25%; terminal state median -37%.)

FLAT     Session close, -0.5% slippage, if still holding.

## Provenance of every number (measured, not searched)

10% junction: EV table peak zone (+5.5%/junction median-based); 25% abandon:
recovery odds collapse; 20% sizing cut: depth clustering +0.38; confirmation
entry: additional-fall table (recovered episodes dip med 5-6% past a naive
crossing buy; failures dip 24-36% past it).

## Validation protocol (binding)

1. BLIND WINDOW: 2023-08-01 .. 2024-08-01, never used anywhere in this
   project. Scanned and scored with zero parameter changes. That result is
   the verdict.
2. 2024-26 windows reported as IN-SAMPLE CONTEXT (every v6 parameter was
   measured on them).
3. Master-table reporting: every qualified ticker-day appears; filters and
   variants are columns, never row removal.
4. No changes after seeing blind results. Failures are recorded.
5. Fill sensitivity reported at 0/2/5% slip-through in all tables.

## Deferred variants (to be pre-registered separately BEFORE testing)

v6.1 LADDER ENTRY: replace confirmation entry with incremental fills on the
way down (e.g. thirds at -5/-10/-15). Measured context: ladder beats lump
entry on price, but failures fill 2.92 rungs vs 1.77 for recoveries
(adverse selection). Spec to be written and frozen before it is scored.

## Known weaknesses at freeze time

- The 10/25/20 depths come from 2024-26 measurements; only the blind window
  tests the framework on unseen data.
- Confirmation entries pay for safety by chasing: entry lands above the
  trough by an unmeasured amount; the backtest measures that cost.
- Fill quality on 1-min triggers in thin names remains the binding
  assumption of every result in this project.
- Junction stats were measured on FULL sessions including afternoon; the
  policy trades the full session, where afternoon liquidity is thinner.
