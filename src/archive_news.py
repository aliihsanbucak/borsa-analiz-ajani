"""Telegram gönderimi başarılı olduktan sonra, işlenen haber dosyalarını
news_inbox/islenmis/ altına taşımak için rutinin çağıracağı küçük CLI.

Kullanım: python src/archive_news.py dosya1.pdf dosya2.txt ...
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import news_reader


def main():
    filenames = sys.argv[1:]
    if not filenames:
        print("Kullanım: python archive_news.py dosya1.pdf dosya2.txt ...")
        sys.exit(1)

    news_reader.archive_processed(PROJECT_ROOT / "news_inbox", filenames)
    print(f"Arşivlendi: {filenames}")


if __name__ == "__main__":
    main()
