# -*- coding: utf-8 -*-
"""İthalat Radarı (ithalat-radar) — ağsız ayrıştırma testleri.

Tüm veriler ``ithalat-radar/ornek/`` altındaki örnek dosyalardan okunur;
bu test paketi **ağ çağrısı yapmaz**.

Çalıştırma:
    python -m unittest discover -v
    pytest -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent
ITHALAT_KOK = KOK / "ithalat-radar"
ORNEK = ITHALAT_KOK / "ornek"

sys.path.insert(0, str(ITHALAT_KOK))

from ithalat import arama                          # noqa: E402
from ithalat import sayfa as sayfa_mod             # noqa: E402
from ithalat.__main__ import argumanlari           # noqa: E402


class AramaTesti(unittest.TestCase):
    """ImportYeti /api/search yanıtının GUI şemasına çevirilmesi."""

    @classmethod
    def setUpClass(cls):
        ham = (ORNEK / "arama_nike.json").read_text(encoding="utf-8")
        cls.ham = json.loads(ham)

    def test_donusum_temel(self):
        veri = arama.donustur(self.ham, "nike", 1)
        self.assertEqual(veri["sorgu"], "nike")
        self.assertEqual(veri["sayfa"], 1)
        self.assertGreater(veri["toplam"], 0)
        self.assertGreaterEqual(veri["toplam_sayfa"], 1)
        self.assertTrue(veri["sonuclar"])

    def test_sonuc_alanlari_tam(self):
        veri = arama.donustur(self.ham, "nike", 1)
        ilk = veri["sonuclar"][0]
        self.assertIn(ilk["tur"], ("firma", "tedarikçi"))
        self.assertTrue(ilk["ad"])
        self.assertTrue(ilk["url"])
        self.assertEqual(ilk["url"], ilk["url"].strip("/"))
        self.assertNotIn(" ", ilk["url"])
        self.assertIsInstance(ilk["sefer"], int)

    def test_bos_url_atlanir(self):
        veri = arama.donustur(
            {"searchResults": [{"url": "/", "title": "X", "type": "company"},
                               {"url": "company/x", "title": "X",
                                "type": "company"}]},
            "s", 1)
        self.assertEqual(len(veri["sonuclar"]), 1)
        self.assertEqual(veri["sonuclar"][0]["url"], "company/x")

    def test_bos_yanit(self):
        veri = arama.donustur({}, "yok", 3)
        self.assertEqual(veri["sonuclar"], [])
        self.assertEqual(veri["sayfa"], 3)
        self.assertIsNone(veri["toplam"])


class SayfaTesti(unittest.TestCase):
    """Firma/tedarikçi sayfası HTML'inin sözlüğe çevrilmesi."""

    @classmethod
    def setUpClass(cls):
        cls.firma = sayfa_mod.ayristir(
            (ORNEK / "company_nike.html").read_text(encoding="utf-8"),
            "company/nike")
        cls.tedarikci = sayfa_mod.ayristir(
            (ORNEK / "supplier_apl.html").read_text(encoding="utf-8"),
            "supplier/apl-logistics-vietnam")

    def test_firma_temel(self):
        self.assertEqual(self.firma["tur"], "firma")
        self.assertEqual(self.firma["ad"], "Nike")
        self.assertTrue(self.firma["adres"])
        self.assertTrue(self.firma["satirlar"])
        self.assertGreaterEqual(len(self.firma["satirlar"]), 5)
        self.assertGreaterEqual(len(self.firma["ulkeler"]), 5)

    def test_firma_satir_sema(self):
        ilk = self.firma["satirlar"][0]
        self.assertTrue(ilk["ad"])
        self.assertTrue(ilk["url"].startswith(("supplier/", "company/")))
        self.assertIsInstance(ilk["sefer"], int)
        self.assertGreater(ilk["sefer"], 0)

    def test_ulkeler_oku(self):
        ulkeler = self.firma["ulkeler"]
        self.assertGreaterEqual(len(ulkeler), 5)
        self.assertTrue(all(u["ulke"] for u in ulkeler))
        self.assertTrue(all(isinstance(u["sefer"], int) for u in ulkeler))
        self.assertEqual(ulkeler[0], {"ulke": "Vietnam", "sefer": 200})

    def test_ozet_tutarli(self):
        oz = self.firma["ozet"]
        self.assertEqual(oz["bagli_sayisi"], len(self.firma["satirlar"]))
        self.assertEqual(oz["ulke_sayisi"],
                         len({u["ulke"] for u in self.firma["ulkeler"]}))
        self.assertTrue(oz["son_sevkiyat"])

    def test_tedarikci_tur(self):
        self.assertEqual(self.tedarikci["tur"], "tedarikçi")
        self.assertTrue(self.tedarikci["ad"])
        self.assertTrue(self.tedarikci["satirlar"])

    def test_tedarikci_baglantilar_firma(self):
        turler = {s["url"].split("/", 1)[0]
                  for s in self.tedarikci["satirlar"]}
        self.assertTrue(turler <= {"company", "supplier"})


class YardimciTesti(unittest.TestCase):
    """Küçük ayrıştırma yardımcıları."""

    def test_basligi_coz(self):
        self.assertEqual(
            sayfa_mod._basligi_coz(
                "Nike - 1 Bowerman Dr, Beaverton - company Report - Import Yeti"),
            ("Nike", "1 Bowerman Dr, Beaverton"))

    def test_basligi_coz_tek_parca(self):
        self.assertEqual(sayfa_mod._basligi_coz("Tek"), ("Tek", ""))

    def test_basligi_coz_bos(self):
        self.assertEqual(sayfa_mod._basligi_coz(""), ("", ""))

    def test_sayi_deger(self):
        self.assertEqual(sayfa_mod._sayi_deger("188 Footwear"), 188)
        self.assertEqual(sayfa_mod._sayi_deger("1.234"), 1234)
        self.assertIsNone(sayfa_mod._sayi_deger("yok"))

    def test_slug_gecerlilik(self):
        self.assertEqual(sayfa_mod._slugi_temizle(" company/nike/"),
                         "company/nike")
        with self.assertRaises(ValueError):
            sayfa_mod._slugi_temizle("bir-sayfa")


class CliTesti(unittest.TestCase):
    """GUI'nin çağırdığı CLI sözleşmesi."""

    def test_ara_argumanlari(self):
        a = argumanlari(["ara", "nike", "--sayfa", "2", "--json", "x.json"])
        self.assertEqual(a.komut, "ara")
        self.assertEqual(a.hedef, "nike")
        self.assertEqual(a.sayfa, 2)
        self.assertEqual(a.json_yol, "x.json")

    def test_gcm_komut(self):
        a = argumanlari(["firma", "company/nike"])
        self.assertEqual(a.komut, "firma")
        self.assertTrue(a.json_yol.endswith("ithalat_gui.json"))

    def test_gecersiz_komut(self):
        with self.assertRaises(SystemExit):
            argumanlari(["yok", "hedef"])


if __name__ == "__main__":
    unittest.main()
