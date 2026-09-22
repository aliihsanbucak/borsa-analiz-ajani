# -RaporSadece: veri pipeline'ini atla, bugunun mevcut bundle'i ile raporu yeniden
# uret ve gonder. Rapor bicimi degistiginde ayni gunu yeniden yazdirmak icin var;
# pipeline aynen calissa bundle'i bulup "zaten var" diye 2 ile cikardi.
param([switch]$RaporSadece)

$ErrorActionPreference = "Continue"
# Script kendi bulundugu klasoru kullanir; makineden makineye tasininca kirilmaz.
$ProjectDir = $PSScriptRoot

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

# Gorev powershell.exe (PS 5.1) ile calisiyor; orada "*>>" yonlendirmesi varsayilan
# olarak UTF-16LE yazar. Wrapper logu UTF-8 baslayip claude ciktisindan sonra
# okunamaz hale geliyordu (grep dosyayi ikili sanip pes ediyordu).
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'

# Ariza sessiz kalmasin: rapor uretilemeyen her cikista Telegram'a kisa bir not
# birak. En iyi caba - gonderilemezse loglanir, asil cikis kodu bozulmaz.
function Send-ArizaUyarisi([string]$Mesaj) {
    "ARIZA UYARISI: $Mesaj" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    try {
        $PyYolu = Join-Path $ProjectDir ".venv\Scripts\python.exe"
        $AlertYolu = Join-Path $ProjectDir "src\send_alert.py"
        & $PyYolu $AlertYolu $Mesaj *>> $WrapperLog
    } catch {
        "UYARI: Ariza bildirimi gonderilemedi: $($_.Exception.Message)" |
            Out-File -FilePath $WrapperLog -Append -Encoding utf8
    }
}

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

# --- KEEP_AWAKE_BEGIN ---
# Calisma sirasinda makine uyumasin. 22 Eylul'de gorev 11:04'te basladi, makine
# 11:11'de "Hibernate from Sleep - Fixed Timeout" ile uyudu; calisan bir pipeline
# boyle sessizce olur. ES_CONTINUOUS cagiran thread icin gecerli ve script
# bitene kadar surer. Basarisiz olursa sadece loglanir, akis bozulmaz.
$KeepAwakeAktif = $false
try {
    if (-not ("BorsaUyanikKal" -as [type])) {
        Add-Type -Namespace "" -Name "BorsaUyanikKal" -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
"@
    }
    # ES_CONTINUOUS (0x80000000) | ES_SYSTEM_REQUIRED (0x00000001)
    $Onceki = [BorsaUyanikKal]::SetThreadExecutionState([uint32]"0x80000001")
    if ($Onceki -ne 0) {
        $KeepAwakeAktif = $true
        "Uyku engeli kuruldu (calisma boyunca makine uyumayacak)." | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    } else {
        "UYARI: Uyku engeli kurulamadi (SetThreadExecutionState 0 dondu)." | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    }
} catch {
    "UYARI: Uyku engeli kurulamadi, devam ediliyor: $($_.Exception.Message)" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
}

function Restore-UykuAyari {
    if ($KeepAwakeAktif) {
        try {
            # ES_CONTINUOUS tek basina: engeli kaldirir.
            [BorsaUyanikKal]::SetThreadExecutionState([uint32]"0x80000000") | Out-Null
            "Uyku engeli kaldirildi." | Out-File -FilePath $WrapperLog -Append -Encoding utf8
        } catch { }
    }
}
# --- KEEP_AWAKE_END ---

# --- NETWORK_READY_WAIT_BEGIN ---
# StartWhenAvailable, bilgisayar acilir acilmaz gorevi baslatabilir. Windows'un
# "ag var" sinyali DNS ve internetin gercekten hazir oldugu anlamina gelmez.
$NetworkHost = "query2.finance.yahoo.com"
$NetworkWaitLimit = [TimeSpan]::FromMinutes(15)
$NetworkRetrySeconds = 20
$NetworkWaitStarted = Get-Date

