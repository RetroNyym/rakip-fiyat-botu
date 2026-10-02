# -*- coding: utf-8 -*-
"""lisans.py testleri — anahtar üretimi/doğrulama, sayaç, GUI koruması.

Ekran (tkinter) yoksa GUI testleri sessizce atlanır.

Çalıştırma:
    python -m unittest discover -v
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Test modu: ipucu balonu/kilit etkileşimi açılmasın (lisans notu da susar)
os.environ["RIYA_TESTI"] = "1"

import lisans
import rakip_takip as cekirdek

# ---------------------------------------------------------------------------
#  Test anahtar çifti
# ---------------------------------------------------------------------------
# Üretim (gerçek) imzalama anahtarı ``lisans_uret.py`` içindedir ve git'e
# girmez → public CI'da mevcut değildir. Bu yüzden testler kendi Ed25519
# anahtar çiftlerini üretir ve ``lisans._GENEL_ANAHTAR``'ı geçici olarak
# bunla değiştirir (mekanizma test edilir, üretim anahtarı değil).
# Gerçek anahtar çifti yalnızca satıcı makinesinde ek testle doğrulanır.
ORIJINAL_GENEL_ANAHTAR = lisans._GENEL_ANAHTAR

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_TEST_OZEL_ANAHTAR = Ed25519PrivateKey.generate()
_TEST_GENEL_ANAHTAR = _TEST_OZEL_ANAHTAR.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _imza(govde: str) -> str:
    """Test anahtarıyla ``govde`` imzası (base32, 103 karakter)."""
    imza = _TEST_OZEL_ANAHTAR.sign(f"RN1|{govde}".encode("utf-8"))
    return base64.b32encode(imza).decode("ascii").rstrip("=")


def anahtar_uret(govde: str | None = None) -> str:
    """Test anahtarıyla geçerli biçimde lisans anahtarı üretir."""
    if govde is None:
        govde = secrets.token_hex(lisans._GOVDE_UZUNLUK // 2).upper()
    return f"{lisans.ANAHTAR_ONEK}-{govde}-{_imza(govde)}"


def setUpModule():
    """Genel anahtarı yalnızca bu modülün testleri boyunca değiştir.

    Import anasında yapılıyordu; pytest/unittest tüm modülleri önce
    topluca içe aktardığı için diğer test modülleri de (ör.
    ``test_anahtar_servisi``) sahte anahtarla çalışıyordu.
    """
    lisans._GENEL_ANAHTAR = _TEST_GENEL_ANAHTAR


def tearDownModule():
    """Üretim genel anahtarını geri koy (sonraki test modülleri için)."""
    lisans._GENEL_ANAHTAR = ORIJINAL_GENEL_ANAHTAR

try:
    import tkinter                                              # noqa: F401
    EKRAN_VAR = True
except Exception:                                   # noqa: BLE001
    EKRAN_VAR = False

if EKRAN_VAR:
    import gui


class AnahtarTesti(unittest.TestCase):
    """RN1-… anahtar üretimi ve Ed25519 doğrulaması (test anahtarıyla).

    Üretim ``lisans_uret.py`` (satıcı) içindedir ve git'e girmez; ``lisans.py``
    yalnızca genel anahtarla doğrular — dağıtılan kodla anahtar üretemez.
    """

    def test_uret_ve_dogrula(self):
        anahtar = anahtar_uret()
        self.assertTrue(lisans.anahtar_gecerli(anahtar))
        parca = anahtar.split("-")
        self.assertEqual(parca[0], "RN1")
        self.assertEqual(len(parca[1]), 8)
        self.assertEqual(len(parca[2]), lisans._IMZA_UZUNLUK)

    def test_kucuk_harf_kabul(self):
        anahtar = anahtar_uret()
        self.assertTrue(lisans.anahtar_gecerli(anahtar.lower()))

    def test_uzunluklar_farkli(self):
        self.assertNotEqual(anahtar_uret(),
                            anahtar_uret())

    def test_gecersiz_girdiler(self):
        for hatali in ("", "RN1", "RN1-ABCDEF12", None, 42, [], {},
                       "RN2-ABCDEF12-0123456789AB",
                       "RN1-ABCDEF12-0123456789ABCD",
                       "RN1-ABCDEF12-" + "A" * 103,        # imzasız gövde
                       "RN1-ABCDEF12-" + "0" * 103):       # base32 dışı
            self.assertFalse(lisans.anahtar_gecerli(hatali), repr(hatali))

    def test_imzasiz_anahtar_red(self):
        anahtar = anahtar_uret()
        govde = anahtar.split("-")[1]
        self.assertFalse(
            lisans.anahtar_gecerli(f"RN1-{govde}-" + "A" * 103))

    def test_baska_govdeye_taklit(self):
        govde1 = anahtar_uret().split("-")[1]
        govde2 = anahtar_uret().split("-")[1]
        self.assertTrue(lisans.anahtar_gecerli(anahtar_uret()))
        # govde2'ye govde1'in imzasını yapıştırmak geçersizdir
        sahte = f"RN1-{govde2}-{_imza(govde1)}"
        self.assertFalse(lisans.anahtar_gecerli(sahte))

    def test_uretim_anahtari_kaynakta_yok(self):
        """lisans.py içinde imzalayabilen özel anahtar bulunmamalı."""
        kaynak = Path(lisans.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_OZEL_ANAHTAR", kaynak)     # özel anahtar yok
        self.assertNotIn("sign(", kaynak)             # imzalama yok
        self.assertIn("_GENEL_ANAHTAR", kaynak)       # doğrulama var
        self.assertTrue(lisans.KRIPTO_VAR)

    def test_anahtar_uzunluklari(self):
        self.assertEqual(len(lisans._GENEL_ANAHTAR), 32)      # Ed25519 genel
        self.assertEqual(len(anahtar_uret().split("-")[2]),
                         lisans._IMZA_UZUNLUK)


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
        self._ayna = Path(self._tmp.name) / "limit-ayna.json"
        self._eski_yol = lisans.LIMIT_YOL
        self._eski_ayna = lisans.AYNA_YOL
        lisans.LIMIT_YOL = self._limit
        lisans.AYNA_YOL = self._ayna
        self.app.ayar.pop("lisans", None)

    def tearDown(self):
        lisans.LIMIT_YOL = self._eski_yol
        lisans.AYNA_YOL = self._eski_ayna
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
            self.app.ayar["lisans"] = anahtar_uret()
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


    def test_gui_hak_tuket_riya_ic_bypass_yapmaz(self):
        """RIYA_IC=1 yalnızca alt süreçler içindir; GUI'de sayılmaz."""
        self._test_modunu_kapat()
        try:
            with mock.patch.dict(os.environ, {"RIYA_IC": "1"}):
                self.assertTrue(self.app._hak_tuket("Tarama"))
            self.assertEqual(lisans.hak_oku(self._limit), 1)
        finally:
            os.environ.pop("RIYA_IC", None)
            os.environ["RIYA_TESTI"] = "1"


