"""Teste pentru varianta de productie (wsgi.py): fara /setup public, cont creat din consola, HTTPS, backup.

Rulare: .venv\\Scripts\\python.exe test_deploy.py
"""
import os
import re
import sqlite3
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["FOND_DB"] = str(tmp / "prod.db")

import wsgi  # noqa: E402  (importa si aplicatia; seteaza WEB_SETUP=False, ProxyFix, cookie Secure, HSTS)
import backup_db  # noqa: E402
import create_admin  # noqa: E402

HTTPS = {"base_url": "https://fond.example"}


def visit(client, ip):
    """Cerere prin proxy: IP-ul real al vizitatorului vine in X-Forwarded-For."""
    return {**HTTPS, "headers": {"X-Forwarded-For": ip, "X-Forwarded-Proto": "https"}}


def csrf(client, ip, url="/login"):
    html = client.get(url, **visit(client, ip)).get_data(as_text=True)
    return re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)


def login(client, ip, username, password):
    return client.post("/login", data={"username": username, "password": password, "csrf": csrf(client, ip)},
                       **visit(client, ip))


def main():
    app = wsgi.application
    anon = app.test_client()

    # 1) fara niciun cont: nu se poate crea unul din browser, oricine ar fi vizitatorul
    for url in ("/login", "/"):
        r = anon.get(url, **visit(anon, "203.0.113.5"))
        assert r.status_code == 503 and "nu a fost configurată" in r.get_data(as_text=True), url
    assert anon.get("/setup", **visit(anon, "203.0.113.5")).status_code == 404
    r = anon.post("/setup", data={"username": "hacker", "password": "parola-lunga-1"}, **visit(anon, "203.0.113.5"))
    assert r.status_code == 404
    assert sqlite3.connect(tmp / "prod.db").execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    # nici antetul X-Forwarded-For fals de tip "sunt local" nu deschide /setup
    r = anon.get("/setup", **{**HTTPS, "headers": {"X-Forwarded-For": "127.0.0.1"}})
    assert r.status_code == 404

    # 2) contul de casier se creeaza din consola
    for bad in (("ab", "parola-lunga-1"), ("casier", "scurta")):
        try:
            create_admin.create_admin(*bad)
            raise AssertionError(f"trebuia refuzat: {bad}")
        except ValueError:
            pass
    create_admin.create_admin("casier", "parola-lunga-1", "Clasa a V-a")
    try:
        create_admin.create_admin("Casier", "alta-parola-1")   # acelasi nume (fara diferenta majuscule)
        raise AssertionError("trebuia refuzat: duplicat")
    except ValueError:
        pass
    assert anon.get("/setup", **visit(anon, "203.0.113.5")).status_code == 302   # acum duce la login

    # 3) autentificare prin proxy: cookie sigur, HSTS, fara indexare
    ip_a, ip_b = "203.0.113.9", "203.0.113.10"
    a, b = app.test_client(), app.test_client()
    r = login(a, ip_a, "casier", "parola-lunga-1")
    assert r.status_code == 302
    cookie = "; ".join(r.headers.getlist("Set-Cookie"))
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie, cookie
    page = a.get("/", **visit(a, ip_a))
    assert page.status_code == 200 and "Clasa a V-a" in page.get_data(as_text=True)
    assert page.headers["Strict-Transport-Security"].startswith("max-age=")
    assert page.headers["X-Robots-Tag"] == "noindex, nofollow"
    robots = anon.get("/robots.txt", **visit(anon, ip_a))
    assert robots.status_code == 200 and "Disallow: /" in robots.get_data(as_text=True)

    # 4) limita de incercari e pe IP-ul real (nu pe al proxy-ului): un vizitator blocat nu-i blocheaza pe ceilalti
    attacker = app.test_client()
    for _ in range(5):
        assert login(attacker, "198.51.100.7", "casier", "gresita-123").status_code == 200
    assert login(attacker, "198.51.100.7", "casier", "parola-lunga-1").status_code == 429, "atacatorul e blocat"
    assert login(b, ip_b, "casier", "parola-lunga-1").status_code == 302, "alt IP nu e afectat"

    # 5) resetarea parolei din consola
    try:
        create_admin.reset_password("nu-exista", "parola-lunga-2")
        raise AssertionError("trebuia refuzat: utilizator inexistent")
    except ValueError:
        pass
    try:
        create_admin.reset_password("casier", "scurta")
        raise AssertionError("trebuia refuzat: parola scurta")
    except ValueError:
        pass
    create_admin.reset_password("casier", "parola-noua-2")
    fresh = app.test_client()
    assert login(fresh, "203.0.113.20", "casier", "parola-lunga-1").status_code == 200, "parola veche nu mai merge"
    assert login(app.test_client(), "203.0.113.21", "casier", "parola-noua-2").status_code == 302

    # 6) copie de siguranta: valida, se poate deschide, iar cele vechi se sterg (raman ultimele `keep`)
    folder = tmp / "backups"
    folder.mkdir(exist_ok=True)
    for i in range(5):   # copii mai vechi, cu date din trecut
        (folder / f"prod-zilnic-2020010{i}-000000.db").write_bytes(b"vechi")
    target = backup_db.backup(tmp / "prod.db", keep=3)
    kept = sorted(p.name for p in folder.glob("prod-zilnic-*.db"))
    assert len(kept) == 3 and target.name in kept, kept
    assert "prod-zilnic-20200100-000000.db" not in kept, "cele mai vechi se sterg"
    copy = sqlite3.connect(target)
    assert copy.execute("SELECT username FROM users").fetchall() == [("casier",)]
    assert copy.execute("PRAGMA user_version").fetchone()[0] >= 2
    copy.close()

    print("OK - varianta de productie functioneaza")


if __name__ == "__main__":
    main()
