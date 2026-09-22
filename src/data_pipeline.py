"""Orkestrasyon: geniş bir sembol evrenini (BIST100 + ABD top 30 + kripto top N)
gezip teknik + temel + değer yatırımı + mum formasyonu + trend + örüntü
sonuçlarını hesaplar, her sembolü şeffaf/mekanik bir puanla değerlendirir
(bkz. scoring.py) ve en yüksek puanlı N sembolü tek bir JSON bundle'a yazar.

Bu script NİHAİ Türkçe raporu YAZMAZ - sadece yapılandırılmış veri üretir.
Nihai Türkçe özet, bu JSON'u okuyan yerel Claude Code CLI tarafından,
haber metinleriyle birlikte sentezlenir (bkz. proje planındaki mimari karar).

Kullanım: python src/data_pipeline.py [config_yolu]
"""
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as config_module
import data_bist_us
import data_crypto
import indicators
import fundamentals
import value_investing
import candlestick_patterns
import trend_analysis
import crypto_snapshot
import pattern_match
import news_reader
import scoring
import macro
import dcf
import news_feeds
import contrarian

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"run_{date.today().isoformat()}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("data_pipeline")


def process_stock_symbol(ticker: str, market: str, risk_free_rate_pct: float | None,
                         try_risk_free_rate_pct: float | None = None) -> dict:
    try:
        bundle = data_bist_us.fetch_symbol_bundle(ticker, market)
        if bundle.get("error"):
            return {"symbol": ticker, "market": market, "error": bundle["error"], "score": None}

        history_1y = bundle["history_1y"]
        history_long = bundle["history_long"]
        fund_info = bundle["fundamentals"]

        tech = indicators.analyze_symbol_technicals(history_1y)
        candle_notes = candlestick_patterns.detect_patterns(history_1y.tail(10))
        trend_notes = trend_analysis.analyze_trend(history_1y, daily_rsi_value=tech["values"].get("rsi"))
        fundamentals_notes = fundamentals.interpret_fundamentals(fund_info)

        # Once gercek bir WACC/DCF hesaplamayi dene (dcf.py); hesaplanamiyorsa
        # (negatif FCF, eksik beta vb.) Lynch'in kaba "adil F/K=buyume" sezgiselene don.
        # Iskonto orani nakit akisiyla AYNI para biriminde olmali: BIST icin TL
        # (TCMB politika faizi), ABD icin dolar (10 yillik tahvil getirisi).
        # Bkz. dcf.currency_regime.
        is_bist = market == "bist"
        dcf_rate = try_risk_free_rate_pct if is_bist else risk_free_rate_pct
        dcf_note = dcf.simplified_dcf_note(fund_info, dcf_rate, is_bist=is_bist) if dcf_rate else None
        value_notes = value_investing.value_investing_notes(fund_info, include_fair_value=(dcf_note is None))
        if dcf_note:
            value_notes.append(dcf_note)

        pattern_result = pattern_match.find_similar_patterns(history_long)
        pattern_note = pattern_match.pattern_match_note(pattern_result)
        score = scoring.stock_score(fund_info, pattern_result)

        # Karsit yatirim taramasi (Gallea & Patalon III, "Contrarian Investing") -
        # zaten cekilmis veriyle, ekstra API cagrisi olmadan hesaplanir.
        contrarian_result = contrarian.contrarian_screen(ticker, market, fund_info, history_1y)

        return {
            "symbol": ticker,
            "market": market,
            "error": None,
            "technical_notes": tech["notes"] + candle_notes + trend_notes,
            "fundamental_notes": fundamentals_notes + value_notes,
            "pattern_note": pattern_note,
            "values": tech["values"],
            "score": score,
            "contrarian": contrarian_result,
        }
    except Exception as e:
        logger.exception(f"{ticker} işlenirken hata oluştu")
        return {"symbol": ticker, "market": market, "error": f"Beklenmeyen hata: {e}", "score": None}


