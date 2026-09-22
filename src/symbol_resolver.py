"""Kullanicinin Telegram'a yazdigi serbest metni (orn. "thyao", "BTC",
"us:AAPL") analiz edilebilir bir (market, tanimlayici) ciftine cevirir.

Tasarim karari: sembolun GERCEKTEN var olup olmadigi Yahoo/CoinGecko'ya
kucuk bir dogrulama cagrisi yapilarak test edilir - sabit bir listeye
bakilmaz. Boylece gunluk raporun evreninde (98 BIST + 30 ABD + 50 kripto)
OLMAYAN bir sembol de sorgulanabilir; yeter ki veri kaynaginda bulunsun.

Belirsizlik (ayni kisaltma hem BIST'te hem kriptoda varsa) sessizce bir
tarafa karar verilerek degil, cagirana birden fazla aday donulerek
cozulur - kullaniciya sorulur.
"""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import requests

import data_bist_us
import data_crypto

COINGECKO_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
SEARCH_TIMEOUT = 15

# COIN_ID_TO_YAHOO_TICKER'dan turetilen ters harita: "BTC" -> "bitcoin".
# Yahoo ticker'larindaki CoinMarketCap son ekleri (UNI7083-USD) temizlenir.
_TICKER_TO_COIN_ID: dict[str, str] = {}
for _coin_id, _yahoo in data_crypto.COIN_ID_TO_YAHOO_TICKER.items():
    _base = _yahoo.replace("-USD", "")
    _clean = re.sub(r"\d+$", "", _base)  # UNI7083 -> UNI
    _TICKER_TO_COIN_ID.setdefault(_clean.upper(), _coin_id)
    _TICKER_TO_COIN_ID.setdefault(_base.upper(), _coin_id)
# coin_id'nin kendisiyle de yazilabilsin ("bitcoin", "avalanche-2").
for _coin_id in data_crypto.COIN_ID_TO_YAHOO_TICKER:
    _TICKER_TO_COIN_ID.setdefault(_coin_id.upper(), _coin_id)

# Kullanicinin acikca pazar belirtmesi icin kabul edilen onekler.
MARKET_PREFIXES = {
    "bist": "bist", "bi": "bist", "tr": "bist",
    "us": "us", "abd": "us", "nasdaq": "us", "nyse": "us",
    "kripto": "crypto", "crypto": "crypto", "coin": "crypto",
}

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9.\-]{1,20}$")


def parse_input(text: str) -> tuple[str | None, str]:
    """Ham metni (istenen_market | None, sembol) olarak ayirir.

    "us:AAPL", "us AAPL", "kripto btc" gibi biciMleri kabul eder.
    """
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^/analiz\s+", "", cleaned, flags=re.IGNORECASE)
    parts = re.split(r"[:\s]+", cleaned, maxsplit=1)
    if len(parts) == 2 and parts[0].lower() in MARKET_PREFIXES:
        return MARKET_PREFIXES[parts[0].lower()], parts[1].strip()
    return None, cleaned


def looks_like_symbol(token: str) -> bool:
    """Gelen metin bir sembol sorgusu olabilir mi? (Sohbet cumlelerini eler.)"""
    return bool(TOKEN_PATTERN.match(token or ""))


def _has_price_data(ticker: str) -> bool:
    hist = data_bist_us.fetch_history(ticker, period="5d")
    return hist is not None and not hist.empty


def _coingecko_search(query: str) -> str | None:
    """Statik haritada olmayan kriptolar icin CoinGecko arama ucu.

    Yalnizca TAM sembol/isim eslesmesi kabul edilir; CoinGecko'nun bulanik
    eslesmeleri (orn. "THY" arandiginda cikan alakasiz tokenlar) bir BIST
    sembolunu yanlislikla kripto sanmamiza yol acabilir.
    """
    try:
        resp = requests.get(COINGECKO_SEARCH_URL, params={"query": query}, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        coins = resp.json().get("coins", [])
    except Exception:
        return None

    q = query.upper()
    for coin in coins:
        if (coin.get("symbol") or "").upper() == q or (coin.get("id") or "").upper() == q:
            return coin.get("id")
    return None


def resolve(text: str) -> dict:
    """Serbest metni analiz edilebilir adaylara cevirir.

    Doner: {"input": ..., "candidates": [{"market", "identifier", "label"}],
            "error": None | str}
    - candidates 1 elemanliysa dogrudan analiz edilebilir.
    - 1'den fazlaysa cagiran kullaniciya hangisini kastettigini sormalidir.
    - bos ve error doluysa sembol hicbir kaynakta bulunamadi.
    """
    wanted_market, raw = parse_input(text)
    result = {"input": raw, "candidates": [], "error": None}

    if not looks_like_symbol(raw):
        result["error"] = "Bu bir sembol gibi gorunmuyor."
        return result

    token = raw.upper()
    # Kullanici zaten ".IS" yazdiysa BIST'i kastediyordur.
    if token.endswith(".IS"):
        wanted_market = wanted_market or "bist"
        token = token[:-3]

    candidates: list[dict] = []

    # 1) Kripto: once statik harita (bedava, aninda), sonra CoinGecko aramasi.
    if wanted_market in (None, "crypto"):
        coin_id = _TICKER_TO_COIN_ID.get(token)
        if coin_id is None and wanted_market == "crypto":
            coin_id = _coingecko_search(token)
        if coin_id:
            candidates.append({"market": "crypto", "identifier": coin_id, "label": f"{token} (kripto)"})

    # 2) BIST: THYAO -> THYAO.IS
    if wanted_market in (None, "bist"):
        bist_ticker = f"{token}.IS"
        if _has_price_data(bist_ticker):
            candidates.append({"market": "bist", "identifier": bist_ticker, "label": f"{bist_ticker} (BIST)"})

    # 3) ABD: yalnizca BIST'te bulunmadiysa VEYA acikca istendiyse.
    #    Neden kosullu: bazi BIST kisaltmalari Yahoo'da baska bir ABD/yabanci
    #    hisseyle cakisabiliyor; BIST eslesmesi varken ikinci bir aday sormak
    #    kullaniciyi gereksiz yere yoruyor.
    if wanted_market == "us" or (wanted_market is None and not candidates):
        if _has_price_data(token):
            candidates.append({"market": "us", "identifier": token, "label": f"{token} (ABD)"})

    # 4) Hicbiri tutmadiysa, son care olarak kriptoda serbest arama.
    if not candidates and wanted_market is None:
        coin_id = _coingecko_search(token)
        if coin_id:
            candidates.append({"market": "crypto", "identifier": coin_id, "label": f"{token} (kripto)"})

    result["candidates"] = candidates
    if not candidates:
        result["error"] = (
            f"'{raw}' Yahoo Finance veya CoinGecko'da bulunamadi. "
            "BIST icin sade kod (THYAO), ABD icin ticker (AAPL), kripto icin "
            "kisaltma (BTC) yazabilirsin. Kararsiz kaldiysam 'bist:THYAO', "
            "'us:AAPL', 'kripto:BTC' bicimiyle pazari da belirtebilirsin."
        )
    return result


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(arg, "->", resolve(arg))
