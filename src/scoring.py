"""Geniş bir sembol evrenini (BIST100 + ABD top 30 + kripto top 50) günlük
raporda tek tek göstermek yerine, ŞEFFAF VE MEKANİK bir puanlama ile en
'dikkat çekici' 30 sembolü öne çıkarmak için kullanılır.

ÖNEMLİ TASARIM İLKESİ: Bu skor bir yatırım tavsiyesi/öneri motoru DEĞİLDİR.
Seçim, Claude'un öznel değerlendirmesiyle değil, burada açıkça tanımlanmış
ve rapora da yazılan sabit bir formülle yapılır - amaç sonucu "en iyi
seçenekler" gibi sunmak değil, "bugünün verisinde şu objektif kriterlere
göre en yüksek puanlananlar" şeklinde şeffaf bir tarama sunmaktır.

Hisseler (BIST/ABD) için orta-uzun vadeli literatüre ağırlık verilir
(Graham defansif skoru + Lynch PEG cazibesi + kazanç büyümesi), kısa vadeli
teknik osilatörler (RSI vb.) skora dahil edilmez - sadece rapor metninde
ayrıca not olarak belirtilir. Kripto için temel veri (F/K, temettü vb.)
uygulanamadığından, tarihsel örüntü performansı ve piyasa değeri sıralaması
kullanılır.
"""
import pandas as pd

import value_investing

SCORING_EXPLANATION = (
    "Sıralama, şu objektif bileşenlerin ağırlıklı ortalamasıyla hesaplanan bir "
    "puana göre yapılır - bu bir öneri değil, mekanik bir tarama sonucudur: "
    "Hisseler için Graham defansif skoru (%35) + Lynch PEG cazibesi (%25) + "
    "kazanç büyümesi (%20) + geçmiş örüntü sonrası ortalama getiri (%20); "
    "kripto için geçmiş örüntü sonrası ortalama getiri (%60) + piyasa değeri "
    "sıralaması (%40). Bir sembol için yeterli veri yoksa (en az 2 bileşen ve "
    "toplam %50 ağırlık; Graham skoru için 5 kriterden en az 3'ü ölçülebilir "
    "olmalı) puan HİÇ verilmez ve sembol o günün sıralamasına girmez - çok yeni "
    "halka arzlarda az veriden şişmiş yüksek puan çıkmasını önlemek için."
)


# Veri yetersizligine karsi koruma (canli tespit: 7 Eylul 2026, INTET.IS).
# Formul, eksik bilesenleri atip kalanlarin agirligini yeniden normalize
# ediyor. Bu, veri ne kadar AZSA skorun o kadar SISMESINE yol aciyordu:
# 1 Eylul 2026'da halka arz olan INTET.IS'in 4 gunluk gecmisiyle Graham'in
# 5 kriterinden yalnizca 1'i (borc/ozkaynak) hesaplanabildi, o da gecti,
# skor 1/1 = 1.00 cikti ve sembol top-30'un basina yerlesecekti. Bu bir
# bulgu degil, bir OLCUM HATASI. Asagidaki esikler, skorun anlamli sayida
# bagimsiz bilesene dayanmasini zorunlu kilar.
MIN_COMPONENT_COUNT = 2      # en az kac bagimsiz bilesen hesaplanabilmeli
MIN_TOTAL_WEIGHT = 0.50      # bu bilesenlerin toplam agirligi (1.00 uzerinden)
MIN_GRAHAM_CRITERIA = 3      # Graham skoru 5 kriterden en az kacini olcebilmeli


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _pattern_return_component(pattern_result: dict | None) -> float | None:
    if not pattern_result or pattern_result.get("insufficient_data"):
        return None
    matches = pattern_result.get("matches", [])
    if not matches:
        return None
    avg_return = sum(m["forward_return_pct"] for m in matches) / len(matches)
    # -10% -> 0.0, +10% -> 1.0 arasında ölçeklenir
    return _clamp((avg_return + 10) / 20)


def stock_score(fundamentals: dict, pattern_result: dict | None) -> float | None:
    if not fundamentals:
        return None

    components: list[tuple[float, float]] = []  # (deger, agirlik)

    graham = value_investing.graham_defensive_score(fundamentals)
    # graham["of"] < MIN_GRAHAM_CRITERIA ise skor 5 kriterin cok azina dayaniyor
    # demektir (tipik olarak yeni halka arzlar) - temsil gucu yok, dahil edilmez.
    if graham["of"] >= MIN_GRAHAM_CRITERIA:
        components.append((graham["score"] / graham["of"], 0.35))

    peg = value_investing.lynch_peg_ratio(fundamentals)
    if peg is not None and peg > 0:
        # PEG <=0.5 -> 1.0 (cok cazip), PEG >=2.0 -> 0.0 (pahali)
        peg_attractiveness = _clamp((2.0 - peg) / 1.5)
        components.append((peg_attractiveness, 0.25))

    growth = fundamentals.get("earningsGrowth")
    if growth is not None:
        # %0 buyume -> 0.0, %50+ buyume -> 1.0
        components.append((_clamp(growth / 0.5), 0.20))

    pattern_component = _pattern_return_component(pattern_result)
    if pattern_component is not None:
        components.append((pattern_component, 0.20))

    total_weight = sum(w for _, w in components)
    if len(components) < MIN_COMPONENT_COUNT or total_weight < MIN_TOTAL_WEIGHT:
        # Yeterli veri yok - yanlis yuksek bir skor uretmektense hic uretme.
        # Sembol atlanmaz, sadece o gunun top-N siralamasina girmez.
        return None

    score = sum(v * w for v, w in components) / total_weight
    return round(score, 4)


def is_stablecoin_like(close: pd.Series, daily_return_std_threshold: float = 0.01) -> bool:
    """Fiyatı dolar/altın gibi bir varlığa sabitlenmiş kripto tokenler (USDC,
    USDT, DAI, tokenize edilmiş fonlar vb.) piyasa değeri sıralamasında çok
    yüksek çıkabilir ama tanım gereği "büyüme potansiyeli" değerlendirmesi
    anlamsızdır - günlük getirilerin standart sapması neredeyse sıfırdır.
    Bu fonksiyon böyle bir varlığı tespit edip skorlamadan hariç tutmak için
    kullanılır (isim bazlı kırılgan bir liste yerine, ölçülebilir bir
    volatilite eşiği kullanılır)."""
    returns = close.pct_change().dropna()
    if len(returns) < 20:
        return False
    return bool(returns.std() < daily_return_std_threshold)


def crypto_score(pattern_result: dict | None, market_cap_rank: int | None) -> float | None:
    components: list[tuple[float, float]] = []

    pattern_component = _pattern_return_component(pattern_result)
    if pattern_component is not None:
        components.append((pattern_component, 0.6))

    if market_cap_rank is not None and market_cap_rank > 0:
        # rank 1 -> 1.0, rank 50 -> ~0.02, lineer azalan
        rank_component = _clamp((51 - market_cap_rank) / 50)
        components.append((rank_component, 0.4))

    if not components:
        return None

    total_weight = sum(w for _, w in components)
    score = sum(v * w for v, w in components) / total_weight
    return round(score, 4)
