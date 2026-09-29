"""Listelemeleri satıcı bazında toplar; GUI'nin beklediği JSON üretir."""
from __future__ import annotations

from .ayristir import Listeleme

# Satış / yorum oranı tahmini (TR pazaryerleri için geniş güven aralığı)
YORUM_BASINA_SATIS = 10


def _satici_anahtari(item: Listeleme) -> str:
    if item.satici:
        return item.satici.strip().lower()
    return f"__bilinmiyor__{item.platform}"


def satirlari_uret(listelemler: list[Listeleme],
                   engellenen: dict[str, str]) -> tuple[list[dict], dict]:
    """Listelemeleri sıralanmış satıcı satırlarına çevirir."""
    gruplar: dict[tuple[str, str], dict] = {}
    for item in listelemler:
        anahtar = (item.platform, _satici_anahtari(item))
        g = gruplar.setdefault(anahtar, {
            "platform": item.platform,
            "satici": item.satici or "Bilinmeyen satıcı",
            "listeleme": 0,
            "yorum": 0,
            "rozetli": 0,
            "rozet_toplam": 0,
            "fiyatlar": [],
            "satici_biliniyor": bool(item.satici),
        })
        g["listeleme"] += 1
        g["yorum"] += item.yorum
        if item.satis_rozet:
            g["rozetli"] += 1
            g["rozet_toplam"] += item.satis_rozet
        if item.fiyat:
            g["fiyatlar"].append(item.fiyat)

    toplam_listeleme = sum(g["listeleme"] for g in gruplar.values())
    if not gruplar:
        return [], _ozet([], 0, engellenen)

    for g in gruplar.values():
        fiyatlar = g.pop("fiyatlar")
        ort_fiyat = (sum(fiyatlar) / len(fiyatlar)) if fiyatlar else 0.0

        if g["rozet_toplam"]:
            alt = g["rozet_toplam"]
        else:
            alt = g["yorum"]
        ust = max(alt, g["yorum"] * YORUM_BASINA_SATIS)

        g["units_lo"] = int(alt)
        g["units_hi"] = int(ust)
        g["revenue_lo"] = int(round(alt * ort_fiyat))
        g["revenue_hi"] = int(round(ust * ort_fiyat))
        g["share_listings"] = (round(g["listeleme"] / toplam_listeleme * 100, 1)
                               if toplam_listeleme else 0.0)

        if not g["satici_biliniyor"]:
            g["confidence"] = "Düşük"
        elif g["rozetli"] >= max(1, g["listeleme"] // 2):
            g["confidence"] = "Yüksek"
        else:
            g["confidence"] = "Orta"
        g.pop("satici_biliniyor")

    sirali = sorted(gruplar.values(),
                    key=lambda g: (g["listeleme"], g["yorum"]), reverse=True)
    satirlar = []
    for i, g in enumerate(sirali, start=1):
        satirlar.append({
            "rank": i,
            "seller_name": g["satici"],
            "platform": g["platform"],
            "marketplace": g["platform"],
            "listings": g["listeleme"],
            "share_listings": g["share_listings"],
            "reviews": g["yorum"],
            "badge_products": g["rozetli"],
            "units_lo": g["units_lo"],
            "units_hi": g["units_hi"],
            "revenue_lo": g["revenue_lo"],
            "revenue_hi": g["revenue_hi"],
            "confidence": g["confidence"],
        })
    return satirlar, _ozet(satirlar, toplam_listeleme, engellenen)


def _ozet(satirlar: list[dict], toplam: int,
          engellenen: dict[str, str]) -> dict:
    return {
        "products_total": toplam,
        "sellers": len(satirlar),
        "units_lo": sum(s["units_lo"] for s in satirlar),
        "units_hi": sum(s["units_hi"] for s in satirlar),
        "engellenen_platformlar": dict(engellenen),
    }
