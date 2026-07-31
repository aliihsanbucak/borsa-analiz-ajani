"""Kripto için klasik F/K, temettü gibi temel göstergeler uygulanamaz - bunun
yerine CoinGecko'dan alınan piyasa değeri/hacim/ATH-uzaklık/dominans verileri
yorumlanır.
"""


def interpret_crypto_snapshot(coin_id: str, snapshot: dict, dominance: dict | None = None) -> list[str]:
    notes: list[str] = []
    if not snapshot:
        return notes

    rank = snapshot.get("market_cap_rank")
    if rank is not None:
        notes.append(f"Piyasa değeri sıralaması: #{rank}")

    change_24h = snapshot.get("price_change_percentage_24h")
    if change_24h is not None:
        yön = "yükseliş" if change_24h >= 0 else "düşüş"
        notes.append(f"Son 24 saatte %{abs(change_24h):.1f} {yön}")

    ath_change = snapshot.get("ath_change_percentage")
    if ath_change is not None:
        notes.append(f"Tüm zamanların zirvesinden %{abs(ath_change):.1f} uzakta")

    if dominance:
        if coin_id == "bitcoin" and dominance.get("btc_dominance") is not None:
            notes.append(f"BTC dominansı %{dominance['btc_dominance']:.1f}")
        elif coin_id == "ethereum" and dominance.get("eth_dominance") is not None:
            notes.append(f"ETH dominansı %{dominance['eth_dominance']:.1f}")

    return notes
