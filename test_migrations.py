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
    mig.mkdir()
    # doar migrarea initiala: restul testelor adauga propriile migrari deasupra ei
    shutil.copy(db.MIGRATIONS_DIR / "0001_initial.sql", mig)

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

    # migrarile reale ale proiectului se aplica una dupa alta, atat pe baza noua cat si pe una veche
    real = db.load_migrations()
    assert [n for n, _ in real] == list(range(1, len(real) + 1)), "numerotare fara goluri"
    latest = real[-1][0]
    fresh_real = work / "real" / "fond.db"
    fresh_real.parent.mkdir()
    db.migrate(fresh_real)
    assert version(fresh_real) == latest
    assert "price" in columns(fresh_real, "supplies")
    assert {"paid_on", "paid_amount"} <= set(columns(fresh_real, "supply_tracking"))
    upgrade = work / "upgrade" / "fond.db"
    upgrade.parent.mkdir()
    conn = sqlite3.connect(upgrade)
    conn.executescript((db.MIGRATIONS_DIR / "0001_initial.sql").read_text(encoding="utf-8"))
    conn.execute("INSERT INTO students(name) VALUES ('Popescu Ana')")
    conn.commit()
    conn.execute("PRAGMA user_version = 1")
    conn.close()
    db.migrate(upgrade)
    assert version(upgrade) == latest
    conn = sqlite3.connect(upgrade)
    assert conn.execute("SELECT name FROM students").fetchall() == [("Popescu Ana",)]
    conn.close()

    # 9) migrarea 0003 (roluri): pe o baza cu utilizatori si date legate de ei nu se pierde nimic
    v2 = work / "v2" / "fond.db"
    v2.parent.mkdir()
    only12 = work / "only12"
    only12.mkdir()
    for name in ("0001_initial.sql", "0002_rechizite.sql"):
        shutil.copy(db.MIGRATIONS_DIR / name, only12)
    db.migrate(v2, only12)
    assert version(v2) == 2
    conn = sqlite3.connect(v2)
    conn.executescript("""
        INSERT INTO students(id, name) VALUES (1, 'Popescu Ana');
        INSERT INTO users(id, username, password_hash, role, student_id) VALUES
            (1, 'casier', 'hash-admin', 'admin', NULL), (2, 'parinte', 'hash-parent', 'parent', 1);
        INSERT INTO contributions(id, name, amount) VALUES (1, 'Fond', 5000);
        INSERT INTO payments(student_id, contribution_id, amount, paid_on, created_by) VALUES (1, 1, 5000, '2026-09-01', 1);
        INSERT INTO expenses(spent_on, category, amount, created_by) VALUES ('2026-09-02', 'Cadouri', 1000, 1);
    """)
    conn.commit()
    conn.close()
    db.migrate(v2)                       # aplica 0003 (si orice migrare ulterioara)
    assert version(v2) == latest
    conn = sqlite3.connect(v2)
    assert conn.execute("SELECT id, username, password_hash, role, student_id FROM users ORDER BY id").fetchall() == [
        (1, "casier", "hash-admin", "admin", None), (2, "parinte", "hash-parent", "parent", 1)], "utilizatorii raman neschimbati"
    assert conn.execute("SELECT created_by FROM payments").fetchall() == [(1,)]
    assert conn.execute("SELECT created_by FROM expenses").fetchall() == [(1,)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.execute("INSERT INTO users(username, password_hash, role) VALUES ('casier2', 'h', 'casier')")   # rol nou permis
    try:
        conn.execute("INSERT INTO users(username, password_hash, role) VALUES ('x', 'h', 'zeu')")
        raise AssertionError("un rol necunoscut trebuia refuzat")
    except sqlite3.IntegrityError:
        pass
    try:
        conn.execute("INSERT INTO users(username, password_hash, role) VALUES ('CASIER', 'h', 'casier')")
        raise AssertionError("numele de utilizator ramane unic, fara diferenta majuscule")
    except sqlite3.IntegrityError:
        pass
    conn.close()

    print("OK - migrarile functioneaza")


if __name__ == "__main__":
    main()
