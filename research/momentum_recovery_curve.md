# Drawdown -> recovery curve (threshold-free) — 291 ticker-days,
  2201 retracement episodes (every dip below a running high counts).

## A. Distribution of ALL retracement depths (no minimum)
   med 6.82%  p75 15.11%  p90 35.24%  p95 44.80%  p99 64.40%  max 87.0%
   episodes per ticker-day reaching at least X%:
     >=1%:7.1  >=2%:6.5  >=3%:5.8  >=4%:5.1  >=5%:4.6  >=6%:4.1  >=8%:3.3  >=10%:2.8  >=12%:2.3  >=15%:1.9  >=20%:1.5  >=25%:1.2  >=30%:1.0

## B. THE RECOVERY CURVE  P(new high | retracement reached >= X%)
     X%   n_ev  event-wtd          95% CI  day-wtd  n_days  t.rec med
      1   2066      86.1% [ 84.5, 87.4]%    67.7%     289         1m
      2   1892      84.9% [ 83.0, 86.4]%    66.6%     288         1m
      3   1686      83.0% [ 81.1, 84.7]%    64.2%     288         2m
      4   1496      80.9% [ 78.9, 82.8]%    61.1%     288         2m
      5   1341      78.7% [ 76.3, 80.7]%    58.0%     288         3m
      6   1205      76.3% [ 73.7, 78.5]%    55.3%     288         4m
      8    969      70.8% [ 67.9, 73.3]%    49.5%     288         7m
     10    807      65.4% [ 62.2, 68.4]%    45.3%     286         9m
     12    680      59.3% [ 55.7, 62.5]%    39.9%     285        15m
     15    554      51.1% [ 47.2, 54.6]%    32.6%     279        21m
     20    431      40.4% [ 35.5, 45.1]%    25.0%     271        25m
     25    345      32.5% [ 27.7, 37.0]%    20.4%     245        32m
     30    285      26.7% [ 21.7, 31.6]%    17.9%     224        42m

## C. Conditional on NO recovery (terminal episode, depth >= X)
     X%     n   terminal depth med/p75   close vs peak med
      1   287         37.5%/49.0%              -30.9%
      2   286         37.6%/49.0%              -30.9%
      3   286         37.6%/49.0%              -30.9%
      4   286         37.6%/49.0%              -30.9%
      5   286         37.6%/49.0%              -30.9%
      6   286         37.6%/49.0%              -30.9%
      8   283         37.6%/49.1%              -30.9%
     10   279         37.6%/49.1%              -31.2%
     12   277         37.8%/49.2%              -31.7%
     15   271         38.0%/49.5%              -31.9%
     20   257         39.2%/50.5%              -33.2%
     25   233         41.1%/50.9%              -34.0%
     30   209         42.2%/51.7%              -36.5%

## D. After recovery at reporting scale X: next-leg advance
   (next >=X% retracement's peak vs the recovered peak)
   X= 2%: n=1021  advance med   +3.8%  p25   +1.7%  p75   +7.3%
   X= 5%: n= 790  advance med   +4.8%  p25   +2.4%  p75   +9.0%
   X= 8%: n= 516  advance med   +7.3%  p25   +3.3%  p75  +14.0%
   X=10%: n= 372  advance med   +9.1%  p25   +4.0%  p75  +16.8%
   X=15%: n= 169  advance med  +13.2%  p25   +5.8%  p75  +25.0%
   X=20%: n=  69  advance med  +16.1%  p25   +6.9%  p75  +34.9%

## E. Window split of the event-weighted curve
   OOS: X2:85%(694) X5:79%(504) X8:72%(383) X10:68%(324) X15:53%(223) X20:45%(184) 
   IS: X2:85%(1198) X5:79%(837) X8:70%(586) X10:64%(483) X15:50%(331) X20:37%(247) 
