# Round 2 — Algo Trading

## Products & Limits
- `ASH_COATED_OSMIUM`: limit 80
- `INTARIAN_PEPPER_ROOT`: limit 80

## Market Access Fee (MAF)
Add `bid()` method to return MAF bid amount (int). Top 50% bids (by median) get 25% extra order book flow. Fee deducted from profit: `final_pnl = profit - bid`.
