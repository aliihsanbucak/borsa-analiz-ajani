"""news_inbox/ klasöründeki PDF/txt/docx haber dosyalarından düz metin çıkarma.

Bu modül SADECE metin çıkarır - duygu/yorum analizi yapmaz. Duygu yorumu,
günlük rutin prompt'u içinde Claude tarafından, buradan çıkan metin + sayısal
bulgular birlikte okunarak yapılır.
"""
from pathlib import Path
from datetime import date

import pypdf
import docx

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".docx")


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".txt":
            return file_path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".pdf":
            reader = pypdf.PdfReader(str(file_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix == ".docx":
            document = docx.Document(str(file_path))
            return "\n".join(p.text for p in document.paragraphs)
    except Exception as e:
        return f"[HATA: {file_path.name} okunamadı - {e}]"
    return ""


def collect_pending_news(inbox_dir: Path) -> dict[str, str]:
    inbox_dir = Path(inbox_dir)
    if not inbox_dir.exists():
        return {}

    pending = {}
    for file_path in sorted(inbox_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            text = extract_text(file_path)
            if text.strip():
                pending[file_path.name] = text
    return pending


def archive_processed(inbox_dir: Path, filenames: list[str]) -> None:
    inbox_dir = Path(inbox_dir)
    archive_dir = inbox_dir / "islenmis"
    archive_dir.mkdir(exist_ok=True)
    today = date.today().isoformat()

    for name in filenames:
        source = inbox_dir / name
        if not source.exists():
            continue
        destination = archive_dir / f"{today}_{name}"
        source.rename(destination)
