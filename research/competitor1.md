# Competitor 1 — Frankfurt Hedgehogs

**Source**: https://github.com/TimoDiehm/imc-prosperity-3
**Finish**: Rank 2 Global
**Team**: Timo Diehm & Arne Witt (Frankfurt business undergrads)
**Final Score**: 1,433,876 SeaShells

---

## Architecture
- Single file `FrankfurtHedgehogs_polished.py` (~925 lines), OOP with `ProductTrader` base class
- Subclasses: `StaticTrader`, `DynamicTrader`, `InkTrader`, `EtfTrader`, `OptionTrader`, `CommodityTrader`
- State persisted across timesteps via JSON `traderData`

## Key Proprietary Insight: Wall Mid
Use the **lowest bid-side price** (bid wall) and **highest ask-side price** (ask wall) — the deep liquidity makers — averaged as fair value. Far more stable than best-bid/ask midpoint.

---

## Round 1 — Market Making

### Rainforest Resin
- True value hardcoded at 10,000
- Take any ask ≤ wall_mid − 1 or bid ≥ wall_mid + 1
- Passive quote one tick better than existing orders around wall mid
- ~39,000 SeaShells/round

### Kelp
- Same Wall Mid strategy as Resin
- Added Olivia (informed trader) detection: if she bought recently (within 500 timestamps), aggressively bid to position 40; if she sold, aggressively ask

### Squid Ink
- Olivia buys exactly 15 lots at the daily low, sells exactly 15 at the daily high
- Strategy: track daily running min/max; when 15-lot trade at daily extreme, take max position (±50) in that direction
- Reset on invalidation (new extremum in opposite direction)
- No market making — purely following Olivia

### Manual Round 1 — FX Arbitrage
- Brute force over currency paths: SeaShells → Snowballs → Silicon Nuggets → Pizza → Snowballs → SeaShells = +8.9%

---

## Round 2 — ETF Statistical Arbitrage

### Key Insight
Baskets mean-revert to synthetic constituent value; constituents do NOT respond to baskets. Trade baskets, not constituents.

### Parameters
- `BASKET_THRESHOLDS = [80, 50]` — enter when spread > threshold
- `INITIAL_ETF_PREMIUMS = [5, 53]` — running average premium to detrend
- `ETF_HEDGE_FACTOR = 0.5` — hedge 50% of basket exposure in constituents
- Olivia signal shifts basket 1&2 thresholds: long entry becomes −170, short entry becomes +10
- Running premium via Welford's online algorithm (up to 60,000 samples)

### Croissants
- Follow Olivia's signal directly; go to ±250 position limit

### Results
- 40,000–60,000 SeaShells/round on baskets + ~20,000/round on Croissants

### Manual Round 2 — Containers
- `payoff = (10,000 × multiplier) / (% teams × 100 + inhabitants)`
- Modeled other teams' behavior; avoided container 37 (human bias), chose container 50

---

## Round 3 — Options / IV Scalping

### Vol Smile IV Scalping (primary)
- Moneyness: `m_t = ln(K / S_t) / sqrt(TTE)`
- Fitted vol smile: `v̂_t = a·m_t² + b·m_t + c`
- Coefficients: `[0.27362531, 0.01007566, 0.14876677]`
- Fair option price via Black-Scholes using fitted IV
- Entry threshold: `IV_SCALPING_THR = 0.7` on rolling average deviation (window 100)
- Open when `current_theo_diff − mean_theo_diff ≥ 0.5` (sell) or `≤ −0.5` (buy)
- Close when crosses zero
- Active on strikes ≥ 9750; 9500 handled separately

### Underlying Mean Reversion (secondary)
- Fast EMA (window 10) on Volcanic Rock; trade deviations > 15 ticks at max volume

### Results
- IV scalping: ~100–150k SeaShells/round

---

## Round 4 — Macarons Location Arbitrage

### Key Hidden Edge: Taker Bot
- A hidden bot fills local sell orders at `floor(externalBid + 0.5)` ~60% of the time
- Yields ~3 SeaShells premium above naive local best bid per unit

### Strategy
- Each timestep, place limit sell orders at `int(externalBid + 0.5)`
- Quote exactly 10 units (conversion limit)
- Convert full negative position after fills: `conversions = max(min(-position, 10), -10)`

### Results
- ~80,000–100,000 SeaShells/round

---

## Round 5 — Trader IDs Revealed
- Replaced inference logic with direct `trade.buyer == 'Olivia'` check
- Re-optimized all parameters; reduced mean reversion exposure to protect lead

### Manual Round 5 — News Trading
- Notable wins: Quantum Coffee (−50% estimate, actual −66.79%, +87k), Cacti Needle (+32k)
- Total: 126,751 SeaShells (optimal was 194,522)

---

## Meta-Insights
- Use the official Prosperity backtester for bot-sensitive products (Resin, Kelp, Macarons)
- Tried brute-force reverse-engineering of NumPy random seed — failed after 4B seeds
- Reported hardcoding exploit to IMC after Round 2 (triggered official rerun)
