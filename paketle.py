# -*- coding: utf-8 -*-
"""Dağıtım paketi üretir (satıcı aracı — pakete kendisi dahil edilmez).

    python paketle.py            # dist/rakip-fiyat-botu-<sürüm>/ oluşturur
    python paketle.py --zip      # ayrıca .zip arşivi üretir
    python paketle.py --temizle  # dist/ klasörünü siler

Ne yapar:
  1. Depo içeriğini ``dist/`` altına, **izin listesi** ile kopyalar.
  2. Asla gitmemesi gereken dosyaları denetler:
       · ``lisans_uret.py``      → özel (imzalama) anahtarı taşır
       · ``paketle.py``          → satıcı aracı
       · ``test_*.py``           → test paketi
       · ``config.json``, ``fiyatlar.db``, ``data/``, ``.git/``
  3. Kopyalanan tüm metin dosyalarında **gizli anahtar sızıntısı** tarar
     (özel lisans anahtarının onaltılık değeri ve sayaç mühür anahtarı).
  4. Paket kökünde ``lisans`` modülünü yükleyip genel anahtarın
     çalıştığını doğrular (sağlam kontrol).

Çıkış kodu: 0 başarılı · 1 denetim hatası (paket SATILMAZ).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                       # noqa: BLE001
    pass

KOK = Path(__file__).resolve().parent

# Pakete girmeyecek dosya/klasör adları (tüm seviyelerde)
HARIC_AD = {
    "lisans_uret.py",          # ✗ özel lisans anahtarı
    "paketle.py",              # ✗ satıcı aracı
    "config.json",             # ✗ kişisel ayar + lisans
    "fiyatlar.db",             # ✗ fiyat geçmişi
    "log.txt",
    ".git", ".github", ".gitignore", ".gitattributes",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    "dist", "build", "venv", ".venv", "env",
    ".gizli", ".wrangler",
}

# İsim kalıbıyla hariç tutulanlar
HARIC_KALIP = (
    re.compile(r"^test_.*\.py$"),       # ✗ test paketi
    re.compile(r"^_test.*$"),           # ✗ geçici denemeler
    re.compile(r"^.*\.py[cod]$"),
    re.compile(r"^.*\.log$"),
    re.compile(r"^requirements\.gelistirme\.txt$"),
)

# Klasör yolu içinde geçen (adı ne olursa olsun) hariç tutulan dizinler
# ``data``: sayaç (limit.json) kişiseldir, pakete girmez — ilk açılışta oluşur.
HARIC_DIZIN = {"__pycache__", ".git", ".pytest_cache", "out", ".venv",
               "venv", "data", "dist", "build", ".mypy_cache"}

# Gizli anahtar sızıntısı taraması için aday dosya uzantıları
METIN_UZANTISI = {".py", ".json", ".md", ".txt", ".bat", ".yml", ".cfg"}


def surum_bul() -> str:
    """Sürümü gui.py'deki rozetten okur (ör. `` v2.7 `` → ``2.7``)."""
    gui = KOK / "gui.py"
    if gui.exists():
        eslesme = re.search(r'"\s*v(\d+\.\d+)\s*"',
                            gui.read_text(encoding="utf-8"))
        if eslesme:
            return eslesme.group(1)
    return "0.0"


def gizli_degerler() -> dict[str, str]:
    """Paket içinde **asla** bulunmaması gereken gizli değerler (ad → değer).

    Tek gerçek gizem, lisans anahtarını imzalayan özel anahtardır: onu elde
    geçen herkes sınırsız anahtar basabilir. Sayaç mühür anahtarı ise
    (simetrik olduğu için) uygulamanın sayacı yazıp doğrulaması adına
    pakette bulunmak **zorundadır** — dolayısıyla denetlenmez.
    """
    degerler: dict[str, str] = {}
    try:
        import lisans_uret
        degerler["lisans özel (imzalama) anahtarı"] = \
            lisans_uret._OZEL_ANAHTAR.hex()
    except Exception:                                   # noqa: BLE001
        pass
    return degerler


def hariç_mi(yol: Path) -> bool:
    """Dosya, pakete girmemeli mi?"""
    for parca in yol.parts:
        if parca in HARIC_AD or parca in HARIC_DIZIN:
            return True
    return any(kalip.search(yol.name) for kalip in HARIC_KALIP)


def kopyala(hedef_kok: Path) -> list[Path]:
    """İzin listesine göre kopyalanan dosyaları döndürür.

    ``os.walk`` ile gereksiz dizinlere hiç inilmez (.git, .venv, data/ …).
    """
    kopyalanan: list[Path] = []
    for kok, dizinler, dosyalar in os.walk(KOK):
        dizinler[:] = [d for d in dizinler if d not in HARIC_DIZIN
                       and d not in HARIC_AD]
        for dosya in dosyalar:
            kaynak = Path(kok) / dosya
            goreli = kaynak.relative_to(KOK)
            if hariç_mi(goreli):
                continue
            hedef = hedef_kok / goreli
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(kaynak, hedef)
            kopyalanan.append(goreli)
    return sorted(kopyalanan)


