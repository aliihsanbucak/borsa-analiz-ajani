"""Fiyat ve finansal tablo para birimi farkli olan sirketlerin oran testleri.

Canli ariza (22 Eylul 2026): THYAO.IS fiyati TRY, bilancosu USD oldugu icin
Yahoo'nun priceToBook alani 298 TRY / 15,88 USD = 18,76 donuyordu ve rapora
"PD/DD 18,76" olarak giriyordu. Gercek deger ~0,38. Ag cagrisi yapmadan,
gercek Yahoo cevaplarinin sadelestirilmis kopyalariyla test edilir.
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import data_bist_us


class FakeTicker:
    """yfinance.Ticker'in _normalize_currency tarafindan kullanilan yuzeyi."""

    def __init__(self, balance: dict, income: dict, cashflow: dict):
        self.balance_sheet = pd.DataFrame(balance, index=["son"]).T
        self.income_stmt = pd.DataFrame(income, index=["son"]).T
        self.cashflow = pd.DataFrame(cashflow, index=["son"]).T


# THYAO.IS, 22 Eylul 2026 - .info blogu USD, fiyat TRY
THYAO_INFO = {
    "currency": "TRY", "financialCurrency": "USD",
    "currentPrice": 298.0, "marketCap": 408_940_445_696, "sharesOutstanding": 1_372_283_353,
    "bookValue": 15.884, "priceToBook": 18.761017, "trailingEps": -6.78, "trailingPE": None,
    "priceToSalesTrailing12Months": 16.5,
    "freeCashflow": 594_875_008, "ebitda": 2_185_999_872,
    "totalDebt": 19_594_000_384, "totalCash": 6_309_000_192,
}
THYAO_TICKER = FakeTicker(
    balance={"Stockholders Equity": 21_312_000_000.0, "Total Debt": 17_804_000_000.0,
             "Cash Cash Equivalents And Short Term Investments": 6_309_000_000.0},
    income={"Net Income": 2_910_000_000.0, "Total Revenue": 24_000_000_000.0,
            "EBITDA": 2_185_000_000.0},
    cashflow={"Free Cash Flow": 2_281_000_000.0},
)

# TAVHL.IS, ayni gun - Yahoo ayni alanlari zaten TRY'ye cevirmis
TAVHL_INFO = {
    "currency": "TRY", "financialCurrency": "EUR",
    "currentPrice": 278.0, "marketCap": 100_992_188_416, "sharesOutstanding": 363_281_250,
    "bookValue": 225.694, "priceToBook": 1.2317563, "trailingEps": 16.74, "trailingPE": 16.6,
    "priceToSalesTrailing12Months": 0.99,
    "freeCashflow": 133_421_000 * 53.0, "ebitda": 26_492_917_760,
    "totalDebt": 110_976_319_488, "totalCash": 16_347_753_472,
}
TAVHL_TICKER = FakeTicker(
    balance={"Stockholders Equity": 1_582_443_000.0, "Total Debt": 2_093_048_000.0,
             "Cash Cash Equivalents And Short Term Investments": 308_000_000.0},
    income={"Net Income": 50_659_000.0, "Total Revenue": 1_820_000_000.0},
    cashflow={"Free Cash Flow": 133_421_000.0},
)


class CurrencyNormalizationTest(unittest.TestCase):
    def setUp(self):
        data_bist_us._FX_CACHE.clear()
        data_bist_us._FX_CACHE["USDTRY"] = 48.81
        data_bist_us._FX_CACHE["EURTRY"] = 53.0

    def test_tablo_para_biriminde_gelen_pd_dd_duzeltilir(self):
        info = dict(THYAO_INFO)
        data_bist_us._normalize_currency(THYAO_TICKER, info)
        self.assertAlmostEqual(info["priceToBook"], 0.384, places=2)
        self.assertIn("USD", info["currency_note"])

    def test_tablo_para_birimindeki_mutlak_kalemler_cevrilir(self):
        info = dict(THYAO_INFO)
        data_bist_us._normalize_currency(THYAO_TICKER, info)
        # FCF getirisi artik ayni para biriminde iki buyuklugun orani
        self.assertAlmostEqual(info["freeCashflow"] / info["marketCap"] * 100, 7.1, places=0)
        self.assertAlmostEqual(info["totalDebt"], 19_594_000_384 * 48.81, places=0)

    def test_olcege_oturmayan_hisse_basi_alan_dusurulur(self):
        # -6,78 ne 2,12 USD'ye ne de 103 TL'ye oturuyor: sayi uretme.
        info = dict(THYAO_INFO)
        data_bist_us._normalize_currency(THYAO_TICKER, info)
        self.assertIsNone(info["trailingEps"])
        self.assertIsNone(info["trailingPE"])

    def test_yahoo_zaten_cevirmisse_ikinci_kez_cevrilmez(self):
        info = dict(TAVHL_INFO)
        data_bist_us._normalize_currency(TAVHL_TICKER, info)
        self.assertAlmostEqual(info["priceToBook"], 1.232, places=2)
        self.assertEqual(info["totalDebt"], TAVHL_INFO["totalDebt"])

    def test_ayni_para_birimi_dokunulmadan_birakilir(self):
        info = {"currency": "TRY", "financialCurrency": "TRY", "priceToBook": 1.68,
                "currentPrice": 100.0, "bookValue": 59.5}
        data_bist_us._normalize_currency(None, info)
        self.assertEqual(info["priceToBook"], 1.68)
        self.assertNotIn("currency_note", info)

    def test_kur_alinamazsa_riskli_alanlar_dusurulur(self):
        data_bist_us._FX_CACHE["USDTRY"] = None
        info = dict(THYAO_INFO)
        data_bist_us._normalize_currency(THYAO_TICKER, info)
        for field in ("priceToBook", "trailingPE", "freeCashflow", "totalDebt"):
            self.assertIsNone(info[field], field)


if __name__ == "__main__":
    unittest.main()
