"""Orkestrasyon: tüm sembolleri gezip teknik + temel + değer yatırımı + mum
formasyonu + trend + örüntü sonuçlarını tek bir JSON bundle'a yazar.

Bu script NİHAİ Türkçe raporu YAZMAZ - sadece yapılandırılmış veri üretir.
Nihai Türkçe özet, bu JSON'u okuyan Claude Code zamanlanmış rutini tarafından,
haber metinleriyle birlikte sentezlenir (bkz. proje planındaki mimari karar).

Kullanım: python src/data_pipeline.py [config_yolu]
"""
import json
import logging
import sys
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


def process_stock_symbol(ticker: str, market: str) -> dict:
    try:
        bundle = data_bist_us.fetch_symbol_bundle(ticker, market)
        if bundle.get("error"):
            return {"symbol": ticker, "market": market, "error": bundle["error"]}

        history_1y = bundle["history_1y"]
        history_long = bundle["history_long"]
        fund_info = bundle["fundamentals"]

        tech = indicators.analyze_symbol_technicals(history_1y)
        candle_notes = candlestick_patterns.detect_patterns(history_1y.tail(10))
        trend_notes = trend_analysis.analyze_trend(history_1y, daily_rsi_value=tech["values"].get("rsi"))
        fundamentals_notes = fundamentals.interpret_fundamentals(fund_info)
        value_notes = value_investing.value_investing_notes(fund_info)
        pattern_result = pattern_match.find_similar_patterns(history_long)
        pattern_note = pattern_match.pattern_match_note(pattern_result)

        return {
            "symbol": ticker,
            "market": market,
            "error": None,
            "technical_notes": tech["notes"] + candle_notes + trend_notes,
            "fundamental_notes": fundamentals_notes + value_notes,
            "pattern_note": pattern_note,
            "values": tech["values"],
        }
    except Exception as e:
        logger.exception(f"{ticker} işlenirken hata oluştu")
        return {"symbol": ticker, "market": market, "error": f"Beklenmeyen hata: {e}"}


def process_crypto_symbol(coin_id: str, snapshot: dict, dominance: dict) -> dict:
    try:
        bundle = data_crypto.fetch_symbol_bundle(coin_id, snapshot)
        if bundle.get("error"):
            return {"symbol": coin_id, "market": "crypto", "error": bundle["error"]}

        history_1y = bundle["history_1y"]
        history_long = bundle["history_long"]

        tech = indicators.analyze_symbol_technicals(history_1y)
        trend_notes = trend_analysis.analyze_trend(history_1y, daily_rsi_value=tech["values"].get("rsi"))
        crypto_notes = crypto_snapshot.interpret_crypto_snapshot(coin_id, bundle["crypto_snapshot"], dominance)
        pattern_result = pattern_match.find_similar_patterns(history_long)
        pattern_note = pattern_match.pattern_match_note(pattern_result)

        return {
            "symbol": coin_id,
            "market": "crypto",
            "error": None,
            "technical_notes": tech["notes"] + trend_notes,
            "fundamental_notes": crypto_notes,
            "pattern_note": pattern_note,
            "values": tech["values"],
        }
    except Exception as e:
        logger.exception(f"{coin_id} işlenirken hata oluştu")
        return {"symbol": coin_id, "market": "crypto", "error": f"Beklenmeyen hata: {e}"}


def build_bundle(config_path: str | Path) -> dict:
    config = config_module.load_config(config_path)
    symbols = config["symbols"]
    results = []

    for ticker in symbols.get("bist", []):
        logger.info(f"İşleniyor: {ticker} (BIST)")
        results.append(process_stock_symbol(ticker, "bist"))

    for ticker in symbols.get("us", []):
        logger.info(f"İşleniyor: {ticker} (ABD)")
        results.append(process_stock_symbol(ticker, "us"))

    crypto_ids = symbols.get("crypto", [])
    if crypto_ids:
        logger.info(f"Kripto snapshot alınıyor: {crypto_ids}")
        snapshot = data_crypto.fetch_snapshot(crypto_ids)
        dominance = data_crypto.fetch_global_dominance()
        for coin_id in crypto_ids:
            logger.info(f"İşleniyor: {coin_id} (kripto)")
            results.append(process_crypto_symbol(coin_id, snapshot, dominance))

    news_inbox_dir = PROJECT_ROOT / "news_inbox"
    pending_news = news_reader.collect_pending_news(news_inbox_dir)
    if pending_news:
        logger.info(f"Bekleyen haber dosyaları bulundu: {list(pending_news.keys())}")

    return {
        "generated_at": datetime.now().isoformat(),
        "symbols": results,
        "pending_news": pending_news,
    }


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ROOT / "config" / "config.yaml"
    bundle = build_bundle(config_path)

    output_path = LOG_DIR / f"bundle_{date.today().isoformat()}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    logger.info(f"Bundle yazıldı: {output_path}")
    print(str(output_path))


if __name__ == "__main__":
    main()
