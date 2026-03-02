#!/usr/bin/env python3
"""
LukaFund Decision Maker
Luka's trading strategy: RSI/SMA momentum + volume signals
"""

from datetime import datetime

# Trading universe
WATCHLIST = ["TSLA", "AMZN", "PLTR", "HOOD", "SOFI", "RIVN", "NIO"]

# Bearish universe (short/put candidates)
BEARISH_UNIVERSE = ["RIVN", "NIO"]

# Max position size as fraction of total portfolio
MAX_POSITION_PCT = 0.15
MIN_CASH_RESERVE_PCT = 0.15


def calculate_sma(prices, period=20):
    """Simple Moving Average."""
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)


def calculate_rsi(prices, period=14):
    """Relative Strength Index."""
    if len(prices) < period + 1:
        return None
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d for d in deltas[-period:] if d > 0]
    losses = [-d for d in deltas[-period:] if d < 0]
    
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = round(100 - (100 / (1 + rs)), 1)
    return rsi


def calculate_avg_volume(candles, period=20):
    """Average daily volume over period."""
    vols = [c["volume"] for c in candles[-period:] if c["volume"] > 0]
    if not vols:
        return 0
    return sum(vols) / len(vols)


def get_position(portfolio, symbol):
    """Find existing position for symbol."""
    for pos in portfolio.get("positions", []):
        if pos["symbol"] == symbol:
            return pos
    return None


def generate_decisions(portfolio, quotes, candles_map):
    """
    Core strategy engine. Returns list of decision dicts.
    
    Args:
        portfolio: current portfolio state dict
        quotes: {symbol: quote_dict}
        candles_map: {symbol: [candle_dicts]}
    
    Returns:
        list of {action, symbol, quantity, price, reasoning, conviction}
    """
    decisions = []
    today = datetime.now().strftime("%Y-%m-%d")
    total_value = portfolio["total_value"]
    cash = portfolio["cash"]
    max_per_position = total_value * MAX_POSITION_PCT
    min_cash = total_value * MIN_CASH_RESERVE_PCT

    for symbol in WATCHLIST:
        quote = quotes.get(symbol)
        candles = candles_map.get(symbol, [])
        
        if not quote or not candles or len(candles) < 15:
            decisions.append({
                "date": today,
                "action": "SKIP",
                "symbol": symbol,
                "quantity": 0,
                "price": quote["price"] if quote else 0,
                "reasoning": f"Insufficient data ({len(candles)} candles). Watching.",
                "conviction": 0
            })
            continue

        price = quote["price"]
        closes = [c["close"] for c in candles]
        
        sma20 = calculate_sma(closes, 20)
        sma50 = calculate_sma(closes, 50) if len(closes) >= 50 else None
        rsi = calculate_rsi(closes, 14)
        avg_vol = calculate_avg_volume(candles, 20)
        today_vol = candles[-1]["volume"] if candles else 0
        vol_ratio = (today_vol / avg_vol) if avg_vol > 0 else 1.0
        change_pct = quote["change_pct"]

        existing_position = get_position(portfolio, symbol)
        existing_value = existing_position["quantity"] * price if existing_position else 0
        existing_cost = existing_position["avg_cost"] * existing_position["quantity"] if existing_position else 0
        pnl_pct = ((price - existing_position["avg_cost"]) / existing_position["avg_cost"] * 100) if existing_position else 0

        reasoning_parts = []
        action = "HOLD"
        quantity = 0
        conviction = 2

        # === SELL / STOP SIGNALS (check existing positions first) ===
        if existing_position:
            qty = existing_position["quantity"]

            # Stop loss: down >15%
            if pnl_pct < -15:
                action = "SELL"
                quantity = qty
                reasoning_parts.append(f"STOP LOSS: position down {pnl_pct:.1f}% — cutting losses, discipline over hope")
                conviction = 5

            # Profit take: up >25% → sell 50%
            elif pnl_pct > 25:
                action = "SELL"
                quantity = max(1, qty // 2)
                reasoning_parts.append(f"PROFIT TAKE: position up {pnl_pct:.1f}% — harvesting 50% of gains, let the rest run")
                conviction = 4

            # RSI overbought >75
            elif rsi and rsi > 75:
                action = "SELL"
                quantity = max(1, qty // 2)
                reasoning_parts.append(f"RSI {rsi} — overbought territory, trimming exposure")
                conviction = 3

        # === BUY SIGNALS (only if no position or small position) ===
        if action == "HOLD" and sma20:
            pct_from_sma = ((price - sma20) / sma20) * 100

            can_buy = (cash - min_cash) > 500 and existing_value < max_per_position

            if can_buy:
                # Bullish momentum: above SMA, RSI not overbought, good volume
                if (symbol not in BEARISH_UNIVERSE and
                    pct_from_sma > 2 and
                    rsi and rsi < 60 and
                    vol_ratio > 1.2 and
                    change_pct > 0):
                    
                    affordable_shares = int(min(max_per_position, cash - min_cash) / price)
                    if affordable_shares >= 1:
                        action = "BUY"
                        quantity = affordable_shares
                        reasoning_parts.append(
                            f"MOMENTUM BUY: price ${price} is {pct_from_sma:.1f}% above 20-day SMA ${sma20}, "
                            f"RSI {rsi} (not overbought), volume {vol_ratio:.1f}x average — "
                            f"bullish confluence, entering with {affordable_shares} shares"
                        )
                        conviction = 4

                # Oversold dip buy: below SMA, RSI oversold
                elif (symbol not in BEARISH_UNIVERSE and
                      pct_from_sma < -3 and
                      rsi and rsi < 40):
                    
                    affordable_shares = int(min(max_per_position * 0.5, cash - min_cash) / price)
                    if affordable_shares >= 1:
                        action = "BUY"
                        quantity = affordable_shares
                        reasoning_parts.append(
                            f"OVERSOLD DIP: price ${price} is {abs(pct_from_sma):.1f}% below 20-day SMA, "
                            f"RSI {rsi} — capitulation zone, small position entry"
                        )
                        conviction = 3

                # Bearish: RIVN/NIO near resistance → short simulation (negative qty)
                elif (symbol in BEARISH_UNIVERSE and
                      pct_from_sma > 3 and
                      rsi and rsi > 60):
                    
                    short_shares = int(min(max_per_position * 0.5, cash - min_cash) / price)
                    if short_shares >= 1:
                        action = "SHORT"
                        quantity = short_shares
                        reasoning_parts.append(
                            f"BEARISH PLAY: {symbol} near resistance (RSI {rsi}, {pct_from_sma:.1f}% above SMA) — "
                            f"structurally weak EV play, simulating put via short position"
                        )
                        conviction = 4

        # Build final reasoning string
        if not reasoning_parts:
            if sma20:
                pct_from_sma = ((price - sma20) / sma20) * 100
                reasoning_parts.append(
                    f"HOLD: no signal. Price ${price} ({pct_from_sma:+.1f}% vs SMA20 ${sma20}), "
                    f"RSI {rsi}, vol ratio {vol_ratio:.1f}x. Watching."
                )
            else:
                reasoning_parts.append(f"HOLD: insufficient SMA data.")
            conviction = 1

        decisions.append({
            "date": today,
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "reasoning": " ".join(reasoning_parts),
            "conviction": conviction,
            "indicators": {
                "rsi": rsi,
                "sma20": sma20,
                "vol_ratio": round(vol_ratio, 2),
                "change_pct": change_pct
            }
        })

    return decisions


if __name__ == "__main__":
    print("Decision maker module loaded. Run portfolio_engine.py to execute.")
