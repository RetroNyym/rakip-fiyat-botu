#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rakip_takip.py — Rakip fiyat takip botu (çekirdek)
===================================================

Ne yapar:
  * config.json'daki rakip ürün sayfalarını gezer
  * Fiyatı çeker, SQLite veritabanına yazar (geçmiş oluşur)
  * Fiyat değişince Telegram'a uyarı gönderir
  * Fiyat geçmişi raporu ve grafik verisi üretir
  * Ürüne ait görselleri bulur

Bu modül hem CLI (kendi başına) hem de GUI (gui.py) tarafından kullanılır.
Tüm fonksiyonlar `log=` parametresi alır; GUI bu sayede çıktıyı
konsol yerine arayüze yönlendirebilir.

CLI:
  python rakip_takip.py                  # tarama yap
  python rakip_takip.py --rapor          # fiyat geçmişini göster
  python rakip_takip.py --inspect URL    # CSS seçici bulmaya yardımcı olur
  python rakip_takip.py --test           # Telegram bağlantısını dener
  python rakip_takip.py --config baska.json

GUI:
  python gui.py
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional
from urllib import robotparser
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Eksik paketler. Lütfen çalıştırın:\n  pip install -r requirements.txt")
    sys.exit(1)

KOK = Path(__file__).resolve().parent
VARSAYILAN_CONFIG = KOK / "config.json"
DB_YOL = KOK / "fiyatlar.db"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Para birimi işaretleri -> kod
PARA_ISARET = {
    "TL": "TL", "TRY": "TL", "₺": "TL", "TL.": "TL",
    "$": "USD", "USD": "USD", "US$": "USD",
    "€": "EUR", "EUR": "EUR",
    "£": "GBP", "GBP": "GBP",
}

# Sayı adayı: bitişik rakam/ayraç dizisi (kısmi eşleşme yapmaz)
#   '4.900,50' | '4,900.50' | '1.234.567,89' | '1990'
SAYI_RE = re.compile(r"\d[\d.,\u00a0]{0,20}\d|\d")

# İlerleme/iptal için tip kısayolları
LogFn = Callable[[str], None]
IlerlemeFn = Callable[[int, int, str], None]

LOG_VARSAYILAN: LogFn = print


def _log_al(log: Optional[LogFn]) -> LogFn:
    return log if log is not None else LOG_VARSAYILAN


