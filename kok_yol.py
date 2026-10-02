"""Kök klasör çözümü — kaynak (Python) ve PyInstaller ``.exe`` için.

PyInstaller dondurulmuş (frozen) modda modül dosyalarını geçici bir
klasöre çıkarır (``sys._MEIPASS``); ``Path(__file__)`` oraya işaret eder.
Yazılabilir veriler (``config.json``, ``fiyatlar.db``, ``data/``) ise
**exe'nin yanında** durmalıdır; aksi hâlde her açılışta sıfırlanırdı.

Bu modül iki şeyi ayırır:

* ``kaynak_kok()`` — ek/dağıtılan dosyaların (radar klasörleri, örnek
  config) aranacağı yer: dondurulmuşta ``_MEIPASS``, kaynakta dosyanın
  klasörü.
* ``veri_kok()`` — kullanıcı verisinin yazılacağı kalıcı yer: dondurulmuşta
  **exe'nin klasörü**, kaynakta dosyanın klasörü.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["frozen_mi", "kaynak_kok", "veri_kok"]


def frozen_mi() -> bool:
    """Program PyInstaller ile mi paketlenmiş?"""
    return bool(getattr(sys, "frozen", False))


def kaynak_kok(bu_dosya: str | None = None) -> Path:
    """Dağıtılan/ek dosyaların bulunduğu klasör."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(bu_dosya or __file__).resolve().parent


def veri_kok(bu_dosya: str | None = None) -> Path:
    """Kullanıcı verisinin (config, veritabanı, sayaç) yazılacağı klasör."""
    if frozen_mi():
        return Path(sys.executable).resolve().parent
    return Path(bu_dosya or __file__).resolve().parent
