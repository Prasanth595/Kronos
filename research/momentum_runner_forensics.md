# Runner forensics — what separates the monsters

## A. Post-entry dip depth vs how far it ran AFTER the target filled
   (all faithful entries that reached their target)
   dip bucket          n  med run     p75     p90      max   >50%  med giveback
   no dip (<2%)       17    +26.1   +56.0  +183.8   +320.1    29%         -33.6
   2-5%               41    +17.6   +37.6   +68.0   +225.9    17%         -31.9
   5-10%              45    +20.5   +48.2  +127.3   +611.7    24%         -26.4
   10-20%             41    +21.5   +64.1  +182.7   +367.3    27%         -37.0
   >=20%              41    +11.5   +37.3   +92.6   +153.3    22%         -43.4

## B. Trailing stop width on a 25% runner (mean %/trade, 0.5%/side)

   ALL entries: OOS n=120 IS n=189 pooled n=309
   variant                    OOS      IS    POOL  pool@1%  poolWR  poolMax
   sell all (baseline)      +0.99   +0.44   +0.65    -0.02     65%    +19.4
   trail 3%                 +1.51   +1.09   +1.26    +0.50     65%    +71.0
   trail 5%                 +1.21   +0.80   +0.96    +0.20     65%    +69.2
   trail 8%                 +0.84   +0.52   +0.65    -0.11     65%    +66.6
   trail 10%                +0.53   +0.33   +0.41    -0.34     65%    +64.8
   trail 12%                +0.22   +0.26   +0.25    -0.50     65%    +63.1
   trail 15%                +0.50   +0.27   +0.36    -0.39     62%    +60.4
   trail 20%                -0.05   +0.08   +0.03    -0.72     56%    +56.1
   flat 10:00               +0.25   +0.26   +0.25    -0.50     54%    +77.0

   1st-pullback only: OOS n=29 IS n=39 pooled n=68
   variant                    OOS      IS    POOL  pool@1%  poolWR  poolMax
   sell all (baseline)      +5.70   +1.25   +3.15    +2.49     74%    +19.4
   trail 3%                 +6.67   +1.23   +3.55    +2.79     74%    +24.3
   trail 5%                 +6.24   +0.94   +3.20    +2.44     74%    +23.4
   trail 8%                 +5.67   +0.76   +2.85    +2.10     74%    +22.1
   trail 10%                +5.24   +0.81   +2.70    +1.95     74%    +21.2
   trail 12%                +4.91   +0.62   +2.45    +1.70     74%    +20.3
   trail 15%                +4.95   +0.66   +2.49    +1.74     69%    +31.1
   trail 20%                +4.06   -0.19   +1.62    +0.88     60%    +28.3
   flat 10:00               +2.03   -0.17   +0.77    +0.04     54%    +34.8

## C. What else predicts a big run after the target?
   entry_min:
     Q1 [2.0..28.0] n=46 med run +13.3%  p90 +155.8%  >50%: 24%
     Q2 [28.0..65.0] n=46 med run +14.3%  p90 +89.7%  >50%: 22%
     Q3 [67.0..111.0] n=46 med run +24.3%  p90 +98.3%  >50%: 20%
     Q4 [112.0..164.0] n=47 med run +19.9%  p90 +130.1%  >50%: 28%
   price:
     Q1 [2.1..3.2] n=46 med run +16.8%  p90 +148.8%  >50%: 26%
     Q2 [3.2..4.6] n=46 med run +20.2%  p90 +128.1%  >50%: 24%
     Q3 [4.6..8.3] n=46 med run +22.3%  p90 +142.8%  >50%: 30%
     Q4 [8.3..20.6] n=47 med run +15.1%  p90 +55.0%  >50%: 13%
   risk_pct:
     Q1 [0.1..3.4] n=46 med run +18.1%  p90 +90.4%  >50%: 17%
     Q2 [3.5..5.0] n=46 med run +12.7%  p90 +73.2%  >50%: 17%
     Q3 [5.0..7.7] n=46 med run +16.3%  p90 +128.8%  >50%: 24%
     Q4 [7.7..26.5] n=47 med run +23.9%  p90 +145.2%  >50%: 34%
   n_dq:
     Q1 [0.0..2.0] n=46 med run +14.4%  p90 +84.1%  >50%: 20%
     Q2 [2.0..2.0] n=46 med run +25.7%  p90 +160.0%  >50%: 26%
     Q3 [2.0..4.0] n=46 med run +19.1%  p90 +168.0%  >50%: 28%
     Q4 [4.0..10.0] n=47 med run +17.3%  p90 +77.1%  >50%: 19%
