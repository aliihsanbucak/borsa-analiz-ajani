"""Telegram'a yazilan sembolu (orn. "THYAO", "AAPL", "kripto:BTC") alip o
sembol icin tam analiz uretip cevaplayan surekli dinleyici.

Mimari, gunluk raporla ayni: Python yapilandirilmis veriyi uretir
(analyze_symbol.py -> JSON), nihai Turkce metni once yerel Claude CLI yazar.
Claude kullanilamazsa Codex CLI otomatik yedek motor olarak devreye girer.

Kullanim: python src/listen.py [config_yolu]
Ctrl+C ile temiz durur.

Offset paylasimi: Telegram'in getUpdates onayi bot geneli icindir. Bu yuzden
dinleyici, check_requests.py ile AYNI durum dosyasini kullanir ve calistigi
surece bir kilit dosyasi tutar; check_requests kilidi gorunce mesajlara hic
dokunmaz (yoksa gunluk rapor sirasinda gelen bir sorguyu yutardi).
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as config_module
import symbol_resolver
import telegram_client

STATE_PATH = PROJECT_ROOT / "config" / "telegram_state.json"
LOCK_PATH = PROJECT_ROOT / "logs" / "listener.lock"
LOG_PATH = PROJECT_ROOT / "logs" / f"listener_{datetime.now():%Y-%m}.log"
QUERY_DIR = PROJECT_ROOT / "logs" / "sorgular"

POLL_TIMEOUT = 50           # saniye; Telegram long-poll
CLAUDE_TIMEOUT = 600        # tek sembol raporu icin ust sinir
CODEX_TIMEOUT = 600         # yedek motor icin ayni ust sinir

# Gunluk raporun (run_daily.ps1) kullandigi bayraklarla ayni: dinleyici
# etkilesimsiz calistigi icin izin sorusu soramaz.
CLAUDE_FLAGS = ["--dangerously-skip-permissions"]

REQUIRED_DISCLAIMER = (
    "Bu mesaj yalnizca bilgilendirme ve egitim amaclidir, yatirim tavsiyesi degildir."
)

# Ayni kisi arka arkaya sembol yagdirirsa hem Yahoo'yu hem Claude'u yormamak
# icin kullanici basina minimum aralik.
MIN_SECONDS_BETWEEN_QUERIES = 20
_last_query_at: dict[str, float] = {}

# Belirsiz sorgularda ("ETH: BIST mi kripto mu?") kullanicinin bir sonraki
# mesajini bekleyen secim durumu: chat_id -> adaylar listesi.
_pending_choice: dict[str, list[dict]] = {}


def log(message: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log(f"UYARI: durum dosyasi yazilamadi: {exc}")


def touch_lock() -> None:
    try:
        LOCK_PATH.parent.mkdir(exist_ok=True)
        LOCK_PATH.write_text(
            json.dumps({"pid": os.getpid(), "heartbeat": datetime.now().isoformat(timespec="seconds")}),
            encoding="utf-8",
        )
    except Exception:
        pass


def release_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except Exception:
        pass


def build_prompt(bundle_path: Path, report_path: Path, label: str) -> str:
    """Tek sembollük rapor icin Claude prompt'u.

    Gunluk rapordaki kurallarin (egitici dil, terim aciklamasi, adil deger
    araligini atlamama, tavsiye vermeme) tek sembole indirgenmis hali.
    """
    return f"""Sen kisisel bir Borsa Analiz Ajanisin. Kullanici Telegram'dan tek bir sembol sordu: {label}. Okuyucu finans konusunda uzman DEGIL. Amac: yatirim TAVSIYESI VERMEDEN, anlasilir ve aciklayici bir analiz yazip dosyaya kaydetmek.