def process_crypto_symbol(coin_id: str, snapshot: dict, dominance: dict) -> dict:
    try:
        bundle = data_crypto.fetch_symbol_bundle(coin_id, snapshot)
        if bundle.get("error"):
            logger.warning(f"{coin_id}: kripto verisi hiçbir kaynaktan alınamadı ({bundle['error']})")
            return {"symbol": coin_id, "market": "crypto", "error": bundle["error"], "score": None}

        history_1y = bundle["history_1y"]
        history_long = bundle["history_long"]
        crypto_snap = bundle["crypto_snapshot"]

        tech = indicators.analyze_symbol_technicals(history_1y)
        trend_notes = trend_analysis.analyze_trend(history_1y, daily_rsi_value=tech["values"].get("rsi"))
        crypto_notes = crypto_snapshot.interpret_crypto_snapshot(coin_id, crypto_snap, dominance)
        pattern_result = pattern_match.find_similar_patterns(history_long)
        pattern_note = pattern_match.pattern_match_note(pattern_result)

        if scoring.is_stablecoin_like(history_1y["Close"]):
            score = None
            crypto_notes = crypto_notes + [
                "Bu varlık fiyatı bir dövize/emtiaya sabitlenmiş bir token gibi görünüyor "
                "(çok düşük fiyat volatilitesi) - büyüme potansiyeli değerlendirmesi bu tür "
                "varlıklar için anlamlı olmadığından puanlamaya dahil edilmedi."
            ]
        else:
            score = scoring.crypto_score(pattern_result, crypto_snap.get("market_cap_rank"))

        return {
            "symbol": coin_id,
            "market": "crypto",
            "error": None,
            "technical_notes": tech["notes"] + trend_notes,
            "fundamental_notes": crypto_notes,
            "pattern_note": pattern_note,
            "values": tech["values"],
            "score": score,
        }
    except Exception as e:
        logger.exception(f"{coin_id} işlenirken hata oluştu")
        return {"symbol": coin_id, "market": "crypto", "error": f"Beklenmeyen hata: {e}", "score": None}


def find_sp500_contrarian_candidates(existing_us_symbols: set[str]) -> list[dict]:
    """Karsit yatirim taramasini mevcut sabit ABD evreninin (top-30) DISINA
    genisletir - kullanicinin istedigi gibi. 2 asamali, performans icin:
    Asama 1 (ucuz): sadece 1 yillik fiyat gecmisi cekilir, 52-hafta-%50-dusus
    + fiyat>5 on-filtresi uygulanir (fundamentals CEKILMEZ). Asama 2 (pahali,
    sadece Asama 1'i gecenler icin): tam fetch_symbol_bundle + tam
    contrarian_screen (market cap + 2/4 degerleme orani testi dahil)."""
    logger.info("Karşıt yatırım taraması için S&P 500 listesi çekiliyor (Wikipedia)")
    sp500_symbols = data_bist_us.fetch_sp500_symbols()
    if not sp500_symbols:
        logger.warning("S&P 500 listesi çekilemedi, karşıt tarama genişlemesi bu çalışmada atlanıyor")
        return []

    new_symbols = [s for s in sp500_symbols if s not in existing_us_symbols]
    logger.info(f"S&P 500'den {len(new_symbols)} yeni sembol (mevcut ABD top-30'da olmayan) Aşama 1 için taranacak")

    stage1_passed = []
    for i, ticker in enumerate(new_symbols):
        if i % 50 == 0:
            logger.info(f"Aşama 1 (ucuz on-filtre) ilerleme: {i}/{len(new_symbols)}")
        hist = data_bist_us.fetch_history(ticker, period="1y")
        time.sleep(0.3)
        if hist is None or hist.empty:
            continue
        pct = contrarian.pct_off_52w_high(hist)
        if pct is None or pct > contrarian.PRIMARY_MAX_PCT_OF_HIGH:
            continue
        last_price = float(hist["Close"].dropna().iloc[-1])
        if last_price <= contrarian.PRIMARY_MIN_PRICE:
            continue
        stage1_passed.append(ticker)

    logger.info(f"Aşama 1'i geçen (52 haftalık zirveden en az %50 düşmüş) sembol sayısı: {len(stage1_passed)}")

    candidates = []
    for ticker in stage1_passed:
        logger.info(f"Aşama 2 (tam analiz): {ticker} (karşıt aday adayı)")
        bundle = data_bist_us.fetch_symbol_bundle(ticker, "us")
        time.sleep(0.5)
        if bundle.get("error"):
            continue
        result = contrarian.contrarian_screen(ticker, "us", bundle["fundamentals"], bundle["history_1y"])
        if result:
            candidates.append(result)

    logger.info(f"S&P 500 genişlemesinden bulunan karşıt yatırım adayı sayısı: {len(candidates)}")
    return candidates


