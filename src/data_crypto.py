"""CoinGecko ücretsiz halka açık API'si ile kripto veri çekme (API key gerekmez).

Not: /coins/{id}/ohlc endpoint'i 30 günden sonra 4 günlük mumlara düşer,
bu yüzden günlük göstergeler için kullanılmaz. Bunun yerine market_chart
endpoint'inin close-price serisi kullanılır.

ÖNEMLİ - gerçek kök neden (27 Ağustos 2026'da canlı teşhis edildi): CoinGecko'nun
ara sıra başarısız olması CoinGecko'ya ÖZGÜ bir kararsızlık DEĞİL. Aynı anda
api.coingecko.com, api.binance.com, api.exchange.coinbase.com, api.kraken.com ve
min-api.cryptocompare.com hepsi AYNI hatayla (SSLError: WRONG_VERSION_NUMBER)
başarısız olurken, kripto-dışı finans siteleri (query1.finance.yahoo.com,
en.wikipedia.org, fred.stlouisfed.org) sorunsuz çalışıyordu - bu, bir ara katmanın
(muhtemelen ISP/DPI seviyesinde, Türkiye'de kripto borsalarına erişim kısıtlamaları
bilinen bir durum) kripto borsası/veri API'si kategorisindeki alan adlarını
engellediğinin klasik belirtisi. Yani Binance de CoinGecko ile AYNI ANDA
engellenebiliyor - birbirinden bağımsız bir yedek değil. Buna karşılık Yahoo
Finance (bu projede zaten BIST/ABD hisseleri için güvenilir şekilde kullanılıyor)
kripto ticker'larını da destekliyor (örn. BTC-USD) ve bu ağda ENGELLENMEMİŞ
durumda - bu yüzden asıl dayanıklı yedek katman Yahoo Finance'tir.

Ayrıca: "hangi coinler taranacak" (fetch_top_n_market_cap) artık CoinGecko'nun
canlı piyasa değeri sıralamasına GÜVENMİYOR - CURATED_TOP_COINS sabit listesini
kullanıyor (27 Ağustos 2026'da değiştirildi, bkz. o sabitin üstündeki yorum).
Sebep: CoinGecko'nun ham "piyasa değerine göre ilk N" sıralaması stablecoin,
tokenize RWA fonu, borsa token'ı ve çok yeni/spekülatif ürünleri "kripto para"
gibi rapora sokabiliyordu - bu artık mekanik/elle seçilmiş bir evrenle önleniyor
(BIST/ABD evreni gibi). CoinGecko sadece bu sabit listedeki coinlerin fiyat/temel
verisini zenginleştirmek için kullanılıyor.

Fiyat verisi için üç katmanlı dayanıklılık:
1. Her CoinGecko isteği 3 kez, artan bekleme süresiyle tekrar denenir (_get_with_retry).
2. Bir coin'in GEÇMİŞ FİYAT verisi (market_chart) başarısız olursa önce Binance'in
   ücretsiz `klines` API'sine denenir (bazı ağlarda CoinGecko engelliyken Binance
   engellenmemiş olabilir) - ama yukarıdaki gözlem gereği bu genelde işe yaramayacaktır.
3. Binance de başarısız olursa (veya CoinGecko'nun `symbol` alanı hiç yoksa),
   Yahoo Finance'e (COIN_ID_TO_YAHOO_TICKER statik eşlemesi + yfinance) düşülür -
   canlı test edilmiş, bu ağda güvenilir. CoinGecko'nun snapshot'ı (market_cap_rank,
   ATH%, FDV gibi zengin alanlar) da tamamen erişilemezse, en azından piyasa
   değeri/güncel fiyat Yahoo'nun `.info`'sundan alınır (bkz. fetch_symbol_bundle).
"""
import time
import random
import requests
import yfinance as yf
import pandas as pd

BASE_URL = "https://api.coingecko.com/api/v3"
BINANCE_URL = "https://api.binance.com/api/v3"
TIMEOUT = 15
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0

