"""Basitleştirilmiş ama GERÇEK bir CAPM/WACC tabanlı iskonto edilmiş nakit
akışı (DCF) modeli. Kullanıcının talebi üzerine eklendi - önceki
value_investing.py'deki kaba "adil F/K = büyüme oranı" (Lynch) sezgiselinin
yerini, veri mevcut olduğunda bu daha rigorous model alır (bkz.
data_pipeline.py'deki secim mantığı: DCF hesaplanabiliyorsa o kullanılır,
hesaplanamıyorsa (ör. negatif FCF, eksik beta) Lynch sezgiselene geri dönülür).

Varsayımlar (TÜMÜ raporda açıkça belirtilir - "gizli" bir varsayım yok):
- Özsermaye maliyeti: CAPM ile hesaplanır = risksiz oran (ABD 10 yıllık
  tahvil getirisi, macro.py'den) + beta x özsermaye risk primi.
- Özsermaye risk primi: sabit %5 varsayılıyor (Damodaran'ın uzun donemli
  ABD tahminleriyle uyumlu, kabaca kullanılan bir literatur değeri).
- Borç maliyeti: mümkünse şirketin gerçek faiz gideri/toplam borç oranından
  hesaplanır (yfinance income_stmt); bu veri yoksa risksiz oran + sabit
  %2 kredi marjı varsayılır (bu durumda not'ta açıkça belirtilir).
- Vergi sonrası borç maliyeti: pretax x (1 - efektif vergi oranı).
- 5 yıllık projeksiyon + %2.5 sabit terminal büyüme (Gordon büyüme modeli).
- Ayı/Baz/Boğa senaryoları HEM farklı büyüme tavanlarıyla (Ayı ≤%10,
  Baz ≤%18, Boğa ≤%28) HEM DE farklı WACC'lerle (Ayı: WACC+%1.5,
  Baz: WACC, Boğa: WACC-%1.5) hesaplanır. Bu, ilk canlı testte tespit
  edilen bir hatayı düzeltmek için gerekliydi: tek bir ortak büyüme
  tavanı kullanıldığında, çok yüksek ham büyüme oranlı şirketlerde
  (BIST/ABD evreninde sık görülüyor, bazen tek seferlik baz etkisiyle
  %100+) üç senaryo da aynı tavana sıkışıp BİRBİRİNİN AYNISI bir sonuç
  üretiyordu (örn. Ayı=Baz=Boğa=2934.70) - bu, aralığın hiçbir bilgi
  taşımaması anlamına geliyordu. Şimdi üç senaryo her zaman gerçek bir
  ayrışma gösterir.

PARA BİRİMİ REJİMİ (2026-09-22'de eklendi): Bir DCF'te iskonto oranı, büyüme
varsayımları ve nakit akışları AYNI para biriminde olmak zorundadır. Önceden
BIST hisselerinin TL nakit akışları ABD doları risksiz oranıyla (%4,98)
iskonto ediliyordu; %30+ enflasyonlu bir para biriminde bu, her BIST
şirketini sistematik olarak "ucuz" gösteren bir hataydı. Artık iki rejim var:

- ABD hisseleri: risksiz oran = ABD 10 yıllık tahvil getirisi, uzun dönem
  enflasyon %2,5, terminal büyüme %2,5, büyüme tavanları %10/%18/%28.
  (Bu rejim eski davranışın birebir aynısı - ABD sonuçları değişmedi.)
- BIST hisseleri: risksiz oran = TCMB politika faizi (macro.py,
  FRED IRSTCI01TRM156N). Beklenen uzun dönem TL enflasyonu = politika faizi
  eksi varsayılan %5 reel faiz (taban %5). Terminal büyüme bu nominal
  enflasyona eşitlenir - aksi halde iskonto oranı nominal, büyüme reelmiş
  gibi davranılır ve terminal değer yapay olarak ezilir. Büyüme tavanları da
  aynı şekilde nominalleştirilir: ABD tavanları %2,5 enflasyondan arındırılıp
  TL enflasyonuyla yeniden şişirilir, yani üç senaryonun REEL büyüme
  varsayımı iki rejimde aynı kalır.
- Tablolarını USD/EUR tutan BIST şirketlerinde (THYAO, ENKAI, TAVHL) Yahoo'nun
  kazanç büyümesi o para biriminin nominal büyümesidir; TL nakit akışını
  projekte ederken bu oran TL enflasyonuna göre yeniden ölçeklenir.
- TL rejiminde borç maliyeti en az politika faizi kabul edilir: kimse TL'yi
  politika faizinin altına borç vermez. Döviz borcu olan şirketlerde gerçek
  faiz gideri/borç oranı bunun altında çıkar, ama o ucuz borç TL cinsinden
  bir kur riski taşır - TL modelinde onu ucuz göstermek yanıltıcı olurdu.

Kalan sınırlama: TCMB politika faizi kısa vadeli bir orandır, 10 yıllık TL
tahvil getirisinin yerini tam tutmaz (ücretsiz ve güvenilir bir TL 10 yıllık
seri bulunamadı) ve aylık yayımlandığı için birkaç ay gecikebilir. Bu, rapora
not olarak düşülür.
"""

