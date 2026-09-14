"""Genel piyasa haberlerini ücretsiz, resmi RSS akışlarından çeker (kullanıcının
paylaştığı kaynak hiyerarşisindeki "Seviye 4 - Haber Kaynakları" katmanı).

Sadece gerçekten ücretsiz/açık, scraping gerektirmeyen kaynaklar kullanılıyor:
- UzmanCoin (kripto haberleri) - /feed/ RSS'i canlı test edildi, çalışıyor
- Investing.com Türkiye (genel piyasa haberleri) - /rss/news.rss canlı test edildi

KAPSAM DIŞI (canlı test edildi, uygun bir yol bulunamadı):
- CoinGlass: eski ücretsiz API endpoint'i "deprecated" hatası veriyor, güncel
  API'si kayıt gerektiriyor - kullanıcı şimdilik istemedi
- KAP: modern bir Next.js tek sayfa uygulaması, belgelenmiş bir genel API yok;
  iç API'lerini reverse-engineer etmek scraping sayılır, yapılmadı
- Bulls Yatırım: bot koruması (WAF) kullanıyor, scraping denenmedi

ÖNEMLİ: Bu haberler kullanıcının kendi hiyerarşisine göre "Seviye 4" - yani
doğrulanmamış, sadece KEŞİF amaçlı bir sinyal. Rapor sentezleyen Claude bu
başlıkları "gerçek" diye sunmamalı, sadece "şu haber başlığı görüldü" şeklinde
aktarmalı - haber → doğrulama zincirinin geri kalanı (birincil kaynak, veri,
fiyat reaksiyonu) bu ücretsiz/otomatik pipeline'da yapılamıyor (bkz. README'deki
KAP/on-chain kapsam dışı gerekçeleri).
"""
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

TIMEOUT = 10

FEEDS = {
    "UzmanCoin": "https://uzmancoin.com/feed/",
    "Investing.com Türkiye": "https://tr.investing.com/rss/news.rss",
}


def _parse_rss(xml_text: str, source: str, since: datetime) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        date_el = item.find("pubDate")
        if title_el is None or title_el.text is None:
            continue

        published = None
        if date_el is not None and date_el.text:
            raw_date = date_el.text.strip()
            try:
                published = parsedate_to_datetime(raw_date)
            except (ValueError, TypeError):
                # Investing.com Turkiye "YYYY-MM-DD HH:MM:SS" gibi standart-disi
                # bir format kullaniyor (RFC 822 degil) - ayrica denenir
                try:
                    published = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    published = None
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)

        if published is not None and published < since:
            continue

        items.append({
            "source": source,
            "title": title_el.text.strip(),
            "link": link_el.text.strip() if link_el is not None and link_el.text else None,
            "published": published.isoformat() if published else None,
        })
    return items


def fetch_market_news(hours: int = 24, max_per_source: int = 30) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_items = []
    for source, url in FEEDS.items():
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception:
            continue
        items = _parse_rss(resp.text, source, since)
        all_items.extend(items[:max_per_source])
    return all_items
