# Rakip Fiyat Takip Botu

Rakip halı satıcılarının (veya herhangi bir pazaryeri satıcısının) ürün fiyatlarını
otomatik çeker, geçmişi tutar ve **fiyat değişince Telegram'dan haber verir.**

---

## 1. Kurulum

```powershell
pip install -r requirements.txt
```

Python 3.10+ gerekir.

Görsel önizleme ve fiyat grafiği için (önerilir):

```powershell
pip install Pillow matplotlib
```

### Arayüzle mi, komut satırıyla mı?

| | Arayüz (`gui.py`) | Komut satırı (`rakip_takip.py`) |
|---|---|---|
| Kim için | Günlük kullanım, ilk kez kullanan | Otomasyon, zamanlayıcı, sunucu |
| Ürün ekle/sil | ✅ butonlarla | `config.json` elle düzenlenir |
| Fiyat seçicisini bul | ✅ "Seçici Bul" penceresi | `--inspect URL` |
| Arama/filtre | ✅ sol üstteki kutu | yok |
| Grafik + görsel | ✅ sekmelerde | yok |
| CSV dışa aktarma | ✅ Dosya menüsü | yok |
| Zamanlanmış otomasyon | ✅ Araçlar → Görev Zamanlayıcı | ✅ `baslat.bat` |

```powershell
# Arayüzü başlat
python gui.py

# Veya çift tıkla
baslat.bat
```

### Lisans ve deneme hakkı

Programı **5 sorgu hakkı** ile ücretsiz denersiniz: tarama, ürün arama ve
ithalat radarı her biri **1 hak** harcar. Hem arayüzde hem komut satırında
ortaktır.

Haklar iki ayrı yerde saklanır (`data/limit.json` ve uygulama verisi
klasörünüzdeki ikinci kopya); tek bir dosyanın silinmesi sayacı sıfırlamaz.

| | |
|---|---|
| Arayüzden girme | **Araçlar → Lisans…** |
| Komut satırından girme | `python rakip_takip.py --lisans RN1-…` |
| Saklama yeri | `config.json` → `"lisans"` alanı (bir daha sormaz) |
| Hak bittiğinde | Arayüzde kilit penceresi; CLI'da **çıkış kodu 4** |
| Geçersiz anahtar | CLI'da **çıkış kodu 1** |
| Polar anahtarı girişi | Aynı alan (ilk girişte **internet gerekir**, cihaz etiketi kaydedilir) |
| Polar doğrulama | Başlatmada ve 7 günde bir; internetsiz **30 gün** çalışmaya devam |
| Polar reddederse | CLI'da **çıkış kodu 5**; arayüzde işlemler kilitlenir |
| Cihaz limiti | Aynı anahtar en fazla belirli sayıda cihazda açılır (satıcı belirler) |

Zamanlanmış tarama (`tarama.bat`) da her çalıştırmada 1 hak harcar —
deneme süresince günde bir kez çalıştırırsanız 5 gün kullanabilirsiniz.

---

