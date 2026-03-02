#!/usr/bin/env python3
"""
LukaFund Portfolio Engine
Main script: fetches data, makes decisions, executes paper trades, updates state.
Run daily: python3 scripts/portfolio_engine.py
"""

import json
import os
import sys
from datetime import datetime

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_data as md
import decision_maker as dm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r") as f:
        return json.load(f)

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_position(portfolio, symbol):
    for pos in portfolio["positions"]:
        if pos["symbol"] == symbol:
            return pos
    return None

def execute_buy(portfolio, symbol, quantity, price, reasoning):
    cost = quantity * price
    if cost > portfolio["cash"]:
        print(f"  [SKIP] Insufficient cash for BUY {quantity} {symbol} @ ${price:.2f} (need ${cost:.2f}, have ${portfolio['cash']:.2f})")
        return None

    existing = get_position(portfolio, symbol)
    if existing:
        # Average up/down
        total_qty = existing["quantity"] + quantity
        total_cost = (existing["avg_cost"] * existing["quantity"]) + cost
        existing["avg_cost"] = round(total_cost / total_qty, 4)
        existing["quantity"] = total_qty
        existing["current_price"] = price
    else:
        portfolio["positions"].append({
            "symbol": symbol,
            "quantity": quantity,
            "avg_cost": round(price, 4),
            "current_price": price,
            "entry_date": datetime.now().strftime("%Y-%m-%d")
        })

    portfolio["cash"] = round(portfolio["cash"] - cost, 2)
    print(f"  ✅ BUY {quantity} {symbol} @ ${price:.2f} | Cost: ${cost:.2f} | Cash left: ${portfolio['cash']:.2f}")
    return {"action": "BUY", "symbol": symbol, "quantity": quantity, "price": price}

def execute_sell(portfolio, symbol, quantity, price, reasoning):
    existing = get_position(portfolio, symbol)
    if not existing:
        print(f"  [SKIP] No position in {symbol} to sell")
        return None

    qty_to_sell = min(quantity, existing["quantity"])
    proceeds = round(qty_to_sell * price, 2)
    pnl = round((price - existing["avg_cost"]) * qty_to_sell, 2)

    existing["quantity"] -= qty_to_sell
    existing["current_price"] = price

    if existing["quantity"] == 0:
        portfolio["positions"] = [p for p in portfolio["positions"] if p["symbol"] != symbol]

    portfolio["cash"] = round(portfolio["cash"] + proceeds, 2)
    print(f"  ✅ SELL {qty_to_sell} {symbol} @ ${price:.2f} | Proceeds: ${proceeds:.2f} | P&L: ${pnl:+.2f}")
    return {"action": "SELL", "symbol": symbol, "quantity": qty_to_sell, "price": price, "pnl": pnl}

def execute_short(portfolio, symbol, quantity, price, reasoning):
    """Simulate a short position (negative quantity)."""
    cost_margin = quantity * price * 0.5  # 50% margin requirement simulation
    if cost_margin > portfolio["cash"] * 0.3:
        print(f"  [SKIP] Insufficient margin for SHORT {quantity} {symbol}")
        return None

    existing = get_position(portfolio, symbol)
    if existing and existing["quantity"] < 0:
        print(f"  [SKIP] Already short {symbol}")
        return None

    portfolio["positions"].append({
        "symbol": symbol,
        "quantity": -quantity,
        "avg_cost": round(price, 4),
        "current_price": price,
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "type": "short"
    })

    print(f"  ✅ SHORT {quantity} {symbol} @ ${price:.2f} (bearish simulation)")
    return {"action": "SHORT", "symbol": symbol, "quantity": -quantity, "price": price}

def update_position_prices(portfolio, quotes):
    """Update current prices on all positions."""
    for pos in portfolio["positions"]:
        q = quotes.get(pos["symbol"])
        if q:
            pos["current_price"] = q["price"]

