# Momentum First-Pullback Backtest v1 (2025-08-11 -> 2026-08-08)

Universe: active US equities (survivorship-biased), open-gap >=10%, open $2-20, morning(<=09:45) volume >=5x 50d avg, top 6 gaps/day. Float pillar NOT applied (no historical float).
Fills: entry +0.5%, exits -0.5%, stops filled 1% through. Spec: momentum_spec_v1.md (frozen before this backtest).

Funnel: 1352 candidate-days -> 373 failed morning relvol, 50 no completed pattern, 831 pullback DQ, 0 data errors, 98 TRADES
DQ breakdown: {'closed below 9EMA': 34, 'retrace>50%': 536, 'heavy red vol in pullback': 144, 'closed below VWAP': 117}

## Distribution (after 0.5%/side slippage)
Win rate: 32/98 = 32.7%
R-multiple: n=98 mean=-0.10 p25=-1.07 med=-0.60 p75=+0.20 min=-1.28 max=+9.13
Return % : n=98 mean=-1.04 p25=-4.84 med=-2.49 p75=+1.18 min=-18.67 max=+28.88
Sum R = -9.7 over 98 trades (expectancy -0.099 R/trade)

## Exit reasons
  stop           n=  38  meanR=-1.11  mean%=-6.07
  topping_tail   n=  26  meanR=+0.76  mean%=+3.38
  material_red   n=  20  meanR=+0.87  mean%=+4.47
  heavy_red      n=   7  meanR=+0.05  mean%=-1.14
  ema_break      n=   6  meanR=-0.76  mean%=-6.32
  slowdown       n=   1  meanR=-0.49  mean%=-2.70

## Cost stress (slippage per side)
  0.00%/side: expectancy +0.170 R/trade, sum +16.7, WR 35%
  0.25%/side: expectancy +0.024 R/trade, sum +2.3, WR 33%
  0.50%/side: expectancy -0.100 R/trade, sum -9.8, WR 33%
  1.00%/side: expectancy -0.297 R/trade, sum -29.1, WR 26%

## Initial-condition analysis (quartiles of each metric, EXPLORATORY)
(multiple comparisons - treat as hypothesis-generating, not conclusions)
### gap_pct
  Q1 [10.2..24.7]: n=24 WR=38% meanR=+0.32 medR=-0.45
  Q2 [25.0..41.5]: n=24 WR=42% meanR=-0.27 medR=-0.47
  Q3 [41.5..87.0]: n=24 WR=25% meanR=-0.15 medR=-0.62
  Q4 [87.9..1200.7]: n=26 WR=27% meanR=-0.28 medR=-0.67
### relvol_0945
  Q1 [5.3..10.6]: n=24 WR=29% meanR=-0.11 medR=-0.90
  Q2 [11.0..41.0]: n=24 WR=38% meanR=+0.04 medR=-0.55
  Q3 [42.5..211.3]: n=24 WR=29% meanR=-0.06 medR=-0.46
  Q4 [217.5..19053.3]: n=26 WR=35% meanR=-0.25 medR=-0.67
### open_px
  Q1 [2.0..3.6]: n=24 WR=33% meanR=+0.28 medR=-0.88
  Q2 [3.8..6.5]: n=24 WR=29% meanR=-0.34 medR=-0.68
  Q3 [6.5..8.9]: n=24 WR=38% meanR=-0.08 medR=-0.50
  Q4 [8.9..19.4]: n=26 WR=31% meanR=-0.24 medR=-0.45
### entry_min
  Q1 [3.0..11.0]: n=24 WR=25% meanR=-0.57 medR=-1.04
  Q2 [11.0..37.0]: n=24 WR=29% meanR=-0.21 medR=-0.55
  Q3 [38.0..76.0]: n=24 WR=29% meanR=+0.10 medR=-0.60
  Q4 [77.0..162.0]: n=26 WR=46% meanR=+0.25 medR=-0.20
### squeeze_pct
  Q1 [10.1..12.0]: n=24 WR=29% meanR=+0.21 medR=-0.41
  Q2 [12.1..15.9]: n=24 WR=38% meanR=-0.09 medR=-0.65
  Q3 [16.1..26.9]: n=24 WR=33% meanR=-0.12 medR=-0.47
  Q4 [27.1..372.1]: n=26 WR=31% meanR=-0.37 medR=-1.04
### retrace_pct
  Q1 [5.6..22.7]: n=24 WR=38% meanR=-0.23 medR=-0.58
  Q2 [22.9..32.3]: n=24 WR=42% meanR=+0.16 medR=-0.33
  Q3 [32.6..37.5]: n=24 WR=25% meanR=-0.18 medR=-0.73
  Q4 [37.6..50.0]: n=26 WR=27% meanR=-0.15 medR=-0.65
### risk_pct
  Q1 [0.2..2.0]: n=24 WR=38% meanR=+0.38 medR=-0.54
  Q2 [2.1..3.5]: n=24 WR=38% meanR=-0.14 medR=-0.67
  Q3 [3.6..5.7]: n=24 WR=21% meanR=-0.40 medR=-0.53
  Q4 [6.0..18.4]: n=26 WR=35% meanR=-0.23 medR=-0.77

## Time-half split
  H1 (2025-08..2026-02): n=36 WR=36% expectancy -0.105 R/trade
  H2 (2026-02..2026-08): n=62 WR=31% expectancy -0.096 R/trade

## Concentration check
  Top-5 symbols by summed R: EDBL +8.3, GSIT +5.8, IOTR +5.4, ATPC +3.0, PMI +2.5
  Excluding top-5 winners: expectancy -0.377 R/trade over 92 trades
