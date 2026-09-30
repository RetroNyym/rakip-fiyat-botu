# -*- coding: utf-8 -*-
"""Ürün Arama — pazaryeri-radar `--mod urun` + GUI sekmesi testleri.

Tüm veriler ``pazaryeri-radar/ornek-html/`` örnekleriyle üretilir;
bu test paketi **ağ çağrısı yapmaz**.

Çalıştırma:
    python -m unittest discover -v
    pytest -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Açılış ipucu balonu testlerde açılmasın
os.environ["RIYA_TESTI"] = "1"

KOK = Path(__file__).resolve().parent
RADAR_KOK = KOK / "pazaryeri-radar"
ORNEK_DIZIN = RADAR_KOK / "ornek-html"

sys.path.insert(0, str(RADAR_KOK))

from radar import ayristir                              # noqa: E402
from radar.__main__ import argumanlari_ayristir, main   # noqa: E402

BEKLENEN = {
    "trendyol": 5,
    "n11": 4,
    "hepsiburada": 4,
    "amazon": 3,
    "pazarama": 10,
    "etsy": 4,
    "ebay": 4,
    "aliexpress": 4,
    "ciceksepeti": 4,
}
TOPLAM_BEKLENEN = sum(BEKLENEN.values())          # 42
ESKI_4_SITE = ["trendyol", "n11", "hepsiburada", "amazon"]


class AyristirTesti(unittest.TestCase):
    """Her platformun arama sayfası ayrı ayrı ayrıştırılır."""

    def _oku(self, platform: str):
        ham = (ORNEK_DIZIN / f"{platform}_1.html").read_text(
            encoding="utf-8")
        return ayristir.sayfayi_ayristir(platform, ham)

    def test_urun_sayilari(self):
        for platform, beklenen in BEKLENEN.items():
            with self.subTest(platform=platform):
                sonuc = self._oku(platform)
                self.assertEqual(len(sonuc), beklenen)

    def test_fiyat_var(self):
        for platform in BEKLENEN:
            with self.subTest(platform=platform):
                for L in self._oku(platform):
                    self.assertIsInstance(L.fiyat, float)
                    self.assertGreater(L.fiyat, 0)

    def test_link_mutlak(self):
        for platform, taban in ayristir.SITE_BAZ.items():
            if platform not in BEKLENEN:
                continue
            with self.subTest(platform=platform):
                for L in self._oku(platform):
                    self.assertTrue(L.url.startswith("http"), L.url)
                    self.assertTrue(L.url.startswith(taban), L.url)

    def test_adlar_bos_degil(self):
        for platform in BEKLENEN:
            with self.subTest(platform=platform):
                for L in self._oku(platform):
                    self.assertTrue(L.ad.strip())

    def test_trendyol_satici_ve_yorum(self):
        ilk = self._oku("trendyol")[0]
        self.assertEqual(ilk.ad, "Apple iPhone 15 128 GB")
        self.assertEqual(ilk.fiyat, 39999.0)
        self.assertEqual(ilk.satici, "TeknolojiMağaza")
        self.assertEqual(ilk.yorum, 1234)

    def test_amazon_dp_linki(self):
        for L in self._oku("amazon"):
            self.assertIn("/dp/", L.url)

    def test_url_sablonlari_9_site(self):
        for platform in BEKLENEN:
            self.assertIn(platform, ayristir.URL_SABLON)
            self.assertIn(platform, ayristir.SITE_BAZ)

    def test_ebay_usd_fiyat_ve_link(self):
        ilk = self._oku("ebay")[0]
        self.assertEqual(ilk.fiyat, 12.34)
        self.assertEqual(ilk.extra.get("para"), "USD")
        self.assertIn("/itm/", ilk.url)
        self.assertNotIn("?", ilk.url)          # takip parametresi atilmis
        self.assertEqual(ilk.satici, "techstore99")

    def test_etsy_link_temiz_ve_satici(self):
        for L in self._oku("etsy"):
            self.assertIn("/listing/", L.url)
            self.assertNotIn("?", L.url)
            self.assertTrue(L.satici)
        ilk = self._oku("etsy")[0]
        self.assertEqual(ilk.yorum, 1234)
        self.assertEqual(ilk.fiyat, 249.9)
        self.assertEqual(ilk.extra.get("para"), "TL")

    def test_pazarama_canli_ayristirma(self):
        sonuc = self._oku("pazarama")
        self.assertEqual(len(sonuc), 10)
        for L in sonuc:
            self.assertTrue(L.url.startswith("https://www.pazarama.com/"))
            self.assertIn("-p-", L.url)
            self.assertEqual(L.extra.get("para"), "TL")

    def test_ciceksepeti_mutlak_link(self):
        for L in self._oku("ciceksepeti"):
            self.assertTrue(
                L.url.startswith("https://www.ciceksepeti.com/"))
            self.assertNotIn("/d/", L.url)      # kategori degil urun

    def test_aliexpress_usd(self):
        for L in self._oku("aliexpress"):
            self.assertIn("/item/", L.url)
            self.assertEqual(L.extra.get("para"), "USD")
            self.assertTrue(L.satici)


class CliTesti(unittest.TestCase):
    """GUI'nin çağırdığı CLI sözleşmesi."""

    def test_mod_urun(self):
        a = argumanlari_ayristir(["sorgu", "--mod", "urun"])
        self.assertEqual(a.mod, "urun")

    def test_mod_varsayilan_satici(self):
        a = argumanlari_ayristir(["sorgu"])
        self.assertEqual(a.mod, "satici")

    def test_uc_dogrulama(self):
        with self.assertRaises(SystemExit):
            argumanlari_ayristir(["sorgu", "--mod", "yanlis"])