# --------------------------------------------------------------------------
# Fiyat ayrıştırma
# --------------------------------------------------------------------------
def sayiyi_normalize_et(s: str) -> float:
    """'4.900,50' -> 4900.50  |  '4,900.50' -> 4900.50  |  '1.900' -> 1900"""
    s = s.replace("\u00a0", "").replace(" ", "")
    if "." in s and "," in s:
        # sağdaki olan ondalık ayracıdır
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # sonu 1-2 haneliyse ondalık, değilse binlik
        if re.search(r",\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        if not re.search(r"\.\d{1,2}$", s):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def para_bul(meta: str) -> str | None:
    if not meta:
        return None
    ust = meta.upper()
    for isaret, kod in PARA_ISARET.items():
        if isaret.upper() in ust:
            return kod
    return None


def fiyat_ayristir(metin: str) -> tuple[float | None, str | None]:
    """Serbest metinden (fiyat, para birimi) üretir.

    Para birimi işareti varsa, o işarete EN YAKIN sayıyı seçer.
    '200x300 halı 1.750,00 TL' -> 1750.00 (200 değil)
    'Ürün Kodu 5544 - TL 89,90' -> 89.90 (5544 değil)
    """
    if not metin:
        return None, None
    metin = metin.replace("\u00a0", " ")
    para = para_bul(metin)

    tum_eslesmeler = list(SAYI_RE.finditer(metin))
    if not tum_eslesmeler:
        return None, para

    # Para birimi işaretinin konumunu bul (başlangıç ve bitiş)
    isaret_bas, isaret_son = None, None
    for isaret in PARA_ISARET:
        k = metin.upper().find(isaret.upper())
        if k != -1:
            isaret_bas, isaret_son = k, k + len(isaret)
            break

    if isaret_bas is not None:
        # İşarete EN YAKIN adayı seç (aradaki boşluk = mesafe)
        en_iyisi, en_kucuk = None, None
        for m in tum_eslesmeler:
            if m.end() <= isaret_bas:          # sayı işareten önce
                bosluk = isaret_bas - m.end()
            elif m.start() >= isaret_son:      # sayı işareten sonra
                bosluk = m.start() - isaret_son
            else:
                bosluk = 0
            if bosluk > 40:
                continue
            # eşitlikte önce gelen (sol taraftaki) tercih edilir
            skor = (bosluk, m.start())
            if en_kucuk is None or skor < en_kucuk:
                en_kucuk = skor
                en_iyisi = m
        if en_iyisi is not None:
            aday = sayiyi_normalize_et(en_iyisi.group(0))
            if aday >= 1:
                return aday, para

    # Para birimi yoksa: fiyat benzeri adayları önceliklendir
    # (ondalık kesir içerenler, ör. '49,90' -> '12' yerine tercih edilir)
    oncelikli, digerleri = [], []
    for m in tum_eslesmeler:
        ham = m.group(0)
        aday = sayiyi_normalize_et(ham)
        if aday < 1:
            continue
        if re.search(r"[.,]\d{1,2}$", ham):
            oncelikli.append(aday)
        else:
            digerleri.append(aday)

    for aday in (oncelikli or digerleri):
        return aday, para
    return None, para


def fiyat_bicimle(deger: Optional[float], para: str = "") -> str:
    """4900.5, 'TL' -> '4.900,50 TL' (Türkçe biçim)"""
    if deger is None:
        return "—"
    metin = f"{deger:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{metin} {para}".strip()


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
SEMBOL_CONFIG = KOK / "config.ornek.json"


def config_oku(yol: str | Path) -> dict:
    """Config okur. utf-8-sig: Windows'un yazdığı BOM karakterini yok sayar.

    İlk çalıştırmada `config.json` yoksa, varsa şablon `config.ornek.json`
    kopyalanır — böylece yeni kullanıcı boş config ile karşılaşmaz.
    """
    yol = Path(yol)
    if not yol.exists():
        if yol.name == "config.json" and SEMBOL_CONFIG.exists():
            import shutil
            shutil.copyfile(SEMBOL_CONFIG, yol)
        else:
            raise FileNotFoundError(f"Config bulunamadı: {yol}")
    with open(yol, encoding="utf-8-sig") as f:
        return json.load(f)


def config_kaydet(config: dict, yol: str | Path) -> None:
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Ağ
# --------------------------------------------------------------------------
def oturum_ac() -> requests.Session:
    oturum = requests.Session()
    oturum.headers.update({
        "User-Agent": UA,
        "Accept-Language": "tr-TR,tr;q=0.9",
    })
    return oturum


def robots_izin_var_mi(url: str, oturum: requests.Session,
                       log: Optional[LogFn] = None) -> bool:
    """robots.txt kontrolü. Okunamazsa geçer (uyarı verilir)."""
    log = _log_al(log)
    try:
        parse = robotparser.RobotFileParser()
        parca = urlparse(url)
        parse.set_url(f"{parca.scheme}://{parca.netloc}/robots.txt")
        parse.read()
        return parse.can_fetch(UA, url)
    except Exception as hata:
        log(f"  [!] robots.txt okunamadı ({hata}), devam ediliyor.")
        return True


def sayfayi_cekir(url: str, oturum: requests.Session, bekleme: float = 3.0,
                  log: Optional[LogFn] = None) -> str:
    log = _log_al(log)
    for deneme in range(1, 4):
        try:
            yanit = oturum.get(url, timeout=25)
            yanit.raise_for_status()
            # Kodlama tahmini (site charset vermezse bozuk çıkar)
            if not yanit.encoding or yanit.encoding.lower() == "iso-8859-1":
                yanit.encoding = yanit.apparent_encoding
            return yanit.text
        except Exception as hata:
            if deneme == 3:
                raise
            log(f"  [!] Deneme {deneme} başarısız: {hata} — tekrar deneniyor")
            time.sleep(bekleme * deneme)
    return ""


# --------------------------------------------------------------------------
# Veritabanı
# --------------------------------------------------------------------------
def db_ac(yol: Path | None = None) -> sqlite3.Connection:
    bag = sqlite3.connect(yol or DB_YOL)
    bag.execute(
        """
        CREATE TABLE IF NOT EXISTS fiyatlar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            zaman      TEXT    NOT NULL,
            ad         TEXT    NOT NULL,
            url        TEXT    NOT NULL,
            fiyat      REAL,
            para       TEXT,
            ham        TEXT,
            UNIQUE(ad, zaman)
        )
        """
    )
    bag.commit()
    return bag


def son_fiyat(bag: sqlite3.Connection, ad: str) -> tuple[Optional[float], str, Optional[str]]:
    satir = bag.execute(
        "SELECT fiyat, para, zaman, ham FROM fiyatlar "
        "WHERE ad = ? ORDER BY id DESC LIMIT 1",
        (ad,),
    ).fetchone()
    if not satir:
        return None, "", None
    return satir[0], satir[1], satir[2]


def kaydet(bag: sqlite3.Connection, ad: str, url: str,
           fiyat: Optional[float], para: Optional[str], ham: str,
           gun: Optional[str] = None) -> None:
    zaman = gun or datetime.now().strftime("%Y-%m-%d")
    try:
        bag.execute(
            "INSERT INTO fiyatlar (zaman, ad, url, fiyat, para, ham) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (zaman, ad, url, fiyat, para, (ham or "")[:300]),
        )
        bag.commit()
    except sqlite3.IntegrityError:
        # Aynı gün aynı ürün için zaten kayıt var → atla (günlük granülerlik)
        pass


def fiyat_gecmisi(ad: str, gun: int = 90, db_yol: Path | None = None) -> list[tuple]:
    """[(zaman, fiyat, para), ...] — eski -> yeni."""
    if not (db_yol or DB_YOL).exists():
        return []
    bag = db_ac(db_yol)
    baslangic = (datetime.now() - timedelta(days=gun)).strftime("%Y-%m-%d")
    satirlar = bag.execute(
        "SELECT zaman, fiyat, para FROM fiyatlar "
        "WHERE ad = ? AND zaman >= ? ORDER BY zaman",
        (ad, baslangic),
    ).fetchall()
    bag.close()
    return satirlar


def tum_ucretler(db_yol: Path | None = None) -> list[tuple]:
    """Tüm kayıtlar (rapor/istatistik için)."""
    if not (db_yol or DB_YOL).exists():
        return []
    bag = db_ac(db_yol)
    satirlar = bag.execute(
        "SELECT zaman, ad, fiyat, para FROM fiyatlar ORDER BY ad, zaman"
    ).fetchall()
    bag.close()
    return satirlar


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------
def telegram_gonder(ayar: dict, mesaj: str,
                    log: Optional[LogFn] = None) -> bool:
    log = _log_al(log)
    token = (ayar.get("telegram_token") or "").strip()
    chat_id = (ayar.get("telegram_chat_id") or "").strip()
    if not token or not chat_id:
        return False
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": mesaj, "parse_mode": "HTML"},
            timeout=20,
        )
        return True
    except Exception as hata:
        log(f"  [!] Telegram hatası: {hata}")
        return False


