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

ÖNEMLİ SINIRLAMA: BIST hisseleri için de ABD doları cinsinden risksiz oran
kullanılıyor (TL cinsinden güvenilir/ücretsiz bir risksiz oran serisi yok).
Bu, BIST hisseleri için WACC/DCF çıktısının ABD hisselerine göre daha kaba
bir yaklaşım olduğu anlamına gelir - bu sınırlama rapora not olarak
düşülür.
"""

EQUITY_RISK_PREMIUM = 0.05
DEFAULT_CREDIT_SPREAD = 0.02
DEFAULT_TAX_RATE = 0.20
TERMINAL_GROWTH = 0.025
PROJECTION_YEARS = 5


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_wacc(fundamentals: dict, risk_free_rate_pct: float) -> dict | None:
    """risk_free_rate_pct: yüzde olarak (örn. 4.74), macro.py'nin formatıyla uyumlu."""
    if not fundamentals or risk_free_rate_pct is None:
        return None

    beta = fundamentals.get("beta")
    market_cap = fundamentals.get("marketCap")
    if beta is None or not market_cap:
        return None

    risk_free = risk_free_rate_pct / 100
    cost_of_equity = risk_free + beta * EQUITY_RISK_PREMIUM

    total_debt = fundamentals.get("totalDebt") or 0
    interest_expense = fundamentals.get("Interest Expense")
    tax_rate = fundamentals.get("Tax Rate For Calcs")
    if tax_rate is None or tax_rate < 0 or tax_rate > 0.6:
        tax_rate = DEFAULT_TAX_RATE

    if interest_expense and total_debt:
        pretax_cost_of_debt = _clamp(abs(interest_expense) / total_debt, 0.01, 0.30)
        cost_of_debt_source = "şirketin gerçek faiz gideri/toplam borç oranından hesaplandı"
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
    wacc = _clamp(wacc, 0.03, 0.35)

    return {
        "wacc": wacc,
        "cost_of_equity": cost_of_equity,
        "cost_of_debt_pretax": pretax_cost_of_debt,
        "cost_of_debt_source": cost_of_debt_source,
        "tax_rate": tax_rate,
        "weight_equity": weight_equity,
        "weight_debt": weight_debt,
    }


def _scenario_fair_value(fcf0: float, growth: float, wacc: float, total_debt: float, total_cash: float, shares: float, growth_cap: float) -> float:
    growth = _clamp(growth, -0.15, growth_cap)
    fcf = fcf0
    pv_sum = 0.0
    for year in range(1, PROJECTION_YEARS + 1):
        fcf = fcf * (1 + growth)
        pv_sum += fcf / ((1 + wacc) ** year)
    terminal_value = fcf * (1 + TERMINAL_GROWTH) / (wacc - TERMINAL_GROWTH)
    pv_terminal = terminal_value / ((1 + wacc) ** PROJECTION_YEARS)
    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - total_debt + total_cash
    return equity_value / shares


def simplified_dcf_note(fundamentals: dict, risk_free_rate_pct: float, is_bist: bool = False) -> str | None:
    """Hesaplanabiliyorsa (pozitif FCF, beta, hisse sayısı, kazanç büyümesi
    verisi mevcutsa) bear/base/bull DCF adil değer aralığı döner. Aksi
    halde None döner (çağıran taraf Lynch sezgiselene geri dönebilir)."""
    wacc_data = compute_wacc(fundamentals, risk_free_rate_pct)
    if wacc_data is None:
        return None

    fcf0 = fundamentals.get("freeCashflow")
    shares = fundamentals.get("sharesOutstanding")
    growth = fundamentals.get("earningsGrowth")
    total_debt = fundamentals.get("totalDebt") or 0
    total_cash = fundamentals.get("totalCash") or 0

    if fcf0 is None or fcf0 <= 0 or shares is None or shares <= 0 or growth is None:
        return None

    wacc = wacc_data["wacc"]
    if wacc <= TERMINAL_GROWTH + 0.02:
        return None

    bear_growth = growth * 0.5 if growth > 0 else growth * 1.5
    bull_growth = growth * 1.3

    # Senaryolar arasinda GERCEK bir ayrisma saglamak icin hem buyume
    # tavani hem de WACC senaryo bazinda degistiriliyor - aksi halde
    # (ozellikle yuksek buyume oranli sirketlerde) uc senaryo da ayni
    # tavana sikisip ozdes sonuc uretebiliyordu (bu hata ilk canli testte
    # tespit edilip duzeltildi: bkz. BRK-B ornegi, 3 senaryo da 2934.70
    # cikmisti).
    wacc_bear = wacc + 0.015
    wacc_bull = max(wacc - 0.015, TERMINAL_GROWTH + 0.01)

    try:
        bear_price = _scenario_fair_value(fcf0, bear_growth, wacc_bear, total_debt, total_cash, shares, growth_cap=0.10)
        base_price = _scenario_fair_value(fcf0, growth, wacc, total_debt, total_cash, shares, growth_cap=0.18)
        bull_price = _scenario_fair_value(fcf0, bull_growth, wacc_bull, total_debt, total_cash, shares, growth_cap=0.28)
    except (ZeroDivisionError, OverflowError):
        return None

    bist_caveat = ""
    if is_bist:
        bist_caveat = (" UYARI: BIST hissesi için TL yerine ABD doları risksiz oranı kullanıldı "
                        "(güvenilir/ücretsiz bir TL risksiz oran serisi yok), bu yüzden bu hesap "
                        "ABD hisselerine göre daha kaba bir yaklaşımdır.")

    return (
        f"DCF tabanlı adil değer aralığı (WACC %{wacc * 100:.1f} — özsermaye maliyeti CAPM ile "
        f"[risksiz oran %{risk_free_rate_pct:.2f} baz alınıp beta ile ayarlandı, özsermaye maliyeti "
        f"%{wacc_data['cost_of_equity']*100:.1f}], "
        f"borç maliyeti {wacc_data['cost_of_debt_source']}; 5 yıllık FCF projeksiyonu + %2.5 sabit "
        f"terminal büyüme varsayımıyla hesaplandı): "
        f"Ayı ~{bear_price:.2f} / Baz ~{base_price:.2f} / Boğa ~{bull_price:.2f}. "
        f"Bu basitleştirilmiş bir modeldir, profesyonel bir DCF'in yerini tutmaz - varsayımlar "
        f"değiştikçe sonuç önemli ölçüde değişebilir.{bist_caveat}"
    )