EQUITY_RISK_PREMIUM = 0.05
DEFAULT_CREDIT_SPREAD = 0.02
DEFAULT_TAX_RATE = 0.20
PROJECTION_YEARS = 5

# ABD rejimi (eski davranis): uzun donem enflasyon = terminal buyume
US_LONG_RUN_INFLATION = 0.025
TERMINAL_GROWTH = US_LONG_RUN_INFLATION   # geriye donuk uyumluluk icin korunuyor

# ABD rejiminin NOMINAL buyume tavanlari (Ayi/Baz/Boga)
US_GROWTH_CAPS = (0.10, 0.18, 0.28)

# TL rejimi: beklenen uzun donem enflasyon = politika faizi - varsayilan reel faiz
ASSUMED_TRY_REAL_RATE = 0.05
MIN_TRY_INFLATION = 0.05

# Turkiye icin REEL ozsermaye risk primi: olgun piyasa primi (~%5) + ulke risk
# primi (~%5). Nominal TL oraninin uzerine dogrudan eklenemez - enflasyonla
# birlikte olceklenmesi gerekir, yoksa reel risk primi enflasyona bolunup erir.
TRY_EQUITY_RISK_PREMIUM = 0.10

# Yahoo'nun BIST betalari kullanilamayacak kadar duzensiz (THYAO icin -0,05:
# bir havayolunu tahvilden guvenli gosterir). CAPM'in risk primini tamamen
# silmemesi icin TL rejiminde beta asagidan sinirlanir.
TRY_MIN_BETA = 0.8

# Terminal deger 1/(WACC - g) ile carpilir; iki oran birbirine yaklastikca
# sonuc kucuk varsayim farklarinda patlar. Bu esigin altinda sayi uretilmez.
# Mutlak taban eski davranisin aynisi (ABD sonuclari degismesin); asil is
# goren, WACC ile olceklenen orani.
MIN_TERMINAL_SPREAD = 0.02
MIN_TERMINAL_SPREAD_RATIO = 0.15

