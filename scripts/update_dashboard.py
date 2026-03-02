#!/usr/bin/env python3
"""
LukaFund Dashboard Data Generator
Generates dashboard_data.json consumed by index.html
"""

import json
import os
from datetime import datetime, date

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

def days_since(date_str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (date.today() - d).days
    except:
        return 0

def calculate_win_rate(trades):
    sells = [t for t in trades if t["action"] == "SELL" and "realized_pnl" in t]
    if not sells:
        return 0.0
    wins = [t for t in sells if t["realized_pnl"] > 0]
    return round(len(wins) / len(sells) * 100, 1)

def main():
    portfolio = load_json("portfolio.json")
    trades_data = load_json("trades.json")
    equity_data = load_json("equity_curve.json")
    decisions_data = load_json("decisions.json")

    all_trades = trades_data["trades"]

    # Build positions with P&L
    positions = []
    for pos in portfolio["positions"]:
        avg_cost = pos["avg_cost"]
        current = pos["current_price"]
        qty = pos["quantity"]
        pnl_dollar = round((current - avg_cost) * qty, 2)
        pnl_pct = round((current - avg_cost) / avg_cost * 100, 2)
        mkt_val = round(current * qty, 2)

        # Conviction score: 1-5 stars based on P&L %
        if pnl_pct > 20:
            conviction = 5
        elif pnl_pct > 10:
            conviction = 4
        elif pnl_pct > 0:
            conviction = 3
        elif pnl_pct > -10:
            conviction = 2
        else:
            conviction = 1

        positions.append({
            "symbol": pos["symbol"],
            "quantity": qty,
            "avg_cost": avg_cost,
            "current_price": current,
            "market_value": mkt_val,
            "pnl_dollar": pnl_dollar,
            "pnl_pct": pnl_pct,
            "conviction": conviction,
            "entry_date": pos.get("entry_date", ""),
            "type": pos.get("type", "long")
        })

    # Sort positions by market value desc
    positions.sort(key=lambda x: x["market_value"], reverse=True)

    # Stats
    best = max(positions, key=lambda x: x["pnl_pct"]) if positions else None
    worst = min(positions, key=lambda x: x["pnl_pct"]) if positions else None
    win_rate = calculate_win_rate(all_trades)
    days_active = days_since(portfolio["inception_date"])

    stats = {
        "total_return_pct": portfolio["total_return_pct"],
        "total_return_dollar": round(portfolio["total_value"] - portfolio["starting_capital"], 2),
        "win_rate": win_rate,
        "total_trades": len(all_trades),
        "days_active": max(days_active, 1),
        "cash_pct": round(portfolio["cash"] / portfolio["total_value"] * 100, 1),
        "best_position": {"symbol": best["symbol"], "pnl_pct": best["pnl_pct"]} if best else None,
        "worst_position": {"symbol": worst["symbol"], "pnl_pct": worst["pnl_pct"]} if worst else None,
    }

    # Recent decisions (last 5 decision days)
    recent_decisions = decisions_data["decisions"][-5:]
    recent_decisions_clean = []
    for day in recent_decisions:
        active = [d for d in day["decisions"] if d["action"] in ("BUY", "SELL", "SHORT")]
        recent_decisions_clean.append({
            "date": day["date"],
            "summary": day["summary"],
            "portfolio_value": day["portfolio_value"],
            "active_trades": active,
            "holds": len([d for d in day["decisions"] if d["action"] == "HOLD"])
        })

    dashboard_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "portfolio": portfolio,
        "positions": positions,
        "recent_trades": all_trades[-10:][::-1],  # Last 10, newest first
        "recent_decisions": recent_decisions_clean[::-1],  # Newest first
        "equity_curve": equity_data["curve"],
        "stats": stats
    }

    # Save to data dir (served from GitHub Pages)
    save_json("dashboard_data.json", dashboard_data)
    print(f"✅ dashboard_data.json generated — {len(positions)} positions, {len(all_trades)} total trades")
    return dashboard_data

if __name__ == "__main__":
    main()
