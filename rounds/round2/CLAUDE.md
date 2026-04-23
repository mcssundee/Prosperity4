# Round 2 — Algo Trading

## Products & Limits
- `ASH_COATED_OSMIUM`: limit 80
- `INTARIAN_PEPPER_ROOT`: limit 80

## Market Access Fee (MAF)
Add `bid()` method to return MAF bid amount (int). Top 50% bids (by median) get 25% extra order book flow. Fee deducted from profit: `final_pnl = profit - bid`.

## Manual: Invest & Expand
Budget: 50,000 XIRECs across Research/Scale/Speed.  
Formula: `PnL = (Research × Scale × Speed) − Budget_Used`
- Research: logarithmic 0→200k
- Scale: linear 0→7  
- Speed: rank-based 0.1→0.9
