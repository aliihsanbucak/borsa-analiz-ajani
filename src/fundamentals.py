"""Hisse temel verilerinin (yfinance .info) basit eşik tabanlı Türkçe yorumu.

Eksik alanlar (None) sessizce atlanır - BIST sembollerinde bu sık görülüyor
(örn. earningsGrowth çoğu zaman None dönüyor).
"""


def dividend_yield_pct(info: dict) -> float | None:
    """Temettu verimini YUZDE olarak dondurur.

    yfinance'in "dividendYield" alani surumden surume anlam degistiriyor: bazen
    oran (0.0015), bazen yuzde (0.15) donuyor. Eski "1'den kucukse oranidir,
    100 ile carp" sezgiseli bu yuzden hatali sonuc uretiyordu - ornegin EMPAE.IS
    icin 68,20 TL fiyata karsi 0,10 TL temettu (gercek verim %0,15) rapora
    "%15,0" olarak giriyordu (canli tespit: 7 Eylul 2026).

    Cozum: belirsiz alani tahmin etmek yerine, mumkun oldugunda dogrudan
    hisse basina temettu / fiyat oranindan hesapla. Ikisi de yoksa None don -
    yanlis bir sayi uretmektense hic uretme.
    """
    if not info:
        return None
    rate = info.get("dividendRate")
    price = info.get("currentPrice")
    if rate is not None and price:
        try:
            return float(rate) / float(price) * 100
        except (TypeError, ZeroDivisionError):
            return None
    return None


def interpret_fundamentals(info: dict) -> list[str]:
    notes: list[str] = []
    if not info:
        return notes

    pe = info.get("trailingPE")
    if pe is not None:
        if pe < 10:
            notes.append(f"F/K oranı düşük ({pe:.1f})")
        elif pe <= 25:
            notes.append(f"F/K normal aralıkta ({pe:.1f})")
        else:
            notes.append(f"F/K yüksek ({pe:.1f})")

    pb = info.get("priceToBook")
    if pb is not None:
        if pb < 1:
            notes.append(f"PD/DD 1'in altında ({pb:.2f})")
        else:
            notes.append(f"PD/DD {pb:.2f}")

    pct = dividend_yield_pct(info)
    if pct is not None and pct > 0:
        notes.append(f"Temettü verimi %{pct:.2f}")

    margins = info.get("profitMargins")
    if margins is not None:
        if margins < 0:
            notes.append("Şirket zarar bildiriyor")
        elif margins > 0.15:
            notes.append(f"Kâr marjı güçlü (%{margins * 100:.1f})")
        else:
            notes.append(f"Kâr marjı %{margins * 100:.1f}")

    growth = info.get("earningsGrowth")
    if growth is not None:
        yön = "büyüme" if growth >= 0 else "daralma"
        notes.append(f"Kazançlarda %{abs(growth) * 100:.1f} {yön}")

    dte = info.get("debtToEquity")
    if dte is not None:
        if dte > 150:
            notes.append(f"Borç/özkaynak oranı yüksek ({dte:.0f})")
        else:
            notes.append(f"Borç/özkaynak oranı {dte:.0f}")

    gross = info.get("grossMargins")
    if gross is not None:
        notes.append(f"Brüt kâr marjı %{gross * 100:.1f}")

    operating = info.get("operatingMargins")
    if operating is not None:
        notes.append(f"Faaliyet kâr marjı %{operating * 100:.1f}")

    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None:
        yön = "büyüme" if rev_growth >= 0 else "daralma"
        notes.append(f"Ciroda %{abs(rev_growth) * 100:.1f} {yön}")

    # FCF getirisi: piyasa değerine göre şirketin ne kadar serbest nakit
    # ürettiğini gösterir - Graham/Lynch'in F/K'sına tamamlayıcı bir kalite
    # ölçütü (kâr muhasebesel olabilir, nakit akışı daha zor manipüle edilir)
    fcf = info.get("freeCashflow")
    market_cap = info.get("marketCap")
    if fcf is not None and market_cap:
        fcf_yield = fcf / market_cap
        if fcf_yield < 0:
            notes.append("Serbest nakit akışı negatif - şirket faaliyetlerinden nakit üretemiyor, bu dikkat edilmesi gereken bir durum")
        else:
            notes.append(f"FCF (serbest nakit akışı) getirisi %{fcf_yield * 100:.1f}")

    # Net Borç/FAVÖK: şirketin mevcut kazancıyla borcunu kaç yılda
    # kapatabileceğinin kaba bir göstergesi - 3'ün altı genelde makul,
    # 4-5 üzeri kaldıraç riskinin arttığı şeklinde yorumlanır
    total_debt = info.get("totalDebt")
    total_cash = info.get("totalCash")
    ebitda = info.get("ebitda")
    if total_debt is not None and total_cash is not None and ebitda:
        net_debt = total_debt - total_cash
        net_debt_ebitda = net_debt / ebitda
        if net_debt_ebitda > 4:
            notes.append(f"Net Borç/FAVÖK {net_debt_ebitda:.1f} - yüksek sayılan bir kaldıraç seviyesi, borç yükü dikkat gerektirebilir")
        elif net_debt_ebitda < 0:
            notes.append(f"Net Borç/FAVÖK negatif ({net_debt_ebitda:.1f}) - şirketin nakdi borcundan fazla, finansal olarak rahat bir pozisyon")
        else:
            notes.append(f"Net Borç/FAVÖK {net_debt_ebitda:.1f}")

    beta = info.get("beta")
    if beta is not None:
        if beta > 1.3:
            notes.append(f"Beta {beta:.2f} - piyasa geneline göre daha oynak (yüksek beta, hem yükselişte hem düşüşte piyasadan daha sert hareket etme eğilimi anlamına gelir)")
        elif beta < 0.7:
            notes.append(f"Beta {beta:.2f} - piyasa geneline göre daha az oynak")
        else:
            notes.append(f"Beta {beta:.2f} - piyasayla benzer oynaklıkta")

    return notes
