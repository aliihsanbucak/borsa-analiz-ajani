"""config.yaml yükleme ve doğrulama."""
from pathlib import Path
import yaml

REQUIRED_TOP_KEYS = ("symbols", "telegram")


def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config dosyası bulunamadı: {path}\n"
            f"config/config.example.yaml dosyasını config/config.yaml olarak kopyalayıp doldurun."
        )

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    for key in REQUIRED_TOP_KEYS:
        if key not in config:
            raise ValueError(f"config.yaml içinde '{key}' bölümü eksik.")

    symbols = config["symbols"]
    total_symbols = sum(len(symbols.get(market, [])) for market in ("bist", "us", "crypto"))
    if total_symbols == 0:
        raise ValueError("config.yaml içinde en az bir sembol tanımlanmalı (symbols.bist/us/crypto).")

    telegram = config["telegram"]
    if not telegram.get("bot_token") or not telegram.get("chat_id"):
        raise ValueError("config.yaml içinde telegram.bot_token ve telegram.chat_id doldurulmalı.")

    return config
