"""Markdown satıcı raporu (leaderboard.md) üretimi."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

YORUM_METNI = "10"


def dosya_adi(sorgu: str) -> str:
    temiz = re.sub(r"[^\w\s-]", "", sorgu, flags=re.UNICODE).strip()
    temiz = re.sub(r"\s+", "-", temiz.lower())[:60] or "sorgu"
    return f"{datetime.now():%Y%m%d-%H%M%S}_{temiz}"


def rapor_yaz(kok: Path, sorgu: str, platformlar: list[str],
              sayfa_sayisi: int, satirlar: list[dict], ozet: dict) -> Path:
    """Raporu `data/out/<zaman>_<sorgu>/leaderboard.md` altına yazar."""
    hedef_klasor = kok / "data" / "out" / dosya_adi(sorgu)
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    hedef = hedef_klasor / "leaderboard.md"

    satirlar_md = []
    for s in satirlar:
        lider = " 🏆" if s["rank"] == 1 else ""
        satirlar_md.append(
            f"| {s['rank']} | {s['seller_name']}{lider} "
            f"| {s['platform']} | {s['listings']} | %{s['share_listings']} "
            f"| {s['reviews']} | {s['badge_products']} "
            f"| {s['units_lo']}–{s['units_hi']} "
            f"| {s['revenue_lo']:,}–{s['revenue_hi']:,} "
            f"| {s['confidence']} |".replace(",", "."))

    engellenen = ozet.get("engellenen_platformlar") or {}
    engel_md = ""
    if engellenen:
        satirlar_engel = "\n".join(
            f"- **{p}**: {neden}" for p, neden in engellenen.items())
        engel_md = ("\n## ⚠️ Erişilemeyen platformlar\n\n"
                    f"{satirlar_engel}\n")

    icerik = f"""# 🏆 Rakip Radar Raporu — "{sorgu}"

- **Tarih:** {datetime.now():%Y-%m-%d %H:%M}
- **Platformlar:** {', '.join(platformlar)}
- **Taranan sayfa / platform:** {sayfa_sayisi}
- **Toplam listeleme:** {ozet.get('products_total', 0)}
- **Bulunan satıcı:** {ozet.get('sellers', 0)}
{engel_md}
## Satıcı Sıralaması

| # | Satıcı | Platform | Liste | Pay | Yorum | Rozetli | Tahmini 30g satış | Tahmini ciro ₺ | Güven |
|---|--------|----------|-------|-----|-------|---------|-------------------|----------------|-------|
{chr(10).join(satirlar_md) if satirlar_md else "| — | Veri yok | — | — | — | — | — | — | — | — |"}

## 🔢 Rakamlar nasıl hesaplanıyor?

Bu rakamlar **tahminidir**, kesin satış verisi değildir:

- **Tahmini 30g satış (alt sınır):** Ürün kartlarındaki *\"…+ Satan\"*
  rozetlerinin toplamı (rozet yoksa yorum sayısı).
- **Tahmini 30g satış (üst sınır):** Toplam yorum sayısı × {YORUM_METNI}
  (yorum yapanların bir kısmı satın alır varsayımı).
- **Tahmini ciro:** Satıcı listelemelerinin ortalama fiyatıyla çarpım.
- **Güven:** Rozet kapsamına ve satıcı bilgisinin bulunabilirliğine göre
  Yüksek / Orta / Düşük.
- Aynı sorguyu günlerce arka arkaya çalıştırdığınızda delta (yorum
  değişimleri) hesaplanır ve aralık sıkışır.

*Bu rapor `pazaryeri-radar` tarafından otomatik üretildi.*
"""
    hedef.write_text(icerik, encoding="utf-8")
    return hedef

