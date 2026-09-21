"""Test de fum: parcurge fluxul complet pe o baza de date temporara.

Rulare: .venv\\Scripts\\python.exe test_app.py
"""
import os
import re
import tempfile

tmp = tempfile.mkdtemp()
os.environ["FOND_DB"] = os.path.join(tmp, "test.db")

import app as fond  # noqa: E402


def token(client, url="/login"):
    html = client.get(url).get_data(as_text=True)
    m = re.search(r'name="csrf" value="([0-9a-f]+)"', html)
    assert m, f"fara csrf pe {url}"
    return m.group(1)


def post(client, url, data, page=None):
    data = {**data, "csrf": token(client, page or "/login")}
    return client.post(url, data=data, follow_redirects=True)


def main():
    admin = fond.app.test_client()

    # fara utilizatori -> setup
    assert admin.get("/").headers["Location"].endswith("/setup")
    r = post(admin, "/setup", {"username": "casier", "password": "parola123", "class_name": "IX B"}, page="/setup")
    assert "Cont de casier creat" in r.get_data(as_text=True)
    assert admin.get("/setup").status_code == 302  # setup se inchide dupa primul cont

    # CSRF lipsa -> 400
    assert admin.post("/login", data={"username": "x", "password": "y"}).status_code == 400

    r = post(admin, "/login", {"username": "casier", "password": "gresita"})
    assert "greșite" in r.get_data(as_text=True)
    r = post(admin, "/login", {"username": "casier", "password": "parola123"})
    assert "Sold curent" in r.get_data(as_text=True)

    # elevi, contributie, plati
    post(admin, "/students", {"names": "Popescu Ana\nIonescu Mihai\n\nVasile Dan"})
    post(admin, "/contributions", {"name": "Fond septembrie", "amount": "50", "due_date": "2026-09-30"})
    r = post(admin, "/contributions", {"name": "Excursie", "amount": "120,50"})
    assert "120,50 lei" in r.get_data(as_text=True)
    r = post(admin, "/contributions", {"name": "Invalid", "amount": "abc"})
    assert "Suma nu este validă" in r.get_data(as_text=True)

    page = "/contributions/1"
    r = post(admin, "/payments", {"student_id": "1", "contribution_id": "1", "amount": "50",
                                 "paid_on": "2026-09-20", "next": page}, page=page)
    assert "Plată înregistrată" in r.get_data(as_text=True)
    post(admin, "/payments", {"student_id": "2", "contribution_id": "1", "amount": "20",
                              "paid_on": "2026-09-20", "next": page}, page=page)
    r = post(admin, "/payments", {"student_id": "1", "contribution_id": "1", "amount": "-5",
                                 "paid_on": "2026-09-20", "next": page}, page=page)
    assert "mai mare ca zero" in r.get_data(as_text=True)
    r = post(admin, "/payments", {"student_id": "1", "contribution_id": "1", "amount": "5",
                                 "paid_on": "nu-e-data", "next": "https://evil.example"}, page=page)
    assert "Data nu este validă" in r.get_data(as_text=True)

    # cheltuieli
    r = post(admin, "/expenses", {"spent_on": "2026-09-21", "category": "Cadouri", "amount": "30", "description": "Flori"})
    assert "Cheltuială înregistrată" in r.get_data(as_text=True)

    # calcule: incasat 70, cheltuit 30 -> sold 40; restante = (3*50-70) + 3*120,50 = 80 + 361,50 = 441,50
    r = admin.get("/").get_data(as_text=True)
    assert "40,00 lei" in r, r
    assert "441,50 lei" in r, "restante"

    # sold initial
    post(admin, "/settings", {"class_name": "IX B", "opening_balance": "1.000,00"})
    assert "1.040,00 lei" in admin.get("/").get_data(as_text=True)

    # student cu plati nu se sterge
    r = post(admin, "/students/1/delete", {}, page="/students/1")
    assert "nu poate fi șters" in r.get_data(as_text=True)
    r = post(admin, "/contributions/1/delete", {}, page="/contributions/1")
    assert "Există plăți" in r.get_data(as_text=True)

    # cont de parinte pentru elevul 1
    r = post(admin, "/users", {"role": "parent", "username": "parinte1", "password": "parola123", "student_id": "1"})
    assert "Cont creat" in r.get_data(as_text=True)
    r = post(admin, "/users", {"role": "parent", "username": "parinte2", "password": "scurta", "student_id": "1"})
    assert "minim 8" in r.get_data(as_text=True)

    # --- parintele
    parent = fond.app.test_client()
    post(parent, "/login", {"username": "parinte1", "password": "parola123"})
    r = parent.get("/", follow_redirects=True).get_data(as_text=True)
    assert "Popescu Ana" in r and "Ultimele plăți" not in r
    assert parent.get("/me").headers["Location"].endswith("/students/1")
    assert "Fond septembrie" in parent.get("/students/1").get_data(as_text=True)
    assert parent.get("/students/2").status_code == 403, "parintele vede alt elev"
    assert parent.get("/students").status_code == 403
    assert parent.get("/contributions").status_code == 403
    assert parent.get("/users").status_code == 403
    assert parent.get("/export/payments.csv").status_code == 403
    assert "Flori" in parent.get("/expenses").get_data(as_text=True)
    assert "Cheltuială nouă" not in parent.get("/expenses").get_data(as_text=True)
    r = parent.post("/expenses", data={"csrf": token(parent, "/expenses"), "spent_on": "2026-09-21",
                                      "category": "X", "amount": "1"})
    assert r.status_code == 403
    r = parent.post("/payments", data={"csrf": token(parent, "/"), "student_id": "1", "contribution_id": "1",
                                      "amount": "1", "paid_on": "2026-09-21"})
    assert r.status_code == 403
    assert parent.get("/export/expenses.csv").status_code == 200

    # neautentificat
    anon = fond.app.test_client()
    assert "/login" in anon.get("/expenses").headers["Location"]

    # export CSV (BOM + ; + formule neutralizate)
    post(admin, "/expenses", {"spent_on": "2026-09-21", "category": "=HYPERLINK(1)", "amount": "1"})
    csv_text = admin.get("/export/expenses.csv").get_data(as_text=True)
    assert csv_text.startswith("﻿Data;Categorie") and "'=HYPERLINK" in csv_text

    # deconectare
    post(admin, "/logout", {}, page="/")
    assert "/login" in admin.get("/").headers["Location"]

    print("OK - toate verificarile au trecut")


if __name__ == "__main__":
    main()
