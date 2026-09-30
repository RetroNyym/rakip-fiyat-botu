# pazaryeri-radar

`rakip-fiyat-botu` GUI'sinin **🏆 Rakip Radar** sekmesi için satıcı radar motoru.

## Kullanım

```bash
python -m radar "iphone 15 kılıf" -m trendyol,n11,hepsiburada -p 2 \
    --json data/out/radar_gui.json
```

| Parametre | Anlamı |
|---|---|
| `sorgu` (posisyonel) | Aranacak kelime grubu |
| `-m` | Virgülle ayrılmış platformlar: `trendyol`, `n11`, `hepsiburada` |
| `-p` | Platform başına sayfa sayısı (1–20) |
| `--json` | Sonucun yazılacağı JSON dosyası (varsayılan: `data/out/radar_gui.json`) |
| `--mod` | `satici` (varsayılan): satıcı liderlik tablosu · `urun`: her siteden ürün listesi (fiyat + link) — GUI'nin "Ürün Arama" sekmesi bunu kullanır |
| `--sayfa-bekleme` | Sayfalar arası bekleme (sn, varsayılan 2) |
| `--html-dizin` | Ağ yerine yerel HTML dosyalarından okur (`<platform>_<n>.html`) — çevrimdışı test için |

Çıktı: konsola (stdout) Türkçe ilerleme satırları, JSON + `data/out/<zaman>_<sorgu>/leaderboard.md`
raporu. En az bir listeleme bulunamazsa **çıkış kodu 2** döner (GUI konsola bakın der).

`--mod urun` çıktısı (toplu ürün araması):

```bash
python -m radar "iphone 15" --mod urun -m trendyol,n11,hepsiburada,amazon \
    -p 1 --json data/out/paz_arama_gui.json
```

→ `{sorgu, siteler: [{site, hata, urunler: [{ad, fiyat, para, url, satici, yorum, puan}]}], toplam}`
— platform başına 1 sayfa okur, `ornek-html/` (4 site örneği) ile çevrimdışı da çalışır.

## Tahmini rakamlar nasıl hesaplanır?

- **Alt sınır:** kartlardaki "…+ Satan" rozetleri toplamı (yoksa yorum sayısı)
- **Üst sınır:** toplam yorum × 10
- **Ciro:** ortalama fiyatla çarpım
- İlk çalıştırmada tarihsel delta (yorum değişimi) yoktur; aynı sorgu günlerce
  tekrarlandığında aralık sıkışır. **Rakamlar tahminidir.**

## Bağımlılıklar

- Python 3.10+
- `beautifulsoup4` (zaten kurulu)
- `curl_cffi` (önerilir — tarayıcı parmak izi ile bot engellerini aşar);
  yoksa `requests` ile dener
- `pazaryeri-radar/.venv` varsa GUI onu kullanır; yoksa ana Python'u kullanır

## Hata ayıklama

- `RADAR_DEBUG_HTML=1` ortam değişkeni her sayfanın ham HTML'ini
  `data/out/debug_<platform>_<n>.html` altına yazar.
- **"Bağlantı hatası / TLS kesiliyor"** hatası genelde ağdaki güvenlik
  duvarıdır (ör. Berqnet "Erişim engellendi"): bu ağa özel, kodla aşılıp
  aşılması siteye/ politikaya göre değişir — önce tarayıcıda siteyi kontrol edin.
- Sayfa yapısı değişip "ürün kartı bulunamadı" çıkarsa `ornek-html/`
  klasöründeki gibi güncel sayfanın kaydını ekleyip seçicileri güncelleyin.
