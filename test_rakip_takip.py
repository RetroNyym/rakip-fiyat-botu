# -*- coding: utf-8 -*-
"""rakip_takip.py çekirdeği için birim + entegrasyon testleri.

Hiçbir dış ağağa gitmez; yerel (127.0.0.1) HTTP sunucusu kurar.

Çalıştırma:
    python -m unittest discover -v
    pytest -v
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import rakip_takip as c


# ==========================================================================
#  Yerel test sunucusu
# ==========================================================================
class YerelSunucu:
    """{yol: (content_type, govde)} tabanlı minik HTTP sunucusu."""

    def __init__(self, sayfalar: dict):
        sahibi = self

        class El(BaseHTTPRequestHandler):
            def do_GET(self):                       # noqa: N802
                veri = sahibi.sayfalar.get(self.path)
                if veri is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                tip, govde = veri
                if isinstance(govde, str):
                    govde = govde.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", tip)
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

            def log_message(self, *args):           # sessiz
                pass

        self.sayfalar = sayfalar
        self.sunucu = ThreadingHTTPServer(("127.0.0.1", 0), El)
        self.ip = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    @property
    def kok(self) -> str:
        return f"http://127.0.0.1:{self.ip}"

    def url(self, yol: str) -> str:
        return self.kok + yol

    def kapat(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()


def sessiz(_metin: str) -> None:
    """Test çıktısını boğmak için log fonksiyonu."""


# ==========================================================================
#  1. Fiyat ayrıştırma
# ==========================================================================
class FiyatAyristirmaTesti(unittest.TestCase):
    DURUMLAR = [
        ("4.900,50 TL", 4900.50, "TL"),
        ("1.900 TL", 1900.0, "TL"),
        ("4,900.50 USD", 4900.50, "USD"),
        ("$19.99", 19.99, "USD"),
        ("€ 99,90", 99.90, "EUR"),
        ("£45.00", 45.0, "GBP"),
        # kritik: sayı mı para birimi mi seçilecek
        ("200x300 halı 1.750,00 TL", 1750.00, "TL"),
        ("Ürün Kodu 5544 - TL 89,90", 89.90, "TL"),
        ("1.234.567,89 TL", 1234567.89, "TL"),
        ("Kargo 12 ay taksit 49,90", 49.90, None),
        ("Ağır indirim: sadece 1.299,00 TL", 1299.00, "TL"),
        ("₺ 750", 750.0, "TL"),
    ]

    def test_fiyat_ayristir_tablo(self):
        for metin, beklenen_fiyat, beklenen_para in self.DURUMLAR:
            with self.subTest(metin=metin):
                fiyat, para = c.fiyat_ayristir(metin)
                self.assertIsNotNone(fiyat, f"'{metin}' çözümlenemedi")
                self.assertAlmostEqual(fiyat, beklenen_fiyat, places=2)
                self.assertEqual(para, beklenen_para)

    def test_fiyat_yok(self):
        for metin in ("", "fiyat yok", "sadece metin", "   "):
            with self.subTest(metin=metin):
                fiyat, para = c.fiyat_ayristir(metin)
                self.assertIsNone(fiyat)
                self.assertIsNone(para)

    def test_nbsp_ayrac(self):
        # Siteler 4.900\u00a0TL gibi yazıdırır
        fiyat, para = c.fiyat_ayristir("4.900\u00a0TL")
        self.assertAlmostEqual(fiyat, 4900.0)
        self.assertEqual(para, "TL")


class SayiNormalizasyonTesti(unittest.TestCase):
    DURUMLAR = [
        ("4.900,50", 4900.50),
        ("4,900.50", 4900.50),
        ("1.234.567,89", 1234567.89),
        ("1.900", 1900.0),        # nokta = binlik
        ("19.99", 19.99),         # nokta = ondalık
        ("1,900", 1900.0),        # virgül + 3 hane = binlik
        ("1,99", 1.99),           # virgül + 2 hane = ondalık
        ("5544", 5544.0),
        ("0,00", 0.0),
    ]

    def test_tablo(self):
        for ham, beklenen in self.DURUMLAR:
            with self.subTest(ham=ham):
                self.assertAlmostEqual(c.sayiyi_normalize_et(ham), beklenen)


class BicimTesti(unittest.TestCase):
    def test_turkce_bicim(self):
        self.assertEqual(c.fiyat_bicimle(4900.5, "TL"), "4.900,50 TL")

    def test_kucuk_deger(self):
        self.assertEqual(c.fiyat_bicimle(51.77, "GBP"), "51,77 GBP")

    def test_yok(self):
        self.assertEqual(c.fiyat_bicimle(None), "—")

    def test_parasiz(self):
        self.assertEqual(c.fiyat_bicimle(100.0), "100,00")

    def test_buyuk_deger(self):
        self.assertEqual(c.fiyat_bicimle(1234567.89, "TL"),
                         "1.234.567,89 TL")


# ==========================================================================
#  2. Config
# ==========================================================================
class ConfigTesti(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.yol = Path(self.klasor.name)

    def tearDown(self):
        self.klasor.cleanup()

    def test_utf8_bom_okunur(self):
        """Windows 'Farklı Kaydet' BOM yazar; okuma bozulmamalı."""
        hedef = self.yol / "bom.json"
        hedef.write_bytes(b"\xef\xbb\xbf" + json.dumps(
            {"urunler": [{"ad": "Türkçe Ürün"}]},
            ensure_ascii=False).encode("utf-8"))
        config = c.config_oku(hedef)
        self.assertEqual(config["urunler"][0]["ad"], "Türkçe Ürün")

    def test_kaydet_oku_dongusu(self):
        hedef = self.yol / "c.json"
        config = {"ayarlar": {"esik_yuzde": 5}, "urunler": []}
        c.config_kaydet(config, hedef)
        self.assertEqual(c.config_oku(hedef), config)

    def test_eksik_config_olmaz_sablon_kopyalanir(self):
        """İlk çalıştırmada config.json yoksa şablondan üretilir."""
        hedef = self.yol / "config.json"
        self.assertFalse(hedef.exists())
        config = c.config_oku(hedef)
        self.assertTrue(hedef.exists(), "şablon kopyalanmadı")
        self.assertIn("urunler", config)
        self.assertIn("ayarlar", config)
        # şablon değişmedi
        self.assertEqual(hedef.read_bytes(), c.SEMBOL_CONFIG.read_bytes())

    def test_eksik_diger_dosya_hata(self):
        with self.assertRaises(FileNotFoundError):
            c.config_oku(self.yol / "olmayan.json")

    def test_bozuk_json_hata(self):
        hedef = self.yol / "bozuk.json"
        hedef.write_text("{yarim", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            c.config_oku(hedef)

    def test_sembol_config_gecerli(self):
        """Depoya giren şablon mutlaka geçerli JSON olmalı."""
        config = c.config_oku(c.SEMBOL_CONFIG)
        self.assertTrue(config["urunler"])
        for u in config["urunler"]:
            self.assertIn("ad", u)
            self.assertIn("url", u)
            self.assertIn("selector", u)


# ==========================================================================
#  3. Veritabanı
# ==========================================================================
class VeritabaniTesti(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.db = Path(self.klasor.name) / "t.db"

    def tearDown(self):
        self.klasor.cleanup()

    def test_tablo_olusur(self):
        bag = c.db_ac(self.db)
        adlar = [s[0] for s in bag.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        bag.close()
        self.assertIn("fiyatlar", adlar)

    def test_gunde_tek_kayit(self):
        """UNIQUE(ad, zaman): aynı gün ikinci kayıt sessizce atlanır."""
        bag = c.db_ac(self.db)
        c.kaydet(bag, "A", "u", 100.0, "TL", "ham", gun="2026-01-01")
        c.kaydet(bag, "A", "u", 150.0, "TL", "ham", gun="2026-01-01")
        sayi = bag.execute("SELECT COUNT(*) FROM fiyatlar").fetchone()[0]
        bag.close()
        self.assertEqual(sayi, 1)

    def test_farkli_gunler_kaydedilir(self):
        bag = c.db_ac(self.db)
        c.kaydet(bag, "A", "u", 100.0, "TL", "h", gun="2026-01-01")
        c.kaydet(bag, "A", "u", 110.0, "TL", "h", gun="2026-01-02")
        sayi = bag.execute("SELECT COUNT(*) FROM fiyatlar").fetchone()[0]
        bag.close()
        self.assertEqual(sayi, 2)

    def test_son_fiyat_en_yeni(self):
        bag = c.db_ac(self.db)
        c.kaydet(bag, "A", "u", 100.0, "TL", "h", gun="2026-01-01")
        c.kaydet(bag, "A", "u", 120.0, "EUR", "h", gun="2026-01-02")
        fiyat, para, zaman = c.son_fiyat(bag, "A")[:3]
        bag.close()
        self.assertEqual((fiyat, para, zaman), (120.0, "EUR", "2026-01-02"))

    def test_olmayan_urun(self):
        bag = c.db_ac(self.db)
        self.assertEqual(c.son_fiyat(bag, "yok"), (None, "", None))
        bag.close()

    def test_fiyat_gecmisi_sirali_ve_aralikli(self):
        bag = c.db_ac(self.db)
        for i, gun in enumerate(["2026-01-01", "2026-02-01", "2026-03-01"]):
            c.kaydet(bag, "A", "u", 100.0 + i, "TL", "h", gun=gun)
        bag.close()
        tumu = c.fiyat_gecmisi("A", gun=3650, db_yol=self.db)
        self.assertEqual([s[0] for s in tumu],
                         ["2026-01-01", "2026-02-01", "2026-03-01"])
        # dar aralık: sadece son kayıt
        dar = c.fiyat_gecmisi("A", gun=1, db_yol=self.db)
        # bugünden 1 gün öncesi → hiç kayıt düşmez
        self.assertEqual(dar, [])

    def test_db_yokken_bos(self):
        self.assertEqual(c.fiyat_gecmisi("A", 30,
                                         db_yol=self.yol_yok()), [])

    def yol_yok(self):
        return Path(self.klasor.name) / "hiçyok.db"


# ==========================================================================
#  4. HTML / seçici
# ==========================================================================
class SeciciTesti(unittest.TestCase):
    HTML = """
    <html><body>
      <div class="urun">
        <h1>Yün Halı 200x300</h1>
        <span class="price">4.900,50 TL</span>
        <div class="stock">Stokta 3 adet</div>
      </div>
    </body></html>
    """

    def setUp(self):
        from bs4 import BeautifulSoup
        self.corba = BeautifulSoup(self.HTML, "html.parser")

    def test_seciciden_fiyat(self):
        fiyat, para, ham = c.seciciden_fiyat_bul(self.corba, "span.price")
        self.assertAlmostEqual(fiyat, 4900.50)
        self.assertEqual(para, "TL")

    def test_secici_bos_dogru_oler(self):
        # boş seçici → para birimli aday seçilir, "3 adet" değil
        fiyat, para, ham = c.seciciden_fiyat_bul(self.corba, "")
        self.assertAlmostEqual(fiyat, 4900.50)
        self.assertEqual(para, "TL")

    def test_secici_yanlis_older(self):
        fiyat, para, ham = c.seciciden_fiyat_bul(self.corba, "div.yok")
        self.assertIsNone(fiyat)

    def test_gersel_secici_hatasi_yutulur(self):
        # geçersiz seçici çökmemeli
        fiyat, para, ham = c.seciciden_fiyat_bul(self.corba, "span[")
        self.assertIsNone(fiyat)

    def test_secici_adaylari_fiyat_elementini_bulur(self):
        adaylar = c.secici_adaylari(self.corba)
        seciciler = [a["secici"] for a in adaylar]
        self.assertIn("span.price", seciciler)
        secili = next(a for a in adaylar if a["secici"] == "span.price")
        self.assertAlmostEqual(secili["fiyat"], 4900.50)
        self.assertEqual(secili["para"], "TL")
        self.assertTrue(secili["guclu"])

    def test_secici_adaylari_gereksiz_elementleri_ele(self):
        """'Stokta 3 adet' gibi para birimsiz sayılar aday olmamalı."""
        adaylar = c.secici_adaylari(self.corba)
        for a in adaylar:
            self.assertNotIn("stock", a["secici"])


# ==========================================================================
#  5. Telegram
# ==========================================================================
class TelegramTesti(unittest.TestCase):
    def test_token_yoksa_gondermez(self):
        """Ağ çağrısı yapılmadan False dönmeli."""
        self.assertFalse(c.telegram_gonder({}, "merhaba", sessiz))

    def test_token_bos_ise(self):
        self.assertFalse(c.telegram_gonder(
            {"telegram_token": "", "telegram_chat_id": ""}, "m", sessiz),
            "boş token ile göndermemeli")

    def test_chat_id_yoksa(self):
        self.assertFalse(c.telegram_gonder(
            {"telegram_token": "123:abc", "telegram_chat_id": ""},
            "m", sessiz))

    def test_test_telegram_kapali(self):
        self.assertFalse(c.test_telegram({"ayarlar": {}}, sessiz))


# ==========================================================================
#  6. Tarama (yerel sunucu — gerçek HTTP)
# ==========================================================================
class TaramaTesti(unittest.TestCase):
    URUN_ADI = "Deneme Ürün"

    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.db = Path(self.klasor.name) / "fiyat.db"
        self.robots = "User-agent: *\nAllow: /\n"

        self.sunucu = YerelSunucu({
            "/robots.txt": ("text/plain; charset=utf-8", self.robots),
            "/urun": ("text/html; charset=utf-8", ""),
        })
        # fiyat sayfası her testte `sayfa_yaz` ile güncellenir

        self.config = {
            "ayarlar": {"bekleme_saniye": 0, "esik_yuzde": 0,
                        "telegram_token": "", "telegram_chat_id": ""},
            "urunler": [{"ad": self.URUN_ADI,
                         "url": self.sunucu.url("/urun"),
                         "selector": "p.price"}],
        }

    def tearDown(self):
        self.sunucu.kapat()
        self.klasor.cleanup()

    def sayfa_yaz(self, fiyat_metni: str):
        self.sunucu.sayfalar["/urun"] = (
            "text/html; charset=utf-8",
            f"<html><body><p class='price'>{fiyat_metni}</p></body></html>")

    def tara(self) -> dict:
        sonuclar = c.tarama_yap(self.config, log=sessiz, db_yol=self.db)
        return sonuclar[0] if sonuclar else {}

    def test_ilk_kayit(self):
        self.sayfa_yaz("1.299,00 TL")
        sonuc = self.tara()
        self.assertEqual(sonuc["durum"], "ilk")
        self.assertAlmostEqual(sonuc["fiyat"], 1299.00)
        self.assertEqual(sonuc["para"], "TL")

    def test_degismedi(self):
        self.sayfa_yaz("1.299,00 TL")
        self.tara()
        sonuc = self.tara()
        self.assertEqual(sonuc["durum"], "degismedi")
        self.assertAlmostEqual(sonuc["fiyat"], 1299.00)

    def test_degisiklik_yuzdesi(self):
        self.sayfa_yaz("1.299,00 TL")
        self.tara()
        self.sayfa_yaz("1.599,00 TL")
        sonuc = self.tara()
        self.assertEqual(sonuc["durum"], "degisti")
        self.assertAlmostEqual(sonuc["onceki"], 1299.00)
        self.assertAlmostEqual(sonuc["fiyat"], 1599.00)
        beklenen = (1599.0 - 1299.0) / 1299.0 * 100
        self.assertAlmostEqual(sonuc["yuzde"], beklenen, places=6)

    def test_inis_yonu(self):
        self.sayfa_yaz("1.299,00 TL")
        self.tara()
        self.sayfa_yaz("999,00 TL")
        sonuc = self.tara()
        self.assertEqual(sonuc["durum"], "degisti")
        self.assertLess(sonuc["yuzde"], 0)

    def test_esik_asimi(self):
        """esik_yuzde=10 → %5'lik değişimde Telegram uyarısı ÜRETİLMEMELİ."""
        gonderilen = []
        orijinal = c.telegram_gonder

        def sahte(ayar, mesaj, log=None):
            gonderilen.append(mesaj)
            return True

        c.telegram_gonder = sahte
        try:
            self.sayfa_yaz("1.000,00 TL")
            self.tara()
            self.sayfa_yaz("1.050,00 TL")
            self.config["ayarlar"]["esik_yuzde"] = 10
            sonuc = c.tarama_yap(self.config, log=sessiz, db_yol=self.db)[0]
            self.assertEqual(sonuc["durum"], "degisti")
            self.assertAlmostEqual(sonuc["yuzde"], 5.0, places=3)
            self.assertEqual(gonderilen, [], "eşik altında uyarı gönderildi")

            # eşik 0'a çek → aynı değişim artık uyarı üretmeli
            self.sayfa_yaz("1.100,00 TL")
            self.config["ayarlar"]["esik_yuzde"] = 0
            c.tarama_yap(self.config, log=sessiz, db_yol=self.db)
            self.assertEqual(len(gonderilen), 1, "eşik 0 iken uyarı yok")
        finally:
            c.telegram_gonder = orijinal

    def test_fiyat_bulunamadi(self):
        self.sunucu.sayfalar["/urun"] = (
            "text/html; charset=utf-8", "<html><body>yok</body></html>")
        sonuc = self.tara()
        self.assertEqual(sonuc["durum"], "bulunamadi")
        self.assertEqual(sonuc["mesaj"], "Fiyat bulunamadı")

    def test_url_eksik(self):
        self.config["urunler"][0]["url"] = ""
        sonuc = self.tara()
        self.assertEqual(sonuc["durum"], "hata")

    def test_secili_urun_filtresi(self):
        """secili_urunler verilmezse diğer ürünler taranmamalı."""
        self.sayfa_yaz("1.299,00 TL")
        self.config["urunler"].append(
            {"ad": "Diğer", "url": self.sunucu.url("/urun"),
             "selector": "p.price"})
        sonuclar = c.tarama_yap(self.config, log=sessiz, db_yol=self.db,
                                secili_urunler=["Diğer"])
        self.assertEqual(len(sonuclar), 1)
        self.assertEqual(sonuclar[0]["ad"], "Diğer")

    def test_iptal_bayragi(self):
        self.sayfa_yaz("1.299,00 TL")
        bayrak = {"deger": True}   # ilk üründe hemen iptal
        sonuclar = c.tarama_yap(self.config, log=sessiz, db_yol=self.db,
                                iptal=lambda: bayrak["deger"])
        self.assertEqual(sonuclar[-1]["durum"], "iptal")

    def test_ilerleme_cagrisi(self):
        self.sayfa_yaz("1.299,00 TL")
        cagrilan = []
        c.tarama_yap(self.config, log=sessiz, db_yol=self.db,
                     ilerleme=lambda i, t, ad: cagrilan.append((i, t, ad)))
        self.assertTrue(cagrilan)
        self.assertEqual(cagrilan[-1][0], cagrilan[-1][1])
        self.assertEqual(cagrilan[-1][2], "Bitti")

    def test_bos_urun_listesi(self):
        self.config["urunler"] = []
        self.assertEqual(c.tarama_yap(self.config, log=sessiz,
                                      db_yol=self.db), [])


