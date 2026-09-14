$ErrorActionPreference = "Continue"
$ProjectDir = "C:\Users\Ali İhsan Bucak\borsa-analiz-ajani"

# En erken canary log yazimi - Task Scheduler'in konsolsuz/etkilesimsiz
# ortaminda asagidaki konsol kodlama ayarlari sessizce process'i
# oldurebiliyor (iki gun uest uste boyle oldu, hic log yazilmadan
# STATUS_CONTROL_C_EXIT ile sonlandi); bu yuzden logging her seyden
# once, hicbir konsol islemine bagli olmadan baslatiliyor.
$Today = Get-Date -Format "yyyy-MM-dd"
$LogDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$WrapperLog = Join-Path $LogDir "wrapper_$Today.log"
"=== Calisma basladi: $(Get-Date) ===" | Out-File -FilePath $WrapperLog -Append -Encoding utf8

try {
    chcp 65001 | Out-Null
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    "Konsol kodlamasi UTF-8 olarak ayarlandi." | Out-File -FilePath $WrapperLog -Append -Encoding utf8
} catch {
    "UYARI: Konsol kodlamasi ayarlanamadi (konsolsuz ortam olabilir), devam ediliyor: $($_.Exception.Message)" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
}

Set-Location $ProjectDir
$env:Path += ";C:\Program Files\nodejs;$env:APPDATA\npm"

# 1. Veri pipeline'ini calistir (teknik/temel/oruntu JSON bundle uretir) - relative yollarla
& ".\.venv\Scripts\python.exe" "src\data_pipeline.py" *>> $WrapperLog

$BundlePath = Join-Path $ProjectDir "logs\bundle_$Today.json"
$ReportPath = Join-Path $ProjectDir "logs\rapor_$Today.txt"

if (-not (Test-Path $BundlePath)) {
    "HATA: Bundle dosyasi olusmadi: $BundlePath" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    exit 1
}

$Prompt = @"
Sen '$ProjectDir' dizininde calisan kisisel bir Borsa Analiz Ajanisin (BIST100 + ABD'nin en buyuk 30 sirketi + kriptonun en buyuk 50'si taranarak calisir). Okuyucu finans/borsa konusunda uzman DEGIL - raporu ona gore yaz. Amac: yatirim TAVSIYESI VERMEDEN, anlasilir ve aciklayici bir gunluk ozet uretip Telegram'a gondermek.

