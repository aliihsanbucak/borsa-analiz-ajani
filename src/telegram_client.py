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


def broadcast_report(token: str, chat_ids: list[str], full_text: str) -> dict:
    """Aynı raporu birden çok alıcıya gönderir.

    Bir alıcıya gönderim başarısız olursa (kişi botu engellemiş, chat ID
    yanlış vb.) diğerleri yine de denenir; sonuç alıcı bazında raporlanır.
    """
    per_chat = {chat_id: send_report(token, chat_id, full_text) for chat_id in chat_ids}
    failed = [chat_id for chat_id, result in per_chat.items() if not result["success"]]
    return {
        "recipients": len(chat_ids),
        "delivered": len(chat_ids) - len(failed),
        "failed_chat_ids": failed,
        "per_chat": per_chat,
        "success": not failed,
    }


def get_updates(token: str, offset: int | None = None, timeout: int = 0) -> list[dict]:
    """getUpdates ile bekleyen mesajları çeker.

    offset verilirse o ID'ye kadarki güncellemeler Telegram tarafında
    onaylanmış (silinmiş) sayılır. Telegram güncellemeleri 24 saat saklar,
    bu yüzden günde bir kez çağırmak /start mesajlarını kaçırmaz.
    """
    params: dict = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/getUpdates",
        data=params,
        timeout=timeout + 20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"getUpdates başarısız: {payload}")
    return payload.get("result", [])