# --------------------------------------------------------------------------
# Fiyat / görsel bulma yardımcıları
# --------------------------------------------------------------------------
def serbest_fiyat_bul(corba: BeautifulSoup) -> tuple[Optional[float], Optional[str], str]:
    """Seçici yoksa sayfadaki fiyat benzeri metinleri tarar."""
    adaylar = []
    for etiket in corba.find_all(string=SAYI_RE):
        metin = str(etiket).strip()
        if not metin or len(metin) > 60:
            continue
        # para birimi işareti içerenleri öne al
        skor = 2 if para_bul(metin) else 1
        fiyat, para = fiyat_ayristir(metin)
        if fiyat:
            adaylar.append((skor, fiyat, para, metin))
    if not adaylar:
        return None, None, ""
    adaylar.sort(key=lambda x: x[0], reverse=True)
    _, fiyat, para, metin = adaylar[0]
    return fiyat, para, metin


def seciciden_fiyat_bul(corba: BeautifulSoup, secici: str
                        ) -> tuple[Optional[float], Optional[str], str]:
    """Verilen CSS seçicisinden fiyat okur. Seçici boşsa serbest arama yapar."""
    if not secici:
        return serbest_fiyat_bul(corba)
    try:
        bulunan = corba.select_one(secici)
    except Exception:
        return None, None, ""
    if not bulunan:
        return None, None, ""
    ham = bulunan.get_text(" ", strip=True)
    fiyat, para = fiyat_ayristir(ham)
    return fiyat, para, ham


