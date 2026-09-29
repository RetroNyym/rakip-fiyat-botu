"""ImportYeti site içi arama API'si (/api/search) istemcisi."""
from __future__ import annotations

import json
from urllib.parse import quote

from .ag import AgHatasi, indir

ARA_URL = "https://www.importyeti.com/api/search?q={sorgu}&sayfa={sayfa}"

# GUI / JSON şeması için: API türü -> Türkçe tür
TUR_ESLEME = {"company": "firma", "supplier": "tedarikçi"}


def ara(sorgu: str, sayfa: int = 1) -> dict:
    """Site aramasını yapar; GUI'nin beklediği JSON şemasına çevirir."""
    url = "https://www.importyeti.com/api/search?q={}&page={}".format(
        quote(sorgu), sayfa)
    ham = indir(url, debug_ad=f"arama_{sayfa}")
    try:
        veri = json.loads(ham)
    except json.JSONDecodeError as hata:
        raise AgHatasi(f"arama yanıtı JSON değil: {hata}") from hata
    return donustur(veri, sorgu, sayfa)


def donustur(veri: dict, sorgu: str, sayfa: int) -> dict:
    """API ham yanıtını GUI/JSON şemasına çevirir (ağsız test edilebilir)."""
    sonuclar = []
    for s in veri.get("searchResults", []) or []:
        slug = (s.get("url") or "").strip("/")
        if not slug:
            continue
        sonuclar.append({
            "tur": TUR_ESLEME.get(s.get("type", ""), s.get("type", "")),
            "ad": s.get("title", ""),
            "ulke": s.get("countryCode", ""),
            "adres": s.get("address", ""),
            "sefer": s.get("totalShipments"),
            "son_sefer": s.get("mostRecentShipment", ""),
            "url": slug,
        })

    return {
        "sorgu": sorgu,
        "sayfa": sayfa,
        "toplam": veri.get("totalHits"),
        "toplam_sayfa": veri.get("totalPages"),
        "kalan_hak": veri.get("requestLimitRemaining"),
        "sonuclar": sonuclar,
    }
