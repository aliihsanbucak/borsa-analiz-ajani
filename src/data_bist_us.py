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
    # PD/DD'yi para birimi uyusmazliginda yeniden kurabilmek icin gerekli:
    "bookValue",
    # Temettu verimini yfinance'in belirsiz "dividendYield" alanindan degil,
    # dogrudan dividendRate/fiyat oranindan hesaplamak icin (bkz. fundamentals.dividend_yield_pct):
    "dividendRate", "currentPrice",
    "earningsGrowth", "debtToEquity", "trailingEps", "marketCap",
    "currentRatio", "returnOnEquity", "heldPercentInsiders", "heldPercentInstitutions",
    "shortName", "sector",
    # Para birimi tutarliligi icin zorunlu (bkz. _normalize_currency): Yahoo bazi
    # sirketlerde fiyati TRY, bilanco kalemlerini USD/EUR cinsinden veriyor.
    "currency", "financialCurrency",
    # Finansal kalite/sağlık için eklendi (bkz. fundamentals.py yorumlama katmanı):
    "freeCashflow", "ebitda", "totalDebt", "totalCash", "beta",
    "revenueGrowth", "grossMargins", "operatingMargins", "returnOnAssets",
    # WACC/DCF için eklendi (bkz. dcf.py):
    "sharesOutstanding",
    # Karşıt yatırım taraması için eklendi (bkz. contrarian.py, F/S orani):
    "priceToSalesTrailing12Months",
)

# Sirketin finansal tablo para biriminde raporlanan MUTLAK buyuklukler. Fiyat
# para birimi farkliysa (currency != financialCurrency) bunlar kur ile
# cevrilmeden marketCap/currentPrice ile ayni formulde kullanilamaz.
# .info blogundaki mutlak kalemler (Yahoo bunlari bazen fiyat para birimine
# cevirip veriyor - bkz. _normalize_currency'deki olcek testi)
STATEMENT_ABSOLUTE_FIELDS = ("freeCashflow", "ebitda", "totalDebt", "totalCash")

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


_FX_CACHE: dict[str, float | None] = {}


def _fx_rate(from_ccy: str, to_ccy: str) -> float | None:
    """from_ccy -> to_ccy kuru (Yahoo'nun 'USDTRY=X' tipi sembolunden).
    Bulunamazsa None doner - cagiran taraf bu durumda sayi uretmez."""
    if from_ccy == to_ccy:
        return 1.0
    key = f"{from_ccy}{to_ccy}"
    if key in _FX_CACHE:
        return _FX_CACHE[key]
    rate = None
    try:
        hist = yf.Ticker(f"{key}=X").history(period="5d")
        if hist is not None and not hist.empty:
            closes = hist["Close"].dropna()
            if not closes.empty and float(closes.iloc[-1]) > 0:
                rate = float(closes.iloc[-1])
    except Exception:
        rate = None
    _FX_CACHE[key] = rate
    return rate


def _same_scale(value, reference) -> bool:
    """value, reference ile ayni buyukluk mertebesinde mi (0.4x - 2.5x arasi)?

    Yahoo bir alani bazen tablo para biriminde, bazen fiyat para biriminde
    veriyor (ayni gun THYAO.IS'te bookValue USD, ENKAI.IS'te trailingEps TRY).
    Hangisi oldugunu tahmin etmek yerine, alani tablolardan bagimsiz hesaplanan
    referansla olcek testine sokuyoruz. TTM/yillik farki oldugu icin esik genis
    tutuldu; iki aday da tutmazsa alan dusurulur (yanlis sayi uretmektense hic
    uretme - bkz. fundamentals.dividend_yield_pct'teki ayni ilke)."""
    if value is None or reference is None:
        return False
    try:
        value, reference = abs(float(value)), abs(float(reference))
    except (TypeError, ValueError):
        return False
    if reference == 0:
        return False
    return 0.4 <= value / reference <= 2.5


