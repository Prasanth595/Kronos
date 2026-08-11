# Momentum First-Pullback Backtest v1 (2025-08-11 -> 2026-08-08)

Universe: active US equities (survivorship-biased), open-gap >=10%, open $2-20, morning(<=09:45) volume >=5x 50d avg, top 6 gaps/day. Float pillar NOT applied (no historical float).
Fills: entry +0.5%, exits -0.5%, stops filled 1% through. Spec: momentum_spec_v1.md (frozen before this backtest).

Funnel: 1357 candidate-days -> 370 failed morning relvol, 50 no completed pattern, 838 pullback DQ, 0 data errors, 99 TRADES
DQ breakdown: {'closed below 9EMA': 35, 'retrace>50%': 541, 'heavy red vol in pullback': 145, 'closed below VWAP': 117}

## Distribution (after 0.5%/side slippage)
Win rate: 32/99 = 32.3%
R-multiple: n=99 mean=-0.10 p25=-1.07 med=-0.62 p75=+0.19 min=-1.28 max=+9.13
Return % : n=99 mean=-1.06 p25=-4.80 med=-2.66 p75=+1.08 min=-18.67 max=+28.88
Sum R = -10.4 over 99 trades (expectancy -0.105 R/trade)

## Exit reasons
  stop           n=  38  meanR=-1.11  mean%=-6.11
  topping_tail   n=  25  meanR=+0.82  mean%=+3.71
  material_red   n=  21  meanR=+0.80  mean%=+4.10
  heavy_red      n=   8  meanR=-0.05  mean%=-1.37
  ema_break      n=   6  meanR=-0.76  mean%=-6.32
  slowdown       n=   1  meanR=-0.49  mean%=-2.70

## Cost stress (slippage per side)
  0.00%/side: expectancy +0.163 R/trade, sum +16.2, WR 34%
  0.25%/side: expectancy +0.017 R/trade, sum +1.7, WR 32%
  0.50%/side: expectancy -0.105 R/trade, sum -10.4, WR 32%
  1.00%/side: expectancy -0.302 R/trade, sum -29.9, WR 25%

## Initial-condition analysis (quartiles of each metric, EXPLORATORY)
(multiple comparisons - treat as hypothesis-generating, not conclusions)
### gap_pct
  Q1 [10.2..24.4]: n=24 WR=33% meanR=+0.17 medR=-0.59
  Q2 [24.7..39.9]: n=24 WR=42% meanR=-0.15 medR=-0.47
  Q3 [41.5..76.3]: n=24 WR=29% meanR=-0.10 medR=-0.53
  Q4 [87.0..1200.7]: n=27 WR=26% meanR=-0.31 medR=-0.67
### relvol_0945
  Q1 [5.3..11.0]: n=24 WR=29% meanR=-0.11 medR=-0.90
  Q2 [11.5..41.0]: n=24 WR=38% meanR=+0.07 medR=-0.55
  Q3 [42.5..211.3]: n=24 WR=29% meanR=-0.07 medR=-0.46
  Q4 [217.5..19053.3]: n=27 WR=33% meanR=-0.28 medR=-0.68
### open_px
  Q1 [2.0..3.6]: n=24 WR=33% meanR=+0.28 medR=-0.88
  Q2 [3.8..6.4]: n=24 WR=29% meanR=-0.34 medR=-0.68
  Q3 [6.4..8.9]: n=24 WR=33% meanR=-0.12 medR=-0.58
  Q4 [8.9..19.7]: n=27 WR=33% meanR=-0.22 medR=-0.40
### entry_min
  Q1 [3.0..11.0]: n=24 WR=25% meanR=-0.57 medR=-1.04
  Q2 [11.0..37.0]: n=24 WR=29% meanR=-0.21 medR=-0.57
  Q3 [38.0..73.0]: n=24 WR=29% meanR=+0.10 medR=-0.60
  Q4 [75.0..162.0]: n=27 WR=44% meanR=+0.22 medR=-0.30
### squeeze_pct
  Q1 [10.1..12.0]: n=24 WR=29% meanR=+0.23 medR=-0.41
  Q2 [12.0..15.8]: n=24 WR=38% meanR=-0.09 medR=-0.65
  Q3 [15.9..25.9]: n=24 WR=33% meanR=-0.15 medR=-0.49
  Q4 [26.8..372.1]: n=27 WR=30% meanR=-0.37 medR=-1.04
### retrace_pct
  Q1 [5.6..22.7]: n=24 WR=38% meanR=-0.20 medR=-0.58
  Q2 [22.9..32.3]: n=24 WR=42% meanR=+0.16 medR=-0.33
  Q3 [32.6..37.6]: n=24 WR=25% meanR=-0.20 medR=-0.85
  Q4 [37.8..50.0]: n=27 WR=26% meanR=-0.17 medR=-0.68
### risk_pct
  Q1 [0.2..2.1]: n=24 WR=42% meanR=+0.44 medR=-0.37
  Q2 [2.1..3.4]: n=24 WR=29% meanR=-0.46 medR=-0.74
  Q3 [3.5..5.6]: n=24 WR=21% meanR=-0.20 medR=-0.55
  Q4 [5.7..18.4]: n=27 WR=37% meanR=-0.19 medR=-0.66

## Time-half split
  H1 (2025-08..2026-02): n=38 WR=34% expectancy -0.147 R/trade
  H2 (2026-02..2026-08): n=61 WR=31% expectancy -0.078 R/trade

## Concentration check
  Top-5 symbols by summed R: EDBL +8.3, GSIT +5.8, IOTR +5.4, ATPC +3.0, PMI +2.5
  Excluding top-5 winners: expectancy -0.380 R/trade over 93 trades
