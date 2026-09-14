"""Anthony M. Gallea & William Patalon III'ün "Contrarian Investing: Buy and Sell
When Others Don't and Make Money Doing It" (Türkçe: "Karşıt Yatırım", Scala
Yayıncılık) kitabından çıkarılan, tamamen mekanik/kural tabanlı bir "gözden
düşmüş hisse" tarama sistemi.

Kitabın nihai sistemi (Bölüm 15'te özetleniyor):
1. Birincil filtre (zorunlu): fiyat 52 haftalık en yüksek seviyesinden en az
   %50 düşmüş, fiyat > 5 (birim para), piyasa değeri > 150 milyon $.
2. Teyit: asagidaki 4 degerleme oranindan EN AZ IKISI:
   F/K < 12, F/DD < 1.0, F/SNA (P/FCF) < 10, F/S < 1.0.

KAPSAM DIŞI: Kitapta ayrıca "içeriden $120.000+ alım" ve "dışarıdan bilgili
yatırımcı %5 hisse alımı" teyitleri var, ama bunlar ücretsiz yfinance verisiyle
otomatikleştirilemiyor (sadece anlık sahiplik yüzdesi var, işlem bazlı/tarihsel
veri yok) - kullanıcıyla konuşulup bilerek dışarıda bırakıldı.

Bu modül, hangi sembollerin "karşıt aday" olduğuna KARAR VERMEZ - sadece Python
tarafında mekanik olarak hesaplar. Rapor sentezleyen Claude bu adayları sadece
AÇIKLAR, kendi seçimini eklemez (mevcut top-30 puanlama sisteminin şeffaflık
ilkesiyle birebir tutarlı).
"""
import pandas as pd

PRIMARY_MIN_PRICE = 5.0
PRIMARY_MIN_MARKET_CAP = 150_000_000
PRIMARY_MAX_PCT_OF_HIGH = 0.50  # fiyat, 52 haftalik zirvenin en fazla %50'si olmali

PE_THRESHOLD = 12.0
PB_THRESHOLD = 1.0
PFCF_THRESHOLD = 10.0
PS_THRESHOLD = 1.0

BOOK_CITATION = (
    "Anthony M. Gallea & William Patalon III, \"Contrarian Investing\" "
    "(\"Karşıt Yatırım\", Scala Yayıncılık)"
)


def pct_off_52w_high(history: pd.DataFrame) -> float | None:
    """Son 252 is gunu (yaklasik 52 hafta) icindeki en yuksek kapanisa gore,
    guncel fiyatin yuzde kacinda oldugunu dondurur (1.0 = zirvede, 0.5 = zirvenin yarisi)."""
    if history is None or history.empty or "Close" not in history.columns:
        return None
    window = history["Close"].dropna().tail(252)
    if window.empty:
        return None
    high_52w = window.max()
    last_price = window.iloc[-1]
    if high_52w <= 0:
        return None
    return float(last_price / high_52w)


def passes_primary_filter(history: pd.DataFrame, market_cap: float | None) -> tuple[bool, float | None, float | None]:
    """Donus: (gecti_mi, pct_of_high, last_price)"""
    if history is None or history.empty or "Close" not in history.columns:
        return False, None, None
    last_price = float(history["Close"].dropna().iloc[-1])
    pct_of_high = pct_off_52w_high(history)
    if pct_of_high is None:
        return False, None, last_price
    if pct_of_high > PRIMARY_MAX_PCT_OF_HIGH:
        return False, pct_of_high, last_price
    if last_price <= PRIMARY_MIN_PRICE:
        return False, pct_of_high, last_price
    if market_cap is None or market_cap <= PRIMARY_MIN_MARKET_CAP:
        return False, pct_of_high, last_price
    return True, pct_of_high, last_price


def price_to_fcf(fundamentals: dict) -> float | None:
    market_cap = fundamentals.get("marketCap")
    fcf = fundamentals.get("freeCashflow")
    if not market_cap or not fcf or fcf <= 0:
        return None
    return market_cap / fcf


def price_to_sales(fundamentals: dict) -> float | None:
    return fundamentals.get("priceToSalesTrailing12Months")


def count_valuation_signals(fundamentals: dict) -> tuple[int, list[str]]:
    signals: list[str] = []

    pe = fundamentals.get("trailingPE")
    if pe is not None and pe > 0 and pe < PE_THRESHOLD:
        signals.append(f"F/K {pe:.1f} < {PE_THRESHOLD:.0f}")

    pb = fundamentals.get("priceToBook")
    if pb is not None and pb > 0 and pb < PB_THRESHOLD:
        signals.append(f"F/DD {pb:.2f} < {PB_THRESHOLD:.1f}")

    pfcf = price_to_fcf(fundamentals)
    if pfcf is not None and pfcf > 0 and pfcf < PFCF_THRESHOLD:
        signals.append(f"F/SNA {pfcf:.1f} < {PFCF_THRESHOLD:.0f}")

    ps = price_to_sales(fundamentals)
    if ps is not None and ps > 0 and ps < PS_THRESHOLD:
        signals.append(f"F/S {ps:.2f} < {PS_THRESHOLD:.1f}")

    return len(signals), signals


def contrarian_screen(symbol: str, market: str, fundamentals: dict, history: pd.DataFrame) -> dict | None:
    """Kripto icin uygulanmaz (F/K, F/DD, F/S gibi oranlar yok). Birincil filtre
    gecilmez ya da 2+ teyit saglanmazsa None doner (rapora girmez)."""
    if market == "crypto" or not fundamentals:
        return None

    market_cap = fundamentals.get("marketCap")
    passed, pct_of_high, last_price = passes_primary_filter(history, market_cap)
    if not passed:
        return None

    signal_count, signals_met = count_valuation_signals(fundamentals)
    if signal_count < 2:
        return None

    return {
        "symbol": symbol,
        "market": market,
        "last_price": round(last_price, 2) if last_price is not None else None,
        "pct_off_high": round((1 - pct_of_high) * 100, 1) if pct_of_high is not None else None,
        "signal_count": signal_count,
        "signals_met": signals_met,
        "high_signal_warning": signal_count >= 3,
    }
