"""DCF'in para birimi rejimi: BIST hisseleri TL, ABD hisseleri dolar.

Onceden BIST'in TL nakit akislari ABD dolari risksiz oraniyla (%4,98) iskonto
ediliyordu. %30+ enflasyonlu bir para biriminde bu, her BIST sirketini
sistematik olarak "ucuz" gosteren bir hataydi. Bu testler iki seyi birden
korur: TL tarafinin kendi icinde tutarli olmasi ve ABD tarafinin
degismemesi.
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import dcf

TCMB_RATE = 35.5   # TCMB politika faizi (%), macro.try_policy_rate formatinda
US_RATE = 4.98     # ABD 10 yillik tahvil getirisi (%)

# TUPRS.IS benzeri, TL raporlayan bir BIST sirketi (degerler yuvarlanmis)
BIST_FUNDAMENTALS = {
    "beta": 0.35, "marketCap": 770_000_000_000, "sharesOutstanding": 1_939_000_000,
    "freeCashflow": 62_000_000_000, "earningsGrowth": 0.20,
    "totalDebt": 120_000_000_000, "totalCash": 90_000_000_000,
    "Interest Expense": 9_000_000_000, "Tax Rate For Calcs": 0.22,
    "currency": "TRY", "financialCurrency": "TRY",
}

US_FUNDAMENTALS = {
    "beta": 1.1, "marketCap": 3_000_000_000_000, "sharesOutstanding": 15_000_000_000,
    "freeCashflow": 100_000_000_000, "earningsGrowth": 0.08,
    "totalDebt": 100_000_000_000, "totalCash": 60_000_000_000,
    "Interest Expense": 3_500_000_000, "Tax Rate For Calcs": 0.15,
    "currency": "USD", "financialCurrency": "USD",
}


class CurrencyRegimeTest(unittest.TestCase):
    def test_bist_rejiminde_terminal_buyume_tl_enflasyonuna_esitlenir(self):
        r = dcf.currency_regime(TCMB_RATE, is_bist=True)
        self.assertEqual(r["para_birimi"], "TRY")
        # %35,5 politika faizi - %5 varsayilan reel faiz
        self.assertAlmostEqual(r["enflasyon"], 0.305, places=3)
        self.assertEqual(r["terminal_growth"], r["enflasyon"])

    def test_buyume_tavanlarinin_reel_karsiligi_iki_rejimde_ayni(self):
        try_caps = dcf.currency_regime(TCMB_RATE, is_bist=True)["growth_caps"]
        us_caps = dcf.currency_regime(US_RATE, is_bist=False)["growth_caps"]
        for nominal_try, nominal_us in zip(try_caps, us_caps):
            reel_try = (1 + nominal_try) / (1 + 0.305) - 1
            reel_us = (1 + nominal_us) / (1 + dcf.US_LONG_RUN_INFLATION) - 1
            self.assertAlmostEqual(reel_try, reel_us, places=6)

    def test_abd_rejimi_eski_davranisla_ayni(self):
        r = dcf.currency_regime(US_RATE, is_bist=False)
        self.assertEqual(r["terminal_growth"], 0.025)
        self.assertEqual(r["growth_caps"], (0.10, 0.18, 0.28))
        wacc = dcf.compute_wacc(US_FUNDAMENTALS, US_RATE, is_bist=False)
        beklenen_ke = US_RATE / 100 + 1.1 * dcf.EQUITY_RISK_PREMIUM
        self.assertAlmostEqual(wacc["cost_of_equity"], beklenen_ke, places=10)

    def test_tl_ozsermaye_maliyeti_reel_kurulup_enflasyonla_sisirilir(self):
        wacc = dcf.compute_wacc(BIST_FUNDAMENTALS, TCMB_RATE, is_bist=True)
        enflasyon = 0.305
        reel_rf = (1 + TCMB_RATE / 100) / (1 + enflasyon) - 1
        beta = max(0.35, dcf.TRY_MIN_BETA)
        beklenen = (1 + reel_rf + beta * dcf.TRY_EQUITY_RISK_PREMIUM) * (1 + enflasyon) - 1
        self.assertAlmostEqual(wacc["cost_of_equity"], beklenen, places=10)
        # Reel risk primi enflasyona bolunup erimemeli: nominal ke > politika faizi
        self.assertGreater(wacc["cost_of_equity"], TCMB_RATE / 100)

    def test_tl_rejiminde_borc_maliyeti_politika_faizinin_altina_inmez(self):
        wacc = dcf.compute_wacc(BIST_FUNDAMENTALS, TCMB_RATE, is_bist=True)
        # 9 mlr faiz / 120 mlr borc = %7,5; TL modelinde politika faizine yukselir
        self.assertAlmostEqual(wacc["cost_of_debt_pretax"], TCMB_RATE / 100, places=10)
        self.assertIn("döviz borcu", wacc["cost_of_debt_source"])

    def test_yabanci_para_raporlayan_sirketin_buyumesi_tl_ye_cevrilir(self):
        r = dcf.currency_regime(TCMB_RATE, is_bist=True)
        usd_raporlayan = dict(BIST_FUNDAMENTALS, financialCurrency="USD")
        tl_buyume = dcf.nominal_growth_in_regime(0.20, usd_raporlayan, r)
        self.assertAlmostEqual(tl_buyume, 1.20 * 1.305 / 1.025 - 1, places=10)
        # TL raporlayan sirkette dokunulmaz
        self.assertEqual(dcf.nominal_growth_in_regime(0.20, BIST_FUNDAMENTALS, r), 0.20)

    def test_wacc_terminal_buyumeye_cok_yakinsa_sayi_uretilmez(self):
        # Beta ve borc oyle secildi ki WACC terminal buyumenin hemen ustunde kalsin
        dar = dict(BIST_FUNDAMENTALS, beta=0.0, totalDebt=900_000_000_000,
                   marketCap=100_000_000_000, **{"Interest Expense": 0})
        wacc = dcf.compute_wacc(dar, TCMB_RATE, is_bist=True)
        r = dcf.currency_regime(TCMB_RATE, is_bist=True)
        self.assertLess(wacc["wacc"] - r["terminal_growth"],
                        max(dcf.MIN_TERMINAL_SPREAD, dcf.MIN_TERMINAL_SPREAD_RATIO * wacc["wacc"]))
        self.assertIsNone(dcf.simplified_dcf_note(dar, TCMB_RATE, is_bist=True))

    def test_bist_notu_tl_oldugunu_ve_kaynagini_soyler(self):
        note = dcf.simplified_dcf_note(BIST_FUNDAMENTALS, TCMB_RATE, is_bist=True)
        self.assertIsNotNone(note)
        self.assertIn("TCMB politika faizi", note)
        self.assertIn("tamamen TL cinsindendir", note)

    def test_abd_notunda_tl_uyarisi_yok(self):
        note = dcf.simplified_dcf_note(US_FUNDAMENTALS, US_RATE, is_bist=False)
        self.assertIsNotNone(note)
        self.assertIn("ABD 10 yıllık tahvil getirisi", note)
        self.assertNotIn("TCMB", note)


if __name__ == "__main__":
    unittest.main()
