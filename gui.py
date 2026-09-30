#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui.py — Rakip Fiyat Takip Botu · Grafik Arayüz
================================================

rakip_takip.py çekirdeği üzerine kurulu tam kapsamlı masaüstü arayüz.

Özellikler
----------
* Ürün listesi + anlık arama/filtre
* Ürün ekle / düzenle / sil / dışa aktar (CSV, JSON)
* "Seçici Bul" — fiyatın CSS seçicisini otomatik keşfeder
* Tek tarama / seçili ürünleri tara / durdur
* Canlı ilerleme çubuğu ve renkli sonuç tablosu
* Fiyat geçmişi tablosu + grafik (matplotlib)
* Özet rapor: en düşük/yüksek, toplam değişim, CSV dışa aktarma
* Alt panel: konsol (log) + görsel önizleme (ürün görselini getirir)
* Ayarlar: Telegram, bekleme süresi, uyarı eşiği
* Görev zamanlayıcıya tek tıkla kayıt (.bat oluşturur)

Çalıştırma:  python gui.py
"""

from __future__ import annotations

import csv
import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from tkinter import (
    BOTH, END, LEFT, RIGHT, X, Y, BOTTOM, TOP, W, E, N, S, CENTER,
    BooleanVar, DoubleVar, IntVar, StringVar, TclError,
)
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import tkinter as tk
except ImportError:
    print("Tkinter bulunamadı. Python'un GUI bileşeni kurulu değil.")
    sys.exit(1)

# --- görsel / grafik (opsiyonel) -----------------------------------------
try:
    from PIL import Image, ImageTk
    PIL_VAR = True
except ImportError:
    PIL_VAR = False

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MPL_VAR = True
except ImportError:
    MPL_VAR = False

import rakip_takip as cekirdek


# ==========================================================================
#  Rakip Radar (pazaryeri-radar) yardımcıları
# ==========================================================================
def radar_kok_bul() -> Path:
    """pazaryeri-radar proje kökünü bulur (yanında ya da üst klasörde)."""
    kendi = Path(__file__).resolve().parent
    for taban in (kendi, kendi.parent):
        aday = taban / "pazaryeri-radar"
        if (aday / "radar").is_dir():
            return aday
    return kendi / "pazaryeri-radar"


def radar_python_bul(kok: Path) -> Path:
    """Radar'ın kendi venv Python'u (curl_cffi/playwright orada kurulu)."""
    for aday in (kok / ".venv" / "Scripts" / "python.exe",
                 kok / ".venv" / "bin" / "python"):
        if aday.exists():
            return aday
    return Path(sys.executable)


def ithalat_kok_bul() -> Path:
    """ithalat-radar proje kökünü bulur (yanında ya da üst klasörde)."""
    kendi = Path(__file__).resolve().parent
    for taban in (kendi, kendi.parent):
        aday = taban / "ithalat-radar"
        if (aday / "ithalat").is_dir():
            return aday
    return kendi / "ithalat-radar"


# ==========================================================================
#  Stil — FiyatAvcısı tarzı karanlık tema (lacivert + camgöbeği vurgu)
# ==========================================================================
RENKLER = {
    "arka":        "#0a0f1c",   # pencere arka planı
    "panel":       "#0f1729",   # panel / diyalog arka planı
    "kart":        "#111c33",   # canlı panel ürün kartları
    "koyu":        "#0d1526",   # alan (entry/treeview) arka planı
    "baslik":      "#e8eefc",   # başlık yazısı
    "metin":       "#9db0d0",   # normal yazı
    "vurgu":       "#22d3ee",   # camgöbeği vurgu
    "vurgu_koyu":  "#0e7490",
    "yesil":       "#34d399",
    "kirmizi":     "#f87171",
    "sari":        "#fbbf24",
    "mor":         "#818cf8",
    "gri":         "#6b7c9c",
    "kenar":       "#22304f",   # kenarlık / çizgi
    "buton":       "#1b2740",   # normal buton
    "buton_act":   "#27365a",
    "baslik_bant": "#0c1424",   # başlık/alt bant
}

# Rozet (rozet) renkleri — kart rozetleri ve durum satırları için
ROZET = {
    "yesil": ("#0b2b22", "#34d399"),   # fiyat düştü / sorunsuz
    "kirmizi": ("#3b1113", "#fca5a5"),  # fiyat arttı
    "cyan": ("#0b3a47", "#67e8f9"),     # sabit fiyat
    "sari": ("#3a2c0b", "#fcd34d"),     # alarm / fiyat yok
    "gri": ("#1b2436", "#94a3b8"),      # beklemede
    "mor": ("#1e1b4b", "#a5b4fc"),      # ilk kayıt
}

STIL = """
.TTk.TFrame { background: %(arka)s; }
.TPanel.TFrame { background: %(panel)s; }
.TLabel { background: %(arka)s; foreground: %(metin)s;
          font: ("Segoe UI", 10); }
.TButton { font: ("Segoe UI", 9, "bold"); padding: 6 6; }
.TNotebook { background: %(arka)s; borderwidth: 0; }
.TNotebook.Tab { font: ("Segoe UI", 9, "bold"); padding: 10 6; }
.Treeview { font: ("Segoe UI", 10); rowheight: 25; }
.Treeview.Heading { font: ("Segoe UI", 9, "bold"); }
.Status.TLabel { background: %(baslik_bant)s; foreground: %(metin)s;
                 font: ("Segoe UI", 9); padding: 6 6; }