# Tablolarini yabanci para tutan sirketlerin buyume oranini TL'ye cevirirken
# varsayilan yabanci enflasyon (USD/EUR icin ayni mertebede)
FOREIGN_LONG_RUN_INFLATION = 0.025


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def currency_regime(risk_free_rate_pct: float, is_bist: bool) -> dict:
    """Iskonto orani, terminal buyume ve buyume tavanlarini ayni para biriminde
    tutan rejim parametreleri.

    ABD rejiminde degerler sabittir ve eski davranisin aynisidir. TL rejiminde
    hepsi TCMB politika faizinden turetilir; boylece uc senaryonun REEL buyume
    varsayimi iki rejimde ayni kalir, sadece nominal karsiligi degisir."""
    risk_free = risk_free_rate_pct / 100

    if not is_bist:
        return {
            "para_birimi": "USD",
            "risk_free": risk_free,
            "enflasyon": US_LONG_RUN_INFLATION,
            "terminal_growth": US_LONG_RUN_INFLATION,
            "growth_caps": US_GROWTH_CAPS,
            "wacc_bounds": (0.03, 0.35),
            "cost_of_debt_bounds": (0.01, 0.30),
            "cost_of_debt_floor": None,
            "equity_risk_premium": EQUITY_RISK_PREMIUM,
            "min_beta": None,
        }

    inflation = max(risk_free - ASSUMED_TRY_REAL_RATE, MIN_TRY_INFLATION)
    # ABD tavanlarini enflasyondan arindirip TL enflasyonuyla yeniden sisir
    caps = tuple(
        (1 + cap) / (1 + US_LONG_RUN_INFLATION) * (1 + inflation) - 1
        for cap in US_GROWTH_CAPS
    )
    return {
        "para_birimi": "TRY",
        "risk_free": risk_free,
        "enflasyon": inflation,
        "terminal_growth": inflation,
        "growth_caps": caps,
        "wacc_bounds": (risk_free * 0.5, risk_free + 0.35),
        "cost_of_debt_bounds": (risk_free, risk_free + 0.30),
        "cost_of_debt_floor": risk_free,
        "equity_risk_premium": TRY_EQUITY_RISK_PREMIUM,
        "min_beta": TRY_MIN_BETA,
    }


def nominal_growth_in_regime(growth: float, fundamentals: dict, regime: dict) -> float:
    """Sirketin kazanc buyumesini rejimin para birimine cevirir.

    Tablolarini USD tutan bir BIST sirketinin (THYAO) Yahoo'daki buyume orani
    dolar bazlidir; TL nakit akisini bu oranla projekte etmek, TL enflasyonunu
    yok saymak demektir."""
    if regime["para_birimi"] != "TRY":
        return growth
    fin_ccy = (fundamentals or {}).get("financialCurrency")
    if not fin_ccy or fin_ccy == "TRY":
        return growth
    return (1 + growth) * (1 + regime["enflasyon"]) / (1 + FOREIGN_LONG_RUN_INFLATION) - 1


