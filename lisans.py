# -*- coding: utf-8 -*-
"""Lisans / deneme hakkı — 5 sorgu sınırı ve anahtar doğrulama.

Ürün koddur; deneme sınırı casual-use (rağbet) engeli içindir:

* Sayaç ``data/limit.json`` içinde HMAC ile mühürlü tutulur — dosya elle
  oynanırsa sayaç geçersiz sayılır ve kilit kalkmaz (kilitli kalır).
* Anahtarlar gömülü gizli anahtarla HMAC-SHA256 imzalanır; imzasız
  üretilen "anahtarlar" reddedilir.
* Geçerli anahtar ``config.json`` → ``"lisans"`` alanına kaydedilir ve
  program tarafından süresiz tanınır.

Sayaç fonksiyonları test için ``yol`` parametresi alır (verilmezse
modül genelindeki ``LIMIT_YOL`` kullanılır).

Satıcı anahtar üretimi:  ``python lisans_uret.py [adet]``
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path

HAK_SINIRI = 5
ANAHTAR_ONEK = "RN1"
_GOVDE_UZUNLUK = 8
_IMZA_UZUNLUK = 12

# Gömülü gizli anahtar (HMAC anahtarı). Kaynak koddan elde edilse bile
# yeni sayaç okunamaz/üretemez; imzalı sayaç silinip yeniden yazılabilir
# (masaüstü ürünü için yeterli casual-use koruması).
_GIZLI_ANAHTAR = (
    b"6b5a535bde67276ef1e8aa3532bdd2198526ee47af22a4737ac9121588883cd7"
)

_KOK = Path(__file__).resolve().parent
LIMIT_YOL = _KOK / "data" / "limit.json"

_HEX = r"[0-9A-F]"


# --------------------------------------------------------------------------
#  Anahtar üretimi / doğrulama
# --------------------------------------------------------------------------
def _tag(alan: str) -> str:
    """``alan`` için kısa HMAC-SHA256 imzası (12 hex karakter, büyük harf)."""
    imza = hmac.new(_GIZLI_ANAHTAR, alan.encode("utf-8"),
                    hashlib.sha256).hexdigest()
    return imza[:_IMZA_UZUNLUK].upper()


def anahtar_uret() -> str:
    """Yeni, doğrulanabilir lisans anahtarı üretir (RN1-XXXXXXXX-XXXXXXXXXXXX)."""
    govde = secrets.token_hex(_GOVDE_UZUNLUK // 2).upper()
    return f"{ANAHTAR_ONEK}-{govde}-{_tag(govde)}"


def anahtar_gecerli(anahtar: object) -> bool:
    """Anahtarın imzasını doğrular (büyük/küçük harf duyarsız)."""
    if not isinstance(anahtar, str):
        return False
    parcalar = anahtar.strip().upper().split("-")
    if len(parcalar) != 3:
        return False
    on, govde, imza = parcalar
    if on != ANAHTAR_ONEK:
        return False
    if not re.fullmatch(f"{_HEX}{{{_GOVDE_UZUNLUK}}}", govde):
        return False
    if not re.fullmatch(f"{_HEX}{{{_IMZA_UZUNLUK}}}", imza):
        return False
    return hmac.compare_digest(_tag(govde), imza)


# --------------------------------------------------------------------------
#  Sayaç (HMAC mühürlü)
# --------------------------------------------------------------------------
def _sayac_mac(hak: int) -> str:
    return hmac.new(_GIZLI_ANAHTAR, f"hak:{hak}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _yol(yol: Path | str | None) -> Path:
    return Path(yol) if yol else LIMIT_YOL


def hak_oku(yol: Path | str | None = None) -> int:
    """Harcanan hakkı okur. Eksik dosya → 0; tahrif/bozuk dosya → sınır (kilit)."""
    hedef = _yol(yol)
    try:
        veri = json.loads(hedef.read_text(encoding="utf-8"))
        hak = int(veri["hak"])
        if not hmac.compare_digest(str(veri.get("mac", "")), _sayac_mac(hak)):
            return HAK_SINIRI
        return max(0, hak)
    except FileNotFoundError:
        return 0
    except Exception:
        return HAK_SINIRI


def hak_yaz(hak: int, yol: Path | str | None = None) -> None:
    """Sayaçı mühürleyerek yazar."""
    hedef = _yol(yol)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    veri = {"hak": int(hak), "mac": _sayac_mac(int(hak))}
    hedef.write_text(json.dumps(veri), encoding="utf-8")


def hak_kalan(yol: Path | str | None = None) -> int:
    """Kullanıcıya kalan deneme hakkını döndürür."""
    return max(0, HAK_SINIRI - hak_oku(yol))


def hak_tuket(yol: Path | str | None = None) -> bool:
    """Bir hakkı harcar. Sınır doluysa ``False`` (kilit)."""
    hak = hak_oku(yol)
    if hak >= HAK_SINIRI:
        return False
    hak_yaz(hak + 1, yol)
    return True


def hak_sifirla(yol: Path | str | None = None) -> None:
    """Sayaç sıfırlar (satıcı/destek amaçlı; lisanslı kullanıcıya gerek yok)."""
    hak_yaz(0, yol)
