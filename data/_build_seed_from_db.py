"""
Backend-DB/database/atik_yonetimi.sql icindeki gercek 'containers' tablosunu
okuyup simulate.py'in bekledigi 'fixed-list' formatinda
containers_backend_seed.json dosyasini ureten bakim scripti.

Bu sadece bakim/dev araci; simulasyonun kendisi bu scripte ihtiyac duymaz.
Yeni ekip arkadaslari icin de calistirmak ZORUNLU degildir; commit edilmis
containers_backend_seed.json dosyasi DB ile zaten uyumludur.

Ne zaman calistirilir:
  Backend-DB/database/atik_yonetimi.sql guncellenirse (yeni konteyner
  eklendi/silindi vb.) bu scripti calistirip JSON'i tazeleriz.

On kosul:
  Backend-DB repo'su, simulation repo'su ile AYNI ust klasorde olmali:

    parent/
      simulation/        <- bu repo
      Backend-DB/        <- yan repo (sql dosyasi burada)

Kullanim:
  cd simulation
  python data/_build_seed_from_db.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIMULATION_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PARENT_DIR = os.path.abspath(os.path.join(SIMULATION_ROOT, ".."))

SQL_PATH = os.path.join(PARENT_DIR, "Backend-DB", "database", "atik_yonetimi.sql")
OUT_PATH = os.path.join(SCRIPT_DIR, "containers_backend_seed.json")

START_MARKER = "COPY public.containers (id, waste_type, lat, lng, status, created_at) FROM stdin;"
END_MARKER = "\\."


def parse_containers(sql_text: str) -> List[Tuple[int, str, float, float]]:
    start = sql_text.find(START_MARKER)
    if start < 0:
        raise RuntimeError(
            "atik_yonetimi.sql icinde 'containers' COPY blogu bulunamadi. "
            "SQL dump dosyasi bozulmus olabilir."
        )

    body_start = sql_text.find("\n", start) + 1
    body_end = sql_text.find(END_MARKER, body_start)
    body = sql_text[body_start:body_end]

    rows: List[Tuple[int, str, float, float]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        cols = line.split("\t")
        if len(cols) < 4:
            continue
        cid = int(cols[0])
        waste_type = cols[1]
        lat = float(cols[2])
        lng = float(cols[3])
        rows.append((cid, waste_type, lat, lng))

    rows.sort(key=lambda r: r[0])
    return rows


def deterministic_fill(cid: int) -> float:
    # 60..95 araliginda deterministik bir baslangic doluluk degeri.
    # %60 threshold uzerinde tutuyor ki ilk tick sonrasi rota uretimine
    # her konteyner aday olabilsin.
    return float(60 + ((cid * 7) % 36))


def main() -> int:
    if not os.path.exists(SQL_PATH):
        sys.stderr.write(
            "HATA: SQL dump dosyasi bulunamadi:\n"
            f"  {SQL_PATH}\n\n"
            "Bu script, Backend-DB repo'sunun simulation repo'su ile AYNI ust\n"
            "klasorde klonlanmis olmasini bekler:\n\n"
            "  parent/\n"
            "    simulation/\n"
            "    Backend-DB/\n\n"
            "Backend-DB'yi klonlayin veya simulasyonun mevcut\n"
            "data/containers_backend_seed.json dosyasini oldugu gibi kullanin\n"
            "(zaten DB seed verisiyle uyumludur).\n"
        )
        return 1

    with open(SQL_PATH, "r", encoding="utf-8") as f:
        sql_text = f.read()

    rows = parse_containers(sql_text)

    payload = {
        "name": "backend-seed",
        "description": (
            "Backend-DB/database/atik_yonetimi.sql icindeki gercek 'containers' "
            "tablosu seed verisi ile birebir uyumlu container seti. "
            "ID/lat/lng degerleri DB ile aynidir; fillPercent deterministik "
            "uretilmistir (60-95 araligi)."
        ),
        "source": "Backend-DB/database/atik_yonetimi.sql",
        "containers": [
            {
                "id": cid,
                "wasteType": wt,
                "lat": lat,
                "lng": lng,
                "fillPercent": deterministic_fill(cid),
            }
            for (cid, wt, lat, lng) in rows
        ],
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    by_type: dict = {}
    for (_cid, wt, _lat, _lng) in rows:
        by_type[wt] = by_type.get(wt, 0) + 1

    print(f"Yazildi: {OUT_PATH}")
    print(f"Toplam konteyner: {len(rows)}")
    print("Tur basina:")
    for wt, c in sorted(by_type.items()):
        print(f"  {wt:18s} {c}")
    if rows:
        ids = [r[0] for r in rows]
        missing = sorted(set(range(min(ids), max(ids) + 1)) - set(ids))
        print(f"ID araligi: {min(ids)}..{max(ids)} (eksik ID'ler: {missing})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