class AynaSayaciTesti(unittest.TestCase):
    """Sayaç iki kopyalıdır: ana dosya + APPDATA aynası (silinemez)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        kok = Path(self._tmp.name)
        self._limit = kok / "limit.json"
        self._ayna = kok / "ayna" / "limit.json"
        self._eski = (lisans.LIMIT_YOL, lisans.AYNA_YOL)
        lisans.LIMIT_YOL, lisans.AYNA_YOL = self._limit, self._ayna

    def tearDown(self):
        lisans.LIMIT_YOL, lisans.AYNA_YOL = self._eski
        self._tmp.cleanup()

    def test_yeni_kurulumda_hak_sifir(self):
        self.assertEqual(lisans.hak_oku(), 0)
        self.assertEqual(lisans.hak_kalan(), lisans.HAK_SINIRI)

    def test_tuketimde_iki_dosya_yazilir(self):
        self.assertTrue(lisans.hak_tuket())
        self.assertTrue(self._limit.exists())
        self.assertTrue(self._ayna.exists())
        self.assertEqual(lisans.hak_oku(), 1)

    def test_ana_dosya_silinirse_ayna_kurtarir(self):
        for _ in range(lisans.HAK_SINIRI):
            self.assertTrue(lisans.hak_tuket())
        self._limit.unlink()
        self.assertEqual(lisans.hak_oku(), lisans.HAK_SINIRI)
        self.assertFalse(lisans.hak_tuket())          # sıfırlanamaz → kilit

    def test_ayna_silinirse_ana_dosya_kurtarir(self):
        for _ in range(lisans.HAK_SINIRI):
            self.assertTrue(lisans.hak_tuket())
        self._ayna.unlink()
        self.assertEqual(lisans.hak_oku(), lisans.HAK_SINIRI)
        self.assertFalse(lisans.hak_tuket())

    def test_bozuk_ayna_kilit(self):
        lisans.hak_yaz(2)
        self._ayna.parent.mkdir(parents=True, exist_ok=True)
        self._ayna.write_text("{bozuk json", encoding="utf-8")
        self.assertEqual(lisans.hak_oku(), lisans.HAK_SINIRI)
        self.assertFalse(lisans.hak_tuket())

    def test_bozuk_ana_dosya_kilit(self):
        lisans.hak_yaz(2)
        self._limit.write_text("{bozuk json", encoding="utf-8")
        self.assertEqual(lisans.hak_oku(), lisans.HAK_SINIRI)

    def test_buyuk_deger_kazanir(self):
        lisans._tek_yaz(self._limit, 3)
        lisans._tek_yaz(self._ayna, 1)
        self.assertEqual(lisans.hak_oku(), 3)

    def test_hak_sifirla_iki_tarafi_da_sifirlar(self):
        for _ in range(lisans.HAK_SINIRI):
            lisans.hak_tuket()
        lisans.hak_sifirla()
        self.assertEqual(lisans.hak_oku(), 0)


class TestModuTesti(unittest.TestCase):
    """``RIYA_TESTI`` tek başına yeterli değildir (rağbet engeli)."""

    def setUp(self):
        self._eski = os.environ.get("RIYA_TESTI")
        os.environ["RIYA_TESTI"] = "1"

    def tearDown(self):
        if self._eski is None:
            os.environ.pop("RIYA_TESTI", None)
        else:
            os.environ["RIYA_TESTI"] = self._eski

    @staticmethod
    def _kanitsiz():
        """Test çalıştırıcısı kanıtlarını (env + argv[0]) geçici olarak söker.

        Önce ``patch.dict``'i başlatır (çıkışta her şeyi geri koyar), sonra
        siler — aksi hâlde ``CI``/``PYTEST_CURRENT_TEST`` kalıcı giderdi.
        """
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        os.environ.pop("PYTEST_CURRENT_TEST", None)
        os.environ.pop("CI", None)
        os.environ.pop("GITHUB_ACTIONS", None)
        argv = mock.patch.object(sys, "argv",
                                 ["C:/uygulama/RakipFiyatBot.exe"])
        argv.start()
        return [env, argv]

    @staticmethod
    def _kanit_kur(yamalar):
        for y in yamalar:
            y.stop()

    def test_pytest_kaniti_varken_acik(self):
        """pytest her test sırasında kurduğu iz test modunu açar."""
        with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "a (call)"}):
            self.assertTrue(lisans.test_mi())

    def test_kanit_yokken_kapali(self):
        """RIYA_TESTI=1 + kanıt yok → kapalı (rağbet engeli)."""
        yamalar = self._kanitsiz()
        try:
            self.assertFalse(lisans.test_mi())
        finally:
            self._kanit_kur(yamalar)

    def test_sahte_pytest_modulu_yetmez(self):
        """sys.modules'e sahte ``pytest`` sokmak test modunu açamaz."""
        import types
        onceki = sys.modules.get("pytest")
        sys.modules["pytest"] = types.ModuleType("pytest")
        yamalar = self._kanitsiz()
        try:
            self.assertNotIn("PYTEST_CURRENT_TEST", os.environ)
            self.assertFalse(lisans.test_mi())
        finally:
            self._kanit_kur(yamalar)
            if onceki is None:
                sys.modules.pop("pytest", None)
            else:
                sys.modules["pytest"] = onceki

    def test_sahte_unittest_importu_yetmez(self):
        """Sadece ``import unittest`` yapmak (herkeste var) yetmez."""
        import unittest as _u                      # noqa: F401
        yamalar = self._kanitsiz()
        try:
            self.assertIn("unittest", sys.modules)
            self.assertFalse(lisans.test_mi())
        finally:
            self._kanit_kur(yamalar)

    def test_unittest_argv0_kaniti(self):
        """``python -m unittest`` argv[0] izi test modunu açar."""
        with mock.patch.object(
                sys, "argv",
                ["C:/Python314/Lib/unittest/__main__.py", "discover"]):
            self.assertTrue(lisans.test_mi())
        with mock.patch.object(sys, "argv", ["/opt/py/test_lisans.py"]):
            self.assertTrue(lisans.test_mi())

    def test_riya_yoksa_kapali(self):
        os.environ.pop("RIYA_TESTI", None)
        self.assertFalse(lisans.test_mi())

    def test_ci_ortaminda_kanit_gerekmez(self):
        yamalar = self._kanitsiz()
        try:
            with mock.patch.dict(os.environ, {"CI": "1"}):
                self.assertTrue(lisans.test_mi())
        finally:
            self._kanit_kur(yamalar)

    def test_ic_cagri_ortam_degiskeni(self):
        with mock.patch.dict(os.environ, {"RIYA_IC": "1"}):
            self.assertTrue(lisans.ic_cagri())
        os.environ.pop("RIYA_IC", None)
        self.assertFalse(lisans.ic_cagri())