""" % RENKLER

# --- sol panel alan seçenekleri ------------------------------------------
URL_IPUCU = "Ürün adı yazın (örn. iphone 15) veya ürün linki yapıştırın"

# Arama sonuçlarında görünen site adları
SITE_ETIKET = {"trendyol": "Trendyol", "hepsiburada": "Hepsiburada",
               "n11": "N11", "amazon": "Amazon"}
PERIYOT_DEGERLER = ["Tek Seferlik Tarama", "5 Dakikada Bir",
                    "15 Dakikada Bir", "30 Dakikada Bir",
                    "60 Dakikada Bir"]
PERIYOT_DAKIKA = [0, 5, 15, 30, 60]
ESIK_DEGERLER = ["Her Fiyat Değişimde", "%2 Üzeri Değişimde",
                 "%5 Üzeri Değişimde", "%10 Üzeri Değişimde"]
ESIK_YUZDE = [0.0, 2.0, 5.0, 10.0]
BILDIRIM_DEGERLER = ["Telegram & Konsol", "Sadece Konsol"]
BILDIRIM_ANAHTAR = ["telegram", "konsol"]


def _indeks(degerler: list, deger, varsayilan: int = 0) -> int:
    """Listede degeri bulur; yoksa varsayilan indeksi döndürür."""
    try:
        return degerler.index(deger)
    except ValueError:
        return varsayilan


# ==========================================================================
#  Yardımcılar
# ==========================================================================
def para_mi(deger) -> bool:
    return deger is not None and deger != ""


def _sayi(deger) -> str:
    """1234567 -> '1.234.567'; None -> '-' (Türkçe binlik ayracı)."""
    if deger is None or deger == "":
        return "-"
    try:
        return f"{float(deger):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(deger)


class KuyrukYazici:
    """Arka plandaki thread'lerin GUI'ye güvenli yazması için kuyruk."""

    def __init__(self, kuyruk: "queue.Queue[str]", on_etiket=None):
        self.kuyruk = kuyruk
        self.on_etiket = on_etiket

    def __call__(self, metin: str) -> None:
        self.kuyruk.put(metin)


class Ipucu:
    """Widget üstüne gelince kısa açıklama balonu gösterir.

    Bir kez bağlanır; `<Enter>` sonrası kısa gecikmeyle açılır,
    `<Leave>`/tıklamada kaybolur.
    """

    def __init__(self, widget, metin: str, gecikme: int = 350):
        self.widget = widget
        self.metin = metin
        self.gecikme = gecikme
        self._pencere = None
        self._zaman = None
        widget.bind("<Enter>", self._planla, add="+")
        widget.bind("<Leave>", self._gizle, add="+")
        widget.bind("<ButtonPress>", self._gizle, add="+")

    def _planla(self, _olay=None):
        self._iptal()
        try:
            self._zaman = self.widget.after(self.gecikme, self._goster)
        except Exception:            # noqa: BLE001 — pencere kapanmış olabilir
            self._zaman = None

    def _iptal(self):
        if self._zaman is not None:
            try:
                self.widget.after_cancel(self._zaman)
            except Exception:        # noqa: BLE001
                pass
            self._zaman = None

    def _goster(self):
        self._zaman = None
        if not self.widget.winfo_exists():
            return
        self._gizle_pencere()
        w = tk.Toplevel(self.widget)
        w.wm_overrideredirect(True)
        try:
            w.attributes("-topmost", True)
        except Exception:            # noqa: BLE001
            pass
        tk.Label(w, text=self.metin, justify="left", wraplength=270,
                 bg=RENKLER["koyu"], fg=RENKLER["baslik"],
                 font=("Segoe UI", 9), padx=8, pady=5,
                 highlightthickness=1,
                 highlightbackground=RENKLER["vurgu"]).pack()
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        w.geometry(f"+{x}+{y}")
        self._pencere = w

    def _gizle_pencere(self):
        if self._pencere is not None:
            try:
                self._pencere.destroy()
            except Exception:        # noqa: BLE001
                pass
            self._pencere = None

    def _gizle(self, _olay=None):
        self._iptal()
        self._gizle_pencere()


# ==========================================================================
#  Ürün ekleme / düzenleme diyalogu
# ==========================================================================
class UrunPenceresi(tk.Toplevel):
    def __init__(self, ebeveyn, baslik: str, veri: dict | None = None):
        super().__init__(ebeveyn)
        self.title(baslik)
        self.resizable(False, False)
        self.configure(bg=RENKLER["arka"])
        self.transient(ebeveyn)
        self.grab_set()
        self.sonuc: dict | None = None

        govde = ttk.Frame(self, style="TPanel.TFrame", padding=16)
        govde.pack(fill=BOTH, expand=True)

        self.alanlar: dict[str, tk.StringVar] = {}
        satirlar = [
            ("ad",      "Ürün adı",      (veri or {}).get("ad", "")),
            ("url",     "Ürün URL'si",   (veri or {}).get("url", "")),
            ("selector","CSS seçici",    (veri or {}).get("selector", "")),
            ("not",     "Not (opsiyonel)",(veri or {}).get("not", "")),
        ]

        for i, (anahtar, etiket, deger) in enumerate(satirlar):
            ttk.Label(govde, text=etiket + ":").grid(
                row=i, column=0, sticky=W, pady=5, padx=(0, 10))
            degisken = StringVar(value=deger)
            girdi = ttk.Entry(govde, textvariable=degisken, width=58)
            girdi.grid(row=i, column=1, sticky=(W, E), pady=5)
            self.alanlar[anahtar] = degisken

        ipucu = ("Fiyatın bulunduğu HTML elementi. Boş bırakırsanız bot "
                 "sayfayı tarar ve para birimli ilk adayı seçer.")
        ttk.Label(govde, text=ipucu, foreground=RENKLER["gri"],
                  wraplength=480).grid(row=len(satirlar), column=0,
                                       columnspan=2, sticky=W, pady=(8, 0))

        dugme = ttk.Frame(govde, style="TPanel.TFrame")
        dugme.grid(row=len(satirlar) + 1, column=0, columnspan=2,
                   pady=(16, 0), sticky=E)
        ttk.Button(dugme, text="Vazgeç", command=self.destroy).pack(
            side=LEFT, padx=(0, 8))
        ttk.Button(dugme, text="Kaydet", command=self._kaydet).pack(side=LEFT)

        self.bind("<Return>", lambda e: self._kaydet())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_visibility()
        self.center()

    def center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2 - 40
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _kaydet(self):
        ad = self.alanlar["ad"].get().strip()
        url = self.alanlar["url"].get().strip()
        if not ad:
            messagebox.showwarning("Eksik alan", "Ürün adı gerekli.", parent=self)
            return
        if not url:
            messagebox.showwarning("Eksik alan", "URL gerekli.", parent=self)
            return
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("Geçersiz URL",
                                   "URL http:// veya https:// ile başlamalı.",
                                   parent=self)
            return
        self.sonuc = {
            "ad": ad,
            "url": url,
            "selector": self.alanlar["selector"].get().strip(),
            "not": self.alanlar["not"].get().strip(),
        }
        self.destroy()


# ==========================================================================
#  Ayarlar penceresi
# ==========================================================================
class AyarlarPenceresi(tk.Toplevel):
    def __init__(self, ebeveyn, ayarlar: dict):
        super().__init__(ebeveyn)
        self.title("Ayarlar")
        self.resizable(False, False)
        self.configure(bg=RENKLER["arka"])
        self.transient(ebeveyn)
        self.grab_set()
        self.sonuc: dict | None = None

        govde = ttk.Frame(self, style="TPanel.TFrame", padding=16)
        govde.pack(fill=BOTH, expand=True)

        ttk.Label(govde, text="Telegram").grid(
            row=0, column=0, columnspan=2, sticky=W, pady=(0, 6))

        self.token = StringVar(value=ayarlar.get("telegram_token", ""))
        self.chat = StringVar(value=ayarlar.get("telegram_chat_id", ""))

        ttk.Label(govde, text="Bot token:").grid(row=1, column=0, sticky=W,
                                                 pady=5, padx=(0, 10))
        ttk.Entry(govde, textvariable=self.token, width=52).grid(
            row=1, column=1, sticky=(W, E), pady=5)

        ttk.Label(govde, text="Chat ID:").grid(row=2, column=0, sticky=W,
                                               pady=5, padx=(0, 10))
        ttk.Entry(govde, textvariable=self.chat, width=52).grid(
            row=2, column=1, sticky=(W, E), pady=5)

        ttk.Separator(govde).grid(row=3, column=0, columnspan=2,
                                  sticky=(W, E), pady=12)

        ttk.Label(govde, text="Tarama").grid(
            row=4, column=0, columnspan=2, sticky=W, pady=(0, 6))

        self.bekleme = DoubleVar(value=float(ayarlar.get("bekleme_saniye", 3)))
        self.esik = DoubleVar(value=float(ayarlar.get("esik_yuzde", 0)))

        ttk.Label(govde, text="İstekler arası bekleme (sn):").grid(
            row=5, column=0, sticky=W, pady=5, padx=(0, 10))
        ttk.Spinbox(govde, from_=1, to=30, increment=1, width=8,
                    textvariable=self.bekleme).grid(row=5, column=1,
                                                    sticky=W, pady=5)

        ttk.Label(govde, text="Uyarı eşiği (%):").grid(
            row=6, column=0, sticky=W, pady=5, padx=(0, 10))
        ttk.Spinbox(govde, from_=0, to=100, increment=1, width=8,
                    textvariable=self.esik).grid(row=6, column=1,
                                                 sticky=W, pady=5)
        ttk.Label(govde, text="0 = her değişiklikte uyarı verilir.",
                  foreground=RENKLER["gri"]).grid(row=7, column=0,
                                                  columnspan=2, sticky=W)

        ttk.Separator(govde).grid(row=8, column=0, columnspan=2,
                                  sticky=(W, E), pady=12)
        ttk.Label(govde, text="Telegram kurulumu: BotFather'dan token alın, "
                              "@userinfobot'a yazıp chat ID öğrenin.",
                  foreground=RENKLER["gri"], wraplength=460).grid(
            row=9, column=0, columnspan=2, sticky=W)

        dugme = ttk.Frame(govde, style="TPanel.TFrame")
        dugme.grid(row=10, column=0, columnspan=2, pady=(16, 0), sticky=E)
        ttk.Button(dugme, text="Vazgeç", command=self.destroy).pack(
            side=LEFT, padx=(0, 8))
        ttk.Button(dugme, text="Kaydet", command=self._kaydet).pack(side=LEFT)

        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_visibility()
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{(self.winfo_screenwidth() - w) // 2}+"
                      f"{max((self.winfo_screenheight() - h) // 2 - 40, 0)}")

    def _kaydet(self):
        self.sonuc = {
            "telegram_token": self.token.get().strip(),
            "telegram_chat_id": self.chat.get().strip(),
            "bekleme_saniye": max(1.0, float(self.bekleme.get())),
            "esik_yuzde": max(0.0, float(self.esik.get())),
        }
        self.destroy()


# ==========================================================================
#  Seçici bulucu penceresi
# ==========================================================================
class SeciciPenceresi(tk.Toplevel):
    """URL girilir → fiyat adayları listelenir → tıklayınca seçici seçilir."""

    def __init__(self, ebeveyn, url: str, yazici, is_bitir):
        super().__init__(ebeveyn)
        self.title("Seçici Bul — fiyatın CSS seçicisini keşfet")
        self.geometry("760x520")
        self.minsize(620, 400)
        self.configure(bg=RENKLER["arka"])
        self.transient(ebeveyn)
        self.secilen: str | None = None
        self._yazici = yazici
        self._is_bitir = is_bitir

        ust = ttk.Frame(self, style="TPanel.TFrame", padding=12)
        ust.pack(fill=X)

        ttk.Label(ust, text="URL:").pack(side=LEFT, padx=(0, 8))
        self.url_deg = StringVar(value=url)
        ttk.Entry(ust, textvariable=self.url_deg).pack(
            side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.tara_btn = ttk.Button(ust, text="Adayları Bul",
                                   command=self._baslat)
        self.tara_btn.pack(side=LEFT)

        kolonlar = ("fiyat", "secici", "metin")
        self.agac = ttk.Treeview(self, columns=kolonlar, show="headings",
                                 height=14)
        for kol, gen, hiza in (("fiyat", 130, E), ("secici", 240, W),
                               ("metin", 300, W)):
            self.agac.heading(kol, text=kol.upper() if kol == "fiyat" else kol)
            self.agac.column(kol, width=gen, anchor=hiza)

        kaydir = ttk.Scrollbar(self, orient="vertical", command=self.agac.yview)
        self.agac.configure(yscrollcommand=kaydir.set)
        self.agac.pack(side=TOP, fill=BOTH, expand=True, padx=12)
        kaydir.place(relx=1.0, rely=0.13, relheight=0.72, anchor="ne")

        alt = ttk.Frame(self, style="TPanel.TFrame", padding=12)
        alt.pack(fill=X)
        self.durum = StringVar(value="Bir URL girip 'Adayları Bul' deyin.")
        ttk.Label(alt, textvariable=self.durum).pack(side=LEFT)

        ttk.Button(alt, text="Kapat", command=self.destroy).pack(
            side=RIGHT, padx=(8, 0))
        ttk.Button(alt, text="Bu Seçiciyi Kullan", command=self._sec).pack(
            side=RIGHT)

        self.agac.bind("<Double-1>", lambda e: self._sec())
        self.bind("<Escape>", lambda e: self.destroy())

    def _baslat(self):
        url = self.url_deg.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("Geçersiz URL",
                                   "http:// veya https:// ile başlayın.",
                                   parent=self)
            return
        self.tara_btn.state(["disabled"])
        self.durum.set("Sayfa indiriliyor…")
        self.agac.delete(*self.agac.get_children())

        def is_calistir():
            try:
                sonuclar = cekirdek.secici_bul(url, log=self._yazici)
            except Exception as hata:
                sonuclar = []
                self._yazici(f"[!] {hata}")
            # kuyruk üzerindeki islev(veri) imzasıyla uyumlu olsun
            self._is_bitir(lambda _v=None: self._doldur(sonuclar))

        threading.Thread(target=is_calistir, daemon=True).start()

    def _doldur(self, sonuclar: list[dict]):
        try:
            self.tara_btn.state(["!disabled"])
        except TclError:
            return
        for s in sonuclar:
            fiyat = cekirdek.fiyat_bicimle(s["fiyat"], s["para"])
            self.agac.insert("", END, values=(fiyat, s["secici"], s["metin"]))
        self.durum.set(f"{len(sonuclar)} aday bulundu. "
                       f"Çift tıklayarak seçin." if sonuclar
                       else "Aday bulunamadı. Sayfa JS ile yükleniyor olabilir.")

    def _sec(self):
        secim = self.agac.selection()
        if not secim:
            messagebox.showinfo("Seçim yok", "Listeden bir satır seçin.",
                                parent=self)
            return
        self.secilen = self.agac.item(secim[0], "values")[1]
        self.destroy()


# ==========================================================================
#  Ana uygulama
# ==========================================================================
class Uygulama(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fiyat Takip Botu — Pazaryeri Rakip Fiyat Takip")
        self.geometry("1340x900")
        self.minsize(1080, 850)
        self.configure(bg=RENKLER["arka"])

        # --- durum ---
        self.app_yolu = cekirdek.VARSAYILAN_CONFIG
        self.ayar = self._config_yukle()
        self.tarama_suriyor = False
        self.otomatik_takip = False          # büyük başlat/durdur butonu
        self._periyot_zamanlayici = None     # after() kimliği
        self.iptal_bayragi = threading.Event()
        self.kuyruk: "queue.Queue[str]" = queue.Queue()
        self.gorsel_ref = None          # PhotoImage referansı (GC'ye karşı)
        self.grafik_canvas = None
        self.son_tarama: list[dict] = []
        # --- rakip radar ---
        self.radar_surec = None          # subprocess.Popen
        self.radar_suriyor = False
        self.radar_iptal = False
        self.radar_sonuc: dict | None = None
        self.gorsel_gosteriliyor = False

        # --- stil (karanlık tema) ---
        self.stil = ttk.Style(self)
        try:
            self.stil.theme_use("clam")
        except TclError:
            pass
        self._stil_kur()

        self._menu_kur()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._baslik_cubugu()
        self._govde()
        self._durum_cubugu()

        self.liste_doldur()
        self._alanlari_yukle()
        self._kuyruk_isle()
        self.protocol("WM_DELETE_WINDOW", self._kapat)

    def _stil_kur(self) -> None:
        """ttk stillerini karanlık palete göre yapılandırır."""
        r = RENKLER
        s = self.stil
        s.configure(".", font=("Segoe UI", 10), background=r["arka"],
                    foreground=r["metin"])
        s.configure("TFrame", background=r["arka"])
        s.configure("TPanel.TFrame", background=r["panel"])
        s.configure("TLabel", background=r["arka"], foreground=r["metin"],
                    font=("Segoe UI", 10))
        s.configure("TPanel.TLabel", background=r["panel"],
                    foreground=r["metin"])
        s.configure("Alan.TLabel", background=r["arka"], foreground=r["gri"],
                    font=("Segoe UI", 8, "bold"))
        s.configure("TButton", background=r["buton"], foreground=r["baslik"],
                    bordercolor=r["kenar"], focusthickness=1,
                    focuscolor=r["vurgu"], padding=(10, 5),
                    font=("Segoe UI", 9, "bold"))
        s.map("TButton",
              background=[("active", r["buton_act"]), ("disabled", "#141d31")],
              foreground=[("disabled", "#4b5a78")])
        s.configure("Baslat.TButton", background=r["vurgu"],
                    foreground="#06121f", bordercolor=r["vurgu"],
                    font=("Segoe UI", 11, "bold"), padding=(16, 10))
        s.map("Baslat.TButton", background=[("active", "#67e8f9"),
                                            ("disabled", "#123c4a")],
              foreground=[("disabled", "#3e6b77")])
        s.configure("Durdur.TButton", background="#7f1d1d",
                    foreground="#fecaca", bordercolor="#991b1b",
                    font=("Segoe UI", 11, "bold"), padding=(16, 10))
        s.map("Durdur.TButton", background=[("active", "#991b1b")])
        s.configure("TEntry", fieldbackground=r["koyu"],
                    foreground=r["baslik"], insertcolor=r["baslik"],
                    bordercolor=r["kenar"], lightcolor=r["kenar"],
                    padding=6, font=("Segoe UI", 10))
        s.configure("TSpinbox", fieldbackground=r["koyu"],
                    foreground=r["baslik"], arrowcolor=r["vurgu"],
                    bordercolor=r["kenar"], padding=4)
        s.configure("TCombobox", fieldbackground=r["koyu"],
                    background=r["buton"], foreground=r["baslik"],
                    arrowcolor=r["vurgu"], bordercolor=r["kenar"],
                    padding=3, font=("Segoe UI", 10, "bold"))
        s.map("TCombobox",
              fieldbackground=[("readonly", r["koyu"])],
              foreground=[("readonly", r["baslik"])],
              selectbackground=[("readonly", r["koyu"])],
              selectforeground=[("readonly", r["baslik"])])
        s.configure("TCheckbutton", background=r["arka"],
                    foreground=r["metin"], font=("Segoe UI", 9))
        s.map("TCheckbutton", background=[("active", r["arka"])])
        s.configure("Treeview", background=r["koyu"],
                    fieldbackground=r["koyu"], foreground=r["metin"],
                    rowheight=25, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background="#16213c",
                    foreground=r["baslik"], relief="flat",
                    padding=6, font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", "#155e75")],
              foreground=[("selected", "#ffffff")])
        s.configure("TNotebook", background=r["arka"], borderwidth=0)
        s.configure("TNotebook.Tab", background=r["panel"],
                    foreground=r["gri"], padding=(12, 6),
                    font=("Segoe UI", 9, "bold"), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", r["vurgu"])],
              foreground=[("selected", "#06121f")])
        s.configure("TScrollbar", background=r["buton"],
                    troughcolor=r["koyu"], bordercolor=r["arka"],
                    arrowcolor=r["metin"], borderwidth=0)
        s.map("TScrollbar", background=[("active", r["buton_act"])])
        s.configure("TProgressbar", troughcolor=r["koyu"],
                    background=r["vurgu"], bordercolor=r["koyu"],
                    lightcolor=r["vurgu"], darkcolor=r["vurgu"])
        s.configure("TSeparator", background=r["kenar"])
        s.configure("TLabelframe", background=r["panel"],
                    bordercolor=r["kenar"])
        s.configure("TLabelframe.Label", background=r["panel"],
                    foreground=r["vurgu"], font=("Segoe UI", 10, "bold"))
        s.configure("Status.TLabel", background=r["baslik_bant"],
                    foreground=r["metin"], font=("Segoe UI", 9), padding=(6, 5))

    @staticmethod
    def _combobox_karanlik(kutu) -> None:
        """Açılır listeyi (dropdown) karanlık temaya çevirir."""
        try:
            p = kutu.tk.eval("ttk::combobox::PopdownWindow %s" % kutu)
            kutu.tk.eval(
                f"{p} configure -background {RENKLER['koyu']} "
                f"-foreground {RENKLER['baslik']} "
                f"-selectbackground {RENKLER['vurgu']} "
                f"-selectforeground #06121f")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    #  Kurulum
    # ------------------------------------------------------------------
    def _config_yukle(self) -> dict:
        try:
            return cekirdek.config_oku(self.app_yolu)
        except Exception:
            return {"ayarlar": {"bekleme_saniye": 3, "esik_yuzde": 0,
                                "telegram_token": "", "telegram_chat_id": ""},
                    "urunler": []}

    def _config_kaydet(self) -> None:
        try:
            cekirdek.config_kaydet(self.ayar, self.app_yolu)
        except Exception as hata:
            messagebox.showerror("Kayıt hatası", f"Config kaydedilemedi:\n{hata}")

    def _menu_yap(self, ebeveyn=None) -> tk.Menu:
        """Karanlık temalı menü üretir."""
        return tk.Menu(ebeveyn or self, tearoff=0,
                       bg=RENKLER["panel"], fg=RENKLER["baslik"],
                       activebackground=RENKLER["vurgu"],
                       activeforeground="#06121f",
                       font=("Segoe UI", 9), borderwidth=1,
                       relief="flat")

    def _menu_kur(self):
        menu = self._menu_yap()

        dosya = self._menu_yap(menu)
        dosya.add_command(label="Config Aç…", command=self._config_ac,
                          accelerator="Ctrl+O")
        dosya.add_command(label="Config Farklı Kaydet…",
                          command=self._config_farkli_kaydet)
        dosya.add_separator()
        dosya.add_command(label="Ürün Listesini CSV Aktar…",
                          command=lambda: self._csv_aktar("urunler"))
        dosya.add_command(label="Tarama Sonuçlarını CSV Aktar…",
                          command=lambda: self._csv_aktar("sonuclar"))
        dosya.add_command(label="Raporu CSV Aktar…",
                          command=lambda: self._csv_aktar("rapor"))
        dosya.add_separator()
        dosya.add_command(label="Çıkış", command=self._kapat)
        menu.add_cascade(label="Dosya", menu=dosya)

        arac = self._menu_yap(menu)
        arac.add_command(label="Tümünü Tara", command=self.tarama_baslat,
                         accelerator="F5")
        arac.add_command(label="Seçili Ürünleri Tara",
                         command=lambda: self.tarama_baslat(secili=True),
                         accelerator="F6")
        arac.add_command(label="Durdur", command=self.tarama_durdur,
                         accelerator="Esc")
        arac.add_command(label="Radar Taraması", command=self.radar_baslat,
                         accelerator="F7")
        arac.add_command(label="Radar Sekmesine Git",
                         command=lambda: self.ust_sayfa.select(self.radar_sayfa))
        arac.add_command(label="Ürün Arama Sekmesine Git",
                         command=lambda: self.ust_sayfa.select(self.arama_sayfa))
        arac.add_command(label="İthalat Radarı'na Git",
                         command=lambda: self.ust_sayfa.select(self.ithalat_sayfa))
        arac.add_separator()
        arac.add_command(label="Seçici Bul…", command=self.secici_bul,
                         accelerator="Ctrl+F")
        arac.add_command(label="Telegram Testi", command=self.telegram_test)
        arac.add_command(label="Ayarlar…", command=self.ayarlar_ac,
                         accelerator="Ctrl+,")
        arac.add_separator()
        arac.add_command(label="Görev Zamanlayıcıya Ekle (Windows)",
                         command=self._zamanlayici_kur)
        arac.add_command(label="Config Klasörünü Aç", command=self._klasor_ac)
        menu.add_cascade(label="Araçlar", menu=arac)

        gorunum = self._menu_yap(menu)
        gorunum.add_command(label="Konsolu Temizle", command=self.konsol_temizle)
        gorunum.add_command(label="Fiyat Geçmişini Yenile",
                            command=self.gecmis_yenile)
        gorunum.add_command(label="Raporu Yenile", command=self.rapor_yenile)
        menu.add_cascade(label="Görünüm", menu=gorunum)

        yardim = self._menu_yap(menu)
        yardim.add_command(label="Hakkında", command=self._hakkinda)
        yardim.add_command(label="Kullanım Kılavuzu", command=self._kilavuz)
        menu.add_cascade(label="Yardım", menu=yardim)

        self.configure(menu=menu)

        # Kısayollar
        self.bind("<Control-o>", lambda e: self._config_ac())
        self.bind("<Control-comma>", lambda e: self.ayarlar_ac())
        self.bind("<Control-f>", lambda e: self.secici_bul())
        self.bind("<F5>", lambda e: self.tarama_baslat())
        self.bind("<F6>", lambda e: self.tarama_baslat(secili=True))
        self.bind("<Escape>", lambda e: self.tarama_durdur())
        self.bind("<F7>", lambda e: self.radar_baslat())

    def _baslik_cubugu(self):
        """Üst başlık: logo + rozetler + hızlı erişim butonları."""
        cerceve = tk.Frame(self, bg=RENKLER["baslik_bant"])
        cerceve.grid(row=0, column=0, sticky=(W, E))

        sol = tk.Frame(cerceve, bg=RENKLER["baslik_bant"])
        sol.pack(side=LEFT, padx=14, pady=9)

        tk.Label(sol, text="⚡", bg=RENKLER["baslik_bant"],
                 fg=RENKLER["vurgu"], font=("Segoe UI", 15)
                 ).pack(side=LEFT)
        tk.Label(sol, text="FİYAT TAKİP BOTU", bg=RENKLER["baslik_bant"],
                 fg=RENKLER["baslik"],
                 font=("Segoe UI", 13, "bold")).pack(side=LEFT, padx=(7, 0))
        tk.Label(sol, text=" v2.5 ", bg=RENKLER["vurgu"], fg="#06121f",
                 font=("Segoe UI", 8, "bold"), padx=5, pady=1
                 ).pack(side=LEFT, padx=(8, 0))
        self._rozetler = []
        for metin in ("🔔 Anında Alarm", "⏱ 7/24 Otomatik Tarama"):
            rozet = tk.Label(sol, text=metin, bg=RENKLER["kart"],
                             fg=RENKLER["metin"], font=("Segoe UI", 9),
                             padx=10, pady=3, highlightthickness=1,
                             highlightbackground=RENKLER["kenar"])
            rozet.pack(side=LEFT, padx=(14, 0))
            self._rozetler.append(rozet)

        # pencere daralırsa rozetleri gizle (başlık taşmasın)
        cerceve.bind("<Configure>", self._baslik_uydur, add="+")

        sag = tk.Frame(cerceve, bg=RENKLER["baslik_bant"])
        sag.pack(side=RIGHT, padx=14, pady=9)

        self._ipucu(ttk.Button(sag, text="＋ Ürün Ekle",
                               command=self.urun_ekle),
                    "Ad + link ile takip listesine yeni ürün ekler."
                    ).pack(side=LEFT, padx=(0, 5))
        self._ipucu(ttk.Button(sag, text="📊 Rapor", command=self._rapor_ac),
                    "Rapor sekmesini açar: dönem özeti, en düşük/en yüksek."
                    ).pack(side=LEFT, padx=(0, 5))

        self.csv_dugme = ttk.Button(sag, text="📄 CSV ▾",
                                    command=self._csv_menusu)
        self.csv_dugme.pack(side=LEFT, padx=(0, 5))
        self._ipucu(self.csv_dugme,
                    "Hangi tabloyu Excel'e aktarmak istediğinizi seçin.")

        self._ipucu(ttk.Button(sag, text="⚙ Ayarlar",
                               command=self.ayarlar_ac),
                    "Telegram token'ı, bekleme süresi, eşik ayarları."
                    ).pack(side=LEFT, padx=(0, 10))

        self.tara_btn = ttk.Button(sag, text="▶  Tarama",
                                   command=self.tarama_baslat)
        self.tara_btn.pack(side=LEFT, padx=(0, 5))
        self._ipucu(self.tara_btn,
                    "Listedeki tüm ürünleri hemen bir kez tarar (F5).")

        self.durdur_btn = ttk.Button(sag, text="■ Durdur",
                                     command=self.tarama_durdur,
                                     state="disabled")
        self.durdur_btn.pack(side=LEFT)
        self._ipucu(self.durdur_btn,
                    "Devam eden taramayı/otomatik takibi iptal eder (Esc).")

        # CSV açılır menüsü
        self.csv_menu = self._menu_yap()
        for etiket, tur in (("Tarama Sonuçları", "sonuclar"),
                            ("Ürün Arama", "pazarama"),
                            ("Rapor", "rapor"),
                            ("Ürün Listesi", "urunler"),
                            ("Fiyat Geçmişi", "gecmis"),
                            ("Rakip Radar", "radar"),
                            ("İthalat Radarı", "ithalat")):
            self.csv_menu.add_command(
                label=etiket, command=lambda t=tur: self._csv_aktar(t))

    def _csv_menusu(self):
        x = self.csv_dugme.winfo_rootx()
        y = self.csv_dugme.winfo_rooty() + self.csv_dugme.winfo_height()
        self.csv_menu.tk.call("tk_popup", self.csv_menu, x, y)

    def _rapor_ac(self):
        """Rapor sekmesini açıp raporu yeniler (başlık butonu)."""
        self.ust_sayfa.select(self.rapor_sayfa)
        self.rapor_yenile()

    def _baslik_uydur(self, olay) -> None:
        """Dar pencerede başlık rozetlerini gizleyip genişleyince geri
        getirir (butonlar taşmasın diye)."""
        genis = olay.width >= 1210
        for rozet in getattr(self, "_rozetler", []):
            gorunur = rozet.winfo_ismapped()
            if genis and not gorunur:
                rozet.pack(side=LEFT, padx=(14, 0))
            elif not genis and gorunur:
                rozet.pack_forget()

    def _govde(self):
        ana = ttk.Frame(self, style="TTk.TFrame", padding=(12, 8))
        ana.grid(row=1, column=0, sticky=(N, S, E, W))
        ana.columnconfigure(0, minsize=330, weight=0)
        ana.columnconfigure(1, weight=1)
        ana.rowconfigure(0, weight=1)

        # ===============================================================
        #  SOL: kontrol paneli (FiyatAvcısı form alanı)
        # ===============================================================
        sol = tk.Frame(ana, bg=RENKLER["panel"], highlightthickness=1,
                       highlightbackground=RENKLER["kenar"])
        sol.grid(row=0, column=0, sticky=(N, S, W), padx=(0, 10))

        # --- marka ---
        marka = tk.Frame(sol, bg=RENKLER["panel"])
        marka.pack(fill=X, padx=14, pady=(10, 3))
        ikon = tk.Frame(marka, bg=RENKLER["koyu"], width=42, height=42,
                        highlightthickness=1,
                        highlightbackground=RENKLER["vurgu"])
        ikon.pack(side=LEFT)
        ikon.pack_propagate(False)
        tk.Label(ikon, text="📈", bg=RENKLER["koyu"],
                 font=("Segoe UI", 17)).pack(expand=True)
        marka_sag = tk.Frame(marka, bg=RENKLER["panel"])
        marka_sag.pack(side=LEFT, padx=(10, 0))
        satir = tk.Frame(marka_sag, bg=RENKLER["panel"])
        satir.pack(anchor=W)
        tk.Label(satir, text="RAKİP FİYAT BOTU", bg=RENKLER["panel"],
                 fg=RENKLER["baslik"],
                 font=("Segoe UI", 12, "bold")).pack(side=LEFT)
        tk.Label(satir, text=" v2.5 ", bg=RENKLER["vurgu"], fg="#06121f",
                 font=("Segoe UI", 8, "bold"), padx=4
                 ).pack(side=LEFT, padx=(6, 0))
        tk.Label(marka_sag,
                 text="Pazaryeri Rakip Fiyat Takip & İndirim Alarmı",
                 bg=RENKLER["panel"], fg=RENKLER["gri"],
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(3, 0))

        alanlar = tk.Frame(sol, bg=RENKLER["panel"])
        alanlar.pack(fill=X, padx=14, pady=(4, 0))

        # 1) ÜRÜN ARA — 4 pazaryerinde toplu arama (+ link ile hızlı ekleme)
        self._alan_etiketi(alanlar, "ÜRÜN ARA (4 SİTE)")
        satir = tk.Frame(alanlar, bg=RENKLER["panel"])
        satir.pack(fill=X, pady=(0, 2))
        self.url_on = tk.Entry(satir, font=("Segoe UI", 10),
                               bg=RENKLER["koyu"], fg=RENKLER["gri"],
                               insertbackground=RENKLER["baslik"],
                               relief="flat", bd=6,
                               highlightthickness=1,
                               highlightbackground=RENKLER["kenar"])
        self.url_on.pack(side=LEFT, fill=X, expand=True, ipady=4)
        self.url_on.insert(0, URL_IPUCU)
        self.url_on.bind("<FocusIn>", self._url_on_basla)
        self.url_on.bind("<FocusOut>", self._url_on_bit)
        self.url_on.bind("<Return>", lambda _e: self.arama_giris())
        self._ipucu(
            self.url_on,
            "Ürün adı yazın → Trendyol, Hepsiburada, N11 ve Amazon'da "
            "fiyatlar karşılaştırılır (Enter). Link yapıştırırsanız "
            "'＋' ile doğrudan takip listesine ekleyebilirsiniz.")
        ara_btn = tk.Button(satir, text="🔍", command=self.arama_giris,
                            bg=RENKLER["vurgu"], fg="#06121f",
                            activebackground="#67e8f9",
                            activeforeground="#06121f", relief="flat", bd=0,
                            padx=7, font=("Segoe UI", 11), cursor="hand2")
        ara_btn.pack(side=LEFT, padx=(6, 0), ipady=2)
        self.paz_ara_btn = ara_btn
        self._ipucu(ara_btn,
                    "Tüm sitelerde ara (Enter da aynı işi yapar).")
        ekle_btn = tk.Button(satir, text="＋", command=self.url_ile_ekle,
                             bg=RENKLER["vurgu"], fg="#06121f",
                             activebackground="#67e8f9",
                             activeforeground="#06121f", relief="flat", bd=0,
                             padx=6, font=("Segoe UI", 12, "bold"),
                             width=3, cursor="hand2")
        ekle_btn.pack(side=LEFT, padx=(6, 0), ipady=2)
        self._ipucu(ekle_btn,
                    "Kutudaki ürün linkini takip listesine ekler "
                    "(sadece http/https linkleri).")

        # 2) TAKİP PERİYODU
        self._alan_etiketi(alanlar, "TAKİP PERİYODU")
        self.periyot_deg = StringVar()
        self._ipucu(self._alan_secici(alanlar, self.periyot_deg,
                                      PERIYOT_DEGERLER,
                                      self.periyot_degisti),
                    "Tarama ne sıklıkla otomatik çalışsın "
                    "(varsayılan 15 dakika).")

        # 3) ALARM KOŞULU
        self._alan_etiketi(alanlar, "ALARM KOŞULU")
        self.esik_deg = StringVar()
        self._ipucu(self._alan_secici(alanlar, self.esik_deg, ESIK_DEGERLER,
                                      self.esik_degisti),
                    "Fiyat bu yüzden fazla değişirse alarm çalar "
                    "(0 = her değişiklikte).")

        # 4) BİLDİRİM TÜRÜ
        self._alan_etiketi(alanlar, "BİLDİRİM TÜRÜ")
        self.bildirim_deg = StringVar()
        self._ipucu(self._alan_secici(alanlar, self.bildirim_deg,
                                      BILDIRIM_DEGERLER,
                                      self.bildirim_degisti),
                    "Alarm nereye gitsin: Telegram, sadece konsol ya da "
                    "ikisi.")

        # --- büyük başlat / durdur butonu ---
        self.takip_btn = ttk.Button(sol, text="☑  Fiyat Takibini Başlat",
                                    command=self.takip_degistir,
                                    style="Baslat.TButton")
        self.takip_btn.pack(fill=X, padx=14, pady=(10, 6))
        self._ipucu(self.takip_btn,
                    "Otomatik takibi açıp kapatır: açıkken listeki tüm "
                    "ürünler periyot süresiyle tekrar taranır.")

        yan = tk.Frame(sol, bg=RENKLER["panel"])
        yan.pack(fill=X, padx=14)
        self.secili_btn = ttk.Button(
            yan, text="▶ Seçili",
            command=lambda: self.tarama_baslat(secili=True))
        self.secili_btn.pack(side=LEFT, fill=X, expand=True)
        self._ipucu(self.secili_btn,
                    "Yalnızca soldaki listede seçili ürünü tarar.")
        self._ipucu(ttk.Button(yan, text="🔍 Seçici Bul",
                               command=self.secici_bul),
                    "Fiyatın CSS seçicisini ürün sayfasında otomatik "
                    "keşfeder; bulunan seçici tek tıkla uygulanır."
                    ).pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        self._ipucu(ttk.Button(yan, text="⚙ Ayarlar",
                               command=self.ayarlar_ac),
                    "Telegram bilgileri, istek arası bekleme ve benzeri "
                    "ayarlar.").pack(side=LEFT, fill=X, expand=True,
                                     padx=(6, 0))

        # --- ürün listesi (arama + tablo) ---
        liste = tk.Frame(sol, bg=RENKLER["panel"])
        liste.pack(fill=BOTH, expand=True, padx=14, pady=(8, 8))

        bas = tk.Frame(liste, bg=RENKLER["panel"])
        bas.pack(fill=X, pady=(0, 5))
        tk.Label(bas, text="ÜRÜNLER", bg=RENKLER["panel"],
                 fg=RENKLER["vurgu"],
                 font=("Segoe UI", 8, "bold")).pack(side=LEFT)
        self.sayac_deg = StringVar(value="0 ürün")
        tk.Label(bas, textvariable=self.sayac_deg, bg=RENKLER["panel"],
                 fg=RENKLER["gri"], font=("Segoe UI", 8)
                 ).pack(side=RIGHT)
        self.arama_deg = StringVar()
        self.arama_deg.trace_add("write", lambda *_: self.liste_doldur())
        ara = tk.Entry(bas, textvariable=self.arama_deg,
                       font=("Segoe UI", 9), bg=RENKLER["koyu"],
                       fg=RENKLER["baslik"],
                       insertbackground=RENKLER["baslik"],
                       relief="flat", bd=5, highlightthickness=1,
                       highlightbackground=RENKLER["kenar"])
        ttk.Button(bas, text="✕", width=2,
                   command=lambda: self.arama_deg.set("")).pack(side=RIGHT)
        ara.pack(side=RIGHT, fill=X, expand=True, padx=(8, 4))
        agac_kutu = tk.Frame(liste, bg=RENKLER["koyu"],
                             highlightthickness=1,
                             highlightbackground=RENKLER["kenar"])
        agac_kutu.pack(fill=BOTH, expand=True)
        agac_kutu.columnconfigure(0, weight=1)
        agac_kutu.rowconfigure(0, weight=1)

        kolonlar = ("ad", "fiyat", "durum")
        self.agac = ttk.Treeview(agac_kutu, columns=kolonlar,
                                 show="headings", height=4,
                                 selectmode="extended")
        self.agac.heading("ad", text="Ürün")
        self.agac.heading("fiyat", text="Son Fiyat")
        self.agac.heading("durum", text="Durum")
        self.agac.column("ad", width=142, anchor=W)
        self.agac.column("fiyat", width=80, anchor=E)
        self.agac.column("durum", width=50, anchor=CENTER)

        self.agac.grid(row=0, column=0, sticky=(N, S, W, E))
        dikey = ttk.Scrollbar(agac_kutu, orient="vertical",
                              command=self.agac.yview)
        self.agac.configure(yscrollcommand=dikey.set)
        dikey.grid(row=0, column=1, sticky=(N, S))

        self.agac.bind("<Double-1>", lambda e: self.urun_duzenle())
        self.agac.bind("<<TreeviewSelect>>", lambda e: self._secim_degisti())

        # ===============================================================
        #  SAĞ: canlı kart paneli + sekmeler
        # ===============================================================
        sag = tk.Frame(ana, bg=RENKLER["arka"])
        sag.grid(row=0, column=1, sticky=(N, S, E, W))
        sag.rowconfigure(1, weight=3, minsize=200)
        sag.rowconfigure(2, weight=2, minsize=170)
        sag.columnconfigure(0, weight=1)

        # --- canlı panel başlığı ---
        canli = tk.Frame(sag, bg=RENKLER["arka"])
        canli.grid(row=0, column=0, columnspan=2, sticky=(W, E),
                   pady=(0, 6))
        tk.Label(canli, text="●", bg=RENKLER["arka"], fg=RENKLER["yesil"],
                 font=("Segoe UI", 10)).pack(side=LEFT)
        self.kart_ozet = StringVar(value="Takip edilen ürün yok.")
        tk.Label(canli, textvariable=self.kart_ozet, bg=RENKLER["arka"],
                 fg=RENKLER["baslik"],
                 font=("Segoe UI", 11, "bold")).pack(side=LEFT, padx=(7, 0))
        tk.Label(canli, text="Canlı Panel v2.0", bg=RENKLER["arka"],
                 fg=RENKLER["gri"], font=("Segoe UI", 9)).pack(side=RIGHT)

        # --- ürün kartları (kaydırılabilir) ---
        kart_kutu = tk.Frame(sag, bg=RENKLER["arka"])
        kart_kutu.grid(row=1, column=0, columnspan=2,
                       sticky=(N, S, E, W))
        kart_kutu.rowconfigure(0, weight=1)
        kart_kutu.columnconfigure(0, weight=1)

        self.kart_canvas = tk.Canvas(kart_kutu, bg=RENKLER["arka"],
                                     highlightthickness=0, bd=0)
        k_kay = ttk.Scrollbar(kart_kutu, orient="vertical",
                              command=self.kart_canvas.yview)
        self.kart_canvas.configure(yscrollcommand=k_kay.set)
        self.kart_canvas.grid(row=0, column=0, sticky=(N, S, E, W))
        k_kay.grid(row=0, column=1, sticky=(N, S))

        self.kart_govde = tk.Frame(self.kart_canvas, bg=RENKLER["arka"])
        self._kart_pencere = self.kart_canvas.create_window(
            (0, 0), window=self.kart_govde, anchor="nw")
        self.kart_govde.bind("<Configure>", self._kart_bolge)
        self.kart_canvas.bind("<Configure>", self._kart_genislik)
        self.kart_govde.bind("<MouseWheel>", self._kart_tekerlek)

        # --- sekmeler ---
        self.ust_sayfa = ttk.Notebook(sag)
        self.ust_sayfa.grid(row=2, column=0, columnspan=2,
                            sticky=(N, S, E, W))

        # --- Tarama sonuçları ---
        sonuc_sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame", padding=6)
        self.ust_sayfa.add(sonuc_sayfa, text="  Tarama Sonuçları  ")

        # --- Ürün Arama sekmesi (4 pazaryeri karşılaştırma) ---
        self._arama_sayfasi_ekle()
        sonuc_sayfa.rowconfigure(1, weight=1)
        sonuc_sayfa.rowconfigure(2, weight=0)
        sonuc_sayfa.columnconfigure(0, weight=1)
        sonuc_sayfa.columnconfigure(1, weight=0)

        ust2 = ttk.Frame(sonuc_sayfa, style="TTk.TFrame")
        ust2.grid(row=0, column=0, columnspan=2, sticky=(W, E), pady=(0, 6))
        self.ozet_deg = StringVar(value="Henüz tarama yapılmadı.")
        ttk.Label(ust2, textvariable=self.ozet_deg,
                  font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        ttk.Button(ust2, text="CSV Aktar",
                   command=lambda: self._csv_aktar("sonuclar")).pack(
            side=RIGHT)
        ttk.Button(ust2, text="Temizle",
                   command=self.sonuclari_temizle).pack(side=RIGHT, padx=(0, 6))

        skolonlar = ("ad", "onceki", "yeni", "yuzde", "durum", "mesaj")
        self.sonuc_agac = ttk.Treeview(sonuc_sayfa, columns=skolonlar,
                                       show="headings", height=4)
        basliklar = {"ad": "Ürün", "onceki": "Önceki", "yeni": "Yeni",
                     "yuzde": "Değişim", "durum": "Durum", "mesaj": "Mesaj"}
        genislik = {"ad": 240, "onceki": 110, "yeni": 110, "yuzde": 90,
                    "durum": 100, "mesaj": 240}
        for k in skolonlar:
            self.sonuc_agac.heading(k, text=basliklar[k])
            self.sonuc_agac.column(k, width=genislik[k],
                                   anchor=W if k in ("ad", "mesaj") else CENTER)
        s_dikey = ttk.Scrollbar(sonuc_sayfa, orient="vertical",
                                command=self.sonuc_agac.yview)
        s_yatay = ttk.Scrollbar(sonuc_sayfa, orient="horizontal",
                                command=self.sonuc_agac.xview)
        self.sonuc_agac.configure(yscrollcommand=s_dikey.set,
                                  xscrollcommand=s_yatay.set)
        self.sonuc_agac.grid(row=1, column=0, sticky=(N, S, E, W))
        s_dikey.grid(row=1, column=1, sticky=(N, S))
        s_yatay.grid(row=2, column=0, sticky=(W, E))

        # --- Fiyat geçmişi + grafik ---
        gecmis_sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame", padding=6)
        self.ust_sayfa.add(gecmis_sayfa, text="  Fiyat Geçmişi  ")
        gecmis_sayfa.rowconfigure(1, weight=1)
        gecmis_sayfa.columnconfigure(0, weight=1)
        gecmis_sayfa.columnconfigure(1, weight=0)
        gecmis_sayfa.columnconfigure(2, weight=2)

        g_ust = ttk.Frame(gecmis_sayfa, style="TTk.TFrame")
        g_ust.grid(row=0, column=0, columnspan=3, sticky=(W, E), pady=(0, 6))
        ttk.Label(g_ust, text="Seçili ürünün geçmişi").pack(side=LEFT)
        self._ipucu(ttk.Button(g_ust, text="Grafiği Yenile",
                               command=self.grafik_ciz),
                    "Seçili ürünün fiyat grafiğini yeniden çizer."
                    ).pack(side=RIGHT)
        self._ipucu(ttk.Button(g_ust, text="CSV Aktar",
                               command=lambda: self._csv_aktar("gecmis")),
                    "Seçili ürünün günlük fiyatlarını CSV yapar."
                    ).pack(side=RIGHT, padx=(0, 6))

        self.gecmis_agac = ttk.Treeview(
            gecmis_sayfa, columns=("tarih", "fiyat"), show="headings",
            height=7)
        self.gecmis_agac.heading("tarih", text="Tarih")
        self.gecmis_agac.heading("fiyat", text="Fiyat")
        self.gecmis_agac.column("tarih", width=130, anchor=W)
        self.gecmis_agac.column("fiyat", width=130, anchor=E)
        gd = ttk.Scrollbar(gecmis_sayfa, orient="vertical",
                           command=self.gecmis_agac.yview)
        self.gecmis_agac.configure(yscrollcommand=gd.set)
        self.gecmis_agac.grid(row=1, column=0, sticky=(N, S, E, W))
        gd.grid(row=1, column=1, sticky=(N, S))

        self.grafik_uyesi = ttk.Frame(gecmis_sayfa, style="TTk.TFrame")
        self.grafik_uyesi.grid(row=1, column=2, sticky=(N, S, E, W),
                               padx=(10, 0))

        # --- Rapor ---
        self.rapor_sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame",
                                     padding=6)
        self.ust_sayfa.add(self.rapor_sayfa, text="  Rapor  ")
        self.rapor_sayfa.rowconfigure(1, weight=1)
        self.rapor_sayfa.rowconfigure(2, weight=0)
        self.rapor_sayfa.columnconfigure(0, weight=1)
        self.rapor_sayfa.columnconfigure(1, weight=0)

        r_ust = ttk.Frame(self.rapor_sayfa, style="TTk.TFrame")
        r_ust.grid(row=0, column=0, columnspan=2, sticky=(W, E), pady=(0, 6))
        ttk.Label(r_ust, text="Son").pack(side=LEFT)
        self.gun_deg = IntVar(value=30)
        ttk.Spinbox(r_ust, from_=7, to=365, increment=1, width=6,
                    textvariable=self.gun_deg).pack(side=LEFT, padx=(6, 4))
        ttk.Label(r_ust, text="gün").pack(side=LEFT)
        self._ipucu(ttk.Button(r_ust, text="Raporu Getir",
                               command=self.rapor_yenile),
                    "Seçili günden geriye tüm ürünlerin özetini getirir."
                    ).pack(side=LEFT, padx=(8, 0))
        self._ipucu(ttk.Button(r_ust, text="CSV Aktar",
                               command=lambda: self._csv_aktar("rapor")),
                    "Rapor tablosunu CSV olarak indirir."
                    ).pack(side=LEFT, padx=(6, 0))
        self.rapor_ozet = StringVar(value="")
        ttk.Label(r_ust, textvariable=self.rapor_ozet,
                  foreground=RENKLER["gri"]).pack(side=RIGHT)

        r_kolonlar = ("ad", "kayit", "ilk", "son", "dusuk", "yuksek",
                      "degisim", "aralik")
        self.rapor_agac = ttk.Treeview(self.rapor_sayfa, columns=r_kolonlar,
                                       show="headings", height=6)
        r_baslik = {"ad": "Ürün", "kayit": "Kayıt", "ilk": "İlk",
                    "son": "Son", "dusuk": "En Düşük", "yuksek": "En Yüksek",
                    "degisim": "Değişim", "aralik": "Aralık"}
        r_gen = {"ad": 230, "kayit": 62, "ilk": 104, "son": 104,
                 "dusuk": 104, "yuksek": 104, "degisim": 86, "aralik": 82}
        for k in r_kolonlar:
            self.rapor_agac.heading(k, text=r_baslik[k])
            self.rapor_agac.column(k, width=r_gen[k],
                                   anchor=W if k == "ad" else CENTER)
        r_dikey = ttk.Scrollbar(self.rapor_sayfa, orient="vertical",
                                command=self.rapor_agac.yview)
        r_yatay = ttk.Scrollbar(self.rapor_sayfa, orient="horizontal",
                                command=self.rapor_agac.xview)
        self.rapor_agac.configure(yscrollcommand=r_dikey.set,
                                  xscrollcommand=r_yatay.set)
        self.rapor_agac.grid(row=1, column=0, sticky=(N, S, E, W))
        r_dikey.grid(row=1, column=1, sticky=(N, S))
        r_yatay.grid(row=2, column=0, sticky=(W, E))

        # --- Rakip Radar sekmesi ---
        self._radar_sayfasi_ekle()

        # --- İthalat Radarı sekmesi ---
        self._ithalat_sayfasi_ekle()

        # --- Ürün görseli sekmesi ---
        gorsel_sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame", padding=6)
        self.ust_sayfa.add(gorsel_sayfa, text="  🖼 Ürün Görseli  ")
        self.gorsel_sayfa = gorsel_sayfa
        gorsel_sayfa.columnconfigure(1, weight=1)
        gorsel_sayfa.rowconfigure(0, weight=1)

        sol_panel = ttk.Frame(gorsel_sayfa, style="TPanel.TFrame")
        sol_panel.grid(row=0, column=0, sticky=(N, S, W), padx=(0, 8))

        self._ipucu(ttk.Button(sol_panel, text="🔄 Görseli Getir",
                               command=self.gorsel_getir),
                    "Seçili ürünün sayfa görsellerini indirir ve ilkini "
                    "gösterir.").pack(fill=X, pady=(0, 4))
        self._ipucu(ttk.Button(sol_panel, text="➡ Sonraki",
                               command=lambda: self.gorsel_degistir(1)),
                    "Sıradaki görseli gösterir.").pack(fill=X, pady=(0, 4))
        self._ipucu(ttk.Button(sol_panel, text="⬅ Önceki",
                               command=lambda: self.gorsel_degistir(-1)),
                    "Önceki görseli gösterir.").pack(fill=X, pady=(0, 4))
        self._ipucu(ttk.Button(sol_panel, text="🌐 Tarayıcıda Aç",
                               command=self._tarayicida_ac),
                    "Ürün sayfasını tarayıcıda açar."
                    ).pack(fill=X, pady=(0, 4))
        ttk.Separator(sol_panel).pack(fill=X, pady=6)
        ttk.Label(sol_panel, text="Görsel listesi:",
                  foreground=RENKLER["gri"]).pack(anchor=W)
        self.gorsel_liste = tk.Listbox(sol_panel, height=8, width=26,
                                       font=("Segoe UI", 9),
                                       exportselection=False,
                                       bg=RENKLER["koyu"],
                                       fg=RENKLER["metin"],
                                       highlightthickness=0, relief="flat",
                                       selectbackground=RENKLER["vurgu"],
                                       selectforeground="#06121f")
        self.gorsel_liste.pack(fill=X, pady=(4, 0))
        self.gorsel_liste.bind("<<ListboxSelect>>",
                               lambda e: self.gorsel_secildi())

        self.gorsel_etiket = tk.Label(
            gorsel_sayfa,
            text="Soldan 'Görseli Getir' deyin.\n\n"
                 "Seçili ürünün fiyatını ve görselini birlikte görürsünüz.",
            bg=RENKLER["koyu"], fg=RENKLER["gri"],
            font=("Segoe UI", 11), justify="center")
        self.gorsel_etiket.grid(row=0, column=1, sticky=(N, S, E, W))

        # ---------- ALT: konsol şeridi (her zaman görünür) ----------
        konsol_kutu = tk.Frame(ana, bg=RENKLER["panel"],
                               highlightthickness=1,
                               highlightbackground=RENKLER["kenar"])
        konsol_kutu.grid(row=1, column=0, columnspan=2,
                         sticky=(W, E), pady=(10, 0))

        k_ust = tk.Frame(konsol_kutu, bg=RENKLER["panel"])
        k_ust.pack(fill=X, padx=8, pady=(5, 0))
        tk.Label(k_ust, text="📟 KONSOL", bg=RENKLER["panel"],
                 fg=RENKLER["vurgu"],
                 font=("Segoe UI", 8, "bold")).pack(side=LEFT)
        self._ipucu(ttk.Button(k_ust, text="Kaydet",
                               command=self._konsol_kaydet),
                    "Konsol kaydını .txt dosyasına yazar.").pack(side=RIGHT)
        self._ipucu(ttk.Button(k_ust, text="Kopyala",
                               command=self._konsol_kopyala),
                    "Konsolun tamamını panoya kopyalar."
                    ).pack(side=RIGHT, padx=(0, 6))
        self._ipucu(ttk.Button(k_ust, text="Temizle",
                               command=self.konsol_temizle),
                    "Konsolu temizler (kayıp olmaz, dosyaya yazıldıysa)."
                    ).pack(side=RIGHT, padx=(0, 6))

        k_govde = tk.Frame(konsol_kutu, bg=RENKLER["koyu"])
        k_govde.pack(fill=X, padx=8, pady=(5, 8))
        k_govde.columnconfigure(0, weight=1)
        k_govde.rowconfigure(0, weight=1)

        self.konsol = tk.Text(k_govde, height=4, wrap="word",
                              font=("Consolas", 9),
                              background=RENKLER["koyu"],
                              foreground="#cbd5e1",
                              insertbackground="#ffffff",
                              relief="flat", padx=8, pady=6,
                              borderwidth=0, state="disabled")
        self.konsol.tag_configure("hata", foreground="#fca5a5")
        self.konsol.tag_configure("basari", foreground="#86efac")
        self.konsol.tag_configure("uyari", foreground="#fcd34d")
        self.konsol.tag_configure("bilgi", foreground="#7dd3fc")
        self.konsol.tag_configure("normal", foreground="#cbd5e1")
        k_d = ttk.Scrollbar(k_govde, orient="vertical",
                            command=self.konsol.yview)
        self.konsol.configure(yscrollcommand=k_d.set)
        self.konsol.grid(row=0, column=0, sticky=(N, S, E, W))
        k_d.grid(row=0, column=1, sticky=(N, S))

        # ---------- ilerleme ----------
        ilerleme = ttk.Frame(self, style="TTk.TFrame")
        ilerleme.grid(row=2, column=0, sticky=(W, E), padx=10, pady=(6, 0))
        self.ilerleme = ttk.Progressbar(ilerleme, mode="determinate",
                                        maximum=100)
        self.ilerleme.pack(fill=X)
        self.ilerleme_deger = StringVar(value="")
        ttk.Label(ilerleme, textvariable=self.ilerleme_deger,
                  foreground=RENKLER["gri"]).pack(anchor=W)

        # ---------- açılış ipucu balonu (ilk açılışta görünür) ----------
        self.after(800, self._hosgeldin_goster)

    def _hosgeldin_goster(self) -> None:
        """Kısa 'nasıl kullanılır' penceresi; 'bir daha gösterme' ile kapanır."""
        if os.environ.get("RIYA_TESTI") == "1":
            return
        ayar = self.ayar.setdefault("ayarlar", {})
        if not ayar.get("ipucu_goster", True):
            return

        p = tk.Toplevel(self)
        p.title("Hoş geldiniz")
        p.configure(bg=RENKLER["panel"])
        p.transient(self)
        p.resizable(False, False)

        govde = tk.Frame(p, bg=RENKLER["panel"], padx=18, pady=14)
        govde.pack(fill=BOTH, expand=True)

        tk.Label(govde, text="👋 Hoş geldiniz — 1 dakikada kullanım",
                 bg=RENKLER["panel"], fg=RENKLER["baslik"],
                 font=("Segoe UI", 12, "bold")).pack(anchor=W)
        tk.Label(govde, justify="left", bg=RENKLER["panel"],
                 fg=RENKLER["metin"], font=("Segoe UI", 10),
                 pady=8,
                 text=("1) 🔍 Ürün arama: soldaki kutuya ürün adı yazıp "
                       "Enter'a basın — Trendyol, Hepsiburada, N11 ve "
                       "Amazon'daki fiyatları tek tabloda görürsünüz.\n\n"
                       "2) ＋ ile bulduğunuz ürünü takip listesine ekleyip "
                       "'☑ Fiyat Takibini Başlat' ile fiyat değişikliklerini "
                       "izleyin.\n\n"
                       "3) 🏆 Rakip Radar satıcıları, 🌍 İthalat Radarı ise "
                       "tedarikçileri gösterir.\n\n"
                       "4) Her butonun üstüne bir süre gelin — kısa "
                       "açıklaması çıkar.")
                 ).pack(anchor=W)

        alt = tk.Frame(govde, bg=RENKLER["panel"])
        alt.pack(fill=X, pady=(10, 0))
        bir_daha = BooleanVar(value=False)
        ttk.Checkbutton(alt, text="Bir daha gösterme",
                        variable=bir_daha).pack(side=LEFT)

        def kapat():
            if bir_daha.get():
                ayar["ipucu_goster"] = False
                self._config_kaydet()
            p.destroy()

        self._ipucu(ttk.Button(alt, text="Kapat", command=kapat),
                    "Bu pencereyi kapatır.").pack(side=RIGHT)
        p.protocol("WM_DELETE_WINDOW", kapat)

        try:
            p.update_idletasks()
            x = self.winfo_rootx() + (self.winfo_width() - p.winfo_width()) // 2
            y = self.winfo_rooty() + (self.winfo_height() - p.winfo_height()) // 3
            p.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:            # noqa: BLE001
            pass

    def _durum_cubugu(self):
        # --- alt bant: özellik şeridi (FiyatAvcısı altındaki tikler) ---
        alt = tk.Frame(self, bg=RENKLER["baslik_bant"])
        alt.grid(row=3, column=0, sticky=(W, E), padx=12, pady=(6, 0))
        for metin in ("7/24 Otomatik Rakip Fiyat Takibi",
                      "Fiyat Değişimlerinde Anlık Alarm",
                      "Kâr Marjınızı Daima Zirvede Tutun",
                      "Sınırsız Ürün Takibi"):
            tk.Label(alt, text="✓ " + metin, bg=RENKLER["baslik_bant"],
                     fg=RENKLER["metin"],
                     font=("Segoe UI", 9)).pack(side=LEFT, expand=True,
                                                padx=10, pady=5)

        # --- durum çubuğu ---
        cerceve = tk.Frame(self, bg=RENKLER["baslik_bant"])
        cerceve.grid(row=4, column=0, sticky=(W, E))

        self.durum_deg = StringVar(value="Hazır")
        ttk.Label(cerceve, textvariable=self.durum_deg,
                  style="Status.TLabel").pack(side=LEFT, fill=X,
                                              expand=True)

        self.sag_durum = StringVar(value=self._sag_durum_metni())
        ttk.Label(cerceve, textvariable=self.sag_durum,
                  style="Status.TLabel").pack(side=RIGHT)

    def _sag_durum_metni(self) -> str:
        parcalar = []
        parcalar.append(f"PIL: {'✓' if PIL_VAR else '✗'}")
        parcalar.append(f"Grafik: {'✓' if MPL_VAR else '✗'}")
        n = len(self.ayar.get("urunler", []))
        parcalar.append(f"{n} ürün")
        return "   ·   ".join(parcalar)

    # ------------------------------------------------------------------
    #  Sol panel alanları
    # ------------------------------------------------------------------
    def _ipucu(self, widget, metin: str):
        """Widget üstüne gelince açıklama balonu bağlar."""
        Ipucu(widget, metin)
        return widget

    def _alan_etiketi(self, ebeveyn, metin: str) -> None:
        tk.Label(ebeveyn, text=metin, bg=RENKLER["panel"],
                 fg=RENKLER["gri"],
                 font=("Segoe UI", 8, "bold")).pack(anchor=W,
                                                    pady=(5, 2))

    def _alan_secici(self, ebeveyn, degisken: StringVar,
                     degerler: list[str], komut) -> ttk.Combobox:
        kutu = ttk.Combobox(ebeveyn, textvariable=degisken,
                            values=degerler, state="readonly")
        kutu.pack(fill=X, ipady=1)
        kutu.bind("<<ComboboxSelected>>", lambda _e: komut())
        self._combobox_karanlik(kutu)
        return kutu

    def _alanlari_yukle(self) -> None:
        """Config değerlerini sol panel alanlarına yansıtır."""
        ayar = self.ayar.get("ayarlar", {})

        dk = ayar.get("periyot_dakika", 15)
        try:
            dk = int(dk)
        except (TypeError, ValueError):
            dk = 15
        i = PERIYOT_DAKIKA.index(dk) if dk in PERIYOT_DAKIKA else 2
        self.periyot_deg.set(PERIYOT_DEGERLER[i])

        try:
            esik = float(ayar.get("esik_yuzde", 0))
        except (TypeError, ValueError):
            esik = 0.0
        self.esik_deg.set(ESIK_DEGERLER[_indeks(ESIK_YUZDE, esik, 0)])

        bildirim = str(ayar.get("bildirim", "telegram"))
        i = (BILDIRIM_ANAHTAR.index(bildirim)
             if bildirim in BILDIRIM_ANAHTAR else 0)
        self.bildirim_deg.set(BILDIRIM_DEGERLER[i])

    def _url_on_basla(self, _olay=None) -> None:
        if self.url_on.get() == URL_IPUCU:
            self.url_on.delete(0, END)
            self.url_on.configure(fg=RENKLER["baslik"])

    def _url_on_bit(self, _olay=None) -> None:
        if not self.url_on.get().strip():
            self.url_on.insert(0, URL_IPUCU)
            self.url_on.configure(fg=RENKLER["gri"])

    def url_ile_ekle(self) -> None:
        """Adres çubuğundaki URL ile hızlıca ürün ekler."""
        deger = self.url_on.get().strip()
        if deger == URL_IPUCU:
            deger = ""
        if deger and not deger.startswith(("http://", "https://")):
            messagebox.showwarning("Geçersiz URL",
                                   "URL http:// veya https:// ile "
                                   "başlamalı.")
            return
        self.urun_ekle(url_on=deger)

    def periyot_degisti(self) -> None:
        i = _indeks(PERIYOT_DEGERLER, self.periyot_deg.get(), 2)
        self.ayar.setdefault("ayarlar", {})["periyot_dakika"] = \
            PERIYOT_DAKIKA[i]
        self._config_kaydet()
        self.durum_deg.set(f"Takip periyodu: {self.periyot_deg.get()}")
        if self.otomatik_takip and not self.tarama_suriyor:
            self._tekrar_planla()

    def esik_degisti(self) -> None:
        i = _indeks(ESIK_DEGERLER, self.esik_deg.get(), 0)
        self.ayar.setdefault("ayarlar", {})["esik_yuzde"] = ESIK_YUZDE[i]
        self._config_kaydet()
        self.kartlari_guncelle()
        self.durum_deg.set(f"Alarm koşulu: {self.esik_deg.get()}")

    def bildirim_degisti(self) -> None:
        i = _indeks(BILDIRIM_DEGERLER, self.bildirim_deg.get(), 0)
        self.ayar.setdefault("ayarlar", {})["bildirim"] = \
            BILDIRIM_ANAHTAR[i]
        self._config_kaydet()
        self.durum_deg.set(f"Bildirim türü: {self.bildirim_deg.get()}")

    # ------------------------------------------------------------------
    #  Otomatik takip (başlat / durdur / periyot)
    # ------------------------------------------------------------------
    def _periyot_dakika(self) -> int:
        try:
            return int(self.ayar.get("ayarlar", {})
                        .get("periyot_dakika", 15))
        except (TypeError, ValueError):
            return 15

    def takip_degistir(self) -> None:
        """Büyük başlat/durdur butonu — otomatik takibi açıp kapatır."""
        if self.otomatik_takip or self.tarama_suriyor:
            self.tarama_durdur()
            self.durum_deg.set("Otomatik takip durduruldu.")
            self.konsol_yaz("■ Otomatik takip durduruldu.")
            return
        if self.tarama_baslat():
            self.otomatik_takip = True
            dk = self._periyot_dakika()
            if dk > 0:
                self.konsol_yaz(f"⏱ Otomatik takip açık — "
                                f"{dk} dakikada bir taranacak.")
        self._takip_guncelle()

    def _takip_guncelle(self) -> None:
        if not hasattr(self, "takip_btn"):
            return
        if self.otomatik_takip or self.tarama_suriyor:
            self.takip_btn.configure(text="■  Takibi Durdur",
                                     style="Durdur.TButton")
        else:
            self.takip_btn.configure(text="☑  Fiyat Takibini Başlat",
                                     style="Baslat.TButton")

    def _periyot_iptal(self) -> None:
        if self._periyot_zamanlayici is not None:
            try:
                self.after_cancel(self._periyot_zamanlayici)
            except Exception:                        # noqa: BLE001
                pass
            self._periyot_zamanlayici = None

    def _tekrar_planla(self) -> None:
        """Tarama bitince otomatik takip sürüyorsa sonraki taramayı kurar."""
        self._periyot_iptal()
        if not self.otomatik_takip:
            self._takip_guncelle()
            return
        dk = self._periyot_dakika()
        if dk <= 0:
            self.otomatik_takip = False
            self._takip_guncelle()
            self.durum_deg.set("Tarama tamamlandı (tek seferlik).")
            return
        self._periyot_zamanlayici = self.after(dk * 60000,
                                               self._periyodik_tarama)
        self.durum_deg.set(f"Otomatik takip — sonraki tarama {dk} dk sonra")
        self._takip_guncelle()

    def _periyodik_tarama(self) -> None:
        self._periyot_zamanlayici = None
        if not self.otomatik_takip:
            return
        if not self.tarama_baslat():
            self.otomatik_takip = False
            self._takip_guncelle()

    # ------------------------------------------------------------------
    #  Canlı panel — ürün kartları
    # ------------------------------------------------------------------
    def _kart_bolge(self, _olay=None) -> None:
        yuk = max(self.kart_govde.winfo_reqheight(), 1)
        self.kart_canvas.itemconfig(self._kart_pencere, height=yuk)
        self.kart_canvas.configure(
            scrollregion=self.kart_canvas.bbox("all"))

    def _kart_genislik(self, olay) -> None:
        yuk = max(self.kart_govde.winfo_reqheight(), 1)
        self.kart_canvas.itemconfig(self._kart_pencere, width=olay.width,
                                    height=yuk)
        self.kart_canvas.configure(
            scrollregion=self.kart_canvas.bbox("all"))

    def _kart_tekerlek(self, olay) -> None:
        adim = -1 if olay.delta > 0 else 1
        self.kart_canvas.yview_scroll(adim, "units")

    def _kart_olay_bagla(self, widget, tikla=None, cift=None) -> None:
        if tikla is not None:
            widget.bind("<Button-1>", tikla, add="+")
        if cift is not None:
            widget.bind("<Double-1>", cift, add="+")
        widget.bind("<MouseWheel>", self._kart_tekerlek, add="+")
        for cocuk in widget.winfo_children():
            self._kart_olay_bagla(cocuk, tikla, cift)

    def kartlari_guncelle(self, son_fiyatlar: dict | None = None) -> None:
        """Canlı paneli config + son tarama ile yeniden çizer."""
        if not hasattr(self, "kart_govde"):
            return
        for cocuk in self.kart_govde.winfo_children():
            cocuk.destroy()

        arama = self.arama_deg.get().strip().lower()
        urunler = [u for u in self.ayar.get("urunler", [])
                   if not arama
                   or arama in (u.get("ad") or "").lower()
                   or arama in (u.get("url") or "").lower()]

        if son_fiyatlar is None:
            son_fiyatlar = self._son_fiyat_haritasi()
        tarama = {s.get("ad"): s for s in self.son_tarama if s.get("ad")}
        esik = self._esik_degeri()

        for u in urunler:
            self._kart_olustur(u, son_fiyatlar, tarama.get(u.get("ad")),
                               esik)

        if not urunler:
            tk.Label(self.kart_govde,
                     text="Liste boş — soldaki alana rakip ürün linkini "
                          "yapıştırıp  ＋  ile ekleyin.",
                     bg=RENKLER["kart"], fg=RENKLER["gri"],
                     font=("Segoe UI", 10), pady=36, padx=20,
                     highlightthickness=1,
                     highlightbackground=RENKLER["kenar"]).pack(fill=X)

        self.kart_ozet.set(
            f"Takip Edilen Ürünler: {len(urunler)} aktif rakip taranıyor")
        self._kart_bolge()

    def _esik_degeri(self) -> float:
        try:
            return float(self.ayar.get("ayarlar", {})
                         .get("esik_yuzde", 0))
        except (TypeError, ValueError):
            return 0.0

    def _kart_olustur(self, u: dict, son_fiyatlar: dict,
                      s: dict | None, esik: float) -> None:
        """Tek bir ürün kartını (FiyatAvcısı kartı gibi) çizer."""
        ad = u.get("ad") or ""
        fiyat, yon = son_fiyatlar.get(ad, (None, "—"))
        try:
            host = urlparse(u.get("url") or "").netloc.replace("www.", "")
        except Exception:                            # noqa: BLE001
            host = ""
        host = host or "—"

        # varsayılanlar
        rozet = ("BEKLEMEDE", "gri")
        durum_metin = "⏱ Tarama Bekliyor"
        durum_renk = "gri"
        vurgu_renk = ROZET["gri"][1]
        alt_metin = f"{host} • Henüz kontrol edilmedi"

        if s:
            durum = s.get("durum")
            yuzde = s.get("yuzde")
            eski = cekirdek.fiyat_bicimle(s.get("onceki"),
                                          s.get("para", ""))
            yeni = cekirdek.fiyat_bicimle(s.get("fiyat"),
                                          s.get("para", ""))
            alt_metin = f"{host} • Eski: {eski} → Yeni: {yeni}"

            if durum == "degisti" and yuzde is not None:
                if yuzde < 0:
                    rozet = (f"FİYAT DÜŞTÜ (%{abs(yuzde):.0f})", "yesil")
                else:
                    rozet = (f"FİYAT ARTTI (+%{yuzde:.0f})", "kirmizi")
                vurgu_renk = ROZET[rozet[1]][1]
                if esik <= 0 or abs(yuzde) >= esik:
                    durum_metin = "🔔 Fiyat Alarmı Tetiklendi"
                    durum_renk = "sari"
                    vurgu_renk = ROZET["sari"][1]
                else:
                    durum_metin = f"○ Eşiğin altında kaldı (esik %{esik:g})"
                    durum_renk = "gri"
            elif durum == "degismedi":
                rozet = ("SABİT FİYAT", "cyan")
                durum_metin = "✓ Değişim Yok"
                durum_renk = "yesil"
                vurgu_renk = ROZET["cyan"][1]
            elif durum in ("bulunamadi", "hata", "robots"):
                rozet = ("FİYAT ALINAMADI", "sari")
                durum_metin = "⚠ Kontrol Edilemedi"
                durum_renk = "kirmizi"
                vurgu_renk = ROZET["sari"][1]
                alt_metin = (f"{host} • "
                             f"{s.get('mesaj') or 'Fiyat okunamadı'}")
            elif durum == "ilk":
                rozet = ("İLK KAYIT", "mor")
                durum_metin = "✔ Takip başlatıldı"
                durum_renk = "yesil"
                vurgu_renk = ROZET["mor"][1]
            elif durum == "iptal":
                rozet = ("DURDURULDU", "gri")
                durum_metin = "■ Tarama iptal edildi"
                durum_renk = "gri"
        elif fiyat is not None:
            para = self._para_ad(ad)
            alt_metin = (f"{host} • Son fiyat: "
                         f"{cekirdek.fiyat_bicimle(fiyat, para)}")
            if yon == "▲":
                rozet = ("FİYAT ARTTI", "kirmizi")
                durum_metin = "↗ Geçmiş kayda göre artış"
                durum_renk = "kirmizi"
                vurgu_renk = ROZET["kirmizi"][1]
            elif yon == "▼":
                rozet = ("FİYAT DÜŞTÜ", "yesil")
                durum_metin = "↘ Geçmiş kayda göre düşüş"
                durum_renk = "yesil"
                vurgu_renk = ROZET["yesil"][1]
            elif yon == "=":
                rozet = ("SABİT FİYAT", "cyan")
                durum_metin = "✓ Değişim Yok"
                durum_renk = "yesil"
                vurgu_renk = ROZET["cyan"][1]

        # --- kart iskeleti ---
        kart = tk.Frame(self.kart_govde, bg=RENKLER["kart"],
                        highlightthickness=1,
                        highlightbackground=RENKLER["kenar"])
        kart.pack(fill=X, pady=(0, 8))
        tk.Frame(kart, bg=vurgu_renk, width=4).pack(side=LEFT, fill=Y)

        ic = tk.Frame(kart, bg=RENKLER["kart"])
        ic.pack(side=LEFT, fill=BOTH, expand=True, padx=(12, 14), pady=9)

        ust = tk.Frame(ic, bg=RENKLER["kart"])
        ust.pack(fill=X)
        tk.Label(ust, text=ad, bg=RENKLER["kart"], fg=RENKLER["baslik"],
                 font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        r_bg, r_fg = ROZET[rozet[1]]
        tk.Label(ust, text=rozet[0], bg=r_bg, fg=r_fg,
                 font=("Segoe UI", 8, "bold"), padx=8, pady=3,
                 highlightthickness=1,
                 highlightbackground=r_fg).pack(side=RIGHT)

        tk.Label(ic, text=alt_metin, bg=RENKLER["kart"],
                 fg=RENKLER["gri"], font=("Segoe UI", 9),
                 anchor=W).pack(fill=X, pady=(4, 0))

        tk.Label(ic, text=durum_metin, bg=RENKLER["kart"],
                 fg=ROZET[durum_renk][1], font=("Segoe UI", 9, "bold"),
                 anchor=W).pack(fill=X, pady=(5, 0))

        # tıklama: kart → listede seç, çift tık → tarayıcıda aç
        secim = lambda _e, a=ad: self._kart_sec(a)
        acilis = lambda _e, a=ad: self._kart_ac(a)
        self._kart_olay_bagla(kart, secim, acilis)

    def _kart_sec(self, ad: str) -> None:
        for iid in self.agac.get_children():
            if self.agac.item(iid, "values")[0] == ad:
                self.agac.selection_set(iid)
                self.agac.see(iid)
                break

    def _kart_ac(self, ad: str) -> None:
        u = self.urun_bul(ad)
        if u and u.get("url"):
            self._url_ac(u["url"])

    # ------------------------------------------------------------------
    #  Konsol
    # ------------------------------------------------------------------
    def konsol_yaz(self, metin: str) -> None:
        """Worker thread'den güvenli yazma (kuyruk üzerinden)."""
        self.kuyruk.put(metin)

    def _kuyruk_isle(self) -> None:
        bitti = False
        try:
            while True:
                metin = self.kuyruk.get_nowait()
                bitti = True
                etiket = "normal"
                kucuk = metin.lower()
                if any(x in kucuk for x in ("[!] hata", "hata:", "traceback",
                                            "[!]")):
                    etiket = "hata"
                elif any(x in kucuk for x in ("✅", "başarı", "ilk kayıt")):
                    etiket = "basari"
                elif any(x in kucuk for x in ("⚠", "uyarı", "değişmedi")):
                    etiket = "uyari"
                elif any(x in kucuk for x in ("📊", "•", "→")):
                    etiket = "bilgi"
                self.konsol.configure(state="normal")
                self.konsol.insert(END, metin + "\n", etiket)
                self.konsol.see(END)
                self.konsol.configure(state="disabled")
        except queue.Empty:
            pass

        if bitti:
            self.durum_deg.set(self._son_satir_ozet())

        # Görsel / rapor işlerini ana thread'de bitir
        while True:
            try:
                islev, veri = self._ana_kuyruk.get_nowait()
            except (queue.Empty, AttributeError):
                break
            try:
                islev(veri)
            except Exception as hata:                # noqa: BLE001
                # Tek bir kötü işlev tüm arka plan döngüsünü öldürmemeli:
                # eskiden bu istisna after() çağrısına da sıçrar, kuyruk
                # boşaltma + grafik/rapor güncellemeleri kalıcı olarak dururdu.
                self.konsol_yaz(f"[!] arayüz işlevi çalıştırılamadı: {hata}")

        try:
            self.after(120, self._kuyruk_isle)
        except (tk.TclError, RuntimeError):
            # pencere kapatıldı / test bitti — döngüyü durdur
            pass

    _ana_kuyruk: "queue.Queue" = queue.Queue()

    def konsol_temizle(self) -> None:
        self.konsol.configure(state="normal")
        self.konsol.delete("1.0", END)
        self.konsol.configure(state="disabled")

    def _konsol_kopyala(self) -> None:
        metin = self.konsol.get("1.0", END).strip()
        if metin:
            self.clipboard_clear()
            self.clipboard_append(metin)
            self.durum_deg.set("Konsol panoya kopyalandı.")

    def _konsol_kaydet(self) -> None:
        yol = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Metin", "*.txt")],
            initialfile=f"konsol_{datetime.now():%Y%m%d_%H%M}.txt")
        if not yol:
            return
        try:
            Path(yol).write_text(self.konsol.get("1.0", END),
                                 encoding="utf-8")
            self.durum_deg.set(f"Konsol kaydedildi: {yol}")
        except Exception as hata:
            messagebox.showerror("Hata", str(hata))

    def _son_satir_ozet(self) -> str:
        satirlar = self.konsol.get("1.0", END).strip().splitlines()
        if not satirlar:
            return "Hazır"
        son = next((s for s in reversed(satirlar) if s.strip()), "Hazır")
        return son.strip()[:150]

    # ------------------------------------------------------------------
    #  Ürün listesi
    # ------------------------------------------------------------------
    def liste_doldur(self) -> None:
        arama = self.arama_deg.get().strip().lower()
        mevcut = {self.agac.item(i, "values")[0]: i
                  for i in self.agac.get_children()}

        self.agac.delete(*self.agac.get_children())
        sayac = 0
        son_fiyatlar = self._son_fiyat_haritasi()

        for u in self.ayar.get("urunler", []):
            ad = u.get("ad", "")
            if arama and arama not in ad.lower() \
                    and arama not in u.get("url", "").lower() \
                    and arama not in u.get("selector", "").lower():
                continue
            fiyat, durum = son_fiyatlar.get(ad, (None, "—"))
            etiket = ""
            if durum == "▲":
                etiket = "yukari"
            elif durum == "▼":
                etiket = "asagi"

            deger = (ad, cekirdek.fiyat_bicimle(fiyat,
                                                self._para_ad(ad)), durum)
            iid = self.agac.insert("", END, values=deger, tags=(etiket,))
            sayac += 1

        self.agac.tag_configure("yukari", foreground=RENKLER["kirmizi"])
        self.agac.tag_configure("asagi", foreground=RENKLER["yesil"])
        self.sayac_deg.set(f"{sayac} ürün"
                           + (f"  (filtre: '{arama}')" if arama else ""))
        self.sag_durum.set(self._sag_durum_metni())
        self.kartlari_guncelle(son_fiyatlar)

    def _para_ad(self, ad: str) -> str:
        bag = cekirdek.db_ac()
        satir = bag.execute(
            "SELECT para FROM fiyatlar WHERE ad = ? "
            "ORDER BY id DESC LIMIT 1", (ad,)).fetchone()
        bag.close()
        return satir[0] if satir and satir[0] else ""

    def _son_fiyat_haritasi(self) -> dict:
        """{ad: (fiyat, yön)} — en son iki kaydı karşılaştırır."""
        if not cekirdek.DB_YOL.exists():
            return {}
        bag = cekirdek.db_ac()
        satirlar = bag.execute(
            "SELECT ad, fiyat, zaman FROM fiyatlar ORDER BY ad, id"
        ).fetchall()
        bag.close()

        grup: dict[str, list] = {}
        for ad, fiyat, zaman in satirlar:
            grup.setdefault(ad, []).append((zaman, fiyat))

        sonuc = {}
        for ad, liste in grup.items():
            if not liste or liste[-1][1] is None:
                sonuc[ad] = (None, "—")
                if len(liste) >= 2 and liste[-1][1] is not None \
                        and liste[-2][1] is not None:
                    pass
                continue
            son_deger = liste[-1][1]
            yon = "—"
            if len(liste) >= 2 and liste[-2][1]:
                onceki = liste[-2][1]
                if son_deger > onceki:
                    yon = "▲"
                elif son_deger < onceki:
                    yon = "▼"
                else:
                    yon = "="
            sonuc[ad] = (son_deger, yon)
        return sonuc

    def _secim_degisti(self) -> None:
        self.gecmis_yenile()
        self.grafik_ciz()

    def secili_urunler(self) -> list[str]:
        return [self.agac.item(i, "values")[0]
                for i in self.agac.selection()]

    def secili_urun(self) -> str | None:
        s = self.secili_urunler()
        return s[0] if s else None

    def urun_bul(self, ad: str) -> dict | None:
        for u in self.ayar.get("urunler", []):
            if u.get("ad") == ad:
                return u
        return None

    # ------------------------------------------------------------------
    #  Ürün işlemleri
    # ------------------------------------------------------------------
    def urun_ekle(self, url_on: str = "", ad_on: str = ""):
        veri = ({"ad": ad_on, "url": url_on, "selector": "", "not": ""}
                if url_on else None)
        p = UrunPenceresi(self, "Yeni Ürün Ekle", veri)
        self.wait_window(p)
        if not p.sonuc:
            return
        if any(u.get("ad") == p.sonuc["ad"]
               for u in self.ayar.get("urunler", [])):
            messagebox.showwarning("Yinelenen ad",
                                   "Bu adda bir ürün zaten var.")
            return
        self.ayar.setdefault("urunler", []).append(p.sonuc)
        self._config_kaydet()
        self.liste_doldur()
        self.konsol_yaz(f"＋ Ürün eklendi: {p.sonuc['ad']}")
        self.durum_deg.set(f"Ürün eklendi: {p.sonuc['ad']}")
        if url_on and hasattr(self, "url_on"):
            self._url_on_bit()

    def urun_duzenle(self):
        ad = self.secili_urun()
        if not ad:
            messagebox.showinfo("Seçim yok",
                                "Düzenlemek için listeden bir ürün seçin.")
            return
        mevcut = self.urun_bul(ad)
        if not mevcut:
            return
        p = UrunPenceresi(self, "Ürünü Düzenle", mevcut)
        self.wait_window(p)
        if not p.sonuc:
            return
        yeni_ad = p.sonuc["ad"]
        if yeni_ad != ad and any(
                u.get("ad") == yeni_ad for u in self.ayar.get("urunler", [])):
            messagebox.showwarning("Yinelenen ad", "Bu adda ürün zaten var.")
            return
        # ad değiştiyse geçmişteki adı da güncelle
        if yeni_ad != ad:
            self._gecmiste_ad_degistir(ad, yeni_ad)
        idx = self.ayar["urunler"].index(mevcut)
        self.ayar["urunler"][idx] = p.sonuc
        self._config_kaydet()
        self.liste_doldur()
        self.konsol_yaz(f"✎ Ürün güncellendi: {yeni_ad}")

    def _gecmiste_ad_degistir(self, eski: str, yeni: str):
        try:
            bag = cekirdek.db_ac()
            bag.execute("UPDATE fiyatlar SET ad = ? WHERE ad = ?",
                        (yeni, eski))
            bag.commit()
            bag.close()
        except Exception as hata:
            self.konsol_yaz(f"[!] Geçmiş adı güncellenemedi: {hata}")

    def urun_sil(self):
        secim = self.secili_urunler()
        if not secim:
            messagebox.showinfo("Seçim yok", "Silmek için ürün seçin.")
            return
        soru = (f"{len(secim)} ürün silinsin mi?\n\n"
                + "\n".join(secim[:10])
                + ("\n…" if len(secim) > 10 else "")
                + "\n\nFiyat geçmişi de silinir.")
        if not messagebox.askyesno("Silme onayı", soru):
            return
        for ad in secim:
            self.ayar["urunler"] = [
                u for u in self.ayar.get("urunler", []) if u.get("ad") != ad]
            try:
                bag = cekirdek.db_ac()
                bag.execute("DELETE FROM fiyatlar WHERE ad = ?", (ad,))
                bag.commit()
                bag.close()
            except Exception:
                pass
        self._config_kaydet()
        self.liste_doldur()
        self.konsol_yaz(f"🗑 {len(secim)} ürün silindi.")
        self.gecmis_yenile()
        self.grafik_ciz()

    # ------------------------------------------------------------------
    #  Tarama
    # ------------------------------------------------------------------
    def tarama_baslat(self, secili: bool = False) -> bool:
        if self.tarama_suriyor:
            messagebox.showinfo("Tarama sürüyor",
                                "Zaten bir tarama çalışıyor. Önce durdurun.")
            return False
        urunler = self.ayar.get("urunler", [])
        if not urunler:
            messagebox.showinfo("Ürün yok",
                                "Önce sol taraftan URL ile rakip ürün "
                                "ekleyin.")
            return False

        secili_adlar = self.secili_urunler() if secili else None
        if secili and not secili_adlar:
            messagebox.showinfo("Seçim yok",
                                "Taranacak ürünleri listeden seçin "
                                "(Ctrl+ ile çoklu seçim).")
            return False

        self.tarama_suriyor = True
        self.iptal_bayragi.clear()
        self.tara_btn.state(["disabled"])
        self.secili_btn.state(["disabled"])
        self.durdur_btn.state(["!disabled"])
        self.ilerleme["value"] = 0
        self._takip_guncelle()
        self.durum_deg.set("Taranıyor…")
        self.konsol_yaz("\n" + "=" * 60)
        self.konsol_yaz(f"▶ Tarama başladı — {datetime.now():%H:%M:%S}")
        self.konsol_yaz("=" * 60)

        yazici = KuyrukYazici(self.kuyruk)

        def ilerleme(i: int, toplam: int, ad: str):
            def guncelle():
                yuzde = int(i / toplam * 100) if toplam else 0
                self.ilerleme["value"] = yuzde
                self.ilerleme_deger.set(f"{i}/{toplam}  ·  {yuzde}%  ·  {ad}")
            self._ana_kuyruk.put((lambda _v: guncelle(), None))

        def is_calistir():
            try:
                sonuclar = cekirdek.tarama_yap(
                    self.ayar,
                    log=yazici,
                    ilerleme=ilerleme,
                    iptal=self.iptal_bayragi.is_set,
                    secili_urunler=secili_adlar,
                )
            except Exception:
                yazici("[!] Beklenmeyen hata:\n" + traceback.format_exc())
                sonuclar = []
            self._ana_kuyruk.put((self._tarama_bitti, sonuclar))

        threading.Thread(target=is_calistir, daemon=True).start()
        return True

    def _tarama_bitti(self, sonuclar: list[dict]):
        self.tarama_suriyor = False
        self.tara_btn.state(["!disabled"])
        self.secili_btn.state(["!disabled"])
        self.durdur_btn.state(["disabled"])
        self.ilerleme["value"] = 100
        self.son_tarama = sonuclar or []
        self.sonuclari_doldur(self.son_tarama)
        self.liste_doldur()
        self.ust_sayfa.select(0)

        degisen = sum(1 for s in self.son_tarama if s.get("durum") == "degisti")
        hata = sum(1 for s in self.son_tarama
                   if s.get("durum") in ("hata", "bulunamadi"))
        self.ozet_deg.set(
            f"{len(self.son_tarama)} ürün tarandı  ·  "
            f"{degisen} değişiklik  ·  {hata} sorun")
        self.durum_deg.set("Tarama tamamlandı.")
        self.ilerleme_deger.set("Tamamlandı")
        self._tekrar_planla()

    def tarama_durdur(self):
        self.otomatik_takip = False
        self._periyot_iptal()
        self._takip_guncelle()
        if not self.tarama_suriyor:
            return
        self.iptal_bayragi.set()
        self.durum_deg.set("Durduruluyor…")
        self.konsol_yaz("■ Tarama durduruluyor…")

    def sonuclari_doldur(self, sonuclar: list[dict]):
        self.sonuc_agac.delete(*self.sonuc_agac.get_children())
        for s in sonuclar:
            durum_adi = {
                "ilk": "İlk kayıt", "degismedi": "Değişmedi",
                "degisti": "▲ Değişti", "bulunamadi": "Bulunamadı",
                "robots": "robots.txt", "hata": "Hata", "iptal": "İptal",
            }.get(s.get("durum", ""), s.get("durum", ""))
            yuzde = ("—" if s.get("yuzde") is None
                     else f"{s['yuzde']:+.1f}%")
            iid = self.sonuc_agac.insert("", END, values=(
                s.get("ad", ""),
                cekirdek.fiyat_bicimle(s.get("onceki"), s.get("para", "")),
                cekirdek.fiyat_bicimle(s.get("fiyat"), s.get("para", "")),
                yuzde,
                durum_adi,
                s.get("mesaj", ""),
            ))
            d = s.get("durum")
            if d == "degisti":
                self.sonuc_agac.item(iid, tags=("degisti",))
            elif d in ("hata", "bulunamadi", "robots"):
                self.sonuc_agac.item(iid, tags=("sorun",))
            elif d == "ilk":
                self.sonuc_agac.item(iid, tags=("ilk",))
        self.sonuc_agac.tag_configure("degisti",
                                      foreground=RENKLER["kirmizi"],
                                      background="#2a1620")
        self.sonuc_agac.tag_configure("sorun",
                                      foreground=RENKLER["sari"])
        self.sonuc_agac.tag_configure("ilk",
                                      foreground=RENKLER["vurgu"])

    def sonuclari_temizle(self):
        self.sonuc_agac.delete(*self.sonuc_agac.get_children())
        self.ozet_deg.set("Temizlendi.")

    # ------------------------------------------------------------------
    #  Rakip Radar (pazaryeri-radar)
    # ------------------------------------------------------------------
    def _radar_sayfasi_ekle(self):
        sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame", padding=6)
        self.ust_sayfa.add(sayfa, text="  🏆 Rakip Radar  ")
        self.radar_sayfa = sayfa
        sayfa.rowconfigure(2, weight=1)
        sayfa.columnconfigure(0, weight=1)

        radar_ayar = self.ayar.get("radar") or {}

        # --- kontrol satırı ---
        ust = ttk.Frame(sayfa, style="TTk.TFrame")
        ust.grid(row=0, column=0, columnspan=2, sticky=(W, E), pady=(0, 6))

        ttk.Label(ust, text="Sorgu:").pack(side=LEFT, padx=(0, 4))
        self.radar_sorgu = StringVar(
            value=radar_ayar.get("sorgu", "iphone 15 kılıf"))
        ttk.Entry(ust, textvariable=self.radar_sorgu, width=30).pack(side=LEFT)

        ttk.Label(ust, text="  Platform:").pack(side=LEFT, padx=(12, 2))
        varsayilan_mp = radar_ayar.get(
            "platformlar", ["trendyol", "n11", "hepsiburada"])
        self.radar_mp: dict[str, BooleanVar] = {}
        for ad in ("trendyol", "n11", "hepsiburada"):
            deg = BooleanVar(value=ad in varsayilan_mp)
            self.radar_mp[ad] = deg
            ttk.Checkbutton(ust, text=ad, variable=deg).pack(
                side=LEFT, padx=(0, 6))

        ttk.Label(ust, text="  Sayfa:").pack(side=LEFT, padx=(8, 2))
        try:
            radar_sayfa = int(radar_ayar.get("sayfa", 2))
        except (TypeError, ValueError):
            radar_sayfa = 2
        self.radar_sayfa_sayi = IntVar(value=radar_sayfa)
        ttk.Spinbox(ust, from_=1, to=5, width=4,
                    textvariable=self.radar_sayfa_sayi).pack(side=LEFT)

        self.radar_tara_btn = ttk.Button(
            ust, text="▶  Radar Taraması", command=self.radar_baslat)
        self.radar_tara_btn.pack(side=LEFT, padx=(12, 4))
        self._ipucu(self.radar_tara_btn,
                    "Ürün adını pazaryerlerinde arayıp satıcıların "
                    "listelerini toplar (F7).")
        self.radar_durdur_btn = ttk.Button(
            ust, text="■ Durdur", command=self.radar_durdur, state="disabled")
        self.radar_durdur_btn.pack(side=LEFT, padx=4)
        self._ipucu(self.radar_durdur_btn,
                    "Devam eden radar taramasını iptal eder.")
        self._ipucu(ttk.Button(ust, text="📄 Raporu Aç",
                               command=self.radar_raporu_ac),
                    "Son radarın markdown raporunu metin olarak açar."
                    ).pack(side=LEFT, padx=4)
        self._ipucu(ttk.Button(ust, text="CSV Aktar",
                               command=lambda: self._csv_aktar("radar")),
                    "Satıcı tablosunu CSV olarak indirir."
                    ).pack(side=LEFT, padx=4)

        # --- özet ---
        self.radar_ozet = StringVar(
            value="Sorgu yazıp 'Radar Taraması' deyin. "
                  "Satış rakamları tahminidir.")
        ttk.Label(sayfa, textvariable=self.radar_ozet,
                  font=("Segoe UI", 10, "bold")).grid(
            row=1, column=0, sticky=(W, E), pady=(0, 6))

        # --- satıcı tablosu ---
        kolonlar = ("sira", "satici", "platform", "liste", "pay", "yorum",
                    "rozet", "satis", "ciro", "guven")
        basliklar = {"sira": "#", "satici": "Satıcı", "platform": "Platform",
                     "liste": "Liste", "pay": "Pay %", "yorum": "Yorum",
                     "rozet": "Rozetli", "satis": "30g satış (alt–üst)",
                     "ciro": "Tahmini ciro ₺", "guven": "Güven"}
        genislik = {"sira": 34, "satici": 210, "platform": 100, "liste": 56,
                    "pay": 62, "yorum": 76, "rozet": 64, "satis": 170,
                    "ciro": 190, "guven": 70}
        self.radar_agac = ttk.Treeview(sayfa, columns=kolonlar,
                                       show="headings", height=7)
        for k in kolonlar:
            self.radar_agac.heading(k, text=basliklar[k])
            self.radar_agac.column(
                k, width=genislik[k],
                anchor=W if k in ("satici", "platform") else CENTER)
        r_d = ttk.Scrollbar(sayfa, orient="vertical",
                            command=self.radar_agac.yview)
        r_y = ttk.Scrollbar(sayfa, orient="horizontal",
                            command=self.radar_agac.xview)
        self.radar_agac.configure(yscrollcommand=r_d.set,
                                  xscrollcommand=r_y.set)
        self.radar_agac.grid(row=2, column=0, sticky=(N, S, E, W))
        r_d.grid(row=2, column=1, sticky=(N, S))
        r_y.grid(row=3, column=0, sticky=(W, E))
        self.radar_agac.tag_configure("lider", background="#0e2a3a",
                                      foreground=RENKLER["vurgu"])

        ttk.Label(
            sayfa, foreground=RENKLER["gri"],
            text="Alt sınır Trendyol satış rozeti (kesin minimum), üst sınır "
                 "yorum delta'sı × satış/yorum oranıdır. Aynı sorguyu "
                 "günlerce sonra tekrar çalıştırınca aralık sıkışır.",
        ).grid(row=4, column=0, sticky=W, pady=(4, 0))

    def radar_baslat(self):
        if self.radar_suriyor:
            messagebox.showinfo("Radar çalışıyor",
                                "Zaten bir radar taraması var. Önce durdurun.")
            return
        sorgu = self.radar_sorgu.get().strip()
        if not sorgu:
            messagebox.showwarning("Sorgu yok",
                                   "Aramak istediğiniz kelimeyi yazın.")
            return
        secili = [ad for ad, deg in self.radar_mp.items() if deg.get()]
        if not secili:
            messagebox.showwarning("Platform yok",
                                   "En az bir platform seçin.")
            return

        kok = radar_kok_bul()
        if not (kok / "radar").is_dir():
            messagebox.showerror("Radar bulunamadı",
                                 f"pazaryeri-radar klasörü yok:\n{kok}")
            return

        try:
            sayfa = max(1, int(self.radar_sayfa_sayi.get()))
        except (TypeError, ValueError):
            sayfa = 2

        # ayarları sakla
        self.ayar.setdefault("radar", {}).update(
            {"sorgu": sorgu, "platformlar": secili, "sayfa": sayfa})
        self._config_kaydet()

        json_yol = kok / "data" / "out" / "radar_gui.json"
        if json_yol.exists():
            json_yol.unlink()

        komut = [str(radar_python_bul(kok)), "-m", "radar", sorgu,
                 "-m", ",".join(secili), "-p", str(sayfa),
                 "--json", str(json_yol)]

        self.radar_suriyor = True
        self.radar_iptal = False
        self.radar_tara_btn.state(["disabled"])
        self.radar_durdur_btn.state(["!disabled"])
        self.radar_ozet.set(f"'{sorgu}' taranıyor… "
                            f"({', '.join(secili)}, {sayfa} sayfa)")
        self.konsol_yaz("=" * 60)
        self.konsol_yaz(f"🏆 Radar başladı: '{sorgu}' → "
                        f"{', '.join(secili)} ({sayfa} sayfa)")
        self.ilerleme.configure(mode="indeterminate")
        self.ilerleme.start(12)

        yazici = KuyrukYazici(self.kuyruk)

        def is_calistir():
            kod = -1
            hata = None
            try:
                ortam = dict(os.environ, PYTHONIOENCODING="utf-8")
                surec = subprocess.Popen(
                    komut, cwd=str(kok), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1, env=ortam)
                self.radar_surec = surec
                for satir in surec.stdout:
                    satir = satir.rstrip()
                    if satir:
                        yazici(satir)
                kod = surec.wait()
            except Exception:
                hata = traceback.format_exc()
            finally:
                self.radar_surec = None

            sonuc = None
            if kod == 0 and json_yol.exists():
                try:
                    sonuc = json.loads(json_yol.read_text(encoding="utf-8"))
                except Exception:
                    hata = traceback.format_exc()
            self._ana_kuyruk.put(
                (lambda _v: self._radar_bitti(sonuc, kod, hata), None))

        threading.Thread(target=is_calistir, daemon=True).start()

    def radar_durdur(self):
        if not self.radar_suriyor:
            return
        self.radar_iptal = True
        if self.radar_surec:
            try:
                self.radar_surec.terminate()
            except Exception:
                pass
        self.konsol_yaz("■ Radar durduruluyor…")
        self.durum_deg.set("Radar durduruluyor…")

    def _radar_bitti(self, sonuc: dict | None, kod: int, hata: str | None):
        self.radar_suriyor = False
        self.radar_tara_btn.state(["!disabled"])
        self.radar_durdur_btn.state(["disabled"])
        try:
            self.ilerleme.stop()
            self.ilerleme.configure(mode="determinate")
        except Exception:
            pass
        self.ilerleme["value"] = 100 if sonuc else 0

        if hata:
            self.konsol_yaz("[!] Radar hatası:\n" + hata)
        if not sonuc:
            mesaj = ("Durduruldu." if self.radar_iptal else
                     f"Radar tamamlanamadı (kod {kod}). Konsola bakın.")
            self.radar_ozet.set(mesaj)
            self.durum_deg.set("Radar tamamlanmadı.")
            return

        self.radar_sonuc = sonuc
        self._radar_tablo_doldur(sonuc)

        oz = sonuc.get("estimate_summary", {}) or {}
        metin = (f"{sonuc.get('query', '')} · "
                 f"{oz.get('products_total', 0)} ürün · "
                 f"{oz.get('sellers', 0)} satıcı · "
                 f"tahmini 30g: {_sayi(oz.get('units_lo'))}–"
                 f"{_sayi(oz.get('units_hi'))} adet")
        if sonuc.get("delta_days"):
            metin += f" · delta {sonuc['delta_days']:.1f} gün"
        self.radar_ozet.set(metin)
        self.durum_deg.set("Radar taraması tamamlandı.")
        self.ust_sayfa.select(self.radar_sayfa)
        self.konsol_yaz(f"🏁 Radar bitti: {oz.get('sellers', 0)} satıcı · "
                        f"rapor: {sonuc.get('report')}")

    def _radar_tablo_doldur(self, sonuc: dict):
        self.radar_agac.delete(*self.radar_agac.get_children())
        for r in sonuc.get("rows", []):
            iid = self.radar_agac.insert("", END, values=(
                r.get("rank"),
                r.get("seller_name") or r.get("seller_id"),
                r.get("platform", r.get("marketplace")),
                r.get("listings"),
                r.get("share_listings"),
                _sayi(r.get("reviews")),
                r.get("badge_products", 0),
                f"{_sayi(r.get('units_lo'))}–{_sayi(r.get('units_hi'))}",
                f"{_sayi(r.get('revenue_lo'))}–{_sayi(r.get('revenue_hi'))}",
                r.get("confidence", ""),
            ))
            if r.get("rank") == 1:
                self.radar_agac.item(iid, tags=("lider",))

    def radar_raporu_ac(self):
        rapor = (self.radar_sonuc or {}).get("report")
        if not rapor or not Path(rapor).exists():
            adaylar = sorted(
                (radar_kok_bul() / "data" / "out").glob("*/leaderboard.md"))
            rapor = str(adaylar[-1]) if adaylar else None
        if not rapor:
            messagebox.showinfo("Rapor yok",
                                "Önce bir radar taraması yapın.")
            return
        self._url_ac(str(rapor))

    # ------------------------------------------------------------------
    #  Ürün Arama (4 pazaryerinde toplu arama)
    # ------------------------------------------------------------------
    def _arama_sayfasi_ekle(self):
        sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame", padding=6)
        self.ust_sayfa.add(sayfa, text="  🔍 Ürün Arama  ")
        self.arama_sayfa = sayfa
        sayfa.rowconfigure(2, weight=1)
        sayfa.columnconfigure(0, weight=1)

        # --- araç satırı ---
        ust = ttk.Frame(sayfa, style="TTk.TFrame")
        ust.grid(row=0, column=0, columnspan=2, sticky=(W, E), pady=(0, 6))

        self._ipucu(ttk.Button(ust, text="🌐 Tarayıcıda Aç",
                               command=self.paz_ac),
                    "Seçili ürünün sayfasını varsayılan tarayıcıda açar."
                    ).pack(side=LEFT, padx=(0, 4))
        self._ipucu(ttk.Button(ust, text="＋ Takibe Al",
                               command=self.paz_takibe_al),
                    "Seçili ürünü fiyat takip listesine ekler "
                    "(ad + link hazır gelir, Kaydet'e basın)."
                    ).pack(side=LEFT, padx=4)
        self._ipucu(ttk.Button(ust, text="📋 Linki Kopyala",
                               command=self.paz_kopyala),
                    "Seçili ürünün linkini panoya kopyalar."
                    ).pack(side=LEFT, padx=4)
        self._ipucu(ttk.Button(ust, text="🗑 Temizle",
                               command=self.paz_temizle),
                    "Arama sonuçlarını tablodan siler."
                    ).pack(side=LEFT, padx=4)
        self._ipucu(ttk.Button(ust, text="📄 CSV Aktar",
                               command=lambda: self._csv_aktar("pazarama")),
                    "Sonuç tablosunu Excel uyumlu CSV olarak kaydeder."
                    ).pack(side=LEFT, padx=4)

        # --- özet ---
        self.paz_ozet = StringVar(
            value="Soldaki kutuya ürün adı yazıp 🔍'e basın: fiyatlar "
                  "Trendyol · Hepsiburada · N11 · Amazon karşılaştırmalı "
                  "buraya düşer.")
        ttk.Label(sayfa, textvariable=self.paz_ozet,
                  font=("Segoe UI", 10, "bold")).grid(
            row=1, column=0, sticky=(W, E), pady=(0, 6))

        # --- sonuç tablosu ---
        self.paz_agac = ttk.Treeview(
            sayfa, columns=("site", "ad", "fiyat", "satici", "yorum", "url"),
            show="headings", height=7)
        kolon = [("site", "Site", 88), ("ad", "Ürün", 330),
                 ("fiyat", "Fiyat", 96), ("satici", "Satıcı", 150),
                 ("yorum", "Yorum", 56), ("url", "Link", 300)]
        for k, baslik, genislik in kolon:
            self.paz_agac.heading(k, text=baslik)
            self.paz_agac.column(
                k, width=genislik,
                anchor=E if k == "fiyat" else
                (CENTER if k in ("site", "yorum") else W))
        r_d = ttk.Scrollbar(sayfa, orient="vertical",
                            command=self.paz_agac.yview)
        r_y = ttk.Scrollbar(sayfa, orient="horizontal",
                            command=self.paz_agac.xview)
        self.paz_agac.configure(yscrollcommand=r_d.set,
                                xscrollcommand=r_y.set)
        self.paz_agac.grid(row=2, column=0, sticky=(N, S, E, W))
        r_d.grid(row=2, column=1, sticky=(N, S))
        r_y.grid(row=3, column=0, sticky=(W, E))
        self.paz_agac.bind("<Double-1>", self.paz_cift_tik)

        self.paz_veri: dict | None = None
        self.paz_suriyor = False
        self.paz_surec = None
        self.paz_url_harita: dict[str, str] = {}

    def arama_giris(self):
        """Arama kutusundaki değere göre arama yapar ya da link ekler."""
        deger = self.url_on.get().strip()
        if deger == URL_IPUCU:
            deger = ""
        if not deger:
            messagebox.showinfo("Arama",
                                "Bir ürün adı yazın (örn. iphone 15).")
            return
        if deger.startswith(("http://", "https://")):
            self.url_ile_ekle()
            return
        self.paz_arama_baslat(deger)

    @staticmethod
    def _tl(deger) -> str:
        """39999.0 → '39.999,00 TL' (yoksa '-')."""
        if deger is None:
            return "-"
        try:
            metin = f"{float(deger):,.2f}"
        except (TypeError, ValueError):
            return str(deger)
        return metin.replace(",", "X").replace(".", ",").replace("X", ".") \
            + " TL"

    def paz_arama_baslat(self, sorgu: str | None = None):
        if self.paz_suriyor:
            self.konsol_yaz("[!] Ürün araması zaten çalışıyor…")
            return
        sorgu = (sorgu or "").strip()
        if not sorgu:
            return
        kok = radar_kok_bul()
        if not (kok / "radar").is_dir():
            messagebox.showerror(
                "pazaryeri-radar bulunamadı",
                f"pazaryeri-radar klasörü yok:\n{kok}")
            return

        json_yol = kok / "data" / "out" / "paz_arama_gui.json"
        if json_yol.exists():
            json_yol.unlink()

        py = radar_python_bul(kok)
        komut = [str(py), "-m", "radar", sorgu, "--mod", "urun",
                 "-m", "trendyol,n11,hepsiburada,amazon", "-p", "1",
                 "--sayfa-bekleme", "1", "--json", str(json_yol)]

        self.paz_suriyor = True
        if hasattr(self, "paz_ara_btn"):
            self.paz_ara_btn.configure(state="disabled")
        self.ust_sayfa.select(self.arama_sayfa)
        mesaj = f"🔍 '{sorgu}' 4 sitede aranıyor…"
        self.paz_ozet.set(mesaj)
        self.konsol_yaz(mesaj)
        self.durum_deg.set(mesaj)
        self.ilerleme.configure(mode="indeterminate")
        self.ilerleme.start(12)

        yazici = KuyrukYazici(self.kuyruk)

        def is_calistir():
            kod = -1
            hata = None
            try:
                ortam = dict(os.environ, PYTHONIOENCODING="utf-8")
                surec = subprocess.Popen(
                    komut, cwd=str(kok), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1, env=ortam)
                self.paz_surec = surec
                for satir in surec.stdout:
                    satir = satir.rstrip()
                    if satir:
                        yazici(satir)
                kod = surec.wait()
            except Exception:
                hata = traceback.format_exc()
            finally:
                self.paz_surec = None

            veri = None
            if json_yol.exists():
                try:
                    veri = json.loads(json_yol.read_text(encoding="utf-8"))
                except Exception:
                    hata = traceback.format_exc()
            self._ana_kuyruk.put(
                (lambda _v: self._paz_bitti(veri, kod, hata), None))

        threading.Thread(target=is_calistir, daemon=True).start()

    def _paz_bitti(self, veri: dict | None, kod: int, hata: str | None):
        self.paz_suriyor = False
        if hasattr(self, "paz_ara_btn"):
            self.paz_ara_btn.configure(state="normal")
        try:
            self.ilerleme.stop()
            self.ilerleme.configure(mode="determinate")
        except Exception:
            pass
        self.ilerleme["value"] = 100 if veri else 0

        if hata:
            self.konsol_yaz("[!] Ürün arama hatası:\n" + hata)
        if not veri:
            self.paz_ozet.set(
                f"Arama tamamlanamadı (kod {kod}). Konsola bakın.")
            self.durum_deg.set("Ürün araması tamamlanmadı.")
            return
        self.paz_goster(veri)

    def paz_goster(self, veri: dict):
        """Arama JSON'unu tabloya döker (fiyat artan sırayla)."""
        self.paz_veri = veri
        self.paz_agac.delete(*self.paz_agac.get_children())
        self.paz_url_harita.clear()

        satirlar = []
        for s in veri.get("siteler", []):
            site = SITE_ETIKET.get(s.get("site", ""), s.get("site", ""))
            for u in s.get("urunler", []):
                satirlar.append((site, u))
        satirlar.sort(key=lambda t: (t[1].get("fiyat") is None,
                                     t[1].get("fiyat") or 0.0))

        for site, u in satirlar:
            iid = self.paz_agac.insert(
                "", END, values=(site, u.get("ad", ""),
                                 self._tl(u.get("fiyat")),
                                 u.get("satici", "") or "",
                                 u.get("yorum") or "",
                                 u.get("url", "") or ""))
            self.paz_url_harita[iid] = u.get("url", "") or ""

        parcalar = [f"'{veri.get('sorgu', '')}'"]
        for s in veri.get("siteler", []):
            site = SITE_ETIKET.get(s.get("site", ""), s.get("site", ""))
            if s.get("hata"):
                parcalar.append(f"{site}: ✗")
            else:
                parcalar.append(f"{site} {len(s.get('urunler', []))}")
        parcalar.append(f"toplam {veri.get('toplam', len(satirlar))}")
        ozet = " · ".join(parcalar)
        self.paz_ozet.set(ozet)
        self.durum_deg.set(f"Ürün araması: {veri.get('toplam', 0)} sonuç.")

        for s in veri.get("siteler", []):
            if s.get("hata"):
                self.konsol_yaz(
                    f"[!] {s.get('site')}: {s['hata']}")
        self.konsol_yaz(
            f"🔍 Arama tamam: {veri.get('toplam', 0)} sonuç gösteriliyor.")
        self.ust_sayfa.select(self.arama_sayfa)

    def _paz_secili(self) -> tuple[str, tuple]:
        """(url, treeview satır değerleri); seçilmediyse ('', ())."""
        iid = self.paz_agac.focus()
        if not iid:
            return "", ()
        return self.paz_url_harita.get(iid, ""), self.paz_agac.item(
            iid, "values") or ()

    def paz_cift_tik(self, _olay):
        url, _deger = self._paz_secili()
        if url:
            self._url_ac(url)

    def paz_ac(self):
        url, _d = self._paz_secili()
        if not url:
            messagebox.showinfo("Seçim yok",
                                "Açmak için listeden bir ürün seçin.")
            return
        self._url_ac(url)

    def paz_kopyala(self):
        url, _d = self._paz_secili()
        if not url:
            messagebox.showinfo("Seçim yok",
                                "Kopyalamak için bir ürün seçin.")
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        self.update()
        self.durum_deg.set("Link kopyalandı.")
        self.konsol_yaz(f"📋 Kopyalandı: {url}")

    def paz_takibe_al(self):
        url, deger = self._paz_secili()
        if not url:
            messagebox.showinfo("Seçim yok",
                                "Eklemek için bir ürün seçin.")
            return
        ad = deger[1] if len(deger) > 1 else ""
        self.urun_ekle(url_on=url, ad_on=ad)

    def paz_temizle(self):
        self.paz_agac.delete(*self.paz_agac.get_children())
        self.paz_url_harita.clear()
        self.paz_veri = None
        self.paz_ozet.set("Sonuçlar temizlendi. Yeni arama için soldaki "
                          "kutuya ürün adı yazın.")
        self.durum_deg.set("Ürün arama temizlendi.")

    # ------------------------------------------------------------------
    #  İthalat Radarı (importyeti)
    # ------------------------------------------------------------------
    def _ithalat_sayfasi_ekle(self):
        sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame", padding=6)
        self.ust_sayfa.add(sayfa, text="  🌍 İthalat Radarı  ")
        self.ithalat_sayfa = sayfa
        sayfa.rowconfigure(2, weight=1)
        sayfa.columnconfigure(0, weight=1)

        # --- kontrol satırı ---
        ust = ttk.Frame(sayfa, style="TTk.TFrame")
        ust.grid(row=0, column=0, columnspan=2, sticky=(W, E), pady=(0, 6))

        ttk.Label(ust, text="Firma / Marka:").pack(side=LEFT, padx=(0, 4))
        self.ithalat_sorgu = StringVar(value="")
        gir = ttk.Entry(ust, textvariable=self.ithalat_sorgu, width=34)
        gir.pack(side=LEFT)
        gir.bind("<Return>", lambda _e: self.ithalat_ara())

        self.ithalat_ara_btn = ttk.Button(
            ust, text="▶  Ara", command=self.ithalat_ara)
        self.ithalat_ara_btn.pack(side=LEFT, padx=(6, 4))
        self._ipucu(self.ithalat_ara_btn,
                    "ImportYeti'de firma/marka arar: tedarikçileri, "
                    "ülke dağılımını ve sefer kayıtlarını getirir.")
        self.ithalat_geri_btn = ttk.Button(
            ust, text="⬅ Geri", command=self.ithalat_geri, state="disabled")
        self.ithalat_geri_btn.pack(side=LEFT, padx=4)
        self._ipucu(self.ithalat_geri_btn,
                    "Bir önceki görüntüye döner (arama ↔ detay).")
        self._ipucu(ttk.Button(ust, text="📄 CSV Aktar",
                               command=lambda: self._csv_aktar("ithalat")),
                    "Listeyi CSV olarak indirir."
                    ).pack(side=LEFT, padx=4)
        self._ipucu(ttk.Button(ust, text="🌐 Tarayıcıda Aç",
                               command=self.ithalat_tarayici),
                    "Aynı sayfayı importyeti.com'da tarayıcıda açar."
                    ).pack(side=LEFT, padx=4)

        # --- özet ---
        self.ithalat_ozet = StringVar(
            value="Firma/marka adı yazıp '▶ Ara' deyin. Sonuçlara çift "
                  "tıklayınca tedarikçiler/müşteriler açılır. "
                  "Veriler: ABD denizyolu ithalat kayıtları (ImportYeti).")
        ttk.Label(sayfa, textvariable=self.ithalat_ozet,
                  font=("Segoe UI", 10, "bold")).grid(
            row=1, column=0, sticky=(W, E), pady=(0, 6))

        # --- tablo ---
        self.ithalat_agac = ttk.Treeview(
            sayfa, columns=("tur", "ad", "ulke", "adres", "sefer",
                            "son_sefer"), show="headings", height=7)
        r_d = ttk.Scrollbar(sayfa, orient="vertical",
                            command=self.ithalat_agac.yview)
        r_y = ttk.Scrollbar(sayfa, orient="horizontal",
                            command=self.ithalat_agac.xview)
        self.ithalat_agac.configure(yscrollcommand=r_d.set,
                                    xscrollcommand=r_y.set)
        self.ithalat_agac.grid(row=2, column=0, sticky=(N, S, E, W))
        r_d.grid(row=2, column=1, sticky=(N, S))
        r_y.grid(row=3, column=0, sticky=(W, E))
        self.ithalat_agac.bind("<Double-1>", self.ithalat_cift_tik)

        self.ithalat_mod = "arama"
        self.ithalat_veri: dict | None = None
        self.ithalat_gecmis: list[tuple[str, dict]] = []
        self.ithalat_url_harita: dict[str, str] = {}
        self.ithalat_suriyor = False
        self.ithalat_surec = None
        self._ithalat_kolonlari_kur("arama")

    ITHALAT_KOLONLAR = {
        "arama": [("tur", "Tür", 74), ("ad", "Ad", 232), ("ulke", "Ülke", 56),
                  ("adres", "Adres", 330), ("sefer", "Sefer", 74),
                  ("son_sefer", "Son Sefer", 96)],
        "detay": [("ad", "Tedarikçi / Müşteri", 268),
                  ("ulke", "Ülke", 150), ("sefer", "Sefer", 76),
                  ("urunler", "Ürün Grupları", 430)],
    }

    def _ithalat_kolonlari_kur(self, mod: str):
        kolonlar = self.ITHALAT_KOLONLAR[mod]
        self.ithalat_agac["columns"] = [k for k, _b, _g in kolonlar]
        for k, baslik, genislik in kolonlar:
            self.ithalat_agac.heading(k, text=baslik)
            self.ithalat_agac.column(
                k, width=genislik,
                anchor=W if k in ("tur", "ad", "adres", "urunler") else CENTER)

    def ithalat_ara(self):
        sorgu = self.ithalat_sorgu.get().strip()
        if not sorgu:
            messagebox.showwarning("Sorgu yok",
                                   "Firma/marka adı yazın.")
            return
        if self.ithalat_veri:
            self.ithalat_gecmis.append((self.ithalat_mod, self.ithalat_veri))
            del self.ithalat_gecmis[:-20]
        self._ithalat_calistir(
            ["ara", sorgu, "--sayfa", "1"],
            lambda v: self._ithalat_goster("arama", v),
            f"🌍 '{sorgu}' aranıyor…")

    def ithalat_git(self, url: str):
        if not url:
            return
        if self.ithalat_veri:
            self.ithalat_gecmis.append((self.ithalat_mod, self.ithalat_veri))
            del self.ithalat_gecmis[:-20]
        tur = "firma" if url.startswith("company/") else "tedarikci"
        self._ithalat_calistir(
            [tur, url],
            lambda v: self._ithalat_goster(v.get("tur", "detay"), v),
            f"🌍 {url} yükleniyor…")

    def ithalat_geri(self):
        if not self.ithalat_gecmis:
            return
        mod, veri = self.ithalat_gecmis.pop()
        self._ithalat_goster(mod, veri)

    def ithalat_cift_tik(self, _olay):
        iid = self.ithalat_agac.focus()
        url = self.ithalat_url_harita.get(iid, "")
        if url and not self.ithalat_suriyor:
            self.ithalat_git(url)

    def ithalat_tarayici(self):
        if self.ithalat_mod == "arama":
            sorgu = self.ithalat_sorgu.get().strip()
            if not sorgu:
                messagebox.showinfo("Yok",
                                    "Önce bir arama yapın ya da satır seçin.")
                return
            url = f"https://www.importyeti.com/search?q={quote(sorgu)}"
        elif self.ithalat_veri:
            url = f"https://www.importyeti.com/{self.ithalat_veri.get('url', '')}"
        else:
            messagebox.showinfo("Yok",
                                "Önce bir arama yapın ya da satır seçin.")
            return
        self._url_ac(url)

    def _ithalat_geri_guncelle(self):
        durum = "disabled" if not self.ithalat_gecmis else "!disabled"
        self.ithalat_geri_btn.state([durum])

    def _ithalat_calistir(self, komutlar: list[str], dolgu, bekleme: str):
        if self.ithalat_suriyor:
            self.konsol_yaz("[!] İthalat Radarı zaten çalışıyor…")
            return
        kok = ithalat_kok_bul()
        if not (kok / "ithalat").is_dir():
            messagebox.showerror(
                "ithalat-radar bulunamadı",
                f"ithalat-radar klasörü yok:\n{kok}")
            return

        json_yol = kok / "data" / "out" / "ithalat_gui.json"
        if json_yol.exists():
            json_yol.unlink()

        komut = [sys.executable, "-m", "ithalat", *komutlar,
                 "--json", str(json_yol)]

        self.ithalat_suriyor = True
        self.ithalat_ara_btn.state(["disabled"])
        self._ithalat_geri_guncelle()
        self.ithalat_geri_btn.state(["disabled"])
        self.ithalat_ozet.set(bekleme)
        self.konsol_yaz(bekleme)
        self.durum_deg.set(bekleme)
        self.ilerleme.configure(mode="indeterminate")
        self.ilerleme.start(12)

        yazici = KuyrukYazici(self.kuyruk)

        def is_calistir():
            kod = -1
            hata = None
            try:
                ortam = dict(os.environ, PYTHONIOENCODING="utf-8")
                surec = subprocess.Popen(
                    komut, cwd=str(kok), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1, env=ortam)
                self.ithalat_surec = surec
                for satir in surec.stdout:
                    satir = satir.rstrip()
                    if satir:
                        yazici(satir)
                kod = surec.wait()
            except Exception:
                hata = traceback.format_exc()
            finally:
                self.ithalat_surec = None

            veri = None
            if kod == 0 and json_yol.exists():
                try:
                    veri = json.loads(json_yol.read_text(encoding="utf-8"))
                except Exception:
                    hata = traceback.format_exc()
            self._ana_kuyruk.put(
                (lambda _v: self._ithalat_bitti(veri, kod, hata, dolgu), None))

        threading.Thread(target=is_calistir, daemon=True).start()

    def _ithalat_bitti(self, veri: dict | None, kod: int,
                       hata: str | None, dolgu):
        self.ithalat_suriyor = False
        self.ithalat_ara_btn.state(["!disabled"])
        self._ithalat_geri_guncelle()
        try:
            self.ilerleme.stop()
            self.ilerleme.configure(mode="determinate")
        except Exception:
            pass
        self.ilerleme["value"] = 100 if veri else 0

        if hata:
            self.konsol_yaz("[!] İthalat Radarı hatası:\n" + hata)
        if not veri:
            mesaj = (f"Tamamlanamadı (kod {kod}). Konsola bakın."
                     if kod != 0 else "Sonuç alınamadı.")
            self.ithalat_ozet.set(mesaj)
            self.durum_deg.set("İthalat Radarı tamamlanmadı.")
            return
        dolgu(veri)

    def _ithalat_goster(self, mod: str, veri: dict):
        self.ithalat_mod = mod
        self.ithalat_veri = veri
        self._ithalat_kolonlari_kur(
            "arama" if mod == "arama" else "detay")
        self.ithalat_agac.delete(*self.ithalat_agac.get_children())
        self.ithalat_url_harita.clear()

        if mod == "arama":
            for s in veri.get("sonuclar", []):
                iid = self.ithalat_agac.insert(
                    "", END, values=(s.get("tur"), s.get("ad"),
                                     s.get("ulke"), s.get("adres"),
                                     _sayi(s.get("sefer")),
                                     s.get("son_sefer")))
                self.ithalat_url_harita[iid] = s.get("url", "")
            ozet = (f"'{veri.get('sorgu', '')}' · {veri.get('toplam', 0)} "
                    f"sonuç · sayfa {veri.get('sayfa', 1)}/"
                    f"{veri.get('toplam_sayfa', 1)} · kalan hak: "
                    f"{veri.get('kalan_hak', '-')}")
            durum = f"İthalat Radarı: {veri.get('toplam', 0)} sonuç bulundu."
            self.konsol_yaz(f"🌍 Arama tamam: {veri.get('toplam', 0)} sonuç "
                            f"(gösterilen: {len(veri.get('sonuclar', []))})")
        else:
            for s in veri.get("satirlar", []):
                iid = self.ithalat_agac.insert(
                    "", END, values=(s.get("ad"), s.get("ulke"),
                                     _sayi(s.get("sefer")),
                                     s.get("urunler")))
                self.ithalat_url_harita[iid] = s.get("url", "")
            oz = veri.get("ozet", {}) or {}
            en_yogun = sorted(veri.get("ulkeler") or [],
                              key=lambda u: -(u.get("sefer") or 0))[:3]
            ilk_ulkeler = ", ".join(
                f"{u['ulke']} ({_sayi(u.get('sefer'))})"
                for u in en_yogun)
            ozet = (f"{veri.get('ad', '')} · {veri.get('adres', '')} · "
                    f"{oz.get('bagli_sayisi', 0)} bağlantı · "
                    f"{oz.get('ulke_sayisi', 0)} ülke · son sevkiyat: "
                    f"{oz.get('son_sevkiyat') or '-'}")
            if ilk_ulkeler:
                ozet += f" · Yoğun: {ilk_ulkeler}"
            durum = f"İthalat Radarı: {veri.get('ad', '')} yüklendi."
            self.konsol_yaz(f"📄 {veri.get('ad', '')}: "
                            f"{len(veri.get('satirlar', []))} bağlantı, "
                            f"{len(veri.get('ulkeler') or [])} ülke")

        self.ithalat_ozet.set(ozet)
        self.durum_deg.set(durum)
        self.ust_sayfa.select(self.ithalat_sayfa)

    # ------------------------------------------------------------------
    #  Seçici bul
    # ------------------------------------------------------------------
    def secici_bul(self):
        ad = self.secili_urun()
        url = ""
        if ad:
            u = self.urun_bul(ad)
            url = (u or {}).get("url", "")
        yazici = KuyrukYazici(self.kuyruk)
        p = SeciciPenceresi(self, url, yazici,
                            lambda islev: self._ana_kuyruk.put((islev, None)))
        self.wait_window(p)
        if p.secilen:
            self._seciciyi_uygula(ad, p.secilen)

    def _seciciyi_uygula(self, ad: str | None, secici: str):
        if not ad:
            # ürün seçilmedi → yine de konsola yaz
            self.konsol_yaz(f"Seçili ürün yok. Bulunan seçici: {secici}")
            self.durum_deg.set(f"Bulunan seçici: {secici}")
            return
        u = self.urun_bul(ad)
        if not u:
            return
        if messagebox.askyesno("Seçiciyi uygula",
                               f"'{ad}' ürününe şu seçici uygulansın mı?\n\n"
                               f"{secici}"):
            u["selector"] = secici
            self._config_kaydet()
            self.liste_doldur()
            self.konsol_yaz(f"✔ Seçici güncellendi: {ad} → {secici}")
            self.durum_deg.set("Seçici kaydedildi.")

    # ------------------------------------------------------------------
    #  Geçmiş / grafik
    # ------------------------------------------------------------------
    def gecmis_yenile(self):
        ad = self.secili_urun()
        self.gecmis_agac.delete(*self.gecmis_agac.get_children())
        if not ad:
            return
        satirlar = cekirdek.fiyat_gecmisi(ad, gun=3650)
        for zaman, fiyat, para in satirlar:
            self.gecmis_agac.insert("", END, values=(
                zaman, cekirdek.fiyat_bicimle(fiyat, para or "")))
        if not satirlar:
            self.gecmis_agac.insert("", END, values=("—", "Henüz kayıt yok"))

    def grafik_ciz(self):
        if not MPL_VAR:
            return
        for child in self.grafik_uyesi.winfo_children():
            child.destroy()

        ad = self.secili_urun()
        if not ad:
            ttk.Label(self.grafik_uyesi,
                      text="Grafik için listeden bir ürün seçin.",
                      foreground=RENKLER["gri"]).pack(expand=True)
            return

        satirlar = [s for s in cekirdek.fiyat_gecmisi(ad, gun=3650)
                    if s[1] is not None]
        if len(satirlar) < 2:
            ttk.Label(self.grafik_uyesi,
                      text="Grafik için en az 2 kayıt gerekli.\n"
                           "İki farklı günde tarama yapın.",
                      foreground=RENKLER["gri"], justify="center").pack(
                expand=True)
            return

        tarihler = [s[0] for s in satirlar]
        fiyatlar = [s[1] for s in satirlar]
        para = satirlar[0][2] or ""

        fig = Figure(figsize=(5.4, 2.6), dpi=96, facecolor="#0d1526")
        eksen = fig.add_subplot(111)
        eksen.plot(tarihler, fiyatlar, marker="o", markersize=5,
                   color=RENKLER["vurgu"], linewidth=2)
        eksen.fill_between(range(len(fiyatlar)), fiyatlar,
                           min(fiyatlar) * 0.98, alpha=0.15,
                           color=RENKLER["vurgu"])
        eksen.set_facecolor("#0d1526")
        eksen.set_title(ad[:44], fontsize=10, fontweight="bold",
                        color=RENKLER["baslik"])
        eksen.set_ylabel(fiyatlar and para or "", fontsize=9,
                         color=RENKLER["metin"])
        eksen.tick_params(axis="x", rotation=45, labelsize=7,
                          colors=RENKLER["metin"])
        eksen.tick_params(axis="y", labelsize=8, colors=RENKLER["metin"])
        eksen.grid(True, alpha=0.25, color=RENKLER["kenar"])
        for kenar in eksen.spines.values():
            kenar.set_color(RENKLER["kenar"])
        en_az, en_cok = min(fiyatlar), max(fiyatlar)
        eksen.annotate(f"En düşük: {cekirdek.fiyat_bicimle(en_az, para)}",
                       xy=(0.02, 0.04), xycoords="axes fraction", fontsize=8,
                       color=RENKLER["yesil"])
        eksen.annotate(f"En yüksek: {cekirdek.fiyat_bicimle(en_cok, para)}",
                       xy=(0.02, 0.93), xycoords="axes fraction", fontsize=8,
                       color=RENKLER["kirmizi"])
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.grafik_uyesi)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=True)
        self.grafik_canvas = canvas

    # ------------------------------------------------------------------
    #  Rapor
    # ------------------------------------------------------------------
    def rapor_yenile(self):
        self.rapor_agac.delete(*self.rapor_agac.get_children())
        gun = int(self.gun_deg.get())
        veri = cekirdek.rapor_verisi(self.ayar, gun=gun)
        if not veri:
            self.rapor_ozet.set("Veri yok")
            self.rapor_agac.insert("", END, values=(
                "Henüz kayıt yok — önce tarama yapın.", "", "", "", "",
                "", "", ""))
            return

        for r in veri:
            degisim = f"{r['toplam_degisim']:+.1f}%"
            aralik = f"±{r['aralik']:.1f}%"
            iid = self.rapor_agac.insert("", END, values=(
                r["ad"], r["kayit_sayisi"],
                cekirdek.fiyat_bicimle(r["ilk"], r["para"]),
                cekirdek.fiyat_bicimle(r["son"], r["para"]),
                cekirdek.fiyat_bicimle(r["en_dusuk"], r["para"]),
                cekirdek.fiyat_bicimle(r["en_yuksek"], r["para"]),
                degisim, aralik))
            if r["toplam_degisim"] > 0:
                self.rapor_agac.item(iid, tags=("artis",))
            elif r["toplam_degisim"] < 0:
                self.rapor_agac.item(iid, tags=("azalis",))
        self.rapor_agac.tag_configure("artis", foreground=RENKLER["kirmizi"])
        self.rapor_agac.tag_configure("azalis", foreground=RENKLER["yesil"])

        artan = sum(1 for r in veri if r["toplam_degisim"] > 0)
        azalan = sum(1 for r in veri if r["toplam_degisim"] < 0)
        self.rapor_ozet.set(
            f"{len(veri)} ürün  ·  {artan} zamlandı  ·  {azalan} indirildi")
        self.konsol_yaz(f"📊 Rapor hazır: {gun} gün, {len(veri)} ürün.")

    # ------------------------------------------------------------------
    #  Görsel
    # ------------------------------------------------------------------
    def gorsel_getir(self):
        ad = self.secili_urun()
        if not ad:
            messagebox.showinfo("Seçim yok",
                                "Görselini görmek için listeden ürün seçin.")
            return
        u = self.urun_bul(ad)
        if not u or not u.get("url"):
            messagebox.showwarning("URL yok", "Bu ürünün URL'si yok.")
            return

        self.durum_deg.set("Görseller getiriliyor…")
        self.konsol_yaz(f"🖼 Görseller aranıyor: {ad}")
        yazici = KuyrukYazici(self.kuyruk)

        def is_calistir():
            try:
                liste = cekirdek.gorselleri_bul(u["url"], log=yazici)
            except Exception as hata:
                liste = []
                yazici(f"[!] Görsel hatası: {hata}")
            self._ana_kuyruk.put((lambda _v: self._gorsel_listele(ad, liste),
                                  None))

        threading.Thread(target=is_calistir, daemon=True).start()

    def _gorsel_listele(self, ad: str, liste: list[str]):
        self.gorsel_liste.delete(0, END)
        if not liste:
            self.gorsel_etiket.configure(
                text="Görsel bulunamadı.\nSayfa görselleri JavaScript ile "
                     "yükleniyor olabilir.")
            self.durum_deg.set("Görsel bulunamadı.")
            return
        for g in liste:
            self.gorsel_liste.insert(END, g.split("/")[-1][:44])
        self.konsol_yaz(f"  → {len(liste)} görsel bulundu.")
        self.durum_deg.set(f"{len(liste)} görsel bulundu. "
                           f"Listeden seçin.")
        self._gorsel_liste_veri = liste
        self.gorsel_liste.selection_clear(0, END)
        self.gorsel_liste.selection_set(0)
        self.gorsel_goster(liste[0])
        self.ust_sayfa.select(self.gorsel_sayfa)

    _gorsel_liste_veri: list[str] = []

    def gorsel_secildi(self):
        secim = self.gorsel_liste.curselection()
        if not secim or not self._gorsel_liste_veri:
            return
        idx = secim[0]
        if idx < len(self._gorsel_liste_veri):
            self.gorsel_goster(self._gorsel_liste_veri[idx])

    def gorsel_degistir(self, yon: int):
        if not self._gorsel_liste_veri:
            return
        mevcut = self.gorsel_liste.curselection()
        idx = (mevcut[0] + yon) if mevcut else 0
        idx = max(0, min(idx, len(self._gorsel_liste_veri) - 1))
        self.gorsel_liste.selection_clear(0, END)
        self.gorsel_liste.selection_set(idx)
        self.gorsel_liste.see(idx)
        self.gorsel_goster(self._gorsel_liste_veri[idx])

    def gorsel_goster(self, url: str):
        if not PIL_VAR:
            self.gorsel_etiket.configure(
                text="Görsel önizleme için Pillow gerekli.\n\n"
                     "pip install Pillow")
            return

        def is_calistir():
            yol = cekirdek.gorseli_indir(url)
            if not yol:
                self._ana_kuyruk.put(
                    (lambda _v: self.gorsel_etiket.configure(
                        text="Görsel indirilemedi."), None))
                return
            try:
                im = Image.open(yol)
                im.thumbnail((520, 380))
                foto = ImageTk.PhotoImage(im)
            except Exception as hata:
                self._ana_kuyruk.put(
                    (lambda _v: self.gorsel_etiket.configure(
                        text=f"Görsel açılamadı:\n{hata}"), None))
                return

            def goster(_v=None):
                self.gorsel_ref = foto          # GC'ye karşı referans
                self.gorsel_etiket.configure(image=foto, text="")
                self.durum_deg.set(f"Görsel: {url[-60:]}")
            self._ana_kuyruk.put((goster, None))

        threading.Thread(target=is_calistir, daemon=True).start()

    def _tarayicida_ac(self):
        ad = self.secili_urun()
        u = self.urun_bul(ad) if ad else None
        if not u or not u.get("url"):
            messagebox.showinfo("URL yok", "Önce bir ürün seçin.")
            return
        self._url_ac(u["url"])

    def _url_ac(self, url: str):
        try:
            if sys.platform.startswith("win"):
                os.startfile(url)           # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
        except Exception as hata:
            messagebox.showerror("Açılamadı", str(hata))

    # ------------------------------------------------------------------
    #  Telegram / Ayarlar
    # ------------------------------------------------------------------
    def telegram_test(self):
        self.konsol_yaz("Telegram test ediliyor…")
        yazici = KuyrukYazici(self.kuyruk)

        def is_calistir():
            ok = cekirdek.test_telegram(self.ayar, log=yazici)
            if ok:
                yazici("✅ Telegram testi başarılı.")
            self._ana_kuyruk.put((lambda _v: self.durum_deg.set(
                "Telegram: başarılı" if ok else "Telegram: başarısız"), None))

        threading.Thread(target=is_calistir, daemon=True).start()

    def ayarlar_ac(self):
        ayar = self.ayar.setdefault("ayarlar", {})
        p = AyarlarPenceresi(self, ayar)
        self.wait_window(p)
        if not p.sonuc:
            return
        self.ayar["ayarlar"] = {**ayar, **p.sonuc}
        self._config_kaydet()
        self._alanlari_yukle()
        self.konsol_yaz("⚙ Ayarlar kaydedildi.")
        self.durum_deg.set("Ayarlar kaydedildi.")

    # ------------------------------------------------------------------
    #  Dosya işlemleri
    # ------------------------------------------------------------------
    def _config_ac(self):
        yol = filedialog.askopenfilename(
            title="Config seç",
            filetypes=[("JSON", "*.json"), ("Tümü", "*.*")],
            initialdir=str(self.app_yolu.parent))
        if not yol:
            return
        try:
            self.ayar = cekirdek.config_oku(yol)
            self.app_yolu = Path(yol)
        except Exception as hata:
            messagebox.showerror("Açılamadı", str(hata))
            return
        self.liste_doldur()
        self.rapor_yenile()
        self.konsol_yaz(f"📂 Config açıldı: {yol}")

    def _config_farkli_kaydet(self):
        yol = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile=self.app_yolu.name)
        if not yol:
            return
        try:
            cekirdek.config_kaydet(self.ayar, yol)
            self.app_yolu = Path(yol)
            self.konsol_yaz(f"💾 Config kaydedildi: {yol}")
        except Exception as hata:
            messagebox.showerror("Kaydedilemedi", str(hata))

    def csv_satirlari(self, tur: str) -> tuple[list, list[list]] | None:
        """CSV başlık ve satırlarını üretir.

        Dosya dialogu açmadığı için test edilebilir. `gecmis` için ürün
        seçimi gerekir; seçilmemişse `None` döner.
        """
        if tur == "urunler":
            return (["Ürün", "URL", "Seçici", "Not"],
                    [[u.get("ad"), u.get("url"), u.get("selector"),
                      u.get("not", "")]
                     for u in self.ayar.get("urunler", [])])

        if tur == "sonuclar":
            satirlar = []
            for s in self.son_tarama:
                satirlar.append([
                    s.get("ad"), s.get("onceki"), s.get("fiyat"),
                    (f"{s['yuzde']:.1f}" if s.get("yuzde") is not None
                     else ""),
                    s.get("durum"), s.get("mesaj"), s.get("url")])
            return (["Ürün", "Önceki", "Yeni", "Değişim %",
                     "Durum", "Mesaj", "URL"], satirlar)

        if tur == "rapor":
            satirlar = []
            for r in cekirdek.rapor_verisi(self.ayar,
                                           gun=int(self.gun_deg.get())):
                satirlar.append([
                    r["ad"], r["kayit_sayisi"], r["ilk"], r["son"],
                    r["en_dusuk"], r["en_yuksek"],
                    f"{r['toplam_degisim']:.1f}", f"{r['aralik']:.1f}"])
            return (["Ürün", "Kayıt", "İlk", "Son", "En Düşük",
                     "En Yüksek", "Değişim %", "Aralık %"], satirlar)

        if tur == "gecmis":
            ad = self.secili_urun()
            if not ad:
                return None
            satirlar = [[zaman, fiyat, para] for zaman, fiyat, para
                        in cekirdek.fiyat_gecmisi(ad, gun=3650)]
            return (["Tarih", "Fiyat", "Para"], satirlar)

        if tur == "radar":
            if not self.radar_sonuc:
                return None
            satirlar = []
            for r in self.radar_sonuc.get("rows", []):
                satirlar.append([
                    r.get("rank"),
                    r.get("seller_name") or r.get("seller_id"),
                    r.get("marketplace"), r.get("listings"),
                    r.get("share_listings"), r.get("reviews"),
                    r.get("badge_products"), r.get("units_lo"),
                    r.get("units_hi"), r.get("revenue_lo"),
                    r.get("revenue_hi"), r.get("confidence")])
            return (["#", "Satıcı", "Platform", "Listeleme", "Pay %",
                     "Yorum", "Rozetli ürün", "30g alt", "30g üst",
                     "Ciro alt ₺", "Ciro üst ₺", "Güven"], satirlar)

        if tur == "pazarama":
            veri = getattr(self, "paz_veri", None)
            if not veri:
                return None
            ara = []
            for s in veri.get("siteler", []):
                site = SITE_ETIKET.get(s.get("site", ""),
                                       s.get("site", ""))
                for u in s.get("urunler", []):
                    ara.append((u.get("fiyat"), [
                        site, u.get("ad", ""),
                        u.get("fiyat") if u.get("fiyat")
                        is not None else "",
                        u.get("satici", "") or "",
                        u.get("yorum") or "",
                        u.get("url", "") or ""]))
            ara.sort(key=lambda t: (t[0] is None, t[0] or 0.0))
            return (["Site", "Ürün", "Fiyat", "Satıcı", "Yorum", "Link"],
                    [satir for _f, satir in ara])

        if tur == "ithalat":
            veri = getattr(self, "ithalat_veri", None)
            if not veri:
                return None
            if self.ithalat_mod == "arama":
                satirlar = [[s.get("tur"), s.get("ad"), s.get("ulke"),
                             s.get("adres"), s.get("sefer"),
                             s.get("son_sefer")]
                            for s in veri.get("sonuclar", [])]
                return (["Tür", "Ad", "Ülke", "Adres", "Sefer", "Son Sefer"],
                        satirlar)
            satirlar = [[s.get("ad"), s.get("ulke"), s.get("sefer"),
                         s.get("urunler"), s.get("url")]
                        for s in veri.get("satirlar", [])]
            return (["Bağlantı", "Ülke", "Sefer", "Ürün Grupları", "Slug"],
                    satirlar)

        return None

    def _csv_aktar(self, tur: str):
        uretim = self.csv_satirlari(tur)
        if uretim is None:
            if tur == "gecmis":
                messagebox.showwarning("Seçim yok",
                                       "Listeden ürün seçin.")
            elif tur == "radar":
                messagebox.showinfo("Veri yok",
                                    "Önce radar taraması yapın.")
            elif tur == "pazarama":
                messagebox.showinfo("Veri yok",
                                    "Önce bir ürün araması yapın.")
            elif tur == "ithalat":
                messagebox.showinfo("Veri yok",
                                    "Önce İthalat Radarı'nda arama yapın.")
            return
        baslik, satirlar = uretim

        varsayilan = {
            "urunler": "urunler.csv", "sonuclar": "tarama_sonuclari.csv",
            "rapor": "rapor.csv", "gecmis": "fiyat_gecmisi.csv",
            "radar": "radar_saticilar.csv",
        }.get(tur, "veri.csv")
        yol = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"{Path(varsayilan).stem}_{datetime.now():%Y%m%d}.csv")
        if not yol:
            return

        try:
            with open(yol, "w", newline="", encoding="utf-8-sig") as f:
                yaz = csv.writer(f, delimiter=";")
                yaz.writerow(baslik)
                yaz.writerows(satirlar)
            self.konsol_yaz(f"📄 CSV aktarıldı: {yol}")
            self.durum_deg.set(f"CSV kaydedildi: {Path(yol).name}")
        except Exception as hata:
            messagebox.showerror("CSV hatası", str(hata))

    def _klasor_ac(self):
        klasor = self.app_yolu.parent
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(klasor))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(klasor)])
            else:
                subprocess.Popen(["xdg-open", str(klasor)])
        except Exception as hata:
            messagebox.showerror("Açılamadı", str(hata))

    def _zamanlayici_kur(self):
        """Windows Görev Zamanlayıcı için .bat üretir ve talimat verir."""
        bat_icerik = (
            "@echo off\r\nchcp 65001 >nul\r\n"
            f'cd /d "{cekirdek.KOK}"\r\n'
            f'python "{cekirdek.KOK / "rakip_takip.py"}" '
            f'>> "{cekirdek.KOK / "log.txt"}" 2>&1\r\n'
        )
        bat_yol = cekirdek.KOK / "zamanlama_tarama.bat"
        try:
            bat_yol.write_text(bat_icerik, encoding="utf-8")
        except Exception as hata:
            messagebox.showerror("Hata", str(hata))
            return

        komut = (
            f'schtasks /Create /TN "RakipFiyatTarama" '
            f'/TR "{bat_yol}" /SC DAILY /ST 09:00 /F'
        )
        messagebox.showinfo(
            "Görev Zamanlayıcı",
            "Günlük 09:00'da otomatik tarama için hazır betik oluşturuldu:\n\n"
            f"{bat_yol}\n\n"
            "Görevi oluşturmak için 'Tamam'a basın, komut satırı "
            "açılacaktır (Yönetici olarak çalıştırın):\n\n"
            + komut)

        def calistir():
            try:
                r = subprocess.run(
                    komut, shell=True, capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                mesaj = (r.stdout or r.stderr or "").strip()
                self._ana_kuyruk.put((
                    lambda _v: (
                        self.konsol_yaz(f"⏱ Görev oluşturuldu: {mesaj}"),
                        self.durum_deg.set("Görev zamanlayıcıya eklendi.")),
                    None))
            except Exception as hata:
                self.konsol_yaz(f"[!] Görev oluşturulamadı: {hata}")

        threading.Thread(target=calistir, daemon=True).start()

    # ------------------------------------------------------------------
    #  Yardım
    # ------------------------------------------------------------------
    def _hakkinda(self):
        messagebox.showinfo(
            "Hakkında",
            "Rakip Fiyat Takip Botu\n\n"
            "Rakip ürünlerin fiyatlarını otomatik takip eder, geçmişi tutar "
            "ve değişikliklerde Telegram ile uyarır.\n\n"
            "Çekirdek: rakip_takip.py  ·  Arayüz: gui.py\n"
            "Veri: fiyatlar.db (SQLite)  ·  Ayarlar: config.json\n\n"
            "Etik: robots.txt'e uyar, istekler arası bekleme yapar.")

    def _kilavuz(self):
        yol = cekirdek.KOK / "KULLANIM.md"
        if yol.exists():
            self._url_ac(str(yol))
        else:
            messagebox.showwarning("Bulunamadı", f"Kılavuz yok:\n{yol}")

    # ------------------------------------------------------------------
    def _kapat(self):
        if self.radar_suriyor:
            if not messagebox.askyesno("Radar çalışıyor",
                                       "Radar taraması devam ediyor. "
                                       "Çıkmak istiyor musunuz?"):
                return
            self.radar_iptal = True
            if self.radar_surec:
                try:
                    self.radar_surec.terminate()
                except Exception:
                    pass
        if self.tarama_suriyor:
            if not messagebox.askyesno("Tarama sürüyor",
                                       "Tarama devam ediyor. Çıkmak "
                                       "istiyor musunuz?"):
                return
            self.iptal_bayragi.set()
        self.otomatik_takip = False
        self._periyot_iptal()
        self._config_kaydet()
        self.destroy()


def main():
    try:
        app = Uygulama()
    except TclError as hata:
        print(f"Arayüz başlatılamadı: {hata}")
        sys.exit(1)
    app.mainloop()


if __name__ == "__main__":
    main()