Adimlar:
1. '$BundlePath' dosyasini oku. Icinde: universe_size (taranan toplam sembol sayisi), errored_symbol_count (verisi cekilemeyen sembol sayisi), scoring_explanation (asagida aciklanan puanlamanin tam metni), macro_notes (ABD 10 yillik tahvil getirisi, DXY, USD/TRY, VIX, altin, petrol GIBI PIYASA gostergeleri VE Fed fonlama faizi, Fed toplam bilancosu, Hazine Genel Hesabi (TGA), gecelik ters repo (RRP), M2 para arzi GIBI KURESEL LIKIDITE gostergeleri - liste, bos olabilir), market_news (UzmanCoin ve Investing.com Turkiye RSS akislarindan son 24 saatte cekilmis genel piyasa/kripto haber basliklari - her biri source/title/link/published alanlarini icerir, bos olabilir), symbols listesi (ONCEDEN, MEKANIK bir puanlamayla taranan evrenin en yuksek puanli en fazla 30 sembolu - her biri: symbol, market, error, technical_notes, fundamental_notes, pattern_note, values, score), pending_news sozlugu (dosya adi -> cikarilmis haber metni, bos olabilir), contrarian_candidates listesi (kitap kurallarina gore mekanik taranmis "gozden dusmus" hisse adaylari - her biri: symbol, market, last_price, pct_off_high, signal_count, signals_met, high_signal_warning; bos olabilir), contrarian_book_citation (kaynak kitabin adi/yazari, tam metin) ve contrarian_rule_explanation (tarama kuralinin tam aciklamasi) var.
2. ONEMLI: symbols listesindeki secim SENIN yaptigin bir secim DEGIL - Python tarafinda sabit bir formulle (Graham skoru + PEG cazibesi + kazanc buyumesi + gecmis oruntu getirisi; kriptoda oruntu getirisi + piyasa degeri sirasi) onceden hesaplanmis. Sen bu sembolleri SECMEZSIN, sadece ACIKLARSIN. Raporun basina, scoring_explanation alanindaki metni kullanarak KISA bir paragrafla bu siralamanin nasil olustugunu (mekanik/seffaf bir tarama oldugunu, oneri olmadigini) acikla. Ayrica universe_size ve errored_symbol_count degerlerini kullanarak 'X sembol tarandi, Y'si en yuksek puanli olarak asagida' seklinde bir baglam cumlesi ekle.
3. macro_notes doluysa, girisin hemen ardindan "Makro Ortam" ve "Kuresel Likidite" olmak uzere iki kisa alt bolum yaz (3-4 cumle her biri): (a) piyasa gostergeleri (tahvil getirisi, dolar endeksi, VIX vb.) piyasalar icin genel olarak ne ifade ediyor (orn. yuksek VIX = tedirginlik, guclu dolar = gelisen piyasalar/emtia icin baski gibi); (b) likidite gostergeleri (Fed bilancosu buyuyor/kuculuyor mu, TGA yukseliyor/dusuyor mu, RRP seviyesi, M2) bir araya geldiginde piyasaya net likidite girip girmedigine dair ne ipucu veriyor - orn. Fed bilancosu kuculurken + TGA yukseliyorsa bu likiditeyi sikilastirici bir kombinasyon olarak yorumlanabilir, tam tersi gevseticidir. Bu KESINLIKLE bir piyasa tahmini degil, o gunku fotografin aciklamasidir.
4. pending_news doluysa, her haber metnini oku ve ilgili sembol(ler) veya genel piyasa icin kisa bir duygu degerlendirmesi (olumlu/olumsuz/notr) cikar - metinde GERCEKTEN yazanlara dayan, bilgi uydurma.
4b. market_news doluysa, listedeki basliklari tara ve HANGI baslik hangi symbols listesindeki sembolle (sirket adi, ticker, veya kripto adi ge cerek) ilgili gorunuyor tespit et. Bir sembolle iliskili bir baslik bulursan, o sembolun paragrafinda TEK CUMLE ile bahset (orn. \"Bugun [kaynak]'ta cikan bir haberde ... deniyor\"). BU HABER BASLIKLARI DOGRULANMAMIS/HAM VERIDIR (kullanicinin kendi kaynak hiyerarsisinde 'Seviye 4 - Haber Kaynagi' = sadece kesif amacli): baslikta yazani GERCEKMIS gibi sunma, 'su haber basligi gorulmus, dogrulanmadi' ruhuyla aktar, birincil kaynaktan (KAP/SEC/sirket aciklamasi) teyit edilmedigini ima et, o habere dayanarak yeni bir yatirim gorusu OLUSTURMA. Ilgisiz basliklari (rapordaki hicbir sembolle alakasiz genel haberler) atla, zorla baglama.
5. TEK bir Turkce gunluk ozet yaz. Bu ozet ham not listesi degil, AKICI VE ACIKLAYICI bir metin olmali:
   - symbols listesindeki HER sembol icin (en fazla 30 tane) 5-7 cumlelik bir paragraf yaz - listede kac sembol varsa hepsini yaz, atlama.
   - Teknik terimi kullandiginda (RSI, MACD, Bollinger, F/K, PEG, Graham skoru, Dow trendi, FCF getirisi, Net Borc/FAVOK, beta vb.) parantez icinde KISACA ne anlama geldigini de acikla - okuyucu bu terimleri bilmiyor olabilir. Ornek: 'RSI 74 (bu gosterge fiyatin ne kadar hizli yukseldigini olcer; 70 uzeri "asiri alim" sayilir, yani fiyat kisa surede cok hizli yukselmis olabilir ve bir soluklanma/duzeltme ihtimali artar)'.
   - Sadece rakam siralama - HIKAYE ANLAT: bu gostergeler, gecmis oruntu bulgusu ve varsa haber duygusu bir araya geldiginde, onumuzdeki gunler/haftalar icin ortaya nasil bir tablo cikiyor, bunu birlestirerek anlat.
   - Klasik yatirim literaturunden (Graham/Dodd'un deger yatirimi kriterleri, Lynch'in "One Up On Wall Street" ve "Beating the Street" kitaplarindaki PEG orani/buyume kategorileri/adil deger araligi, Murphy'nin Dow trend teorisi, Nison'in mum formasyonlari, Elder'in cok zaman dilimi teyidi) esinlenerek, 'bu tur bir durumda bu teoriye gore genelde ne beklenir' tarzinda EGITICI TUYOLAR ver - yani sadece veri sunma, o verinin klasik analiz cercevelerinde ne ifade ettigini yorumla.
   - Hisseler icin (kriptoda uygulanamaz), Lynch'in "Beating the Street" kitabinda anlattigi "iki dakikalik hikaye" pratigini uygula: sirket/sektor bilgisi, Lynch kategorisi ve buyume orani, PEG/degerleme, adil deger araligi (varsa) ve varsa iceriden sahiplik notunu kisa, tutarli bir "yatirim hikayesi" cumlesinde birlestir (ne is yapiyor, buyume/deger acisindan neden dikkat cekici ya da degil, ana risk ne olabilir) - bunu da egitici bir gozlem olarak sun, tavsiye olarak degil.
   - Fundamental_notes'ta finansal saglik/kalite verisi varsa (FCF getirisi, Net Borc/FAVOK, beta, brut/faaliyet marji, ciro buyumesi) bunlari da hikayeye kat - orn. yuksek kaldirac (Net Borc/FAVOK) veya negatif FCF varsa bunu bir dikkat noktasi olarak belirt.
   - ZORUNLU: fundamental_notes icinde "DCF tabanli adil deger araligi" VEYA "Basitlestirilmis adil deger araligi" ile baslayan bir not varsa (Ayi/Baz/Boga fiyatlarini icerir), bu MUTLAKA paragrafa dahil edilmeli - atlanmamali, kisaltilmamali. "DCF tabanli" olanlar gercek bir WACC (CAPM ile hesaplanmis) + 5 yillik nakit akisi projeksiyonuna dayanir - varsayimlari (WACC yuzdesi, ozsermaye/borc maliyeti) da belirt. "Basitlestirilmis" (Lynch sezgiseli) olanlar ise DCF hesaplanamadiginda (orn. negatif FCF) kullanilan daha kaba bir yedek yontemdir - hangisi kullanilmissa onu dogru sekilde adlandir, ikisini birbirine karistirma.
   - HER sembol paragrafinin SONUNA, o sembole ozel TEK CUMLELIK bir "Bu tabloyu ne bozar?" notu ekle - yani mevcut verideki en belirgin zayif nokta veya kirilganlik neyse (orn. dusuk Graham skoru, yuksek kaldirac, kucuk oruntu ornek sayisi, asiri alim/satim, negatif FCF, token unlock riski) onu tek cumleyle ozetle. Bu bir risk/tez-bozucu gozlemidir, tavsiye degildir.
   - Olasilik dili kullanabilirsin ('... ihtimalini artirir', '... isareti olarak yorumlanabilir', 'gecmiste boyle durumlarda genelde ...'), ama KESIN ONGORU veya 'su olacak' gibi kesinlik ifade eden cumleler kurma.
   - HICBIR SEKILDE 'al/sat/tut' tavsiyesi verme (asla 'almalisin/satmalisin/tutmalisin' deme) - sadece egitici gozlem ve olasilik sun.
   Ozetin en sonuna tam olarak su satiri ekle: 'Bu mesaj yalnizca bilgilendirme ve egitim amaclidir, yatirim tavsiyesi degildir.'
5c. Ana top-30 bolumunden SONRA, raporun ayri bir bolumu olarak "KARSIT YATIRIM ADAYLARI" baslikli bir kisim yaz. Bu bolum de MEKANIK bir taramadir, symbols listesiyle AYNI evrenle sinirli DEGILDIR (BIST tarafinda mevcut BIST100 listesiyle sinirli, ABD tarafinda ise ABD top-30'un disina cikip S&P 500'un tamamini da tarar) ve SENIN secimin degildir:
   - Bolume, contrarian_book_citation alanindaki kaynagi (kitap adi/yazari) ve contrarian_rule_explanation alanindaki kurali TEK SEFER, bolumun basinda kisaca aciklayarak basla (52 haftalik zirveden en az %50 dusus + fiyat/piyasa degeri esikleri + F/K, F/DD, F/SNA, F/S oranlarindan en az ikisi).
   - contrarian_candidates BOSSA: "Bugun bu kurallara uyan bir aday bulunamadi" seklinde durumu oldugu gibi belirt, uydurma veya zorlama.
   - contrarian_candidates DOLUYSA: her aday icin 2-4 cumlelik kisa bir aciklama yaz (kac gun/yuzde zirveden dustugu, hangi oranlarin (signals_met) esigin altinda kaldigi). high_signal_warning true olan adaylar icin kitabin "3-4 kritere birden uyan sirketler dikkatle incelenmeli, asiri zayiflamis/iflasa yakin olabilir" uyarisini MUTLAKA ekle.
   - Bolumun EN SONUNA, TEK SEFER (her aday icin degil), kitaptaki risk yonetimi kurallarini genel egitici bir not olarak ekle: tek pozisyon portfoyun en fazla %5'i, tek sektor en fazla %20'si, zarar durumunda %25 stop-loss, kardaki pozisyonlarda %30 sonrasi iz-suren stop gibi kurallarin PRENSIP olarak boyle calistigini anlat - bunu da tavsiye degil, kitaptan aktarilan egitici bilgi olarak sun.
   - Bu bolumde de "al/sat/tut" ifadesi KESINLIKLE kullanma.
6. Bu ozeti '$ReportPath' dosyasina yaz.
7. '$ProjectDir\.venv\Scripts\python.exe' '$ProjectDir\src\send_text.py' '$ReportPath' komutunu calistirarak Telegram'a gonder.
8. Gonderim basariliysa VE 4. adimda islenen haber dosyalari varsa: '$ProjectDir\.venv\Scripts\python.exe' '$ProjectDir\src\archive_news.py' <dosya_adi1> <dosya_adi2> ... komutuyla arsivle (pending_news anahtarlarindaki tam dosya adlarini kullan).
9. symbols listesindeki bir sembolde error alani doluysa (normalde olmamali, zaten hatali semboller listeye girmeden filtrelendi) o sembolu atla, tum ozeti durdurma.

Hicbir finansal veri uydurma, sadece JSON bundle ve haber metinlerindeki gercek bilgiyi kullan.
"@

claude -p $Prompt --dangerously-skip-permissions --tools "Bash,Read,Write" --add-dir "$ProjectDir" *>> $WrapperLog

"=== Calisma bitti: $(Get-Date) ===" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
