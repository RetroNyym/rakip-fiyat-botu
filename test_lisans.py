# -*- coding: utf-8 -*-
"""lisans.py testleri — anahtar üretimi/doğrulama, sayaç, GUI koruması.

Ekran (tkinter) yoksa GUI testleri sessizce atlanır.

Çalıştırma:
    python -m unittest discover -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Test modu: ipucu balonu/kilit etkileşimi açılmasın (lisans notu da susar)
os.environ["RIYA_TESTI"] = "1"

import lisans

try:
    import tkinter                                              # noqa: F401
    EKRAN_VAR = True
except Exception:                                   # noqa: BLE001
    EKRAN_VAR = False

if EKRAN_VAR:
    import gui


class AnahtarTesti(unittest.TestCase):
    """RN1-… anahtar üretimi ve HMAC doğrulaması."""

    def test_uret_ve_dogrula(self):
        anahtar = lisans.anahtar_uret()
        self.assertTrue(lisans.anahtar_gecerli(anahtar))
        parca = anahtar.split("-")
        self.assertEqual(parca[0], "RN1")
        self.assertEqual(len(parca[1]), 8)
        self.assertEqual(len(parca[2]), 12)

    def test_kucuk_harf_kabul(self):
        anahtar = lisans.anahtar_uret()
        self.assertTrue(lisans.anahtar_gecerli(anahtar.lower()))

    def test_uzunluklar_farkli(self):
        self.assertNotEqual(lisans.anahtar_uret(), lisans.anahtar_uret())

    def test_gecersiz_girdiler(self):
        for hatali in ("", "RN1", "RN1-ABCDEF12", None, 42, [], {},
                       "RN2-ABCDEF12-0123456789AB",
                       "RN1-ABCDEF12-0123456789ABCD"):
            self.assertFalse(lisans.anahtar_gecerli(hatali), repr(hatali))

    def test_imzasiz_anahtar_red(self):
        anahtar = lisans.anahtar_uret()
        govde = anahtar.split("-")[1]
        self.assertFalse(
            lisans.anahtar_gecerli(f"RN1-{govde}-000000000000"))

    def test_baska_govdeye_taklit(self):
        govde1 = lisans.anahtar_uret().split("-")[1]
        govde2 = lisans.anahtar_uret().split("-")[1]
        self.assertTrue(lisans.anahtar_gecerli(lisans.anahtar_uret()))
        # govde2'ye govde1'in imzasını yapıştırmak geçersizdir
        sahte = f"RN1-{govde2}-{lisans._tag(govde1)}"
        self.assertFalse(lisans.anahtar_gecerli(sahte))


class HakTesti(unittest.TestCase):
    """HMAC mühürlü sayaç: 5 hak, tahrif → kilit."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.yol = Path(self._tmp.name) / "limit.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_bos_dosya_sifir(self):
        self.assertEqual(lisans.hak_oku(self.yol), 0)
        self.assertEqual(lisans.hak_kalan(self.yol), lisans.HAK_SINIRI)

    def test_sınira_kadar_tuket(self):
        for _ in range(lisans.HAK_SINIRI):
            self.assertTrue(lisans.hak_tuket(self.yol))
        self.assertFalse(lisans.hak_tuket(self.yol))
        self.assertEqual(lisans.hak_oku(self.yol), lisans.HAK_SINIRI)
        self.assertEqual(lisans.hak_kalan(self.yol), 0)

    def test_tahrif_kilit(self):
        lisans.hak_yaz(2, self.yol)
        veri = json.loads(self.yol.read_text(encoding="utf-8"))
        veri["hak"] = 0                       # mac eski → uyuşmazlık
        self.yol.write_text(json.dumps(veri), encoding="utf-8")
        self.assertEqual(lisans.hak_oku(self.yol), lisans.HAK_SINIRI)
        self.assertFalse(lisans.hak_tuket(self.yol))

    def test_bozuk_dosya_kilit(self):
        self.yol.write_text("bozuk json {{{", encoding="utf-8")
        self.assertEqual(lisans.hak_oku(self.yol), lisans.HAK_SINIRI)

    def test_silinen_dosya_sifirlanir(self):
        lisans.hak_yaz(lisans.HAK_SINIRI, self.yol)
        self.yol.unlink()
        self.assertEqual(lisans.hak_oku(self.yol), 0)
        self.assertTrue(lisans.hak_tuket(self.yol))

    def test_sifirlama(self):
        lisans.hak_yaz(4, self.yol)
        lisans.hak_sifirla(self.yol)
        self.assertEqual(lisans.hak_oku(self.yol), 0)


