"""BIST ve ABD hisseleri için yfinance ile veri çekme.

BIST sembolleri Yahoo Finance'de '.IS' son ekiyle bulunur (örn. THYAO.IS).
yfinance 1.x, Yahoo'nun bot engellemesini aşmak için curl_cffi kullanır -
bu yüzden plain requests ile değiştirilmemeli.
"""
import time
import io
import requests
import yfinance as yf
import pandas as pd

SP500_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

FUNDAMENTAL_FIELDS = (
    "trailingPE", "priceToBook", "dividendYield", "profitMargins",
    # Temettu verimini yfinance'in belirsiz "dividendYield" alanindan degil,
    # dogrudan dividendRate/fiyat oranindan hesaplamak icin (bkz. fundamentals.dividend_yield_pct):
    "dividendRate", "currentPrice",
    "earningsGrowth", "debtToEquity", "trailingEps", "marketCap",
    "currentRatio", "returnOnEquity", "heldPercentInsiders", "heldPercentInstitutions",
    "shortName", "sector",
    # Finansal kalite/sağlık için eklendi (bkz. fundamentals.py yorumlama katmanı):
    "freeCashflow", "ebitda", "totalDebt", "totalCash", "beta",
    "revenueGrowth", "grossMargins", "operatingMargins", "returnOnAssets",
    # WACC/DCF için eklendi (bkz. dcf.py):
    "sharesOutstanding",
    # Karşıt yatırım taraması için eklendi (bkz. contrarian.py, F/S orani):
    "priceToSalesTrailing12Months",
)

# income_stmt'ten cekilen, WACC hesaplaması için gereken alanlar (bkz. dcf.py)
INCOME_STMT_FIELDS = ("Interest Expense", "Tax Rate For Calcs", "EBIT")


def fetch_sp500_symbols() -> list[str]:
    """S&P 500 sembol listesini Wikipedia'dan çeker (canlı test edildi: 503
    sembol, GICS sektörü dahil, ücretsiz, key gerekmiyor - Wikipedia verisi
    yeniden kullanıma açık). Karşıt yatırım taraması için mevcut ABD top-30
    evrenini genişletmek amacıyla kullanılır. Başarısız olursa boş liste
    döner (çağıran taraf bu durumda sadece mevcut evrenle devam eder)."""
    try:
        resp = requests.get(SP500_WIKIPEDIA_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        symbols = df["Symbol"].astype(str).str.strip().tolist()
        # Wikipedia bazı sembollerde nokta kullanıyor (örn. BRK.B), yfinance tire ister (BRK-B)
        symbols = [s.replace(".", "-") for s in symbols]
        return symbols
    except Exception:
        return []


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
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info
    except Exception:
        return {}
    if not info:
        return {}
    fundamentals = {field: info.get(field) for field in FUNDAMENTAL_FIELDS}

    try:
        income_stmt = yf_ticker.income_stmt
        if income_stmt is not None and not income_stmt.empty:
            latest = income_stmt.iloc[:, 0]
            for field in INCOME_STMT_FIELDS:
                value = latest.get(field)
                fundamentals[field] = None if value is None or pd.isna(value) else float(value)
    except Exception:
        pass

    return fundamentals


def fetch_symbol_bundle(ticker: str, market: str) -> dict:
    """Bir hisse için kısa (gösterge) + uzun (örüntü arama) geçmiş ve temel verileri toplar.

    Tek bir 10y history çağrısı yapılır, 1y'lik dilim bunun son ~252 barından
    türetilir - ayrı bir history çağrısına gerek kalmaz (180+ sembollük evrende
    performans için önemli: sembol başına 3 yerine 2 ağ çağrısı)."""
    result = {"symbol": ticker, "market": market, "error": None}

    history_long = fetch_history(ticker, period="10y")
    if history_long is None or history_long.empty:
        result["error"] = "Fiyat verisi alınamadı"
        return result

    history_1y = history_long.tail(252)

    time.sleep(0.5)
    fundamentals = fetch_fundamentals(ticker)

    result["history_1y"] = history_1y
    result["history_long"] = history_long
    result["fundamentals"] = fundamentals
    return result
