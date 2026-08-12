# Momentum exit-scheme comparison — oos

Entries: 71 (identical across all schemes; v1 entry logic)
Ladder (5, 10, 20, 35) @ 25% each, ratchet {0: None, 1: 0.0, 2: 5.0, 3: 10.0, 4: 20.0}, flat 10:00 ET

### v3-nostop (PRIMARY)
  0.5%/side : n= 71 WR= 46% mean= +0.31% med= -0.37% p25= -0.37% min= -36.92%
  1.0%/side : n= 71 WR= 46% mean= -0.47% med= -1.23% p25= -1.23% min= -37.55%
  ex-top5   : n= 65 WR= 42% mean= -1.03% med= -0.37% p25= -0.37% min= -36.92%
  H1        : n= 33 WR= 45% mean= +0.20% med= -0.37% p25= -0.37% min= -28.86%
  H2        : n= 38 WR= 47% mean= +0.41% med= -0.37% p25= -0.37% min= -36.92%
  [P] a mean>0 @0.5%  [F] b mean>0 @1.0%  [F] c ex-top5>0  [P] d halves>0  [P] e n>=50
  ALL PASS: False

### v3-pbstop
  0.5%/side : n= 71 WR= 23% mean= -1.81% med= -3.15% p25= -6.17% min= -19.98%
  1.0%/side : n= 71 WR= 23% mean= -2.68% med= -4.11% p25= -7.10% min= -20.78%
  ex-top5   : n= 66 WR= 17% mean= -3.23% med= -3.35% p25= -6.39% min= -19.98%
  H1        : n= 33 WR= 12% mean= -3.28% med= -4.23% p25= -6.53% min= -11.07%
  H2        : n= 38 WR= 32% mean= -0.53% med= -2.29% p25= -5.00% min= -19.98%
  [F] a mean>0 @0.5%  [F] b mean>0 @1.0%  [F] c ex-top5>0  [F] d halves>0  [P] e n>=50
  ALL PASS: False

### v3-dipcond
  0.5%/side : n= 71 WR= 48% mean= +1.04% med= -0.37% p25= -0.99% min= -36.92%
  1.0%/side : n= 71 WR= 48% mean= +0.26% med= -1.23% p25= -1.85% min= -37.55%
  ex-top5   : n= 65 WR= 43% mean= -0.26% med= -0.37% p25= -0.99% min= -36.92%
  H1        : n= 33 WR= 52% mean= +1.03% med= +3.07% p25= -0.37% min= -25.38%
  H2        : n= 38 WR= 45% mean= +1.05% med= -0.37% p25= -0.99% min= -36.92%
  [P] a mean>0 @0.5%  [P] b mean>0 @1.0%  [F] c ex-top5>0  [P] d halves>0  [P] e n>=50
  ALL PASS: False

### v2 dip-conditioned target
  0.5%/side : n= 71 WR= 75% mean= +3.61% med= +7.46% p25= +1.08% min= -36.92%
  1.0%/side : n= 71 WR= 75% mean= +2.99% med= +6.93% p25= +0.34% min= -37.55%
  ex-top5   : n= 65 WR= 72% mean= +2.41% med= +7.46% p25= -3.68% min= -36.92%
  H1        : n= 33 WR= 88% mean= +5.39% med= +7.46% p25= +3.48% min= -25.38%
  H2        : n= 38 WR= 63% mean= +2.07% med= +7.46% p25=-11.10% min= -36.92%
  [P] a mean>0 @0.5%  [P] b mean>0 @1.0%  [P] c ex-top5>0  [P] d halves>0  [P] e n>=50
  ALL PASS: True

### control flat +10%
  0.5%/side : n= 71 WR= 62% mean= -0.66% med= +9.45% p25=-12.49% min= -36.92%
  1.0%/side : n= 71 WR= 62% mean= -1.31% med= +8.91% p25=-13.36% min= -37.55%
  ex-top5   : n= 64 WR= 58% mean= -1.77% med= +9.45% p25=-13.58% min= -36.92%
  H1        : n= 33 WR= 64% mean= -0.63% med= +9.45% p25=-13.37% min= -30.27%
  H2        : n= 38 WR= 61% mean= -0.68% med= +9.45% p25=-11.59% min= -36.92%
  [F] a mean>0 @0.5%  [F] b mean>0 @1.0%  [F] c ex-top5>0  [F] d halves>0  [P] e n>=50
  ALL PASS: False

## Summary
  fail  v3-nostop (PRIMARY)
  fail  v3-pbstop
  fail  v3-dipcond
  PASS  v2 dip-conditioned target
  fail  control flat +10%