def denetle(hedef_kok: Path, dosyalar: list[Path]) -> list[str]:
    """Paket denetimi — sorun listesi döner (boşsa paket sağlam)."""
    hatalar: list[str] = []

    # 0) Satıcı dosyası git takibinde mi? (public depoda = özel anahtar sızıntısı)
    if (KOK / ".git").exists():
        try:
            sonuc = subprocess.run(
                ["git", "-C", str(KOK), "ls-files", "--error-unmatch",
                 "lisans_uret.py"],
                capture_output=True, text=True, timeout=20)
            if sonuc.returncode == 0:
                hatalar.append(
                    "lisans_uret.py git takibinde → "
                    "`git rm --cached lisans_uret.py` çalıştır (public depoda "
                    "özel anahtar herkese açık olur)")
        except Exception:                               # noqa: BLE001
            pass

    # 1) Yasaklı dosya var mı?
    yasakli = ["lisans_uret.py", "paketle.py"]
    for ad in yasakli:
        for bulunan in hedef_kok.rglob(ad):
            hatalar.append(f"YASAKLI DOSYA PAKETTE: {bulunan.relative_to(hedef_kok)}")
    for bulunan in hedef_kok.rglob("test_*.py"):
        hatalar.append(f"TEST DOSYASI PAKETTE: {bulunan.relative_to(hedef_kok)}")
    for ad in ("config.json", "fiyatlar.db"):
        if (hedef_kok / ad).exists():
            hatalar.append(f"KİŞİSEL DOSYA PAKETTE: {ad}")

    # 2) Gizli anahtar sızıntısı
    gizliler = gizli_degerler()
    for goreli in dosyalar:
        if goreli.suffix.lower() not in METIN_UZANTISI:
            continue
        try:
            icerik = (hedef_kok / goreli).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for ad, deger in gizliler.items():
            if deger and deger in icerik:
                hatalar.append(f"GİZLİ ANAHTAR SIZINTISI: {goreli} ({ad})")

    # 3) Lisans modülü yüklenebiliyor mu? (genel anahtarla doğrulama)
    sistem_yolu = [str(m) for m in sys.path]
    eski_pyc = sys.dont_write_bytecode
    sys.dont_write_bytecode = True        # .pyc pakete sızmamalı
    try:
        sys.path.insert(0, str(hedef_kok))
        for ad in ("lisans", "lisans_uret"):
            sys.modules.pop(ad, None)
        import lisans
        if not lisans.KRIPTO_VAR:
            hatalar.append("lisans.py: cryptography yüklenemedi")
        if lisans.anahtar_gecerli("RN1-00000000-" + "A" * 103):
            hatalar.append("lisans.py: sahte anahtar kabul edildi (!)")
        if not hasattr(lisans, "_SAYAC_ANAHTARI"):
            hatalar.append("lisans.py: sayaç mühür anahtarı eksik")
        if not hasattr(lisans, "test_mi"):
            hatalar.append("lisans.py: test_mi() eksik")
        if (hedef_kok / "lisans_uret.py").exists():
            hatalar.append("lisans_uret.py paketten çıkarılmamış")
    except Exception as hata:                            # noqa: BLE001
        hatalar.append(f"lisans.py paketten yüklenemedi: {hata}")
    finally:
        sys.path[:] = sistem_yolu
        sys.dont_write_bytecode = eski_pyc
        for ad in ("lisans", "lisans_uret"):
            sys.modules.pop(ad, None)
    return hatalar


def pyc_temizle(hedef_kok: Path) -> int:
    """Denetim sırasındaki import'ların ürettiği ``__pycache__``'leri siler."""
    adet = 0
    for bulunan in sorted(hedef_kok.rglob("__pycache__"), reverse=True):
        if bulunan.is_dir():
            shutil.rmtree(bulunan, ignore_errors=True)
            adet += 1
    return adet


def arsivle(hedef_kok: Path, yol: Path) -> None:
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as arsiv:
        for dosya in sorted(hedef_kok.rglob("*")):
            if dosya.is_file():
                arsiv.write(dosya, dosya.relative_to(hedef_kok.parent))


def main() -> None:
    p = argparse.ArgumentParser(description="Dağıtım paketi üret")
    p.add_argument("--zip", action="store_true", help=".zip arşivi de üret")
    p.add_argument("--temizle", action="store_true",
                   help="dist/ klasörünü sil ve çık")
    args = p.parse_args()

    dist = KOK / "dist"
    if args.temizle:
        if dist.exists():
            shutil.rmtree(dist)
            print("dist/ silindi.")
        return

    surum = surum_bul()
    hedef = dist / f"rakip-fiyat-botu-{surum}"
    if hedef.exists():
        shutil.rmtree(hedef)
    hedef.mkdir(parents=True)

    dosyalar = kopyala(hedef)
    hatalar = denetle(hedef, dosyalar)
    pyc_temizle(hedef)

    print(f"Paket: {hedef}")
    print(f"  · {len(dosyalar)} dosya kopyalandı")
    print(f"  · sürüm: {surum}")
    print("  · hariç: lisans_uret.py, paketle.py, test_*.py, config.json, "
          "fiyatlar.db, data/, .git/")
    if hatalar:
        print("\n✗ DENETIM BAŞARISIZ — bu paket SATILMAZ:")
        for hata in hatalar:
            print(f"   - {hata}")
        sys.exit(1)
    print("\n✓ Denetim temiz — paket dağıtıma hazır.")

    if args.zip:
        arsiv_yol = dist / f"rakip-fiyat-botu-{surum}.zip"
        if arsiv_yol.exists():
            arsiv_yol.unlink()
        arsivle(hedef, arsiv_yol)
        print(f"✓ Arşiv: {arsiv_yol} "
              f"({arsiv_yol.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
