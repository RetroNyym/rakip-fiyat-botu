# -*- coding: utf-8 -*-
"""Lisans / deneme hakkı — asimetrik anahtar doğrulama + 5 sorgu sınırı.

Ürün koddur; deneme sınırı casual-use (rağbet) engeli içindir:

* **Anahtarlar asimetrik (Ed25519) imzalanır.** Bu dosyada yalnızca
  *genel* (doğrulama) anahtarı bulunur; imzalayabilen *özel* anahtar
  ``lisans_uret.py`` içindedir ve **dağıtım paketine girmez**. Kaynak
  kodu elde geçen biri yeni anahtar *üretemez*.
* Sayaç ``data/limit.json`` içinde HMAC ile mühürlü tutulur; ayrıca
  ``AYNA_YOL`` (APPDATA) ikinci kopyası yazılır. Dosyalardan biri
  silinirse/bozulursa diğeri sayacı taşır → deneme hakkı sıfırlanamaz.
* Geçerli anahtar ``config.json`` → ``"lisans"`` alanına kaydedilir ve
  program tarafından süresiz tanınır.

Sayaç fonksiyonları test için ``yol`` parametresi alır (verilirse yalnızca
o dosya kullanılır; verilmezse ana dosya + ayna birlikte okunur).

Satıcı anahtar üretimi:  ``python lisans_uret.py [adet]``
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path

from kok_yol import veri_kok

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    KRIPTO_VAR = True
except ImportError:                                   # cryptography yok
    KRIPTO_VAR = False

HAK_SINIRI = 5
ANAHTAR_ONEK = "RN1"
_GOVDE_UZUNLUK = 8
_IMZA_UZUNLUK = 103          # base32 (büyük harf), 64 byte Ed25519 imzası

_HEX = r"[0-9A-F]"
_BASE32 = r"[A-Z2-7]"

# Genel (doğrulama) anahtarı — dağıtılan pakettedir, yalnızca imza doğrular.
# Eşleniği (imzalama anahtarı) lisans_uret.py içindedir, dağıtılmaz.
_GENEL_ANAHTAR = bytes.fromhex(
    "fce7a82c664ad24dadf3994c9a95ab796d1883fd22536d00a2b7bba239dd4b74")

# Sayaç mührü için ayrı gömülü simetrik anahtar. Lisans üretmeye YETMEZ;
# yalnızca sayacın bozulup bozulmadığını kontrol eder.
_SAYAC_ANAHTARI = bytes.fromhex(
    "b7e0f3a1c95d4e8276af0b13c5d8e94216f7a05b3c8d214e6fa9b7c05d3e8f16")

_KOK = veri_kok(__file__)
LIMIT_YOL = _KOK / "data" / "limit.json"


def _varsayilan_ayna() -> Path:
    """İkinci sayaç kopyasının yolu (proje klasörünün dışında)."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "RakipFiyatBot" / "limit.json"
    return Path.home() / ".config" / "rakip-fiyat-botu" / "limit.json"


AYNA_YOL = _varsayilan_ayna()

# GUI'nin çağırdığı alt modüller (radar/ithalat CLI) için: RIYA_IC=1
# "ücreti çağıran ödedi" demektir — modül kendi hakkı harcamaz.
IC_ORTAM = "RIYA_IC"


