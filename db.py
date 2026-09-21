import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
KEEP_BACKUPS = 10


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def one(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def scalar(sql, params=()):
    row = get_db().execute(sql, params).fetchone()
    return row[0] if row else None


def execute(sql, params=()):
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur


def get_setting(key, default=""):
    row = one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key, value):
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def load_migrations(directory=MIGRATIONS_DIR):
    """Returneaza [(numar, cale)] pentru fisierele NNNN_descriere.sql, in ordine."""
    found = {}
    for path in Path(directory).glob("*.sql"):
        m = re.match(r"(\d+)_", path.name)
        if not m:
            raise RuntimeError(f"Nume de migrare invalid: {path.name} (foloseste 0002_descriere.sql)")
        number = int(m.group(1))
        if number in found:
            raise RuntimeError(f"Doua migrari cu numarul {number}: {found[number].name}, {path.name}")
        found[number] = path
    return [(n, found[n]) for n in sorted(found)]


def _statements(sql):
    """Imparte un script SQL in instructiuni (executate pe rand, in tranzactia migrarii)."""
    buf = ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            yield buf
            buf = ""
    if buf.strip():
        yield buf


def _backup(conn, db_file, version):
    folder = db_file.parent / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"{db_file.stem}-v{version}-{datetime.now():%Y%m%d-%H%M%S}.db"
    dest = sqlite3.connect(target)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    by_age = sorted(folder.glob(f"{db_file.stem}-v*.db"), key=lambda f: f.stat().st_mtime_ns)
    for old in by_age[:-KEEP_BACKUPS]:
        old.unlink()


def migrate(db_path, directory=MIGRATIONS_DIR):
    """Aplica migrarile lipsa. Versiunea structurii e tinuta in PRAGMA user_version.

    Fiecare migrare ruleaza intr-o tranzactie (la eroare se anuleaza complet), iar inainte de
    prima migrare aplicata pe o baza de date existenta se face o copie in instance/backups/.
    """
    migrations = load_migrations(directory)
    db_file = Path(db_path)
    existed = db_file.exists() and db_file.stat().st_size > 0
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        pending = [(n, p) for n, p in migrations if n > current]
        if not pending:
            return
        if existed:
            _backup(conn, db_file, current)
        for number, path in pending:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # un alt proces (ex: al doilea worker al hostingului) poate sa o fi aplicat deja
                if conn.execute("PRAGMA user_version").fetchone()[0] >= number:
                    conn.execute("ROLLBACK")
                    continue
                for statement in _statements(path.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {number}")
                conn.execute("COMMIT")
            except Exception as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise RuntimeError(f"Migrarea {path.name} a esuat: {exc}") from exc
    finally:
        conn.close()


def init_db():
    migrate(current_app.config["DATABASE"])


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