@unittest.skipUnless(EKRAN_VAR, "ekran (tkinter) yok")
class LisansGuiTesti(unittest.TestCase):
    """GUI'de _hak_tuket koruması: test modu, kilit, lisanslı geçiş."""

    @classmethod
    def setUpClass(cls):
        cls.app = gui.Uygulama()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def setUp(self):
        os.environ["RIYA_TESTI"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self._limit = Path(self._tmp.name) / "limit.json"
        self._eski_yol = lisans.LIMIT_YOL
        lisans.LIMIT_YOL = self._limit
        self.app.ayar.pop("lisans", None)

    def tearDown(self):
        lisans.LIMIT_YOL = self._eski_yol
        self._tmp.cleanup()
        self.app.ayar.pop("lisans", None)
        os.environ["RIYA_TESTI"] = "1"

    def _test_modunu_kapat(self):
        os.environ.pop("RIYA_TESTI", None)

    def test_test_modunda_hak_harcanmaz(self):
        self.assertTrue(self.app._hak_tuket("Ürün Arama"))
        self.assertFalse(self._limit.exists())

    def test_hak_bir_azalir(self):
        self._test_modunu_kapat()
        try:
            self.assertTrue(self.app._hak_tuket("Tarama"))
            self.assertEqual(lisans.hak_oku(self._limit), 1)
            self.assertEqual(lisans.hak_kalan(self._limit),
                             lisans.HAK_SINIRI - 1)
        finally:
            os.environ["RIYA_TESTI"] = "1"

    def test_sinirda_kilit_acilir(self):
        lisans.hak_yaz(lisans.HAK_SINIRI, self._limit)
        self._test_modunu_kapat()
        try:
            with mock.patch.object(self.app, "_lisans_penceresi",
                                   return_value=False) as pencere:
                sonuc = self.app._hak_tuket("İthalat Radarı")
            self.assertFalse(sonuc)
            pencere.assert_called_once()
        finally:
            os.environ["RIYA_TESTI"] = "1"

    def test_lisansli_sinirsiz(self):
        self._test_modunu_kapat()
        try:
            self.app.ayar["lisans"] = lisans.anahtar_uret()
            with mock.patch.object(self.app, "_lisans_penceresi") as pencere:
                self.assertTrue(self.app._hak_tuket("Tarama"))
            pencere.assert_not_called()
            self.assertFalse(self._limit.exists())
        finally:
            os.environ["RIYA_TESTI"] = "1"

    def test_yanlis_anahtar_kilidi_kaldirmaz(self):
        lisans.hak_yaz(lisans.HAK_SINIRI, self._limit)
        self._test_modunu_kapat()
        try:
            self.app.ayar["lisans"] = "RN1-00000000-000000000000"
            with mock.patch.object(self.app, "_lisans_penceresi",
                                   return_value=False):
                self.assertFalse(self.app._hak_tuket("Ürün Arama"))
        finally:
            os.environ["RIYA_TESTI"] = "1"

    def test_otomatik_takip_hak_flag_gonderir(self):
        """Otomatik takip yeniden taraması hak=False ile çağrılır (hak yemez)."""
        self.app.otomatik_takip = True
        try:
            with mock.patch.object(self.app, "tarama_baslat",
                                   return_value=True) as tarama:
                self.app._periyodik_tarama()
            tarama.assert_called_once_with(hak=False)
        finally:
            self.app.otomatik_takip = False


if __name__ == "__main__":
    unittest.main()
