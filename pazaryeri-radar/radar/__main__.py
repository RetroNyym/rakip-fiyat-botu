"""CLI girişi — GUI'nin çağırdığı biçim:

    python -m radar "iphone 15 kılıf" -m trendyol,n11 -p 2 \
        --json C:/.../data/out/radar_gui.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .ag import AgHatasi, indir
from .ayristir import URL_SABLON, Listeleme, sayfayi_ayristir
from .rapor import rapor_yaz
from .topla import satirlari_uret

PLATFORM_VARSAYILAN = "trendyol,n11,hepsiburada"
KOK = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def yaz(metin: str = "") -> None:
    """GUI kuyruğuna anlık düşmesi için satır satır, tamponlamasız yazar."""
    print(metin, flush=True)


def argumanlari_ayristir(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="radar",
        description="Pazaryeri satıcı radar motoru (rakip-fiyat-botu).")
    p.add_argument("sorgu", help="aranacak ürün kelime grubu")
    p.add_argument("-m", "--platformlar", default=PLATFORM_VARSAYILAN,
                   help="virgülle ayrılmış platformlar "
                        f"(varsayılan: {PLATFORM_VARSAYILAN})")
    p.add_argument("-p", "--sayfa", type=int, default=2,
                   help="platform başına sayfa sayısı (varsayılan: 2)")
    p.add_argument("--json", dest="json_yol",
                   default=str(KOK / "data" / "out" / "radar_gui.json"),
                   help="sonucun yazılacağı JSON dosyası")
    p.add_argument("--sayfa-bekleme", type=float, default=2.0,
                   help="sayfalar arası bekleme (sn, varsayılan: 2)")
    p.add_argument("--zaman-asimi", type=float, default=25.0,
                   help="istek zaman aşımı (sn)")
    p.add_argument("--html-dizin", default=None,
                   help="ağ yerine yerel HTML dosyalarından oku "
                        "(geliştirme/çevrimdışı test; <platform>_<n>.html)")
    p.add_argument("--surum", action="version",
                   version=f"radar {__version__}")
    return p.parse_args(argv)


def sayfalari_topla(args: argparse.Namespace,
                    platform: str) -> tuple[list[Listeleme], str | None]:
    """Bir platformun tüm sayfalarını indirir/ayrıştırır.

    (listelemler, hata) döner; hata varsa o platform hiç alınamamıştır.
    """
    if platform not in URL_SABLON:
        return [], f"bilinmeyen platform: {platform}"

    if args.html_dizin:
        bulunan: list[Listeleme] = []
        dizin = Path(args.html_dizin)
        for s in range(1, max(1, args.sayfa) + 1):
            dosya = dizin / f"{platform}_{s}.html"
            if not dosya.exists():
                continue
            ham = dosya.read_text(encoding="utf-8", errors="replace")
            bulunan.extend(sayfayi_ayristir(platform, ham))
            yaz(f"[{platform}] yerel sayfa {s}: {len(bulunan)} listeleme")
        if not bulunan and not (dizin / f"{platform}_1.html").exists():
            return [], f"yerel dosya yok: {dizin / (platform + '_1.html')}"
        return bulunan, None

    toplam: list[Listeleme] = []
    ilk_hata: str | None = None
    for s in range(1, max(1, args.sayfa) + 1):
        url = URL_SABLON[platform].format(sorgu=args.sorgu, sayfa=s)
        yaz(f"[{platform}] sayfa {s}/{args.sayfa} alınıyor…")
        try:
            ham = indir(url, platform=platform, sayfa=s,
                        zaman_asimi=args.zaman_asimi)
        except AgHatasi as hata:
            ilk_hata = str(hata)
            yaz(f"[{platform}] ✗ {hata}")
            break
        yeni = sayfayi_ayristir(platform, ham)
        toplam.extend(yeni)
        yaz(f"[{platform}] sayfa {s}: {len(yeni)} listeleme")
        if not yeni:
            yaz(f"[{platform}] ⚠ Ürün kartı bulunamadı — sayfa yapısı "
                "değişmiş ya da bot engeli. (RADAR_DEBUG_HTML=1 ile ham "
                "HTML'i kaydedip inceleyin.)")
        if s < args.sayfa and args.sayfa_bekleme > 0:
            time.sleep(args.sayfa_bekleme)
    return toplam, ilk_hata if not toplam else None


def main(argv: list[str] | None = None) -> int:
    args = argumanlari_ayristir(argv)
    platformlar = [p.strip().lower() for p in
                   args.platformlar.split(",") if p.strip()]
    sayfa_sayisi = max(1, min(args.sayfa, 20))

    yaz("=" * 60)
    yaz(f"🏆 radar {__version__} · sorgu: '{args.sorgu}' · "
        f"platformlar: {', '.join(platformlar)} · {sayfa_sayisi} sayfa")
    yaz("=" * 60)

    tum_listelemler: list[Listeleme] = []
    engellenen: dict[str, str] = {}
    for platform in platformlar:
        liste, hata = sayfalari_topla(args, platform)
        tum_listelemler.extend(liste)
        if hata and not liste:
            engellenen[platform] = hata
        if platform != platformlar[-1] and not args.html_dizin \
                and args.sayfa_bekleme > 0:
            time.sleep(args.sayfa_bekleme)

    if not tum_listelemler:
        yaz("✗ Hiç listeleme bulunamadı.")
        for p, neden in engellenen.items():
            yaz(f"  · {p}: {neden}")
        yaz("İpucu: ağ erişimi var mı kontrol edin (tarayıcıda da "
            "açılmıyorsa güvenlik duvarı/VPN engeli olabilir).")
        return 2

    satirlar, ozet = satirlari_uret(tum_listelemler, engellenen)
    rapor_yolu = rapor_yaz(KOK, args.sorgu, platformlar, sayfa_sayisi,
                           satirlar, ozet)

    sonuc = {
        "query": args.sorgu,
        "rows": satirlar,
        "estimate_summary": {
            "products_total": ozet["products_total"],
            "sellers": ozet["sellers"],
            "units_lo": ozet["units_lo"],
            "units_hi": ozet["units_hi"],
        },
        "delta_days": None,
        "report": str(rapor_yolu),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine_version": __version__,
    }

    json_yol = Path(args.json_yol).resolve()
    json_yol.parent.mkdir(parents=True, exist_ok=True)
    json_yol.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    yaz(f"✅ Toplam {ozet['products_total']} listeleme, "
        f"{ozet['sellers']} satıcı bulundu.")
    for p, neden in engellenen.items():
        yaz(f"⚠ {p} alınamadı: {neden}")
    yaz(f"📄 Rapor: {rapor_yolu}")
    yaz(f"📦 JSON: {json_yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
