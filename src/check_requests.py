"""Bota yazan ama abone listesinde olmayan kişileri tespit edip sahibe bildirir.

Abonelik otomatik DEĞİLDİR: bu betik kimseyi listeye eklemez. Sadece iki iş yapar:

1. Bota yazan, config'de tanımlı olmayan kişileri sahibe tek bir Telegram
   mesajıyla bildirir - chat ID'si hazır, kopyalanıp config'e yapıştırılacak
   biçimde. Böylece sahip getUpdates URL'sini elle açmak zorunda kalmaz.
2. İstek sahibine "isteğin iletildi" nezaket cevabı gönderir, ki kişi boşluğa
   yazdığını sanmasın.

Kullanım: python src/check_requests.py [config_yolu] [--dry-run]

--dry-run: hiç mesaj göndermez ve işlenmiş sayılan noktayı ilerletmez;
sadece bota kimlerin yazdığını ekrana yazar.

Not: Çıkış kodu her zaman 0'dır. Bu betik raporun yan işidir; başarısız olması
günlük raporu engellememelidir.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as config_module
import telegram_client

# Hangi güncellemeye kadar işlendiğini tutar. Bu dosya olmadan da çalışır
# (Telegram 24 saatlik geçmişi verir), dosya sadece aynı kişiyi her gün
# yeniden bildirmemizi önler.
STATE_PATH = PROJECT_ROOT / "config" / "telegram_state.json"

# listen.py calisirken tuttugu kilit. Telegram'in getUpdates onayi bot
# genelidir: bu betik mesajlari okursa dinleyici onlari bir daha goremez ve
# gunluk rapor saatinde gelen bir sembol sorgusu sessizce kaybolur. Kilit
# tazeyse bu betik hicbir seye dokunmadan cikar.
LOCK_PATH = PROJECT_ROOT / "logs" / "listener.lock"
LOCK_STALE_AFTER = timedelta(minutes=5)


def listener_alive() -> bool:
    """Dinleyici su anda mesajlari devraliyor mu?"""
    try:
        beat = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["heartbeat"]
        return datetime.now() - datetime.fromisoformat(beat) < LOCK_STALE_AFTER
    except Exception:
        return False


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"UYARI: durum dosyasi yazilamadi: {exc}")


def describe(chat: dict) -> str:
    """Telegram chat nesnesinden okunabilir bir isim üretir."""
    parts = [chat.get("first_name"), chat.get("last_name")]
    name = " ".join(p for p in parts if p).strip()
    username = chat.get("username")
    if username:
        name = f"{name} (@{username})".strip()
    return name or "isimsiz"


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv
    config_path = args[0] if args else PROJECT_ROOT / "config" / "config.yaml"

    if listener_alive():
        print("Dinleyici (listen.py) calisiyor; mesajlari o isliyor, bu adim atlandi.")
        sys.exit(0)

    try:
        config = config_module.load_config(config_path)
        token = config["telegram"]["bot_token"]
        known = set(config["telegram"]["recipients"])
        owner = config["telegram"]["recipients"][0]

        state = load_state()
        offset = state.get("offset")
        updates = telegram_client.get_updates(token, offset=offset)

        if not updates:
            print("Bekleyen yeni mesaj yok.")
            sys.exit(0)

        # Aynı kişi birden çok kez yazmış olabilir; chat ID başına tek kayıt.
        newcomers: dict[str, str] = {}
        last_update_id = offset
        for update in updates:
            last_update_id = update.get("update_id")
            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", "")).strip()
            if not chat_id or chat_id in known or chat_id in newcomers:
                continue
            newcomers[chat_id] = describe(chat)

        if last_update_id is not None and not dry_run:
            # +1: bu güncelleme işlendi, bir daha gelmesin.
            save_state({"offset": last_update_id + 1})

        if not newcomers:
            print(f"{len(updates)} mesaj islendi, listede olmayan yeni kisi yok.")
            sys.exit(0)

        satirlar = [f"  {ad}: {chat_id}" for chat_id, ad in newcomers.items()]
        bildirim = (
            "Bota yeni kisi(ler) yazdi - abone listesinde yoklar:\n\n"
            + "\n".join(satirlar)
            + "\n\nRaporu almalarini istiyorsan config/config.yaml icindeki "
            "telegram.extra_chat_ids listesine ID'lerini ekle."
        )
        if dry_run:
            print("[dry-run] Hicbir mesaj gonderilmedi. Listede olmayan kisiler:")
            for chat_id, ad in newcomers.items():
                print(f"  {ad}: {chat_id}")
            sys.exit(0)

        telegram_client.send_message(token, owner, bildirim)
        print(f"{len(newcomers)} yeni kisi sahibe bildirildi: {', '.join(newcomers)}")

        for chat_id in newcomers:
            telegram_client.send_message(
                token,
                chat_id,
                "Merhaba! Bu bot ozel bir gunluk borsa tarama raporu gonderiyor ve "
                "abone listesi elle yonetiliyor. Istegin bot sahibine iletildi; "
                "onaylanirsa raporu her hafta ici sabah almaya baslayacaksin.",
            )

    except Exception as exc:
        print(f"ISTEK KONTROLU BASARISIZ: {exc}")

    sys.exit(0)


if __name__ == "__main__":
    main()
