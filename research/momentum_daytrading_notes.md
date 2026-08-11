# Momentum Day Trading Strategy — Structured Notes

Source: Ross Cameron (Warrior Trading), "Growing a $2k Account to $65,662.04 in 30 Days," ~59 min.
Notes reconstructed from transcript across multiple pulls; gap status noted at the end.

---

## Framing

- 30-day small-account challenge: $2,000 → ~$65,000, two red days in the period.
- Stated stop date: day 30. Profits donated to charity ($427k raised, 40 children's hospitals).
- Explicit caveat repeated at open and close: results are not typical; practice in a simulator before risking capital.
- Core self-description: "manager of risk and hunter of volatility." He needs movement to make money, so he accepts volatility but caps downside per trade.

---

## Step 1 — Stock Selection (the "five pillars")

Four pillars measure **demand**; one measures **supply**. A 400–500% single-day move requires an imbalance between the two.

| # | Pillar | Threshold | Type |
|---|--------|-----------|------|
| 1 | Relative volume | ≥ 5× the 50-day average | Demand |
| 2 | Total volume | Higher is better; ~25M shares cited as strong, not required | Demand |
| 3 | Percentage gain | ≥ 10% on the day; 30%+ preferred | Demand |
| 4 | Price | $2–$20 | Demand |
| 5 | Float | < 20M shares; lower is better | Supply |

**Supporting filters**

- **Gap-up:** opening at least 2% above the prior close — usually implies a catalyst.
- **Catalyst:** breaking news is the typical demand driver. He will waive this pillar only if the stock is the obvious #1 leading gainer in the market.
- **Hot sector:** crypto, biotech, AI, Chinese tech.
- **Time window:** 7:00–10:00 a.m.

**The funnel:** relative volume ≥ 5× alone cuts ~10,000 tradables to ~100; ≥ 20× cuts to roughly 20. Adding float, gain, and price filters narrows to a handful per day.

**Worked example (YXT):** ~2.87M share float, 44M shares of volume against 500 shares the prior day (~14,000× relative volume), +500% on the day, started around $2–3. No clear catalyst — the one pillar it missed.

**Float logic — why it matters.** Contrast with Shopify the same day: 1.3B share float, +36% on earnings, but on under 1M shares — less than 1/1000th of the float. Not enough buyers to hold a 36% gain once holders sell, and it faded to +16%. On YXT the entire float could have turned over many times and the stock still held, which caps upside resistance and becomes partly self-fulfilling.

---

## Step 2 — Entry Pattern: the First Pullback

Let the stock squeeze (it will hit the scanners), then wait for the retrace. **Do not chase.**

**Four disqualifiers — the pullback should NOT:**

1. Retrace more than 50% of the initial move
2. Show high volume on red candles (want heavy volume on green, light on red)
3. Break below VWAP
4. Break below the 9 EMA

**Candle wicks:**
- **Topping tail** (large upper wick) = bearish, sign of rejection. Avoid buying back into an area that already saw heavy selling.
- **Bottoming tail** = bullish.
- Preferred shape: price stalls at the top and dips back without a pronounced upper wick.

**Entry trigger:** the *crossing candle* — the first candle to make a new high by breaking above the prior candle's high, wick included. That break marks the momentum shift.

**Stop:** the low of the pullback. This is the whole reason to wait — entering mid-squeeze puts the stop far below, entering after the pullback defines risk tightly.

**Target:** minimum 2:1 profit-to-loss.

**Discipline note:** a stock can meet all five pillars and still never offer a valid pattern. No pattern, no trade.

---

## Step 3 — Execution on Level 2

- **Half-dollar and whole-dollar psychology:** $7.50 → $8.00 → $8.50 → $9.00. Stocks respect these levels as support and resistance.
- **Timing the crossing candle:** candles close on the minute. He entered at 8:18:59, anticipating the close of the second red candle and a crossing candle around $7.65.

**The YXT trade, fully specified:**

| Element | Value |
|---|---|
| Entry | $7.60 |
| Hard stop | $7.45 (15¢) |
| Size | 5,000 shares |
| Risk | $750 |
| Target | $8.00, optimistic $8.50 |
| Potential | ~$2,000–$4,500 |
| Best exit | $10.10, then $9.79, then $9.00 |

His own framing of the decision: risking $750 to make $2,000–$4,500 is only correct *if you know your accuracy* and can take the next ten setups. A single trade's ratio means nothing in isolation.

---

## Step 4 — Exits

### Exit indicators (hold until one appears)

1. **A large sell order sitting on Level 2.** A briefly flashing order isn't enough — spoofing is illegal but happens. It has to sit there and feel real.
2. **Hidden seller / iceberg** — heavy buying but price won't advance, because someone is quietly unloading.
3. **Large burst of red on the tape** — surge of selling, possible false breakout.
4. **Dramatic reversal after a pop** — forms a topping tail and a false breakout.
5. **Buying slowing down**, visible on time and sales.
6. **A topping-tail candle or a red candle.**

**Do not cap winners.** He will not sell merely because he's up 20¢, even with a 50¢–$1 target. But an indicator gets respected whether he's up 5¢ or $5.

### Rules for walking away (four)

1. **Gave back half the day's profit.** Below half, he can no longer see the glass as half full, and emotional compromise follows.
2. **Hit max daily loss** — set roughly equal to average daily gain (~$10k lifetime average, ~$19k over the trailing 30 days, so ~$20k comfort zone). Principle: never lose more than you can make on one good day.
3. **The good window has closed.** His metrics show losses between 10:00 and 11:00 a.m., so 10:00 a.m. is a hard stop regardless of how a setup looks.
4. **No quality stocks.** Some days nothing meets even four of five pillars. He averaged about one no-trade day per week during the challenge.

**Annie Duke, *Quit*:** the right moment to walk away almost always feels too soon. Waiting until it feels right means waiting too long.

---

## Step 5 — Track and Data-Mine Every Trade

Habit started in a school class using a paper ledger; carried into his first funded account in 2001.

**What review surfaces — his own examples:**

- *Biggest loser (INLF):* entered anticipating a crossing candle, then held far too long past the point he should have sold. Compounding factors — first trade on the ticker after missing several pullbacks, stock extended, 10:30 a.m., FOMO after stepping away and coming back. Called it a rookie mistake.
- *A tolerable loss (YXT):* thesis was clear, setup didn't work, no regret.
- *A bad loss:* chased the entry, should have been in lower.

**Dimensions he sorts by:** time of day, price, volume, profitability by stock. His finding for the period: entry precision and exit discipline, not stock selection. "Getting a little stubborn in the small account has cost me."

---

## Risk / Accuracy Math

Break-even win rate = **1 / (1 + R)**, where R is reward per unit risked.

| Risk : Reward | Break-even accuracy |
|---|---|
| 1 : 1 | 50% |
| 1 : 2 | 33% |
| 1 : 3 | 25% |
| 1 : 4 | 20% |

Rows 1 and 2 are from the video; rows 3 and 4 are derived (the slide was not recovered). One later summary reported a "2:1 → 67%" row — that is an inverted reading and contradicts his stated recommendation; disregard it.

---

## The Equity-Curve Argument

Three trader profiles he sketches:

- **Break-even trader:** steady progress, then one day gives it all back. Repeat.
- **Slow bleeder:** small profits accumulating while the account actually declines.
- **Profitable trader:** same setups, but shallower drawdowns and more spacing between losses.

The difference between break-even and profitable is not a better strategy — it's walking away sooner on bad days. Profits are a byproduct of process and confidence; trade in a way that builds self-confidence rather than erodes it.

**On simplicity:** most traders struggle by overcomplicating. Get good at one pattern — the first pullback — before adding the one-minute/five-minute/ten-second variants, ABCD, cup and handle, or inverted head and shoulders. Duke's brother taught her only the highest-probability poker hands; that became her foundation.

---

## Reconstruction Notes

**Fully recovered:** stock selection and pillars; pullback pattern and disqualifiers; crossing-candle entry; Level 2 execution and the YXT trade parameters; all six exit indicators; all four walk-away rules; the Duke principle; metrics review.

**Not recovered:** the full profit/loss ratio slide beyond the 1:1 and 1:2 rows. Derivable from the formula above.

**Corrections applied:**
- YXT starting price transcribed as "$23 a share" — actually "two, three a share," consistent with the $3–4 figure given elsewhere.
- One summary pass reported "two rules for walking away" including a daily profit goal; the transcript gives four, and no profit goal among them. Discarded as reconstruction.
- The "2:1 → 67% accuracy" row is inverted relative to his usage of "2:1"; excluded.