def _statement_value(frame, row: str, column: int = 0):
    try:
        value = frame.loc[row].iloc[column]
        return None if value is None or pd.isna(value) else float(value)
    except Exception:
        return None


def _drop_currency_sensitive(fundamentals: dict) -> None:
    for field in STATEMENT_ABSOLUTE_FIELDS + INCOME_STMT_FIELDS + (
            "bookValue", "trailingEps", "priceToBook", "trailingPE",
            "priceToSalesTrailing12Months"):
        fundamentals[field] = None


def _normalize_currency(yf_ticker, fundamentals: dict) -> None:
    """Fiyat ve finansal tablo para birimi farkliysa oranlari yeniden kurar.

    Canli tespit (22 Eylul 2026): THYAO.IS fiyati TRY, bilancosu USD -
    Yahoo'nun priceToBook'u 298 TRY / 15,88 USD = 18,76 cikiyor ve rapora
    "PD/DD 18,76" olarak giriyordu; gercegi ~0,38. Ayni hata ENKAI.IS'te
    (PD/DD 57,7) vardi. TAVHL.IS'te ise Yahoo ayni alanlari zaten TRY'ye
    cevirdigi icin degerler dogruydu - koru korune kurla carpmak orada yeni
    bir hata uretirdi. Bu yuzden hicbir sey varsayilmiyor: her alan, finansal
    tablolardan bagimsiz hesaplanan referansla olcek testine sokuluyor.

    Etkilenen her sey ayni desende: fiyat para birimindeki bir buyukluk
    (fiyat, piyasa degeri) tablo para birimindeki bir buyuklukle ayni formule
    giriyor (PD/DD, F/K, F/S, FCF getirisi, Net Borc/FAVOK, WACC, DCF)."""
    price_ccy = fundamentals.get("currency")
    fin_ccy = fundamentals.get("financialCurrency")
    if not price_ccy or not fin_ccy or price_ccy == fin_ccy:
        return

    fx = _fx_rate(fin_ccy, price_ccy)
    if not fx:
        _drop_currency_sensitive(fundamentals)
        fundamentals["currency_note"] = (
            f"Sirket fiyati {price_ccy}, finansal tablolari {fin_ccy} cinsinden ve "
            f"{fin_ccy}/{price_ccy} kuru alinamadi - PD/DD, F/K, F/S, FCF getirisi ve "
            "DCF gibi para birimi karistiran tum alanlar bu sembol icin dusuruldu."
        )
        return

    shares = fundamentals.get("sharesOutstanding")
    price = fundamentals.get("currentPrice")
    market_cap = fundamentals.get("marketCap")

    balance = getattr(yf_ticker, "balance_sheet", None)
    income = getattr(yf_ticker, "income_stmt", None)
    cashflow = getattr(yf_ticker, "cashflow", None)
    equity = _statement_value(balance, "Stockholders Equity")
    net_income = _statement_value(income, "Net Income")
    revenue = _statement_value(income, "Total Revenue")

    # Alan -> tablo para birimindeki bagimsiz referans. Referansi olmayan
    # alanlar (orn. bazi sirketlerde EBITDA satiri yok) blok oyuyla kararlanir.
    references = {
        "bookValue": (equity / shares) if (equity is not None and shares) else None,
        "trailingEps": (net_income / shares) if (net_income is not None and shares) else None,
        "totalDebt": _statement_value(balance, "Total Debt"),
        "totalCash": _statement_value(balance, "Cash Cash Equivalents And Short Term Investments"),
        "freeCashflow": _statement_value(cashflow, "Free Cash Flow"),
        "ebitda": _statement_value(income, "EBITDA"),
    }

    # Yahoo bazen blogun tamamini fiyat para birimine cevirip veriyor (TAVHL),
    # bazen ham tablo para biriminde birakiyor (THYAO, ENKAI). Once olcebildigimiz
    # alanlarda oylama yapiyoruz, sonra karari referanssiz alanlara tasiyoruz.
    votes_fin = votes_price = 0
    verdicts: dict[str, str] = {}
    for field, reference in references.items():
        value = fundamentals.get(field)
        if value is None or reference is None:
            continue
        in_fin = _same_scale(value, reference)
        in_price = _same_scale(value, reference * fx)
        if in_fin and not in_price:
            verdicts[field] = "fin"
            votes_fin += 1
        elif in_price and not in_fin:
            verdicts[field] = "price"
            votes_price += 1
        else:
            verdicts[field] = "belirsiz"

    if votes_fin and not votes_price:
        block = "fin"
    elif votes_price and not votes_fin:
        block = "price"
    elif votes_fin or votes_price:
        block = "fin" if votes_fin > votes_price else "price"
    else:
        block = None

    if block is None:
        _drop_currency_sensitive(fundamentals)
        fundamentals["currency_note"] = (
            f"Sirket fiyati {price_ccy}, finansal tablolari {fin_ccy} cinsinden; "
            "Yahoo'nun hangi alani hangi para biriminde verdigi tablolarla "
            "dogrulanamadi - para birimi karistiran tum alanlar dusuruldu."
        )
        return

    for field in STATEMENT_ABSOLUTE_FIELDS + ("bookValue", "trailingEps"):
        value = fundamentals.get(field)
        if value is None:
            continue
        verdict = verdicts.get(field, block)
        if verdict == "belirsiz":
            # Alan iki adaydan hicbirine oturmadi. Mutlak nakit/borc kalemlerinde
            # bunun olagan sebebi TTM ile yillik tablo arasindaki fark (Yahoo tek
            # bir .info blogunu tek para biriminde verdigi icin blok karari
            # guvenilir), ama hisse basi kalemlerde (orn. THYAO trailingEps: ne
            # 2,12 USD'ye ne 103 TL'ye oturan -6,78) yanlis olcek dogrudan F/K
            # gibi bir orana sizar - orada sayi uretmektense alani dusuruyoruz.
            if field in ("bookValue", "trailingEps"):
                fundamentals[field] = None
                continue
            verdict = block
        if verdict == "fin":
            fundamentals[field] = float(value) * fx

    # income_stmt'ten dogrudan cekilen kalemler her zaman tablo para birimindedir.
    for field in ("Interest Expense", "EBIT"):
        value = fundamentals.get(field)
        if value is not None:
            fundamentals[field] = float(value) * fx

    # Para birimi karistiran oranlari duzeltilmis alanlardan yeniden kur.
    book_value = fundamentals.get("bookValue")
    fundamentals["priceToBook"] = (price / book_value) if (price and book_value) else None

    eps = fundamentals.get("trailingEps")
    fundamentals["trailingPE"] = (price / eps) if (price and eps and eps > 0) else None

    if market_cap and revenue:
        fundamentals["priceToSalesTrailing12Months"] = market_cap / (revenue * fx)
    else:
        fundamentals["priceToSalesTrailing12Months"] = None

    donusturuldu = "tablo para biriminden kurla cevrildi" if block == "fin" else "Yahoo tarafindan zaten cevrilmisti, oldugu gibi birakildi"
    fundamentals["currency_note"] = (
        f"Fiyat {price_ccy}, finansal tablolar {fin_ccy} cinsinden; Yahoo'nun hazir "
        f"oranlari bu ikisini karistirabiliyor. Bilanco/nakit akisi kalemleri "
        f"{donusturuldu}; PD/DD, F/K ve F/S {fin_ccy}/{price_ccy} = {fx:,.2f} kuruyla "
        "tutarli hale getirildi."
    )


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

    try:
        _normalize_currency(yf_ticker, fundamentals)
    except Exception:
        # Normalizasyon yapilamadiysa sessizce ham (karisik para birimli) veriyle
        # devam etmek yerine riskli alanlari dusur.
        if fundamentals.get("currency") != fundamentals.get("financialCurrency"):
            _drop_currency_sensitive(fundamentals)

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
