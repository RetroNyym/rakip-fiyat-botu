"""Polar.sh lisans doğrulaması — masaüstü için tasarlanmış **auth'suz** uçlar.

Polar'ın ``/v1/customer-portal/license-keys/*`` uçları hiçbir API anahtarı
istemeyecek şekilde üretilmiştir ("saf bir masaüstü/mobil uygulamada güvenle
kullanılabilir"); yani istemcide saklanacak bir sır yok, kendi doğrulama
sunucumuzu kurmak zorunda değiliz. Satıcı Polar panelinden anahtarı **iptal
edebilir**, **cihaz limiti** koyabilir, müşteri portalinden aktivasyon
sıfırlatabilir.

İki anahtar kanalı birlikte yaşar (biçimden ayırt edilir):

* ``RN1-…`` — paket içinde Ed25519 ile **çevrimdışı** doğrulanır
  (``lisans.py``). Polar'a bağlı değildir; imzasız üretilemez.
* Diğer biçimler (Polar'ın ürettiği anahtar, ör. ``RN1_UUID…``) — yalnızca
  Polar API ile doğrulanabilir; yerel imza denemesi yapılmaz.

Doğrulama akışı (Polar anahtarı):

1. Önbellek taze ise (``ONAY_TAZE`` içinde) ağ çağrılmadan ``True``.
2. Yoksa cihaz aktivasyonu (yoksa) + ``validate`` çağrısı.
3. Ağ hatasında **çevrimdışı lütuf**: son başarılı doğrulamanın üzerinden
   ``CEVRIM_DISI_GRACE`` geçmemişse çalışmaya devam edilir.
4. Polar ``404``/``400`` (iptal, süre dolu, aktivasyon uyuşmuyor) → ``False``.

Test modu (``lisans.test_mi()``) ve deneme modu (anahtar yok) bu akışa
girmez; ``ORG_ID`` tanımlı değilse RN1 kanalı gibi çevrimdışı kalır.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import lisans
from kok_yol import veri_kok

__all__ = [
    "POLAR_API", "ORG_ID", "ONAY_TAZE", "CEVRIM_DISI_GRACE",
    "ONAY_YOL", "sirket_id", "rn1_mi", "makine_etiketi",
    "etkinlestir", "dogrula", "iptal", "lisans_kontrol",
]

POLAR_API = "https://api.polar.sh/v1/customer-portal/license-keys"
ORG_ID = ""                     # Polar Dashboard → organizasyon UUID'si
ZAMAN_ASIMI = 10                # saniye
ONAY_TAZE = 7 * 24 * 3600       # bu kadar sürede bir online tazeleme
CEVRIM_DISI_GRACE = 30 * 24 * 3600   # son doğrulamadan sonra çevrimdışı izin

ONAY_YOL: Path | None = None    # testler buradan yeniden yönlendirir


# --------------------------------------------------------------------------
#  Yapılandırma / kimlik
# --------------------------------------------------------------------------
def sirket_id(config: dict | None = None) -> str:
    """Polar organizasyon kimliği: env → config → modül sabiti."""
    for aday in (os.environ.get("POLAR_ORG_ID"),
                 ((config or {}).get("ayarlar") or {}).get("polar_org_id"),
                 ORG_ID):
        if aday and str(aday).strip():
            return str(aday).strip()
    return ""


def rn1_mi(anahtar: str) -> bool:
    """Anahtar yerel Ed25519 (``RN1-…``) kanalına mı ait?"""
    return anahtar.strip().upper().startswith(f"{lisans.ANAHTAR_ONEK}-")


def makine_etiketi() -> str:
    """Kararlı, kısa cihaz etiketi (aktivasyon ``label`` alanı için).

    Windows'ta kayıt defterindeki ``MachineGuid`` (biçimlendirme/hostname
    değişse de sabit kalır); başka platformlarda MAC adresinden.
    """
    try:
        import winreg                                   # Windows
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography") as anahtar:
            guid, _ = winreg.QueryValueEx(anahtar, "MachineGuid")
        ham = str(guid)
    except Exception:                                   # noqa: BLE001
        ham = str(uuid.getnode())
    return "CIHAZ-" + hashlib.sha256(ham.encode("utf-8")).hexdigest()[:8].upper()


# --------------------------------------------------------------------------
#  HTTP — testlerin sahtelediği tek nokta
# --------------------------------------------------------------------------
def _post(yol: str, veri: dict) -> tuple[int, dict | None]:
    """``POST {POLAR_API}{yol}`` → ``(durum_kodu, gövde)``.

    ``0`` = ağ/bağlantı hatası (sunucuya ulaşılamadı).
    """
    ham = json.dumps(veri).encode("utf-8")
    istek = urllib.request.Request(
        POLAR_API + yol, data=ham, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "RakipFiyatBot"})
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            govde = yanit.read().decode("utf-8", "replace")
            return int(yanit.status), _json(govde)
    except urllib.error.HTTPError as hata:
        try:
            govde = hata.read().decode("utf-8", "replace")
        except OSError:
            govde = ""
        return int(hata.code), _json(govde)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None


def _json(metin: str) -> dict | None:
    if not metin.strip():
        return None
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError:
        return None
    return veri if isinstance(veri, dict) else None


# --------------------------------------------------------------------------
#  Polar uçları
# --------------------------------------------------------------------------
def etkinlestir(anahtar: str, org: str,
                etiket: str | None = None) -> tuple[str | None, str]:
    """Cihaz aktivasyonu → ``(activation_id, hata_mesajı)``.

    ``403`` = cihaz limiti dolu (Panalda ``limit_activations``).
    """
    kod, govde = _post("/activate", {
        "key": anahtar, "organization_id": org,
        "label": etiket or makine_etiketi()})
    if kod == 200 and isinstance(govde, dict) and govde.get("id"):
        return str(govde["id"]), ""
    if kod == 403:
        return None, "cihaz limiti doldu (Polar panelinden başka bir aktivasyonu kaldırın)"
    if kod == 404:
        return None, "Polar'da böyle bir lisans anahtarı yok"
    if kod == 0:
        return None, "ağ"
    return None, f"Polar hatası (HTTP {kod})"


def dogrula(anahtar: str, org: str,
            etkinlestirme: str | None = None) -> tuple[int, dict | None]:
    """``validate`` → ``(durum_kodu, gövde)``; ``404`` = geçersiz/iptal."""
    veri: dict = {"key": anahtar, "organization_id": org}
    if etkinlestirme:
        veri["activation_id"] = etkinlestirme
    return _post("/validate", veri)


def iptal(anahtar: str, org: str, etkinlestirme: str) -> int:
    """Aktivasyonu bırakır (0 = ağ hatası)."""
    kod, _ = _post("/deactivate", {
        "key": anahtar, "organization_id": org,
        "activation_id": etkinlestirme})
    return kod


# --------------------------------------------------------------------------
#  Önbellek (çevrimdışı lütuf)
# --------------------------------------------------------------------------
def _onay_yolu() -> Path:
    if ONAY_YOL is not None:
        return Path(ONAY_YOL)
    return veri_kok(__file__) / "data" / "polar_onay.json"


def _hash(anahtar: str) -> str:
    return hashlib.sha256(anahtar.strip().upper().encode("utf-8")).hexdigest()


def _onay_oku() -> dict:
    try:
        veri = json.loads(_onay_yolu().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _onay_yaz(anahtar: str, etkinlestirme: str, son_onay: float,
              durum: str) -> None:
    try:
        yol = _onay_yolu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps({
            "anahtar": _hash(anahtar), "etkinlestirme": etkinlestirme,
            "son_onay": son_onay, "durum": durum}, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass    # önbellek yazılamazsa online doğrulama yine çalışır


def _taze_mi(anahtar: str, onay: dict) -> bool:
    return (onay.get("anahtar") == _hash(anahtar)
            and onay.get("durum") == "gecerli"
            and isinstance(onay.get("son_onay"), (int, float))
            and 0 < time.time() - float(onay["son_onay"]) < ONAY_TAZE)


def _cevrimdisi_lutuf(anahtar: str, onay: dict, hata: str) -> tuple[bool, str]:
    """Ağ yoksa: son başarılı doğrulama yeterince tazeyse devam."""
    if (onay.get("anahtar") == _hash(anahtar)
            and onay.get("durum") == "gecerli"
            and isinstance(onay.get("son_onay"), (int, float))
            and 0 < time.time() - float(onay["son_onay"]) < CEVRIM_DISI_GRACE):
        return True, "çevrimdışı doğrulama (son Polar kontrolü taze)"
    return False, ("internet bağlantısı gerekli — "
                   f"Polar'a ulaşılamadı ({hata})")


# --------------------------------------------------------------------------
#  Ana kontrol
# --------------------------------------------------------------------------
def lisans_kontrol(config: dict | None = None,
                   zorla: bool = False) -> tuple[bool, str]:
    """``(geçerli, mesaj)`` — ``--lisans`` ve çalışma öncesi çağrılır.

    * Test modu / anahtar yok (deneme modu) → her zaman ``True``.
    * ``RN1-…`` anahtarı → yalnızca yerel Ed25519 imzası (Polar'a bakılmaz).
    * Diğer anahtarlar → Polar ``activate`` + ``validate`` (+ önbellek/lütuf).
    """
    if lisans.test_mi():
        return True, "test modu"
    anahtar = ((config or {}).get("lisans") or "").strip()
    if not anahtar:
        return True, "anahtar yok (deneme hakkı ayrıca sayılır)"
    if rn1_mi(anahtar):
        ok = lisans.anahtar_gecerli(anahtar)
        return ok, ("yerel imza geçerli" if ok
                    else "yerel imza doğrulanamadı (RN1 anahtarı geçersiz)")
    org = sirket_id(config)
    if not org:
        return False, ("Polar lisans doğrulaması yapılandırılmamış — "
                       "ayarlar.polar_org_id tanımlı değil")

    onay = _onay_oku()
    if not zorla and _taze_mi(anahtar, onay):
        return True, "Polar onayı önbellekte taze"

    etkinlestirme = str(onay.get("etkinlestirme") or "")
    if not etkinlestirme:
        eid, hata = etkinlestir(anahtar, org)
        if hata == "ağ":
            return _cevrimdisi_lutuf(anahtar, onay, hata)
        if eid is None:
            return False, hata
        etkinlestirme = eid
        _onay_yaz(anahtar, etkinlestirme, 0, "bekliyor")

    kod, _govde = dogrula(anahtar, org, etkinlestirme)
    if kod == 200:
        _onay_yaz(anahtar, etkinlestirme, time.time(), "gecerli")
        return True, "Polar doğrulandı"
    if kod in (400, 404):
        _onay_yaz(anahtar, etkinlestirme, 0, "gecersiz")
        return False, ("lisans geçersiz, iptal edilmiş veya süresi dolmuş "
                       "(Polar panelini kontrol edin)")
    if kod == 0:
        return _cevrimdisi_lutuf(anahtar, onay, "bağlantı yok")
    return False, f"Polar hatası (HTTP {kod})"
