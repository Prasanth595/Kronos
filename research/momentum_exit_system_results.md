# Exit-system search (initial stop x activation x trail)

Scored on IS n=189; OOS n=120 held out of selection.
Fills: 0.5%/side + 2% slip through stops. Flat 10:00 ET.

## Top 15 configurations by IS mean
    stop   act  trail  IS mean  IS med  IS WR  OOS mean  OOS med  OOS WR  OOSp10
    None     4      3    +1.21    +0.4    54%     +1.25     +1.0     58%    -6.6
    None   dip      2    +1.16    +3.9    62%     +1.20     +4.7     65%   -22.8
    None    15      2    +1.14    +9.5    57%     -0.07     +8.4     58%   -27.3
    None   dip      5    +1.09    +2.0    57%     +0.27     +1.8     61%   -22.8
    None     6      2    +1.09    +2.1    79%     +1.51     +3.1     80%   -17.0
    None   dip      3    +1.07    +3.1    60%     +0.76     +3.8     65%   -22.8
    None    15      3    +1.04    +8.4    57%     -0.42     +7.9     58%   -27.3
    None     4   None    +0.97    +3.5    87%     +0.94     +3.5     87%    -6.6
    None    15     12    +0.85    -0.2    48%     -2.75     +0.3     53%   -27.3
    None     6      3    +0.81    +1.4    76%     +0.86     +2.3     77%   -17.0
    None   dip      8    +0.70    +0.3    52%     -0.68     +0.2     52%   -22.8
    None    10      2    +0.66    +5.4    63%     -0.43     +5.7     65%   -26.7
    None   dip     12    +0.62    -2.1    40%     -2.65     -2.8     42%   -22.8
    None     6   None    +0.58    +5.5    79%     +0.67     +5.5     80%   -17.0
    None     4      5    +0.52    -1.1    41%     +0.70     -0.4     48%    -6.6

## SELECTED ON IS: stop None, activation 4, trail 3
  window      n    WR     mean     p10     p25     med     p75     p90      max      min
  IS        189   54%    +1.21    -4.8    -1.5    +0.4    +3.1    +8.2   +233.8    -36.3
  OOS       120   58%    +1.25    -6.6    -1.4    +1.0    +5.0    +8.5    +71.5    -33.0
  POOL      309   56%    +1.23    -5.5    -1.4    +0.5    +3.8    +8.4   +233.8    -36.3

## Robustness of the selected config
  variant                            IS      OOS     POOL
  0.5% slip, 0% thru              +3.04    +3.07    +3.05
  0.5% slip, 2% thru              +1.21    +1.25    +1.23
  0.5% slip, 5% thru              -1.53    -1.48    -1.51
  1.0% slip, 2% thru              +0.20    +0.24    +0.22
  1.0% slip, 5% thru              -2.51    -2.46    -2.49
  hold to close, 2% thru          +0.87    +0.96    +0.90

## Neighbourhood of the selection (POOL mean, 2% thru)
  stop/trail      None       2       3       5       8      12
  None           +0.96   +0.91   +1.23   +0.59   -0.18   -1.81
  20             -0.01   -0.02   +0.32   -0.28   -0.93   -2.47
  15             -0.39   -0.45   -0.07   -0.58   -1.30   -2.77
  12             -0.49   -0.75   -0.35   -0.81   -1.44   -2.95
  10             -0.71   -1.06   -0.64   -1.04   -1.67   -3.07
  8              -1.15   -1.40   -0.91   -1.27   -1.72   -2.89
  6              -1.65   -1.72   -1.17   -1.42   -1.85   -2.78

## Selected config on 1st-pullback entries only
  IS: n=39 WR=56% mean=-1.08% med=+0.6% p10=-5.5% max=+13.5%
  OOS: n=29 WR=62% mean=+3.63% med=+2.6% p10=-7.2% max=+71.5%
