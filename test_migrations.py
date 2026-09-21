"""Teste pentru sistemul de migrari a bazei de date.

Rulare: .venv\\Scripts\\python.exe test_migrations.py
"""
import shutil
import sqlite3
import tempfile
from pathlib import Path

import db


def version(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def columns(path, table):
    conn = sqlite3.connect(path)
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def backups(folder):
    return sorted((Path(folder) / "backups").glob("*.db"))


def main():
    work = Path(tempfile.mkdtemp())
    mig = work / "migrations"
    shutil.copytree(db.MIGRATIONS_DIR, mig)

    # 1. baza noua: se aplica migrarea initiala, fara backup (nu exista nimic de salvat)
    fresh = work / "fresh" / "fond.db"
    fresh.parent.mkdir()
    db.migrate(fresh, mig)
    assert version(fresh) == 1
    assert "name" in columns(fresh, "students")
    assert not backups(fresh.parent)

    # a doua rulare nu face nimic
    db.migrate(fresh, mig)
    assert version(fresh) == 1 and not backups(fresh.parent)

    # 2. baza veche (creata inainte de migrari: user_version 0, dar cu tabele si date)
    old = work / "old" / "fond.db"
    old.parent.mkdir()
    conn = sqlite3.connect(old)
    conn.executescript((mig / "0001_initial.sql").read_text(encoding="utf-8"))
    conn.execute("INSERT INTO students(name) VALUES ('Popescu Ana')")
    conn.execute("INSERT INTO expenses(spent_on, category, amount) VALUES ('2026-09-01', 'Cadouri', 1000)")
    conn.commit()
    conn.close()
    assert version(old) == 0
    db.migrate(old, mig)
    assert version(old) == 1
    assert len(backups(old.parent)) == 1, "trebuia sa se faca backup inainte de migrare"

    # 3. o coloana noua, adaugata printr-un fisier nou
    (mig / "0002_chitanta.sql").write_text(
        "-- poza/numarul chitantei\nALTER TABLE expenses ADD COLUMN receipt TEXT;\n"
        "CREATE INDEX idx_expenses_date ON expenses(spent_on);\n",
        encoding="utf-8",
    )
    db.migrate(old, mig)
    assert version(old) == 2
    assert "receipt" in columns(old, "expenses")
    conn = sqlite3.connect(old)
    assert conn.execute("SELECT category, amount, receipt FROM expenses").fetchall() == [("Cadouri", 1000, None)]
    assert conn.execute("SELECT name FROM students").fetchall() == [("Popescu Ana",)]
    conn.close()
    assert len(backups(old.parent)) == 2

    # 4. migrare defectuoasa: se anuleaza complet, versiunea ramane, datele raman
    (mig / "0003_defecta.sql").write_text(
        "ALTER TABLE students ADD COLUMN phone TEXT;\nALTER TABLE nu_exista ADD COLUMN x TEXT;\n",
        encoding="utf-8",
    )
    try:
        db.migrate(old, mig)
        raise AssertionError("trebuia sa esueze")
    except RuntimeError as e:
        assert "0003_defecta.sql" in str(e)
    assert version(old) == 2
    assert "phone" not in columns(old, "students"), "prima instructiune trebuia anulata"
    conn = sqlite3.connect(old)
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 1
    conn.close()

    # 5. dupa corectare, migrarea se aplica
    (mig / "0003_defecta.sql").unlink()
    (mig / "0003_telefon.sql").write_text("ALTER TABLE students ADD COLUMN phone TEXT;\n", encoding="utf-8")
    db.migrate(old, mig)
    assert version(old) == 3 and "phone" in columns(old, "students")

    # 6. numere duplicate / nume invalide
    (mig / "0003_alta.sql").write_text("SELECT 1;\n", encoding="utf-8")
    try:
        db.load_migrations(mig)
        raise AssertionError("trebuia sa esueze (numar duplicat)")
    except RuntimeError:
        pass
    (mig / "0003_alta.sql").unlink()
    (mig / "fara_numar.sql").write_text("SELECT 1;\n", encoding="utf-8")
    try:
        db.load_migrations(mig)
        raise AssertionError("trebuia sa esueze (nume invalid)")
    except RuntimeError:
        pass

    # 7. backup-urile vechi se sterg (raman maxim KEEP_BACKUPS)
    (mig / "fara_numar.sql").unlink()
    for i in range(4, 4 + db.KEEP_BACKUPS + 3):
        (mig / f"{i:04d}_pas.sql").write_text(f"CREATE TABLE t{i}(x);\n", encoding="utf-8")
        db.migrate(old, mig)
    assert len(backups(old.parent)) <= db.KEEP_BACKUPS

    print("OK - migrarile functioneaza")


if __name__ == "__main__":
    main()
