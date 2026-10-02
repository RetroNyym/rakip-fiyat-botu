# Rakip Fiyat Takip Botu / Competitor Price Tracker

[![testler](https://github.com/RetroNyym/rakip-fiyat-botu/actions/workflows/test.yml/badge.svg)](https://github.com/RetroNyym/rakip-fiyat-botu/actions/workflows/test.yml)
[![lisans: MIT](https://img.shields.io/badge/lisans-MIT-blue.svg)](LICENSE)

> **Türkçe:** Rakip ürünlerin fiyatlarını otomatik takip eder, geçmişi tutar,
> fiyat değişince Telegram'dan uyarır. Masaüstü arayüzü + komut satırı.
>
> **English:** Tracks competitor product prices, keeps a price history and
> alerts you on Telegram when a price changes. Ships with a desktop GUI and
> a CLI.

---

## 🎯 Ne yapar / What it does

| | |
|---|---|
| 🔍 **Tarama** | `config.json`'daki rakip ürün sayfalarını gezer, fiyatı çeker |
| 🔍 **Ürün Arama** | Ürün adını Trendyol · Hepsiburada · N11 · Amazon'da toplu arar, fiyatları karşılaştırır |
| 📈 **Geçmiş** | Her günün fiyatını SQLite'a yazar → geçmiş + grafik oluşur (dönem: 7 gün – Tümü) |
| 🗂 **Sonuçlar** | Kolon başlığıyla sıralama, "sadece değişenler" filtresi |
| 🔔 **Uyarı** | Fiyat değişince Telegram'a mesaj atar — mesajda ürüne giden 🔗 butonu |
| 🧭 **Rakip Radar** | Pazaryerlerinde satıcı listesi: pazar payı, yorum, tahmini ciro + lider tablosu |
| 🌍 **İthalat Radarı** | Rakibinin tedarikçilerini ABD ithalat kayıtlarından (ImportYeti) keşfeder |
| 🧭 **Seçici bul** | Fiyatın CSS seçicisini sayfadan otomatik keşfeder |
| 🖼 **Görsel** | Rakip ürününün görselini arayüzde gösterir |
| 📊 **Rapor** | En düşük / en yüksek / toplam değişim / dalgalanma aralığı |
| 📄 **CSV** | Liste, sonuç, rapor ve geçmişi Excel uyumlu CSV olarak aktarır |
| 🔑 **Lisans** | Deneme modu: 5 sorgu hakkı (Ürün Arama + Tarama + İthalat); sınırda lisans anahtarıyla kilit ekranı. Asimetrik (Ed25519) anahtar — kaynak kodu elde geçse de **yeni anahtar üretemez** |
| ⏰ **Otomasyon** | Görev Zamanlayıcı'ya tek tıkla günlük tarama kurar |

**Fiyat ayrıştırma** Türkçe ve uluslararası formatları ayırt eder:

```
'4.900,50 TL'              → 4900.50 TL
'200x300 halı 1.750,00 TL' → 1750.00 TL   (200 değil)
'Ürün Kodu 5544 - TL 89,90'→ 89.90 TL     (5544 değil)
'$19.99'                   → 19.99 USD
'1.234.567,89 TL'          → 1234567.89 TL
```

---

## 🖥 Ekran / Screenshots

| Arayüz | Fiyat geçmişi + grafik |
|---|---|
| ![GUI](docs/gui.png) | ![Geçmiş](docs/gecmis.png) |

**🔍 Ürün Arama** — 9 pazaryerinde fiyat karşılaştırması
(Trendyol · Hepsiburada · N11 · Amazon · Pazarama · Etsy · eBay · AliExpress · Çiçeksepeti):

![Ürün Arama](docs/urun-arama.png)

**🌍 İthalat Radarı** — tedarikçi/müşteri keşfi (ABD ithalat kayıtları):

![İthalat Radarı](docs/ithalat.png)

---

## 🚀 Kurulum / Installation

```bash
git clone https://github.com/RetroNyym/rakip-fiyat-botu.git
cd rakip-fiyat-botu
pip install -r requirements.txt
```

**Temel (zorunlu):** `requests`, `beautifulsoup4`, `cryptography`
**Opsiyonel ama önerilir:** `Pillow` (görsel önizleme), `matplotlib` (grafik)

```bash
pip install Pillow matplotlib
```

Python **3.10+** gerekir.

### Windows'ta Python gerekmeden (.exe)

Müşteriye Python kurulumu yaptırmak istemiyorsanız hazır `.exe` dağıtımı
kullanın (`dist/rakip-fiyat-botu-<sürüm>-exe/`):

- `RakipFiyatBot.exe` — arayüz (konsolsuz)
- `rakip-takip.exe` — komut satırı (konsollu)

Taşınabilir klasörün tamamı tek yerden çalışır: `config.json`, `data/`,
`fiyatlar.db` **exe'nin yanında** oluşur. Hak sayacının ikinci kopyası ayrıca
`%APPDATA%\RakipFiyatBot\limit.json`'dadır (ana dosya silinse kurtarır).

> ⚠️ Klasörü `Program Files` altına **koymayın**: orası yazmaya kapalıdır ve
> config/db dosyaları exe'nin yanına yazılamaz. `C:\RakipFiyatBot` gibi
> yazılabilir bir dizin kullanın.

---

## ▶ Çalıştırma / Usage

### Arayüz / GUI

```bash
python gui.py
```

Veya Windows'ta `baslat.bat` dosyasına çift tıkla.

### Komut satırı / CLI

```bash
python rakip_takip.py                  # tarama yap (1 deneme hakkı)
python rakip_takip.py --rapor          # fiyat geçmişini göster
python rakip_takip.py --rapor --gun 90 # son 90 gün
python rakip_takip.py --inspect URL    # CSS seçici bul
python rakip_takip.py --test           # Telegram bağlantısını dene
python rakip_takip.py --lisans RN1-…   # lisans anahtarını gir ve kaydet
python rakip_takip.py --config baska.json
```

**Çıkış kodları:** `0` başarılı · `1` config / geçersiz anahtar ·
`4` deneme hakkı doldu (lisans gerekli) · `5` Polar online doğrulama
başarısız (iptal / süre / cihaz limiti / ağ).

> Deneme hakkı hem GUI'de hem CLI'da **ortaktır**: her tarama / ürün arama /
> ithalat sorgusu 1 hak harcar. Hak sayacı `data/limit.json` **ve**
> `%APPDATA%\RakipFiyatBot\limit.json` içinde tutulur — dosyalardan biri
> silinse diğeri sayacı taşır.

### Zamanlanmış günlük tarama / Scheduled daily run

```bash
# Araçlar → Görev Zamanlayıcıya Ekle (Windows)
# veya elle: tarama.bat dosyasını Görev Zamanlayıcı'ya ekle
```

---

## ⚙️ Yapılandırma / Configuration

`config.json`:

```json
{
  "ayarlar": {
    "bekleme_saniye": 3,
    "esik_yuzde": 0,
    "telegram_token": "",
    "telegram_chat_id": ""
  },
  "urunler": [
    {
      "ad": "Rakip A - 200x300 yün halı",
      "url": "https://rakip.com/urun/yun-hali-200x300",
      "selector": "span.price",
      "not": "opsiyonel not"
    }
  ],
  "lisans": ""
}
```

| Alan | Açıklama |
|---|---|
| `ad` | Ürüne verdiğin ad (raporda ve uyarıda görünür) |
| `url` | Rakip ürün sayfası |
| `selector` | Fiyatın bulunduğu CSS seçicisi. **Boş bırakırsa** bot sayfayı tarar ve para birimli ilk adayı seçer |
| `bekleme_saniye` | İstekler arası bekleme (3 önerilir) |
| `esik_yuzde` | `0` = her değişimde uyar. `5` = %5 üstü değişimlerde uyar |
| `telegram_token` | @BotFather'dan alınan bot token'ı |
| `telegram_chat_id` | @userinfobot'a yazarak aldığın chat ID |
| `lisans` | Lisans anahtarı (`RN1-…`). Geçerliyse deneme hakkı sınırı kalkar; **Araçlar → Lisans…** ile (GUI) veya `python rakip_takip.py --lisans RN1-…` (CLI) ile girilir |

> CSS seçicisini bilmiyorsan arayüzde `🔍 Seçici Bul` butonu sayfayı tarayıp
> aday listesi çıkarır; çift tıklayınca ürüne uygulanır.

---

## 📁 Dosya yapısı / Project structure

```
rakip-fiyat-botu/
├── gui.py            # Masaüstü arayüz (Tkinter)
├── rakip_takip.py    # Çekirdek: tarama, ayrıştırma, DB, Telegram, rapor
├── lisans.py         # 🔑 Deneme hakkı (5 sorgu) + Ed25519 anahtar DOĞRULAMA
├── lisans_uret.py    # 🔑 Satıcı: anahtar ÜRETİR — dağıtım paketine girmez
├── paketle.py        # 📦 Satıcı: dağıtılacak paketi üretir + denetler
├── config.json       # Ayarlar + rakip ürün listesi (git'e girmez)
├── config.ornek.json # Şablon — ilk açılışta config.json buna kopyalanır
├── requirements.txt  # Çalışma bağımlılıkları
├── requirements.gelistirme.txt  # Test/CI bağımlılıkları
├── test_rakip_takip.py   # Çekirdek testleri (61 durum)
├── test_gui.py           # Arayüz duman + regresyon testleri (45 durum)
├── test_urun_arama.py    # Ürün Arama modülü + sekmesi testleri (30 durum)
├── test_ithalat_radar.py # İthalat Radarı ayrıştırma testleri (18 durum)
├── test_lisans.py        # Lisans + deneme hakkı + CLI kilidi (41 durum)
├── baslat.bat        # Arayüzü başlat (çift tık)
├── tarama.bat        # Zamanlanmış CLI taraması
├── pazaryeri-radar/  # 🏆 Rakip Radar modülü (satıcı toplama + rapor)
├── ithalat-radar/    # 🌍 İthalat Radarı modülü (ImportYeti istemcisi)
├── .github/workflows/test.yml  # Her push'ta otomatik test
├── KULLANIM.md       # Türkçe kullanım kılavuzu
├── REHBER.md         # Buton buton arayüz rehberi (docs/rehber/ görselleriyle)
├── docs/             # Ekran görüntüleri
└── fiyatlar.db       # SQLite fiyat geçmişi (oluşturulur, git'e girmez)
```

---

## 🧪 Testler / Tests

Testler **ağ erişimi gerektirmez** — yerel (127.0.0.1) bir HTTP sunucusu
kurar, fiyat sayfasını, `robots.txt`'i ve görselleri ondan servis eder.
Gerçek `requests`, `BeautifulSoup`, SQLite ve Tkinter yığını uçtan uca
çalışır.

```bash
# stdlib ile (ekstra kurulum gerektirmez)
python -m unittest discover -v

# pytest ile
pip install -r requirements.gelistirme.txt
pytest -q
```

Ne kapsanıyor:

| Alan | Örnek durumlar |
|---|---|
| Fiyat ayrıştırma | `4.900,50 TL`, `$19.99`, `£45.00`, `200x300 halı 1.750,00 TL` |
| Sayı biçimi | `1.900` (binlik) ↔ `19.99` (ondalık), `1.234.567,89` |
| Config | UTF-8 BOM, bozuk JSON, şablondan otomatik kopyalama |
| Veritabanı | `UNIQUE(ad, zaman)` günde tek kayıt, sıralı geçmiş |
| Tarama (uçtan uca) | ilk kayıt / değişti / değişmedi / fiyat yok / robots.txt |
| Telegram | token yokken **ağ çağrısı yapmadan** `False` |
| Arayüz | liste + canlı arama, seçim, geçmiş, grafik, rapor, CSV, konsol |
| Ürün Arama | 9 site HTML örnekleriyle ayrıştırma + GUI sekmesi (ağsız) |
| İthalat Radarı | HTML/JSON ayrıştırma örnek dosyalarla **ağsız** test edilir |
| Lisans | Ed25519 imza doğrulama, 5 sorgu sınırı, aynalı sayaç, tahrif → kilit, GUI/CLI koruması |
| CLI | `--help`, hata kodları, eksik config mesajı, `--lisans` aktivasyonu |

CI (GitHub Actions) her push'ta **2 işletim sistemi × 3 Python sürümü**
üzerinde hem `unittest` hem `pytest` ile koşar. Başsız ortamlarda arayüz
testleri kendiliğinden atlanır.

---

## 🗄 Veri / Data

- `fiyatlar.db` — tüm fiyat geçmişi (SQLite). Aynı ürün için günde tek kayıt.
- `log.txt` — zamanlanmış tarama kayıtları.
- `config.json` — senin ayarların.

Bu dosyalar git'e **girmez** (`.gitignore`), böylece kişisel verilerin
ve Telegram token'ın yayınlanmaz.

---

## 🛠 Teknik notlar / Technical notes

- **robots.txt** kontrol edilir; izin verilmeyen sayfalar atlanır.
- **Nazik istek:** varsayılan olarak istekler arasında 3 sn bekleme.
- **Kodlama:** site charset vermezse `apparent_encoding` kullanılır (Türkçe
  karakter bozulması önlenir).
- **BOM:** Windows'un yazdığı UTF-8 BOM `utf-8-sig` ile yok sayılır.
- **Yeniden deneme:** ağ hatasında 3 deneme, artan bekleme ile.
- **Eşzamanlılık:** tarama arka thread'de çalışır; arayüz kilitlenmez,
  `■ Durdur` ile anında iptal edilir.
- **Config taşınabilir:** UTF-8, girintili JSON. Farklı dosyalarla
  (`--config`) çoklu rakip listesi tutabilirsin.

---

## 📖 Dokümantasyon / Docs

Türkçe ayrıntılı kılavuz: **[KULLANIM.md](KULLANIM.md)**

- Arayüz rehberi ve klavye kısayolları
- Adım adım başlangıç
- Telegram kurulumu
- Görev Zamanlayıcı kurulumu
- Sık karşılaşılan sorunlar
- Etik ve hukuki notlar

---

## ⚖️ Etik / Ethics

- **robots.txt**'e uy. İzin verilmeyen sayfayı tarama (bot bunu otomatik yapar).
- **Günde 1-2 kez** yeterli. Saniyede istek atma.
- Çektiğin veriyi **kendi kararın için** kullan; rakibin içeriğini kopyalama.
- Fiyat verisi **kamuya açık** bilgidir; sorumluluk kullanıcıya aittir.

---

## 🔐 Satıcı notları / Seller notes

Bu bölüm ürünün **satışını yürüten** kişi içindir; müşterilere dağıtılırken
`lisans_uret.py`, `paketle.py` ve `test_*.py` hariç tutulur.

### Lisans anahtarı üretimi

```powershell
# 5 anahtar üretir, her birini ayrıca doğrular
python lisans_uret.py 5

# Eldeki bir anahtarı doğrula
python lisans_uret.py --dogrula RN1-…
```

- Anahtar biçimi: `RN1-<8 hex gövde>-<103 karakter base32 Ed25519 imzası>`
- İmza **asimetriktir**: `lisans_uret.py` içindeki özel anahtarla üretilir,
  dağıtılan `lisans.py` yalnızca **genel anahtar** ile doğrular — tersinden
  anahtar üretilemez.
- ⚠️ `lisans_uret.py` **git'e girmez** (`.gitignore`'da) ve paketlere
  konmaz. Repo public olduğu için dosya takipten çıkarılmıştır; unutursanız
  `paketle.py` denetimi hatayı verir.

### Deneme hakkını sıfırlama

Müşterinin deneme hakkı bittiyse tek kullanımlık jeton üretip destek
kanalından gönderirsiniz:

```powershell
# satıcı makinesinde (özel anahtar sizde):
python lisans_uret.py --sifirla-jetonu
#   → SIFIRLA-<16 hex nonce>-<103 karakter imza>

# müşteri makinesinde (veya .exe ile aynı):
python rakip_takip.py --sifirla SIFIRLA-…
#   ✔ Deneme hakkı sayacı sıfırlandı — kalan 5 hak.
```

Jeton Ed25519 ile imzalanır; özel anahtar dağıtılan pakette bulunmadığı için
**müşteri kendi sayacını sıfırlayamaz** (`lisans.hak_sifirla()` jetonsuz
`False` döner). Geçersiz jetonda CLI çıkış `1` verir ve sayaç değişmez.

### Polar anahtarı ile cihaz aktivasyonu

Polar'ın `/v1/customer-portal/license-keys/*` uçları **auth'suz** üretilmiştir
("saf bir masaüstü uygulamasında güvenle kullanılabilir") — yani istemcide
saklanacak bir API sırrı yok ve **kendi doğrulama sunucunuzu kurmanız gerekmez.**
Cihaz limiti, iptal ve süre kontrolü Polar'ın kendisinde yaşar.

**Kurulum (Polar Dashboard):**

1. **Benefits → License key** benefit'i oluşturun: anahtar ön eki `RN1_`,
   **activation limit** = 3 (ör. aynı anda en fazla 3 cihaz), isteğe bağlı süre.
2. **Settings → Organization** sayfasındaki UUID'yi kopyalayın.
3. Uygulamada tanımlayın (üçünden biri): `config.json → ayarlar.polar_org_id`
   · `POLAR_ORG_ID` ortam değişkeni · `polar_lisans.py` içindeki `ORG_ID`.
   `.exe` derlemeden **önce** doldurun; boşsa Polar anahtarı kabul edilmez
   (`paketle.py --exe` bu durumda uyarır).

**İstemci akışı (`polar_lisans.py`):**

| Adım | Ne olur |
|---|---|
| `--lisans <Polar anahtarı>` | `activate` (cihaz etiketi `CIHAZ-…`) → `validate` → kaydet |
| Her çalışma öncesi | Önbellek **7 gün** tazeyse ağ çağrısı yapılmaz |
| `validate` → 404/400 | İptal, süre dolu veya aktivasyon uyuşmuyor → **çıkış 5**, GUI'de işlemler kilitli |
| Ağ yok | Son başarılı doğrulamanın üzerinden **30 gün** geçmemişse çalışmaya devam |
| `activate` → 403 | Cihaz limiti dolu → çıkış 5 (Pano'dan başka bir aktivasyonu kaldırın) |

**İptal:** Polar Dashboard → lisansı `revoked` yapın; müşteri de kendi
portalinden aktivasyonunu sıfırlayabilir (yeni cihaza taşınma).

**İki kanal — hangisi ne işe yarar:**

| Kanal | Anahtar | Doğrulama | Cihaz limiti | İptal |
|---|---|---|---|---|
| RN1 (yerel) | `RN1-…-<imza>` | Ed25519, çevrimdışı | yok | yok |
| Polar | Polar üretir | online + 30 gün çevrimdışı lütuf | **var** | panelden |

⚠️ Kanalları karıştırmayın: `anahtar_servisi.py` webhook'u RN1 anahtarı üretir.
Polar benefit'ini etkinleştirdiyseniz webhook'u kapatın — aksi hâlde müşteriye
iki farklı anahtar gider.

### Dağıtım paketi

```powershell
python paketle.py --zip
```

`dist/rakip-fiyat-botu-<sürüm>/` klasörü ve `.zip` arşivi üretir.
Denetim şunları kontrol eder: gizli değer sızıntısı (anahtar/token),
`lisans_uret.py`'nin git takibinde olmaması, gerekli dosyaların paket
içinde bulunması, hariç tutulanların (`config.json`, `fiyatlar.db`,
`test_*.py`, `.git/`) dışarıda kalması.

**Windows `.exe` paketi (Python gerekmez):**

```powershell
pip install -r requirements.txt -r requirements.gelistirme.txt  # pyinstaller dahil
python paketle.py --exe --zip
```

`dist/rakip-fiyat-botu-<sürüm>-exe/` klasörü üretilir: `RakipFiyatBot.exe`
(arayüz), `rakip-takip.exe` (komut satırı) + `config.ornek.json`,
`KULLANIM.md`, `README.md`, `LICENSE`, `baslat.bat`.

Her derlemeden sonra paket **kendi kendini sınar** ve hata varsa çıkış `1`
ile biter (paket SATILMAZ):

- iki `.exe` de var mı, boyut makul mü (< 5 MB ise şüpheli),
- `lisans_uret.py` sızmış mı,
- duman testleri: `rakip-takip.exe --help` ve
  `RakipFiyatBot.exe --kendini-sina` (dondurulmuş pakette bs4/PIL/matplotlib
  gibi gizli import eksikse arayüz açılmadan burada düşer).

`--exe-hizli` duman testlerini atlar (yalnızca geliştirirken).

### Otomatik anahtar teslimi (Polar.sh)

Anahtarın elle yazılmaması için `anahtar_servisi.py` Polar webhook'unu alır,
**Standard Webhooks / Svix** imzasını doğrular, `lisans_uret.py` ile anahtar
üretip `data/lisans_kayitlari.json`'a yazar.

```powershell
set POLAR_WEBHOOK_SECRET=whsec_...
python anahtar_servisi.py --kontrol     # önce kendi kendini sınaire
python anahtar_servisi.py --port 8080   # dinlemeye başla
```

| Uç | Ne yapar |
|---|---|
| `POST /webhook` | İmza doğrula → anahtar üret (**202**); imzasız → **403** |
| `GET /lisans?eposta=…` | Sipariş e-postasıyla anahtar sorgula |
| `GET /health` | Sağlık kontrolü |

- Aynı sipariş ikinci kez gelirse **aynı anahtar** döner (idempotent),
  farklı sipariş farklı anahtar alır.
- SMTP tanımlıysa (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`,
  `MAIL_FROM`) anahtar müşteriye e-posta ile gider; tanımlı değilse
  indirme/destek sayfanıza `GET /lisans?eposta=…` linki koymanız yeterli.
- Polar tarafı: **Dashboard → Webhooks →** `https://<sunucu>/webhook`,
  olay `order.created`, format **Raw**. Sunucu HTTPS arkasında olmalı
  (Cloudflare Tunnel, ngrok veya nginx ters vekil).

---

## 📄 Lisans / License

[MIT](LICENSE)
