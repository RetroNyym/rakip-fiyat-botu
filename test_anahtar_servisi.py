"""``anahtar_servisi`` — Polar webhook → otomatik lisans anahtarı testleri.

Svip/Standard Webhooks imza doğrulama, e-posta çıkarma, sipariş işleme
(idempotency) ve HTTP uçlarının uçtan uca testi. Ağ erişimi yoktur;
sunucu 127.0.0.1'de geçici portta açılır.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import anahtar_servisi as asrv

GIZLI = "whsec_" + "dGVzdC1nemxpLWtpbGltLWtpdGVjaA=="
URETIM_VAR = asrv.lisans_uret is not None


def _olay(siparis_id: str = "ord_123", eposta: str | None = "Musteri@Ornek.com",
          ek: dict | None = None) -> dict:
    data: dict = {"id": siparis_id, "amount": 1900, "currency": "USD"}
    if eposta:
        data["email"] = eposta
    if ek:
        data.update(ek)
    return {"type": "order.created", "data": data}


def _imzali(olay: dict, gizli: str = GIZLI, sid: str = "msg_1",
            simdi: int | None = None, payload_duzenle=None) -> tuple[bytes, dict]:
    payload = json.dumps(olay, ensure_ascii=False).encode("utf-8")
    if payload_duzenle:
        payload = payload_duzenle(payload)
    simdi = int(time.time()) if simdi is None else simdi
    return payload, asrv.imza_uret(payload, sid, simdi, gizli)


class ImzaDogrulamaTesti(unittest.TestCase):
    def test_gecerli_imza_kabul_edilir(self):
        payload, b = _imzali(_olay())
        self.assertTrue(asrv.imza_dogrula(payload, b, GIZLI))

    def test_degistirilmis_yuk_red(self):
        payload, b = _imzali(_olay())
        payload = payload.replace(b"ord_123", b"ord_999")
        self.assertFalse(asrv.imza_dogrula(payload, b, GIZLI))

    def test_yanlis_gizli_red(self):
        payload, b = _imzali(_olay())
        baska = "whsec_" + "ZGlkZXJlLWd6bGktZGlnZXJl".replace("=", "")
        self.assertFalse(asrv.imza_dogrula(payload, b, baska))

    def test_eski_zaman_damgasi_red(self):
        payload, b = _imzali(_olay(), simdi=int(time.time()) - 3600)
        self.assertFalse(asrv.imza_dogrula(payload, b, GIZLI))

    def test_ileri_zaman_damgasi_red(self):
        payload, b = _imzali(_olay(), simdi=int(time.time()) + 3600)
        self.assertFalse(asrv.imza_dogrula(payload, b, GIZLI))

    def test_eksik_baslik_red(self):
        payload, b = _imzali(_olay())
        for eksik in ("svix-id", "svix-timestamp", "svix-signature"):
            kisilmis = {k: v for k, v in b.items() if k != eksik}
            self.assertFalse(asrv.imza_dogrula(payload, kisilmis, GIZLI))

    def test_v1_on_eki_zorunlu(self):
        payload, b = _imzali(_olay())
        b2 = dict(b)
        b2["svix-signature"] = b["svix-signature"].replace("v1,", "v2,")
        self.assertFalse(asrv.imza_dogrula(payload, b2, GIZLI))

    def test_birden_fazla_imzadan_biri_tutar(self):
        payload, b = _imzali(_olay())
        b2 = dict(b)
        b2["svix-signature"] = "v1,YANLIS= " + b["svix-signature"]
        self.assertTrue(asrv.imza_dogrula(payload, b2, GIZLI))

    def test_bas_gizli_de__calisir(self):
        duz = "c2VkZXRpbS1nb3psaS1hbmFodGFyaQ=="
        payload, b = _imzali(_olay(), gizli="whsec_" + duz)
        self.assertTrue(asrv.imza_dogrula(payload, b, duz))

    def test_bos_gizli_red(self):
        payload, b = _imzali(_olay())
        self.assertFalse(asrv.imza_dogrula(payload, b, ""))

    def test_standart_webhooks_takma_adlari(self):
        payload, b = _imzali(_olay())
        takma = {"webhook-id": b["svix-id"],
                 "webhook-timestamp": b["svix-timestamp"],
                 "webhook-signature": b["svix-signature"]}
        self.assertTrue(asrv.imza_dogrula(payload, takma, GIZLI))


class EpostaCikarTesti(unittest.TestCase):
    def test_duz_email(self):
        self.assertEqual(asrv.eposta_cikar({"data": {"email": " A@B.C "}}),
                         "a@b.c")

    def test_ic_ce_email(self):
        self.assertEqual(
            asrv.eposta_cikar({"data": {"customer": {"email": "x@y.z"}}}),
            "x@y.z")

    def test_checkout_email(self):
        self.assertEqual(
            asrv.eposta_cikar({"data": {"checkout": {"email": "a@b.c"}}}),
            "a@b.c")

    def test_gecersiz_degerler(self):
        for olay in ({"data": {}}, {"data": {"email": "atsiz"}},
                     {"data": "metin"}, {}, {"data": None}):
            self.assertIsNone(asrv.eposta_cikar(olay))


@unittest.skipUnless(URETIM_VAR, "lisans_uret.py yalnızca satıcı makinesinde")
class SiparisIsleTesti(unittest.TestCase):
    def setUp(self):
        self._klasor = tempfile.TemporaryDirectory()
        self.kayit = Path(self._klasor.name) / "kayit.json"

    def tearDown(self):
        self._klasor.cleanup()

    def test_yeni_siparis_anahtar_uretir_ve_kaydeder(self):
        durum, detay = asrv.siparis_isle(_olay(eposta="a@b.c"), self.kayit)
        self.assertEqual(durum, "yeni")
        self.assertTrue(detay["anahtar"].startswith("RN1-"))
        self.assertEqual(detay["eposta"], "a@b.c")
        import lisans
        self.assertTrue(lisans.anahtar_gecerli(detay["anahtar"]))
        self.assertTrue(self.kayit.exists())

    def test_ayni_siparis_ikinci_kez_ayni_anahtari_verir(self):
        _, ilk = asrv.siparis_isle(_olay(), self.kayit)
        durum, ikinci = asrv.siparis_isle(_olay(), self.kayit)
        self.assertEqual(durum, "mevcut")
        self.assertEqual(ilk["anahtar"], ikinci["anahtar"])
        kayitlar = json.loads(self.kayit.read_text(encoding="utf-8"))
        self.assertEqual(len(kayitlar), 1)

    def test_farkli_siparis_farkli_anahtar(self):
        _, a = asrv.siparis_isle(_olay("ord_1"), self.kayit)
        _, b = asrv.siparis_isle(_olay("ord_2"), self.kayit)
        self.assertNotEqual(a["anahtar"], b["anahtar"])

    def test_siparis_disi_olay_atlanir(self):
        durum, detay = asrv.siparis_isle(
            {"type": "subscription.created", "data": {"id": "sub_1"}},
            self.kayit)
        self.assertEqual(durum, "atlandi")
        self.assertFalse(self.kayit.exists())

    def test_id_yoksa_hata(self):
        durum, detay = asrv.siparis_isle({"type": "order.created",
                                          "data": {}}, self.kayit)
        self.assertEqual(durum, "hata")
        self.assertEqual(detay["sebep"], "siparis_id_yok")

    def test_bozuk_kayit_dosyasi_sifirdan_kurulur(self):
        self.kayit.parent.mkdir(parents=True, exist_ok=True)
        self.kayit.write_text("{bozuk", encoding="utf-8")
        durum, _ = asrv.siparis_isle(_olay(), self.kayit)
        self.assertEqual(durum, "yeni")


class AnahtarBulTesti(unittest.TestCase):
    def setUp(self):
        self._klasor = tempfile.TemporaryDirectory()
        self.kayit = Path(self._klasor.name) / "kayit.json"
        asrv.kayit_yaz(self.kayit, {
            "ord_1": {"siparis_id": "ord_1", "eposta": "a@b.c",
                      "anahtar": "RN1-AAAA-1"},
            "ord_2": {"siparis_id": "ord_2", "eposta": "d@e.f",
                      "anahtar": "RN1-BBBB-2"},
        })

    def tearDown(self):
        self._klasor.cleanup()

    def test_buyuk_kucuk_harf_fark_etmez(self):
        sonuc = asrv.anahtar_bul(self.kayit, "A@B.C")
        self.assertEqual(len(sonuc), 1)
        self.assertEqual(sonuc[0]["anahtar"], "RN1-AAAA-1")

    def test_olmayan_eposta(self):
        self.assertEqual(asrv.anahtar_bul(self.kayit, "yok@yok.c"), [])
        self.assertEqual(asrv.anahtar_bul(self.kayit, ""), [])


@unittest.skipUnless(URETIM_VAR, "lisans_uret.py yalnızca satıcı makinesinde")
class HttpUcTesti(unittest.TestCase):
    """Sunucu + webhook + sorgu uçtan uca (127.0.0.1, geçici port)."""

    @classmethod
    def setUpClass(cls):
        cls._klasor = tempfile.TemporaryDirectory()
        cls.kayit = Path(cls._klasor.name) / "kayit.json"
        cls.sunucu = asrv.sunucu_baslat("127.0.0.1", 0, GIZLI, cls.kayit,
                                        "http://127.0.0.1", eposta_acik=False)
        cls.port = cls.sunucu.server_address[1]
        cls._ip = threading.Thread(target=cls.sunucu.serve_forever,
                                   daemon=True)
        cls._ip.start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()
        cls._ip.join(timeout=5)
        cls._klasor.cleanup()

    def _istek(self, yol: str, method: str = "GET", veri: bytes | None = None,
               basliklar: dict | None = None) -> tuple[int, dict]:
        istek = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{yol}", data=veri, method=method,
            headers=basliklar or {})
        try:
            with urllib.request.urlopen(istek, timeout=10) as yanit:
                return yanit.status, json.loads(yanit.read().decode("utf-8"))
        except urllib.error.HTTPError as hata:
            govde = hata.read().decode("utf-8")
            try:
                return hata.code, json.loads(govde)
            except ValueError:
                return hata.code, {"govde": govde}

    def test_saglik(self):
        kod, govde = self._istek("/health")
        self.assertEqual((kod, govde["durum"]), (200, "ok"))

    def test_imzali_webhook_anahtar_uretir_ve_sorgulanir(self):
        payload, b = _imzali(_olay("ord_http_1", "musteri@site.com"))
        kod, govde = self._istek("/webhook", "POST", payload, b)
        self.assertEqual(kod, 202)
        self.assertEqual(govde["durum"], "yeni")

        kod, govde = self._istek("/lisans?eposta=musteri%40site.com")
        self.assertEqual(kod, 200)
        self.assertTrue(govde["anahtarlar"][0]["anahtar"].startswith("RN1-"))

    def test_imzasiz_webhook_403(self):
        payload = json.dumps(_olay("ord_siz")).encode("utf-8")
        kod, _ = self._istek("/webhook", "POST", payload,
                             {"Content-Type": "application/json"})
        self.assertEqual(kod, 403)

    def test_bozuk_json_400(self):
        payload, b = _imzali(_olay(), payload_duzenle=lambda p: p + b"}")
        kod, _ = self._istek("/webhook", "POST", payload, b)
        self.assertEqual(kod, 400)

    def test_olmayan_eposta_404(self):
        kod, govde = self._istek("/lisans?eposta=olmayan%40x.com")
        self.assertEqual(kod, 404)
        self.assertEqual(govde["hata"], "bulunamadi")

    def test_bilinmeyen_yol_404(self):
        kod, _ = self._istek("/yok")
        self.assertEqual(kod, 404)


class KendiniSinamaTesti(unittest.TestCase):
    def test_kontrol_gecer(self):
        self.assertTrue(asrv.kendini_sina(GIZLI))


if __name__ == "__main__":
    unittest.main()