# --------------------------------------------------------------------------
#  Test modu (yalnızca gerçek test çalıştırıcısı)
# --------------------------------------------------------------------------
def _calistirici_kaniti() -> bool:
    """Gerçek bir test çalıştırıcısının **çalıştığına** dair kanıt.

    ``sys.modules``'e sahte bir ``pytest.py``/``unittest`` sokmak yetmez;
    kanıt çalıştırıcının kendisinin koyduğu izlerdir:

    * ``PYTEST_CURRENT_TEST`` — pytest her test sırasında kurar ve siler;
    * ``argv[0]`` — ``python -m unittest`` → ``…/unittest/__main__.py`` ya
      da ``python test_….py`` (doğrudan test dosyası).
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    argv0 = (sys.argv[0] or "").replace("\\", "/").lower()
    if argv0.endswith("unittest/__main__.py"):          # Linux/mac
        return True
    if "-m unittest" in argv0:                          # Windows: "python.exe -m unittest"
        return True
    if "-m pytest" in argv0:
        return True
    ad = argv0.rsplit("/", 1)[-1]
    return ad.startswith("test_") and ad.endswith(".py")


def test_mi() -> bool:
    """``RIYA_TESTI=1`` yalnızca gerçek test çalıştırıcısı altında geçerlidir.

    Boşluk: ortam değişkenini alan kullanıcı deneme sınırını aşamasın diye
    test bayrağı tek başına yeterli değildir; ayrıca test çalıştırıcısının
    **çalıştığına dair kanıt** (``_calistirici_kaniti``) veya CI ortamı
    gerekir.
    """
    if os.environ.get("RIYA_TESTI") != "1":
        return False
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return True
    return _calistirici_kaniti()



def ic_cagri() -> bool:
    """Çağrı, ücreti zaten ödenmiş bir iç (GUI) çağrısı mı?"""
    return os.environ.get(IC_ORTAM) == "1"


def ayar_izinli(ayar: dict | None) -> bool:
    """Config içinde geçerli lisans anahtarı var mı (veya test/ic modu)?"""
    if test_mi() or ic_cagri():
        return True
    return anahtar_gecerli((ayar or {}).get("lisans") or "")


# --------------------------------------------------------------------------
#  Anahtar üretimi / doğrulama (Ed25519)
# --------------------------------------------------------------------------
def _imza_metni(govde: str) -> bytes:
    """İmzalanan baytlar (anahtar gövdesi ile bağlanır)."""
    return f"{ANAHTAR_ONEK}|{govde}".encode("utf-8")


def _b32coz(deger: str) -> bytes | None:
    try:
        ham = base64.b32decode(deger + "=" * (-len(deger) % 8))
    except Exception:                                   # noqa: BLE001
        return None
    return ham


def anahtar_gecerli(anahtar: object) -> bool:
    """Anahtarın Ed25519 imzasını doğrular (büyük/küçük harf duyarsız).

    Üretim yalnızca ``lisans_uret.py`` (satıcı) içindedir; bu dosya
    dağıtılsa bile yeni anahtar imzalanamaz.
    """
    if not KRIPTO_VAR or not isinstance(anahtar, str):
        return False
    parcalar = anahtar.strip().upper().split("-")
    if len(parcalar) != 3:
        return False
    on, govde, imza = parcalar
    if on != ANAHTAR_ONEK:
        return False
    if not re.fullmatch(f"{_HEX}{{{_GOVDE_UZUNLUK}}}", govde):
        return False
    if not re.fullmatch(f"{_BASE32}{{{_IMZA_UZUNLUK}}}", imza):
        return False
    ham = _b32coz(imza)
    if ham is None or len(ham) != 64:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(_GENEL_ANAHTAR).verify(
            ham, _imza_metni(govde))
    except (InvalidSignature, ValueError):
        return False
    return True


# --------------------------------------------------------------------------
#  Sayaç (HMAC mühürlü, iki kopyalı)
# --------------------------------------------------------------------------
def _sayac_mac(hak: int) -> str:
    return hmac.new(_SAYAC_ANAHTARI, f"hak:{hak}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _yol(yol: Path | str | None) -> Path:
    return Path(yol) if yol else LIMIT_YOL


def _tek_oku(hedef: Path) -> int | None:
    """``None`` = dosya yok · int = harcanan hak · ``HAK_SINIRI`` = bozuk."""
    try:
        veri = json.loads(hedef.read_text(encoding="utf-8"))
        hak = int(veri["hak"])
        if not hmac.compare_digest(str(veri.get("mac", "")), _sayac_mac(hak)):
            return HAK_SINIRI
        return max(0, hak)
    except FileNotFoundError:
        return None
    except Exception:                                   # noqa: BLE001
        return HAK_SINIRI


def _tek_yaz(hedef: Path, hak: int) -> None:
    hedef.parent.mkdir(parents=True, exist_ok=True)
    veri = {"hak": int(hak), "mac": _sayac_mac(int(hak))}
    hedef.write_text(json.dumps(veri), encoding="utf-8")


def hak_oku(yol: Path | str | None = None) -> int:
    """Harcanan hakkı okur.

    Belirli bir ``yol`` verilirse yalnızca o dosya okunur (test). Verilmezse
    ana dosya ile ``AYNA_YOL`` birlikte okunur; **ikisinden en yükseği**
    geçerlidir, yani dosyalardan birinin silinmesi sayacı sıfırlamaz.
    """
    if yol is not None:
        sonuc = _tek_oku(Path(yol))
        return 0 if sonuc is None else sonuc
    degerler = [d for d in (_tek_oku(_yol(None)), _tek_oku(AYNA_YOL))
                if d is not None]
    if not degerler:
        return 0
    return max(degerler)


def hak_yaz(hak: int, yol: Path | str | None = None) -> None:
    """Sayaçı mühürleyerek yazar (ana dosya + ayna).

    Ana dosya yazılamazsa (ör. ``exe`` Program Files'ta) aynaya düşülür;
    ikisi de başarısızsa hata **yükselir** — sessizce kayıp, demek
    sınırsız kullanım demek olurdu.
    """
    hedef = _yol(yol)
    hata: OSError | None = None
    try:
        _tek_yaz(hedef, int(hak))
    except OSError as exc:
        if yol is not None:
            raise
        hata = exc
    if yol is None:
        ayna = Path(AYNA_YOL)
        if ayna != hedef:
            try:
                _tek_yaz(ayna, int(hak))
                hata = None
            except OSError:
                pass                                    # ayna yazılamadı
    if hata is not None:
        raise hata


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


def sifirlama_jetonu_gecerli(jeton: object) -> bool:
    """Satıcının ürettiği sıfırlama jetonu: ``SIFIRLA-<nonce>-<imza>``.

    İmza Ed25519 ile **özel anahtar** atılır; özel anahtar dağıtılan
    pakette yoktur → müşteri ``hak_sifirla``'yı kendi başına çağıramaz.
    """
    if not KRIPTO_VAR or not isinstance(jeton, str):
        return False
    parcalar = jeton.strip().upper().split("-")
    if len(parcalar) != 3 or parcalar[0] != "SIFIRLA":
        return False
    nonce, imza = parcalar[1], parcalar[2]
    if not re.fullmatch(r"[0-9A-F]{16}", nonce):
        return False
    if not re.fullmatch(f"{_BASE32}{{{_IMZA_UZUNLUK}}}", imza):
        return False
    ham = _b32coz(imza)
    if ham is None or len(ham) != 64:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(_GENEL_ANAHTAR).verify(
            ham, f"{ANAHTAR_ONEK}|SIFIRLA|{nonce}".encode("utf-8"))
    except (InvalidSignature, ValueError):
        return False
    return True


def hak_sifirla(yol: Path | str | None = None,
                jeton: str | None = None) -> bool:
    """Sayaç sıfırlar — test modunda veya geçerli satıcı jetonuyla.

    Dağıtılan kodda jeton üretilemez (özel anahtar ``lisans_uret.py``'de
    kalır); aksi hâlde müşteri ``lisans.hak_sifirla()`` ile deneme hakkını
    tek satırla sıfırlayabilirdi. ``False`` = yetki yok, sayaç değişmedi.
    """
    if not (test_mi() or sifirlama_jetonu_gecerli(jeton)):
        return False
    hak_yaz(0, yol)
    return True
