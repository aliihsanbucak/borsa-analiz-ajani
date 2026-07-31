"""BIST ve ABD hisseleri için yfinance ile veri çekme.

BIST sembolleri Yahoo Finance'de '.IS' son ekiyle bulunur (örn. THYAO.IS).
yfinance 1.x, Yahoo'nun bot engellemesini aşmak için curl_cffi kullanır -
bu yüzden plain requests ile değiştirilmemeli.
"""
import time
import yfinance as yf
import pandas as pd

FUNDAMENTAL_FIELDS = (
    "trailingPE", "priceToBook", "dividendYield", "profitMargins",
    "earningsGrowth", "debtToEquity", "trailingEps", "marketCap",
    "currentRatio", "returnOnEquity",
)


def fetch_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame | None:
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df is None or df.empty:
            return None
        return df
    except Exception:
        return None


def fetch_fundamentals(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return {}
    if not info:
        return {}
    return {field: info.get(field) for field in FUNDAMENTAL_FIELDS}


def fetch_symbol_bundle(ticker: str, market: str) -> dict:
    """Bir hisse için kısa (gösterge) + uzun (örüntü arama) geçmiş ve temel verileri toplar."""
    result = {"symbol": ticker, "market": market, "error": None}

    history_1y = fetch_history(ticker, period="1y")
    if history_1y is None:
        result["error"] = "Fiyat verisi alınamadı"
        return result

    time.sleep(1)
    history_long = fetch_history(ticker, period="10y")
    if history_long is None or history_long.empty:
        history_long = history_1y

    time.sleep(1)
    fundamentals = fetch_fundamentals(ticker)

    result["history_1y"] = history_1y
    result["history_long"] = history_long
    result["fundamentals"] = fundamentals
    return result
