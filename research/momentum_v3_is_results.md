# Momentum exit-scheme comparison — is

Entries: 98 (identical across all schemes; v1 entry logic)
Ladder (5, 10, 20, 35) @ 25% each, ratchet {0: None, 1: 0.0, 2: 5.0, 3: 10.0, 4: 20.0}, flat 10:00 ET

### v3-nostop (PRIMARY)
  0.5%/side : n= 98 WR= 53% mean= +1.03% med= +4.94% p25= -0.37% min= -38.87%
  1.0%/side : n= 98 WR= 53% mean= +0.26% med= +4.16% p25= -1.23% min= -39.48%
  ex-top5   : n= 92 WR= 50% mean= +0.14% med= +0.45% p25= -0.37% min= -38.87%
  H1        : n= 47 WR= 55% mean= +2.40% med= +4.94% p25= -0.37% min= -29.72%
  H2        : n= 51 WR= 51% mean= -0.23% med= +1.27% p25= -0.37% min= -38.87%
  [P] a mean>0 @0.5%  [P] b mean>0 @1.0%  [P] c ex-top5>0  [F] d halves>0  [P] e n>=50
  ALL PASS: False

### v3-pbstop
  0.5%/side : n= 98 WR= 28% mean= -1.54% med= -3.11% p25= -5.78% min= -19.97%
  1.0%/side : n= 98 WR= 28% mean= -2.41% med= -4.07% p25= -6.72% min= -20.77%
  ex-top5   : n= 92 WR= 23% mean= -2.60% med= -3.50% p25= -6.08% min= -19.97%
  H1        : n= 47 WR= 34% mean= -0.12% med= -2.62% p25= -4.88% min= -11.65%
  H2        : n= 51 WR= 22% mean= -2.85% med= -3.70% p25= -6.70% min= -19.97%
  [F] a mean>0 @0.5%  [F] b mean>0 @1.0%  [F] c ex-top5>0  [F] d halves>0  [P] e n>=50
  ALL PASS: False

### v3-dipcond
  0.5%/side : n= 98 WR= 52% mean= +1.19% med= +2.46% p25= -0.84% min= -38.87%
  1.0%/side : n= 98 WR= 52% mean= +0.41% med= +1.64% p25= -1.69% min= -39.48%
  ex-top5   : n= 92 WR= 49% mean= +0.31% med= -0.37% p25= -0.99% min= -38.87%
  H1        : n= 47 WR= 49% mean= +3.20% med= -0.37% p25= -0.37% min= -24.35%
  H2        : n= 51 WR= 55% mean= -0.66% med= +3.07% p25= -0.99% min= -38.87%
  [P] a mean>0 @0.5%  [P] b mean>0 @1.0%  [P] c ex-top5>0  [F] d halves>0  [P] e n>=50
  ALL PASS: False

### v2 dip-conditioned target
  0.5%/side : n= 98 WR= 82% mean= +5.23% med= +7.46% p25= +3.48% min= -38.87%
  1.0%/side : n= 98 WR= 80% mean= +4.60% med= +6.93% p25= +2.97% min= -39.48%
  ex-top5   : n= 92 WR= 80% mean= +4.41% med= +7.46% p25= +3.40% min= -38.87%
  H1        : n= 47 WR= 89% mean= +7.31% med= +7.46% p25= +3.48% min= -24.35%
  H2        : n= 51 WR= 75% mean= +3.31% med= +7.46% p25= -2.48% min= -38.87%
  [P] a mean>0 @0.5%  [P] b mean>0 @1.0%  [P] c ex-top5>0  [P] d halves>0  [P] e n>=50
  ALL PASS: True

### control flat +10%
  0.5%/side : n= 98 WR= 78% mean= +2.98% med= +9.45% p25= +3.32% min= -38.87%
  1.0%/side : n= 98 WR= 76% mean= +2.36% med= +8.91% p25= +2.43% min= -39.48%
  ex-top5   : n= 89 WR= 75% mean= +2.43% med= +9.45% p25= +0.97% min= -38.87%
  H1        : n= 47 WR= 79% mean= +3.33% med= +9.45% p25= +5.21% min= -29.72%
  H2        : n= 51 WR= 76% mean= +2.66% med= +9.45% p25= +5.36% min= -38.87%
  [P] a mean>0 @0.5%  [P] b mean>0 @1.0%  [P] c ex-top5>0  [P] d halves>0  [P] e n>=50
  ALL PASS: True

## Summary
  fail  v3-nostop (PRIMARY)
  fail  v3-pbstop
  fail  v3-dipcond
  PASS  v2 dip-conditioned target
  PASS  control flat +10%
