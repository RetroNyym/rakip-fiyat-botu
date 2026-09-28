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


# ==========================================================================
#  Stil
# ==========================================================================
RENKLER = {
    "arka":        "#f4f6f9",
    "panel":       "#ffffff",
    "baslik":      "#1f2a44",
    "vurgu":       "#2563eb",
    "vurgu_koyu":  "#1d4ed8",
    "yesil":       "#16a34a",
    "kirmizi":     "#dc2626",
    "sari":        "#d97706",
    "gri":         "#64748b",
    "kenar":       "#dbe1ea",
}

STIL = """
.TTk.TFrame { background: %(arka)s; }
.TPanel.TFrame { background: %(panel)s; }
.TLabelframe { background: %(panel)s; bordercolor: %(kenar)s; }
.TLabelframe.Label { background: %(panel)s; foreground: %(baslik)s;
                     font: ("Segoe UI", 10, "bold"); }
.TLabel { background: %(panel)s; foreground: #33415c;
          font: ("Segoe UI", 10); }
.TEntry { font: ("Segoe UI", 10); }
.TButton { font: ("Segoe UI", 10); padding: 4 6; }
.TNotebook { background: %(arka)s; }
.TNotebook.Tab { font: ("Segoe UI", 10); padding: 6 4; }
.Treeview { font: ("Segoe UI", 10); rowheight: 24; }
.Treeview.Heading { font: ("Segoe UI", 10, "bold"); background: #e8edf5; }
.TStatus.TLabel { background: #e8edf5; foreground: %(baslik)s;
                  font: ("Segoe UI", 9); padding: 4 6; }
""" % RENKLER


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


