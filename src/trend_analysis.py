"""John Murphy'nin 'Technical Analysis of the Financial Markets' kitabındaki Dow
Teorisi tabanlı trend tespiti + basit destek/direnç, ve Alexander Elder'ın
'Trading for a Living' kitabındaki 'üç ekran' (triple screen) çoklu zaman
dilimi teyidinden esinlenen haftalık/günlük karşılaştırma.

Tüm notlar gözlemseldir, al/sat tavsiyesi içermez.
"""
import pandas as pd


def swing_highs_lows(close: pd.Series, order: int = 3) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Basit yerel maksimum/minimum (swing point) tespiti."""
    values = close.values
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(order, len(values) - order):
        window = values[i - order: i + order + 1]
        if values[i] == window.max() and (window == values[i]).sum() == 1:
            highs.append((i, float(values[i])))
        if values[i] == window.min() and (window == values[i]).sum() == 1:
            lows.append((i, float(values[i])))
    return highs, lows


def dow_trend_note(close: pd.Series) -> str:
    highs, lows = swing_highs_lows(close)
    if len(highs) < 2 or len(lows) < 2:
        return "Trend belirlemek için yeterli swing noktası yok"

    higher_highs = highs[-1][1] > highs[-2][1]
    higher_lows = lows[-1][1] > lows[-2][1]
    lower_highs = highs[-1][1] < highs[-2][1]
    lower_lows = lows[-1][1] < lows[-2][1]

    if higher_highs and higher_lows:
        return "Dow Teorisi'ne göre trend yukarı yönlü (yükselen tepeler ve dipler)"
    if lower_highs and lower_lows:
        return "Dow Teorisi'ne göre trend aşağı yönlü (alçalan tepeler ve dipler)"
    return "Dow Teorisi'ne göre net bir trend yok (yatay/karışık seyir)"


def support_resistance_notes(close: pd.Series, lookback: int = 90) -> list[str]:
    recent = close.tail(lookback)
    last_close = close.iloc[-1]
    highs, lows = swing_highs_lows(recent)
    notes: list[str] = []

    resistances = [h[1] for h in highs if h[1] > last_close]
    if resistances:
        nearest_res = min(resistances)
        pct = (nearest_res / last_close - 1) * 100
        notes.append(f"En yakın direnç seviyesi ~{nearest_res:.2f} (fiyatın %{pct:.1f} üzerinde)")

    supports = [l[1] for l in lows if l[1] < last_close]
    if supports:
        nearest_sup = max(supports)
        pct = (1 - nearest_sup / last_close) * 100
        notes.append(f"En yakın destek seviyesi ~{nearest_sup:.2f} (fiyatın %{pct:.1f} altında)")

    return notes


def multi_timeframe_note(df: pd.DataFrame, daily_rsi_value: float) -> str | None:
    """Elder'ın 'üç ekran' mantığından esinlenerek haftalık trend + günlük RSI kıyaslaması."""
    close = df["Close"].dropna()
    if not isinstance(close.index, pd.DatetimeIndex) or len(close) < 70:
        return None

    weekly = close.resample("W").last().dropna()
    if len(weekly) < 10:
        return None

    weekly_sma = weekly.rolling(10).mean()
    if pd.isna(weekly_sma.iloc[-1]):
        return None

    weekly_trend_up = weekly.iloc[-1] > weekly_sma.iloc[-1]

    if weekly_trend_up and daily_rsi_value > 70:
        return ("Haftalık trend yukarı yönlü ama günlük RSI aşırı alımda - Elder'ın 'üç ekran' "
                "mantığına göre kısa vadeli bir düzeltme riski olabilir")
    if not weekly_trend_up and daily_rsi_value < 30:
        return ("Haftalık trend aşağı yönlü ama günlük RSI aşırı satımda - kısa vadeli bir tepki "
                "hareketi olabilir, ana trend hâlâ aşağı yönlü görünüyor")
    if weekly_trend_up:
        return "Haftalık ana trend yukarı yönlü, günlük göstergelerle uyumlu görünüyor (Elder 'üç ekran' teyidi)"
    return "Haftalık ana trend aşağı yönlü, günlük göstergelerle uyumlu görünüyor (Elder 'üç ekran' teyidi)"


def analyze_trend(df: pd.DataFrame, daily_rsi_value: float | None = None) -> list[str]:
    close = df["Close"].dropna()
    if len(close) < 20:
        return []

    notes = [dow_trend_note(close)]
    notes.extend(support_resistance_notes(close))

    if daily_rsi_value is not None:
        mtf_note = multi_timeframe_note(df, daily_rsi_value)
        if mtf_note:
            notes.append(mtf_note)

    return notes
