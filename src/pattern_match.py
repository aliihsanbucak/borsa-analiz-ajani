"""Sembolün kendi geçmişinde, güncel fiyat örüntüsüne benzer dönemleri arar ve
bu dönemlerin ardından tipik olarak ne olduğunu raporlar.

Bu istatistiksel bir gözlem/tarama aracıdır - klasik bir kitaptan alınmış bir
yöntem değil, kullanıcının isteği üzerine eklenen tamamlayıcı bir analizdir.
Hiçbir şekilde gelecek garantisi vermez; az örnek bulunursa bu açıkça belirtilir.
"""
import numpy as np
import pandas as pd


def _normalize(window: pd.Series) -> np.ndarray:
    base = window.iloc[0]
    if base == 0:
        return np.zeros(len(window))
    return (window.values / base) - 1.0


def find_similar_patterns(
    history: pd.DataFrame,
    window: int = 20,
    lookahead: int = 10,
    top_k: int = 5,
    min_similarity: float = 0.7,
) -> dict:
    close = history["Close"].dropna()
    n = len(close)

    if n < window * 2 + lookahead:
        return {"matches": [], "insufficient_data": True}

    current_window = close.tail(window)
    current_norm = _normalize(current_window)

    current_start = n - window
    max_start = current_start - lookahead - window
    if max_start < 0:
        return {"matches": [], "insufficient_data": True}

    candidates = []
    for start in range(0, max_start + 1):
        cand_window = close.iloc[start:start + window]
        cand_norm = _normalize(cand_window)
        if np.std(cand_norm) == 0 or np.std(current_norm) == 0:
            continue
        similarity = np.corrcoef(current_norm, cand_norm)[0, 1]
        if np.isnan(similarity):
            continue
        candidates.append((start, similarity))

    candidates.sort(key=lambda x: x[1], reverse=True)
    top_matches = [c for c in candidates if c[1] >= min_similarity][:top_k]

    matches = []
    for start, similarity in top_matches:
        window_end = start + window - 1
        forward_end = window_end + lookahead
        price_at_end = close.iloc[window_end]
        price_forward = close.iloc[forward_end]
        forward_return = (price_forward / price_at_end - 1.0) * 100
        matches.append({
            "date": str(close.index[window_end].date()) if isinstance(close.index, pd.DatetimeIndex) else str(window_end),
            "similarity": round(float(similarity), 2),
            "forward_return_pct": round(float(forward_return), 2),
        })

    return {"matches": matches, "insufficient_data": False, "window": window, "lookahead": lookahead}


def pattern_match_note(result: dict) -> str | None:
    if result.get("insufficient_data"):
        return "Örüntü karşılaştırması için yeterli geçmiş veri yok"

    matches = result.get("matches", [])
    if not matches:
        return "Geçmişte yeterince benzer bir fiyat örüntüsü bulunamadı"

    window = result.get("window")
    lookahead = result.get("lookahead")
    returns = [m["forward_return_pct"] for m in matches]
    avg_return = sum(returns) / len(returns)
    positive_count = sum(1 for r in returns if r > 0)
    nearest = max(matches, key=lambda m: m["similarity"])

    reliability_note = ""
    if len(matches) == 1:
        reliability_note = " (sadece 1 benzer örnek bulundu, güvenilirliği düşük)"

    return (
        f"Son {window} günlük fiyat hareketi, geçmişte {len(matches)} kez benzer şekilde "
        f"gerçekleşti (en yakın: {nearest['date']}). Bu örüntülerin ardından sonraki {lookahead} "
        f"iş gününde ortalama %{avg_return:.1f} hareket görüldü ({positive_count}/{len(matches)} "
        f"örnekte yükseliş){reliability_note}. Bu istatistiksel bir gözlemdir, gelecek garantisi vermez."
    )