def secici_adaylari(corba: BeautifulSoup, limit: int = 40) -> list[dict]:
    """Sayfadaki fiyat olası elementleri — GUI seçici bulucu için."""
    sonuclar: list[dict] = []
    gorulen = set()
    for etiket in corba.find_all(string=SAYI_RE):
        metin = str(etiket).strip()
        if not metin or len(metin) > 60:
            continue
        fiyat, para = fiyat_ayristir(metin)
        if not fiyat or fiyat < 1:
            continue

        ust = etiket.parent
        sinif = ust.get("class") or []
        secici = ust.name or "div"
        if sinif:
            secici += "." + ".".join(str(s) for s in sinif)
        elif ust.get("id"):
            secici += "#" + ust.get("id")

        # Güçlü sinyal: ya para birimi var ya da seçicide 'price' geçiyor
        guclu = bool(para) or bool(
            re.search(r"price|fiyat|cost|tutar|maliyet|urun|product", secici, re.I)
        )
        if not guclu:
            continue
        if secici in gorulen:
            continue
        gorulen.add(secici)

        sonuclar.append({
            "secici": secici,
            "fiyat": fiyat,
            "para": para or "",
            "metin": metin,
            "guclu": guclu,
        })
        if len(sonuclar) >= limit:
            break
    # güçlü olanlar önce
    sonuclar.sort(key=lambda x: (not x["guclu"], -x["fiyat"]))
    return sonuclar


def gorselleri_bul(url: str, oturum: Optional[requests.Session] = None,
                   bekleme: float = 2.0, limit: int = 20,
                   log: Optional[LogFn] = None) -> list[str]:
    """Sayfadaki görsel URL'lerini bulur (önce og:image / ürün görselleri)."""
    log = _log_al(log)
    oturum = oturum or oturum_ac()
    try:
        html = sayfayi_cekir(url, oturum, bekleme, log)
    except Exception as hata:
        log(f"  [!] Görsel sayfası çekilemedi: {hata}")
        return []

    corba = BeautifulSoup(html, "html.parser")
    sira: list[str] = []

    # 1) Sosyal/ürün meta görselleri en güvenilir
    for etiket in corba.find_all("meta", attrs={"property": True}):
        ozellik = (etiket.get("property") or "").lower()
        if ozellik in ("og:image", "og:image:secure_url", "twitter:image"):
            icerik = etiket.get("content")
            if icerik:
                sira.append(urljoin(url, icerik))

    # 2) Ürün görselleri (class/id içinde 'product','urun','gallery','main')
    for img in corba.find_all("img", src=True):
        src = img.get("src") or ""
        ipucu = " ".join([
            " ".join(img.get("class") or []),
            img.get("id") or "",
            img.get("alt") or "",
            src,
        ])
        if re.search(r"product|urun|main|gallery|hero|detail|zoom", ipucu, re.I):
            sira.append(urljoin(url, src))

    # 3) Diğer görseller
    for img in corba.find_all("img", src=True):
        sira.append(urljoin(url, img.get("src")))

    # Temizle: data: URI ve logo/icon benzeri küçük dosyaları ele
    temiz: list[str] = []
    gorulen = set()
    for g in sira:
        if not g.startswith(("http://", "https://")) or g in gorulen:
            continue
        if g.startswith("data:"):
            continue
        if re.search(r"logo|icon|favicon|sprite|avatar|placeholder|blank|pixel",
                     g, re.I):
            continue
        gorulen.add(g)
        temiz.append(g)
        if len(temiz) >= limit:
            break
    return temiz


