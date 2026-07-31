# Borsa Analiz Ajanı

BIST, ABD hisseleri ve kripto paralar için otomatik günlük teknik + temel
analiz üretip Telegram'a gönderen kişisel bir araç. **Yatırım tavsiyesi
vermez** — sadece nesnel gözlemler sunar.

## İçerdiği analiz yöntemleri

- **Teknik göstergeler**: RSI, MACD, SMA/EMA (20/50/200), Bollinger Bantları, hacim trendi
- **Mum formasyonları** (Steve Nison — *Japanese Candlestick Charting Techniques*): doji, çekiç, asılı adam, kayan yıldız, yutan boğa/ayı, sabah/akşam yıldızı — sadece BIST/ABD hisselerinde (OHLC verisi gerektirir)
- **Trend analizi** (John Murphy — *Technical Analysis of the Financial Markets*): Dow Teorisi tabanlı trend yönü, destek/direnç seviyeleri
- **Çoklu zaman dilimi teyidi** (Alexander Elder — *Trading for a Living*, "üç ekran" mantığı): haftalık trend + günlük RSI karşılaştırması
- **Temel analiz**: F/K, PD/DD, temettü verimi, kâr marjı, borç/özkaynak (sadece hisseler)
- **Değer yatırımı kriterleri** (Benjamin Graham & David Dodd — *Security Analysis*, Graham — *The Intelligent Investor*): "defansif yatırımcı" skoru (cari oran, borçluluk, kazanç istikrarı, temettü, F/K, F/K×PD/DD)
- **PEG oranı ve büyüme kategorisi** (Peter Lynch — *One Up On Wall Street*)
- **Geçmiş örüntü karşılaştırması**: sembolün kendi geçmişinde benzer fiyat hareketlerini bulup, ardından tipik olarak ne olduğunu istatistiksel olarak raporlar
- **Haber duygu analizi**: `news_inbox/` klasörüne bıraktığınız PDF/txt/docx haberleri, günlük çalışma sırasında Claude tarafından okunup teknik/temel bulgularla birlikte yorumlanır

## Kurulum

```powershell
cd "C:\Users\Ali İhsan Bucak\borsa-analiz-ajani"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config\config.example.yaml config\config.yaml
```

`config\config.yaml` dosyasını açıp:
- `symbols.bist` / `symbols.us`: takip etmek istediğiniz hisse sembolleri (BIST için `.IS` son eki şart, örn. `THYAO.IS`)
- `symbols.crypto`: CoinGecko id'leri (ticker değil — örn. `bitcoin`, `ethereum`, `solana`)
- `telegram.bot_token` / `telegram.chat_id`: aşağıdaki adımlarla doldurun

### Telegram bot kurulumu

1. Telegram'da `@BotFather`'a `/newbot` yazın, botunuza isim verin — size bir **token** verecek.
2. Yeni botunuza Telegram'dan herhangi bir mesaj atın (örn. "merhaba").
3. Tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini açın, dönen JSON'da `"chat":{"id": ...}` alanındaki sayıyı **chat_id** olarak not edin.
4. Her ikisini de `config.yaml` içine yazın.

## Haber dosyası bırakma

Piyasa/hisse hakkında okuduğunuz haber, makale veya analist raporlarını
(`.pdf`, `.txt`, `.docx`) `news_inbox\` klasörüne bırakın. Günlük çalışma
sırasında bu dosyalar okunup rapora dahil edilir, ardından
`news_inbox\islenmis\` altına tarihli olarak arşivlenir (aynı haber ertesi gün
tekrar rapora girmez).

## Manuel test

```powershell
.venv\Scripts\python src\data_pipeline.py
```

Bu komut `logs\bundle_YYYY-MM-DD.json` dosyasını üretir — tüm sembollerin
teknik/temel/örüntü verilerini içerir. **Nihai Türkçe raporu üretmez** —
bu adım, günlük çalışan Claude Code rutini tarafından, bu JSON + haber
metinleri birlikte okunarak yazılır ve `src\send_text.py` ile Telegram'a
gönderilir.

## Zamanlama

Bu proje Windows Task Scheduler kullanmaz. Otomatik günlük çalışma, bir
Claude Code zamanlanmış rutini (`/schedule`) olarak kurulur — hafta içi
~08:45 İstanbul saatinde (BIST açılışından önce) tetiklenir ve şu adımları
izler:

1. `src\data_pipeline.py` çalıştırılır → JSON bundle üretilir
2. `news_inbox\`'taki bekleyen haberler okunur
3. JSON + haberler birlikte değerlendirilip Türkçe özet yazılır
4. `src\send_text.py <özet_dosyası>` ile Telegram'a gönderilir
5. `src\archive_news.py <dosyalar>` ile işlenen haberler arşivlenir

## Kapsam dışı

Alım/satım emri gönderilmez, backtesting motoru yoktur, veritabanı yoktur
(sadece log dosyası + JSON bundle), çoklu kullanıcı desteği ve web
dashboard yoktur.