# ==========================================================================
#  Ürün ekleme / düzenleme diyalogu
# ==========================================================================
class UrunPenceresi(tk.Toplevel):
    def __init__(self, ebeveyn, baslik: str, veri: dict | None = None):
        super().__init__(ebeveyn)
        self.title(baslik)
        self.resizable(False, False)
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
        self.title("Rakip Fiyat Takip Botu")
        self.geometry("1280x840")
        self.minsize(1020, 680)
        self.configure(bg=RENKLER["arka"])

        # --- durum ---
        self.app_yolu = cekirdek.VARSAYILAN_CONFIG
        self.ayar = self._config_yukle()
        self.tarama_suriyor = False
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

        # --- stil ---
        self.stil = ttk.Style(self)
        try:
            self.stil.theme_use("clam")
        except TclError:
            pass
        self.stil.configure(".", font=("Segoe UI", 10))
        self.stil.configure("TFrame", background=RENKLER["arka"])
        self.stil.configure("TLabel", background=RENKLER["arka"])
        self.stil.configure("TButton", font=("Segoe UI", 10))
        self.stil.configure("Status.TLabel", background="#e8edf5",
                            foreground=RENKLER["baslik"])
        self.stil.configure("Treeview", font=("Segoe UI", 10), rowheight=25)
        self.stil.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"),
                            background="#e8edf5")
        self.stil.map("Treeview", background=[("selected", RENKLER["vurgu"])],
                      foreground=[("selected", "#ffffff")])

        self._menu_kur()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._arac_cubugu()
        self._govde()
        self._durum_cubugu()

        self.liste_doldur()
        self._kuyruk_isle()
        self.protocol("WM_DELETE_WINDOW", self._kapat)

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

    def _menu_kur(self):
        menu = tk.Menu(self)

        dosya = tk.Menu(menu, tearoff=0)
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

        arac = tk.Menu(menu, tearoff=0)
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

        gorunum = tk.Menu(menu, tearoff=0)
        gorunum.add_command(label="Konsolu Temizle", command=self.konsol_temizle)
        gorunum.add_command(label="Fiyat Geçmişini Yenile",
                            command=self.gecmis_yenile)
        gorunum.add_command(label="Raporu Yenile", command=self.rapor_yenile)
        menu.add_cascade(label="Görünüm", menu=gorunum)

        yardim = tk.Menu(menu, tearoff=0)
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

    def _arac_cubugu(self):
        cerceve = ttk.Frame(self, style="TTk.TFrame", padding=(10, 8))
        cerceve.grid(row=0, column=0, sticky=(W, E))

        self.tara_btn = ttk.Button(cerceve, text="▶  Tarama Başlat",
                                   command=self.tarama_baslat)
        self.tara_btn.pack(side=LEFT, padx=(0, 6))

        self.secili_btn = ttk.Button(cerceve, text="▶ Seçiliyi Tara",
                                     command=lambda: self.tarama_baslat(secili=True))
        self.secili_btn.pack(side=LEFT, padx=(0, 6))

        self.durdur_btn = ttk.Button(cerceve, text="■ Durdur",
                                     command=self.tarama_durdur,
                                     state="disabled")
        self.durdur_btn.pack(side=LEFT, padx=(0, 6))

        ttk.Separator(cerceve, orient="vertical").pack(side=LEFT, fill=Y,
                                                       padx=8)
        ttk.Button(cerceve, text="+ Ürün Ekle",
                   command=self.urun_ekle).pack(side=LEFT, padx=(0, 6))
        ttk.Button(cerceve, text="✎ Düzenle",
                   command=self.urun_duzenle).pack(side=LEFT, padx=(0, 6))
        ttk.Button(cerceve, text="🗑 Sil",
                   command=self.urun_sil).pack(side=LEFT, padx=(0, 6))

        ttk.Separator(cerceve, orient="vertical").pack(side=LEFT, fill=Y,
                                                       padx=8)
        ttk.Button(cerceve, text="🔍 Seçici Bul",
                   command=self.secici_bul).pack(side=LEFT, padx=(0, 6))
        ttk.Button(cerceve, text="📊 Rapor",
                   command=lambda: self.ust_sayfa.select(self.rapor_sayfa)
                   ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(cerceve, text="🏆 Radar",
                   command=lambda: self.ust_sayfa.select(self.radar_sayfa)
                   ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(cerceve, text="🖼 Görsel Getir",
                   command=self.gorsel_getir).pack(side=LEFT, padx=(0, 6))
        ttk.Button(cerceve, text="⚙ Ayarlar",
                   command=self.ayarlar_ac).pack(side=LEFT)

    def _govde(self):
        ana = ttk.Frame(self, style="TTk.TFrame", padding=10)
        ana.grid(row=1, column=0, sticky=(N, S, E, W))
        ana.columnconfigure(1, weight=1)
        ana.rowconfigure(0, weight=1)

        # ---------- SOL: ürün listesi ----------
        sol = ttk.LabelFrame(ana, text="  Ürünler  ", padding=8)
        sol.grid(row=0, column=0, sticky=(N, S, W), padx=(0, 8))
        sol.rowconfigure(2, weight=1)

        arama_cerceve = ttk.Frame(sol, style="TPanel.TFrame")
        arama_cerceve.grid(row=0, column=0, columnspan=2, sticky=(W, E),
                           pady=(0, 6))
        ttk.Label(arama_cerceve, text="🔍").pack(side=LEFT)
        self.arama_deg = StringVar()
        self.arama_deg.trace_add("write", lambda *_: self.liste_doldur())
        ttk.Entry(arama_cerceve, textvariable=self.arama_deg,
                  width=26).pack(side=LEFT, fill=X, expand=True, padx=(4, 0))
        ttk.Button(arama_cerceve, text="✕", width=3,
                   command=lambda: self.arama_deg.set("")).pack(side=LEFT,
                                                                padx=(4, 0))

        kolonlar = ("ad", "fiyat", "durum")
        self.agac = ttk.Treeview(sol, columns=kolonlar, show="headings",
                                 height=20, selectmode="extended")
        self.agac.heading("ad", text="Ürün")
        self.agac.heading("fiyat", text="Son Fiyat")
        self.agac.heading("durum", text="Durum")
        self.agac.column("ad", width=210, anchor=W)
        self.agac.column("fiyat", width=110, anchor=E)
        self.agac.column("durum", width=86, anchor=CENTER)

        yatay = ttk.Scrollbar(sol, orient="horizontal",
                              command=self.agac.xview)
        self.agac.configure(xscrollcommand=yatay.set)
        self.agac.grid(row=2, column=0, sticky=(N, S, W, E))
        dikey = ttk.Scrollbar(sol, orient="vertical", command=self.agac.yview)
        self.agac.configure(yscrollcommand=dikey.set)
        dikey.grid(row=2, column=1, sticky=(N, S))
        yatay.grid(row=3, column=0, columnspan=2, sticky=(W, E))

        self.agac.bind("<Double-1>", lambda e: self.urun_duzenle())
        self.agac.bind("<<TreeviewSelect>>", lambda e: self._secim_degisti())

        sayac = ttk.Frame(sol, style="TPanel.TFrame")
        sayac.grid(row=4, column=0, columnspan=2, sticky=(W, E), pady=(6, 0))
        self.sayac_deg = StringVar(value="0 ürün")
        ttk.Label(sayac, textvariable=self.sayac_deg,
                  foreground=RENKLER["gri"]).pack(side=LEFT)

        # ---------- SAĞ: sekmeler ----------
        sag = ttk.Frame(ana, style="TTk.TFrame")
        sag.grid(row=0, column=1, sticky=(N, S, E, W))
        sag.rowconfigure(0, weight=1)
        sag.columnconfigure(0, weight=1)

        self.ust_sayfa = ttk.Notebook(sag)
        self.ust_sayfa.grid(row=0, column=0, sticky=(N, S, E, W))

        # --- Tarama sonuçları ---
        sonuc_sayfa = ttk.Frame(self.ust_sayfa, style="TTk.TFrame", padding=6)
        self.ust_sayfa.add(sonuc_sayfa, text="  Tarama Sonuçları  ")
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
                                       show="headings")
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
        ttk.Button(g_ust, text="Grafiği Yenile",
                   command=self.grafik_ciz).pack(side=RIGHT)
        ttk.Button(g_ust, text="CSV Aktar",
                   command=lambda: self._csv_aktar("gecmis")).pack(
            side=RIGHT, padx=(0, 6))

        self.gecmis_agac = ttk.Treeview(
            gecmis_sayfa, columns=("tarih", "fiyat"), show="headings",
            height=14)
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
        ttk.Button(r_ust, text="Raporu Getir",
                   command=self.rapor_yenile).pack(side=LEFT, padx=(8, 0))
        ttk.Button(r_ust, text="CSV Aktar",
                   command=lambda: self._csv_aktar("rapor")).pack(
            side=LEFT, padx=(6, 0))
        self.rapor_ozet = StringVar(value="")
        ttk.Label(r_ust, textvariable=self.rapor_ozet,
                  foreground=RENKLER["gri"]).pack(side=RIGHT)

        r_kolonlar = ("ad", "kayit", "ilk", "son", "dusuk", "yuksek",
                      "degisim", "aralik")
        self.rapor_agac = ttk.Treeview(self.rapor_sayfa, columns=r_kolonlar,
                                       show="headings")
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

        # ---------- ALT: konsol + görsel ----------
        alt = ttk.Frame(ana, style="TTk.TFrame")
        alt.grid(row=1, column=0, columnspan=2, sticky=(W, E, N, S),
                 pady=(10, 0))
        alt.rowconfigure(0, weight=1)
        alt.columnconfigure(0, weight=1)

        self.alt_sayfa = ttk.Notebook(alt)
        self.alt_sayfa.grid(row=0, column=0, sticky=(N, S, E, W))

        # Konsol
        konsol_sayfa = ttk.Frame(self.alt_sayfa, style="TTk.TFrame")
        self.alt_sayfa.add(konsol_sayfa, text="  📟 Konsol  ")
        konsol_sayfa.rowconfigure(0, weight=1)
        konsol_sayfa.columnconfigure(0, weight=1)

        self.konsol = tk.Text(konsol_sayfa, height=11, wrap="word",
                              font=("Consolas", 10),
                              background="#101828", foreground="#d5e0f0",
                              insertbackground="#ffffff",
                              relief="flat", padx=10, pady=8,
                              state="disabled")
        self.konsol.tag_configure("hata", foreground="#fca5a5")
        self.konsol.tag_configure("basari", foreground="#86efac")
        self.konsol.tag_configure("uyari", foreground="#fcd34d")
        self.konsol.tag_configure("bilgi", foreground="#93c5fd")
        self.konsol.tag_configure("normal", foreground="#d5e0f0")
        k_d = ttk.Scrollbar(konsol_sayfa, orient="vertical",
                            command=self.konsol.yview)
        self.konsol.configure(yscrollcommand=k_d.set)
        self.konsol.grid(row=0, column=0, sticky=(N, S, E, W))
        k_d.grid(row=0, column=1, sticky=(N, S))

        k_ust = ttk.Frame(konsol_sayfa, style="TTk.TFrame")
        k_ust.grid(row=1, column=0, columnspan=2, sticky=(W, E), pady=(4, 0))
        ttk.Button(k_ust, text="Temizle",
                   command=self.konsol_temizle).pack(side=LEFT)
        ttk.Button(k_ust, text="Konsolu Kopyala",
                   command=self._konsol_kopyala).pack(side=LEFT, padx=(6, 0))
        ttk.Button(k_ust, text="Dosyaya Kaydet",
                   command=self._konsol_kaydet).pack(side=LEFT, padx=(6, 0))

        # Görsel
        gorsel_sayfa = ttk.Frame(self.alt_sayfa, style="TTk.TFrame", padding=6)
        self.alt_sayfa.add(gorsel_sayfa, text="  🖼 Ürün Görseli  ")
        gorsel_sayfa.columnconfigure(1, weight=1)
        gorsel_sayfa.rowconfigure(0, weight=1)

        sol_panel = ttk.Frame(gorsel_sayfa, style="TPanel.TFrame")
        sol_panel.grid(row=0, column=0, sticky=(N, S, W), padx=(0, 8))

        ttk.Button(sol_panel, text="🔄 Görseli Getir",
                   command=self.gorsel_getir).pack(fill=X, pady=(0, 4))
        ttk.Button(sol_panel, text="➡ Sonraki",
                   command=lambda: self.gorsel_degistir(1)).pack(fill=X,
                                                                 pady=(0, 4))
        ttk.Button(sol_panel, text="⬅ Önceki",
                   command=lambda: self.gorsel_degistir(-1)).pack(fill=X,
                                                                  pady=(0, 4))
        ttk.Button(sol_panel, text="🌐 Tarayıcıda Aç",
                   command=self._tarayicida_ac).pack(fill=X, pady=(0, 4))
        ttk.Separator(sol_panel).pack(fill=X, pady=6)
        ttk.Label(sol_panel, text="Görsel listesi:",
                  foreground=RENKLER["gri"]).pack(anchor=W)
        self.gorsel_liste = tk.Listbox(sol_panel, height=8, width=26,
                                       font=("Segoe UI", 9), exportselection=False)
        self.gorsel_liste.pack(fill=X, pady=(4, 0))
        self.gorsel_liste.bind("<<ListboxSelect>>",
                               lambda e: self.gorsel_secildi())

        self.gorsel_etiket = tk.Label(
            gorsel_sayfa,
            text="Soldan 'Görseli Getir' deyin.\n\n"
                 "Seçili ürünün fiyatını ve görselini birlikte görürsünüz.",
            bg=RENKLER["panel"], fg=RENKLER["gri"],
            font=("Segoe UI", 11), justify="center")
        self.gorsel_etiket.grid(row=0, column=1, sticky=(N, S, E, W))

        # ---------- ilerleme ----------
        ilerleme = ttk.Frame(self, style="TTk.TFrame")
        ilerleme.grid(row=2, column=0, sticky=(W, E), padx=10, pady=(6, 0))
        self.ilerleme = ttk.Progressbar(ilerleme, mode="determinate",
                                        maximum=100)
        self.ilerleme.pack(fill=X)
        self.ilerleme_deger = StringVar(value="")
        ttk.Label(ilerleme, textvariable=self.ilerleme_deger,
                  foreground=RENKLER["gri"]).pack(anchor=W)

    def _durum_cubugu(self):
        cerceve = ttk.Frame(self, style="TTk.TFrame")
        cerceve.grid(row=3, column=0, sticky=(W, E))

        self.durum_deg = StringVar(value="Hazır")
        ttk.Label(cerceve, textvariable=self.durum_deg,
                  style="Status.TLabel").pack(side=LEFT, fill=X, expand=True)

        sag = ttk.Label(cerceve, style="Status.TLabel")
        sag.pack(side=RIGHT)
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
    def urun_ekle(self):
        p = UrunPenceresi(self, "Yeni Ürün Ekle")
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
    def tarama_baslat(self, secili: bool = False):
        if self.tarama_suriyor:
            messagebox.showinfo("Tarama sürüyor",
                                "Zaten bir tarama çalışıyor. Önce durdurun.")
            return
        urunler = self.ayar.get("urunler", [])
        if not urunler:
            messagebox.showinfo("Ürün yok",
                                "Önce '+ Ürün Ekle' ile rakip ürün ekleyin.")
            return

        secili_adlar = self.secili_urunler() if secili else None
        if secili and not secili_adlar:
            messagebox.showinfo("Seçim yok",
                                "Taranacak ürünleri listeden seçin "
                                "(Ctrl+ ile çoklu seçim).")
            return

        self.tarama_suriyor = True
        self.iptal_bayragi.clear()
        self.tara_btn.state(["disabled"])
        self.secili_btn.state(["disabled"])
        self.durdur_btn.state(["!disabled"])
        self.ilerleme["value"] = 0
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

    def tarama_durdur(self):
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
                                      background="#fef2f2")
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
        self.radar_durdur_btn = ttk.Button(
            ust, text="■ Durdur", command=self.radar_durdur, state="disabled")
        self.radar_durdur_btn.pack(side=LEFT, padx=4)
        ttk.Button(ust, text="📄 Raporu Aç",
                   command=self.radar_raporu_ac).pack(side=LEFT, padx=4)
        ttk.Button(ust, text="CSV Aktar",
                   command=lambda: self._csv_aktar("radar")).pack(
            side=LEFT, padx=4)

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
                                       show="headings", height=14)
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
        self.radar_agac.tag_configure("lider", background="#eff6ff",
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

        fig = Figure(figsize=(5.4, 3.2), dpi=96, facecolor="white")
        eksen = fig.add_subplot(111)
        eksen.plot(tarihler, fiyatlar, marker="o", markersize=5,
                   color=RENKLER["vurgu"], linewidth=2)
        eksen.fill_between(range(len(fiyatlar)), fiyatlar,
                           min(fiyatlar) * 0.98, alpha=0.10,
                           color=RENKLER["vurgu"])
        eksen.set_title(ad[:44], fontsize=10, fontweight="bold",
                        color=RENKLER["baslik"])
        eksen.set_ylabel(fiyatlar and para or "", fontsize=9)
        eksen.tick_params(axis="x", rotation=45, labelsize=7)
        eksen.tick_params(axis="y", labelsize=8)
        eksen.grid(True, alpha=0.3)
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
        self.alt_sayfa.select(1)

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