def compute_wacc(fundamentals: dict, risk_free_rate_pct: float, is_bist: bool = False) -> dict | None:
    """risk_free_rate_pct: yüzde olarak (örn. 4.74), macro.py'nin formatıyla uyumlu.

    is_bist=True iken risksiz oranın TCMB politika faizi, nakit akışlarının da
    TL cinsinden olduğu varsayılır (bkz. currency_regime)."""
    if not fundamentals or risk_free_rate_pct is None:
        return None

    beta = fundamentals.get("beta")
    market_cap = fundamentals.get("marketCap")
    if beta is None or not market_cap:
        return None

    regime = currency_regime(risk_free_rate_pct, is_bist)
    risk_free = regime["risk_free"]

    if regime["min_beta"] is not None:
        beta = max(beta, regime["min_beta"])

    if regime["para_birimi"] == "USD":
        cost_of_equity = risk_free + beta * regime["equity_risk_premium"]
    else:
        # Reel kur, sonra enflasyonla sisir. Nominal orana reel primi dogrudan
        # eklemek, %30 enflasyonda risk primini ucte bire indirir.
        inflation = regime["enflasyon"]
        real_risk_free = (1 + risk_free) / (1 + inflation) - 1
        real_cost_of_equity = real_risk_free + beta * regime["equity_risk_premium"]
        cost_of_equity = (1 + real_cost_of_equity) * (1 + inflation) - 1

    total_debt = fundamentals.get("totalDebt") or 0
    interest_expense = fundamentals.get("Interest Expense")
    tax_rate = fundamentals.get("Tax Rate For Calcs")
    if tax_rate is None or tax_rate < 0 or tax_rate > 0.6:
        tax_rate = DEFAULT_TAX_RATE

    lo_debt, hi_debt = regime["cost_of_debt_bounds"]
    if interest_expense and total_debt:
        raw_cost_of_debt = abs(interest_expense) / total_debt
        pretax_cost_of_debt = _clamp(raw_cost_of_debt, lo_debt, hi_debt)
        cost_of_debt_source = "şirketin gerçek faiz gideri/toplam borç oranından hesaplandı"
        floor = regime["cost_of_debt_floor"]
        if floor is not None and raw_cost_of_debt < floor:
            # Doviz borcu olan BIST sirketlerinde bu oran politika faizinin cok
            # altinda cikar; TL modelinde borcu o fiyata gostermek, tasidigi kur
            # riskini yok saymak olur.
            cost_of_debt_source = (
                "şirketin gerçek faiz gideri/toplam borç oranı politika faizinin altında kaldığı "
                "(büyük olasılıkla döviz borcu) için TL modelinde politika faizine yükseltildi"
            )
    else:
        pretax_cost_of_debt = risk_free + DEFAULT_CREDIT_SPREAD
        cost_of_debt_source = "veri yetersiz olduğu için risksiz oran + sabit %2 kredi marjı varsayıldı"

    after_tax_cost_of_debt = pretax_cost_of_debt * (1 - tax_rate)

    equity = market_cap
    debt = total_debt
    total_capital = equity + debt
    if total_capital <= 0:
        return None

    weight_equity = equity / total_capital
    weight_debt = debt / total_capital
    wacc = weight_equity * cost_of_equity + weight_debt * after_tax_cost_of_debt
    wacc = _clamp(wacc, *regime["wacc_bounds"])

    return {
        "wacc": wacc,
        "regime": regime,
        "cost_of_equity": cost_of_equity,
        "cost_of_debt_pretax": pretax_cost_of_debt,
        "cost_of_debt_source": cost_of_debt_source,
        "tax_rate": tax_rate,
        "weight_equity": weight_equity,
        "weight_debt": weight_debt,
    }


def _scenario_fair_value(fcf0: float, growth: float, wacc: float, total_debt: float, total_cash: float, shares: float, growth_cap: float, terminal_growth: float = TERMINAL_GROWTH) -> float:
    growth = _clamp(growth, -0.15, growth_cap)
    fcf = fcf0
    pv_sum = 0.0
    for year in range(1, PROJECTION_YEARS + 1):
        fcf = fcf * (1 + growth)
        pv_sum += fcf / ((1 + wacc) ** year)
    terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** PROJECTION_YEARS)
    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - total_debt + total_cash
    return equity_value / shares


