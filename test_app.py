"""Test de fum: parcurge fluxul complet pe o baza de date temporara.

Rulare: .venv\\Scripts\\python.exe test_app.py
"""
import os
import re
import sqlite3
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

    # --- rechizite: cantitatea de comandat vine din voturi (bifa "Ales")
    def ajax(client, url, data, page="/supplies"):
        return client.post(url, data={**data, "csrf": token(client, page)}, headers={"X-Requested-With": "fetch"})

    def sql(query, *params):
        c = sqlite3.connect(os.environ["FOND_DB"])
        try:
            return c.execute(query, params).fetchall()
        finally:
            c.close()

    r = post(admin, "/supplies", {"name": "Caiet dictando", "category": "Caiete", "note": "tip II"}, page="/supplies")
    assert "Rechizit adăugat" in r.get_data(as_text=True)
    post(admin, "/supplies", {"name": "Engleza", "category": "Manual", "qty": "99", "bought": "9"}, page="/supplies")  # campurile vechi sunt ignorate
    r = post(admin, "/supplies", {"name": ""}, page="/supplies")
    assert "Denumirea este obligatorie" in r.get_data(as_text=True)
    post(admin, "/supplies", {"name": "Foarfeca"}, page="/supplies")  # categorie implicita: General
    assert sql("SELECT category FROM supplies WHERE id = 3") == [("General",)]
    assert sql("PRAGMA user_version")[0][0] >= 2

    # pagina nu mai arata cantitate / cumparat / status / butoane -/+
    page_html = admin.get("/supplies").get_data(as_text=True)
    assert "General" in page_html and "tip II" in page_html and "De comandat" in page_html
    for gone in ("Cantitate", "Cumpărat", "Cumpărate", "Parțial", 'class="stepper"', "/adjust"):
        assert gone not in page_html, f"nu mai trebuie afisat: {gone}"
    assert admin.post("/supplies/1/adjust", data={"csrf": token(admin, "/supplies")}).status_code == 404

    # bife per elev; "De comandat" = numarul de voturi (Ales)
    d = "/supplies/1"
    r = ajax(admin, d + "/track", {"student_id": "1", "chosen": "1", "paid": "1"}, page=d)
    assert r.get_json() == {"chosen": 1, "paid": 1, "received": 0}
    r = ajax(admin, d + "/track", {"student_id": "2", "chosen": "1"}, page=d)
    assert r.get_json() == {"chosen": 2, "paid": 1, "received": 0}
    r = ajax(admin, d + "/track", {"student_id": "1", "chosen": "1", "received": "1"}, page=d)  # paid debifat
    assert r.get_json() == {"chosen": 2, "paid": 0, "received": 1}
    assert admin.post(d + "/track", data={"csrf": token(admin, d), "student_id": "999"}).status_code == 404
    with fond.app.app_context():
        assert fond.supply_stats() == {"total": 3, "cu_voturi": 1, "fara_voturi": 2, "de_comandat": 2}
    listing = admin.get("/supplies").get_data(as_text=True)
    assert 'class="order">2<' in listing and "din 3" in listing, "2 voturi din 3 elevi"
    detail = admin.get(d).get_data(as_text=True)
    assert "Popescu Ana" in detail and "Ionescu Mihai" in detail and "Vasile Dan" in detail
    assert 'name="chosen"' in detail and 'id="c-order">2<' in detail and "de comandat" in detail
    assert "Rechizite:" in admin.get("/").get_data(as_text=True)
    assert "2 bucăți de comandat" in admin.get("/").get_data(as_text=True)

    # un elev dezactivat nu mai conteaza la voturi
    post(admin, "/students/2/toggle", {}, page="/students")
    with fond.app.app_context():
        assert fond.supply_stats()["de_comandat"] == 1
    post(admin, "/students/2/toggle", {}, page="/students")
    with fond.app.app_context():
        assert fond.supply_stats()["de_comandat"] == 2

    # filtre, cautare, sortare (se verifica linkurile din tabel, nu textul-exemplu din formular)
    row = lambda html, name: f">{name}</a>" in html
    cu = admin.get("/supplies?votes=cu").get_data(as_text=True)
    assert row(cu, "Caiet dictando") and not row(cu, "Foarfeca") and not row(cu, "Engleza")
    fara = admin.get("/supplies?votes=fara").get_data(as_text=True)
    assert not row(fara, "Caiet dictando") and row(fara, "Foarfeca") and row(fara, "Engleza")
    only_caiete = admin.get("/supplies?cat=Caiete").get_data(as_text=True)
    assert row(only_caiete, "Caiet dictando") and not row(only_caiete, "Foarfeca")
    assert row(admin.get("/supplies?q=foar").get_data(as_text=True), "Foarfeca")
    assert "nu se potrivește" in admin.get("/supplies?q=zzzz").get_data(as_text=True)
    desc = admin.get("/supplies?sort=votes&dir=desc").get_data(as_text=True)
    assert desc.index(">Caiet dictando</a>") < desc.index(">Engleza</a>"), "sortare descrescatoare dupa voturi"
    asc = admin.get("/supplies?sort=votes&dir=asc").get_data(as_text=True)
    assert asc.index(">Engleza</a>") < asc.index(">Caiet dictando</a>"), "sortare crescatoare dupa voturi"
    for sort in ("name", "cat", "votes", "invalid"):
        assert admin.get(f"/supplies?sort={sort}&dir=desc").status_code == 200

    # parintele: doar citire, vede doar bifele copilului lui
    pd = parent.get(d).get_data(as_text=True)
    assert "Popescu Ana" in pd and "Ionescu Mihai" not in pd and "Vasile Dan" not in pd
    assert 'action="/supplies/1/vote"' in pd and "/supplies/1/track" not in pd
    assert 'name="chosen"' in pd and 'name="paid"' not in pd and 'name="received"' not in pd, "Plătit/Primit nu se pot bifa de parinte"
    pl = parent.get("/supplies").get_data(as_text=True)
    assert "Copilul meu" in pl and row(pl, "Caiet dictando") and 'class="order">2<' in pl
    assert "Rechizite:" in parent.get("/").get_data(as_text=True)
    for url, data in (("/supplies", {"name": "X"}), ("/supplies/1/track", {"student_id": "1", "chosen": "1"}),
                      ("/supplies/1/edit", {"name": "X"}), ("/supplies/1/delete", {})):
        assert parent.post(url, data={**data, "csrf": token(parent, "/supplies")}).status_code == 403, url
    assert parent.get("/supplies/1/edit").status_code == 403
    assert parent.get("/export/supplies.csv").status_code == 403
    assert parent.get("/supplies/999").status_code == 404

    # --- parintele voteaza (Ales) pentru copilul lui; Platit / Primit raman la casier
    def vote(client, supply_id, data):
        return client.post(f"/supplies/{supply_id}/vote", data={**data, "csrf": token(client, "/supplies")},
                           headers={"X-Requested-With": "fetch"})

    def tracked(supply_id, student_id):
        return sql("SELECT chosen, paid, received FROM supply_tracking WHERE supply_id = ? AND student_id = ?",
                   supply_id, student_id)

    r = vote(parent, 2, {"chosen": "1"})
    assert r.get_json() == {"chosen": 1, "paid": 0, "received": 0} and tracked(2, 1) == [(1, 0, 0)]
    # incearca sa bifeze Platit / Primit si sa voteze pentru alt elev: se ignora, elevul vine din cont
    vote(parent, 2, {"chosen": "1", "paid": "1", "received": "1", "student_id": "2"})
    assert tracked(2, 1) == [(1, 0, 0)] and tracked(2, 2) == []
    # casierul bifeaza Platit; parintele nu-l poate sterge si nu poate retrage votul
    ajax(admin, "/supplies/2/track", {"student_id": "1", "chosen": "1", "paid": "1"}, page="/supplies/2")
    assert tracked(2, 1) == [(1, 1, 0)]
    assert vote(parent, 2, {"chosen": "1"}).status_code == 200 and tracked(2, 1) == [(1, 1, 0)], "votul repetat pastreaza Platit"
    r = vote(parent, 2, {})
    assert r.status_code == 409 and "plătit" in r.get_json()["error"] and tracked(2, 1) == [(1, 1, 0)]
    # fara plata, votul se poate retrage
    assert tracked(3, 1) == []
    vote(parent, 3, {"chosen": "1"})
    assert tracked(3, 1) == [(1, 0, 0)]
    assert vote(parent, 3, {}).get_json()["chosen"] == 0 and tracked(3, 1) == [(0, 0, 0)]
    with fond.app.app_context():
        assert fond.supply_stats()["de_comandat"] == 3, "votul parintelui conteaza la cantitatea de comandat"
    # casierul nu are elev asociat, elevul dezactivat nu poate vota, anonimul e trimis la login
    assert vote(admin, 3, {"chosen": "1"}).status_code == 403
    post(admin, "/students/1/toggle", {}, page="/students")
    assert vote(parent, 3, {"chosen": "1"}).status_code == 403
    post(admin, "/students/1/toggle", {}, page="/students")
    anon_client = fond.app.test_client()
    r = anon_client.post("/supplies/3/vote", data={"chosen": "1", "csrf": token(anon_client, "/login")})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    # in lista: parintele are caseta Ales, casierul nu
    pl = parent.get("/supplies").get_data(as_text=True)
    assert 'action="/supplies/2/vote"' in pl and 'class="votebox"' in pl
    assert 'class="vote"' not in admin.get("/supplies").get_data(as_text=True)

    # export (admin): cantitatea de comandat si numele elevilor pe coloane
    csv_text = admin.get("/export/supplies.csv").get_data(as_text=True).replace("\r", "")
    assert csv_text.startswith("\ufeffRechizit;Categorie;De comandat (buc.);Ales de")
    assert 'Caiet dictando;Caiete;2;"Ionescu Mihai; Popescu Ana"' in csv_text
    assert "Cantitate" not in csv_text and "Status" not in csv_text

    # editare si stergere (bifele se sterg odata cu rechizitul)
    r = post(admin, "/supplies/3/edit", {"name": "Foarfeca mare", "category": "Diverse", "note": "cu varf rotund"}, page="/supplies/3/edit")
    assert "Rechizit actualizat" in r.get_data(as_text=True) and "Foarfeca mare" in r.get_data(as_text=True)
    r = post(admin, "/supplies/1/delete", {}, page="/supplies")
    body = r.get_data(as_text=True)
    assert "Rechizit șters" in body and 'class="item-name" href="/supplies/1"' not in body
    assert sql("SELECT COUNT(*) FROM supply_tracking WHERE supply_id = 1") == [(0,)]

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