def gorseli_indir(url: str, oturum: Optional[requests.Session] = None,
                  hedef: Path | None = None) -> Optional[Path]:
    """Görseli indirir, yerel dosya yolunu döndürür. Başarısızsa None."""
    oturum = oturum or oturum_ac()
    try:
        yanit = oturum.get(url, timeout=25)
        yanit.raise_for_status()
    except Exception:
        return None

    tip = (yanit.headers.get("Content-Type") or "").lower()
    uzanti = ".png"
    if "jpeg" in tip or "jpg" in tip:
        uzanti = ".jpg"
    elif "webp" in tip:
        uzanti = ".webp"
    elif "gif" in tip:
        uzanti = ".gif"
    elif "svg" in tip:
        uzanti = ".svg"

    hedef = hedef or (KOK / ".gorseller" / f"gorsel_{int(time.time())}{uzanti}")
    hedef.parent.mkdir(exist_ok=True)
    try:
        hedef.write_bytes(yanit.content)
        return hedef
    except Exception:
        return None


# --------------------------------------------------------------------------
# Tarama
# --------------------------------------------------------------------------
def tarama_yap(config: dict,
               log: Optional[LogFn] = None,
               ilerleme: Optional[IlerlemeFn] = None,
               iptal: Optional[Callable[[], bool]] = None,
               db_yol: Path | None = None,
               secili_urunler: Optional[list[str]] = None) -> list[dict]:
    """Ürünleri tarar.

    Dönen liste, her ürün için dict:
      ad, url, fiyat, para, onceki, yuzde, durum, mesaj

    durum: 'ilk' | 'degismedi' | 'degisti' | 'bulunamadi'
           | 'robots' | 'hata' | 'iptal'
    """
    log = _log_al(log)
    ayar = config.get("ayarlar", {})
    urunler = config.get("urunler", [])

    if secili_urunler:
        urunler = [u for u in urunler if (u.get("ad") or u.get("url")) in secili_urunler]

    sonuclar: list[dict] = []
    if not urunler:
        log("Taranacak ürün yok. Önce ürün ekleyin.")
        return sonuclar

    bekleme = float(ayar.get("bekleme_saniye", 3))
    esik = float(ayar.get("esik_yuzde", 0))  # 0 = her değişimde uyarı

    oturum = oturum_ac()
    bag = db_ac(db_yol)
    uyari_satirlari: list[str] = []
    toplam = len(urunler)

    log(f"\n{toplam} ürün taranıyor...\n")

    for i, u in enumerate(urunler, start=1):
        if iptal and iptal():
            log("⛔ Tarama iptal edildi.")
            for kalan in sonuclar:
                kalan.setdefault("durum", "iptal")
            sonuclar.append({"ad": "", "url": "", "durum": "iptal",
                             "mesaj": "İptal edildi"})
            break

        ad = u.get("ad") or u.get("url") or ""
        url = u.get("url")
        secici = u.get("selector") or ""

        if ilerleme:
            ilerleme(i, toplam, ad)

        kayit = {"ad": ad, "url": url or "", "fiyat": None, "para": "",
                 "onceki": None, "yuzde": None, "durum": "", "mesaj": ""}
        sonuclar.append(kayit)

        log(f"• {ad}")
        if not url:
            log("  [!] 'url' eksik, atlandı.")
            kayit["durum"] = "hata"
            kayit["mesaj"] = "URL eksik"
            continue

        try:
            if not robots_izin_var_mi(url, oturum, log):
                log("  [!] robots.txt izin vermiyor, atlandı.")
                kayit["durum"] = "robots"
                kayit["mesaj"] = "robots.txt izin vermiyor"
                continue

            html = sayfayi_cekir(url, oturum, bekleme, log)
            corba = BeautifulSoup(html, "html.parser")
            fiyat, para, ham = seciciden_fiyat_bul(corba, secici)

            if fiyat is None:
                log("  [!] Fiyat bulunamadı — seçiciyi kontrol edin (Seçici Bul).")
                kayit["durum"] = "bulunamadi"
                kayit["mesaj"] = "Fiyat bulunamadı"
                continue

            onceki, _onceki_para, _on = son_fiyat(bag, ad)
            kaydet(bag, ad, url, fiyat, para, ham)

            kayit.update({
                "fiyat": fiyat,
                "para": para or "",
                "onceki": onceki,
                "durum": "ilk" if onceki is None else "",
            })

            if onceki is None:
                log(f"  → İlk kayıt: {fiyat_bicimle(fiyat, para)}")
                kayit["durum"] = "ilk"
                kayit["mesaj"] = "İlk kayıt"
            elif abs(onceki - fiyat) < 0.01:
                log(f"  → Değişmedi: {fiyat_bicimle(fiyat, para)}")
                kayit["durum"] = "degismedi"
                kayit["mesaj"] = "Değişmedi"
            else:
                fark = fiyat - onceki
                yuzde = (fark / onceki) * 100
                ok = "▲" if fark > 0 else "▼"
                log(f"  {ok} DEĞİŞTİ: {fiyat_bicimle(onceki, para)} → "
                    f"{fiyat_bicimle(fiyat, para)} ({yuzde:+.1f}%)")
                kayit.update({"durum": "degisti", "yuzde": yuzde,
                              "mesaj": f"{ok} {yuzde:+.1f}%"})

                if esik <= 0 or abs(yuzde) >= esik:
                    uyari_satirlari.append(
                        f"<b>{ok} {ad}</b>\n"
                        f"{fiyat_bicimle(onceki, para)} → {fiyat_bicimle(fiyat, para)} "
                        f"({yuzde:+.1f}%)\n{url}"
                    )

        except Exception as hata:
            log(f"  [!] Hata: {hata}")
            kayit["durum"] = "hata"
            kayit["mesaj"] = str(hata)
        finally:
            if i < toplam:
                time.sleep(bekleme)

    bag.close()

    # Özet
    degisen = [k for k in sonuclar if k["durum"] == "degisti"]
    log("")
    if degisen:
        log(f"📊 {len(degisen)} fiyat değişikliği bulundu.")
        if uyari_satirlari:
            mesaj = "🔔 <b>Rakip fiyat değişikliği</b>\n\n" + "\n\n".join(uyari_satirlari)
            if telegram_gonder(ayar, mesaj, log):
                log(f"✅ {len(degisen)} değişiklik Telegram'a gönderildi.")
            else:
                log("⚠️ Değişiklikler var ama Telegram ayarlanmamış "
                    "(Ayarlar → Telegram).")
    else:
        log("Fiyat değişikliği yok.")

    if ilerleme:
        ilerleme(toplam, toplam, "Bitti")

    return sonuclar


