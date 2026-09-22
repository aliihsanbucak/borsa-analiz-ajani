"""Raporun her sembole gercekten paragraf ayirdigini denetler.

Neden var: 18 Eylul 2026'da rapor sessizce bicim degistirdi. 16-17 Eylul'de
30 sembolun her biri 5-7 cumlelik bir paragraf ve kendine ozel bir
"Bu tabloyu ne bozar?" risk notu aliyordu; 18 Eylul'den itibaren hepsi tek
satirlik bir tabloya sikisti ve yalnizca birkac isim aciklandi (22 Eylul: 30'da 8).
Prompt bunu her zaman zorunlu tutuyordu, ama uyulup uyulmadigini kontrol eden
hicbir sey yoktu - arizanin gunlerce sessiz kalmasinin sebebi buydu.

Olcut, sembol basina zorunlu olan risk notudur. Ticker'i raporda saymayi denedim
ve ise yaramadi: eski (dogru) bicimde her sembol tam bir kez geciyor, yani
"az geciyor" sinyali iyi raporlari da suclu gosteriyordu. Risk notu sayisi ise
16-17 Eylul'de 30/30, 22 Eylul'de 0/30 - temiz bir ayirt edici.

Kullanim:  python src/rapor_denetle.py <bundle.json> <rapor.txt>
Cikis:     0 = her sembol islenmis, 1 = eksik var, 2 = kullanim hatasi
"""
import json
import sys

RISK_ISARETI = "Bu tabloyu ne bozar?"


def main() -> int:
    if len(sys.argv) != 3:
        print("KULLANIM: rapor_denetle.py <bundle.json> <rapor.txt>")
        return 2

    bundle_yolu, rapor_yolu = sys.argv[1], sys.argv[2]

    with open(bundle_yolu, encoding="utf-8") as f:
        bundle = json.load(f)
    with open(rapor_yolu, encoding="utf-8") as f:
        rapor = f.read()

    # Prompt, error alani dolu sembollerin atlanmasina izin veriyor.
    semboller = [
        s["symbol"] for s in bundle.get("symbols", [])
        if not s.get("error") or str(s.get("error")).lower() in ("none", "")
    ]
    beklenen = len(semboller)
    bulunan = rapor.count(RISK_ISARETI)

    print("[rapor-denetim] beklenen sembol paragrafi: %d" % beklenen)
    print("[rapor-denetim] bulunan risk notu: %d" % bulunan)

    if bulunan >= beklenen:
        print("[rapor-denetim] TAMAM: her sembol kendi paragrafini ve risk notunu almis.")
        return 0

    print(
        "[rapor-denetim] EKSIK: %d sembolden yalnizca %d tanesi kendi paragrafini almis."
        % (beklenen, bulunan)
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
