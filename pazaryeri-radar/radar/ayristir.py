"""HTML ayrıştırma — trendyol / n11 / hepsiburada arama sayfaları.

Her platform için katmanlı yaklaşım uygulanır:
  1) Ürün kartı seçicileri (birden fazla aday denenir, en çok sonucu
     veren kazanır),
  2) Kart içinde alan seçicileri (ad, fiyat, satıcı, yorum, rozet, link),
  3) Kart metnindeki kalıplar ("Satıcı: …", "Mağaza: …", "…+ Satan",
     "₺" fiyat regex'i),
  4) Kart attribute'ları (data-merchant-name vb.).

Sayfa yapısı değişirse kart bulunamaz; çağıran kod bunu açıkça raporlar.
"""
from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
#  Veri modeli
# --------------------------------------------------------------------------
@dataclass
class Listeleme:
    platform: str
    ad: str = ""
    fiyat: float | None = None
    satici: str | None = None
    yorum: int = 0
    puan: float | None = None
    satis_rozet: int | None = None   # "5.000+ Satan" gibi rozet sayısı
    url: str = ""
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
#  Yardımcılar
# --------------------------------------------------------------------------
def sayiyi_coz(metin: str | None) -> float | None:
    """'1.234', '12,5', '500+', '1,2 Bin+' → sayı (yoksa None)."""
    if not metin:
        return None
    temiz = str(metin).strip()
    carpan = 1.0
    kucuk = temiz.lower().replace(" ", "")
    if kucuk.endswith("bin+") or kucuk.endswith("bin"):
        carpan, kucuk = 1_000.0, kucuk.rstrip("+")
        kucuk = kucuk[:-3] if kucuk.endswith("bin") else kucuk
    elif kucuk.endswith("mn+") or kucuk.endswith("mn") \
            or kucuk.endswith("m+") or kucuk.endswith("m"):
        carpan = 1_000_000.0
        kucuk = re.sub(r"(mn|m)\+?$", "", kucuk)
    kucuk = kucuk.rstrip("+")
    kucuk = kucuk.replace(".", "").replace(",", ".")
    eslesme = re.search(r"\d+(\.\d+)?", kucuk)
    if not eslesme:
        return None
    try:
        return float(eslesme.group()) * carpan
    except ValueError:
        return None


def para_coz(metin: str | None) -> float | None:
    """Fiyat metninden TL tutarını çözer: '1.299,90 TL' → 1299.90"""
    if not metin:
        return None
    temiz = str(metin).replace("TL", "").replace("₺", "").strip()
    eslesme = re.search(r"(\d{1,3}(?:\.\d{3})+,\d{1,2}|\d+,\d{1,2}"
                        r"|\d{1,3}(?:\.\d{3})+|\d+)", temiz)
    if not eslesme:
        return None
    sayi = eslesme.group()
    if "," in sayi:
        sayi = sayi.replace(".", "").replace(",", ".")
    else:
        sayi = sayi.replace(".", "")
    try:
        return float(sayi)
    except ValueError:
        return None


def metinden_fiyat(metin: str) -> float | None:
    """Serbest metinden '… 1.299,90 TL' / '₺ 899' kalıplarını arar."""
    for kalip in (r"(\d[\d.,]*)\s*(?:TL|₺)",
                  r"(?:TL|₺)\s*(\d[\d.,]*)"):
        eslesme = re.search(kalip, metin, re.IGNORECASE)
        if eslesme:
            tutar = para_coz(eslesme.group(1))
            if tutar:
                return tutar
    return None



def metni_temizle(metin: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(metin or "")).strip()


_SATICI_KALIPLARI = [
    re.compile(r"(?:sat(?:ı|i)c(?:ı|i)|mağaza|magaza|store)\s*[:\-]\s*"
               r"([^|·•()\d₺]{2,60}?)(?=\s*(?:[|·•()]|₺|\d|$)|\s+TL\b)",
               re.IGNORECASE),
]
_SATIS_KALIP = re.compile(
    r"(\d[\d.,]*\s*(?:bin|mn)?\s*\+?\s*satan)", re.IGNORECASE)
_YORUM_KALIP = re.compile(r"\((\d[\d.]*)\)")


