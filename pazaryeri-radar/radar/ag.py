"""Ağ katmanı: sayfa indirme, engel/blokaj tespiti, debug HTML kaydı."""
from __future__ import annotations

import os
import random
import time
from pathlib import Path

UYARI_METNI = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BASLIKLAR = {
    "User-Agent": UYARI_METNI,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


class AgHatasi(Exception):
    """İndirme başarısız ya da erişim engellendi."""


def _engel_tespiti(kod: int, metin: str) -> str | None:
    """Yanıt metninden bilinen engel kalıplarını arar; bulunamazsa None."""
    kucuk = metin.lower()
    if "berqnet" in kucuk or "erişim engellendi" in kucuk \
            or "erisim engellendi" in kucuk:
        return ("Ağ güvenliği duvarı sayfayı engelledi "
                "(\"Erişim engellendi\"). Bu ağa/agan politikasına bakın.")
    if "captcha" in kucuk or "güvenlik doğrulamas" in kucuk \
            or "robot olduğunuzu" in kucuk or "verify you are human" in kucuk:
        return ("Site bot doğrulaması (captcha) gösteriyor — tekrar "
                "deneyin; devam ederse VPN/farklı IP deneyin.")
    if kod in (401, 403):
        return f"HTTP {kod} — erişim reddedildi (bot engeli olabilir)."
    if kod == 429:
        return "HTTP 429 — çok fazla istek; biraz bekleyip tekrar deneyin."
    if kod == 404:
        return "HTTP 404 — adres bulunamadı (sorgu ya da URL yanlış olabilir)."
    if kod >= 500:
        return f"HTTP {kod} — sunucu tarafında hata."
    return None


def _indir_curl_cffi(url: str, zaman_asimi: float) -> tuple[int, str]:
    from curl_cffi import requests as istek

    yanit = istek.get(url, impersonate="chrome", timeout=zaman_asimi,
                      headers=BASLIKLAR, allow_redirects=True)
    return yanit.status_code, yanit.text


def _indir_requests(url: str, zaman_asimi: float) -> tuple[int, str]:
    import requests

    yanit = requests.get(url, headers=BASLIKLAR, timeout=zaman_asimi,
                         allow_redirects=True)
    return yanit.status_code, yanit.text


def debug_html_kaydet(platform: str, sayfa: int, html: str) -> None:
    """RADAR_DEBUG_HTML=1 ise sayfanın ham HTML'ini diske yazar."""
    if os.environ.get("RADAR_DEBUG_HTML") != "1":
        return
    hedef = Path(__file__).resolve().parent.parent / "data" / "out"
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / f"debug_{platform}_{sayfa}.html").write_text(
        html, encoding="utf-8", errors="replace")


def indir(url: str, platform: str = "", sayfa: int = 0,
          deneme: int = 3, zaman_asimi: float = 25.0) -> str:
    """URL'yi indirir; engellenmiş ya da ulaşılamıyorsa AgHatasi fırlatır.

    Önce curl_cffi (tarayıcı parmak izi), olmazsa requests ile dener.
    Hatalar tekrar denenir; sonunda engel nedeni Türkçe olarak bildirilir.
    """
    son_hata = ""
    for i in range(deneme):
        try:
            try:
                kod, metin = _indir_curl_cffi(url, zaman_asimi)
            except ImportError:
                kod, metin = _indir_requests(url, zaman_asimi)
        except Exception as hata:
            son_hata = (f"bağlantı hatası: {type(hata).__name__}: "
                        f"{str(hata)[:160]}")
            if i < deneme - 1:
                time.sleep(1.0 + random.random())
                continue
            break

        if kod == 200 and metin and len(metin) > 500:
            debug_html_kaydet(platform or "bilinmiyor", sayfa, metin)
            return metin

        engel = _engel_tespiti(kod, metin)
        if engel:
            raise AgHatasi(engel)
        son_hata = f"HTTP {kod} (içerik {len(metin)} bayt)"
        if i < deneme - 1:
            time.sleep(1.0 + random.random())

    ipucu = ""
    if "SSL" in son_hata or "Connection" in son_hata or "EOF" in son_hata:
        ipucu = (" — ağ güvenliği TLS bağlantılarını kesiyor olabilir "
                 "(firma duvarı/VPN). Tarayıcıda da açılmıyorsa ağı kontrol edin.")
    raise AgHatasi(f"{platform or 'sayfa'} indirilemedi: {son_hata}{ipucu}")