# --------------------------------------------------------------------------
# Seçici bulma (inspect)
# --------------------------------------------------------------------------
def secici_bul(url: str, log: Optional[LogFn] = None,
               bekleme: float = 2.0) -> list[dict]:
    """URL'deki fiyat olası elementleri listeler. GUI'nin 'Seçici Bul' butonu."""
    log = _log_al(log)
    oturum = oturum_ac()
    log(f"{url} indiriliyor, fiyat olası elementler aranıyor...")
    try:
        html = sayfayi_cekir(url, oturum, bekleme, log)
    except Exception as hata:
        log(f"Hata: {hata}")
        return []

    corba = BeautifulSoup(html, "html.parser")
    sonuclar = secici_adaylari(corba)
    if not sonuclar:
        log("Güçlü fiyat adayı bulunamadı. Sayfa JavaScript ile yükleniyor olabilir.")
        return sonuclar

    log(f"{len(sonuclar)} aday bulundu:")
    for s in sonuclar:
        log(f"  fiyat={fiyat_bicimle(s['fiyat'], s['para']):<16} seçici: {s['secici']}")
        log(f"    metin: {s['metin']}")
    return sonuclar


# --------------------------------------------------------------------------
# Rapor
# --------------------------------------------------------------------------
def rapor_verisi(config: dict, gun: int = 30,
                 db_yol: Path | None = None) -> list[dict]:
    """Rapor için veri üretir (GUI ve CLI ortak kullanır)."""
    if not (db_yol or DB_YOL).exists():
        return []
    bag = db_ac(db_yol)
    baslangic = (datetime.now() - timedelta(days=gun)).strftime("%Y-%m-%d")
    urunler = config.get("urunler", [])
    cikti: list[dict] = []

    for u in urunler:
        ad = u.get("ad") or u.get("url")
        satirlar = bag.execute(
            "SELECT zaman, fiyat, para FROM fiyatlar "
            "WHERE ad = ? AND zaman >= ? ORDER BY zaman",
            (ad, baslangic),
        ).fetchall()
        if not satirlar:
            continue
        fiyatlar = [s[1] for s in satirlar if s[1] is not None]
        if not fiyatlar:
            continue
        en_dusuk, en_yuksek = min(fiyatlar), max(fiyatlar)
        ilk = fiyatlar[0]
        son = fiyatlar[-1]
        toplam_degisim = ((son - ilk) / ilk * 100) if ilk else 0.0
        aralik = ((en_yuksek - en_dusuk) / en_dusuk * 100) if en_dusuk else 0.0
        cikti.append({
            "ad": ad,
            "url": u.get("url", ""),
            "para": satirlar[0][2] or "",
            "kayit_sayisi": len(fiyatlar),
            "ilk": ilk,
            "son": son,
            "en_dusuk": en_dusuk,
            "en_yuksek": en_yuksek,
            "toplam_degisim": toplam_degisim,
            "aralik": aralik,
            "satirlar": satirlar,
        })
    bag.close()
    return cikti


