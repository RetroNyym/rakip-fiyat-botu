"""Firma (/company/…) ve tedarikçi (/supplier/…) sayfası ayrıştırma.

ImportYeti sayfaları sunucu tarafında render edilir; gerekli veriler:
  * <title>  -> "Nike - 1 Bowerman Dr… - company Report - Import Yeti"
  * tablo 0  -> Tedarikçiler (firma sayfası) / Müşteriler (tedarikçi sayfası)
       hücre 0: isim linki (/supplier/x veya /company/x) + lokasyon linkleri
       hücre 2: "188 Footwear Apparel - knitted …" (sefer sayısı + ürün grupları)
  * [Country, Shipments] tabloları -> ülkelere göre dağılım
  * [Date, Bill of Lading, …] tablosu -> son sevkiyatlar
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .ag import indir

TABAN = "https://www.importyeti.com"
_SAYI = re.compile(r"(\d[\d.,]*)")


def _basligi_coz(title: str) -> tuple[str, str]:
    """'<ad> - <adres> - company Report - Import Yeti' -> (ad, adres)."""
    parcalar = [p.strip() for p in re.split(r"\s*-\s*", title) if p.strip()]
    if not parcalar:
        return "", ""
    ad = parcalar[0]
    adres = parcalar[1] if len(parcalar) > 1 else ""
    return ad, adres


def _sayi_deger(metin: str) -> int | None:
    eslesme = _SAYI.search(metin or "")
    if not eslesme:
        return None
    temiz = eslesme.group(1).replace(".", "").replace(",", "")
    try:
        return int(temiz)
    except ValueError:
        return None


def _satirlari_oku(tablo) -> list[dict]:
    """Tedarikçi/Müşteri tablosunun satırlarını okur."""
    satirlar = []
    for tr in tablo.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        t0 = tds[0]
        isim_linki = t0.find("a", href=re.compile(r"^/(?:supplier|company)/"))
        if not isim_linki:
            continue
        slug = isim_linki["href"].strip("/")
        ad = isim_linki.get_text(" ", strip=True)

        ulke = ""
        for a in t0.find_all("a", href=True):
            if a["href"].endswith("/country"):
                ulke = a.get_text(" ", strip=True)
                break
        if not ulke:
            lokasyonlar = t0.find_all("a", href=re.compile(r"^/location/"))
            if lokasyonlar:
                ulke = lokasyonlar[-1].get_text(" ", strip=True)

        tel_text = tds[2].get_text(" ", strip=True)
        sefer = _sayi_deger(tel_text)
        urunler = ""
        if sefer is not None:
            kalan = tel_text[len(str(sefer)):].strip()
            urunler = kalan
        else:
            urunler = tel_text

        satirlar.append({"ad": ad, "slug": slug, "ulke": ulke,
                         "sefer": sefer, "urunler": urunler,
                         "url": slug})
    return satirlar


def _ulkeleri_oku(soup: BeautifulSoup) -> list[dict]:
    ulkeler = []
    for tablo in soup.find_all("table"):
        basliklar = [th.get_text(" ", strip=True).lower()
                     for th in tablo.find_all("th")]
        if len(basliklar) == 2 and basliklar[0].startswith("country") \
                and basliklar[1].startswith("shipment"):
            for tr in tablo.find_all("tr")[1:]:
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    ad = tds[0].get_text(" ", strip=True)
                    sefer = _sayi_deger(tds[1].get_text(" ", strip=True))
                    if ad:
                        ulkeler.append({"ulke": ad, "sefer": sefer})
    return ulkeler


def _son_sevkiyetleri_oku(soup: BeautifulSoup) -> list[dict]:
    sonuc = []
    for tablo in soup.find_all("table"):
        basliklar = [th.get_text(" ", strip=True).lower()
                     for th in tablo.find_all("th")]
        if not basliklar or not basliklar[0].startswith("date"):
            continue
        for tr in tablo.find_all("tr")[1:11]:
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            metinler = [td.get_text(" ", strip=True) for td in tds]
            sonuc.append({
                "tarih": metinler[0],
                "bol": metinler[1],
                "ulke": metinler[2],
                "agirlik": metinler[3],
                "miktar": metinler[4],
                "aciklama": metinler[6] if len(metinler) > 6 else "",
            })
        break
    return sonuc


def sayfa_al(slug: str) -> dict:
    """company/<x> ya da supplier/<x> sayfasını indirir/ayırt eder."""
    slug = _slugi_temizle(slug)
    url = f"{TABAN}/{slug}"
    ham = indir(url, debug_ad=slug.replace("/", "_"))
    return ayristir(ham, slug)


def _slugi_temizle(slug: str) -> str:
    slug = slug.strip().strip("/")
    if slug.startswith(("http://", "https://")):
        slug = slug.split("importyeti.com/", 1)[-1].strip("/")
    if not slug.startswith(("company/", "supplier/")):
        raise ValueError("slug 'company/…' ya da 'supplier/…' ile başlamalı")
    return slug


def ayristir(ham: str, slug: str) -> dict:
    """HTML metnini sözlüğe çevirir (ağsız test edilebilir)."""
    soup = BeautifulSoup(ham, "html.parser")

    baslik = soup.title.get_text(" ", strip=True) if soup.title else ""
    ad, adres = _basligi_coz(baslik)

    tablolar = soup.find_all("table")
    satirlar = _satirlari_oku(tablolar[0]) if tablolar else []

    tur = "firma" if slug.startswith("company/") else "tedarikçi"
    son_sevkiyats = _son_sevkiyetleri_oku(soup)
    ulkeler = _ulkeleri_oku(soup)
    return {
        "tur": tur,
        "slug": slug,
        "ad": ad,
        "adres": adres,
        "url": slug,
        "satirlar": satirlar,
        "ulkeler": ulkeler,
        "son_sevkiyats": son_sevkiyats,
        "ozet": {
            "bagli_sayisi": len(satirlar),
            "ulke_sayisi": len({u["ulke"] for u in ulkeler if u["ulke"]}),
            "son_sevkiyat": son_sevkiyats[0]["tarih"] if son_sevkiyats else "",
        },
    }
