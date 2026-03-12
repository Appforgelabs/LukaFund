#!/usr/bin/env python3
"""
LukaFund — update_prices.py
Syncs current prices from Alpaca paper account positions into portfolio.json,
then recalculates total_value and total_return_pct using the correct
short P&L formula. Fast — no Polygon candle fetches, no rate limiting.
"""
import json, os, sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

def load_json(fn):
    with open(os.path.join(DATA_DIR, fn)) as f:
        return json.load(f)

def save_json(fn, obj):
    with open(os.path.join(DATA_DIR, fn), "w") as f:
        json.dump(obj, f, indent=2)

def calculate_total_value(portfolio):
    """
    Longs:  qty × current_price
    Shorts: no cash received on entry → contribute only unrealized P&L
            = (avg_cost - current_price) × abs(qty)
    """
    val = 0.0
    for pos in portfolio["positions"]:
        if pos.get("type") == "short":
            val += (pos["avg_cost"] - pos["current_price"]) * abs(pos["quantity"])
        else:
            val += pos["quantity"] * pos["current_price"]
    return round(portfolio["cash"] + val, 2)

def main():
    portfolio = load_json("portfolio.json")

    # Alpaca positions.json has current market prices
    try:
        alpaca_positions = load_json("positions.json")
    except FileNotFoundError:
        print("  [update_prices] positions.json not found — run pipeline.py first")
        sys.exit(1)

    # Build price map from Alpaca data
    price_map = {}
    for ap in (alpaca_positions if isinstance(alpaca_positions, list) else []):
        sym = ap.get("symbol", "")
        # Alpaca provides current_price as string
        try:
            price_map[sym] = float(ap.get("current_price") or ap.get("lastday_price") or 0)
        except (TypeError, ValueError):
            pass

    # Also check account.json for any price hints
    updates = 0
    for pos in portfolio["positions"]:
        sym = pos["symbol"]
        if sym in price_map and price_map[sym] > 0:
            old = pos["current_price"]
            pos["current_price"] = round(price_map[sym], 4)
            if old != pos["current_price"]:
                print(f"  {sym}: ${old} → ${pos['current_price']}")
                updates += 1

    if updates == 0:
        print("  [update_prices] No Alpaca position data found for held symbols — trying Finnhub...")
        # Fallback: Finnhub quotes
        import urllib.request
        FINNHUB_KEY = "d6952r9r01qs7u9kq240d6952r9r01qs7u9kq24g"
        import time
        for pos in portfolio["positions"]:
            sym = pos["symbol"]
            url = f"https://finnhub.io/api/v1/quote?symbol={sym}&token={FINNHUB_KEY}"
            try:
                with urllib.request.urlopen(url, timeout=8) as r:
                    q = json.loads(r.read())
                if q.get("c"):
                    old = pos["current_price"]
                    pos["current_price"] = round(q["c"], 4)
                    print(f"  {sym}: ${old} → ${pos['current_price']} (Finnhub)")
                    updates += 1
            except Exception as e:
                print(f"  {sym}: Finnhub failed — {e}")
            time.sleep(0.4)

    # Recalculate total value with correct short formula
    portfolio["total_value"] = calculate_total_value(portfolio)
    portfolio["total_return_pct"] = round(
        (portfolio["total_value"] - portfolio["starting_capital"]) / portfolio["starting_capital"] * 100, 2
    )
    portfolio["last_updated"] = datetime.now().strftime("%Y-%m-%d")

    # Update equity curve (today's entry)
    today = datetime.now().strftime("%Y-%m-%d")
    eq = load_json("equity_curve.json")
    curve = eq["curve"]

    # Get SPY price for benchmark
    spy_price = None
    for ap in (alpaca_positions if isinstance(alpaca_positions, list) else []):
        if ap.get("symbol") == "SPY":
            spy_price = float(ap.get("current_price") or 0) or None

    # Absolute SPY normalization: 10000 × (current_price / benchmark_start_price)
    # This matches portfolio_engine.py exactly and avoids compounding drift.
    benchmark_start = portfolio.get("benchmark_start_price")
    spy_norm = None

    if spy_price and benchmark_start:
        spy_norm = round(10000 * (spy_price / benchmark_start), 2)
    elif not spy_price:
        # Fetch SPY quote from Finnhub
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol=SPY&token=d6952r9r01qs7u9kq240d6952r9r01qs7u9kq24g"
            with urllib.request.urlopen(url, timeout=8) as r:
                q = json.loads(r.read())
            spy_price = q.get("c")
            if spy_price and benchmark_start:
                spy_norm = round(10000 * (spy_price / benchmark_start), 2)
        except Exception as e:
            print(f"  [update_prices] SPY Finnhub fetch failed: {e}")

    if spy_norm is None:
        # Fallback: keep last known value
        spy_norm = next((c["spy_value"] for c in reversed(curve) if c.get("spy_value")), 10000)

    if curve and curve[-1]["date"] == today:
        curve[-1]["value"]     = portfolio["total_value"]
        curve[-1]["spy_value"] = spy_norm
        curve[-1]["cash"]      = portfolio["cash"]
    else:
        curve.append({"date": today, "value": portfolio["total_value"],
                      "spy_value": spy_norm, "cash": portfolio["cash"]})

    save_json("portfolio.json", portfolio)
    save_json("equity_curve.json", eq)

    print(f"  [update_prices] Done — ${portfolio['total_value']:.2f} ({portfolio['total_return_pct']:+.2f}%) | {updates} prices updated")

if __name__ == "__main__":
    main()