Adimlar:
1. '{bundle_path}' dosyasini oku. Icinde: query (sorulan sembol ve pazari), company_name/sector (hisse ise), symbol (technical_notes, fundamental_notes, pattern_note, values, score, hisselerde contrarian), macro_notes (piyasa ve kuresel likidite gostergeleri), related_news (son 24 saatte RSS akislarinda bu sembolle iliskili gorunen basliklar; bos olabilir) ve scoring_explanation (puanin nasil hesaplandigi) var.
2. Turkce, akici, 3-5 paragrafik bir analiz yaz:
   - Ilk paragraf: bu sirket/varlik ne, hangi sektorde, guncel fiyat ve son donem hareketi.
   - Teknik gorunum: RSI, MACD, Bollinger, hareketli ortalamalar, trend ve varsa mum formasyonu. Her teknik terimi parantez icinde KISACA acikla (orn. 'RSI 74 (fiyatin ne kadar hizli yukseldigini olcer; 70 uzeri "asiri alim" sayilir)').
   - Temel gorunum (hisse ise): F/K, PEG, Graham skoru, FCF getirisi, Net Borc/FAVOK, marjlar, beta, buyume. ZORUNLU: fundamental_notes icinde "DCF tabanli adil deger araligi" VEYA "Basitlestirilmis adil deger araligi" ile baslayan bir not varsa MUTLAKA dahil et, kisaltma; hangisi kullanilmissa dogru adlandir (DCF gercek WACC'a dayanir, "Basitlestirilmis" ise DCF hesaplanamadiginda kullanilan kaba Lynch sezgiselidir). Lynch'in "iki dakikalik hikaye" pratigini uygula: ne is yapiyor, buyume/deger acisindan neden dikkat cekici ya da degil, ana risk ne.
   - Kripto ise: piyasa degeri sirasi, hacim, ATH'den uzaklik, arz/dolasim ve BTC/ETH dominansi baglami.
   - Gecmis oruntu bulgusu (pattern_note) varsa mutlaka aktar ve ornek sayisinin kucuklugu gibi sinirlarini belirt.
   - macro_notes'tan SADECE bu sembolu ilgilendiren 1-2 cumle kullan (orn. yuksek faiz borclu bir sirketi, guclu dolar gelisen piyasa hissesini nasil etkiler).
   - related_news doluysa, baslik(lar)i TEK cumleyle aktar. Bu basliklar DOGRULANMAMIS ham veridir: gercekmis gibi sunma, birincil kaynaktan (KAP/SEC/sirket aciklamasi) teyit edilmedigini ima et, habere dayanarak yeni bir gorus OLUSTURMA. related_news bossa "bu sembolle ilgili son 24 saatte takip edilen akislarda bir baslik cikmadi" de.
   - Klasik yatirim literaturunden (Graham/Dodd, Lynch, Murphy'nin Dow trend teorisi, Nison'in mum formasyonlari, Elder'in cok zaman dilimi teyidi) esinlenerek EGITICI tuyolar ver: bu tur bir tabloda o teoriye gore genelde ne beklenir.
2b. Paragraflardan SONRA, ayri bir bolum olarak tam su basligi yaz: "DESTEK VE DIRENC SEVIYELERI". Kaynak: symbol.support_resistance (bos/null ise bolumu yine ac ve "yeterli fiyat gecmisi olmadigi icin seviye hesaplanamadi" yaz, seviye UYDURMA).
   - Once tek cumleyle destek/direncin ne oldugunu acikla (destek: fiyatin gecmiste dusmeyi durdurup geri dondugu bolge; direnc: yukselisin tikandigi bolge) ve seviyelerin nasil bulundugunu 'method' alanina dayanarak kisaca anlat.
   - Sonra seviyeleri madde madde, fiyattan uzaga dogru sirala. Her madde: seviye (fiyat biriminde, 2 ondalik), guncel fiyata uzaklik (distance_pct, yuzde olarak) ve touches (o bolgenin kac kez tepe/dip verdigi; 1 = tek sefer, zayif; 3+ = cok test edilmis, daha belirgin). Bicim:
     Direnc 1: 305,00 (fiyatin %1,3 uzerinde, 2 kez test edildi)
     Destek 1: 292,40 (fiyatin %2,9 altinda, 3 kez test edildi)
   - resistances veya supports bos ise bunu acikca yaz (orn. 'fiyat 1 yillik zirvesinde, ustunde gecmis bir direnc yok').
   - Ayrica 52 haftalik zirve/dip (high_52w/low_52w) ve dynamic icindeki SMA50/SMA200'u "hareketli/ucdeger seviyeler" olarak ayri iki-uc madde halinde ver.
   - Bolumu Murphy'nin rol degisimi ilkesiyle bitir (kirilan direnc sonradan destek, kirilan destek sonradan direnc olarak calisma egilimindedir) ve bu seviyelerin kesin donus noktalari DEGIL, gecmiste tepki gelmis bolgeler oldugunu belirt.
3. Analizin sonuna TEK CUMLELIK bir "Bu tabloyu ne bozar?" notu ekle - mevcut verideki en belirgin zayif nokta/kirilganlik.
4. Olasilik dili kullan ('... ihtimalini artirir', '... olarak yorumlanabilir'). KESIN ONGORU kurma. HICBIR SEKILDE 'al/sat/tut' tavsiyesi verme.
5. En sona tam olarak su satiri ekle: 'Bu mesaj yalnizca bilgilendirme ve egitim amaclidir, yatirim tavsiyesi degildir.'
6. Metni '{report_path}' dosyasina yaz. BASKA hicbir sey yapma - Telegram'a gonderme islemini cagiran betik yapacak.

Hicbir finansal veri uydurma, sadece JSON bundle'daki gercek bilgiyi kullan. Bundle'da olmayan bir sayiyi yazma.
"""


def _read_valid_report(report_path: Path) -> str | None:
    """Motorun gercekten kullanilabilir bir rapor yazdigini dogrular."""
    try:
        text = report_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    if len(text) < 200 or REQUIRED_DISCLAIMER not in text:
        return None
    return text


def _remove_invalid_report(report_path: Path) -> None:
    """Bir motorun yarim ciktisi sonraki motoru basarili gostermesin."""
    try:
        report_path.unlink(missing_ok=True)
    except OSError:
        pass


def _find_codex() -> str | None:
    """Windows'ta calistirilabilir sarmalayici genellikle codex.cmd'dir."""
    for command in ("codex.cmd", "codex.exe", "codex"):
        found = shutil.which(command)
        if found:
            return found
    return None


def generate_report_with_fallback(
    prompt: str, report_path: Path, label: str
) -> tuple[bool, str]:
    """Claude ile rapor uretir; basarisizsa Codex'i otomatik dener."""
    claude_exe = shutil.which("claude")
    if claude_exe:
        try:
            claude = subprocess.run(
                [claude_exe, "-p", prompt, *CLAUDE_FLAGS, "--add-dir", str(PROJECT_ROOT)],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=CLAUDE_TIMEOUT,
            )
            report = _read_valid_report(report_path)
            if report:
                return True, report
            log(f"Claude rapor yazmadi ({label}): rc={claude.returncode} "
                f"stdout={claude.stdout.strip()[:400]} stderr={claude.stderr.strip()[:400]}")
        except subprocess.TimeoutExpired:
            log(f"Claude zaman asimina ugradi ({label}); Codex yedegi denenecek.")
        except OSError as exc:
            log(f"Claude baslatilamadi ({label}): {exc}; Codex yedegi denenecek.")
    else:
        log("claude CLI PATH'te bulunamadi; Codex yedegi denenecek.")

    _remove_invalid_report(report_path)
    codex_exe = _find_codex()
    if not codex_exe:
        log("codex CLI PATH'te bulunamadi.")
        return False, f"{label} verisi alindi ama analiz motorlari kullanilamadi; bot sahibine haber ver."

    # Ana prompt Claude'a dosyayi yazmasini soyluyor. Codex'te daha dar bir
    # yetki modeli kullaniyoruz: repo salt okunur, son yaniti -o ile CLI yazar.
    codex_prompt = prompt + """

CODEX YEDEK MOTOR TALIMATI (onceki cikti talimatinin yerine gecer):
- Sadece promptun 1. adiminda belirtilen JSON bundle'i oku; hicbir dosyayi veya ayari degistirme.
- Nihai yanitinda SADECE Telegram'a gonderilecek Turkce rapor metnini ver.
- Rapor dosyasina kendin yazma; CLI son yanitini rapor dosyasina kaydedecek.
"""
    try:
        codex = subprocess.run(
            [
                codex_exe, "exec", "--ephemeral", "--sandbox", "read-only",
                "--color", "never", "-C", str(PROJECT_ROOT),
                "-o", str(report_path), codex_prompt,
            ],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=CODEX_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log(f"Codex zaman asimina ugradi ({label}).")
        return False, f"{label} analizi zaman asimina ugradi. Birazdan tekrar dener misin?"
    except OSError as exc:
        log(f"Codex baslatilamadi ({label}): {exc}")
        return False, f"{label} verisi alindi ama analiz motoru baslatilamadi; bot sahibine haber ver."

    report = _read_valid_report(report_path)
    if report:
        log(f"Claude kullanilamadi; rapor Codex yedegiyle uretildi ({label}).")
        return True, report

    log(f"Codex rapor yazmadi ({label}): rc={codex.returncode} "
        f"stdout={codex.stdout.strip()[:400]} stderr={codex.stderr.strip()[:400]}")
    _remove_invalid_report(report_path)
    return False, f"{label} verisi alindi ama rapor metni uretilemedi. Tekrar dener misin?"
def run_analysis(candidate: dict) -> tuple[bool, str]:
    """Sembolu analiz eder ve (basarili, metin_veya_hata) doner."""
    market = candidate["market"]
    identifier = candidate["identifier"]
    label = candidate["label"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = identifier.replace(".", "_").replace("-", "_")
    QUERY_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = QUERY_DIR / f"{safe}_{stamp}.json"
    report_path = QUERY_DIR / f"{safe}_{stamp}.txt"

    python_exe = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.run(
        [str(python_exe), str(PROJECT_ROOT / "src" / "analyze_symbol.py"),
         market, identifier, str(bundle_path)],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    if proc.returncode != 0:
        log(f"Analiz basarisiz ({label}): {proc.stdout.strip()} {proc.stderr.strip()}")
        return False, (f"{label} icin veri cekilemedi. Sembolu kontrol edip tekrar dener misin? "
                       "(Yahoo/CoinGecko gecici olarak da cevap vermemis olabilir.)")

    prompt = build_prompt(bundle_path, report_path, label)
    # shell=True KULLANMA: cok satirli prompt ve ozel karakterler cmd.exe
    # tarafindan bozulmasin. Her iki CLI da arguman listesiyle cagrilir.
    return generate_report_with_fallback(prompt, report_path, label)


def describe(chat: dict) -> str:
    parts = [chat.get("first_name"), chat.get("last_name")]
    name = " ".join(p for p in parts if p).strip()
    username = chat.get("username")
    if username:
        name = f"{name} (@{username})".strip()
    return name or "isimsiz"


HELP_TEXT = (
    "Bir sembol yaz, analiz edeyim:\n"
    "  THYAO  - BIST hissesi\n"
    "  AAPL   - ABD hissesi\n"
    "  BTC    - kripto\n\n"
    "Kararsiz kalirsam pazari sen belirtebilirsin: bist:THYAO, us:AAPL, kripto:BTC\n"
    "Analiz 1-2 dakika surer; hazir olunca buraya dusecek."
)


def handle_message(token: str, chat_id: str, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return

    if text.lower() in ("/start", "/help", "/yardim", "yardim"):
        telegram_client.send_message(token, chat_id, HELP_TEXT)
        return

    # Onceki belirsiz sorgunun cevabi mi? ("1" veya "bist" gibi)
    if chat_id in _pending_choice:
        options = _pending_choice.pop(chat_id)
        chosen = None
        if text.isdigit() and 1 <= int(text) <= len(options):
            chosen = options[int(text) - 1]
        else:
            for opt in options:
                if text.lower() in opt["label"].lower() or text.lower() == opt["market"]:
                    chosen = opt
                    break
        if chosen:
            _last_query_at[chat_id] = time.time()
            _dispatch(token, chat_id, chosen)
            return
        # Secim anlasilmadi: normal sembol sorgusu gibi devam et.

    now = time.time()
    if now - _last_query_at.get(chat_id, 0) < MIN_SECONDS_BETWEEN_QUERIES:
        telegram_client.send_message(
            token, chat_id,
            f"Bir onceki sorgu daha yeni bitti; {MIN_SECONDS_BETWEEN_QUERIES} saniye aralikla sorabilirsin.")
        return

    resolved = symbol_resolver.resolve(text)
    candidates = resolved["candidates"]

    if not candidates:
        telegram_client.send_message(token, chat_id, resolved["error"] + "\n\n" + HELP_TEXT)
        return

    if len(candidates) > 1:
        _pending_choice[chat_id] = candidates
        satirlar = "\n".join(f"  {i + 1}. {c['label']}" for i, c in enumerate(candidates))
        telegram_client.send_message(
            token, chat_id,
            f"'{resolved['input']}' birden fazla yerde var. Hangisi?\n{satirlar}\n\nNumarasini yaz.")
        return

    _last_query_at[chat_id] = now
    _dispatch(token, chat_id, candidates[0])


def _dispatch(token: str, chat_id: str, candidate: dict) -> None:
    label = candidate["label"]
    log(f"Sorgu: {label} (chat {chat_id})")
    telegram_client.send_message(token, chat_id, f"{label} analiz ediliyor, 1-2 dakika surebilir...")
    try:
        ok, text = run_analysis(candidate)
    except Exception as exc:
        log(f"Analiz sirasinda beklenmeyen hata ({label}): {exc}")
        ok, text = False, f"{label} analiz edilirken beklenmeyen bir hata olustu."

    if ok:
        result = telegram_client.send_report(token, chat_id, text)
        log(f"Rapor gonderildi ({label}): {result['chunks_sent']}/{result['chunks_total']} parca")
    else:
        telegram_client.send_message(token, chat_id, text)
        log(f"Hata mesaji gonderildi ({label})")


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ROOT / "config" / "config.yaml"
    config = config_module.load_config(config_path)
    token = config["telegram"]["bot_token"]
    known = set(config["telegram"]["recipients"])
    owner = config["telegram"]["recipients"][0]

    log(f"Dinleyici basladi (pid {os.getpid()}). Yetkili chat sayisi: {len(known)}")
    touch_lock()

    state = load_state()
    offset = state.get("offset")
    notified_newcomers: set[str] = set()

    try:
        while True:
            touch_lock()
            try:
                updates = telegram_client.get_updates(token, offset=offset, timeout=POLL_TIMEOUT)
            except Exception as exc:
                log(f"getUpdates basarisiz, 30 sn sonra tekrar: {exc}")
                time.sleep(30)
                continue

            for update in updates:
                offset = update.get("update_id", 0) + 1
                save_state({"offset": offset})

                message = update.get("message") or update.get("edited_message") or {}
                chat = message.get("chat") or {}
                chat_id = str(chat.get("id", "")).strip()
                text = message.get("text") or ""
                if not chat_id:
                    continue

                if chat_id not in known:
                    # Abonelik elle yonetilir; dinleyici kimseyi listeye eklemez.
                    if chat_id not in notified_newcomers:
                        notified_newcomers.add(chat_id)
                        telegram_client.send_message(
                            token, owner,
                            f"Bota listede olmayan biri yazdi: {describe(chat)} -> {chat_id}\n"
                            f"Mesaj: {text[:200]}\n\n"
                            "Erisim vermek istersen config.yaml'daki telegram.extra_chat_ids "
                            "listesine ekle.")
                        telegram_client.send_message(
                            token, chat_id,
                            "Merhaba! Bu bot ozel bir borsa analiz botudur ve erisim listesi elle "
                            "yonetiliyor. Istegin bot sahibine iletildi.")
                    continue

                try:
                    handle_message(token, chat_id, text)
                except Exception as exc:
                    log(f"Mesaj islenirken hata (chat {chat_id}): {exc}")
                    telegram_client.send_message(
                        token, chat_id, "Beklenmeyen bir hata olustu, tekrar dener misin?")

    except KeyboardInterrupt:
        log("Dinleyici durduruldu (Ctrl+C).")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
