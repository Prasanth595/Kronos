# Runner-tranche test — first-pullback entries only
Sell 75% at the v2 dip-conditioned target; the last 25% rides.
All figures %/trade after 0.5%/side slippage (last column 1.0%).

### OOS  (n=29)
  variant                      WR     p25     med     p75     p90      max    mean     @1%
  v2 sell all (baseline)      79%    +3.5    +7.5   +14.4   +14.4    +19.4   +5.70   +5.05
  25% runner, trail 20%       69%    -0.8    +6.5   +10.7   +16.0    +17.4   +4.06   +3.32
  25% runner, trail 30%       66%    -3.4    +4.7    +7.6   +13.3    +20.6   +2.30   +1.58
  25% runner, trail 40%       62%    -4.0    +3.2    +7.5   +10.5    +16.8   +1.04   +0.34
  25% runner, trail 50%       55%    -4.0    +1.2    +6.3   +10.8    +15.9   +0.18   -0.52
  25% runner, flat 10:00      59%    -3.7    +2.9    +7.8   +15.2    +18.8   +2.03   +1.31
  25% runner, to close        55%    -4.0    +1.2    +6.3   +11.7    +32.6   +0.70   +0.00

### IS  (n=39)
  variant                      WR     p25     med     p75     p90      max    mean     @1%
  v2 sell all (baseline)      69%    -4.6    +3.5   +11.4   +14.4    +19.4   +1.25   +0.58
  25% runner, trail 20%       54%    -4.6    +0.6    +7.8   +11.6    +28.3   -0.19   -0.93
  25% runner, trail 30%       49%    -5.1    -0.4    +6.2   +12.9    +26.2   -0.87   -1.60
  25% runner, trail 40%       44%    -6.5    -2.0    +5.5   +13.7    +25.1   -1.91   -2.63
  25% runner, trail 50%       44%    -8.6    -2.1    +5.5   +13.2    +25.1   -1.98   -2.70
  25% runner, flat 10:00      51%    -8.4    +0.4    +8.8   +16.7    +34.8   -0.17   -0.91
  25% runner, to close        41%    -9.6    -2.1    +5.4   +12.8    +25.1   -2.80   -3.52

### POOLED OOS+IS  (n=68)
  variant                      WR     p25     med     p75     p90      max    mean     @1%
  v2 sell all (baseline)      74%    -0.9    +7.5   +11.4   +14.4    +19.4   +3.15   +2.49
  25% runner, trail 20%       60%    -1.5    +4.1    +9.0   +14.3    +28.3   +1.62   +0.88
  25% runner, trail 30%       56%    -4.0    +1.9    +6.8   +13.3    +26.2   +0.48   -0.24
  25% runner, trail 40%       51%    -5.9    +0.2    +6.5   +12.9    +25.1   -0.65   -1.36
  25% runner, trail 50%       49%    -6.3    -0.8    +6.2   +12.8    +25.1   -1.06   -1.77
  25% runner, flat 10:00      54%    -6.1    +0.7    +8.2   +16.1    +34.8   +0.77   +0.04
  25% runner, to close        47%    -8.2    -0.8    +5.9   +12.9    +32.6   -1.31   -2.02