# CoinGecko tamamen erişilemez olduğunda (snapshot başarısız) bile Yahoo Finance
# yedeğinin çalışabilmesi için CoinGecko'nun 'symbol' alanına BAĞIMLI OLMAYAN
# statik bir coin_id -> Yahoo ticker eşlemesi. CURATED_TOP_COINS ile birebir
# örtüşür, her biri canlı olarak yf.Ticker(...).history() ile
# doğrulandı (27 Ağustos 2026). Bazı coinler Yahoo'da CoinMarketCap ID son ekiyle
# listeleniyor (örn. UNI7083-USD) çünkü sembol başka bir varlıkla çakışıyor;
# Fantom, Sonic'e (S) yeniden markalandığı için S32684-USD kullanılıyor.
COIN_ID_TO_YAHOO_TICKER = {
    "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "tether": "USDT-USD",
    "ripple": "XRP-USD", "binancecoin": "BNB-USD", "solana": "SOL-USD",
    "usd-coin": "USDC-USD", "dogecoin": "DOGE-USD", "cardano": "ADA-USD",
    "tron": "TRX-USD", "avalanche-2": "AVAX-USD", "chainlink": "LINK-USD",
    "the-open-network": "TON-USD", "shiba-inu": "SHIB-USD", "polkadot": "DOT-USD",
    "bitcoin-cash": "BCH-USD", "near": "NEAR-USD", "litecoin": "LTC-USD",
    "uniswap": "UNI7083-USD", "internet-computer": "ICP-USD", "aptos": "APT21794-USD",
    "stellar": "XLM-USD", "monero": "XMR-USD", "ethereum-classic": "ETC-USD",
    "cosmos": "ATOM-USD", "hedera-hashgraph": "HBAR-USD", "filecoin": "FIL-USD",
    "arbitrum": "ARB-USD", "vechain": "VET-USD", "optimism": "OP-USD",
    "the-graph": "GRT6719-USD", "aave": "AAVE-USD", "algorand": "ALGO-USD",
    "render-token": "RENDER-USD", "immutable-x": "IMX10603-USD", "fantom": "S32684-USD",
    "quant-network": "QNT-USD", "sui": "SUI20947-USD", "injective-protocol": "INJ-USD",
    "sei-network": "SEI-USD", "thorchain": "RUNE-USD", "tezos": "XTZ-USD",
    "flow": "FLOW-USD", "theta-token": "THETA-USD", "axie-infinity": "AXS-USD",
    "eos": "EOS-USD", "kava": "KAVA-USD", "chiliz": "CHZ-USD", "gala": "GALA-USD",
    "pancakeswap-token": "CAKE-USD", "bittensor": "TAO22974-USD",
}

# Elle seçilmiş, genel olarak tanınan kripto para evreni - fetch_top_n_market_cap
# artık CoinGecko'nun HAM piyasa değeri sıralamasını kullanmıyor, bu sabit listeyi
# kullanıyor (27 Ağustos 2026'da kullanıcı geri bildirimiyle değiştirildi).
# Neden: CoinGecko'nun "piyasa değerine göre ilk N" sıralaması, gerçek/tanınan
# kripto paraların yanına stablecoin'leri (dai, usds, paypal-usd), tokenize
# edilmiş RWA fonlarını (blackrock-usd-institutional-digital-liquidity-fund,
# tether-gold, hashnote-usyc), borsa token'larını (okb, leo-token, whitebit) ve
# çok yeni/spekülatif ürünleri (figure-heloc, pump-fun, aster-2, memecore vb.)
# de karıştırabiliyor - bunlar "kripto para" analizi için anlamlı bir evren
# oluşturmuyor. BIST/ABD evreninin de (config.yaml) elle seçilmiş, best-effort
# bir liste olduğu gibi, kripto evreni de artık aynı mekanik/şeffaf prensiple
# elle seçiliyor - CoinGecko sadece bu sabit listedeki coinlerin fiyat/temel
# verisini ZENGİNLEŞTİRMEK için kullanılıyor, HANGİ coinlerin taranacağına karar
# vermek için değil.
CURATED_TOP_COINS = [
    "bitcoin", "ethereum", "tether", "ripple", "binancecoin", "solana",
    "usd-coin", "dogecoin", "cardano", "tron", "avalanche-2", "chainlink",
    "the-open-network", "shiba-inu", "polkadot", "bitcoin-cash", "near",
    "litecoin", "uniswap", "internet-computer", "aptos", "stellar",
    "monero", "ethereum-classic", "cosmos", "hedera-hashgraph", "filecoin",
    "arbitrum", "vechain", "optimism", "the-graph", "aave", "algorand",
    "render-token", "immutable-x", "fantom", "quant-network", "sui",
    "injective-protocol", "sei-network", "thorchain", "tezos", "flow",
    "theta-token", "axie-infinity", "eos", "kava", "chiliz", "gala",
    "pancakeswap-token", "bittensor",
]


