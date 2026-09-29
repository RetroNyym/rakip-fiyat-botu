# ithalat-radar

`rakip-fiyat-botu` GUI'sinin **🌍 İthalat Radarı** sekmesi için tedarikçi keşif
motoru. Veri kaynağı: [ImportYeti](https://www.importyeti.com) — ABD denizyolu
ithalat (bill of lading) kayıtları.

## Kullanım

```bash
python -m ithalat ara "nike" --sayfa 1 --json data/out/ithalat_gui.json
python -m ithalat firma company/nike --json data/out/ithalat_gui.json
python -m ithalat tedarikci supplier/apl-logistics-vietnam --json data/out/ithalat_gui.json
```

| Komut | Ne yapar |
|---|---|
| `ara <sorgu>` | Firma/marka arar (ImportYeti `/api/search`) |
| `firma company/<x>` | Firmanın tedarikçilerini + ülke dağılımını çeker |
| `tedarikci supplier/<x>` | Tedarikçinin müşterilerini + ülke dağılımını çeker |

Ortak bayraklar: `--sayfa` (arama sayfası), `--json` (sonuç dosyası yolu),
`--surum`.

Çıktı: stdout'a Türkçe özet + `--json` dosyası. Çıkış kodları:
**0** başarı · **2** ağ/yanıt hatası (`AgHatasi`, JSON değil) · **3** beklenmeyen hata.

## JSON şeması (GUI'nin beklediği)

- Arama: `{sorgu, sayfa, toplam, toplam_sayfa, kalan_hak, sonuclar:[{tur, ad, ulke, adres, sefer, son_sefer, url}]}`
- Sayfa: `{tur, slug, ad, adres, url, satirlar:[{ad, slug, ulke, sefer, urunler, url}], ulkeler:[{ulke, sefer}], son_sevkiyats, ozet:{bagli_sayisi, ulke_sayisi, son_sevkiyat}}`

## Notlar

- `ornek/` klasörü örnek sayfa/JSON çıktılarıdır — birim testleri
  (`test_ithalat_radar.py`, repo kökünde) **ağsız** olarak bunlarla koşar.
- Arama API'si dakikalık istek hakkı döndürür (`kalan_hak`); nazik kullanın.
- Resmî `data.importyeti.com` API'si anahtar gerektirir — bu modül site
  içi (`/api/search`) uç noktasını kullanır.
- `ITHALAT_DEBUG=1` ortam değişkeni ham HTML/JSON'u `data/out/debug_*.html`
  altına yazar (ayrıştırıcı geliştirirken kullanışlı).

## Hata ayıklama

- "Tamamlanamadı (kod 2)" + bağlantı/TLS hatası → ağdaki güvenlik duvarı
  importyeti.com'u engelliyor olabilir (VPN deneyin).
- Arama sonuç boşsa isim İngilizce olmalı: *nike*, *IKEA*, *adidas*.
- Sayfa yapısı değişirse `ornek/` altına güncel HTML kaydını ekleyip
  `ithalat/sayfa.py` seçicilerini güncelleyin.