class RobotsTesti(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.db = Path(self.klasor.name) / "t.db"

    def tearDown(self):
        self.klasor.cleanup()

    def test_robots_izin_vermiyor(self):
        sunucu = YerelSunucu({
            "/robots.txt": ("text/plain; charset=utf-8",
                            "User-agent: *\nDisallow: /\n"),
            "/urun": ("text/html; charset=utf-8",
                      "<p class='price'>100,00 TL</p>"),
        })
        try:
            config = {
                "ayarlar": {"bekleme_saniye": 0, "esik_yuzde": 0,
                            "telegram_token": "", "telegram_chat_id": ""},
                "urunler": [{"ad": "X", "url": sunucu.url("/urun"),
                             "selector": "p.price"}],
            }
            sonuc = c.tarama_yap(config, log=sessiz, db_yol=self.db)[0]
            self.assertEqual(sonuc["durum"], "robots")
            self.assertEqual(sonuc["mesaj"], "robots.txt izin vermiyor")
        finally:
            sunucu.kapat()

    def test_robots_izin_veriyor(self):
        sunucu = YerelSunucu({
            "/robots.txt": ("text/plain; charset=utf-8",
                            "User-agent: *\nAllow: /\n"),
            "/urun": ("text/html; charset=utf-8",
                      "<p class='price'>100,00 TL</p>"),
        })
        try:
            config = {
                "ayarlar": {"bekleme_saniye": 0, "esik_yuzde": 0,
                            "telegram_token": "", "telegram_chat_id": ""},
                "urunler": [{"ad": "X", "url": sunucu.url("/urun"),
                             "selector": "p.price"}],
            }
            sonuc = c.tarama_yap(config, log=sessiz, db_yol=self.db)[0]
            self.assertEqual(sonuc["durum"], "ilk")
        finally:
            sunucu.kapat()


# ==========================================================================
#  7. Seçici bulma / görseller (yerel sunucu)
# ==========================================================================
class SeciciBulTesti(unittest.TestCase):
    def setUp(self):
        self.sunucu = YerelSunucu({
            "/urun": ("text/html; charset=utf-8", """
                <html><body>
                  <div class="product">
                    <span class="price">49,90 TL</span>
                    <div class="badge">Yeni</div>
                  </div>
                </body></html>"""),
        })

    def tearDown(self):
        self.sunucu.kapat()

    def test_aday_listesi(self):
        sonuclar = c.secici_bul(self.sunucu.url("/urun"), log=sessiz)
        self.assertTrue(sonuclar)
        self.assertIn("span.price", [s["secici"] for s in sonuclar])

    def test_olmayan_adres(self):
        sonuclar = c.secici_bul(self.sunucu.url("/yok"), log=sessiz)
        self.assertEqual(sonuclar, [])


class GorselTesti(unittest.TestCase):
    def setUp(self):
        self.sunucu = YerelSunucu({
            "/urun": ("text/html; charset=utf-8", """
                <html><head>
                  <meta property="og:image"
                        content="/media/hero.jpg">
                </head><body>
                  <img src="/media/logo-sirket.png" alt="logo">
                  <img src="/media/urun-1.jpg" alt="ürün görseli">
                  <img src="/media/ikincil.jpg">
                </body></html>"""),
            "/media/hero.jpg": ("image/jpeg", b"\xff\xd8\xff"),
            "/media/urun-1.jpg": ("image/jpeg", b"\xff\xd8\xff"),
            "/media/ikincil.jpg": ("image/jpeg", b"\xff\xd8\xff"),
            "/media/logo-sirket.png": ("image/png", b"\x89PNG"),
        })

    def tearDown(self):
        self.sunucu.kapat()

    def test_gorsel_listesi_sirali(self):
        liste = c.gorselleri_bul(self.sunucu.url("/urun"), log=sessiz)
        self.assertTrue(liste)
        # og:image en başta olmalı
        self.assertTrue(liste[0].endswith("hero.jpg"), liste)
        # logo elenmiş olmalı
        self.assertFalse(any("logo" in g for g in liste), liste)

    def test_gorsel_indirme(self):
        import tempfile
        with tempfile.TemporaryDirectory() as k:
            hedef = Path(k) / "g.jpg"
            yol = c.gorseli_indir(self.sunucu.url("/media/hero.jpg"),
                                  hedef=hedef)
            self.assertIsNotNone(yol)
            self.assertTrue(Path(yol).exists())
            self.assertGreater(Path(yol).stat().st_size, 0)

    def test_gorsel_indirme_hatasi(self):
        self.assertIsNone(c.gorseli_indir(
            self.sunucu.url("/media/olmayan.jpg")))

    def test_bozuk_adres_bos_liste(self):
        self.assertEqual(
            c.gorselleri_bul("http://127.0.0.1:1/yok", log=sessiz), [])


# ==========================================================================
#  8. Rapor
# ==========================================================================
class RaporTesti(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.db = Path(self.klasor.name) / "t.db"
        bag = c.db_ac(self.db)
        for i, gun in enumerate(["2026-01-01", "2026-02-01", "2026-03-01"]):
            c.kaydet(bag, "A", "u", 100.0 + i * 50, "TL", "h", gun=gun)
        c.kaydet(bag, "B", "u", 50.0, "USD", "h", gun="2026-03-01")
        bag.close()
        self.config = {"urunler": [{"ad": "A", "url": "u"},
                                   {"ad": "B", "url": "u"},
                                   {"ad": "C", "url": "u"}]}

    def tearDown(self):
        self.klasor.cleanup()

    def test_rapor_verisi(self):
        veri = c.rapor_verisi(self.config, gun=3650, db_yol=self.db)
        adlar = [r["ad"] for r in veri]
        self.assertEqual(adlar, ["A", "B"])       # C'nin kaydı yok
        a = veri[0]
        self.assertEqual(a["kayit_sayisi"], 3)
        self.assertAlmostEqual(a["ilk"], 100.0)
        self.assertAlmostEqual(a["son"], 200.0)
        self.assertAlmostEqual(a["en_dusuk"], 100.0)
        self.assertAlmostEqual(a["en_yuksek"], 200.0)
        self.assertAlmostEqual(a["toplam_degisim"], 100.0)
        self.assertAlmostEqual(a["aralik"], 100.0)
        self.assertEqual(a["para"], "TL")

    def test_rapor_db_yok(self):
        veri = c.rapor_verisi(self.config, gun=30,
                              db_yol=Path(self.klasor.name) / "yok.db")
        self.assertEqual(veri, [])

    def test_rapor_yazdir(self):
        ciktilar = []
        c.rapor_yazdir(self.config, gun=3650, log=ciktilar.append,
                       db_yol=self.db)
        metin = "\n".join(ciktilar)
        self.assertIn("fiyat raporu", metin)
        self.assertIn("• A", metin)
        self.assertIn("• B", metin)
        self.assertIn("100,00 TL", metin)      # ilk
        self.assertIn("200,00 TL", metin)      # son
        self.assertIn("±100.0%", metin)        # aralık
        # "C" ürününün kaydı yok → raporda geçmemeli
        self.assertNotIn("• C", metin)

    def test_rapor_yazdir_veri_yok(self):
        ciktilar = []
        c.rapor_yazdir({"urunler": []}, log=ciktilar.append, db_yol=self.db)
        self.assertTrue(any("veri yok" in s.lower() for s in ciktilar))


# ==========================================================================
#  9. CLI
# ==========================================================================
class CliTesti(unittest.TestCase):
    """Alt süreçleri UTF-8 ile çalıştır (Windows varsayılanı cp1254'tür)."""

    @staticmethod
    def ortam():
        import os
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    @staticmethod
    def calistir(arglar: list) -> "object":
        import subprocess
        import sys
        return subprocess.run(
            [sys.executable, "rakip_takip.py", *arglar],
            capture_output=True, timeout=90, encoding="utf-8",
            errors="replace", env=CliTesti.ortam())

    def test_yardim(self):
        sonuc = self.calistir(["--help"])
        self.assertEqual(sonuc.returncode, 0)
        self.assertIn("--inspect", sonuc.stdout)
        self.assertIn("--rapor", sonuc.stdout)
        self.assertIn("--test", sonuc.stdout)

    def test_eksik_config_hata_kodu(self):
        sonuc = self.calistir(["--config", "yok-böyle.json", "--rapor"])
        self.assertEqual(sonuc.returncode, 1)
        self.assertIn("bulunamadı", sonuc.stdout + sonuc.stderr)

    def test_rapor_veri_yok(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as k:
            cfg = Path(k) / "bos.json"
            cfg.write_text('{"urunler": []}', encoding="utf-8")
            sonuc = self.calistir(["--config", str(cfg), "--rapor"])
        self.assertEqual(sonuc.returncode, 0)
        self.assertIn("veri yok", sonuc.stdout + sonuc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
