"""CLI girişi — GUI'nin çağırdığı biçim:

    python -m ithalat ara "nike" --sayfa 1 --json ithalat_gui.json
    python -m ithalat firma company/nike --json ithalat_gui.json
    python -m ithalat tedarikci supplier/nike --json ithalat_gui.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .ag import AgHatasi
from .arama import ara
from .sayfa import sayfa_al

KOK = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def yaz(metin: str = "") -> None:
    print(metin, flush=True)


def argumanlari(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ithalat",
        description="ImportYeti tabanlı tedarikçi/rakip analiz motoru.")
    p.add_argument("komut", choices=["ara", "firma", "tedarikci"])
    p.add_argument("hedef",
                   help="ara: sorgu; firma/tedarikci: company/x ya da supplier/x")
    p.add_argument("--sayfa", type=int, default=1, help="arama sayfası")
    p.add_argument("--json", dest="json_yol",
                   default=str(KOK / "data" / "out" / "ithalat_gui.json"))
    p.add_argument("--surum", action="version", version=f"ithalat {__version__}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = argumanlari(argv)
    yaz("=" * 60)
    yaz(f"🌍 ithalat {__version__} · {args.komut}: {args.hedef}")
    yaz("=" * 60)

    try:
        if args.komut == "ara":
            veri = ara(args.hedef, sayfa=max(1, args.sayfa))
            yaz(f"🔎 '{veri['sorgu']}' → {veri['toplam']} sonuç "
                f"(sayfa {veri['sayfa']}/{veri['toplam_sayfa']}, "
                f"kalan hak: {veri['kalan_hak']})")
            for s in veri["sonuclar"][:5]:
                yaz(f"  · [{s['tur']}] {s['ad']} ({s['ulke']}) — "
                    f"{s['sefer']} sefer")
        else:
            veri = sayfa_al(args.hedef)
            ad = "firma" if veri["tur"] == "firma" else "tedarikçi"
            yaz(f"📄 {veri['ad']} — {veri['adres']}")
            yaz(f"  {len(veri['satirlar'])} {ad} bağlantısı, "
                f"{len(veri['ulkeler'])} ülke, "
                f"son sevkiyat: {veri['ozet']['son_sevkiyat'] or '-'}")
    except (AgHatasi, ValueError) as hata:
        yaz(f"✗ {hata}")
        return 2
    except Exception as hata:  # noqa: BLE001 — GUI'ye tam hata metni gerekir
        import traceback
        yaz("✗ beklenmeyen hata:\n" + traceback.format_exc(limit=6))
        return 3

    json_yol = Path(args.json_yol).resolve()
    json_yol.parent.mkdir(parents=True, exist_ok=True)
    json_yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    yaz(f"📦 JSON: {json_yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