def rapor_yazdir(config: dict, gun: int = 30,
                 log: Optional[LogFn] = None,
                 db_yol: Path | None = None) -> None:
    """CLI için düz metin rapor."""
    log = _log_al(log)
    veri = rapor_verisi(config, gun, db_yol)
    if not veri:
        log("Henüz veri yok. Önce tarama çalıştırın.")
        return

    log(f"\n=== Son {gun} günün fiyat raporu ===\n")
    for r in veri:
        log(f"• {r['ad']}")
        for zaman, fiyat, _p in r["satirlar"]:
            log(f"    {zaman}  {fiyat_bicimle(fiyat, r['para']):>16}")
        log(f"    İlk: {fiyat_bicimle(r['ilk'], r['para'])}   "
            f"Son: {fiyat_bicimle(r['son'], r['para'])}")
        log(f"    Aralık: {fiyat_bicimle(r['en_dusuk'], r['para'])} – "
            f"{fiyat_bicimle(r['en_yuksek'], r['para'])} "
            f"(±{r['aralik']:.1f}%)\n")


# --------------------------------------------------------------------------
# Telegram testi
# --------------------------------------------------------------------------
def test_telegram(config: dict, log: Optional[LogFn] = None) -> bool:
    log = _log_al(log)
    ayar = config.get("ayarlar", {})
    if telegram_gonder(ayar, "✅ Rakip fiyat botu bağlantı testi başarılı.", log):
        log("Telegram çalışıyor.")
        return True
    log("Telegram gönderilemedi. 'telegram_token' ve 'telegram_chat_id' "
        "alanlarını kontrol edin.\n"
        "Token: BotFather'dan alınır. Chat ID: @userinfobot'a yazarak.")
    return False


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description="Rakip fiyat takip botu")
    p.add_argument("--config", default=str(VARSAYILAN_CONFIG))
    p.add_argument("--rapor", action="store_true", help="Fiyat geçmişini göster")
    p.add_argument("--inspect", metavar="URL", help="CSS seçici bul")
    p.add_argument("--test", action="store_true", help="Telegram testi")
    p.add_argument("--gun", type=int, default=30, help="Rapor gün aralığı")
    args = p.parse_args()

    try:
        config = config_oku(args.config)
    except FileNotFoundError as hata:
        print(hata)
        sys.exit(1)
    except json.JSONDecodeError as hata:
        print(f"Config okunamadı (JSON hatası): {hata}")
        sys.exit(1)

    if args.inspect:
        secici_bul(args.inspect)
    elif args.rapor:
        rapor_yazdir(config, args.gun)
    elif args.test:
        test_telegram(config)
    else:
        tarama_yap(config)


if __name__ == "__main__":
    main()
