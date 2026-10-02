#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""polar_lisans.py testleri — sahte HTTP ile (ağ çağrılmaz).

Polar uçları auth'suz olduğu için istemcide sır yok; burada sınanan şey
istemci mantığı: önbellek tazeliği, çevrimdışı lütuf, hata kodlarının
çözümü, biçim ayrımı (RN1 vs Polar) ve CLI çıkış kodu 5.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import lisans
import polar_lisans
import rakip_takip as cekirdek

GENEL = "1C285B2D-6CE6-4BC7-B8BE-ADB6A7E304DA"      # Polar biçimi anahtar
ORG = "fda84e25-7b55-4d67-916d-60ead04ff61f"


class TemelTest(unittest.TestCase):
    """Ortak kurulum: önbellek temp klasörüne, test modu kapatılır."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.onay = Path(self._tmp.name) / "polar_onay.json"
        self._eski_yol = polar_lisans.ONAY_YOL
        polar_lisans.ONAY_YOL = self.onay
        self._ortam = mock.patch.object(lisans, "test_mi", return_value=False)
        self._ortam.start()
        self._env = mock.patch.dict(os.environ, {"POLAR_ORG_ID": ORG})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._ortam.stop()
        polar_lisans.ONAY_YOL = self._eski_yol
        self._tmp.cleanup()

    @staticmethod
    def _kontrol(config=None, zorla=False, yanit=None, cagri_sayaci=None):
        """``lisans_kontrol`` çağrısını sahte ``_post`` ile yapar."""
        def _saglayici(yol, veri):
            if cagri_sayaci is not None:
                cagri_sayaci.append((yol, veri))
            return yanit or (200, {"id": "act-1"})
        with mock.patch.object(polar_lisans, "_post", side_effect=_saglayici):
            return polar_lisans.lisans_kontrol(config or {}, zorla=zorla)


class KimlikTesti(TemelTest):
    def test_rn1_biimi_ayrimitir(self):
        self.assertTrue(polar_lisans.rn1_mi("RN1-ABCDEF01-" + "A" * 103))
        self.assertTrue(polar_lisans.rn1_mi("  rn1-x  "))
        self.assertFalse(polar_lisans.rn1_mi(GENEL))
        self.assertFalse(polar_lisans.rn1_mi("RN1_YOK"))

    def test_sirket_id_siralamasi(self):
        os.environ["POLAR_ORG_ID"] = "env-org"
        self.assertEqual(polar_lisans.sirket_id({"ayarlar": {"polar_org_id": "cfg"}}),
                         "env-org")
        os.environ.pop("POLAR_ORG_ID")
        self.assertEqual(polar_lisans.sirket_id({"ayarlar": {"polar_org_id": "cfg"}}),
                         "cfg")
        os.environ.pop("POLAR_ORG_ID", None)
        eski = polar_lisans.ORG_ID
        polar_lisans.ORG_ID = "modul-org"
        try:
            self.assertEqual(polar_lisans.sirket_id({}), "modul-org")
            polar_lisans.ORG_ID = ""
            self.assertEqual(polar_lisans.sirket_id({}), "")
        finally:
            polar_lisans.ORG_ID = eski

    def test_makine_etiketi_kararli_ve_kisa(self):
        ilk = polar_lisans.makine_etiketi()
        self.assertEqual(ilk, polar_lisans.makine_etiketi())
        self.assertTrue(ilk.startswith("CIHAZ-"))
        self.assertEqual(len(ilk), len("CIHAZ-") + 8)


class PasifModTesti(TemelTest):
    def test_test_modunda_ag_cagirilmaz(self):
        with mock.patch.object(lisans, "test_mi", return_value=True):
            with mock.patch.object(polar_lisans, "_post") as post:
                ok, _ = polar_lisans.lisans_kontrol({"lisans": GENEL})
        self.assertTrue(ok)
        post.assert_not_called()

    def test_anahtar_yokken_ag_cagirilmaz(self):
        cagri: list = []
        ok, mesaj = self._kontrol({}, yanit=(999, None), cagri_sayaci=cagri)
        self.assertTrue(ok)
        self.assertEqual(cagri, [])

    def test_rn1_anahtari_polar_cagirmaz(self):
        cagri: list = []
        with mock.patch.object(lisans, "anahtar_gecerli", return_value=True):
            ok, mesaj = self._kontrol({"lisans": "RN1-ABCDEF01-" + "A" * 103},
                                      yanit=(404, None), cagri_sayaci=cagri)
        self.assertTrue(ok)
        self.assertEqual(cagri, [])
        self.assertIn("yerel imza", mesaj)

    def test_rn1_gecersiz_imza_yerelde_kilit(self):
        cagri: list = []
        with mock.patch.object(lisans, "anahtar_gecerli", return_value=False):
            ok, mesaj = self._kontrol({"lisans": "RN1-00000000-" + "A" * 103},
                                      yanit=(200, {}), cagri_sayaci=cagri)
        self.assertFalse(ok)
        self.assertEqual(cagri, [])

    def test_polar_anahtari_org_yokken_kapali(self):
        os.environ.pop("POLAR_ORG_ID", None)
        eski = polar_lisans.ORG_ID
        polar_lisans.ORG_ID = ""
        try:
            ok, mesaj = self._kontrol({"lisans": GENEL, "ayarlar": {}})
        finally:
            polar_lisans.ORG_ID = eski
        self.assertFalse(ok)
        self.assertIn("yapılandırılmamış", mesaj)


class CevrimIciAkisTesti(TemelTest):
    def test_etkinlestir_ve_dogrula_basarili(self):
        cagri: list = []
        ok, mesaj = self._kontrol({"lisans": GENEL}, cagri_sayaci=cagri)
        self.assertTrue(ok, mesaj)
        self.assertEqual([y for y, _ in cagri], ["/activate", "/validate"])
        akt = cagri[0][1]
        self.assertEqual(akt["key"], GENEL)
        self.assertEqual(akt["organization_id"], ORG)
        self.assertIn("label", akt)
        self.assertEqual(cagri[1][1].get("activation_id"), "act-1")
        veri = json.loads(self.onay.read_text(encoding="utf-8"))
        self.assertEqual(veri["durum"], "gecerli")
        self.assertEqual(veri["etkinlestirme"], "act-1")

    def test_taze_obellek_ag_cagirmaz(self):
        cagri: list = []
        self._kontrol({"lisans": GENEL})                 # bir kez dolsun
        ok, _ = self._kontrol({"lisans": GENEL}, cagri_sayaci=cagri)
        self.assertTrue(ok)
        self.assertEqual(cagri, [])

    def test_zorla_taze_obellege_baskin_gelir(self):
        self._kontrol({"lisans": GENEL})
        cagri: list = []
        ok, _ = self._kontrol({"lisans": GENEL}, zorla=True, cagri_sayaci=cagri)
        self.assertTrue(ok)
        self.assertTrue(cagri)

    def test_cihaz_limiti_dolu(self):
        ok, mesaj = self._kontrol({"lisans": GENEL}, yanit=(403, {"error": "x"}))
        self.assertFalse(ok)
        self.assertIn("cihaz limiti", mesaj)

    def test_iptal_edilmis_lisans(self):
        self._kontrol({"lisans": GENEL})                 # etkinleşsin
        ok, mesaj = self._kontrol({"lisans": GENEL}, zorla=True,
                                  yanit=(404, {"error": "ResourceNotFound"}))
        self.assertFalse(ok)
        self.assertIn("geçersiz", mesaj)
        veri = json.loads(self.onay.read_text(encoding="utf-8"))
        self.assertEqual(veri["durum"], "gecersiz")

    def test_ikinci_etkinlestirme_istemez(self):
        cagri: list = []
        self._kontrol({"lisans": GENEL})                 # activate bir kez
        ok, _ = self._kontrol({"lisans": GENEL}, zorla=True, cagri_sayaci=cagri)
        self.assertTrue(ok)
        self.assertEqual([y for y, _ in cagri], ["/validate"])   # activate yok


class CevrimDisiTesti(TemelTest):
    def test_aga_gitsin_ama_lutuf_varsa_devam(self):
        self._kontrol({"lisans": GENEL})                 # başarılı doğrulama
        ok, mesaj = self._kontrol({"lisans": GENEL}, zorla=True, yanit=(0, None))
        self.assertTrue(ok, mesaj)
        self.assertIn("çevrimdışı", mesaj)

    def test_ilk_kurulumda_agsiz_calismaz(self):
        ok, mesaj = self._kontrol({"lisans": GENEL}, yanit=(0, None))
        self.assertFalse(ok)
        self.assertIn("internet", mesaj)

    def test_lutuf_suresi_dolunca_kilit(self):
        self._kontrol({"lisans": GENEL})
        veri = json.loads(self.onay.read_text(encoding="utf-8"))
        veri["son_onay"] = time.time() - polar_lisans.CEVRIM_DISI_GRACE - 10
        self.onay.write_text(json.dumps(veri), encoding="utf-8")
        ok, mesaj = self._kontrol({"lisans": GENEL}, zorla=True, yanit=(0, None))
        self.assertFalse(ok)
        self.assertIn("internet", mesaj)

    def test_obellek_baska_anahtara_aitse_lutuf_yok(self):
        self._kontrol({"lisans": GENEL})
        ok, _ = self._kontrol({"lisans": GENEL + "F"}, zorla=True, yanit=(0, None))
        self.assertFalse(ok)


class CliAktivasyonTesti(unittest.TestCase):
    """``rakip_takip.py``: Polar reddederse çıkış 5, kabul ederse kaydeder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        kok = Path(self._tmp.name)
        self.config = kok / "config.json"
        # Çoğu test Polar anahtarıyla çalışır (Polar kanalı aktif olsun).
        self.config.write_text(json.dumps(
            {"ayarlar": {}, "urunler": [], "lisans": GENEL}),
            encoding="utf-8")
        self._eski_yol = polar_lisans.ONAY_YOL
        polar_lisans.ONAY_YOL = kok / "polar_onay.json"
        self._ortam = mock.patch.object(lisans, "test_mi", return_value=False)
        self._ortam.start()
        self._org = mock.patch.dict(os.environ, {"POLAR_ORG_ID": ORG})
        self._org.start()

    def tearDown(self):
        self._org.stop()
        self._ortam.stop()
        polar_lisans.ONAY_YOL = self._eski_yol
        self._tmp.cleanup()

    def _calistir(self, *arglar):
        with mock.patch.object(sys, "argv",
                               [sys.argv[0], "--config", str(self.config),
                                *arglar]):
            cekirdek.main()

    def test_polar_reddederse_cikis_5(self):
        with mock.patch.object(polar_lisans, "_post",
                               return_value=(404, {"error": "ResourceNotFound"})):
            with self.assertRaises(SystemExit) as hata:
                self._calistir("--rapor")
        self.assertEqual(hata.exception.code, cekirdek.CIKIS_AKTIVASYON)

    def test_polar_kabul_ederse_calisir(self):
        def _sahte(yol, veri):
            return (200, {"id": "act-1"}) if yol == "/activate" else (200, {})
        with mock.patch.object(polar_lisans, "_post", side_effect=_sahte):
            with mock.patch.object(cekirdek, "rapor_yazdir") as rapor:
                self._calistir("--rapor")
        rapor.assert_called_once()

    def test_rn1_anahtari_polar_kontrolunden_gecer(self):
        anahtar = "RN1-ABCDEF01-" + "A" * 103
        veri = json.loads(self.config.read_text(encoding="utf-8"))
        veri["lisans"] = anahtar
        self.config.write_text(json.dumps(veri), encoding="utf-8")
        with mock.patch.object(polar_lisans, "_post") as post:
            with mock.patch.object(cekirdek, "rapor_yazdir") as rapor:
                with mock.patch.object(lisans, "anahtar_gecerli", return_value=True):
                    self._calistir("--rapor")
        rapor.assert_called_once()
        post.assert_not_called()

    def test_lisans_kaydederken_polar_konusur(self):
        yeni = "2C285B2D-6CE6-4BC7-B8BE-ADB6A7E304DB"
        with mock.patch.object(polar_lisans, "_post",
                               return_value=(403, {"error": "NotPermitted"})):
            with self.assertRaises(SystemExit) as hata:
                self._calistir("--lisans", yeni)
        self.assertEqual(hata.exception.code, cekirdek.CIKIS_AKTIVASYON)
        veri = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(veri["lisans"], GENEL)          # eskisi korundu

    def test_lisans_polar_basarliysa_kaydolur(self):
        yeni = "3C285B2D-6CE6-4BC7-B8BE-ADB6A7E304DC"
        def _sahte(yol, veri):
            return (200, {"id": "act-2"}) if yol == "/activate" else (200, {})
        with mock.patch.object(polar_lisans, "_post", side_effect=_sahte):
            self._calistir("--lisans", yeni)
        veri = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(veri["lisans"], yeni)

    def test_rn1_imzasiz_lisans_kabul_edilmez(self):
        with mock.patch.object(lisans, "anahtar_gecerli", return_value=False):
            with self.assertRaises(SystemExit) as hata:
                self._calistir("--lisans", "RN1-00000000-" + "A" * 103)
        self.assertEqual(hata.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
