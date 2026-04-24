# Round 3 — Manual Trading: Celestial Gardeners' Guild

## Goal
Buy Ornamental Bio-Pods cheap; they auto-sell at 920 next round.

## Counterparties
Reserve prices: Uniform distribution, 670–920 in increments of 5

## Bid Strategy
Submit 2 bids:

### Bid 1
- Trades with anyone whose reserve price < bid 1 (you pay bid 1)

### Bid 2
- If bid 2 > reserve price and bid 2 ≥ avg of all players' bid 2 → trade at bid 2
- If bid 2 > reserve price but bid 2 < avg bid 2 → trade occurs but PnL penalised by:
  - Penalty factor: `((920 - avg_b2) / (920 - b2))^3`


Each counterparty is willing to trade with you at most once