def _kart_metninden_satici(metin: str) -> str | None:
    for kalip in _SATICI_KALIPLARI:
        eslesme = kalip.search(metin)
        if eslesme:
            aday = metni_temizle(eslesme.group(1))
            if 1 < len(aday) < 80:
                return aday
    return None


def _satici_temiz(deger: str | None) -> str | None:
    """Seçici/attribute değerini temizler; 'Satıcı: X' önekini atar."""
    if not deger:
        return None
    metin = metni_temizle(deger)
    for kalip in _SATICI_KALIPLARI:
        eslesme = kalip.search(metin)
        if eslesme and eslesme.group(1).strip():
            metin = metni_temizle(eslesme.group(1))
            break
    return metin if 1 < len(metin) < 80 else None


def _ilk_deger(card, seciciler: list[str]) -> str | None:
    for sec in seciciler:
        dugum = card.select_one(sec)
        if dugum:
            metin = metni_temizle(dugum.get_text(" ", strip=True))
            if metin:
                return metin
    return None


def _link_bul(card, kalip: str) -> str | None:
    for a in card.find_all("a", href=True):
        if re.search(kalip, a["href"]):
            return a["href"]
    return None


# --------------------------------------------------------------------------
#  Platform tanımıkları
# --------------------------------------------------------------------------
URL_SABLON = {
    "trendyol": "https://www.trendyol.com/sr?q={sorgu}&pi={sayfa}",
    "n11": "https://www.n11.com/ara?q={sorgu}&paging={sayfa}",
    "hepsiburada": "https://www.hepsiburada.com/ara?q={sorgu}&sayfa={sayfa}",
    "amazon": "https://www.amazon.com.tr/s?k={sorgu}&page={sayfa}",
}

# Göreli linkleri mutlak yapan taban adresler
SITE_BAZ = {
    "trendyol": "https://www.trendyol.com",
    "n11": "https://www.n11.com",
    "hepsiburada": "https://www.hepsiburada.com",
    "amazon": "https://www.amazon.com.tr",
}

KART_SECICILERI = {
    "trendyol": [
        '[data-testid="product-card"]',
        '[data-test-id="product-card"]',
        'div[data-product-id]',
        'div.product-card',
        'div[class*="product-card"]',
        'div.searchResultItem',
        'div[class*="prdct"]',
        'div[class*="ProductCard"]',
    ],
    "n11": [
        '[data-testid="product-card"]',
        'div.searchProductItem',
        'li.searchProductItem',
        'div[class*="searchProduct"]',
        'div[data-product-id]',
        'li[class*="product"][class*="item"]',
        'div[class*="ProductItem"]',
    ],
    "hepsiburada": [
        '[data-testid="product-card"]',
        '[data-test-id="productCard"]',
        'div[data-test-id="product-card"]',
        'div.productCard',
        'div[class*="product-card"]',
        'div[class*="ProductCard"]',
        'li.productListContentItem',
        'div.productListContentItem',
        'div[class*="productList"]',
    ],
    "amazon": [
        'div[data-component-type="s-search-result"]',
        'div[data-asin][data-component-type]',
        'div.s-result-item[data-asin]',
        'div.s-result-item',
    ],
}

AD_SECICILERI = [
    '[data-testid="product-name"]', '[data-test-id="product-name"]',
    '[data-testid="title"]', '.product-name', '.productName',
    '.prd-name', '.name', 'h3', 'h2 .title', '.title',
    'h2 span', 'h2',
]
FIYAT_SECICILERI = [
    '.a-price .a-offscreen',   # Amazon: tek temiz "₺…" değeri
    '[data-testid="price-current"]', '[data-test-id="price"]',
    '[data-test-id="currentPrice"]', '.price-current', '.price',
    '.prc-dsc', '.discountPrice', '.sale-price', '.money',
    '[class*="price"]', '[class*="Price"]',
]
YORUM_SECICILERI = [
    '[data-testid="rating-count"]', '[data-test-id="ratingCount"]',
    '.rating-count', '.review-count', '.commentCount', '.ratingCount',
    '[class*="rating-count"]', '[class*="reviewCount"]',
]
SATICI_SECICILERI = [
    '[data-testid="merchant-name"]', '[data-testid="seller-name"]',
    '[data-test-id="merchantName"]', '[data-test-id="sellerName"]',
    '.merchant-name', '.merchantName', '.seller-name', '.sellerName',
    '.merchant-title', '.merchantTitle', '.store-name', '.storeName',
    '[class*="merchant"]', '[class*="seller"]', '[class*="satici"]',
]


