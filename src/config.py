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
    total_symbols = (
        len(symbols.get("bist", []))
        + len(symbols.get("us", []))
        + symbols.get("crypto_count", 0)
    )
    if total_symbols == 0:
        raise ValueError("config.yaml içinde en az bir sembol tanımlanmalı (symbols.bist/us/crypto_count).")

    telegram = config["telegram"]
    if not telegram.get("bot_token"):
        raise ValueError("config.yaml içinde telegram.bot_token doldurulmalı.")

    recipients = collect_recipients(telegram)
    if not recipients:
        raise ValueError(
            "config.yaml içinde telegram.chat_id (sahip) doldurulmalı; "
            "ek alıcılar telegram.extra_chat_ids listesine yazılır."
        )
    telegram["recipients"] = recipients

    return config


def collect_recipients(telegram: dict) -> list[str]:
    """Raporun gideceği chat ID'lerinin sırası korunmuş, tekrarsız listesi.

    Sahibin chat_id'si her zaman ilk sıradadır; ardından extra_chat_ids
    listesindeki kişiler gelir. Liste girdileri string'e çevrilir çünkü
    YAML'da tırnaksız yazılan ID'ler int olarak okunur.
    """
    ids: list[str] = []
    owner = telegram.get("chat_id")
    if owner:
        ids.append(str(owner).strip())

    for entry in telegram.get("extra_chat_ids") or []:
        # Liste hem düz ID hem de {id: ..., ad: ...} biçimini kabul eder.
        raw = entry.get("id") if isinstance(entry, dict) else entry
        if raw is None:
            continue
        value = str(raw).strip()
        if value and value not in ids:
            ids.append(value)

    return ids