class CevrimdisiUctanUcaTesti(unittest.TestCase):
    """main() --html-dizin ile 9 siteden toplu arama yapar (ağ yok)."""

    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.json_yol = Path(cls.gecici.name) / "sonuc.json"
        cls.kod = main([
            "iphone", "--mod", "urun",
            "-m", ",".join(BEKLENEN), "-p", "1",
            "--html-dizin", str(ORNEK_DIZIN),
            "--json", str(cls.json_yol),
        ])
        cls.veri = json.loads(cls.json_yol.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_cikis_kodu(self):
        self.assertEqual(self.kod, 0)

    def test_sema(self):
        self.assertEqual(self.veri["mod"], "urun")
        self.assertEqual(self.veri["sorgu"], "iphone")
        self.assertEqual(self.veri["toplam"], TOPLAM_BEKLENEN)
        self.assertEqual(len(self.veri["siteler"]), 9)

    def test_site_basina_sonuc(self):
        for s in self.veri["siteler"]:
            with self.subTest(site=s["site"]):
                self.assertIsNone(s["hata"])
                self.assertEqual(len(s["urunler"]), BEKLENEN[s["site"]])
                u = s["urunler"][0]
                for alan in ("ad", "fiyat", "para", "url", "satici",
                             "yorum", "puan"):
                    self.assertIn(alan, u)

    def test_para_birimleri(self):
        for s in self.veri["siteler"]:
            beklenen = ("USD" if s["site"] in ("ebay", "aliexpress")
                        else "TL")
            with self.subTest(site=s["site"]):
                for u in s["urunler"]:
                    self.assertEqual(u["para"], beklenen)

    def test_fiyat_artan_siralanabilir(self):
        fiyatlar = [u["fiyat"] for s in self.veri["siteler"]
                    for u in s["urunler"]]
        self.assertTrue(all(f is not None for f in fiyatlar))


try:
    import tkinter                                              # noqa: F401
    EKRAN_VAR = True
except Exception:                                   # noqa: BLE001
    EKRAN_VAR = False

if EKRAN_VAR:
    import gui


@unittest.skipUnless(EKRAN_VAR, "tkinter/ekran yok")
class AramaSekmesiTesti(unittest.TestCase):
    """GUI'nin 🔍 Ürün Arama sekmesi (ağsız, hazır JSON ile)."""

    app = None

    @classmethod
    def setUpClass(cls):
        cls.app = gui.Uygulama()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        if cls.app is not None:
            cls.app.destroy()
            cls.app = None

    def setUp(self):
        self.app.paz_temizle()

    def _ornek_veri(self) -> dict:
        return {
            "mod": "urun", "sorgu": "iphone", "toplam": 3,
            "siteler": [
                {"site": "trendyol", "hata": None, "urunler": [
                    {"ad": "A", "fiyat": 200.0, "para": "TL",
                     "url": "https://www.trendyol.com/a-p-1",
                     "satici": "X", "yorum": 5, "puan": None}]},
                {"site": "amazon", "hata": "test engeli", "urunler": [
                    {"ad": "B", "fiyat": 100.0, "para": "TL",
                     "url": "https://www.amazon.com.tr/dp/B1",
                     "satici": "", "yorum": 0, "puan": None}]},
                {"site": "n11", "hata": None, "urunler": []},
            ],
        }

    def test_sekme_var(self):
        self.assertTrue(hasattr(self.app, "arama_sayfa"))
        self.assertIn(self.app.arama_sayfa._w, self.app.ust_sayfa.tabs())

    def test_bos_csv(self):
        self.assertIsNone(self.app.csv_satirlari("pazarama"))

    def test_goster_sirala_ve_ozet(self):
        self.app.paz_goster(self._ornek_veri())
        satirlar = [self.app.paz_agac.item(i, "values")
                    for i in self.app.paz_agac.get_children()]
        self.assertEqual(len(satirlar), 2)
        # en ucuz önce: Amazon 100 → Trendyol 200
        self.assertEqual(satirlar[0][0], "Amazon")
        self.assertEqual(satirlar[1][0], "Trendyol")
        self.assertEqual(satirlar[0][2], "100,00 TL")
        ozet = self.app.paz_ozet.get()
        self.assertIn("Trendyol 1", ozet)
        self.assertIn("Amazon: ✗", ozet)
        self.assertIn("toplam 3", ozet)

    def test_csv_aktarim(self):
        self.app.paz_goster(self._ornek_veri())
        basliklar, satirlar = self.app.csv_satirlari("pazarama")
        self.assertEqual(basliklar,
                         ["Site", "Ürün", "Fiyat", "Satıcı", "Yorum",
                          "Link"])
        self.assertEqual(len(satirlar), 2)
        self.assertEqual(satirlar[0][1], "B")
        self.assertEqual(satirlar[0][2], 100.0)

    def test_url_haritasi(self):
        self.app.paz_goster(self._ornek_veri())
        iid = self.app.paz_agac.get_children()[0]
        self.assertEqual(self.app.paz_url_harita[iid],
                         "https://www.amazon.com.tr/dp/B1")

    def test_temizle(self):
        self.app.paz_goster(self._ornek_veri())
        self.app.paz_temizle()
        self.assertEqual(self.app.paz_agac.get_children(), ())
        self.assertIsNone(self.app.paz_veri)
        self.assertIsNone(self.app.csv_satirlari("pazarama"))

    def test_tl_biçim(self):
        self.assertEqual(self.app._tl(39999.0), "39.999,00 TL")
        self.assertEqual(self.app._tl(0), "0,00 TL")
        self.assertEqual(self.app._tl(None), "-")

    def test_diger_para_birimleri(self):
        self.assertEqual(self.app._tl(12.34, "USD"), "12,34 USD")
        self.assertEqual(self.app._tl(9.99, "EUR"), "9,99 EUR")
        self.assertEqual(self.app._tl(None, "USD"), "-")

    def test_9_site_sozlesmesi(self):
        self.assertEqual(len(gui.ARAMA_SITELERI), 9)
        for site in gui.ARAMA_SITELERI:
            self.assertIn(site, gui.SITE_ETIKET)
            self.assertIn(site, ayristir.URL_SABLON)

    def test_karisik_para_gosterimi(self):
        veri = {
            "mod": "urun", "sorgu": "kulaklik", "toplam": 2,
            "siteler": [
                {"site": "ebay", "hata": None, "urunler": [
                    {"ad": "USD Urun", "fiyat": 12.34, "para": "USD",
                     "url": "https://www.ebay.com/itm/1",
                     "satici": "", "yorum": 0, "puan": None}]},
                {"site": "pazarama", "hata": None, "urunler": [
                    {"ad": "TL Urun", "fiyat": 500.0, "para": "TL",
                     "url": "https://www.pazarama.com/x-p-1",
                     "satici": "", "yorum": 0, "puan": None}]},
            ],
        }
        self.app.paz_goster(veri)
        satirlar = [self.app.paz_agac.item(i, "values")
                    for i in self.app.paz_agac.get_children()]
        self.assertEqual(len(satirlar), 2)
        # TL grubu önce gelir
        self.assertEqual(satirlar[0][0], "Pazarama")
        self.assertEqual(satirlar[0][2], "500,00 TL")
        self.assertEqual(satirlar[1][2], "12,34 USD")


if __name__ == "__main__":
    unittest.main()
