"""Teknik göstergeler - elle pandas/numpy (pandas-ta bu makinede Python 3.14 ile
kurulamadığı için kullanılmıyor, bkz. plan dosyasındaki not).

Tüm yorum fonksiyonları nesnel gözlem cümleleri üretir, asla al/sat tavsiyesi vermez.
"""
import pandas as pd
import numpy as np


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.fillna(50)


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0):
    mid = sma(close, window)
    std = close.rolling(window=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def volume_trend_note(volume: pd.Series) -> str | None:
    if volume is None or volume.dropna().empty:
        return None
    recent_avg = volume.tail(5).mean()
    baseline_avg = volume.tail(25).head(20).mean()
    if not baseline_avg or np.isnan(baseline_avg) or baseline_avg == 0:
        return None
    ratio = recent_avg / baseline_avg
    if ratio > 1.3:
        return f"İşlem hacmi son 5 günde ortalamanın üzerinde (x{ratio:.1f})"
    if ratio < 0.7:
        return f"İşlem hacmi son 5 günde ortalamanın altında (x{ratio:.1f})"
    return None


def analyze_symbol_technicals(df: pd.DataFrame) -> dict:
    """df: 'Close' ve tercihen 'Volume' kolonlarına sahip, tarih indeksli DataFrame."""
    close = df["Close"].dropna()
    notes: list[str] = []
    values: dict = {}

    if len(close) < 20:
        return {"notes": ["Gösterge hesaplamak için yeterli geçmiş veri yok"], "values": {}}

    rsi_series = rsi(close)
    last_rsi = rsi_series.iloc[-1]
    values["rsi"] = round(float(last_rsi), 1)
    if last_rsi > 70:
        notes.append(f"RSI {last_rsi:.0f} - aşırı alım bölgesinde")
    elif last_rsi < 30:
        notes.append(f"RSI {last_rsi:.0f} - aşırı satım bölgesinde")
    else:
        notes.append(f"RSI {last_rsi:.0f} - nötr bölgede")

    macd_line, signal_line, hist = macd(close)
    values["macd_histogram"] = round(float(hist.iloc[-1]), 4)
    if len(hist) >= 2:
        prev_hist, cur_hist = hist.iloc[-2], hist.iloc[-1]
        if prev_hist < 0 <= cur_hist:
            notes.append("MACD altın kesişim yaptı (yükseliş sinyali olabilir)")
        elif prev_hist > 0 >= cur_hist:
            notes.append("MACD ölüm kesişimi yaptı (düşüş sinyali olabilir)")
        else:
            notes.append(f"MACD histogramı {'pozitif' if cur_hist > 0 else 'negatif'} momentum gösteriyor")

    last_close = close.iloc[-1]
    for window in (20, 50, 200):
        if len(close) >= window:
            avg = sma(close, window).iloc[-1]
            values[f"sma_{window}"] = round(float(avg), 4)
            konum = "üzerinde" if last_close > avg else "altında"
            notes.append(f"Fiyat SMA{window} {konum}")

    mid, upper, lower = bollinger_bands(close)
    if not np.isnan(upper.iloc[-1]):
        if last_close >= upper.iloc[-1]:
            notes.append("Fiyat Bollinger üst bandına değdi/aştı - aşırı alım işareti olabilir")
        elif last_close <= lower.iloc[-1]:
            notes.append("Fiyat Bollinger alt bandına değdi - aşırı satım işareti olabilir")

    if "Volume" in df.columns:
        vol_note = volume_trend_note(df["Volume"])
        if vol_note:
            notes.append(vol_note)

    values["last_close"] = round(float(last_close), 4)
    return {"notes": notes, "values": values}