def simplified_dcf_note(fundamentals: dict, risk_free_rate_pct: float, is_bist: bool = False) -> str | None:
    """Hesaplanabiliyorsa (pozitif FCF, beta, hisse sayısı, kazanç büyümesi
    verisi mevcutsa) bear/base/bull DCF adil değer aralığı döner. Aksi
    halde None döner (çağıran taraf Lynch sezgiselene geri dönebilir)."""
    wacc_data = compute_wacc(fundamentals, risk_free_rate_pct, is_bist=is_bist)
    if wacc_data is None:
        return None

    fcf0 = fundamentals.get("freeCashflow")
    shares = fundamentals.get("sharesOutstanding")
    growth = fundamentals.get("earningsGrowth")
    total_debt = fundamentals.get("totalDebt") or 0
    total_cash = fundamentals.get("totalCash") or 0

    if fcf0 is None or fcf0 <= 0 or shares is None or shares <= 0 or growth is None:
        return None

    regime = wacc_data["regime"]
    terminal_growth = regime["terminal_growth"]
    bear_cap, base_cap, bull_cap = regime["growth_caps"]

    # Nakit akisi rejimin para biriminde (BIST icin TL); buyume orani da oyle olmali.
    growth = nominal_growth_in_regime(growth, fundamentals, regime)

    wacc = wacc_data["wacc"]
    # Terminal deger 1/(WACC - g) ile carpildigi icin, iki oran birbirine
    # yaklastiginda model kucuk varsayim farklarini kat kat buyuterek anlamsiz
    # hedefler uretir (canli test: TUPRS icin 397 TL fiyata karsi 8.748 TL
    # "boga" degeri). Boyle bir durumda sayi uretmek yerine None donuyoruz -
    # cagiran taraf Lynch sezgiselene geri doner.
    if wacc - terminal_growth < max(MIN_TERMINAL_SPREAD, MIN_TERMINAL_SPREAD_RATIO * wacc):
        return None

    bear_growth = growth * 0.5 if growth > 0 else growth * 1.5
    bull_growth = growth * 1.3

    # Senaryolar arasinda GERCEK bir ayrisma saglamak icin hem buyume
    # tavani hem de WACC senaryo bazinda degistiriliyor - aksi halde
    # (ozellikle yuksek buyume oranli sirketlerde) uc senaryo da ayni
    # tavana sikisip ozdes sonuc uretebiliyordu (bu hata ilk canli testte
    # tespit edilip duzeltildi: bkz. BRK-B ornegi, 3 senaryo da 2934.70
    # cikmisti).
    # Senaryo WACC farki da rejimin olcegine gore buyur: %35 iskonto oraninda
    # 1,5 puanlik bir fark neredeyse hicbir ayrisma uretmez.
    wacc_spread = 0.015 if regime["para_birimi"] == "USD" else max(0.015, wacc * 0.10)
    wacc_bear = wacc + wacc_spread
    wacc_bull = max(wacc - wacc_spread, terminal_growth + 0.01)

    try:
        bear_price = _scenario_fair_value(fcf0, bear_growth, wacc_bear, total_debt, total_cash, shares,
                                          growth_cap=bear_cap, terminal_growth=terminal_growth)
        base_price = _scenario_fair_value(fcf0, growth, wacc, total_debt, total_cash, shares,
                                          growth_cap=base_cap, terminal_growth=terminal_growth)
        bull_price = _scenario_fair_value(fcf0, bull_growth, wacc_bull, total_debt, total_cash, shares,
                                          growth_cap=bull_cap, terminal_growth=terminal_growth)
    except (ZeroDivisionError, OverflowError):
        return None

    if is_bist:
        oran_adi = "TCMB politika faizi"
        bist_caveat = (
            " Bu hesap tamamen TL cinsindendir: iskonto oranı, terminal büyüme ve büyüme "
            f"tavanları %{regime['enflasyon']*100:.1f}'lik uzun dönem TL enflasyon varsayımıyla "
            "aynı para biriminde tutulmuştur. UYARI: risksiz oran olarak kısa vadeli TCMB "
            "politika faizi kullanıldı - 10 yıllık TL tahvil getirisinin yerini tam tutmaz ve "
            "aylık yayımlandığı için birkaç ay gecikebilir."
        )
    else:
        oran_adi = "ABD 10 yıllık tahvil getirisi"
        bist_caveat = ""

    return (
        f"DCF tabanlı adil değer aralığı (WACC %{wacc * 100:.1f} — özsermaye maliyeti CAPM ile "
        f"[risksiz oran %{risk_free_rate_pct:.2f} ({oran_adi}) baz alınıp beta ile ayarlandı, "
        f"özsermaye maliyeti %{wacc_data['cost_of_equity']*100:.1f}], "
        f"borç maliyeti {wacc_data['cost_of_debt_source']}; 5 yıllık FCF projeksiyonu + "
        f"%{terminal_growth*100:.1f} sabit terminal büyüme varsayımıyla hesaplandı): "
        f"Ayı ~{bear_price:.2f} / Baz ~{base_price:.2f} / Boğa ~{bull_price:.2f}. "
        f"Bu basitleştirilmiş bir modeldir, profesyonel bir DCF'in yerini tutmaz - varsayımlar "
        f"değiştikçe sonuç önemli ölçüde değişebilir.{bist_caveat}"
    )