## 2. Arayüz Rehberi (`gui.py`)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ▶ Tarama Başlat  ▶ Seçiliyi Tara  ■ Durdur │ + Ürün Ekle  ✎ ✗ │ 🔍 Seçici Bul  📊 Rapor  🖼 Görsel Getir  ⚙ │
├────────────┬─────────────────────────────────────────────────────────┤
│ 🔍 [arama] │ Tarama Sonuçları│Fiyat Geçmişi│Rapor│🖼│🏆│🔍│🌍 (7 sekme)│
│ [sayfa 1▾] │  ┌───────────────────────────────────────────────────┐ │
│ Ürün listesi│  │ tablo: önceki → yeni, değişim %, durum, mesaj    │ │
│ (çift      │  │ ↑↓ başlık = sırala · ☑ Sadece değişenler         │ │
│  tıkla =   │  │ İthalat: ⬅ Önceki / Sonraki ➡ sayfa butonları    │ │
│  düzenle)  │  └───────────────────────────────────────────────────┘ │
│            │  [dönem ▾] [geçmiş tablosu]     [fiyat grafiği]        │
├────────────┴─────────────────────────────────────────────────────────┤
│ 📟 Konsol  │  🖼 Ürün Görseli   ← görseli burada görürsün           │
├──────────────────────────────────────────────────────────────────────┤
│ ▓▓▓▓░░░░ 1/3 · 33% · Rakip A          Hazır        PIL ✓ · Grafik ✓│
└──────────────────────────────────────────────────────────────────────┘
```

### Sık kullanılan işlemler

| Ne yapmak istiyorsun | Nereye tıklayacaksın |
|---|---|
| Yeni rakip ekle | `+ Ürün Ekle` (veya ürün adını çift tıkla) |
| Fiyatın CSS seçicisini bul | Ürünü seç → `🔍 Seçici Bul` → adayı çift tıkla |
| Tüm rakipleri tara | `▶ Tarama Başlat` (F5) |
| Sadece seçtiklerini tara | Listeden seç → `▶ Seçiliyi Tara` (F6) |
| Taramayı durdur | `■ Durdur` (Esc) |
| Ürünün fiyat geçmişini gör | Sol listeden seç → `Fiyat Geçmişi` sekmesi |
| Fiyat grafiği çiz | Aynı sekmede (en az 2 günlük kayıt gerekir) |
| Özet rapor al | `📊 Rapor` → `Raporu Getir` |
| Rakip ürününün görselini gör | Ürünü seç → `🖼 Görsel Getir` → `Ürün Görseli` sekmesi |
| Telegram'ı dene | `⚙ Ayarlar` → token/chat_id gir → `Araçlar → Telegram Testi` |
| Veriyi Excel'e aktar | `Dosya → ... CSV Aktar` (UTF-8 BOM, Excel'de Türkçe karakterler bozulmaz) |
| Sonuç tablosunu sırala | Tarama Sonuçları'nda **sütun başlığına tıkla** (▲ artan / ▼ azalan) |
| Sadece değişenleri gör | **☑ Sadece değişenler** onay kutusu (tablo anında süzülür) |
| Birçok sonucu toplu takibe al | Sonuçları seç (Ctrl+sol tık) → **＋ Takibe Al** (tekrarlar atlanır) |
| İthalat'ta sayfa değiştir | **⬅ Önceki / Sonraki ➡** butonları (her sayfa 1 deneme hakkı) |
| Geçmişi daralt | Fiyat Geçmişi sekmesinde **Dönem**: 7 gün / 30 / 90 / 1 yıl / Tümü |

### Klavye kısayolları

| Kısayol | İş |
|---|---|
| `F5` | Tümünü tara |
| `F6` | Seçili ürünleri tara |
| `Esc` | Taramayı durdur |
| `Ctrl+F` | Seçici Bul |
| `Ctrl+O` | Config aç |
| `Ctrl+,` | Ayarlar |
| `Enter` | Diyalogda kaydet |
| `Tab` | Çoklu seçim için `Ctrl`+sol tık |

---

## 3. Adım Adım Başlangıç (komut satırı)

### Adım A — Rakip ürünün URL'sini bul

Rakip ürün sayfasını tarayıcıda aç → adres çubuğundaki linki kopyala.

### Adım B — CSS seçicini bul (en önemli adım)

Bot'a fiyatın HTML'de nerede olduğunu söylemen lazım. Bunun için:

```powershell
python rakip_takip.py --inspect "https://rakip.com/urun/xxx"
```

Bu komut sayfada fiyat içeren elementleri listeler ve **hazır seçici** önerir:

```
  fiyat=4900.5   TL   seçici: span.price
  metin: 4.900,50 TL
```

Çıktıdan doğru olanı seçip `config.json`'a yaz.

> **Not:** Site JavaScript ile yüklüyse fiyat görünmeyebilir. Bu durumda
> fiyatı `--inspect` yerine elle kontrol et, ya da farklı bir URL dene.

### Adım C — config.json doldur

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
      "selector": "span.price"
    }
  ]
}
```

| Alan | Açıklama |
|---|---|
| `ad` | Ürünün sana özel adı (raporda ve uyarıda görünür) |
| `url` | Rakip ürün sayfası |
| `selector` | Fiyatın bulunduğu CSS seçicisi. **Boş bırakırsan** bot sayfayı tarayıp para birimli ilk adayı seçer — daha az güvenilir |
| `esik_yuzde` | `0` = her değişiklikte uyar. `5` = %5'ten büyük değişikliklerde uyar |
| `bekleme_saniye` | İstekler arası bekleme. Sayfayı yormamak için 3 ideal |

### Adım D — Telegram kur (bildirim için)

1. Telegram'da **@BotFather**'a git → `/newbot` → ad ver → **token** al
2. Yeni botuna bir kez mesaj gönder
3. Tarayıcıdan aç: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Çıktıda `"chat":{"id": 123456789}` → bu sayı **chat_id**
5. İkisini `config.json`'a yaz

Test et:

```powershell
python rakip_takip.py --test
```

---

## 4. Kullanım (komut satırı)

```powershell
# Tarama yap (günde 1 kez çalıştır)
python rakip_takip.py

# Başka bir config ile
python rakip_takip.py --config rakiplerim.json

# Fiyat geçmişini göster (son 30 gün)
python rakip_takip.py --rapor

# Daha geniş aralık
python rakip_takip.py --rapor --gun 90

# CSS seçici bul
python rakip_takip.py --inspect "URL"

# Telegram testi
python rakip_takip.py --test
```

### Beklenen çıktı

```
2 ürün taranıyor...

• Rakip A - 200x300 yün halı
  ▼ DEĞİŞTİ: 4900.00 → 4200.00 (-14.3%) TL
• Rakip B - Makine dokuma 160x230
  → Değişmedi: 1750.00 TL

🔔 1 değişiklik Telegram'a gönderildi.
```

---

## 5. Otomatik Günlük Çalıştırma (Windows)

Zamanlanmış çalıştırma **arayüzden tek tıkla** kurulabilir:

> `Araçlar → Görev Zamanlayıcıya Ekle (Windows)` → komutu yönetici
> komut satırında çalıştır.

Elle yapmak istersen `tarama.bat` zaten hazır:

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
python rakip_takip.py >> "%~dp0log.txt" 2>&1
```

Sonra **Görev Zamanlayıcı**'da:

1. `taskschd.msc` aç
2. **Görev Oluştur** → isim: `Rakip Takip`
3. **Tetikleyici** → Günlük → saat 09:00
4. **Eylem** → Program başlat → `tarama.bat`'in tam yolu
5. **Koşullar** → "Güç kaynağı: Duvar prize takılı" seç (laptop'ta uyumasın)

> Zamanlanmış görevin **arka planda** çalışması için önemli:
> tarama ekran başında yapılmasa da `config.json`'daki ürünlere göre
> çalışır ve değişiklik olursa Telegram'a mesaj atar.

Artık her sabah çalışır ve değişiklik olursa Telegram'a mesaj gelir.

---

## 6. Veriler Nerede?

- `fiyatlar.db` → tüm fiyat geçmişi (SQLite, Excel'de de açılır)
- `log.txt` → çalıştırma kayıtları

`--rapor` ile özetini görürsün:

```
• Rakip A - 200x300 yün halı
    2026-09-01     4900.00 TL
    2026-09-15     4650.00 TL
    2026-09-28     4200.00 TL
    Aralık: 4200.00 – 4900.00 (±16.7%)
```

---

## 7. Sık Karşılaşılan Sorunlar

| Sorun | Çözüm |
|---|---|
| `Fiyat bulunamadı` | `--inspect URL` (veya arayüzde `🔍 Seçici Bul`) ile doğru seçiciyi bul |
| Yanlış sayı çekiyor | `selector` alanını dolu bırak — boş bırakırsan tahmin eder |
| Sayfa JS ile yükleniyor | Statik URL bul ya da fiyatı elle takip et |
| `robots.txt izin vermiyor` | Site izin vermiyorsa o ürünü atla — saygılı ol |
| Telegram gelmiyor | `--test` çalıştır, token/chat_id kontrol et |
| `Unexpected UTF-8 BOM` | Halledildi (`utf-8-sig`), eski sürümü güncelle |
| Arayüz açılmıyor | `pip install -r requirements.txt` çalıştır, sonra `python gui.py` |
| Grafik görünmüyor | `pip install matplotlib` — durum çubuğunda "Grafik: ✓" olmalı |
| Görsel gelmiyor | `pip install Pillow` — durum çubuğunda "PIL: ✓" olmalı |
| Ürün listesi boş | `+ Ürün Ekle` ile rakip URL'si gir, `🔍 Seçici Bul` ile seçiciyi keşfet |
| `tkinter bulunamadı` | Windows'ta Python'u "tcl/tk" seçeneğiyle yeniden kur |
| Tarama çok yavaş | `⚙ Ayarlar → bekleme` değerini 3'ün altına çekme (sayfayı yorma) |

---

## 8. Testler (geliştirici notu)

Kodu değiştirdiysen veya sorun yaşadıysan test paketini çalıştır:

```bash
python -m unittest discover -v      # ekstra kurulum yok
pip install -r requirements.gelistirme.txt
pytest -q                           # isteğe bağlı
```

- Testler **internete çıkmaz**; yerel bir HTTP sunucusu kurup sayfayı
  oradan okur. Bu yüzden `--config` dosyana dokunmadan koşar.
- 198 test: fiyat ayrıştırma, config (BOM), SQLite, robots.txt, tarama
  akışı (ilk/değişti/değişmedi), Telegram (butonlu uyarı mesajı), lisans
  (Ed25519 + deneme sayacı + CLI kilidi), arayüz (sıralama, filtre, dönem,
  sayfa gezinme), CLI ve "Seçici Bul" penceresinin uçtan uca akışı.
- GitHub'a her push'ta aynı testler `.github/workflows/test.yml` ile
  Windows ve Linux üzerinde otomatik koşar.

---

## 9. Etiği ve Hukuku

- **robots.txt**'e uy. İzin verilmeyen sayfayı tarama (bot bunu otomatik yapar).
- **Günde 1-2 kez** yeterli. Saniyede istek atma — sitenin sunucusunu yorma.
- Çektiğin veriyi **kendi kararın için** kullan; rakibin içeriğini kopyalama.
- Fiyat verisi **kamuya açık** bilgidir; sorumluluk kullanıcıya aittir.

---

## 10. Sonraki Adımlar (öneri)

1. **Görsel karşılaştırma** — ürün görselinde değişiklik algılama
2. **Kampanya yakalama** — "%20 indirim" gibi ifadeleri log'la
3. **Yorum/puan takibi** — rakip puanı düşünce fırsat
4. **WhatsApp bildirimi** — Telegram yerine (takip eden kitlen varsa)
5. **Bot'u web'e taşı** — her pazaryeri satıcısına SaaS olarak sat
