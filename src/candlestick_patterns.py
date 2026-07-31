"""Steve Nison'ın 'Japanese Candlestick Charting Techniques' kitabından esinlenen,
kural tabanlı mum formasyonu tanıma. Open/High/Low/Close verisi gerektirir - bu
yüzden sadece yfinance'ten OHLC alınabilen BIST/ABD hisseleri için çalışır;
kripto tarafında (sadece kapanış fiyatı serisi) uygulanmaz.

Tüm tespitler basit gövde/fitil oranı kurallarıdır, klasik tanımların
sadeleştirilmiş halidir - kesin sinyal değil, gözlemsel bir nottur.
"""
import pandas as pd


def _body(row) -> float:
    return abs(row["Close"] - row["Open"])


def _range(row) -> float:
    return row["High"] - row["Low"]


def _upper_shadow(row) -> float:
    return row["High"] - max(row["Close"], row["Open"])


def _lower_shadow(row) -> float:
    return min(row["Close"], row["Open"]) - row["Low"]


def _is_bullish(row) -> bool:
    return row["Close"] > row["Open"]


def detect_patterns(df: pd.DataFrame) -> list[str]:
    """df: Open/High/Low/Close kolonlarına sahip, son barı en güncel olan DataFrame."""
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(df.columns) or len(df) < 3:
        return []

    notes: list[str] = []
    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    last_range = _range(last)
    if last_range == 0:
        return notes

    body = _body(last)
    upper = _upper_shadow(last)
    lower = _lower_shadow(last)

    # Doji: gövde, toplam aralığın çok küçük bir kısmı
    if body <= 0.1 * last_range:
        notes.append("Son mumda 'Doji' formasyonu görüldü - piyasa kararsızlığına işaret edebilir")

    # Çekiç (Hammer): küçük gövde üstte, uzun alt fitil, kısa/yok üst fitil - düşüş sonrası
    elif lower >= 2 * body and upper <= 0.3 * body and prev["Close"] < prev2["Close"]:
        notes.append("Son mumda 'Çekiç (Hammer)' formasyonu görüldü - düşüş sonrası potansiyel dip sinyali olabilir")

    # Asılı Adam (Hanging Man): çekiçle aynı şekil ama yükseliş sonrası
    elif lower >= 2 * body and upper <= 0.3 * body and prev["Close"] > prev2["Close"]:
        notes.append("Son mumda 'Asılı Adam (Hanging Man)' formasyonu görüldü - yükseliş sonrası potansiyel zirve sinyali olabilir")

    # Kayan Yıldız (Shooting Star): küçük gövde altta, uzun üst fitil - yükseliş sonrası
    elif upper >= 2 * body and lower <= 0.3 * body and prev["Close"] > prev2["Close"]:
        notes.append("Son mumda 'Kayan Yıldız (Shooting Star)' formasyonu görüldü - yükseliş sonrası potansiyel zirve sinyali olabilir")

    # Yutan Boğa / Yutan Ayı (Engulfing)
    prev_body = _body(prev)
    if prev_body > 0:
        if (not _is_bullish(prev) and _is_bullish(last)
                and last["Open"] <= prev["Close"] and last["Close"] >= prev["Open"]
                and body > prev_body):
            notes.append("'Yutan Boğa (Bullish Engulfing)' formasyonu görüldü - potansiyel yükseliş sinyali olabilir")
        elif (_is_bullish(prev) and not _is_bullish(last)
                and last["Open"] >= prev["Close"] and last["Close"] <= prev["Open"]
                and body > prev_body):
            notes.append("'Yutan Ayı (Bearish Engulfing)' formasyonu görüldü - potansiyel düşüş sinyali olabilir")

    # Sabah/Akşam Yıldızı (Morning/Evening Star) - 3 mumluk basitleştirilmiş kontrol
    mid_body = _body(prev)
    first_body = _body(prev2)
    if first_body > 0 and mid_body <= 0.3 * first_body:
        if (not _is_bullish(prev2) and _is_bullish(last)
                and last["Close"] > (prev2["Open"] + prev2["Close"]) / 2):
            notes.append("'Sabah Yıldızı (Morning Star)' formasyonuna benzer bir dizilim görüldü - potansiyel dip sinyali olabilir")
        elif (_is_bullish(prev2) and not _is_bullish(last)
                and last["Close"] < (prev2["Open"] + prev2["Close"]) / 2):
            notes.append("'Akşam Yıldızı (Evening Star)' formasyonuna benzer bir dizilim görüldü - potansiyel zirve sinyali olabilir")

    return notes
