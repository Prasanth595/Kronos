# Momentum First-Pullback Backtest v1 (2024-08-01 -> 2025-08-01)

Universe: active US equities (survivorship-biased), open-gap >=10%, open $2-20, morning(<=09:45) volume >=5x 50d avg, top 6 gaps/day. Float pillar NOT applied (no historical float).
Fills: entry +0.5%, exits -0.5%, stops filled 1% through. Spec: momentum_spec_v1.md (frozen before this backtest).

Funnel: 1213 candidate-days -> 447 failed morning relvol, 27 no completed pattern, 668 pullback DQ, 0 data errors, 71 TRADES
DQ breakdown: {'closed below VWAP': 104, 'retrace>50%': 438, 'heavy red vol in pullback': 102, 'closed below 9EMA': 23, 'trigger outside window': 1}

## Distribution (after 0.5%/side slippage)
Win rate: 22/71 = 31.0%
R-multiple: n=71 mean=-0.10 p25=-1.05 med=-0.42 p75=+0.11 min=-1.28 max=+5.28
Return % : n=71 mean=-1.27 p25=-4.28 med=-2.22 p75=+0.69 min=-12.38 max=+28.83
Sum R = -7.4 over 71 trades (expectancy -0.105 R/trade)

## Exit reasons
  material_red   n=  25  meanR=+0.46  mean%=+1.12
  stop           n=  23  meanR=-1.12  mean%=-5.82
  topping_tail   n=  17  meanR=+0.25  mean%=+1.59
  ema_break      n=   3  meanR=-0.70  mean%=-7.38
  heavy_red      n=   2  meanR=+2.50  mean%=+6.18
  slowdown       n=   1  meanR=-0.39  mean%=-1.42

## Cost stress (slippage per side)
  0.00%/side: expectancy +0.211 R/trade, sum +15.0, WR 37%
  0.25%/side: expectancy +0.035 R/trade, sum +2.5, WR 32%
  0.50%/side: expectancy -0.105 R/trade, sum -7.4, WR 31%
  1.00%/side: expectancy -0.320 R/trade, sum -22.7, WR 23%

## Initial-condition analysis (quartiles of each metric, EXPLORATORY)
(multiple comparisons - treat as hypothesis-generating, not conclusions)
### gap_pct
  Q1 [11.0..24.8]: n=17 WR=24% meanR=-0.41 medR=-0.81
  Q2 [25.0..48.9]: n=17 WR=41% meanR=+0.32 medR=-0.42
  Q3 [50.0..85.5]: n=17 WR=35% meanR=-0.07 medR=-0.26
  Q4 [87.2..388.9]: n=20 WR=25% meanR=-0.24 medR=-0.31
### relvol_0945
  Q1 [5.3..15.1]: n=17 WR=41% meanR=-0.10 medR=-0.67
  Q2 [15.8..53.0]: n=17 WR=29% meanR=-0.09 medR=-0.30
  Q3 [53.7..195.9]: n=17 WR=24% meanR=-0.39 medR=-1.04
  Q4 [196.1..10550.6]: n=20 WR=30% meanR=+0.12 medR=-0.30
### open_px
  Q1 [2.0..4.1]: n=17 WR=35% meanR=-0.28 medR=-0.39
  Q2 [4.2..6.5]: n=17 WR=35% meanR=-0.20 medR=-0.71
  Q3 [6.6..11.4]: n=17 WR=35% meanR=+0.58 medR=-0.16
  Q4 [11.8..19.9]: n=20 WR=20% meanR=-0.46 medR=-0.65
### entry_min
  Q1 [3.0..12.0]: n=17 WR=24% meanR=-0.53 medR=-0.76
  Q2 [15.0..35.0]: n=17 WR=35% meanR=+0.04 medR=-0.25
  Q3 [35.0..67.0]: n=17 WR=24% meanR=-0.11 medR=-0.39
  Q4 [70.0..157.0]: n=20 WR=40% meanR=+0.14 medR=-0.44
### squeeze_pct
  Q1 [10.3..12.5]: n=17 WR=35% meanR=+0.00 medR=-0.77
  Q2 [12.6..18.3]: n=17 WR=24% meanR=-0.33 medR=-0.47
  Q3 [18.7..32.6]: n=17 WR=29% meanR=-0.08 medR=-0.27
  Q4 [35.0..277.5]: n=20 WR=35% meanR=-0.03 medR=-0.26
### retrace_pct
  Q1 [1.6..22.6]: n=17 WR=53% meanR=+0.21 medR=+0.01
  Q2 [25.0..34.5]: n=17 WR=24% meanR=-0.17 medR=-0.32
  Q3 [35.3..40.5]: n=17 WR=24% meanR=-0.29 medR=-1.05
  Q4 [41.7..49.9]: n=20 WR=25% meanR=-0.16 medR=-0.41
### risk_pct
  Q1 [0.1..1.3]: n=17 WR=47% meanR=+0.54 medR=-0.47
  Q2 [1.4..3.4]: n=17 WR=18% meanR=-0.53 medR=-1.10
  Q3 [3.9..5.9]: n=17 WR=35% meanR=-0.01 medR=-0.26
  Q4 [6.1..22.4]: n=20 WR=25% meanR=-0.37 medR=-0.39

## Time-half split
  H1 (2025-08..2026-02): n=34 WR=26% expectancy +0.016 R/trade
  H2 (2026-02..2026-08): n=37 WR=35% expectancy -0.215 R/trade

## Concentration check
  Top-5 symbols by summed R: PRHI +5.3, CING +4.0, UCFI +3.5, LTBR +3.1, TPST +2.7
  Excluding top-5 winners: expectancy -0.392 R/trade over 66 trades
