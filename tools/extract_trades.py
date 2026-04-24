"""
Extract market trades with buyer/seller IDs from a Prosperity log file.

Handles both log formats:
  - Official IMC website log (JSON with submissionId, tradeHistory, logs fields)
  - Local backtester log (line-by-line JSON from Logger class)

Usage:
    python3 tools/extract_trades.py path/to/your.log

Output:
    tools/extracted_trades.csv          (all named trades)
    tools/extracted_trades_summary.txt  (per-bot behaviour summary)
"""

import json
import sys
import csv
from collections import defaultdict
from pathlib import Path


def parse_official_log(data: dict) -> list:
    """Parse the official IMC website log format."""
    trades = []

    # Check tradeHistory field
    for t in data.get("tradeHistory", []):
        buyer = t.get("buyer", "")
        seller = t.get("seller", "")
        if (buyer and buyer != "SUBMISSION") or (seller and seller != "SUBMISSION"):
            trades.append({
                "timestamp": t["timestamp"],
                "symbol": t["symbol"],
                "price": t["price"],
                "quantity": t["quantity"],
                "buyer": buyer if buyer != "SUBMISSION" else "",
                "seller": seller if seller != "SUBMISSION" else "",
            })

    # Also check lambdaLog market_trades for any named bots
    for entry in data.get("logs", []):
        raw = entry.get("lambdaLog", "")
        if not raw:
            continue
        try:
            row = json.loads(raw)
            state = row[0]
            market_trades = state[5] if len(state) > 5 else []
            ts = state[0]
            for t in market_trades:
                if len(t) >= 5:
                    sym, price, qty, buyer, seller = t[0], t[1], t[2], t[3], t[4]
                    if (buyer and buyer != "SUBMISSION") or (seller and seller != "SUBMISSION"):
                        trades.append({
                            "timestamp": ts,
                            "symbol": sym,
                            "price": price,
                            "quantity": qty,
                            "buyer": buyer if buyer != "SUBMISSION" else "",
                            "seller": seller if seller != "SUBMISSION" else "",
                        })
        except Exception:
            continue

    return trades


def parse_local_log(path: str) -> list:
    """Parse local backtester log (line-by-line JSON)."""
    trades = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, list) or len(row) < 2:
                    continue
                state = row[0]
                if not isinstance(state, list) or len(state) < 6:
                    continue
                ts = state[0]
                for t in state[5]:
                    if len(t) >= 5:
                        sym, price, qty, buyer, seller = t[0], t[1], t[2], t[3], t[4]
                        if (buyer and buyer != "SUBMISSION") or (seller and seller != "SUBMISSION"):
                            trades.append({
                                "timestamp": ts,
                                "symbol": sym,
                                "price": price,
                                "quantity": qty,
                                "buyer": buyer if buyer != "SUBMISSION" else "",
                                "seller": seller if seller != "SUBMISSION" else "",
                            })
            except Exception:
                continue
    return trades


def summarise(trades: list) -> str:
    bots = defaultdict(lambda: {"buys": [], "sells": [], "products": set()})
    for t in trades:
        sym, px, qty = t["symbol"], float(t["price"]), int(t["quantity"])
        ts = t["timestamp"]
        if t["buyer"]:
            bots[t["buyer"]]["buys"].append((sym, px, qty, ts))
            bots[t["buyer"]]["products"].add(sym)
        if t["seller"]:
            bots[t["seller"]]["sells"].append((sym, px, qty, ts))
            bots[t["seller"]]["products"].add(sym)

    lines = [f"{'Bot':<20} {'Buys':>6} {'Sells':>6} {'Net pos':>8}  Products", "-" * 70]
    for bot, d in sorted(bots.items()):
        net = sum(q for _, _, q, _ in d["buys"]) - sum(q for _, _, q, _ in d["sells"])
        lines.append(
            f"{bot:<20} {len(d['buys']):>6} {len(d['sells']):>6} {net:>8}  "
            f"{', '.join(sorted(d['products']))}"
        )
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/extract_trades.py <path/to/logfile.log>")
        sys.exit(1)

    log_path = sys.argv[1]
    print(f"Parsing {log_path} ...")

    # Detect format
    with open(log_path) as f:
        first = f.read(1)

    if first == "{":
        with open(log_path) as f:
            data = json.load(f)
        print("Detected: official IMC website log format")
        trades = parse_official_log(data)

        # Report what's available even if no named trades
        th = data.get("tradeHistory", [])
        print(f"  tradeHistory entries: {len(th)}")
        buyers = set(t.get("buyer","") for t in th)
        sellers = set(t.get("seller","") for t in th)
        print(f"  Unique buyers in tradeHistory: {buyers}")
        print(f"  Unique sellers in tradeHistory: {sellers}")
    else:
        print("Detected: local backtester log format")
        trades = parse_local_log(log_path)

    if not trades:
        print("\nNo named bot trades found in this log.")
        print("\nThis is expected for early rounds of Prosperity 4 —")
        print("IMC does not reveal trader IDs until later rounds (was Round 5 in Prosperity 3).")
        print("\nWatch for trader IDs to appear in later round log files.")
        sys.exit(0)

    print(f"\nFound {len(trades)} named trades.")
    out_dir = Path(__file__).parent
    csv_path = out_dir / "extracted_trades.csv"
    summary_path = out_dir / "extracted_trades_summary.txt"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp","symbol","price","quantity","buyer","seller"])
        writer.writeheader()
        writer.writerows(trades)

    summary = summarise(trades)
    with open(summary_path, "w") as f:
        f.write(summary)

    print(f"\nBot summary:\n{summary}")
    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    print(f"\nNow tell Claude: 'read tools/extracted_trades.csv and analyse bot behaviour'")


if __name__ == "__main__":
    main()
