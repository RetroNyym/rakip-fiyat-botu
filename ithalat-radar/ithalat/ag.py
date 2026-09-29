"""Ağ katmanı: indirme + engel tespiti + debug HTML kaydı."""
from __future__ import annotations

import os
import random
import time
from pathlib import Path

UYARI = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BASLIKLAR = {
    "User-Agent": UYARI,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}


class AgHatasi(Exception):
    """İndirme başarısız ya da erişim engellendi."""


def debug_kaydet(ad: str, icerik: str) -> None:
    if os.environ.get("ITHALAT_DEBUG") != "1":
        return
    hedef = Path(__file__).resolve().parent.parent / "data" / "out"
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / f"debug_{ad}.html").write_text(icerik, encoding="utf-8",
                                            errors="replace")


def indir(url: str, debug_ad: str = "sayfa", deneme: int = 3,
          zaman_asimi: float = 30.0) -> str:
    """URL'yi indirir; engellenirse Türkçe hata fırlatır."""
    try:
        from curl_cffi import requests as istek
        fonk = istek.get
        ekstra = {"impersonate": "chrome"}
    except ImportError:
        import requests
        fonk = requests.get
        ekstra = {}

    son_hata = ""
    for i in range(deneme):
        try:
            yanit = fonk(url, headers=BASLIKLAR, timeout=zaman_asimi,
                         allow_redirects=True, **ekstra)
            kod = yanit.status_code
            metin = yanit.text
        except Exception as hata:
            son_hata = f"{type(hata).__name__}: {str(hata)[:140]}"
            if i < deneme - 1:
                time.sleep(1.0 + random.random())
                continue
            break

        if kod == 200 and metin:
            debug_kaydet(debug_ad, metin)
            return metin
        son_hata = f"HTTP {kod}"
        if kod in (401, 403):
            raise AgHatasi(f"HTTP {kod} — erişim reddedildi (bot engeli olabilir).")
        if kod == 429:
            raise AgHatasi("HTTP 429 — çok fazla istek, biraz bekleyin.")
        if i < deneme - 1:
            time.sleep(1.0 + random.random())

    ipucu = ""
    if any(x in son_hata for x in ("SSL", "Connection", "EOF")):
        ipucu = (" — ağ güvenliği TLS bağlantılarını kesiyor olabilir "
                 "(firma duvarı/VPN). Tarayıcıda da açılmıyorsa ağı kontrol edin.")
    raise AgHatasi(f"indirilemedi: {son_hata}{ipucu}")
