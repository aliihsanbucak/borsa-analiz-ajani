# Borsa Analiz Ajanı

BIST100 + ABD'nin en büyük 30 şirketi + kriptonun en büyük 50'si taranarak
her gün otomatik teknik + temel analiz üretip Telegram'a gönderen kişisel
bir araç. **Yatırım tavsiyesi vermez** — sadece nesnel gözlemler sunar.

Taranan ~180 sembolün tamamı rapora girmez: **şeffaf ve mekanik bir puanlama**
(bkz. `src/scoring.py`) ile en yüksek puanlı 30 tanesi rapora alınır. Bu
puanlama Claude'un öznel "bence iyi" seçimi DEĞİLDİR — sabit bir formülle
hesaplanır ve formül her raporun başında açıklanır (bkz. "Puanlama nasıl
çalışır?" bölümü).

## İçerdiği analiz yöntemleri

- **Teknik göstergeler**: RSI, MACD, SMA/EMA (20/50/200), Bollinger Bantları, hacim trendi
- **Mum formasyonları** (Steve Nison — *Japanese Candlestick Charting Techniques*): doji, çekiç, asılı adam, kayan yıldız, yutan boğa/ayı, sabah/akşam yıldızı — sadece BIST/ABD hisselerinde (OHLC verisi gerektirir)
- **Trend analizi** (John Murphy — *Technical Analysis of the Financial Markets*): Dow Teorisi tabanlı trend yönü, destek/direnç seviyeleri
- **Çoklu zaman dilimi teyidi** (Alexander Elder — *Trading for a Living*, "üç ekran" mantığı): haftalık trend + günlük RSI karşılaştırması
- **Temel analiz**: F/K, PD/DD, temettü verimi, kâr marjı, borç/özkaynak (sadece hisseler)
- **Değer yatırımı kriterleri** (Benjamin Graham & David Dodd — *Security Analysis*, Graham — *The Intelligent Investor*): "defansif yatırımcı" skoru (cari oran, borçluluk, kazanç istikrarı, temettü, F/K, F/K×PD/DD)
- **PEG oranı, büyüme kategorisi, içeriden sahiplik ve "iki dakikalık hikaye"** (Peter Lynch — *One Up On Wall Street*, *Beating the Street*)
- **Geçmiş örüntü karşılaştırması**: sembolün kendi geçmişinde benzer fiyat hareketlerini bulup, ardından tipik olarak ne olduğunu istatistiksel olarak raporlar
- **Haber duygu analizi**: `news_inbox/` klasörüne bıraktığınız PDF/txt/docx haberleri, günlük çalışma sırasında Claude tarafından okunup teknik/temel bulgularla birlikte yorumlanır
- **Finansal kalite metrikleri** (hisseler): FCF (serbest nakit akışı) getirisi, Net Borç/FAVÖK, beta, brüt/faaliyet kâr marjı, ciro büyümesi
- **WACC/DCF tabanlı adil değer aralığı** (bkz. `src/dcf.py`): özsermaye maliyeti CAPM ile (risksiz oran + beta×risk primi), borç maliyeti mümkünse şirketin gerçek faiz gideri/toplam borç oranından hesaplanır, 5 yıllık nakit akışı projeksiyonu + Gordon büyüme modeliyle terminal değer — ayı/baz/boğa senaryoları hem farklı büyüme tavanları hem farklı WACC ile hesaplanır. **Basitleştirilmiş bir modeldir, profesyonel bir DCF'in yerini tutmaz** — tüm varsayımlar raporda açıkça belirtilir (bkz. "WACC/DCF nasıl hesaplanıyor?"). DCF hesaplanamadığında (negatif FCF, eksik veri vb.) Lynch'in daha kaba "adil F/K = büyüme oranı" sezgiseline geri dönülür — hangisinin kullanıldığı raporda belirtilir.
- **Kripto seyrelme riski**: Piyasa Değeri/FDV (tam seyreltilmiş değerleme) oranı — düşükse ileride token unlock'larının satış baskısı yaratabileceğine dair not
- **Kripto evreni artık elle seçilmiş (curated)**: Daha önce "hangi coinler taranacak" sorusu CoinGecko'nun canlı piyasa değeri sıralamasıyla (`/coins/markets?order=market_cap_desc`) cevaplanıyordu. Bu, gerçek/tanınan kripto paraların yanına stablecoin'leri (`dai`, `usds`, `paypal-usd`), tokenize edilmiş RWA fonlarını (`blackrock-usd-institutional-digital-liquidity-fund`, `tether-gold`, `hashnote-usyc`), borsa token'larını (`okb`, `leo-token`, `whitebit`) ve çok yeni/spekülatif ürünleri (`figure-heloc`, `pump-fun`, `aster-2`, `memecore`) de karıştırabiliyordu — canlı bir çalışmada bu tür girdiler raporun top-30'una kadar girdi ve kullanıcı geri bildirimiyle fark edildi (27 Ağustos 2026). Düzeltme: `symbols.crypto_count` artık `src/data_crypto.py`'deki `CURATED_TOP_COINS` sabit, elle seçilmiş ~50 kripto para listesinden (bitcoin, ethereum, solana, chainlink, aave vb. — genel olarak tanınan projeler) ilk N tanesini kullanıyor; CoinGecko sadece bu sabit listedeki coinlerin fiyat/temel verisini zenginleştirmek için kullanılıyor, HANGİ coinlerin taranacağına karar vermiyor. BIST/ABD evreninin `config.yaml`'da elle seçilmiş olmasıyla aynı prensip.
- **Kripto veri dayanıklılığı**: CoinGecko'nun ücretsiz erişiminde ara sıra geçici bağlantı sorunları (SSL/zaman aşımı) yaşanabiliyor — bu yüzden tüm CoinGecko çağrıları 3 kez, artan bekleme süresiyle otomatik tekrar deniyor (bkz. `src/data_crypto.py`). **Gerçek kök neden (27 Ağustos 2026'da canlı teşhis edildi)**: bazı günler kripto verisi tamamen gelmiyor çünkü CoinGecko'ya özgü bir sorun değil — bu ağda `api.coingecko.com`, `api.binance.com`, `api.exchange.coinbase.com`, `api.kraken.com` ve `min-api.cryptocompare.com` gibi kripto borsası/veri API'si kategorisindeki TÜM alan adları aynı anda aynı hatayla (SSL: WRONG_VERSION_NUMBER) engelleniyor — muhtemelen ISP/DPI seviyesinde bir engelleme (Türkiye'de kripto borsalarına erişim kısıtlamaları bilinen bir durum). Kripto-dışı finans siteleri (Yahoo Finance, Wikipedia, FRED) bu sırada sorunsuz çalışıyor. Bu yüzden Binance'i "bağımsız bir yedek" olarak eklemek yeterli olmadı — aynı anda o da engellenmiş olabiliyor. Gerçek çözüm: **Yahoo Finance'in kendisi kripto ticker'larını da destekliyor** (örn. `BTC-USD`) ve bu ağda engellenmemiş — bu proje zaten BIST/ABD hisseleri için aynı yfinance altyapısını güvenilir şekilde kullanıyor. Dayanıklılık sırası: CoinGecko → Binance (ucuz, bazen işe yarar) → **Yahoo Finance** (`COIN_ID_TO_YAHOO_TICKER` statik eşlemesi, canlı doğrulanmış ~50 coin). CoinGecko'nun snapshot'ı (piyasa değeri sıralaması, ATH%, FDV) da tamamen erişilemezse, en azından piyasa değeri/güncel fiyat Yahoo'nun `.info`'sundan kurtarılır — CoinGecko kalitesiyle birebir aynı değil ama veri hiç gelmemesinden çok daha iyi.
- **Karşıt yatırım (contrarian) taraması** (Anthony M. Gallea & William Patalon III — *Contrarian Investing*, Türkçe: *Karşıt Yatırım*, Scala Yayıncılık): kitabın mekanik "gözden düşmüş hisse" kurallarına uyan adaylar, mevcut top-30 evreninin DIŞINDA da (S&P 500'ün tamamı dahil) taranır — bkz. aşağıdaki "Karşıt Yatırım Taraması" bölümü.
- **Makro bağlam ve küresel likidite**: ABD 10 yıllık tahvil getirisi, dolar endeksi (DXY), USD/TRY, VIX, altın, petrol; ayrıca Fed fonlama faizi, Fed toplam bilançosu, Hazine Genel Hesabı (TGA), gecelik ters repo (RRP), M2 para arzı (FRED'in key gerektirmeyen CSV endpoint'inden) — raporun başında kısa bir özet olarak
- **Tez-bozucu risk notu**: rapora giren her sembol için, o günkü veride görülen en belirgin zayıf nokta/kırılganlık tek cümleyle belirtilir
- **Genel piyasa haberleri** (bkz. `src/news_feeds.py`): UzmanCoin (kripto) ve Investing.com Türkiye (genel piyasa) RSS akışlarından son 24 saatin başlıkları çekilir; rapordaki bir sembolle ilgili görünen bir başlık varsa tek cümlelik bir not olarak eklenir — bu başlıklar **doğrulanmamış/ham veridir** (kullanıcının kendi kaynak hiyerarşisinde "Seviye 4"), birincil kaynaktan teyit edilmeden gerçekmiş gibi sunulmaz

## WACC/DCF nasıl hesaplanıyor?

`src/dcf.py` içinde tanımlı, tüm varsayımları açık bir model:

- **Özsermaye maliyeti**: CAPM ile = risksiz oran (ABD 10 yıllık tahvil getirisi) + beta × özsermaye risk primi (sabit %5 varsayım, Damodaran'ın uzun dönemli ABD tahminleriyle uyumlu bir literatür değeri)
- **Borç maliyeti**: mümkünse şirketin gerçek faiz gideri/toplam borç oranından (yfinance `income_stmt`), yoksa risksiz oran + sabit %2 kredi marjı varsayılır (bu durumda notta belirtilir)
- **WACC**: özsermaye/borç ağırlıklarına göre birleştirilir
- **Nakit akışı projeksiyonu**: 5 yıl + %2.5 sabit terminal büyüme (Gordon büyüme modeli)
- **Ayı/Baz/Boğa**: hem büyüme tavanı (Ayı ≤%10, Baz ≤%18, Boğa ≤%28) hem WACC (Ayı: +%1.5, Boğa: -%1.5) senaryo bazında değişir — bu, ilk testte bulunan bir hatayı düzeltmek için gerekliydi (çok yüksek ham büyüme oranlarında üç senaryo aynı tavana sıkışıp özdeş sonuç üretiyordu)

**Önemli sınırlama**: BIST hisseleri için de ABD doları risksiz oranı kullanılıyor (TL cinsinden güvenilir/ücretsiz bir risksiz oran serisi yok) — bu, BIST DCF çıktılarının ABD hisselerine göre daha kaba bir yaklaşım olduğu anlamına gelir, rapor bunu her BIST hissesi için ayrıca not düşer.

## Puanlama nasıl çalışır?

`src/scoring.py` içinde tanımlı, tamamen mekanik bir formül (`SCORING_EXPLANATION`
sabitinde tam metni var):

- **Hisseler (BIST/ABD)**: Graham defansif skoru (%35) + Lynch PEG cazibesi (%25)
  + kazanç büyümesi (%20) + geçmiş örüntü sonrası ortalama getiri (%20)
- **Kripto**: geçmiş örüntü sonrası ortalama getiri (%60) + piyasa değeri sıralaması (%40)

Eksik veri olan bileşenler formülden çıkarılır, kalan bileşenler üzerinden
ağırlıklar yeniden normalize edilir. Tüm evren (~180 sembol) her gün taranır,
en yüksek puanlı `top_n_report` (varsayılan 30) tanesi rapora girer — geri
kalanı atlanmaz, sadece o günün raporunda gösterilmez.

## Karşıt Yatırım Taraması

`src/contrarian.py`, Anthony M. Gallea & William Patalon III'ün *Contrarian
Investing: Buy and Sell When Others Don't and Make Money Doing It* kitabından
(Türkçe: *Karşıt Yatırım*, Scala Yayıncılık) çıkarılan, tamamen mekanik/kural
tabanlı bir "gözden düşmüş hisse" tarama sistemidir. Kitabın kendisi kullanıcı
tarafından sağlanan fotoğraflı bir kopyadan okunup kuralları çıkarıldı; sadece
kural setleri koda döküldü, kitabın metni projeye dahil edilmedi.

**Birincil filtre** (ikisi de sağlanmalı):
- Fiyat, 52 haftalık en yüksek seviyesinden en az %50 düşmüş olmalı
- Fiyat > 5 (birim para) ve piyasa değeri > 150 milyon $ olmalı (mikro-kap/düşük likidite dışlaması)

**Teyit** (aşağıdaki 4 oranından en az 2'si sağlanmalı): F/K < 12, F/DD < 1.0,
F/SNA (Fiyat/Serbest Nakit Akışı) < 10, F/S (Fiyat/Satışlar) < 1.0.

3-4 kritere birden uyan adaylar için kitabın "dikkatle incelenmeli, aşırı
zayıflamış/iflasa yakın olabilir" uyarısı rapora eklenir. Kitapta ayrıca
"içeriden $120.000+ alım" ve "dışarıdan bilgili yatırımcı %5 alımı" gibi
teyit sinyalleri de var, ama bunlar ücretsiz yfinance verisiyle
otomatikleştirilemiyor (sadece anlık sahiplik yüzdesi var, işlem bazlı veri
yok) — bilinçli olarak kapsam dışı bırakıldı. Kitabın risk yönetimi kuralları
(tek pozisyon ≤ portföyün %5'i, tek sektör ≤ %20, %25 zarar-stopu, %30 kârdan
sonra iz-süren stop) rapora her adaydan bağımsız, bölüm sonunda BİR KEZ genel
eğitici not olarak eklenir.

**Taranan evren**: Bu tarama mevcut top-30 puanlama evreniyle SINIRLI DEĞİLDİR:
- Zaten tam işlenen BIST100+ABD30 sembolleri için ekstra API çağrısı olmadan (mevcut veriyle) taranır
- ABD tarafında ayrıca **S&P 500'ün tamamı** (Wikipedia'dan `pandas.read_html` ile çekilir, ~503 sembol, ücretsiz/key gerektirmez) iki aşamalı olarak taranır: önce ucuz bir fiyat-geçmişi filtresi (52 hafta %50 düşüş), sonra sadece bunu geçenler için pahalı tam temel veri çekimi. Bu, toplam pipeline süresini ~35-40 dakikaya çıkarır.
- **BIST tarafında böyle bir genişleme yok**: BIST'in tam şirket listesi için temiz/güvenilir bir ücretsiz kaynak bulunamadı (İngilizce Wikipedia'daki BIST_100 sayfasında sadece endeks seviye geçmişi var, şirket tablosu yok; Türkçe Wikipedia'da sayfa mevcut değil). Bu yüzden BIST tarafı mevcut best-effort BIST100 listesiyle sınırlı kalıyor.

Sonuç, JSON bundle'da `contrarian_candidates` (liste), `contrarian_book_citation`
ve `contrarian_rule_explanation` alanlarında taşınır; rapor sentezi sırasında
Claude, top-30 bölümünden ayrı, "KARŞIT YATIRIM ADAYLARI" başlıklı bir bölümde
bunu açıklar — burada da sembol seçimi Claude'a değil, Python'daki mekanik
kurala aittir.

## Kurulum

```powershell
cd "C:\Users\Ali İhsan Bucak\borsa-analiz-ajani"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config\config.example.yaml config\config.yaml
```

`config\config.yaml` dosyasını açıp:
- `symbols.bist`: BIST100 best-effort listesi (zaten dolu geliyor — endeks
  bileşimi periyodik değiştiği için ara sıra kontrol edin, yanlış/eski bir
  sembol pipeline'ı bozmaz, sadece atlanır)
- `symbols.us`: ABD'nin piyasa değerine göre en büyük ~30 şirketi (zaten dolu
  geliyor, best-effort)
- `symbols.crypto_count`: `src/data_crypto.py`'deki `CURATED_TOP_COINS` (elle
  seçilmiş, tanınan kripto paralar — bkz. aşağıdaki not) listesinden kaç
  tanesinin taranacağı
- `top_n_report`: günlük raporda detaylı gösterilecek en yüksek puanlı sembol sayısı (varsayılan 30)
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

Bu komut `logs\bundle_YYYY-MM-DD.json` dosyasını üretir — tüm evrenin (~180
sembol) taranmasından sonra en yüksek puanlı `top_n_report` (varsayılan 30)
sembolün teknik/temel/örüntü verilerini, ayrıca `universe_size`,
`errored_symbol_count`, `scoring_explanation`, `contrarian_candidates`,
`contrarian_book_citation` ve `contrarian_rule_explanation` alanlarını içerir.
**Nihai Türkçe raporu üretmez** — bu adım `run_daily.ps1` tarafından çağrılan
yerel Claude Code CLI tarafından, bu JSON + haber metinleri birlikte okunarak
yazılır ve `src\send_text.py` ile Telegram'a gönderilir. ~180 sembollük ana
evren + karşıt yatırım taraması için S&P 500'ün tamamının iki aşamalı
taranması (bkz. "Karşıt Yatırım Taraması") nedeniyle bu adım yaklaşık 35-40
dakika sürebilir.

## Zamanlama

Otomatik günlük çalışma tamamen yereldir (bulut ajanı DENENDİ ama bu
projenin ihtiyaç duyduğu finans API'lerine (Yahoo Finance, CoinGecko)
bulut ortamının ağ politikası izin vermediği için terk edildi):

- **Windows Task Scheduler** görevi: `BorsaAnalizAjani` (hafta içi 11:00'de
  çalışır — BIST 10:00'da açıldığı için bir saat sonra veri oturmuş olsun diye
  bu saat seçildi; `Get-ScheduledTask -TaskName BorsaAnalizAjani` ile kontrol
  edilebilir)
- Görev, `run_daily.ps1` script'ini çalıştırır; bu script sırasıyla:
  1. `src\data_pipeline.py`'yi çalıştırıp JSON bundle üretir
  2. Yerel **Claude Code CLI**'yi (`claude -p ...`) headless modda çağırıp
     JSON + `news_inbox\`'taki bekleyen haberleri okutur, açıklayıcı/eğitici
     bir Türkçe özet yazdırır (`logs\rapor_YYYY-MM-DD.txt`)
  3. `src\send_text.py` ile Telegram'a gönderir
  4. İşlenen haber dosyalarını `src\archive_news.py` ile arşivler

Bilgisayarın o saatte açık ve oturumun aktif olması gerekir (uyku modunda
değilse Task Scheduler yine de "wake to run" ile uyandırmayı dener, ama bu
varsayılan olarak kapalıdır — gerekirse görev özelliklerinden açılabilir).

Claude Code CLI kurulumu (Node.js + `npm install -g @anthropic-ai/claude-code`)
zaten bu kurulum sırasında yapıldı ve mevcut Claude aboneliğinizle
oturum açık durumda; ekstra API ücreti gerekmez.

Logları kontrol etmek için: `logs\wrapper_YYYY-MM-DD.log` (script akışı) ve
`logs\run_YYYY-MM-DD.log` (Python pipeline detayları).

## Neden on-chain analiz, KAP belge taraması, SQL/Excel yok?

Kapsamlı bir kurumsal yatırım araştırma çerçevesinde bulunması gereken bazı
bölümler, ilk değerlendirmede "imkansız" diye çok çabuk elenmişti — tekrar
bakılınca WACC/DCF ve TGA/RRP gibi bazıları aslında ücretsiz ve güvenilir
şekilde yapılabiliyordu (yukarıda eklendi). Gerçekten kapsam dışı kalanlar
ve nedenleri:

- **On-chain analiz (SOPR, MVRV, whale hareketleri, exchange flow vb.)**:
  Glassnode, CryptoQuant, Dune Analytics, Token Terminal gibi kaynaklar bu
  düzeyde veriyi genelde ücretli abonelikle sağlıyor; ücretsiz/kişisel bir
  araçta güvenilir şekilde otomatikleştirilemedi.
- **KAP belge taraması (özel durum açıklamaları)**: Yapılandırılmış, ücretsiz
  bir API yok — güvenilir bir entegrasyon için özel bir scraping/parsing
  altyapısı kurulması gerekir, bu ayrı bir proje büyüklüğünde. (SEC EDGAR'ın
  kendisi aslında ücretsiz bir XBRL API'sine sahip, ama bu proje için ayrıca
  entegre edilmedi — yfinance'in `income_stmt`'i şimdilik yeterli veriyi
  sağlıyor.)
- **TCMB politika faizi anlık takibi**: Doğrudan güncel değer için ücretsiz/
  basit bir API yok (FRED'de de TCMB serisi bulunmuyor, FRED entegrasyonu
  sadece ABD tarafı - Fed/TGA/RRP/M2 - için geçerli).
- **SQL veri ambarı / Excel dashboard**: Bu araç Telegram'a günlük bir metin
  özeti göndermek üzere tasarlandı; tarihsel veri saklama ve portföy takibi
  için ayrı bir araç (Google Sheets/Excel + SQL) kurmak isterseniz bu ayrı
  bir proje olarak ele alınabilir.

Ayrıca kullanıcının paylaştığı bir kaynak listesi (Investing.com Türkiye,
UzmanCoin, CoinGlass, KAP, Bulls Yatırım) canlı olarak test edildi:

- **UzmanCoin ve Investing.com Türkiye**: gerçek, ücretsiz RSS akışları var
  (`/feed/` ve `/rss/news.rss`) — **eklendi** (bkz. `src/news_feeds.py`)
- **CoinGlass**: eski ücretsiz API endpoint'i canlı testte `"deprecated"`
  hatası verdi; güncel API'si kayıt/API key gerektiriyor — kullanıcı
  şimdilik istemedi, eklenmedi (isterseniz ücretsiz bir CoinGlass API key
  alıp paylaşırsanız OI/funding/liquidation verisi sonradan eklenebilir)
- **KAP**: modern bir Next.js tek sayfa uygulaması, canlı testte belgelenmiş
  bir genel API bulunamadı — iç API'lerini reverse-engineer etmek scraping
  sayılır, yapılmadı
- **Bulls Yatırım**: canlı testte bot koruması (WAF) tespit edildi
  (405/anti-bot cookie'leri) — scraping denenmedi

## Kapsam dışı

Alım/satım emri gönderilmez, backtesting motoru yoktur, veritabanı yoktur
(sadece log dosyası + JSON bundle), çoklu kullanıcı desteği ve web
dashboard yoktur.