def _get_with_retry(url: str, params: dict | None = None, retries: int = MAX_RETRIES) -> requests.Response | None:
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except Exception:
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF_BASE * (attempt + 1) + random.uniform(0, 1))
    return None


def _fetch_binance_klines(binance_symbol: str, days: int = 365) -> pd.DataFrame | None:
    """CoinGecko'nun geçmiş fiyat verisi başarısız olduğunda kullanılan yedek
    kaynak. binance_symbol örn. 'BTC' -> 'BTCUSDT' çifti denenir. Binance'in
    ücretsiz, key gerektirmeyen klines API'si - canlı test edildi, gerçek
    OHLCV veriyor."""
    if not binance_symbol:
        return None
    pair = f"{binance_symbol.upper()}USDT"
    try:
        resp = requests.get(
            f"{BINANCE_URL}/klines",
            params={"symbol": pair, "interval": "1d", "limit": min(days, 1000)},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return None
    if not rows or not isinstance(rows, list):
        return None

    records = []
    for row in rows:
        # [open_time, open, high, low, close, volume, close_time, ...]
        records.append({
            "Date": pd.to_datetime(row[0], unit="ms"),
            "Close": float(row[4]),
            "Volume": float(row[5]),
        })
    df = pd.DataFrame(records).set_index("Date")[["Close", "Volume"]]
    return df


def _fetch_yahoo_crypto_history(yahoo_ticker: str | None) -> pd.DataFrame | None:
    """CoinGecko VE Binance başarısız olduğunda (veya binance_symbol yoksa)
    kullanılan son yedek katman. Bu ağda kripto borsası API'leri engellenmiş
    olsa bile Yahoo Finance erişilebilir kalıyor (canlı doğrulandı, bkz. modül
    docstring'i) - bu proje zaten BIST/ABD için aynı yfinance altyapısını
    güvenilir şekilde kullanıyor."""
    if not yahoo_ticker:
        return None
    try:
        df = yf.Ticker(yahoo_ticker).history(period="1y", interval="1d")
        if df is None or df.empty:
            return None
        return df.rename(columns={"Volume": "Volume", "Close": "Close"})[["Close", "Volume"]]
    except Exception:
        return None


def _fetch_yahoo_crypto_snapshot(yahoo_ticker: str | None) -> dict:
    """CoinGecko'nun snapshot'ı (fetch_snapshot) tamamen başarısız olduğunda,
    en azından piyasa değeri/güncel fiyat bağlamını Yahoo'dan kurtarır. Rank,
    24s değişim, ATH%, FDV gibi CoinGecko'ya özgü alanlar burada yok - ama
    crypto_snapshot.interpret_crypto_snapshot ve scoring.crypto_score bu
    alanları zaten `is not None` kontrolleriyle güvenle atlıyor."""
    if not yahoo_ticker:
        return {}
    try:
        info = yf.Ticker(yahoo_ticker).info
    except Exception:
        return {}
    if not info:
        return {}
    return {
        "symbol": yahoo_ticker.split("-")[0].lower(),
        "current_price": info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "circulating_supply": info.get("circulatingSupply"),
        "max_supply": info.get("maxSupply"),
    }


def fetch_ohlc_daily(coin_id: str, days: int = 365, binance_symbol: str | None = None) -> pd.DataFrame | None:
    resp = _get_with_retry(
        f"{BASE_URL}/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": days},
    )
    if resp is not None:
        try:
            data = resp.json()
            prices = data.get("prices", [])
            volumes = data.get("total_volumes", [])
            if prices:
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
                if not df.empty:
                    return df
        except Exception:
            pass

    # CoinGecko basarisiz oldu (retry'lardan sonra da) - Binance yedegine dus
    binance_df = _fetch_binance_klines(binance_symbol, days)
    if binance_df is not None and not binance_df.empty:
        return binance_df

    # Binance de basarisiz (ayni ag engeline takilmis olabilir) - Yahoo Finance'e dus
    yahoo_ticker = COIN_ID_TO_YAHOO_TICKER.get(coin_id)
    return _fetch_yahoo_crypto_history(yahoo_ticker)