def build_bundle(config_path: str | Path) -> dict:
    config = config_module.load_config(config_path)
    symbols = config["symbols"]
    top_n = config.get("top_n_report", 30)
    results = []

    # Makro gostergeler (ozellikle ABD 10y tahvil getirisi) hisse islemeye
    # baslamadan ONCE cekiliyor - dcf.py'nin WACC hesaplamasi icin risksiz
    # oran gerekiyor.
    logger.info("Makro göstergeler alınıyor (WACC hesaplaması için risksiz oran dahil)")
    macro_snapshot = macro.fetch_macro_snapshot()
    macro_notes = macro.interpret_macro(macro_snapshot)
    risk_free_rate_pct = None
    y10 = macro_snapshot.get("us_10y_yield")
    if y10:
        risk_free_rate_pct = y10["value"]

    try_risk_free_rate_pct = None
    tcmb = macro_snapshot.get("try_policy_rate")
    if tcmb:
        try_risk_free_rate_pct = tcmb["value"]
    else:
        logger.warning("TCMB politika faizi alınamadı - BIST sembolleri için DCF hesaplanmayacak "
                       "(dolar oranıyla hesaplamak TL nakit akışını sistematik olarak ucuz gösterir)")

    bist_list = symbols.get("bist", [])
    us_list = symbols.get("us", [])
    logger.info(f"BIST evreni: {len(bist_list)} sembol, ABD evreni: {len(us_list)} sembol işlenecek")

    for ticker in bist_list:
        logger.info(f"İşleniyor: {ticker} (BIST)")
        results.append(process_stock_symbol(ticker, "bist", risk_free_rate_pct, try_risk_free_rate_pct))

    for ticker in us_list:
        logger.info(f"İşleniyor: {ticker} (ABD)")
        results.append(process_stock_symbol(ticker, "us", risk_free_rate_pct, try_risk_free_rate_pct))

    crypto_count = symbols.get("crypto_count", 0)
    if crypto_count > 0:
        crypto_ids = data_crypto.fetch_top_n_market_cap(crypto_count)
        logger.info(f"Kripto evreni (elle seçilmiş, tanınan ilk {crypto_count}): {len(crypto_ids)} coin bulundu")
        if crypto_ids:
            snapshot = data_crypto.fetch_snapshot(crypto_ids)
            dominance = data_crypto.fetch_global_dominance()
            for coin_id in crypto_ids:
                logger.info(f"İşleniyor: {coin_id} (kripto)")
                results.append(process_crypto_symbol(coin_id, snapshot, dominance))

    total_processed = len(results)
    errored = [r for r in results if r.get("error")]
    scored = [r for r in results if r.get("error") is None and r.get("score") is not None]
    scored.sort(key=lambda r: r["score"], reverse=True)
    top_results = scored[:top_n]

    logger.info(
        f"Toplam {total_processed} sembol işlendi, {len(errored)} hata, "
        f"{len(scored)} sembol puanlanabildi, en yüksek puanlı {len(top_results)} tanesi rapora alınıyor"
    )

    # Karsit yatirim (Gallea & Patalon III) adaylari: mevcut evrenden (bedava,
    # zaten cekilmis veriyle) + S&P 500 genislemesinden (2 asamali, ayri tarama)
    contrarian_from_existing = [r["contrarian"] for r in results if r.get("contrarian")]
    existing_us_symbols = set(us_list)
    contrarian_from_sp500 = find_sp500_contrarian_candidates(existing_us_symbols)
    contrarian_candidates = contrarian_from_existing + contrarian_from_sp500
    contrarian_candidates.sort(key=lambda c: c["signal_count"], reverse=True)
    logger.info(
        f"Karşıt yatırım adayı toplamı: {len(contrarian_candidates)} "
        f"(mevcut evrenden {len(contrarian_from_existing)}, S&P 500 genişlemesinden {len(contrarian_from_sp500)})"
    )

    news_inbox_dir = PROJECT_ROOT / "news_inbox"
    pending_news = news_reader.collect_pending_news(news_inbox_dir)
    if pending_news:
        logger.info(f"Bekleyen haber dosyaları bulundu: {list(pending_news.keys())}")

    logger.info("Piyasa haberleri RSS akışlarından çekiliyor (UzmanCoin, Investing.com Türkiye)")
    market_news = news_feeds.fetch_market_news(hours=24)
    logger.info(f"Son 24 saatte {len(market_news)} haber başlığı bulundu")

    return {
        "generated_at": datetime.now().isoformat(),
        "universe_size": total_processed,
        "errored_symbol_count": len(errored),
        "scoring_explanation": scoring.SCORING_EXPLANATION,
        "macro_notes": macro_notes,
        "market_news": market_news,
        "contrarian_candidates": contrarian_candidates,
        "contrarian_book_citation": contrarian.BOOK_CITATION,
        "contrarian_rule_explanation": (
            "Birincil filtre: fiyat 52 haftalık en yüksek seviyesinden en az %50 düşmüş, "
            "fiyat > 5, piyasa değeri > 150 milyon $. Teyit: F/K<12, F/DD<1.0, F/SNA (P/FCF)<10, "
            "F/S<1.0 oranlarından en az ikisi karşılanmalı. Kitapta ayrıca içeriden/dışarıdan "
            "yatırımcı alım sinyalleri var ama bunlar ücretsiz veriyle otomatikleştirilemediği "
            "için (sadece anlık sahiplik yüzdesi var, işlem bazlı veri yok) uygulanmadı."
        ),
        "symbols": top_results,
        "pending_news": pending_news,
    }


