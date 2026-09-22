"""Tek bir sembolu, gunluk raporla AYNI analiz katmanlarindan gecirip
kucuk bir JSON bundle uretir. Nihai Turkce metni bu betik YAZMAZ - gunluk
rapordaki mimariyle ayni sekilde, JSON'u okuyan Claude CLI yazar.

Kullanim:
    python src/analyze_symbol.py <market> <tanimlayici> <cikti_json_yolu>
    python src/analyze_symbol.py bist THYAO.IS logs/sorgu_THYAO.json
    python src/analyze_symbol.py crypto bitcoin logs/sorgu_BTC.json

Cikis kodu 0 = bundle yazildi, 1 = veri cekilemedi/hata.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import data_bist_us
import data_crypto
import data_pipeline
import macro
import news_feeds
import scoring


def related_news(identifier: str, market: str, fund_info: dict | None, hours: int = 24) -> list[dict]:
    """Son 24 saatin RSS basliklarindan yalnizca bu sembolle ilgili gorunenleri
    suzer. Eslesme kaba ve kasitli olarak dar: sembol kodu veya sirket adinin
    ilk kelimesi baslikta gecmeli. Yanlis pozitif, alakasiz bir haberi sembole
    yapistirmaktan daha zararli oldugu icin genis eslesme yapilmaz.
    """
    try:
        all_news = news_feeds.fetch_market_news(hours=hours)
    except Exception:
        return []

    needles = set()
    base = identifier.replace(".IS", "").replace("-USD", "")
    if len(base) >= 3:
        needles.add(base.lower())
    if market == "crypto":
        needles.add(identifier.lower().replace("-", " "))
    if fund_info:
        short_name = (fund_info.get("shortName") or "").strip()
        first_word = short_name.split(" ")[0] if short_name else ""
        if len(first_word) >= 4:
            needles.add(first_word.lower())

    hits = []
    for item in all_news:
        title = (item.get("title") or "").lower()
        if any(n in title for n in needles):
            hits.append(item)
    return hits


def build(market: str, identifier: str) -> dict:
    bundle: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "query": {"market": market, "identifier": identifier},
        "scoring_explanation": scoring.SCORING_EXPLANATION,
    }

    # Makro, DCF'in risksiz orani icin gerekli; gunluk raporla ayni kaynak.
    macro_snapshot = macro.fetch_macro_snapshot()
    bundle["macro_notes"] = macro.interpret_macro(macro_snapshot)
    y10 = macro_snapshot.get("us_10y_yield")
    risk_free = y10["value"] if y10 and y10.get("value") else None
    # BIST icin TL risksiz orani (TCMB politika faizi) - gunluk raporla ayni mantik
    tcmb = macro_snapshot.get("try_policy_rate")
    try_risk_free = tcmb["value"] if tcmb and tcmb.get("value") else None

    fund_info = None
    if market == "crypto":
        snapshot = data_crypto.fetch_snapshot([identifier])
        dominance = data_crypto.fetch_global_dominance()
        result = data_pipeline.process_crypto_symbol(identifier, snapshot, dominance)
    else:
        result = data_pipeline.process_stock_symbol(identifier, market, risk_free, try_risk_free)

    bundle["symbol"] = result
    if result.get("error"):
        return bundle

    if market != "crypto":
        # process_stock_symbol temel veriyi disariya vermiyor; haber eslesmesi
        # ve baslik icin sirket adi/sektoru gerektiginden bir kez daha okunur
        # (tek sembollük sorguda bu ek cagrinin maliyeti onemsiz).
        try:
            fund_info = data_bist_us.fetch_fundamentals(identifier)
        except Exception:
            fund_info = None

    bundle["related_news"] = related_news(identifier, market, fund_info)
    bundle["company_name"] = (fund_info or {}).get("shortName")
    bundle["sector"] = (fund_info or {}).get("sector")
    return bundle


def main():
    if len(sys.argv) < 4:
        print("Kullanim: python analyze_symbol.py <market> <tanimlayici> <cikti_json>")
        sys.exit(1)

    market, identifier, out_path = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    bundle = build(market, identifier)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    err = bundle.get("symbol", {}).get("error")
    if err:
        print(f"HATA: {identifier} verisi alinamadi: {err}")
        sys.exit(1)
    print(f"Bundle yazildi: {out_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
