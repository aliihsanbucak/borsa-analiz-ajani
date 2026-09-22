"""Rapor üretilemediğinde Telegram'a kısa bir arıza uyarısı gönderen CLI.

`send_text.py` nihai raporu bir dosyadan okur; bu betik ise uyarı metnini
doğrudan argüman olarak alır, çünkü arıza anında ortada yazılmış bir rapor
dosyası yoktur.

Kullanım: python src/send_alert.py "<uyari metni>" [config_yolu]

Not: Çıkış kodu kasıtlı olarak her zaman 0'dır. Uyarı gönderimi en iyi çaba
prensibiyle çalışır; gönderilemezse bile çağıran betiğin kendi arıza çıkış
kodunu bozmamalıdır.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as config_module
import telegram_client


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python send_alert.py \"<uyari metni>\" [config_yolu]")
        sys.exit(0)

    text = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else PROJECT_ROOT / "config" / "config.yaml"

    try:
        config = config_module.load_config(config_path)
        # Ariza uyarisi yalnizca sahibe gider; abonelerin ic isleyisle isi yok.
        result = telegram_client.send_report(
            config["telegram"]["bot_token"],
            config["telegram"]["recipients"][0],
            text,
        )
        print(result)
    except Exception as exc:  # ağ yoksa, config bozuksa vs. - sessizce yutulmasin
        print(f"UYARI GONDERILEMEDI: {exc}")

    sys.exit(0)


if __name__ == "__main__":
    main()
