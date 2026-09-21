"""Copie de siguranta a bazei de date. Se poate rula oricand si e gandit sa ruleze zilnic (sarcina programata).

    python3 backup_db.py

Copiile ajung in instance/backups/ (fond-zilnic-AAAALLZZ-OOMMSS.db); se pastreaza ultimele 14.
Nu are nevoie de Flask si nu opreste aplicatia (foloseste copierea sigura din SQLite).
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DEFAULT_DB = BASE_DIR / "instance" / "fond.db"
KEEP = 14


def backup(db_path=None, keep=KEEP):
    db_path = Path(db_path or os.environ.get("FOND_DB", DEFAULT_DB))
    if not db_path.exists():
        raise SystemExit(f"Nu există baza de date: {db_path}")
    folder = db_path.parent / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"{db_path.stem}-zilnic-{datetime.now():%Y%m%d-%H%M%S}.db"

    source, copy = sqlite3.connect(db_path), sqlite3.connect(target)
    try:
        source.backup(copy)
        ok = copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        copy.close()
        source.close()
    if not ok:
        target.unlink()
        raise SystemExit("Copia de siguranță nu a trecut verificarea de integritate; a fost ștearsă.")

    # numele contin data in ordine cronologica, deci sortarea alfabetica = cea in timp
    for old in sorted(folder.glob(f"{db_path.stem}-zilnic-*.db"))[:-keep]:
        old.unlink()
    return target


if __name__ == "__main__":
    print(f"Copie creată: {backup()}")