def _satici_attribute_tara(card) -> str | None:
    for dugum in card.find_all(True):
        for nitelik, deger in dugum.attrs.items():
            if not isinstance(deger, str):
                continue
            if any(anahtar in nitelik.lower()
                   for anahtar in ("merchant", "seller", "satici", "magaza")):
                if 1 < len(deger) < 80 and not deger.startswith(("/", "http")):
                    return metni_temizle(deger)
    return None


def kart_coz(card, platform: str) -> Listeleme | None:
    """Tek bir ürün kartını ayrıştırır."""
    metin = metni_temizle(card.get_text(" ", strip=True))
    if not metin:
        return None

    ad = (_ilk_deger(card, AD_SECICILERI)
          or card.get("data-product-name")
          or card.get("aria-label"))
    if not ad:
        return None

    fiyat = para_coz(_ilk_deger(card, FIYAT_SECICILERI))
    if fiyat is None:
        fiyat = metinden_fiyat(metin)

    satici = (_satici_temiz(_ilk_deger(card, SATICI_SECICILERI))
              or _satici_temiz(_satici_attribute_tara(card))
              or _kart_metninden_satici(metin))
    if not satici:
        href = _link_bul(card, r"/(?:magaza|magaza/|store/|satici/)")
        if href:
            parca = [p for p in href.split("/") if p]
            if parca:
                satici = metni_temizle(parca[-1].replace("-", " "))

    yorum_metni = _ilk_deger(card, YORUM_SECICILERI)
    yorum = int(sayiyi_coz(yorum_metni) or 0)
    if not yorum:
        eslesme = _YORUM_KALIP.search(metin)
        if eslesme:
            yorum = int(sayiyi_coz(eslesme.group(1)) or 0)

    rozet_metni = None
    eslesme = _SATIS_KALIP.search(metin)
    if eslesme:
        rozet_metni = eslesme.group(1)
    satis_rozet = int(sayiyi_coz(rozet_metni) or 0) or None

    puan = None
    for nitelik in ("data-rating", "data-score", "aria-label"):
        for dugum in card.find_all(True):
            deger = dugum.get(nitelik)
            if isinstance(deger, str):
                aday = re.search(r"(\d[.,]\d)", deger)
                if aday:
                    puan = float(aday.group(1).replace(",", "."))
                    break
            if puan is not None:
                break
        if puan is not None:
            break

    url = ""
    a = card.find("a", href=True)
    if a:
        url = a["href"]
    if not url or not re.search(r"-p-\d+|/dp/|/p/|/urun/", url):
        aday = _link_bul(card, r"-p-\d+") or _link_bul(card, r"/dp/") \
            or _link_bul(card, r"/p/")
        if aday:
            url = aday
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = SITE_BAZ.get(platform, "") + url

    if fiyat is None and not satici:
        return None

    return Listeleme(platform=platform, ad=metni_temizle(ad)[:200],
                     fiyat=fiyat, satici=satici, yorum=yorum, puan=puan,
                     satis_rozet=satis_rozet, url=url)


def sayfayi_ayristir(platform: str, ham_html: str) -> list[Listeleme]:
    """Arama sayfasının HTML'inden tüm listelemleri çıkarır."""
    soup = BeautifulSoup(ham_html, "html.parser")
    en_iyi: list = []
    for secici in KART_SECICILERI.get(platform, []):
        kartlar = soup.select(secici)
        if len(kartlar) > len(en_iyi):
            en_iyi = kartlar
        if len(en_iyi) >= 24:
            break

    sonuc: list[Listeleme] = []
    gorulen: set[str] = set()
    for card in en_iyi:
        item = kart_coz(card, platform)
        if item and item.ad not in gorulen:
            gorulen.add(item.ad)
            sonuc.append(item)
    return sonuc
