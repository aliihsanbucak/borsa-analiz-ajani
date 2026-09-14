"""Klasik değer yatırımı literatüründen (Graham & Dodd, Graham, Lynch) esinlenen
kural tabanlı hisse değerlendirme yöntemleri. Sadece BIST/ABD hisseleri için
anlamlıdır - kriptoda uygulanmaz.

Kaynaklar:
- Benjamin Graham & David Dodd, "Security Analysis"
- Benjamin Graham, "The Intelligent Investor" (Bölüm 14 - defansif yatırımcı kriterleri)
- Peter Lynch, "One Up On Wall Street" (PEG oranı, büyüme kategorileri)
- Peter Lynch, "Beating the Street" (insider/içeriden sahiplik oranı, "iki dakikalık hikaye" yaklaşımı için gerekli şirket/sektör bilgisi)

Ayrıca basitleştirilmiş bir bear/base/bull adil değer aralığı da üretilir
(lynch_fair_value_range_note) - Lynch'in "adil F/K büyüme oranına eşittir"
kuralından türetilen, ±%30'luk mekanik bir bant. Bu KESİNLİKLE kurumsal
anlamda bir DCF/WACC modeli değildir - bunun nedeni açıkça not olarak
belirtilir (WACC/beta tabanlı gerçek bir DCF, şirket bazında güvenilir
kredi spreadi ve uzun vadeli büyüme varsayımları gerektirir, bunlar
ücretsiz/otomatik bir pipeline'da güvenilir şekilde elde edilemez).

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


def lynch_peg_ratio(info: dict) -> float | None:
    """Ham PEG oranını döner (skorlama gibi programatik kullanım için).
    Kazanç büyümesi negatif/yok veya F/K eksikse None döner."""
    pe = info.get("trailingPE")
    growth = info.get("earningsGrowth")
    if pe is None or growth is None or growth <= 0:
        return None
    return pe / (growth * 100)


def lynch_peg_note(info: dict) -> str | None:
    peg = lynch_peg_ratio(info)
    if peg is None:
        return None
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


def lynch_insider_ownership_note(info: dict) -> str | None:
    """Beating the Street'te Lynch, yöneticilerin/içeridekilerin kendi hissesini
    elinde tutmasını (ve mümkünse satın almasını) yönetimin şirketin geleceğine
    güvendiğinin bir işareti olarak yorumlar. yfinance'in ücretsiz verisi
    içeriden alım/satım işlemlerini değil, sadece anlık sahiplik yüzdesini
    verdiği için burada sadece bu vekil (proxy) kullanılıyor."""
    insiders = info.get("heldPercentInsiders")
    if insiders is None:
        return None
    pct = insiders * 100
    if pct > 5:
        return (f"İçeriden sahiplik oranı %{pct:.1f} - Lynch'in 'Beating the Street' kitabında "
                f"vurguladığı gibi, yöneticilerin kendi hissesini elinde tutması genelde yönetimin "
                f"şirketin geleceğine güvendiğinin bir işareti olarak yorumlanır")
    return f"İçeriden sahiplik oranı %{pct:.1f}"


def lynch_two_minute_story_context(info: dict) -> str | None:
    """Lynch'in 'Beating the Street'te anlattığı 'iki dakikalık hikaye' pratiği
    icin gereken temel baglami (sirket adi, sektor) dondurur - raporu yazacak
    olan, bu bilgiyi kategori/PEG/buyume notlarıyla birlestirerek kisa ve
    anlasilir bir yatirim hikayesi kurabilir."""
    name = info.get("shortName")
    sector = info.get("sector")
    if name and sector:
        return f"Şirket: {name} ({sector} sektörü)"
    if name:
        return f"Şirket: {name}"
    return None


def lynch_fair_value_range_note(info: dict) -> str | None:
    """Basitlestirilmis, seffaf bir bear/base/bull adil deger araligi.

    ONEMLI: Bu tam bir DCF/WACC modeli DEGILDIR - kurumsal analizde
    kullanilan iskonto edilmis nakit akisi (WACC, beta, terminal buyume
    varsayimlariyla) modeli icin sirket-bazinda guvenilir varsayimlar
    (kredi spreadi, uzun vadeli buyume projeksiyonu vb.) gerekir ve bu
    ucretsiz/otomatik pipeline'da elde edilemez. Bunun yerine Peter
    Lynch'in "adil F/K, buyume oranina esittir" (PEG=1) kuralindan
    turetilen, seffaf ve mekanik bir carpan araligi kullaniliyor:
    - Adil F/K (PEG=1 varsayimi) = yillik kazanc buyume orani (%), ama gercekci
      kalmasi icin 40 ile sinirlandirilir (bkz. asagidaki not) - aksi halde
      tek seferlik/duşuk-baz kaynakli asiri buyume oranlari (orn. %500)
      anlamsiz derecede yuksek "adil deger" ciktilari uretebiliyordu.
    - Ayi senaryosu: adil F/K'nin %30 altinda
    - Boga senaryosu: adil F/K'nin %30 uzerinde
    Bu bir tahmin araligidir, kesinlik iddia etmez."""
    eps = info.get("trailingEps")
    growth = info.get("earningsGrowth")
    if eps is None or eps <= 0 or growth is None or growth <= 0:
        return None

    fair_pe_raw = growth * 100
    fair_pe = min(fair_pe_raw, 40)
    bear_price = eps * fair_pe * 0.7
    base_price = eps * fair_pe
    bull_price = eps * fair_pe * 1.3

    cap_note = ""
    if fair_pe_raw > 40:
        cap_note = (
            f" (Not: raporlanan kazanç büyümesi %{fair_pe_raw:.0f} gibi olağanüstü yüksek - "
            f"muhtemelen düşük bir önceki dönem bazından kaynaklanıyor; bu heuristik gerçekçi "
            f"kalması için adil F/K'yi 40 ile sınırlandırdı, ham oran kullanılmadı)"
        )

    return (
        f"Basitleştirilmiş adil değer aralığı (Lynch'in 'adil F/K büyüme oranına eşittir' "
        f"kuralından türetilmiştir, tam bir DCF/WACC modeli değildir): "
        f"Ayı ~{bear_price:.2f} / Baz ~{base_price:.2f} / Boğa ~{bull_price:.2f}{cap_note}"
    )


def value_investing_notes(info: dict, include_fair_value: bool = True) -> list[str]:
    """include_fair_value=False: data_pipeline.py, gercek bir DCF (dcf.py)
    hesaplanabildiginde bu kaba Lynch sezgiselini eklemez - DCF notu onun
    yerini alir. DCF hesaplanamazsa (negatif FCF, eksik beta vb.) data_pipeline.py
    bu sezgisele geri doner (bkz. data_pipeline.py process_stock_symbol)."""
    notes: list[str] = []

    story_context = lynch_two_minute_story_context(info)
    if story_context:
        notes.append(story_context)

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

    insider_note = lynch_insider_ownership_note(info)
    if insider_note:
        notes.append(insider_note)

    if include_fair_value:
        fair_value_note = lynch_fair_value_range_note(info)
        if fair_value_note:
            notes.append(fair_value_note)

    return notes
