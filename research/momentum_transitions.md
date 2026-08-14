# Post-entry state sequences — corrected Cameron entries (n=291)
Pullback threshold T=5% of the running high (measurement convention).
All figures descriptive; nothing optimized.

## 1. First level touched after entry (race among +-2/5/10%)
   first touch          2:   45  (15%)
   first touch          5:    0  (0%)
   first touch         10:    0  (0%)
   first touch         -2:  144  (49%)
   first touch         -5:    0  (0%)
   first touch        -10:    0  (0%)
   first touch  ambiguous:  100  (34%)
   first touch       none:    2  (1%)

## 2. Conditional races (u/d same bar counted adverse)
   reached +5% (n=233): next +10% first 42% | fell to +0% first 58% | neither 0%
   reached +10% (n=186): next +20% first 46% | fell to +0% first 53% | neither 1%
   reached +10% (n=186): next +15% first 40% | fell to +5% first 60% | neither 0%
   reached +2% (n=263): next +5% first 44% | fell to -2% first 56% | neither 0%

## 3. How many >=5% pullbacks occur per ticker-day
   0 pullbacks:    3 (1%)
   1 pullbacks:   62 (21%)
   2 pullbacks:   47 (16%)
   3 pullbacks:   40 (14%)
   4 pullbacks:   36 (12%)
   5 pullbacks:   28 (10%)
   6 pullbacks:   16 (5%)
   mean 4.5 pullback events/day

## 4. Expansion legs (size of each squeeze)
   leg 1 = entry->first peak; leg k = trough(k-1)->peak k
   leg 1: n=288  gain med   +2.9%  p25   +1.3%  p75   +6.1%  dur med 0min
   leg 2: n=226  gain med  +18.0%  p25  +12.0%  p75  +28.0%  dur med 3min
   leg 3: n=179  gain med  +19.0%  p25  +12.9%  p75  +32.9%  dur med 3min
   leg 4+: n=609  gain med  +19.0%  p25  +13.5%  p75  +29.0%  dur med 4min

## 5. Pullback events by order (the transition table)
   PB#     n P(new high)  depth med    p25    p75 peak@ med  t.peak  t.rec
   1     288         78%      11.6%   7.8%  26.9%     +2.9%      0m     4m
   2     226         79%      14.0%   7.8%  30.6%     +8.7%      6m     5m
   3     179         78%      14.0%   8.6%  28.4%    +16.2%     20m     5m
   4+    609         78%      13.1%   8.5%  24.8%    +47.2%    104m     4m
   (depth = % off the peak; peak@ = peak level vs entry; t.peak =
   minutes entry->peak; t.rec = minutes pullback-start->new high)

## 6. Failed pullbacks: where they end up
   PB1 failures n=62: depth by close med 36.9% p75 46.5% max 78.0%
   PB2 failures n=47: depth by close med 39.3% p75 50.7% max 84.4%
   PB3 failures n=40: depth by close med 37.4% p75 49.1% max 70.6%
   PB4+ failures n=137: depth by close med 37.5% p75 49.0% max 87.0%

## 7. Path dependence checks
   P(PB2 new high | PB1 shallow (<8%)): 79%  (n=77)
   P(PB2 new high | PB1 deep (>=8%)): 79%  (n=149)
   P(new high) by pullback START time (all PB orders):
     start  0-60min:  78%  (n=829)
     start   60-120:  76%  (n=172)
     start  120-240:  82%  (n=187)
     start     240+:  72%  (n=114)

## 8. Sensitivity: same transition probs at T=8%
   PB1: n=288  P(new high) 70%
   PB2: n=202  P(new high) 72%
   PB3: n=143  P(new high) 69%
   PB4+: n=369  P(new high) 74%

## 9. Window stability (T=5%)
   OOS: PB1 81% (n=108)  PB2 77% (n=88)  PB3 78% (n=68)  PB4+ 77% (n=223)  
   IS: PB1 77% (n=180)  PB2 80% (n=138)  PB3 77% (n=111)  PB4+ 78% (n=386)  
