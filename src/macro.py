"""Günlük rapora makroekonomik bağlam eklemek için ücretsiz piyasa ve
küresel likidite göstergeleri çeker.

KAPSAM DIŞI (ücretsiz/güvenilir bir API olmadığı için otomatikleştirilemedi):
- KAP özel durum açıklamaları (yapılandırılmış ücretsiz bir API yok)

İki farklı ücretsiz kaynak kullanılıyor:
1. yfinance ticker'ları: piyasa fiyatlı göstergeler (tahvil getirisi, DXY,
   USD/TRY, VIX, altın, petrol)
2. FRED'in (St. Louis Fed) API KEY GEREKTİRMEYEN CSV indirme endpoint'i
   (fredgraph.csv): Fed bilançosu, TGA (Hazine Genel Hesabı), RRP (ters
   repo), Fed fonlama faizi, M2 para arzı - kullanıcının "küresel likidite"
   olarak talep ettiği göstergeler.
"""
import yfinance as yf
import requests
import csv
import io

TIMEOUT = 15

TICKERS = {
    "us_10y_yield": "^TNX",       # ABD 10 yıllık tahvil getirisi (%)
    "dxy": "DX-Y.NYB",             # Dolar endeksi
    "usdtry": "TRY=X",             # USD/TRY
    "vix": "^VIX",                  # Piyasa oynaklık/korku endeksi
    "gold": "GC=F",                 # Altın vadeli işlem fiyatı (USD/ons)
    "oil": "CL=F",                   # WTI ham petrol vadeli işlem fiyatı (USD/varil)
}

# FRED seri kodları - fredgraph.csv API key gerektirmiyor, herkese açık
FRED_SERIES = {
    "fed_funds_rate": "DFF",         # Fed fonlama faizi (%)
    "fed_balance_sheet": "WALCL",    # Fed toplam bilançosu (milyon USD)
    "tga": "WTREGEN",                 # Hazine Genel Hesabı / TGA (milyar USD)
    "reverse_repo": "RRPONTSYD",      # Gecelik ters repo (milyar USD)
    "m2": "M2SL",                      # M2 para arzı (milyar USD)
    # TCMB politika faizi (OECD "Immediate Rates: Central Bank Rates" serisi,
    # aylık). BIST hisselerinin TL cinsinden WACC/DCF hesabında risksiz oran
    # olarak kullanılıyor (bkz. dcf.py). Modülün başındaki "TCMB faizi için
    # ücretsiz API yok" notu bu seriyle geçersiz kaldı.
    "try_policy_rate": "IRSTCI01TRM156N",
}


def _fetch_fred_series(series_id: str) -> dict | None:
    try:
        resp = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        reader = csv.reader(io.StringIO(resp.text))
        next(reader)  # header
        rows = [(row[0], row[1]) for row in reader if len(row) == 2 and row[1].strip() not in ("", ".")]
        if len(rows) < 2:
            return None
        latest_date, latest_value = rows[-1]
        prev_date, prev_value = rows[-2]
        latest_value = float(latest_value)
        prev_value = float(prev_value)
        change_pct = ((latest_value / prev_value) - 1) * 100 if prev_value else None
        return {
            "value": latest_value,
            "as_of": latest_date,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
        }
    except Exception:
        return None


def fetch_macro_snapshot() -> dict:
    snapshot = {}
    for key, ticker in TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if hist is None or hist.empty:
                snapshot[key] = None
                continue
            last_close = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[-2] if len(hist) >= 2 else None
            change_pct = ((last_close / prev_close) - 1) * 100 if prev_close else None
            snapshot[key] = {"value": round(float(last_close), 2), "change_pct": round(float(change_pct), 2) if change_pct is not None else None}
        except Exception:
            snapshot[key] = None

    for key, series_id in FRED_SERIES.items():
        snapshot[key] = _fetch_fred_series(series_id)

    return snapshot