while ($true) {
    try {
        $Addresses = [System.Net.Dns]::GetHostAddresses($NetworkHost)
        if ($Addresses.Count -gt 0) {
            $WaitedSeconds = [int]((Get-Date) - $NetworkWaitStarted).TotalSeconds
            "Ag hazir: $NetworkHost cozuldu ($($Addresses[0].IPAddressToString)); bekleme suresi $WaitedSeconds sn." |
                Out-File -FilePath $WrapperLog -Append -Encoding utf8
            break
        }
    } catch {
        $ElapsedSeconds = [int]((Get-Date) - $NetworkWaitStarted).TotalSeconds
        "Ag henuz hazir degil ($ElapsedSeconds sn): $($_.Exception.Message)" |
            Out-File -FilePath $WrapperLog -Append -Encoding utf8
    }

    if (((Get-Date) - $NetworkWaitStarted) -ge $NetworkWaitLimit) {
        "HATA: Ag 15 dakika icinde hazir olmadi; veri pipeline'i baslatilmadi." |
            Out-File -FilePath $WrapperLog -Append -Encoding utf8
        Send-ArizaUyarisi "Borsa Analiz Ajani: ag 15 dakika icinde hazir olmadi (Yahoo DNS cozulemedi). Bugun rapor uretilemedi."
        "=== Calisma bitti (ag zaman asimi): $(Get-Date) ===" |
            Out-File -FilePath $WrapperLog -Append -Encoding utf8
        Restore-UykuAyari
        exit 3
    }

    Start-Sleep -Seconds $NetworkRetrySeconds
}
# --- NETWORK_READY_WAIT_END ---

# 0. Bota yazan, abone listesinde olmayan kisileri sahibe bildir (abonelik elle
# yonetilir; bu adim kimseyi listeye eklemez ve basarisiz olsa da rapor akisini
# bozmaz - betik her zaman 0 ile cikar).
if (-not $RaporSadece) {
& ".\.venv\Scripts\python.exe" "src\check_requests.py" *>> $WrapperLog

# 1. Veri pipeline'ini calistir (teknik/temel/oruntu JSON bundle uretir) - relative yollarla
& ".\.venv\Scripts\python.exe" "src\data_pipeline.py" *>> $WrapperLog
$PipelineExit = $LASTEXITCODE

# Cikis kodu 2 = pipeline bugun icin daha saglam bir bundle buldu ve bozuk sonucun
# uzerine yazmayi reddetti. Bundle dosyasi VAR ama eski/iyi olani; devam edersek
# ayni raporu ikinci kez gondeririz. Diger sifir disi kodlar da gercek arizadir.
if ($PipelineExit -ne 0) {
    "HATA: Veri pipeline'i $PipelineExit kodu ile cikti; rapor uretilmeyecek." | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    if ($PipelineExit -eq 2) {
        Send-ArizaUyarisi "Borsa Analiz Ajani: bozuk bir calisma tespit edildi; bugunun saglam verisi korundu ve ikinci rapor gonderilmedi."
    } else {
        Send-ArizaUyarisi "Borsa Analiz Ajani: veri pipeline'i $PipelineExit koduyla cikti. Bugun rapor uretilemedi."
    }
    "=== Calisma bitti (pipeline hatasi): $(Get-Date) ===" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    Restore-UykuAyari
    exit $PipelineExit
    }
} else {
    "RaporSadece: veri pipeline'i atlandi, mevcut bundle kullanilacak." | Out-File -FilePath $WrapperLog -Append -Encoding utf8
}

$BundlePath = Join-Path $ProjectDir "logs\bundle_$Today.json"
$ReportPath = Join-Path $ProjectDir "logs\rapor_$Today.txt"

