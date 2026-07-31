"""Zamanlanmış Claude rutininin, sentezlediği nihai Türkçe raporu Telegram'a
göndermek için çağıracağı küçük CLI sarmalayıcı.

Kullanım: python src/send_text.py <rapor_metni_dosyasi.txt> [config_yolu]
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config as config_module
import telegram_client


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python send_text.py <rapor_metni_dosyasi.txt> [config_yolu]")
        sys.exit(1)

    report_path = Path(sys.argv[1])
    config_path = sys.argv[2] if len(sys.argv) > 2 else PROJECT_ROOT / "config" / "config.yaml"

    config = config_module.load_config(config_path)
    text = report_path.read_text(encoding="utf-8")

    result = telegram_client.send_report(
        config["telegram"]["bot_token"],
        config["telegram"]["chat_id"],
        text,
    )
    print(result)
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
