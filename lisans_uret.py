# -*- coding: utf-8 -*-
"""Lisans anahtarı üretir (satıcı içindir).

Kullanım:
    python lisans_uret.py        # 1 anahtar
    python lisans_uret.py 10     # 10 anahtar

Üretilen anahtarlar müşteriye verilir; müşteri programda
**Araçlar → Lisans…** menüsünden girer.
"""
from __future__ import annotations

import sys

from lisans import anahtar_uret


def main() -> None:
    adet = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for _ in range(adet):
        print(anahtar_uret())


if __name__ == "__main__":
    main()