def interpret_macro(snapshot: dict) -> list[str]:
    notes: list[str] = []
    if not snapshot:
        return notes

    y10 = snapshot.get("us_10y_yield")
    if y10:
        notes.append(f"ABD 10 yıllık tahvil getirisi %{y10['value']:.2f} - risksiz getiri oranının göstergesi, yükselmesi genelde büyüme hisselerinin değerlemesi üzerinde baskı olarak yorumlanır")

    try_rate = snapshot.get("try_policy_rate")
    if try_rate:
        notes.append(
            f"TCMB politika faizi %{try_rate['value']:.2f} ({try_rate['as_of']} itibarıyla) - "
            "BIST hisselerinin TL cinsinden iskonto oranı (WACC) bu orana dayandırılıyor"
        )

    dxy = snapshot.get("dxy")
    if dxy:
        yön = "güçleniyor" if (dxy.get("change_pct") or 0) >= 0 else "zayıflıyor"
        notes.append(f"Dolar endeksi (DXY) {dxy['value']:.1f}, son günde {yön} - güçlü dolar genelde gelişen piyasalar ve emtialar için baskı unsuru olarak yorumlanır")

    usdtry = snapshot.get("usdtry")
    if usdtry:
        notes.append(f"USD/TRY {usdtry['value']:.2f}")

    vix = snapshot.get("vix")
    if vix:
        if vix["value"] > 25:
            notes.append(f"VIX (piyasa oynaklık endeksi) {vix['value']:.1f} - yüksek seviyede, piyasada belirgin bir tedirginlik/risk iştahı azalması olduğuna işaret edebilir")
        elif vix["value"] < 15:
            notes.append(f"VIX {vix['value']:.1f} - düşük seviyede, piyasada görece sakin/risk iştahlı bir ortam olduğuna işaret edebilir")
        else:
            notes.append(f"VIX {vix['value']:.1f} - normal aralıkta")

    gold = snapshot.get("gold")
    if gold:
        notes.append(f"Altın (ons) ${gold['value']:.0f}")

    oil = snapshot.get("oil")
    if oil:
        notes.append(f"WTI petrol (varil) ${oil['value']:.1f}")

    fed_funds = snapshot.get("fed_funds_rate")
    if fed_funds:
        notes.append(f"Fed fonlama faizi %{fed_funds['value']:.2f} ({fed_funds['as_of']} itibarıyla)")

    fed_bs = snapshot.get("fed_balance_sheet")
    if fed_bs:
        yön = "genişliyor" if (fed_bs.get("change_pct") or 0) >= 0 else "daralıyor"
        notes.append(
            f"Fed toplam bilançosu ${fed_bs['value']/1e6:.2f} trilyon ({fed_bs['as_of']} itibarıyla, son ölçümde {yön}) "
            f"- bilançonun büyümesi piyasaya likidite eklendiği, küçülmesi likidite çekildiği (QT) şeklinde yorumlanır"
        )

    tga = snapshot.get("tga")
    if tga:
        notes.append(
            f"Hazine Genel Hesabı (TGA) ${tga['value']/1000:.0f} milyar ({tga['as_of']} itibarıyla) "
            f"- TGA yükseldiğinde Hazine piyasadan nakit çekiyor (likiditeyi sıkılaştırıcı), düştüğünde piyasaya nakit geri veriyor demektir"
        )

    rrp = snapshot.get("reverse_repo")
    if rrp:
        notes.append(
            f"Gecelik ters repo (RRP) ${rrp['value']:.0f} milyar ({rrp['as_of']} itibarıyla) "
            f"- bu tutar bankacılık sisteminin dışında Fed'de 'parkedilmiş' likiditeyi gösterir, düşmesi genelde piyasaya likidite döndüğü şeklinde yorumlanır"
        )

    m2 = snapshot.get("m2")
    if m2:
        notes.append(f"M2 para arzı ${m2['value']/1000:.1f} trilyon ({m2['as_of']} itibarıyla)")

    return notes