class SifirlamaJetonuTesti(unittest.TestCase):
    """``hak_sifirla`` dağıtılan kodla çağrılamaz (jeton Ed25519 imzalı)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        kok = Path(self._tmp.name)
        self._limit = kok / "limit.json"
        self._ayna = kok / "ayna" / "limit.json"
        self._eski = (lisans.LIMIT_YOL, lisans.AYNA_YOL)
        lisans.LIMIT_YOL, lisans.AYNA_YOL = self._limit, self._ayna
        lisans.hak_yaz(3)                               # 3 hak harcanmış

    def tearDown(self):
        lisans.LIMIT_YOL, lisans.AYNA_YOL = self._eski
        self._tmp.cleanup()
        os.environ["RIYA_TESTI"] = "1"

    @staticmethod
    def _gercek_mod():
        return mock.patch.dict(os.environ, {}, clear=True)   # RIYA_TESTI gider

    def test_jetonsuz_sifirlanamaz(self):
        with self._gercek_mod():
            self.assertFalse(lisans.hak_sifirla())
        self.assertEqual(lisans.hak_oku(), 3)          # sayaç olduğu gibi

    def test_sahte_jeton_sifirlamaz(self):
        sahte = "SIFIRLA-0123456789ABCDEF-" + "A" * 103
        with self._gercek_mod():
            self.assertFalse(lisans.hak_sifirla(jeton=sahte))
        self.assertEqual(lisans.hak_oku(), 3)

    def test_yanlis_biimli_jetonlar(self):
        for jeton in ("", "RN1-00000000-" + "A" * 103, "SIFIRLA-kucuk-" + "A" * 103,
                      "SIFIRLA-0123456789ABCDEF-" + "A" * 102,
                      "SIFIRLA-0123456789ABCDEF-" + "1" * 103):
            with self._gercek_mod():
                self.assertFalse(lisans.sifirlama_jetonu_gecerli(jeton))

    def test_gercek_jeton_sifirlar(self):
        nonce = "FEEDFACE12345678"
        jeton = f"SIFIRLA-{nonce}-{_imza(f'SIFIRLA|{nonce}')}"
        self.assertTrue(lisans.sifirlama_jetonu_gecerli(jeton))
        with self._gercek_mod():
            self.assertTrue(lisans.hak_sifirla(jeton=jeton))
        self.assertEqual(lisans.hak_oku(), 0)

    def test_test_modunda_jeton_gerekmez(self):
        os.environ["RIYA_TESTI"] = "1"
        self.assertTrue(lisans.hak_sifirla())
        self.assertEqual(lisans.hak_oku(), 0)

    def test_ayar_izinli(self):
        anahtar = anahtar_uret()
        eski = os.environ.pop("RIYA_TESTI", None)
        try:
            self.assertTrue(lisans.ayar_izinli({"lisans": anahtar}))
            self.assertFalse(lisans.ayar_izinli({"lisans": "RN1-00000000-AAAA"}))
            self.assertFalse(lisans.ayar_izinli({}))
            self.assertFalse(lisans.ayar_izinli(None))
        finally:
            if eski is not None:
                os.environ["RIYA_TESTI"] = eski
        # test modu açıkken lisanssız da izin vardır
        os.environ["RIYA_TESTI"] = "1"
        self.assertTrue(lisans.ayar_izinli({}))


class CliLisansTesti(unittest.TestCase):
    """``rakip_takip.py`` CLI: tarama/inspect hak harcar, ``--lisans`` kaydeder."""

    def setUp(self):
        os.environ["RIYA_TESTI"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        kok = Path(self._tmp.name)
        self.config = kok / "config.json"
        self._config_yaz({})
        self._eski = (lisans.LIMIT_YOL, lisans.AYNA_YOL)
        lisans.LIMIT_YOL = kok / "limit.json"
        lisans.AYNA_YOL = kok / "ayna.json"

    def tearDown(self):
        lisans.LIMIT_YOL, lisans.AYNA_YOL = self._eski
        self._tmp.cleanup()
        os.environ["RIYA_TESTI"] = "1"

    def _config_yaz(self, veri: dict) -> None:
        veri.setdefault("ayarlar", {})
        veri.setdefault("urunler", [])
        self.config.write_text(json.dumps(veri, ensure_ascii=False),
                               encoding="utf-8")

    def _calistir(self, *arglar):
        # argv[0]'ı bozmuyoruz: lisans.test_mi() koşucu kanıtını argv[0]'dan
        # okur (pytest ayrıca PYTEST_CURRENT_TEST ortam değişkenini kurar).
        with mock.patch.object(sys, "argv",
                               [sys.argv[0], "--config",
                                str(self.config), *arglar]):
            cekirdek.main()

    def _gercek_mod(self):
        os.environ.pop("RIYA_TESTI", None)

    def test_riya_ic_ile_ucretsiz_gecilemez(self):
        """CLI ``RIYA_IC=1``i dikkate almaz → hak yine harcanır.

        (GUI ``rakip_takip.py``'yi hiç bu bayrakla çağırmaz; dikkate
        alınsaydı kullanıcı tek satırla sınırı aşabilirdi.)
        """
        with mock.patch.dict(os.environ, {"RIYA_IC": "1"}, clear=True):
            self.assertTrue(cekirdek._hak_al({}, "Tarama"))
        self.assertEqual(lisans.hak_oku(), 1)     # atlamadı, harcadı
        with mock.patch.dict(os.environ, {"RIYA_IC": "1"}, clear=True):
            self.assertTrue(cekirdek._hak_al({}, "Tarama"))
        self.assertEqual(lisans.hak_oku(), 2)

    def test_lisans_kaydedilir_ve_tarama_baslamaz(self):
        anahtar = anahtar_uret()
        with mock.patch.object(cekirdek, "tarama_yap") as tarama:
            self._calistir("--lisans", anahtar)
        tarama.assert_not_called()                  # yalnızca aktivasyon
        veri = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(veri["lisans"], anahtar)
        self.assertEqual(lisans.hak_oku(), 0)

    def test_lisans_alanisi_cikis_kodu_1(self):
        with mock.patch.object(cekirdek, "tarama_yap"):
            with self.assertRaises(SystemExit) as hata:
                self._calistir("--lisans", "RN1-00000000-" + "A" * 103)
        self.assertEqual(hata.exception.code, 1)

    def test_hak_dolunca_cikis_kodu_4(self):
        lisans.hak_yaz(lisans.HAK_SINIRI)
        self._gercek_mod()
        try:
            with mock.patch.object(cekirdek, "tarama_yap") as tarama:
                with self.assertRaises(SystemExit) as hata:
                    self._calistir()
            self.assertEqual(hata.exception.code, cekirdek.CIKIS_LISANS)
            tarama.assert_not_called()
        finally:
            os.environ["RIYA_TESTI"] = "1"

    def _sifirla_calistir(self, jeton: str) -> None:
        """``--sifirla``'yı üretim kanıtsız (gerçek kullanıcı modu) çalıştırır."""
        yamalar = TestModuTesti._kanitsiz()
        try:
            self._calistir("--sifirla", jeton)
        finally:
            TestModuTesti._kanit_kur(yamalar)

    def test_sifirla_gercek_jetonda_sifirlar(self):
        """Satıcı jetonu test kanıtı olmadan da sayacı sıfırlar."""
        lisans.hak_yaz(5)
        nonce = "AABBCCDDEEFF0011"
        jeton = f"SIFIRLA-{nonce}-{_imza(f'SIFIRLA|{nonce}')}"
        self._sifirla_calistir(jeton)
        self.assertEqual(lisans.hak_oku(), 0)
        self.assertEqual(lisans.hak_kalan(), lisans.HAK_SINIRI)

    def test_sifirla_jetonsuz_cikis_kodu_1(self):
        """Geçersiz jeton → çıkış 1, sayaç olduğu gibi kalır."""
        lisans.hak_yaz(5)
        sahte = "SIFIRLA-0123456789ABCDEF-" + "A" * 103
        yamalar = TestModuTesti._kanitsiz()
        try:
            with self.assertRaises(SystemExit) as hata:
                self._calistir("--sifirla", sahte)
        finally:
            TestModuTesti._kanit_kur(yamalar)
        self.assertEqual(hata.exception.code, 1)
        self.assertEqual(lisans.hak_oku(), 5)

    def test_tarama_bir_hak_harcar(self):
        self._gercek_mod()
        try:
            with mock.patch.object(cekirdek, "tarama_yap") as tarama:
                self._calistir()
            tarama.assert_called_once()
            self.assertEqual(lisans.hak_oku(), 1)
        finally:
            os.environ["RIYA_TESTI"] = "1"

    def test_lisansli_ucretsiz(self):
        self._gercek_mod()
        try:
            self._config_yaz({"lisans": anahtar_uret()})
            with mock.patch.object(cekirdek, "tarama_yap") as tarama:
                self._calistir()
            tarama.assert_called_once()
            self.assertEqual(lisans.hak_oku(), 0)
        finally:
            os.environ["RIYA_TESTI"] = "1"

    def test_test_modunda_ucretsiz(self):
        with mock.patch.object(cekirdek, "tarama_yap") as tarama:
            self._calistir()
        tarama.assert_called_once()
        self.assertEqual(lisans.hak_oku(), 0)

    def test_rapor_hak_harcamaz(self):
        self._gercek_mod()
        try:
            with mock.patch.object(cekirdek, "rapor_yazdir") as rapor:
                self._calistir("--rapor")
            rapor.assert_called_once()
            self.assertEqual(lisans.hak_oku(), 0)
        finally:
            os.environ["RIYA_TESTI"] = "1"


@unittest.skipUnless(Path(__file__).with_name("lisans_uret.py").exists(),
                     "lisans_uret.py yalnızca satıcı makinesinde (git'e girmez)")
class UretimAnahtariTesti(unittest.TestCase):
    """Gerçek (üretim) anahtar çifti — satıcı makinesinde çalışır, CI'da atlanır."""

    def test_uretilen_anahtar_gercek_genel_anahtarla_gecerli(self):
        import lisans_uret
        anahtar = lisans_uret.anahtar_uret()
        eski = lisans._GENEL_ANAHTAR
        lisans._GENEL_ANAHTAR = ORIJINAL_GENEL_ANAHTAR
        try:
            self.assertTrue(lisans.anahtar_gecerli(anahtar))
            self.assertFalse(lisans.anahtar_gecerli(
                "RN1-00000000-" + anahtar.split("-")[2]))
        finally:
            lisans._GENEL_ANAHTAR = eski

    def test_lisans_uret_gizli_anahtar_icermez_gibidir(self):
        """paketle.py'nin tarayacağı değer dosyadan okunabiliyor mu?"""
        import lisans_uret
        self.assertEqual(len(lisans_uret._OZEL_ANAHTAR), 32)


if __name__ == "__main__":
    unittest.main()