def fetch_top_n_market_cap(n: int = 50) -> list[str]:
    """Taranacak n kripto parayı döner. CoinGecko'nun CANLI piyasa değeri
    sıralamasını KULLANMIYOR (27 Ağustos 2026'da bilinçli olarak kaldırıldı) -
    o sıralama stablecoin/RWA-fonu/borsa-token'ı/çok yeni-spekülatif ürünleri
    "kripto para" gibi rapora sokabiliyordu. Bunun yerine CURATED_TOP_COINS
    sabit, elle seçilmiş listesinden ilk n tanesi kullanılır (bkz. o sabitin
    üstündeki yorum) - BIST/ABD evreninin config.yaml'da elle seçilmiş olmasıyla
    aynı prensip."""
    return CURATED_TOP_COINS[:n]


def fetch_snapshot(coin_ids: list[str]) -> dict[str, dict]:
    if not coin_ids:
        return {}
    resp = _get_with_retry(
        f"{BASE_URL}/coins/markets",
        params={"vs_currency": "usd", "ids": ",".join(coin_ids)},
    )
    if resp is None:
        return {}
    try:
        rows = resp.json()
    except Exception:
        return {}

    snapshot = {}
    for row in rows:
        snapshot[row["id"]] = {
            "symbol": row.get("symbol"),  # Binance yedek kaynagi icin gerekli (fetch_symbol_bundle)
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
            "max_supply": row.get("max_supply"),
            "fully_diluted_valuation": row.get("fully_diluted_valuation"),
        }
    return snapshot


def fetch_global_dominance() -> dict:
    resp = _get_with_retry(f"{BASE_URL}/global")
    if resp is None:
        return {}
    try:
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

    coin_snap = snapshot.get(coin_id, {})
    binance_symbol = coin_snap.get("symbol")
    history = fetch_ohlc_daily(coin_id, days=365, binance_symbol=binance_symbol)
    if history is None or history.empty:
        result["error"] = "Fiyat verisi alınamadı"
        return result
    time.sleep(0.3)

    # CoinGecko snapshot'ı tamamen başarısızsa (coin_snap boş - discovery/snapshot
    # da engellenmiş olabilir), Yahoo Finance'ten en azından piyasa değeri/fiyat
    # bağlamını kurtarmaya çalış - tamamen boş kalmaktan iyidir.
    if not coin_snap:
        yahoo_ticker = COIN_ID_TO_YAHOO_TICKER.get(coin_id)
        coin_snap = _fetch_yahoo_crypto_snapshot(yahoo_ticker)

    result["history_1y"] = history
    result["history_long"] = history  # kripto için ücretsiz katmanda uzun geçmiş sınırlı
    result["crypto_snapshot"] = coin_snap
    return result
