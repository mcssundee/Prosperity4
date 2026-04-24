"""
Extract market trades with buyer/seller IDs from a Prosperity log file.

Usage:
    python3 tools/extract_trades.py path/to/your.log

Output:
    tools/extracted_trades.csv  (tiny — only named trades)
    tools/extracted_trades_summary.txt  (bot behaviour summary)
"""

import json
import sys
import csv
from collections import defaultdict
from pathlib import Path


def parse_log(log_path: str):
    trades = []
    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Log format: [state_data, orders, conversions, trader_data, logs]
            if not isinstance(row, list) or len(row) < 2:
                continue
            state = row[0]
            if not isinstance(state, list) or len(state) < 6:
                continue

            timestamp = state[0]
            market_trades_raw = state[5]  # [[symbol, price, qty, buyer, seller, ts], ...]

            if not isinstance(market_trades_raw, list):
                continue

            for trade in market_trades_raw:
                if not isinstance(trade, list) or len(trade) < 5:
                    continue
                symbol, price, qty, buyer, seller, *_ = trade
                # Only keep trades where at least one party is identified
                if buyer or seller:
                    trades.append({
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "price": price,
                        "quantity": qty,
                        "buyer": buyer or "",
                        "seller": seller or "",
                    })

    return trades


def summarise(trades):
    """Per-bot: trade count, products traded, avg buy price, avg sell price, net position."""
    bots = defaultdict(lambda: {
        "buys": [], "sells": [], "products": set()
    })

    for t in trades:
        sym = t["symbol"]
        px = float(t["price"])
        qty = int(t["quantity"])
        if t["buyer"]:
            bots[t["buyer"]]["buys"].append((sym, px, qty, t["timestamp"]))
            bots[t["buyer"]]["products"].add(sym)
        if t["seller"]:
            bots[t["seller"]]["sells"].append((sym, px, qty, t["timestamp"]))
            bots[t["seller"]]["products"].add(sym)

    lines = []
    lines.append(f"{'Bot':<20} {'Buys':>6} {'Sells':>6} {'Net pos':>8}  Products")
    lines.append("-" * 70)
    for bot, data in sorted(bots.items()):
        net = sum(q for _, _, q, _ in data["buys"]) - sum(q for _, _, q, _ in data["sells"])
        lines.append(
            f"{bot:<20} {len(data['buys']):>6} {len(data['sells']):>6} {net:>8}  "
            f"{', '.join(sorted(data['products']))}"
        )
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/extract_trades.py <path/to/logfile.log>")
        sys.exit(1)

    log_path = sys.argv[1]
    print(f"Parsing {log_path} ...")
    trades = parse_log(log_path)

    if not trades:
        print("No named trades found. The log may not contain trader IDs.")
        print("Make sure you're using the log from the official IMC Prosperity backtester.")
        sys.exit(0)

    print(f"Found {len(trades)} named trades.")

    out_dir = Path(__file__).parent
    csv_path = out_dir / "extracted_trades.csv"
    summary_path = out_dir / "extracted_trades_summary.txt"

    # Write compact CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "symbol", "price", "quantity", "buyer", "seller"])
        writer.writeheader()
        writer.writerows(trades)

    # Write summary
    summary = summarise(trades)
    with open(summary_path, "w") as f:
        f.write(summary)

    print(f"\nBot summary:\n{summary}")
    print(f"\nFull trade data saved to: {csv_path}")
    print(f"Summary saved to:         {summary_path}")
    print(f"\nNow tell Claude: 'read tools/extracted_trades.csv and analyse bot behaviour'")


if __name__ == "__main__":
    main()
