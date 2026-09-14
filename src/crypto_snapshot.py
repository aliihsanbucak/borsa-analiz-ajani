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

    # Market Cap / FDV: hisse senedindeki "seyrelme" riskinin kripto
    # karşılığı. FDV (tam seyreltilmiş değerleme), max arz tamamen
    # dolaşıma girdiğinde oluşacak piyasa değeridir. MC/FDV oranı 1'e
    # yakınsa arzın çoğu zaten dolaşımda demektir; oran düşükse (örn. 0.3)
    # önemli bir kısmı henüz kilitli/vestinge tabi demektir - ileride
    # dolaşıma girdikçe (unlock) satış baskısı oluşturabilir.
    market_cap = snapshot.get("market_cap")
    fdv = snapshot.get("fully_diluted_valuation")
    if market_cap and fdv and fdv > 0:
        mc_fdv_ratio = market_cap / fdv
        if mc_fdv_ratio < 0.5:
            notes.append(
                f"Piyasa Değeri/FDV oranı {mc_fdv_ratio:.2f} - dolaşımdaki arzın toplam (tam seyreltilmiş) "
                f"arza oranı düşük, ileride önemli miktarda token kilidi çözülebilir (unlock), bu da "
                f"gelecekte satış baskısı yaratabilecek bir seyrelme riski taşır"
            )
        else:
            notes.append(f"Piyasa Değeri/FDV oranı {mc_fdv_ratio:.2f} - arzın büyük kısmı zaten dolaşımda")

    if dominance:
        if coin_id == "bitcoin" and dominance.get("btc_dominance") is not None:
            notes.append(f"BTC dominansı %{dominance['btc_dominance']:.1f}")
        elif coin_id == "ethereum" and dominance.get("eth_dominance") is not None:
            notes.append(f"ETH dominansı %{dominance['eth_dominance']:.1f}")

    return notes
