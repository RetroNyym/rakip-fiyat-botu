"""Polar.sh webhook → otomatik lisans anahtarı teslimi (satıcı aracı).

Bu dosya **satıcıya** aittir, müşterilere dağıtılmaz (``paketle.py`` hariç
tutar). Ne yapar:

  1. Polar'dan gelen ``order.created`` webhook'unu **Standard Webhooks /
     Svix** imzasıyla doğrular (``POLAR_WEBHOOK_SECRET``).
  2. Doğrulanan sipariş için ``lisans_uret.py`` ile imzalı ``RN1-…`` anahtarı
     üretir ve ``data/lisans_kayitlari.json`` içine (sipariş id → anahtar)
     **bir kez** kaydeder — aynı sipariş tekrar gelirse aynı anahtar döner.
  3. SMTP tanımlıysa müşteriye e-posta ile gönderir; değilse anahtar
     ``GET /lisans?eposta=…`` ile sorgulanabilir (indirme sayfasına link).

Kullanım::

    set POLAR_WEBHOOK_SECRET=whsec_...          # Polar → Webhooks → secret
    python anahtar_servisi.py --port 8080        # http://127.0.0.1:8080
    python anahtar_servisi.py --kontrol          # kendi kendini sınar

Polar tarafı: Dashboard → Webhooks → endpoint ``https://<sunucu>/webhook``,
event ``order.created``, format **Raw**.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import smtplib
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import lisans_uret                                # satıcı makinesinde
except ImportError:                                   # CI / müşteri paketi
    lisans_uret = None                                # type: ignore[assignment]

# Türkçe Windows konsolu (cp1254) ✔/✖ karakterlerini basamaz → çıkış
# bozulmasın diye stdout/stderr baştan UTF-8'e alınır (rakip_takip.py gibi).
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        try:
            _akis.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                             # noqa: BLE001
            pass

VARSAYILAN_KAYIT = Path("data") / "lisans_kayitlari.json"
TOLERANS = 300            # imza zaman damgası toleransı (sn)
GIZLI_ORTAM = "POLAR_WEBHOOK_SECRET"

_kilit = threading.Lock()


# ---------------------------------------------------------------------------
#  Svix / Standard Webhooks imza doğrulama
# ---------------------------------------------------------------------------
def _gizli_bayt(secret: str) -> bytes:
    """``whsec_<base64>`` gizlisini HMAC anahtarına çevirir.

    Standard Webhooks'a göre gizli ``whsec_`` önekinden sonraki base64
    değerdir; base64 değilse olduğu gibi UTF-8 bayt olarak kullanılır.
    """
    s = (secret or "").strip()
    if s.startswith("whsec_"):
        s = s[len("whsec_"):]
    try:
        return base64.b64decode(s, validate=True)
    except Exception:                                 # noqa: BLE001
        return s.encode("utf-8")


def imza_dogrula(payload: bytes, basliklar: dict, secret: str,
                 tolerans: int = TOLERANS, simdi: int | None = None) -> bool:
    """Gelen webhook'un imzasını doğrular (ham bayt gerekli — JSON'a
    dokunmadan, ``{id}.{zaman}.{payload}`` HMAC-SHA256, base64).

    ``svix-signature`` birkaç ``v1,<base64>`` değerinden oluşabilir;
    herhangi biri eşleşirse doğrulanmış sayılır. Zaman damgası
    ``tolerans`` saniyeden eskiyse (yeniden oynatma saldırısı) reddedilir.
    """
    if not secret:
        return False
    sid = basliklar.get("svix-id") or basliklar.get("webhook-id")
    sts = basliklar.get("svix-timestamp") or basliklar.get("webhook-timestamp")
    ssg = basliklar.get("svix-signature") or basliklar.get("webhook-signature")
    if not (sid and sts and ssg):
        return False
    try:
        damga = int(sts)
    except (TypeError, ValueError):
        return False
    simdi = int(time.time()) if simdi is None else int(simdi)
    if abs(simdi - damga) > tolerans:
        return False
    taban = _gizli_bayt(secret)
    mesaj = f"{sid}.{sts}.".encode("utf-8") + payload
    beklenen = base64.b64encode(
        hmac.new(taban, mesaj, hashlib.sha256).digest()).decode("ascii")
    for aday in str(ssg).split():
        if aday.startswith("v1,") and hmac.compare_digest(
                aday[len("v1,"):], beklenen):
            return True
    return False


def imza_uret(payload: bytes, sid: str, simdi: int, secret: str) -> dict:
    """(test aracı) Polar'ın göndereceği başlıkları üretir."""
    taban = _gizli_bayt(secret)
    mesaj = f"{sid}.{simdi}.".encode("utf-8") + payload
    imza = base64.b64encode(
        hmac.new(taban, mesaj, hashlib.sha256).digest()).decode("ascii")
    return {"svix-id": sid, "svix-timestamp": str(simdi),
            "svix-signature": f"v1,{imza}"}


