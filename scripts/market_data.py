#!/usr/bin/env python3
"""
LukaFund Market Data Module
Fetches real prices from Finnhub API
"""

import requests
import time
import json
from datetime import datetime, timedelta

FINNHUB_API_KEY = "FINNHUB_KEY_REDACTED"
FINNHUB_BASE = "https://finnhub.io/api/v1"

POLYGON_API_KEY = "POLYGON_KEY_REDACTED"
POLYGON_BASE = "https://api.polygon.io"

_cache = {}

def _get_finnhub(endpoint, params):
    """Make a cached Finnhub API request."""
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
    """Make a cached Polygon API request."""
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
    Uses Finnhub for real-time quotes.
    """
    data = _get_finnhub("/quote", {"symbol": symbol})
    if not data or data.get("c", 0) == 0:
        return None
    return {
        "symbol": symbol,
        "price": round(data["c"], 2),
        "change_pct": round(data["dp"], 2) if data.get("dp") else 0.0,
        "high": round(data["h"], 2),
        "low": round(data["l"], 2),
        "open": round(data["o"], 2),
        "prev_close": round(data["pc"], 2),
        "volume": data.get("v", 0)
    }


def get_candles(symbol, days=60):
    """
    Returns list of {date, open, high, low, close, volume} dicts, oldest first.
    Uses Polygon.io for historical OHLCV data.
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    path = f"/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
    data = _get_polygon(path, {"adjusted": "true", "sort": "asc", "limit": 120})
    
    if not data or data.get("status") == "ERROR" or not data.get("results"):
        return []
    
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


def get_company_news(symbol, days=3):
    """
    Returns list of recent news headlines via Finnhub.
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
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
    print("Testing market data...")
    quote = get_quote("TSLA")
    print(f"TSLA: {quote}")
    candles = get_candles("TSLA", days=5)
    print(f"TSLA candles (last 5 days): {len(candles)} records")
    if candles:
        print(f"  Latest: {candles[-1]}")
