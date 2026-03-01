#!/usr/bin/env python3
"""LukaFund pipeline — pulls Alpaca paper account data -> JSON files in data/"""

import json, os, requests
from datetime import datetime, timezone

API_KEY    = "ALPACA_KEY_REDACTED"
API_SECRET = "ALPACA_SECRET_REDACTED"
BASE       = "https://paper-api.alpaca.markets/v2"
HEADERS    = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET}
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

def ts(): return datetime.now(timezone.utc).isoformat()
def save(fn, obj):
    with open(os.path.join(DATA_DIR, fn), "w") as f: json.dump(obj, f, indent=2)
    print(f"  ✓ {fn}")
def get(ep, params=None):
    r = requests.get(f"{BASE}{ep}", headers=HEADERS, params=params); r.raise_for_status(); return r.json()

def pull_account():
    d = get("/account")
    eq, leq = float(d["equity"]), float(d["last_equity"])
    out = {"last_updated": ts(), "equity": eq, "cash": float(d["cash"]),
           "buying_power": float(d["buying_power"]),
           "options_buying_power": float(d.get("options_buying_power", 0)),
           "portfolio_value": float(d["portfolio_value"]),
           "last_equity": leq, "daily_pl": eq - leq,
           "daily_pl_pct": (eq - leq) / leq * 100 if leq else 0}
    save("account.json", out); return out

def pull_positions():
    trades_path = os.path.join(DATA_DIR, "trades.json")
    trades = json.load(open(trades_path)).get("trades", []) if os.path.exists(trades_path) else []
    smap = {t["symbol"]: t.get("strategy", "unknown") for t in trades}
    positions = [{"symbol": p["symbol"], "qty": float(p["qty"]), "side": p["side"],
                  "avg_entry_price": float(p["avg_entry_price"]),
                  "current_price": float(p["current_price"]),
                  "market_value": float(p["market_value"]),
                  "unrealized_pl": float(p["unrealized_pl"]),
                  "unrealized_plpc": float(p["unrealized_plpc"]) * 100,
                  "strategy": smap.get(p["symbol"], "unknown")} for p in get("/positions")]
    save("positions.json", {"last_updated": ts(), "positions": positions})

def pull_orders():
    orders = [{"id": o["id"],
               "symbol": o.get("symbol") or (o.get("legs") or [{}])[0].get("symbol",""),
               "side": o["side"], "type": o["type"], "qty": o.get("qty"),
               "filled_qty": o.get("filled_qty"), "limit_price": o.get("limit_price"),
               "filled_avg_price": o.get("filled_avg_price"), "status": o["status"],
               "submitted_at": o.get("submitted_at"), "filled_at": o.get("filled_at"),
               "order_class": o.get("order_class", "simple")}
              for o in get("/orders", {"limit": 50, "status": "all"})]
    save("orders.json", {"last_updated": ts(), "orders": orders})

def update_pnl(account):
    path = os.path.join(DATA_DIR, "pnl_history.json")
    hist = json.load(open(path)).get("history", []) if os.path.exists(path) else []
    hist.append({"timestamp": ts(), "equity": account["equity"], "daily_pl": account["daily_pl"]})
    save("pnl_history.json", {"last_updated": ts(), "history": hist[-365:]})

def init_trades():
    path = os.path.join(DATA_DIR, "trades.json")
    if not os.path.exists(path): save("trades.json", {"last_updated": ts(), "trades": []})

if __name__ == "__main__":
    print("🔄 LukaFund Pipeline running...")
    init_trades(); account = pull_account(); pull_positions(); pull_orders(); update_pnl(account)
    print(f"\n✅ Done — Equity: ${account['equity']:,.2f} | Daily P&L: ${account['daily_pl']:+,.2f} ({account['daily_pl_pct']:+.2f}%)")
