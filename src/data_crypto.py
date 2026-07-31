"""CoinGecko ücretsiz halka açık API'si ile kripto veri çekme (API key gerekmez).

Not: /coins/{id}/ohlc endpoint'i 30 günden sonra 4 günlük mumlara düşer,
bu yüzden günlük göstergeler için kullanılmaz. Bunun yerine market_chart
endpoint'inin close-price serisi kullanılır.
"""
import time
import requests
import pandas as pd

BASE_URL = "https://api.coingecko.com/api/v3"
TIMEOUT = 15


def fetch_ohlc_daily(coin_id: str, days: int = 365) -> pd.DataFrame | None:
    try:
        resp = requests.get(
            f"{BASE_URL}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": days},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])
    if not prices:
        return None

    df = pd.DataFrame(prices, columns=["timestamp", "Close"])
    df["Date"] = pd.to_datetime(df["timestamp"], unit="ms")
    if volumes:
        vol_df = pd.DataFrame(volumes, columns=["timestamp", "Volume"])
        df["Volume"] = vol_df["Volume"]
    else:
        df["Volume"] = None

    df = df.set_index("Date")[["Close", "Volume"]]
    # market_chart bazen aynı güne ait birden fazla veri noktası dönebilir; günlük son değeri al
    df = df.resample("D").last().dropna(subset=["Close"])
    return df


def fetch_snapshot(coin_ids: list[str]) -> dict[str, dict]:
    if not coin_ids:
        return {}
    try:
        resp = requests.get(
            f"{BASE_URL}/coins/markets",
            params={"vs_currency": "usd", "ids": ",".join(coin_ids)},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return {}

    snapshot = {}
    for row in rows:
        snapshot[row["id"]] = {
            "current_price": row.get("current_price"),
            "market_cap": row.get("market_cap"),
            "market_cap_rank": row.get("market_cap_rank"),
            "total_volume": row.get("total_volume"),
            "price_change_percentage_24h": row.get("price_change_percentage_24h"),
            "high_24h": row.get("high_24h"),
            "low_24h": row.get("low_24h"),
            "ath": row.get("ath"),
            "ath_change_percentage": row.get("ath_change_percentage"),
            "circulating_supply": row.get("circulating_supply"),
        }
    return snapshot


def fetch_global_dominance() -> dict:
    try:
        resp = requests.get(f"{BASE_URL}/global", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception:
        return {}
    return {
        "btc_dominance": data.get("market_cap_percentage", {}).get("btc"),
        "eth_dominance": data.get("market_cap_percentage", {}).get("eth"),
        "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
    }


def fetch_symbol_bundle(coin_id: str, snapshot: dict) -> dict:
    result = {"symbol": coin_id, "market": "crypto", "error": None}

    history = fetch_ohlc_daily(coin_id, days=365)
    if history is None or history.empty:
        result["error"] = "Fiyat verisi alınamadı"
        return result
    time.sleep(1)

    result["history_1y"] = history
    result["history_long"] = history  # kripto için ücretsiz katmanda uzun geçmiş sınırlı
    result["crypto_snapshot"] = snapshot.get(coin_id, {})
    return result