def calculate_total_value(portfolio):
    """Sum cash + all position market values."""
    positions_value = sum(
        pos["quantity"] * pos["current_price"]
        for pos in portfolio["positions"]
    )
    return round(portfolio["cash"] + positions_value, 2)

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M ET")
    print(f"\n{'='*60}")
    print(f"  LukaFund Portfolio Engine — {now_str}")
    print(f"{'='*60}\n")

    # Load state
    portfolio = load_json("portfolio.json")
    trades_data = load_json("trades.json")
    equity_data = load_json("equity_curve.json")
    decisions_data = load_json("decisions.json")

    print(f"  Starting value: ${portfolio['total_value']:.2f} | Cash: ${portfolio['cash']:.2f}")
    print(f"  Positions: {len(portfolio['positions'])}")

    # Fetch market data
    print(f"\n  Fetching market data for {len(dm.WATCHLIST)} symbols...")
    quotes = {}
    candles_map = {}

    all_symbols = list(set(dm.WATCHLIST + [p["symbol"] for p in portfolio["positions"]] + ["SPY"]))
    for symbol in all_symbols:
        print(f"    → {symbol}...", end=" ")
        q = md.get_quote(symbol)
        if q:
            quotes[symbol] = q
            print(f"${q['price']:.2f} ({q['change_pct']:+.1f}%)", end="")
        else:
            print("(no data)", end="")

        c = md.get_candles(symbol, days=60)
        if c:
            candles_map[symbol] = c
            print(f" [{len(c)} candles]")
        else:
            print()

    # Update position prices
    update_position_prices(portfolio, quotes)

    # Set SPY benchmark start price
    if portfolio["benchmark_start_price"] is None and "SPY" in quotes:
        portfolio["benchmark_start_price"] = quotes["SPY"]["price"]
        print(f"\n  SPY benchmark set at ${portfolio['benchmark_start_price']:.2f}")

    # Run decision engine
    print(f"\n  Running decision engine...")
    decisions = dm.generate_decisions(portfolio, quotes, candles_map)

    new_trades = []
    for d in decisions:
        symbol = d["symbol"]
        action = d["action"]
        qty = d["quantity"]
        price = d["price"]
        reasoning = d["reasoning"]

        print(f"\n  [{action}] {symbol} x{qty} @ ${price:.2f}")
        print(f"    Reason: {reasoning[:100]}...")

        trade_result = None
        if action == "BUY" and qty > 0:
            trade_result = execute_buy(portfolio, symbol, qty, price, reasoning)
        elif action == "SELL" and qty > 0:
            trade_result = execute_sell(portfolio, symbol, qty, price, reasoning)
        elif action == "SHORT" and qty > 0:
            trade_result = execute_short(portfolio, symbol, qty, price, reasoning)

        # Record trade
        if trade_result:
            portfolio_value = calculate_total_value(portfolio)
            trade_record = {
                "date": today,
                "symbol": symbol,
                "action": action,
                "quantity": qty,
                "price": price,
                "total_cost": round(qty * price, 2),
                "reasoning": reasoning,
                "cash_after": portfolio["cash"],
                "portfolio_value_after": portfolio_value,
                "indicators": d.get("indicators", {}),
                "conviction": d.get("conviction", 0)
            }
            if "pnl" in trade_result:
                trade_record["realized_pnl"] = trade_result["pnl"]
            new_trades.append(trade_record)

    # Update total portfolio value
    portfolio["total_value"] = calculate_total_value(portfolio)
    portfolio["total_return_pct"] = round(
        (portfolio["total_value"] - portfolio["starting_capital"]) / portfolio["starting_capital"] * 100, 2
    )
    portfolio["last_updated"] = today

    # Calculate SPY normalized value
    spy_normalized = 10000.0
    if portfolio["benchmark_start_price"] and "SPY" in quotes:
        spy_current = quotes["SPY"]["price"]
        spy_normalized = round(10000 * (spy_current / portfolio["benchmark_start_price"]), 2)

    # Append to equity curve (avoid duplicates for today)
    curve = equity_data["curve"]
    if not curve or curve[-1]["date"] != today:
        curve.append({
            "date": today,
            "value": portfolio["total_value"],
            "spy_value": spy_normalized,
            "cash": portfolio["cash"]
        })
    else:
        curve[-1]["value"] = portfolio["total_value"]
        curve[-1]["spy_value"] = spy_normalized
        curve[-1]["cash"] = portfolio["cash"]

    # Save decisions
    today_decisions = {
        "date": today,
        "decisions": decisions,
        "portfolio_value": portfolio["total_value"],
        "cash": portfolio["cash"],
        "summary": f"{len([d for d in decisions if d['action'] in ('BUY','SELL','SHORT')])} trades executed"
    }
    decisions_data["decisions"].append(today_decisions)

    # Append new trades
    trades_data["trades"].extend(new_trades)

    # Save everything
    save_json("portfolio.json", portfolio)
    save_json("trades.json", trades_data)
    save_json("equity_curve.json", equity_data)
    save_json("decisions.json", decisions_data)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY — {today}")
    print(f"  Portfolio Value: ${portfolio['total_value']:.2f} ({portfolio['total_return_pct']:+.2f}%)")
    print(f"  Cash: ${portfolio['cash']:.2f} ({portfolio['cash']/portfolio['total_value']*100:.1f}%)")
    print(f"  Positions: {len(portfolio['positions'])}")
    print(f"  Trades today: {len(new_trades)}")
    for pos in portfolio["positions"]:
        pnl_pct = (pos["current_price"] - pos["avg_cost"]) / pos["avg_cost"] * 100
        mkt_val = pos["quantity"] * pos["current_price"]
        print(f"    {pos['symbol']}: {pos['quantity']}sh @ ${pos['avg_cost']:.2f} → ${pos['current_price']:.2f} ({pnl_pct:+.1f}%) = ${mkt_val:.2f}")
    print(f"{'='*60}\n")

    return portfolio

if __name__ == "__main__":
    main()
