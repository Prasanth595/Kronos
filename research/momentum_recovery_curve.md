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

## D2. Next-leg advance: full percentiles (added on request)

  X%      n      p5     p10     p25     med     p75      p90      p95       p99       max    mean
   2   1021    +0.4    +0.7    +1.7    +3.8    +7.3    +13.4    +18.1     +30.7     +61.2    +5.7
   5    790    +0.5    +1.0    +2.4    +4.8    +9.0    +15.7    +19.6     +32.8     +61.2    +7.0
   8    516    +0.6    +1.3    +3.3    +7.3   +14.0    +19.9    +24.9     +39.2     +61.2    +9.5
  10    372    +0.6    +1.5    +4.0    +9.1   +16.8    +24.6    +30.2     +42.3     +61.2   +11.5
  15    169    +0.6    +2.0    +5.8   +13.2   +25.0    +37.5    +49.7     +61.3     +69.5   +17.4
  20     69    +1.1    +2.8    +6.9   +16.1   +34.9    +49.5    +60.0     +97.7    +120.9   +23.3

Share of legs advancing >= threshold:
  X%      n    >=2%    >=5%   >=10%   >=20%   >=50%   >=100%
   2   1021     71%     39%     15%      3%      0%      0%
   5    790     79%     49%     21%      5%      0%      0%
   8    516     83%     62%     37%     10%      0%      0%
  10    372     85%     69%     47%     17%      0%      0%
  15    169     90%     77%     59%     36%      5%      0%
  20     69     91%     83%     67%     41%     10%      1%

Windows: med/p90 OOS vs IS agree within ~1pt at X2/X5/X10; X20 thin (30/39).
Note: advance is measured next-peak vs recovered-peak, so it is positive by
construction; p5 ~ +0.5% means 1 in 20 legs barely extends past the old high.

## D3. Order differentiation (added on request)

P(recover) and next-leg advance by ORDER of the retracement within the day,
at fixed reporting scales:

X=2%:  k=1 85% | k=2 83% | k=3 78% | k4+ 81%   adv med +3.6/+4.2/+3.8/+3.5
X=5%:  k=1 78% | k=2 79% | k=3 78% | k4+ 78%   adv med +4.1/+5.3/+4.0/+4.8
X=10%: k=1 68% | k=2 62% | k=3 65% | k4+ 71%   adv med +7.3/+7.0/+9.1/+8.7

Depth-band control (X=5 events): within every depth band, order is flat
(e.g. 20%+: 41/46/39% for k=1/2/3). ORDER CARRIES NO MEASURABLE
INFORMATION ONCE DEPTH IS KNOWN; depth is the sufficient statistic among
the variables measured.

CAUTION on the depth-band numbers (5-8%: ~99-100% recover; 12-20%: ~90-96%;
20%+: ~40%): banding on an episode's FINAL depth is ex-post conditioning -
an episode "ends" shallow mostly because it recovered, and failures keep
deepening (terminal med 37%). The knowable-in-real-time object remains the
survival curve P(recover | depth has REACHED X), section B. The band table's
legitimate reading: failures are almost never shallow - if a retracement is
going to kill the day, it does so by cutting deep, not by stalling small.
