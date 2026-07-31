"""Klasik değer yatırımı literatüründen (Graham & Dodd, Graham, Lynch) esinlenen
kural tabanlı hisse değerlendirme yöntemleri. Sadece BIST/ABD hisseleri için
anlamlıdır - kriptoda uygulanmaz.

Kaynaklar:
- Benjamin Graham & David Dodd, "Security Analysis"
- Benjamin Graham, "The Intelligent Investor" (Bölüm 14 - defansif yatırımcı kriterleri)
- Peter Lynch, "One Up On Wall Street" (PEG oranı, büyüme kategorileri)

Not: yfinance'in ücretsiz .info verisi Graham'ın orijinal kriterlerinin bir kısmını
(örn. "son 10 yılın her yılında pozitif kazanç") doğrudan sağlamıyor; bu yüzden
en yakın mevcut vekil (proxy) alanlar kullanılıyor ve bu açıkça belirtiliyor.
Eksik alanlar kriterden sessizce çıkarılır, skor sadece değerlendirilebilen
kriterler üzerinden hesaplanır (örn. "5/6").
"""


def graham_defensive_score(info: dict) -> dict:
    """Graham'ın 'defansif yatırımcı' kriterlerine kaç tanesinin karşılandığını
    değerlendirir. Dönüş: {"score": int, "of": int, "notes": [str, ...]}
    """
    if not info:
        return {"score": 0, "of": 0, "notes": []}

    notes: list[str] = []
    passed = 0
    evaluated = 0

    current_ratio = info.get("currentRatio")
    if current_ratio is not None:
        evaluated += 1
        if current_ratio >= 2:
            passed += 1
            notes.append(f"Cari oran {current_ratio:.1f} - Graham'ın güçlü finansal yapı eşiğini (≥2) karşılıyor")
        else:
            notes.append(f"Cari oran {current_ratio:.1f} - Graham'ın ≥2 eşiğinin altında")

    dte = info.get("debtToEquity")
    if dte is not None:
        evaluated += 1
        if dte < 100:
            passed += 1
            notes.append("Borç/özkaynak oranı makul seviyede")
        else:
            notes.append("Borç/özkaynak oranı Graham'ın tercih ettiği düşük borçluluk profiline uymuyor")

    eps = info.get("trailingEps")
    if eps is not None:
        evaluated += 1
        if eps > 0:
            passed += 1
            notes.append("Pozitif kazanç bildiriyor (Graham'ın istikrarlı kazanç kriterine kısmi vekil)")
        else:
            notes.append("Negatif kazanç - Graham'ın istikrarlı kazanç kriterini karşılamıyor")

    div_yield = info.get("dividendYield")
    if div_yield is not None:
        evaluated += 1
        if div_yield > 0:
            passed += 1
            notes.append("Temettü ödüyor (Graham'ın temettü kaydı kriterine kısmi vekil)")
        else:
            notes.append("Temettü ödemiyor")

    growth = info.get("earningsGrowth")
    if growth is not None:
        evaluated += 1
        if growth > 0:
            passed += 1
            notes.append("Kazançlarda büyüme var")
        else:
            notes.append("Kazançlarda büyüme yok/daralma var")

    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    if pe is not None:
        evaluated += 1
        if pe < 15:
            passed += 1
            notes.append(f"F/K {pe:.1f} - Graham'ın makul F/K eşiğinin (<15) altında")
        else:
            notes.append(f"F/K {pe:.1f} - Graham'ın makul F/K eşiğinin (<15) üzerinde")
    if pe is not None and pb is not None:
        evaluated += 1
        combined = pe * pb
        if combined <= 22.5:
            passed += 1
            notes.append(f"F/K×PD/DD = {combined:.1f} - Graham'ın 22.5 eşiğinin altında")
        else:
            notes.append(f"F/K×PD/DD = {combined:.1f} - Graham'ın 22.5 eşiğinin üzerinde")

    return {"score": passed, "of": evaluated, "notes": notes}


def lynch_peg_note(info: dict) -> str | None:
    pe = info.get("trailingPE")
    growth = info.get("earningsGrowth")
    if pe is None or growth is None or growth <= 0:
        return None
    growth_pct = growth * 100
    peg = pe / growth_pct
    if peg < 1:
        yorum = "cazip (Lynch'e göre PEG<1)"
    elif peg <= 2:
        yorum = "makul"
    else:
        yorum = "pahalı (Lynch'e göre PEG>2)"
    return f"PEG oranı {peg:.2f} - {yorum}"


def lynch_category_note(info: dict) -> str | None:
    growth = info.get("earningsGrowth")
    if growth is None:
        return None
    growth_pct = growth * 100
    if growth_pct > 20:
        return "Lynch kategorisi: hızlı büyüyen (fast grower) - gözlemsel bir etiket, kesin sınıflandırma değil"
    if growth_pct > 10:
        return "Lynch kategorisi: istikrarlı (stalwart) - gözlemsel bir etiket"
    if growth_pct >= 0:
        return "Lynch kategorisi: yavaş büyüyen (slow grower) - gözlemsel bir etiket"
    return "Lynch kategorisi: kazançları daralıyor, dönüş potansiyeli (turnaround) veya döngüsel olabilir - gözlemsel bir etiket"


def value_investing_notes(info: dict) -> list[str]:
    notes: list[str] = []
    graham = graham_defensive_score(info)
    if graham["of"] > 0:
        notes.append(f"Graham defansif yatırımcı skoru: {graham['score']}/{graham['of']}")
        notes.extend(graham["notes"])

    peg_note = lynch_peg_note(info)
    if peg_note:
        notes.append(peg_note)

    category_note = lynch_category_note(info)
    if category_note:
        notes.append(category_note)

    return notes
