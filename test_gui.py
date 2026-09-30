# -*- coding: utf-8 -*-
"""gui.py duman testleri.

Ekran (tkinter) yoksa sessizce atlanır — bu yüzden Linux CI'da koşmayabilir.

Çalıştırma:
    python -m unittest discover -v
    pytest -v
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

# Açılış ipucu balonu testlerde açılmasın
os.environ["RIYA_TESTI"] = "1"

import rakip_takip as cekirdek

# gui.py tkinter yokken import edilirse sys.exit(1) yapar → önce deneyelim.
try:
    import tkinter                                              # noqa: F401
    EKRAN_VAR = True
except Exception:                                   # noqa: BLE001
    EKRAN_VAR = False

if EKRAN_VAR:
    import gui


ORNEK_SONUCLAR = [
    {"ad": "A", "url": "http://x/a", "fiyat": 120.0, "para": "TL",
     "onceki": 100.0, "yuzde": 20.0, "durum": "degisti", "mesaj": "▲ +20.0%"},
    {"ad": "B", "url": "http://x/b", "fiyat": 50.0, "para": "TL",
     "onceki": 50.0, "yuzde": 0.0, "durum": "degismedi", "mesaj": "Değişmedi"},
    {"ad": "C", "url": "http://x/c", "fiyat": None, "para": "",
     "onceki": None, "yuzde": None, "durum": "bulunamadi",
     "mesaj": "Fiyat bulunamadı"},
]


@unittest.skipUnless(EKRAN_VAR, "tkinter/ekran yok")
class GuiTesti(unittest.TestCase):
    """Süreç boyunca TEK pencere kullanılır.

    Her testte yeni bir ``tk.Tk()`` açmak Windows'ta yarışa giriyor ve
    seyrek olarak ``Can't find a usable init.tcl`` hatası veriyordu.
    Pencere bir kez açılır, her test öncesi durum sıfırlanır.
    """

    app = None

    @classmethod
    def setUpClass(cls):
        cls.config_yol = cekirdek.VARSAYILAN_CONFIG
        cls.config_yedek = (cls.config_yol.read_bytes()
                            if cls.config_yol.exists() else None)

        cls.db_yedek = (cekirdek.DB_YOL.read_bytes()
                        if cekirdek.DB_YOL.exists() else None)
        cls.db_yaratildi = not cekirdek.DB_YOL.exists()
        cls.db_olustur()

        try:
            cls.app = gui.Uygulama()
        except Exception as hata:                    # noqa: BLE001
            # başsız ortam (CI) — pencere açılamıyorsa testler atlanır
            cls._temizle()
            raise unittest.SkipTest(f"pencere açılamadı: {hata}")
        cls.app.withdraw()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls._temizle()

    @classmethod
    def _temizle(cls):
        """Pencereyi ve yedeklenen config/DB dosyalarını eski haline getir."""
        if cls.app is not None:
            try:
                cls.app.destroy()
            except Exception:                        # noqa: BLE001
                pass
            cls.app = None

        if cls.config_yedek is None:
            cls.config_yol.unlink(missing_ok=True)
        else:
            cls.config_yol.write_bytes(cls.config_yedek)
        if cls.db_yaratildi:
            cekirdek.DB_YOL.unlink(missing_ok=True)
        elif cls.db_yedek is not None:
            cekirdek.DB_YOL.write_bytes(cls.db_yedek)

    @classmethod
    def db_olustur(cls):
        """Geçmiş verisi oluşturur (grafik/rapor en az 2 kayıt ister)."""
        bag = cekirdek.db_ac()
        bag.execute("DELETE FROM fiyatlar")
        bag.commit()
        for i, gun in enumerate(["2026-09-01", "2026-09-08", "2026-09-15"]):
            cekirdek.kaydet(bag, "Test Ürün", "http://x/t",
                            100.0 + i * 10, "TL", "h", gun=gun)
        bag.close()

    def setUp(self):
        """Her test öncesi uygulamayı fabrika ayarına döndür."""
        self.app = self.__class__.app
        self.app.ayar = cekirdek.config_oku(self.config_yol)
        self.app.arama_deg.set("")
        self.app.son_tarama = []
        self.app.liste_doldur()
        self.app.sonuclari_temizle()
        self.app.konsol_temizle()
        self.app.update()

    # ------------------------------------------------------------------
    #  Kurulum / config
    # ------------------------------------------------------------------
    def test_config_yuklendi(self):
        self.assertIn("urunler", self.app.ayar)
        self.assertIn("ayarlar", self.app.ayar)
        self.assertGreaterEqual(len(self.app.ayar["urunler"]), 1)

    def test_config_kaydet(self):
        self.app._config_kaydet()
        disk = cekirdek.config_oku(self.config_yol)
        self.assertEqual(disk, self.app.ayar)

    def test_durum_cubugu(self):
        metin = self.app._sag_durum_metni()
        self.assertIn("ürün", metin)
        self.assertIn("PIL:", metin)
        self.assertIn("Grafik:", metin)

    def test_baslangic_bos_dogrulamasi(self):
        """Açılışta hiçbir şey çökmemeli."""
        self.app.liste_doldur()
        self.app.gecmis_yenile()
        self.app.grafik_ciz()
        self.app.rapor_yenile()
        self.app.sonuclari_temizle()

    # ------------------------------------------------------------------
    #  Ürün listesi + arama
    # ------------------------------------------------------------------
    def test_liste_urun_sayisi(self):
        self.assertEqual(len(self.app.agac.get_children()),
                         len(self.app.ayar["urunler"]))

    def test_arama_eslesme(self):
        ilk = self.app.ayar["urunler"][0]["ad"]
        self.app.arama_deg.set(ilk[:4])
        self.app.liste_doldur()
        self.assertEqual(len(self.app.agac.get_children()), 1)

    def test_arama_eslesmeme(self):
        self.app.arama_deg.set("zzzz-yok-boyle-sey")
        self.app.liste_doldur()
        self.assertEqual(len(self.app.agac.get_children()), 0)

    def test_arama_temizleme(self):
        self.app.arama_deg.set("zzzz")
        self.app.liste_doldur()
        self.app.arama_deg.set("")
        self.app.liste_doldur()
        self.assertEqual(len(self.app.agac.get_children()),
                         len(self.app.ayar["urunler"]))

    def test_arama_url_uzerinden(self):
        url = self.app.ayar["urunler"][0].get("url", "")
        parca = url.split("//")[-1][:6]
        self.app.arama_deg.set(parca)
        self.app.liste_doldur()
        self.assertGreaterEqual(len(self.app.agac.get_children()), 1)

    def test_urun_bul(self):
        ad = self.app.ayar["urunler"][0]["ad"]
        bulunan = self.app.urun_bul(ad)
        self.assertIsNotNone(bulunan)
        self.assertEqual(bulunan["ad"], ad)
        self.assertIsNone(self.app.urun_bul("böyle bir ürün yok"))

    def test_urun_ekleme_ve_silme(self):
        yeni = {"ad": "Geçici Ürün", "url": "http://x/gecici",
                "selector": ".p", "not": ""}
        self.app.ayar.setdefault("urunler", []).append(yeni)
        self.app.liste_doldur()
        self.assertEqual(len(self.app.agac.get_children()),
                         len(self.app.ayar["urunler"]))

        self.app.ayar["urunler"] = [
            u for u in self.app.ayar["urunler"] if u["ad"] != "Geçici Ürün"]
        self.app.liste_doldur()
        self.assertFalse(any(
            self.app.agac.item(i, "values")[0] == "Geçici Ürün"
            for i in self.app.agac.get_children()))

    # ------------------------------------------------------------------
    #  Seçim
    # ------------------------------------------------------------------
    def test_secim(self):
        cocuk = self.app.agac.get_children()
        self.assertTrue(cocuk)
        self.app.agac.selection_set(cocuk[0])
        beklenen = self.app.agac.item(cocuk[0], "values")[0]
        self.assertEqual(self.app.secili_urun(), beklenen)
        self.assertEqual(self.app.secili_urunler(), [beklenen])

    def test_secim_yok(self):
        self.app.agac.selection_remove(*self.app.agac.get_children())
        self.assertIsNone(self.app.secili_urun())

    # ------------------------------------------------------------------
    #  Geçmiş / grafik / rapor
    # ------------------------------------------------------------------
    def test_gecmis_doluyor(self):
        self.app.ayar["urunler"] = [{"ad": "Test Ürün",
                                     "url": "http://x/t",
                                     "selector": ".p"}]
        self.app.liste_doldur()
        ilk = self.app.agac.get_children()[0]
        self.app.agac.selection_set(ilk)
        self.app.gecmis_yenile()
        satirlar = self.app.gecmis_agac.get_children()
        self.assertEqual(len(satirlar), 3)
        degerler = self.app.gecmis_agac.item(satirlar[0], "values")
        self.assertEqual(degerler[0], "2026-09-01")
        self.assertIn("TL", degerler[1])

    def test_gecmis_secim_yok(self):
        self.app.gecmis_yenile()
        self.assertEqual(self.app.gecmis_agac.get_children(), ())

    def test_grafik_cizimi(self):
        self.app.ayar["urunler"] = [{"ad": "Test Ürün",
                                     "url": "http://x/t",
                                     "selector": ".p"}]
        self.app.liste_doldur()
        self.app.agac.selection_set(self.app.agac.get_children()[0])
        self.app.grafik_ciz()          # hata atmamalı
        if gui.MPL_VAR:
            self.assertIsNotNone(self.app.grafik_canvas)

    def test_grafik_yetersiz_kayit(self):
        self.app.ayar["urunler"] = [{"ad": "Verisi Olmayan",
                                     "url": "http://x/y", "selector": ""}]
        self.app.liste_doldur()
        self.app.agac.selection_set(self.app.agac.get_children()[0])
        self.app.grafik_ciz()          # 0 kayıtta da çökmemeli

    def test_rapor_yenileme(self):
        self.app.rapor_yenile()
        self.assertGreaterEqual(len(self.app.rapor_agac.get_children()), 1)
        self.assertTrue(self.app.rapor_ozet.get())

    # ------------------------------------------------------------------
    #  Tarama sonuçları
    # ------------------------------------------------------------------
    def test_sonuclari_doldur(self):
        self.app.sonuclari_doldur(ORNEK_SONUCLAR)
        cocuk = self.app.sonuc_agac.get_children()
        self.assertEqual(len(cocuk), 3)
        ilk = self.app.sonuc_agac.item(cocuk[0], "values")
        self.assertEqual(ilk[0], "A")
        self.assertEqual(ilk[2], "120,00 TL")
        self.assertEqual(ilk[3], "+20.0%")
        self.assertIn("Değişti", ilk[4])

    def test_sonuc_etiketleri(self):
        self.app.sonuclari_doldur(ORNEK_SONUCLAR)
        cocuk = self.app.sonuc_agac.get_children()
        self.assertEqual(self.app.sonuc_agac.item(cocuk[0], "tags"),
                         ("degisti",))
        # 'degismedi' için etiket verilmez → Tk boş string döndürür
        self.assertFalse(self.app.sonuc_agac.item(cocuk[1], "tags"))
        self.assertEqual(self.app.sonuc_agac.item(cocuk[2], "tags"),
                         ("sorun",))

    def test_sonuclari_temizle(self):
        self.app.sonuclari_doldur(ORNEK_SONUCLAR)
        self.app.sonuclari_temizle()
        self.assertEqual(self.app.sonuc_agac.get_children(), ())

    def test_bulunamadi_sonucu(self):
        """durum_metni sözlüğünde olmayan bir durum çökmemeli."""
        self.app.sonuclari_doldur([{"ad": "D", "durum": "garip", "mesaj": ""}])
        self.assertEqual(len(self.app.sonuc_agac.get_children()), 1)

    def test_tarama_durdur_kapaliyken(self):
        self.assertFalse(self.app.tarama_suriyor)
        self.app.tarama_durdur()      # hata atmamalı

    # ------------------------------------------------------------------
    #  Konsol
    # ------------------------------------------------------------------
    def test_konsol_yazimi(self):
        self.app.konsol_yaz("deneme mesajı 123")
        self.app._kuyruk_isle()
        icerik = self.app.konsol.get("1.0", "end")
        self.assertIn("deneme mesajı 123", icerik)

    def test_konsol_etiketleme(self):
        self.app.konsol_yaz("[!] hata oldu")
        self.app._kuyruk_isle()
        etiketler = self.app.konsol.tag_ranges("hata")
        self.assertTrue(etiketler)

    def test_konsol_temizleme(self):
        self.app.konsol_yaz("bir şey")
        self.app._kuyruk_isle()
        self.app.konsol_temizle()
        self.assertEqual(self.app.konsol.get("1.0", "end").strip(), "")

    def test_konsol_kopyalama(self):
        self.app.konsol_yaz("kopyalanacak")
        self.app._kuyruk_isle()
        self.app._konsol_kopyala()
        self.assertEqual(self.app.clipboard_get(), "kopyalanacak")

    # ------------------------------------------------------------------
    #  CSV
    # ------------------------------------------------------------------
    def test_csv_urunler(self):
        baslik, satirlar = self.app.csv_satirlari("urunler")
        self.assertEqual(baslik[0], "Ürün")
        self.assertEqual(len(satirlar), len(self.app.ayar["urunler"]))

    def test_csv_sonuclar(self):
        self.app.son_tarama = ORNEK_SONUCLAR
        baslik, satirlar = self.app.csv_satirlari("sonuclar")
        self.assertEqual(len(satirlar), 3)
        self.assertEqual(satirlar[0][0], "A")
        self.assertEqual(satirlar[0][3], "20.0")
        self.assertEqual(satirlar[2][3], "")       # yuzde yoksa boş

    def test_csv_rapor(self):
        baslik, satirlar = self.app.csv_satirlari("rapor")
        self.assertEqual(baslik[0], "Ürün")
        self.assertIsInstance(satirlar, list)

    def test_csv_gecmis_secim_yok(self):
        self.assertIsNone(self.app.csv_satirlari("gecmis"))

    def test_csv_gecmis_secimli(self):
        self.app.ayar["urunler"] = [{"ad": "Test Ürün",
                                     "url": "http://x/t",
                                     "selector": ".p"}]
        self.app.liste_doldur()
        self.app.agac.selection_set(self.app.agac.get_children()[0])
        baslik, satirlar = self.app.csv_satirlari("gecmis")
        self.assertEqual(baslik, ["Tarih", "Fiyat", "Para"])
        self.assertEqual(len(satirlar), 3)

    def test_csv_bilinmeyen_tur(self):
        self.assertIsNone(self.app.csv_satirlari("yok-boyle"))

    def test_csv_dosyaya_yazma(self):
        """UTF-8 BOM ile yazılmalı — Excel Türkçe karakteri bozmasın."""
        import csv
        import tempfile

        self.app.son_tarama = ORNEK_SONUCLAR
        baslik, satirlar = self.app.csv_satirlari("sonuclar")
        with tempfile.TemporaryDirectory() as k:
            hedef = Path(k) / "c.csv"
            with open(hedef, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(baslik)
                w.writerows(satirlar)
            ham = hedef.read_bytes()
            self.assertTrue(ham.startswith(b"\xef\xbb\xbf"),
                            "BOM yok — Excel bozulur")
            metin = hedef.read_text(encoding="utf-8-sig")
            self.assertIn("Önceki", metin)

    # ------------------------------------------------------------------
    #  Ayarlar
    # ------------------------------------------------------------------
    def test_ayar_varsayilanlari(self):
        ayar = self.app.ayar["ayarlar"]
        self.assertIn("bekleme_saniye", ayar)
        self.assertIn("esik_yuzde", ayar)
        self.assertIn("telegram_token", ayar)

    def test_ayar_degisikligi_kaydedilir(self):
        onceki = self.app.ayar["ayarlar"].get("esik_yuzde")
        self.addCleanup(self._esik_geri_koy, onceki)

        self.app.ayar["ayarlar"]["esik_yuzde"] = 7
        self.app._config_kaydet()
        self.assertEqual(
            cekirdek.config_oku(self.config_yol)["ayarlar"]["esik_yuzde"], 7)

    def _esik_geri_koy(self, deger):
        self.app.ayar["ayarlar"]["esik_yuzde"] = deger
        self.app._config_kaydet()

    # ------------------------------------------------------------------
    #  Ana kuyruk (_ana_kuyruk) sözleşmesi
    # ------------------------------------------------------------------
    def test_ana_kuyruk_islevi_calisir(self):
        """`_ana_kuyruk` üzerindeki sözleşme: `islev(veri)` çağrılır."""
        isaret = []
        self.app._ana_kuyruk.put((lambda _v: isaret.append(_v), "veri-degeri"))
        self.app._kuyruk_isle()
        self.assertEqual(isaret, ["veri-degeri"])

    def test_kotu_islev_donguyu_oldurmez(self):
        """Bozuk tek bir işlev arka plan döngüsünü kalıcı olarak durdurmamalı.

        Eskiden `islev(veri)` try/except dışında idi; istisna `after(...)`
        çağrısına da sıçrar, konsol/grafik/rapor güncellemeleri sonsuza dek
        dururdu (GUI ses vermeden donardı).
        """
        def patlak(_v=None):
            raise RuntimeError("kasitli test hatasi")

        self.app._ana_kuyruk.put((patlak, None))
        self.app._kuyruk_isle()          # istisna dışarı sıçramamalı

        # döngü hâlâ çalışır durumda olmalı
        isaret = []
        self.app._ana_kuyruk.put((lambda _v=None: isaret.append(1), None))
        self.app._kuyruk_isle()          # hata konsola düşer, akış sürer

        self.assertEqual(isaret, [1], "döngü durmuş")
        icerik = self.app.konsol.get("1.0", "end")
        self.assertIn("kasitli test hatasi", icerik)
        self.assertIn("arayüz işlevi çalıştırılamadı", icerik)

    def test_seci_bul_sonuclari_listelenir(self):
        """Seçici Bul penceresi sonuçları ana döngü üzerinden listelemeli.

        Regresyon: `SeciciPenceresi._baslat` sıfır argümanlı bir lambda
        kuyruğa atıyordu; `islev(veri)` TypeError fırlatıyor ve aday listesi
        hiç dolmuyordu.
        """
        import time

        from test_rakip_takip import YerelSunucu

        sunucu = YerelSunucu({
            "/urun": ("text/html; charset=utf-8",
                      "<html><body>"
                      "<span class='price'>4.900,50 TL</span>"
                      "</body></html>"),
        })
        p = None
        try:
            yazici = gui.KuyrukYazici(self.app.kuyruk)
            p = gui.SeciciPenceresi(
                self.app, sunucu.url("/urun"), yazici,
                lambda islev: self.app._ana_kuyruk.put((islev, None)))

            p._baslat()                       # arka thread'i başlat

            son = time.time() + 15
            while time.time() < son and not p.agac.get_children():
                self.app.update()
                self.app._kuyruk_isle()
                time.sleep(0.05)

            cocuk = p.agac.get_children()
            self.assertTrue(cocuk, "aday listesi hiç dolmadı")
            degerler = p.agac.item(cocuk[0], "values")
            self.assertIn("span.price", degerler)
            self.assertIn("4.900,50 TL", degerler)
            self.assertFalse(p.tara_btn.instate(["disabled"]),
                             "düğme tekrar aktifleşmedi")
        finally:
            if p is not None:
                try:
                    p.destroy()
                except Exception:            # noqa: BLE001
                    pass
            sunucu.kapat()


if __name__ == "__main__":
    unittest.main(verbosity=2)
