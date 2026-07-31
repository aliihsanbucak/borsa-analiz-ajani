"""Hisse temel verilerinin (yfinance .info) basit eşik tabanlı Türkçe yorumu.

Eksik alanlar (None) sessizce atlanır - BIST sembollerinde bu sık görülüyor
(örn. earningsGrowth çoğu zaman None dönüyor).
"""


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

    div_yield = info.get("dividendYield")
    if div_yield:
        # yfinance dividendYield bazı sürümlerde oran (0.02), bazılarında yüzde (2.0) döner
        pct = div_yield * 100 if div_yield < 1 else div_yield
        notes.append(f"Temettü verimi %{pct:.1f}")

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

    return notes