if (-not (Test-Path $BundlePath)) {
    "HATA: Bundle dosyasi olusmadi: $BundlePath" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    Send-ArizaUyarisi "Borsa Analiz Ajani: veri paketi (bundle) olusmadi. Bugun rapor uretilemedi."
    Restore-UykuAyari
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
   - ZORUNLU VE PAZARLIKSIZ: symbols listesindeki HER sembol icin ayri, 5-7 cumlelik bir paragraf yaz. Listede kac sembol varsa (en fazla 30) o kadar paragraf olacak - atlama, ozetleme, 'birkac ismi acalim' deyip gerisini tabloya sikistirma. 18-22 Eylul 2026 arasinda tam bu oldu: 30 sembol tek satirlik bir tabloya indi ve yalnizca 8'i aciklandi; raporun asil degeri olan kisim kayboldu. Ozet tablo EKLEYEBILIRSIN ama paragraflarin YERINE degil, ONLARA EK olarak.
   - Her sembol paragrafi kendi basligiyla baslasin ve bicim sabit olsun (otomatik denetim bunu sayiyor):
     N) SEMBOL - SIRKET ADI | Puan 0,XXXX
     Ornek: '1) AKBNK.IS - AKBANK (Financial Services) | Puan 0,9468'
   - Teknik terimi kullandiginda (RSI, MACD, Bollinger, F/K, PEG, Graham skoru, Dow trendi, FCF getirisi, Net Borc/FAVOK, beta vb.) parantez icinde KISACA ne anlama geldigini de acikla - okuyucu bu terimleri bilmiyor olabilir. Ornek: 'RSI 74 (bu gosterge fiyatin ne kadar hizli yukseldigini olcer; 70 uzeri "asiri alim" sayilir, yani fiyat kisa surede cok hizli yukselmis olabilir ve bir soluklanma/duzeltme ihtimali artar)'.
   - Sadece rakam siralama - HIKAYE ANLAT: bu gostergeler, gecmis oruntu bulgusu ve varsa haber duygusu bir araya geldiginde, onumuzdeki gunler/haftalar icin ortaya nasil bir tablo cikiyor, bunu birlestirerek anlat.
   - Klasik yatirim literaturunden (Graham/Dodd'un deger yatirimi kriterleri, Lynch'in "One Up On Wall Street" ve "Beating the Street" kitaplarindaki PEG orani/buyume kategorileri/adil deger araligi, Murphy'nin Dow trend teorisi, Nison'in mum formasyonlari, Elder'in cok zaman dilimi teyidi) esinlenerek, 'bu tur bir durumda bu teoriye gore genelde ne beklenir' tarzinda EGITICI TUYOLAR ver - yani sadece veri sunma, o verinin klasik analiz cercevelerinde ne ifade ettigini yorumla.
   - Hisseler icin (kriptoda uygulanamaz), Lynch'in "Beating the Street" kitabinda anlattigi "iki dakikalik hikaye" pratigini uygula: sirket/sektor bilgisi, Lynch kategorisi ve buyume orani, PEG/degerleme, adil deger araligi (varsa) ve varsa iceriden sahiplik notunu kisa, tutarli bir "yatirim hikayesi" cumlesinde birlestir (ne is yapiyor, buyume/deger acisindan neden dikkat cekici ya da degil, ana risk ne olabilir) - bunu da egitici bir gozlem olarak sun, tavsiye olarak degil.
   - Fundamental_notes'ta finansal saglik/kalite verisi varsa (FCF getirisi, Net Borc/FAVOK, beta, brut/faaliyet marji, ciro buyumesi) bunlari da hikayeye kat - orn. yuksek kaldirac (Net Borc/FAVOK) veya negatif FCF varsa bunu bir dikkat noktasi olarak belirt.
   - ZORUNLU: fundamental_notes icinde "DCF tabanli adil deger araligi" VEYA "Basitlestirilmis adil deger araligi" ile baslayan bir not varsa (Ayi/Baz/Boga fiyatlarini icerir), bu MUTLAKA paragrafa dahil edilmeli - atlanmamali, kisaltilmamali. "DCF tabanli" olanlar gercek bir WACC (CAPM ile hesaplanmis) + 5 yillik nakit akisi projeksiyonuna dayanir - varsayimlari (WACC yuzdesi, ozsermaye/borc maliyeti) da belirt. "Basitlestirilmis" (Lynch sezgiseli) olanlar ise DCF hesaplanamadiginda (orn. negatif FCF) kullanilan daha kaba bir yedek yontemdir - hangisi kullanilmissa onu dogru sekilde adlandir, ikisini birbirine karistirma.
   - HER sembol paragrafinin SONUNA, o sembole ozel TEK CUMLELIK bir not ekle ve satiri TAM OLARAK "Bu tabloyu ne bozar?" ibaresiyle basla (otomatik denetim bu ibareyi sayarak kac sembolun islendigini olcuyor; ibareyi degistirirsen rapor eksik sayilir) - yani mevcut verideki en belirgin zayif nokta veya kirilganlik neyse (orn. dusuk Graham skoru, yuksek kaldirac, kucuk oruntu ornek sayisi, asiri alim/satim, negatif FCF, token unlock riski) onu tek cumleyle ozetle. Bu bir risk/tez-bozucu gozlemidir, tavsiye degildir.
   - Olasilik dili kullanabilirsin ('... ihtimalini artirir', '... isareti olarak yorumlanabilir', 'gecmiste boyle durumlarda genelde ...'), ama KESIN ONGORU veya 'su olacak' gibi kesinlik ifade eden cumleler kurma.
   - HICBIR SEKILDE 'al/sat/tut' tavsiyesi verme (asla 'almalisin/satmalisin/tutmalisin' deme) - sadece egitici gozlem ve olasilik sun.
   Ozetin en sonuna tam olarak su satiri ekle: 'Bu mesaj yalnizca bilgilendirme ve egitim amaclidir, yatirim tavsiyesi degildir.'
5d. 18-22 Eylul raporlarinda ortaya cikan su bolumler ISE YARIYOR, onlari KORU ve uygun oldugunda yaz - ama yine sembol paragraflarinin YERINE degil, EK olarak: (a) "VERININ YALAN SOYLEDIGI YERLER" - puanlama formulunun bozuk/yanlis okudugu veriler (negatif ozkaynak, sifir PD/DD, tek seferlik kardan sismis PEG, az ornekli oruntu istatistigi, sadece birkac kriteri olculebildigi icin kusursuz gorunen Graham skoru); (b) gunun tek cumlelik ana bulgusu; (c) dune gore listeye girenler/cikanlar ve bunun neden "kotuleme" anlamina gelmedigi; (d) puan ile fiyat yonu celisiyorsa bunun nedeni. Bu bolumler raporun en degerli kismi olabilir, cunku okuyucuyu veriye koru korune guvenmekten korurlar.
5c. Ana top-30 bolumunden SONRA, raporun ayri bir bolumu olarak "KARSIT YATIRIM ADAYLARI" baslikli bir kisim yaz. Bu bolum de MEKANIK bir taramadir, symbols listesiyle AYNI evrenle sinirli DEGILDIR (BIST tarafinda mevcut BIST100 listesiyle sinirli, ABD tarafinda ise ABD top-30'un disina cikip S&P 500'un tamamini da tarar) ve SENIN secimin degildir:
   - Bolume, contrarian_book_citation alanindaki kaynagi (kitap adi/yazari) ve contrarian_rule_explanation alanindaki kurali TEK SEFER, bolumun basinda kisaca aciklayarak basla (52 haftalik zirveden en az %50 dusus + fiyat/piyasa degeri esikleri + F/K, F/DD, F/SNA, F/S oranlarindan en az ikisi).
   - contrarian_candidates BOSSA: "Bugun bu kurallara uyan bir aday bulunamadi" seklinde durumu oldugu gibi belirt, uydurma veya zorlama.
   - contrarian_candidates DOLUYSA: her aday icin 2-4 cumlelik kisa bir aciklama yaz (kac gun/yuzde zirveden dustugu, hangi oranlarin (signals_met) esigin altinda kaldigi). high_signal_warning true olan adaylar icin kitabin "3-4 kritere birden uyan sirketler dikkatle incelenmeli, asiri zayiflamis/iflasa yakin olabilir" uyarisini MUTLAKA ekle.
   - Bolumun EN SONUNA, TEK SEFER (her aday icin degil), kitaptaki risk yonetimi kurallarini genel egitici bir not olarak ekle: tek pozisyon portfoyun en fazla %5'i, tek sektor en fazla %20'si, zarar durumunda %25 stop-loss, kardaki pozisyonlarda %30 sonrasi iz-suren stop gibi kurallarin PRENSIP olarak boyle calistigini anlat - bunu da tavsiye degil, kitaptan aktarilan egitici bilgi olarak sun.
   - Bu bolumde de "al/sat/tut" ifadesi KESINLIKLE kullanma.
6. Bu ozeti '$ReportPath' dosyasina yaz.
6b. GONDERMEDEN ONCE kendini denetle: '$ProjectDir\.venv\Scripts\python.exe' '$ProjectDir\src
apor_denetle.py' '$BundlePath' '$ReportPath' komutunu calistir. Cikis kodu 1 ise raporda eksik sembol var demektir - eksik sembollerin paragraflarini yaz, dosyayi guncelle ve denetimi tekrar calistir. Denetim 0 donene kadar gondermeye gecme (en fazla 3 deneme; ucunde de basaramazsan yine gonder, asagidaki PowerShell denetimi durumu sahibe bildirecek).
7. '$ProjectDir\.venv\Scripts\python.exe' '$ProjectDir\src\send_text.py' '$ReportPath' komutunu calistirarak Telegram'a gonder.
8. Gonderim basariliysa VE 4. adimda islenen haber dosyalari varsa: '$ProjectDir\.venv\Scripts\python.exe' '$ProjectDir\src\archive_news.py' <dosya_adi1> <dosya_adi2> ... komutuyla arsivle (pending_news anahtarlarindaki tam dosya adlarini kullan).
9. symbols listesindeki bir sembolde error alani doluysa (normalde olmamali, zaten hatali semboller listeye girmeden filtrelendi) o sembolu atla, tum ozeti durdurma.

Hicbir finansal veri uydurma, sadece JSON bundle ve haber metinlerindeki gercek bilgiyi kullan.
"@

claude -p $Prompt --dangerously-skip-permissions --tools "Bash,Read,Write" --add-dir "$ProjectDir" *>> $WrapperLog

# Prompt her sembole ayri paragraf yazilmasini sart kosuyor, ama 18-22 Eylul 2026
# arasinda bu sessizce terk edildi: 30 sembol tek satirlik bir tabloya indi, sadece
# 8'i aciklandi ve kimse fark etmedi. Rapor zaten gonderildi; burada amac engellemek
# degil, bir daha sessiz kalmamasi.
if (Test-Path $ReportPath) {
    & ".\.venv\Scripts\python.exe" "src\rapor_denetle.py" $BundlePath $ReportPath *>> $WrapperLog
    if ($LASTEXITCODE -ne 0) {
        Send-ArizaUyarisi "Borsa Analiz Ajani: rapor gonderildi ama eksik - sembollerin bir kismi kendi paragrafini almamis (detay wrapper logunda). Gecmiste bu sekilde 30 sembol tek satira inmisti."
    }
} else {
    "HATA: Rapor dosyasi olusmadi: $ReportPath" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
    Send-ArizaUyarisi "Borsa Analiz Ajani: veri paketi olustu ama rapor dosyasi yazilmadi; Telegram'a bugun rapor gitmedi."
}

Restore-UykuAyari
"=== Calisma bitti: $(Get-Date) ===" | Out-File -FilePath $WrapperLog -Append -Encoding utf8