# Bir calismada sembollerin bu orandan fazlasi hata verirse (tipik sebep: gecici
# DNS/ag arizasi, veri saglayici rate-limit) uretilen bundle piyasayi degil arizayi
# yansitir. 15 Eylul 2026'da 02:19'daki saglam calismanin ustune 18:23'teki %93
# hatali calisma yazdi ve o gunun verisi kayboldu.
MAX_ERROR_RATE = 0.50


def _error_rate(bundle: dict) -> float:
    total = bundle.get("universe_size") or 0
    if not total:
        return 1.0
    return (bundle.get("errored_symbol_count") or 0) / total


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ROOT / "config" / "config.yaml"
    bundle = build_bundle(config_path)

    output_path = LOG_DIR / f"bundle_{date.today().isoformat()}.json"
    rate = _error_rate(bundle)

    if rate > MAX_ERROR_RATE and output_path.exists():
        try:
            with open(output_path, encoding="utf-8") as f:
                existing_rate = _error_rate(json.load(f))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Mevcut bundle okunamadi, uzerine yaziliyor: {exc}")
            existing_rate = 1.0

        if existing_rate <= rate:
            degraded_path = output_path.with_suffix(".degraded.json")
            with open(degraded_path, "w", encoding="utf-8") as f:
                json.dump(bundle, f, ensure_ascii=False, indent=2)
            logger.error(
                f"Bu calismada sembollerin %{rate * 100:.0f}'i hata verdi; bugun icin "
                f"zaten daha saglam bir bundle var (%{existing_rate * 100:.0f} hata). "
                f"Mevcut dosya KORUNDU, bozuk sonuc {degraded_path} altina yazildi."
            )
            sys.exit(2)

    if rate > MAX_ERROR_RATE:
        logger.warning(
            f"Sembollerin %{rate * 100:.0f}'i hata verdi - bundle yine de yaziliyor "
            "(bugun icin karsilastirilacak onceki bir calisma yok)."
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    logger.info(f"Bundle yazıldı: {output_path}")
    print(str(output_path))


if __name__ == "__main__":
    main()
