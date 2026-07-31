"""Telegram bot API üzerinden mesaj gönderme - tek yönlü bildirim için ekstra
SDK gerekmez, düz requests.post yeterli.

Kurulum:
1. Telegram'da @BotFather'a /newbot yazıp bot token alın.
2. Bota bir mesaj atın (herhangi bir şey yazın).
3. https://api.telegram.org/bot<token>/getUpdates adresini tarayıcıda açıp
   "chat":{"id": ...} alanındaki sayıyı chat_id olarak not edin.
4. Bu ikisini config/config.yaml içine yazın.
"""
import requests

MAX_CHUNK_SIZE = 4000  # Telegram sınırı 4096, güvenlik payı bırakıldı


def chunk_message(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Metni, satır/blok ortasından bölmeden max_size karakterlik parçalara ayırır."""
    if len(text) <= max_size:
        return [text]

    chunks = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > max_size and current:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_message(token: str, chat_id: str, text: str) -> bool:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def send_report(token: str, chat_id: str, full_text: str) -> dict:
    chunks = chunk_message(full_text)
    results = [send_message(token, chat_id, chunk) for chunk in chunks]
    return {"chunks_sent": sum(results), "chunks_total": len(chunks), "success": all(results)}
