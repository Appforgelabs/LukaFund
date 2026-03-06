#!/usr/bin/env python3
"""
LukaFund Market Data Module
Primary: Alpaca Market Data API (free tier, same key as paper trading)
Fallback: Finnhub API
Historical candles: Polygon.io
"""

import requests
import time
import json
from datetime import datetime, timedelta

# Alpaca (primary quotes)
ALPACA_KEY    = "PKSAEPZ4YMNDN4ERB6Z7DLVWOK"
ALPACA_SECRET = "FeJjXmsXSmYX1tdXTxp6qb8fUX1SLE8LGyrLEvmAsAcK"
ALPACA_DATA   = "https://data.alpaca.markets/v2"
ALPACA_HEADERS = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
}

# Finnhub (fallback quotes)
FINNHUB_API_KEY = "d6952r9r01qs7u9kq240d6952r9r01qs7u9kq24g"
FINNHUB_BASE    = "https://finnhub.io/api/v1"

# Polygon (historical candles)
POLYGON_API_KEY = "D2BcKzvYOpCfDBmHedtLAHu2CV3jKtU7"
POLYGON_BASE    = "https://api.polygon.io"

_cache = {}


def _get_alpaca(path, params=None):
    """Alpaca Market Data API request."""
    cache_key = f"alp:{path}:{json.dumps(params or {}, sort_keys=True)}"
    if cache_key in _cache:
        return _cache[cache_key]
    try:
        r = requests.get(f"{ALPACA_DATA}{path}", headers=ALPACA_HEADERS,
                         params=params or {}, timeout=10)
        r.raise_for_status()
        data = r.json()
        _cache[cache_key] = data
        time.sleep(0.1)
        return data
    except Exception as e:
        print(f"  [alpaca] Error {path}: {e}")
        return None


def _get_finnhub(endpoint, params):
    """Finnhub API request (fallback)."""
    cache_key = f"fh:{endpoint}:{json.dumps(params, sort_keys=True)}"
    if cache_key in _cache:
        return _cache[cache_key]
    params["token"] = FINNHUB_API_KEY
    try:
        r = requests.get(f"{FINNHUB_BASE}{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        _cache[cache_key] = data
        time.sleep(0.2)
        return data
    except Exception as e:
        print(f"  [finnhub] Error {endpoint}: {e}")
        return None


def _get_polygon(path, params=None):
    """Polygon API request (candle history)."""
    cache_key = f"poly:{path}:{json.dumps(params or {}, sort_keys=True)}"
    if cache_key in _cache:
        return _cache[cache_key]
    p = dict(params or {})
    p["apiKey"] = POLYGON_API_KEY
    try:
        r = requests.get(f"{POLYGON_BASE}{path}", params=p, timeout=10)
        r.raise_for_status()
        data = r.json()
        _cache[cache_key] = data
        time.sleep(13)  # Polygon free tier: 5 req/min
        return data
    except Exception as e:
        print(f"  [polygon] Error {path}: {e}")
        return None


def get_quote(symbol):
    """
    Returns: {price, change_pct, volume, high, low, open, prev_close}
    Primary: Alpaca Market Data API
    Fallback: Finnhub
    """
    # Try Alpaca first
    data = _get_alpaca(f"/stocks/{symbol}/snapshot")
    if data and "snapshot" in data:
        snap = data["snapshot"]
        daily = snap.get("dailyBar", {})
        prev  = snap.get("prevDailyBar", {})
        trade = snap.get("latestTrade", {})
        price = trade.get("p") or daily.get("c")
        prev_close = prev.get("c") or daily.get("o")
        if price:
            change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0
            return {
                "symbol": symbol,
                "price": round(price, 2),
                "change_pct": change_pct,
                "high": round(daily.get("h", price), 2),
                "low": round(daily.get("l", price), 2),
                "open": round(daily.get("o", price), 2),
                "prev_close": round(prev_close, 2) if prev_close else None,
                "volume": int(daily.get("v", 0)),
                "source": "alpaca"
            }

    # Fallback: Finnhub
    data = _get_finnhub("/quote", {"symbol": symbol})
    if data and data.get("c", 0) != 0:
        return {
            "symbol": symbol,
            "price": round(data["c"], 2),
            "change_pct": round(data["dp"], 2) if data.get("dp") else 0.0,
            "high": round(data["h"], 2),
            "low": round(data["l"], 2),
            "open": round(data["o"], 2),
            "prev_close": round(data["pc"], 2),
            "volume": data.get("v", 0),
            "source": "finnhub"
        }

    return None


def get_candles(symbol, days=60):
    """
    Returns list of {date, open, high, low, close, volume} dicts, oldest first.
    Primary: Alpaca bars API
    Fallback: Polygon.io
    """
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Try Alpaca bars first
    data = _get_alpaca(f"/stocks/{symbol}/bars", {
        "timeframe": "1Day",
        "start": f"{start_date}T00:00:00Z",
        "end": f"{end_date}T23:59:59Z",
        "limit": 150,
        "adjustment": "all"
    })
    if data and data.get("bars"):
        candles = []
        for bar in data["bars"]:
            ts = bar.get("t", "")
            date_str = ts[:10] if ts else ""
            candles.append({
                "date": date_str,
                "open": round(bar["o"], 2),
                "high": round(bar["h"], 2),
                "low": round(bar["l"], 2),
                "close": round(bar["c"], 2),
                "volume": int(bar.get("v", 0))
            })
        if candles:
            return candles

    # Fallback: Polygon
    path = f"/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
    data = _get_polygon(path, {"adjusted": "true", "sort": "asc", "limit": 120})
    if data and data.get("results"):
        candles = []
        for bar in data["results"]:
            ts_ms = bar.get("t", 0)
            candles.append({
                "date": datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d"),
                "open": round(bar["o"], 2),
                "high": round(bar["h"], 2),
                "low": round(bar["l"], 2),
                "close": round(bar["c"], 2),
                "volume": int(bar.get("v", 0))
            })
        return candles

    return []


def get_company_news(symbol, days=3):
    """Returns list of recent news headlines via Finnhub."""
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    data = _get_finnhub("/company-news", {
        "symbol": symbol,
        "from": start_date,
        "to": end_date
    })
    if not data:
        return []
    headlines = []
    for item in data[:5]:
        headlines.append({
            "headline": item.get("headline", ""),
            "source": item.get("source", ""),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d")
        })
    return headlines


if __name__ == "__main__":
    print("Testing market data (Alpaca primary)...")
    quote = get_quote("TSLA")
    print(f"TSLA: {quote}")
    candles = get_candles("TSLA", days=5)
    print(f"TSLA candles: {len(candles)} bars")
    if candles:
        print(f"  Latest: {candles[-1]}")
