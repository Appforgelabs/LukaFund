#!/usr/bin/env python3
"""LukaFund trade executor — place paper trades via Alpaca API"""

import json, os, sys, argparse, requests
from datetime import datetime, timezone

API_KEY    = "PKSAEPZ4YMNDN4ERB6Z7DLVWOK"
API_SECRET = "FeJjXmsXSmYX1tdXTxp6qb8fUX1SLE8LGyrLEvmAsAcK"
BASE       = "https://paper-api.alpaca.markets/v2"
HEADERS    = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET, "Content-Type": "application/json"}
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")

def ts(): return datetime.now(timezone.utc).isoformat()

def log_trade(symbol, side, qty, strategy, order_id, price=None):
    path = os.path.join(DATA_DIR, "trades.json")
    data = json.load(open(path)) if os.path.exists(path) else {"trades": []}
    data["trades"].append({"id": order_id, "symbol": symbol, "side": side,
                           "qty": qty, "strategy": strategy,
                           "limit_price": price, "submitted_at": ts()})
    data["last_updated"] = ts()
    with open(path, "w") as f: json.dump(data, f, indent=2)

parser = argparse.ArgumentParser(description="LukaFund Trade Executor")
parser.add_argument("--symbol", required=True)
parser.add_argument("--side", required=True, choices=["buy", "sell"])
parser.add_argument("--qty", type=float, required=True)
parser.add_argument("--type", dest="order_type", default="limit", choices=["market", "limit"])
parser.add_argument("--limit_price", type=float)
parser.add_argument("--strategy", default="unknown",
                    choices=["covered_call","leap","bear_put_spread","bull_call_spread","short_stock","long_stock","unknown"])
parser.add_argument("--dry_run", action="store_true")
args = parser.parse_args()

order = {"symbol": args.symbol.upper(), "qty": str(args.qty),
         "side": args.side, "type": args.order_type, "time_in_force": "day"}
if args.order_type == "limit":
    if not args.limit_price:
        print("❌ limit_price required for limit orders"); sys.exit(1)
    order["limit_price"] = str(args.limit_price)

print(f"\n📋 Order: {args.side.upper()} {args.qty}x {args.symbol} @ "
      f"{'$'+str(args.limit_price) if args.limit_price else 'MKT'} [{args.strategy}]")

if args.dry_run:
    print("🧪 DRY RUN — not submitted"); sys.exit(0)

r = requests.post(f"{BASE}/orders", headers=HEADERS, json=order)
if r.status_code in (200, 201):
    resp = r.json()
    print(f"✅ Order submitted! ID: {resp['id']} | Status: {resp['status']}")
    log_trade(args.symbol, args.side, args.qty, args.strategy, resp["id"], args.limit_price)
else:
    print(f"❌ Error {r.status_code}: {r.text}"); sys.exit(1)
