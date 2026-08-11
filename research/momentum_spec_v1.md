# Momentum First-Pullback — Mechanical Spec v1 (pre-registered 2026-08-11)

Sleeve E candidate. Source: momentum_daytrading_notes.md (Ross Cameron first-pullback).
This file freezes the MECHANICAL translation before any paper results exist.
Threshold choices marked [MECH] are our judgment calls where the source uses discretion;
they may be revised only by backtest evidence, never by peeking at forward results.

## Universe scan (daily, after close, via Alpaca screener + FMP float)

Pillars (all required unless noted):
1. Relative volume >= 5x 50-day average
2. Day gain >= +10%
3. Price $2-$20 at scan time
4. Float < 20M shares (FMP shares-float; if unavailable, flag float_unknown and log
   the trade separately - does not count toward gauntlet n)
5. Gap-up >= +2% vs prior close
Catalyst pillar: not checkable mechanically; waived when the stock is a top-3 gainer
on the day (per source: waived for the obvious leading gainer).

## Session replay (1-min bars, SIP, 04:00 ET premarket onward)

- VWAP: cumulative from 04:00 ET. 9EMA: on 1-min closes.
- Entry window: 07:00-09:45 ET. Hard flat: 10:00 ET.
- [MECH] Move detection starts at 07:00 ET (source watches scanners from 07:00;
  pre-7:00 premarket wiggles do not consume the "first pullback"). VWAP/9EMA still
  accumulate from 04:00.
- Initial move: swing_low = low since 07:00; squeeze active when running high
  >= swing_low * 1.10.
- Pullback: begins when a candle fails to make a new session high. Track pullback_low.
- Disqualifiers (any -> no trade on this ticker today; FIRST pullback only):
  a. Retrace > 50% of (squeeze_high - swing_low)
  b. [MECH] Red pullback candle with volume > 1.25x mean green-candle volume of the
     initial move (source: "high volume on red candles")
  c. Any pullback candle CLOSES below VWAP
  d. Any pullback candle CLOSES below 9EMA
- Entry trigger: after >= 2 pullback candles, first candle whose high breaks the prior
  candle's high. Fill = prior candle's high + $0.01, + 0.5% slippage.
- Stop: pullback_low. Assumed fill 1% below stop (gap/halt risk).

## Exits (evaluated on each completed 1-min candle, first hit wins)

1. STOP: bar low <= stop -> filled at stop * 0.99.
2. [MECH] TOPPING TAIL: upper wick >= 2x body AND upper wick >= 50% of bar range
   -> exit at close.
3. [MECH] HEAVY RED (tape-burst proxy): red candle with volume >= 2x the preceding
   green candle's volume -> exit at close.
4. [MECH] MATERIAL RED (source: "a red candle" respected with discretion): red candle
   with body >= 0.5x entry risk (entry - stop) -> exit at close.
5. [MECH] BUYING SLOWDOWN: 3 consecutive bars, each volume < 0.5x entry-bar volume,
   with no net price gain across them -> exit at close.
6. 9EMA BREAK: close below 9EMA -> exit at close.
7. TIME: flat at 10:00 ET open, no exceptions.
- No profit cap (per source). 2:1 is a selection concept, not an auto-target.
- All exits less 0.5% slippage. One trade per ticker per day; first valid pullback only.

## Paper accounting

- Log in R-multiples: R = (exit - entry) / (entry - stop), plus raw %.
- Notional: risk 1% of a nominal $10,000 sleeve-E paper account per trade ($100 risk).
- NOT in AGG-MAX book weights until adapted gauntlet passes:
  cross-ticker replication (survives dropping top-5 winners), both time halves in
  backtest, n >= 100 combined, costs survive 1% round-trip stress.
- Data honesty: replay uses post-close data but rules are 100% mechanical and frozen
  here; no discretionary element exists that could exploit hindsight.

## Known infidelities vs source (accepted)

- No Level 2 / tape exits (3 of 6 source indicators) -> our exits are strictly worse
  than the source's skilled execution. If edge survives anyway, strong result.
- No halt modeling in fills beyond the 1%-through-stop assumption.
- No news/catalyst read; hot-sector pillar unchecked.
- Walk-away rules 1-2 (give back half day's profit / max daily loss) inactive at
  1-trade-per-ticker paper scale; revisit if concurrency added.