# ---------------------------------------------------------------------------
#  Sipariş işleme
# ---------------------------------------------------------------------------
def eposta_cikar(event: dict) -> str | None:
    """Webhook gövdesinden müşteri e-postasını bulur."""
    data = event.get("data") if isinstance(event, dict) else None
    if not isinstance(data, dict):
        return None
    yollar = (("email",), ("billing_email",), ("customer_email",),
              ("customer", "email"), ("customer", "billing_email"),
              ("checkout", "email"), ("checkout", "customer_email"))
    for yol in yollar:
        deger = data
        for parca in yol:
            deger = deger.get(parca) if isinstance(deger, dict) else None
            if deger is None:
                break
        if isinstance(deger, str) and "@" in deger:
            return deger.strip().lower()
    return None


def kayitlari_oku(yol: Path) -> dict:
    if not yol.exists():
        return {}
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return veri if isinstance(veri, dict) else {}


def kayit_yaz(yol: Path, kayitlar: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(yol.suffix + ".tmp")
    gecici.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    gecici.replace(yol)


def siparis_isle(event: dict, yol: Path = VARSAYILAN_KAYIT) -> tuple[str, dict]:
    """``order.created`` olayını işler → ``(durum, detay)``.

    Durumlar: ``yeni`` (anahtar üretildi), ``mevcut`` (aynı sipariş, aynı
    anahtar — webhook idempotent), ``atlandi`` (olay türü başka),
    ``hata`` (sipariş id yok).
    """
    if lisans_uret is None:
        return "hata", {"sebep": "lisans_uret_yok"}
    tip = str(event.get("type") or "")
    if tip and not tip.startswith("order."):
        return "atlandi", {"type": tip}
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    siparis_id = data.get("id") or data.get("order_id")
    if not siparis_id:
        return "hata", {"sebep": "siparis_id_yok"}
    with _kilit:
        kayitlar = kayitlari_oku(yol)
        mevcut = kayitlar.get(str(siparis_id))
        if isinstance(mevcut, dict) and mevcut.get("anahtar"):
            return "mevcut", mevcut
        anahtar = lisans_uret.anahtar_uret()
        kayit = {
            "siparis_id": str(siparis_id),
            "eposta": eposta_cikar(event),
            "anahtar": anahtar,
            "tutar": data.get("amount"),
            "para_birimi": data.get("currency"),
            "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        kayitlar[str(siparis_id)] = kayit
        kayit_yaz(yol, kayitlar)
    return "yeni", kayit


def anahtar_bul(yol: Path, eposta: str) -> list[dict]:
    """E-postaya ait tüm anahtarları döndürür (küçük harfe indirgenmiş)."""
    hedef = (eposta or "").strip().lower()
    if not hedef:
        return []
    with _kilit:
        kayitlar = kayitlari_oku(yol)
    return [k for k in kayitlar.values()
            if isinstance(k, dict) and (k.get("eposta") or "").lower() == hedef]


# ---------------------------------------------------------------------------
#  E-posta teslimi (opsiyonel — SMTP_* ortam değişkenleriyle)
# ---------------------------------------------------------------------------
def eposta_gonder(kayit: dict, sunucu: str = "http://127.0.0.1:8080") -> bool:
    """SMTP tanımlıysa anahtarı müşteriye yollar; yoksa sessizce ``False``."""
    host = os.environ.get("SMTP_HOST")
    if not host or not kayit.get("eposta"):
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    kullanici = os.environ.get("SMTP_USER", "")
    parola = os.environ.get("SMTP_PASS", "")
    gonderen = os.environ.get("MAIL_FROM", kullanici or "noreply@example.com")
    anahtar = kayit.get("anahtar", "")
    eposta = EmailMessage()
    eposta["From"] = gonderen
    eposta["To"] = kayit["eposta"]
    eposta["Subject"] = "Rakip Fiyat Takip Botu — lisans anahtarınız"
    eposta.set_content(
        "Merhaba,\n\n"
        "Rakip Fiyat Takip Botu'nu satın aldığınız için teşekkürler.\n\n"
        f"Lisans anahtarınız:\n\n    {anahtar}\n\n"
        "Kullanım:\n"
        "  • Komut satırı:  python rakip_takip.py --lisans ANAHTAR\n"
        "  • Arayüz:  Araçlar → Lisans…\n"
        "Anahtarınız ayrıca sipariş e-postanızla bu adresten de sorgulanır:\n"
        f"    {sunucu.rstrip('/')}/lisans?eposta={kayit['eposta']}\n\n"
        "İyi çalışmalar.\n"
    )
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            if kullanici:
                s.login(kullanici, parola)
            s.send_message(eposta)
        return True
    except Exception:                                 # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
#  HTTP sunucusu (stdlib — ek bağımlılık yok)
# ---------------------------------------------------------------------------
def _handler_yap(secret: str, kayit_yolu: Path, sunucu: str,
                 eposta_acik: bool):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):            # gürültüsüz
            pass

        def _cevap(self, kod: int, govde: dict | str) -> None:
            if isinstance(govde, dict):
                metin = json.dumps(govde, ensure_ascii=False)
                icerik = "application/json; charset=utf-8"
            else:
                metin = govde
                icerik = "text/plain; charset=utf-8"
            bayt = metin.encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", icerik)
            self.send_header("Content-Length", str(len(bayt)))
            self.end_headers()
            self.wfile.write(bayt)

        def do_GET(self):                             # noqa: N802
            yol = urlparse(self.path)
            if yol.path == "/health":
                return self._cevap(200, {"durum": "ok"})
            if yol.path == "/lisans":
                eposta = (parse_qs(yol.query).get("eposta") or [""])[0]
                sonuclar = anahtar_bul(kayit_yolu, eposta)
                if not sonuclar:
                    return self._cevap(404, {"hata": "bulunamadi",
                                             "eposta": eposta})
                return self._cevap(200, {"anahtarlar": sonuclar})
            return self._cevap(404, {"hata": "yok"})

        def do_POST(self):                            # noqa: N802
            if urlparse(self.path).path != "/webhook":
                return self._cevap(404, {"hata": "yok"})
            try:
                uzunluk = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                uzunluk = 0
            payload = self.rfile.read(uzunluk) if uzunluk else b""
            basliklar = {k.lower(): v for k, v in self.headers.items()}
            if not imza_dogrula(payload, basliklar, secret):
                return self._cevap(403, {"hata": "imza_gecersiz"})
            try:
                olay = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return self._cevap(400, {"hata": "json_degil"})
            durum, detay = siparis_isle(olay, kayit_yolu)
            if durum == "hata":
                return self._cevap(400, {"durum": durum, "detay": detay})
            if durum == "yeni" and eposta_acik:
                eposta_gonder(detay, sunucu)
            return self._cevap(202, {"durum": durum, "detay": detay})

    return Handler


def sunucu_baslat(adres: str, port: int, secret: str, kayit_yolu: Path,
                 sunucu: str, eposta_acik: bool) -> ThreadingHTTPServer:
    handler = _handler_yap(secret, kayit_yolu, sunucu, eposta_acik)
    return ThreadingHTTPServer((adres, port), handler)


# ---------------------------------------------------------------------------
#  Kendi kendini sınama + CLI
# ---------------------------------------------------------------------------
def kendini_sina(secret: str) -> bool:
    """İmza üret→doğrula döngüsü ve ``lisans_uret`` kullanılabilirliği."""
    if lisans_uret is None:
        print("✖ lisans_uret.py yok (satıcı makinesinde çalıştırın)")
        return False
    gizli = secret or "whsec_" + base64.b64encode(
        b"deneme-gizli-anahtar").decode("ascii")
    payload = json.dumps({"type": "order.created",
                          "data": {"id": "ord_test", "email": "a@b.c"}},
                         ensure_ascii=False).encode("utf-8")
    simdi = int(time.time())
    basliklar = imza_uret(payload, "msg_test", simdi, gizli)
    if not imza_dogrula(payload, basliklar, gizli, simdi=simdi):
        print("✖ imza döngüsü başarısız")
        return False
    if imza_dogrula(payload + b" ", basliklar, gizli, simdi=simdi):
        print("✖ bozulmuş yük reddedilmedi")
        return False
    anahtar = lisans_uret.anahtar_uret()
    import lisans
    if not lisans.anahtar_gecerli(anahtar):
        print("✖ üretilen anahtar lisans.py ile doğrulanamadı")
        return False
    print("✔ imza döngüsü, hata reddi ve anahtar doğrulama tamam")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Polar webhook → otomatik lisans anahtarı")
    ap.add_argument("--adres", default="127.0.0.1", help="dinlenecek adres")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--kayit", default=str(VARSAYILAN_KAYIT),
                    help="sipariş→anahtar kayıt dosyası")
    ap.add_argument("--gizli", default=os.environ.get(GIZLI_ORTAM, ""),
                    help=f"webhook gizlisi (ortam: {GIZLI_ORTAM})")
    ap.add_argument("--sunucu", default=os.environ.get("SUNUCU_URL",
                                                        "http://127.0.0.1:8080"),
                    help="e-postadaki sorgu linki için dış adres")
    ap.add_argument("--eposta-yok", action="store_true",
                    help="SMTP ne tanımlı olsa bile e-posta gönderme")
    ap.add_argument("--kontrol", action="store_true",
                    help="sunucu açmadan kendi kendini sınaire")
    args = ap.parse_args(argv)

    if args.kontrol:
        return 0 if kendini_sina(args.gizli) else 1
    if not args.gizli:
        print(f"✖ {GIZLI_ORTAM} tanımlı değil — Polar webhook gizlisi gerekli")
        return 2
    if lisans_uret is None:
        print("✖ lisans_uret.py bulunamadı (yalnızca satıcı makinesinde)")
        return 2

    sunucu = sunucu_baslat(args.adres, args.port, args.gizli,
                           Path(args.kayit), args.sunucu,
                           not args.eposta_yok)
    print(f"▶ Polar webhook dinleniyor: http://{args.adres}:{args.port}/webhook")
    print(f"  kayıt: {args.kayit}")
    print(f"  sorgu: GET /lisans?eposta=...   sağlık: GET /health")
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\n■ durduruldu")
    finally:
        sunucu.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
