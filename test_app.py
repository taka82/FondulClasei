"""Test de fum: parcurge fluxul complet pe o baza de date temporara.

Rulare: .venv\\Scripts\\python.exe test_app.py
"""
import os
from datetime import date
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
    assert "Cont de administrator creat" in r.get_data(as_text=True)
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
    # parintele NU vede Panoul: e trimis la situatia copilului; soldul si totalurile clasei nu apar nicaieri la el
    redirected = parent.get("/")
    assert redirected.status_code == 302 and redirected.headers["Location"].endswith("/students/1")
    for hidden in ("Sold curent", "Total încasat", "Total cheltuit", "Restanțe", "Panou"):
        assert hidden not in r, f"parintele nu are voie sa vada: {hidden}"
    assert parent.get("/me").headers["Location"].endswith("/students/1")
    login_again = fond.app.test_client()
    landing = login_again.post("/login", data={"username": "parinte1", "password": "parola123",
                                                "csrf": token(login_again, "/login")})
    assert landing.headers["Location"].endswith("/students/1"), "dupa autentificare parintele ajunge la copilul lui"
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
    r = parent.post("/payments", data={"csrf": token(parent, "/expenses"), "student_id": "1", "contribution_id": "1",
                                      "amount": "1", "paid_on": "2026-09-21"})
    assert r.status_code == 403
    assert parent.get("/export/expenses.csv").status_code == 200

    # meniul: casierul are alta ordine decat parintele
    def menu(html):
        nav = re.search(r"<nav.*?</nav>", html, re.S).group(0)
        return re.findall(r'<a href="[^"]*"[^>]*>([^<]+)</a>', nav)

    assert menu(parent.get("/students/1").get_data(as_text=True)) == ["Situația mea", "Rechizite", "Cheltuieli"]
    assert menu(parent.get("/supplies").get_data(as_text=True)) == ["Situația mea", "Rechizite", "Cheltuieli"]
    assert menu(admin.get("/").get_data(as_text=True)) == ["Panou", "Elevi", "Contribuții", "Rechizite", "Cheltuieli", "Conturi", "Setări"]
    assert 'class="on">Situația mea' in parent.get("/students/1").get_data(as_text=True)
    assert 'class="on">Panou' in admin.get("/").get_data(as_text=True)

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
    assert 'data-field="chosen"' in pd and 'data-field="received"' in pd, "parintele poate bifa Ales si Primit"
    assert 'data-field="paid"' not in pd and 'name="paid"' not in pd
    assert re.search(r'class="ck paid" disabled', pd), "Plătit ramane dezactivat pentru parinte"
    pl = parent.get("/supplies").get_data(as_text=True)
    assert "Copilul meu" in pl and row(pl, "Caiet dictando") and 'class="order">2<' in pl
    assert "Rechizite:" not in parent.get("/", follow_redirects=True).get_data(as_text=True), "cardul cu bucati de comandat e doar pentru casier"
    for url, data in (("/supplies", {"name": "X"}), ("/supplies/1/track", {"student_id": "1", "chosen": "1"}),
                      ("/supplies/1/edit", {"name": "X"}), ("/supplies/1/delete", {})):
        assert parent.post(url, data={**data, "csrf": token(parent, "/supplies")}).status_code == 403, url
    assert parent.get("/supplies/1/edit").status_code == 403
    assert parent.get("/export/supplies.csv").status_code == 403
    assert parent.get("/supplies/999").status_code == 404

    # --- parintele bifeaza Ales / Primit pentru copilul lui; Platit ramane la casier
    def vote(client, supply_id, field, value):
        return client.post(f"/supplies/{supply_id}/vote",
                           data={"field": field, "value": value, "csrf": token(client, "/supplies")},
                           headers={"X-Requested-With": "fetch"})

    def tracked(supply_id, student_id):
        return sql("SELECT chosen, paid, received FROM supply_tracking WHERE supply_id = ? AND student_id = ?",
                   supply_id, student_id)

    r = vote(parent, 2, "chosen", "1")
    assert r.get_json() == {"chosen": 1, "paid": 0, "received": 0} and tracked(2, 1) == [(1, 0, 0)]
    # o cerere care incearca sa bifeze Platit, sa trimita alte campuri sau sa vizeze alt elev: nu are efect
    assert vote(parent, 2, "paid", "1").status_code == 400
    assert vote(parent, 2, "chosen", "da").status_code == 400
    assert vote(parent, 2, "student_id", "2").status_code == 400
    parent.post("/supplies/2/vote", data={"field": "chosen", "value": "1", "student_id": "2", "paid": "1",
                                          "received": "1", "csrf": token(parent, "/supplies")})
    assert tracked(2, 1) == [(1, 0, 0)] and tracked(2, 2) == [], "elevul vine din cont, nu din cerere"
    # Primit: se bifeaza si se debifeaza fara sa se atinga Ales
    r = vote(parent, 2, "received", "1")
    assert r.get_json() == {"chosen": 1, "paid": 0, "received": 1} and tracked(2, 1) == [(1, 0, 1)]
    # cat timp e primit, votul nu se poate retrage (trebuie debifat intai Primit)
    r = vote(parent, 2, "chosen", "0")
    assert r.status_code == 409 and "Primit" in r.get_json()["error"] and tracked(2, 1) == [(1, 0, 1)]
    assert vote(parent, 2, "received", "0").get_json() == {"chosen": 1, "paid": 0, "received": 0}
    # casierul bifeaza Platit; parintele nu-l poate schimba si nu poate retrage votul
    ajax(admin, "/supplies/2/track", {"student_id": "1", "chosen": "1", "paid": "1"}, page="/supplies/2")
    assert tracked(2, 1) == [(1, 1, 0)]
    assert vote(parent, 2, "chosen", "1").status_code == 200 and tracked(2, 1) == [(1, 1, 0)], "Platit se pastreaza"
    assert vote(parent, 2, "received", "1").get_json() == {"chosen": 1, "paid": 1, "received": 1}
    assert vote(parent, 2, "received", "0").get_json() == {"chosen": 1, "paid": 1, "received": 0}
    r = vote(parent, 2, "chosen", "0")
    assert r.status_code == 409 and "plătit" in r.get_json()["error"] and tracked(2, 1) == [(1, 1, 0)]
    # fara plata / primire, votul se poate retrage
    assert tracked(3, 1) == []
    vote(parent, 3, "chosen", "1")
    assert tracked(3, 1) == [(1, 0, 0)]
    assert vote(parent, 3, "chosen", "0").get_json()["chosen"] == 0 and tracked(3, 1) == [(0, 0, 0)]
    with fond.app.app_context():
        assert fond.supply_stats()["de_comandat"] == 3, "votul parintelui conteaza la cantitatea de comandat"
    # casierul nu are elev asociat, elevul dezactivat nu poate bifa, anonimul e trimis la login
    assert vote(admin, 3, "chosen", "1").status_code == 403
    post(admin, "/students/1/toggle", {}, page="/students")
    assert vote(parent, 3, "chosen", "1").status_code == 403
    post(admin, "/students/1/toggle", {}, page="/students")
    anon_client = fond.app.test_client()
    r = anon_client.post("/supplies/3/vote", data={"field": "chosen", "value": "1", "csrf": token(anon_client, "/login")})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    # in lista: parintele are casetele Ales si Primit (nu Platit), casierul nu are formularul de vot
    pl = parent.get("/supplies").get_data(as_text=True)
    assert 'action="/supplies/2/vote"' in pl and pl.count('class="votebox"') >= 2 * 2
    # indicatorul de plata: "Plătit" (verde) cand e platit, "Neplătit" (gri) cand nu e; niciodata un "Plătit" gri
    assert 'class="pip on paid"' in pl and ">Plătit</span>" in pl, "Engleza e platita"
    assert re.search(r'<span class="pip"[^>]*>Neplătit</span>', pl), "Caiet dictando nu e platit"
    assert not re.search(r'<span class="pip"[^>]*>Plătit</span>', pl), "nu mai apare un Plătit gri, care induce in eroare"
    assert 'data-field="chosen"' in pl and 'data-field="received"' in pl and 'data-field="paid"' not in pl
    assert 'class="vote"' not in admin.get("/supplies").get_data(as_text=True)

    # pagina "Situatia mea" a parintelui arata rechizitele copilului, inclusiv ce a platit
    # (elevul 1: Caiet = ales + primit, neplatit; Engleza = ales + platit; Foarfeca = neatinsa)
    mine_page = parent.get("/students/1").get_data(as_text=True)
    assert "<h2>Rechizite</h2>" in mine_page
    assert row(mine_page, "Engleza") and row(mine_page, "Caiet dictando") and not row(mine_page, "Foarfeca")
    assert 'badge ok">Plătit' in mine_page, "manualul platit apare cu starea Plătit"
    assert 'badge warn">Neplătit' in mine_page, "rechizitul ales dar neplatit apare ca Neplătit"
    # ordinea sectiunilor: la parinte Rechizite e prima; la casier contributiile raman primele
    assert mine_page.index("<h2>Rechizite</h2>") < mine_page.index("<h2>Contribuții</h2>") < mine_page.index("<h2>Istoric plăți</h2>")
    adm_page = admin.get("/students/1").get_data(as_text=True)
    assert adm_page.index("<h2>Contribuții</h2>") < adm_page.index("<h2>Rechizite</h2>") < adm_page.index("<h2>Istoric plăți</h2>")
    assert adm_page.count("<h2>Rechizite</h2>") == 1 and mine_page.count("<h2>Rechizite</h2>") == 1
    # casierul vede aceleasi date pe pagina elevului, iar alt elev are doar rechizitele lui
    assert row(admin.get("/students/1").get_data(as_text=True), "Engleza")
    other = admin.get("/students/2").get_data(as_text=True)
    assert row(other, "Caiet dictando") and not row(other, "Engleza"), "elevul 2 nu are Engleza"
    assert "Niciun rechizit ales" in admin.get("/students/3").get_data(as_text=True)

    # --- pretul rechizitelor (informativ): se seteaza de casier, il vad toti, totalul doar casierul
    assert sql("SELECT COUNT(*) FROM pragma_table_info('supplies') WHERE name = 'price'") == [(1,)]
    edit_url = "/supplies/1/edit"
    same = {"name": "Caiet dictando", "category": "Caiete", "note": "tip II"}
    r = post(admin, edit_url, {**same, "price": "12,50"}, page=edit_url)
    assert "Rechizit actualizat" in r.get_data(as_text=True) and sql("SELECT price FROM supplies WHERE id = 1") == [(1250,)]
    for bad in ("abc", "0", "-5"):
        r = post(admin, edit_url, {**same, "price": bad}, page=edit_url)
        assert "Prețul nu este valid" in r.get_data(as_text=True), bad
        assert sql("SELECT price FROM supplies WHERE id = 1") == [(1250,)], "pretul ramane neschimbat la o valoare gresita"
    post(admin, "/supplies", {"name": "Caiet mate", "category": "Caiete", "price": "3"}, page="/supplies")
    assert sql("SELECT price FROM supplies WHERE name = 'Caiet mate'") == [(300,)]
    assert "Prețul nu este valid" in post(admin, "/supplies", {"name": "Fara pret valid", "price": "x"}, page="/supplies").get_data(as_text=True)
    assert sql("SELECT COUNT(*) FROM supplies WHERE name = 'Fara pret valid'") == [(0,)]
    post(admin, "/supplies", {"name": "Fara pret"}, page="/supplies")
    assert sql("SELECT price FROM supplies WHERE name = 'Fara pret'") == [(None,)], "pretul e optional"
    listing = admin.get("/supplies").get_data(as_text=True)
    assert "12,50 lei" in listing and "3,00 lei" in listing and '<span class="muted">—</span></td>' in listing
    sorted_desc = admin.get("/supplies?sort=price&dir=desc").get_data(as_text=True)
    assert sorted_desc.index(">Caiet dictando</a>") < sorted_desc.index(">Caiet mate</a>") < sorted_desc.index(">Engleza</a>")
    detail = admin.get("/supplies/1").get_data(as_text=True)
    assert "preț: <strong>12,50 lei</strong>" in detail
    assert 'id="c-total" data-price="1250">25,00 lei' in detail, "total de comandat = pret x voturi (2 x 12,50)"
    assert 'value="12,50"' in admin.get(edit_url).get_data(as_text=True), "formularul de editare arata pretul"
    # parintele vede pretul (lista, detalii, Situatia mea), dar nu totalul de comandat
    assert "12,50 lei" in parent.get("/supplies").get_data(as_text=True)
    parent_detail = parent.get("/supplies/1").get_data(as_text=True)
    assert "preț: <strong>12,50 lei</strong>" in parent_detail and 'id="c-total"' not in parent_detail
    assert "12,50 lei" in parent.get("/students/1").get_data(as_text=True)
    # pretul e informativ: nu schimba soldul fondului
    assert sql("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE contribution_id IN (SELECT id FROM contributions)")[0][0] >= 0

    # --- restante: contributii + rechizite (alese si neplatite, la pretul lor) pe pagina Elevi
    def strip(cell):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()

    def student_cells(html, name):
        row = re.search(r"<tr[^>]*>(?:(?!</tr>).)*?>%s</a>(?:(?!</tr>).)*?</tr>" % re.escape(name), html, re.S).group(0)
        return [strip(c) for c in re.findall(r'<td class="num[^"]*">(.*?)</td>', row, re.S)]

    sup_id = lambda name: sql("SELECT id FROM supplies WHERE name = ?", name)[0][0]
    # elevul 3: Caiet mate (3,00) ales si neplatit; "Fara pret" ales si neplatit, dar fara pret
    for name in ("Caiet mate", "Fara pret"):
        assert ajax(admin, f"/supplies/{sup_id(name)}/track", {"student_id": "3", "chosen": "1"}, page="/supplies").status_code == 200
    page_students = admin.get("/students").get_data(as_text=True)
    # [platit, restanta contributii, restanta rechizite, total]
    assert student_cells(page_students, "Popescu Ana") == ["50,00 lei", "120,50 lei", "12,50 lei", "133,00 lei"]
    assert student_cells(page_students, "Ionescu Mihai") == ["20,00 lei", "150,50 lei", "12,50 lei", "163,00 lei"]
    assert student_cells(page_students, "Vasile Dan") == ["0,00 lei", "170,50 lei", "3,00 lei +1 fără preț", "173,50 lei"]
    tfoot = strip(re.search(r"<tfoot>(.*?)</tfoot>", page_students, re.S).group(1))
    assert tfoot == "Total 70,00 lei 441,50 lei 28,00 lei 469,50 lei", tfoot
    assert "Restanță" in page_students and "Rechizite" in page_students
    # bifa Plătit la rechizit scoate suma din restanta; rechizitul fara pret ramane doar semnalat
    ajax(admin, f"/supplies/{sup_id('Caiet mate')}/track", {"student_id": "3", "chosen": "1", "paid": "1"}, page="/supplies")
    assert student_cells(admin.get("/students").get_data(as_text=True), "Vasile Dan") == ["0,00 lei", "170,50 lei", "0,00 lei +1 fără preț", "170,50 lei"]
    ajax(admin, f"/supplies/{sup_id('Caiet mate')}/track", {"student_id": "3", "chosen": "1"}, page="/supplies")   # inapoi la neplatit
    # elev dezactivat: fara restante
    post(admin, "/students/3/toggle", {}, page="/students")
    assert student_cells(admin.get("/students").get_data(as_text=True), "Vasile Dan")[1:] == ["0,00 lei", "0,00 lei", "0,00 lei"]
    post(admin, "/students/3/toggle", {}, page="/students")
    # panou: Restante = contributii + rechizite, cu mentiune separata
    dash = admin.get("/").get_data(as_text=True)
    assert "469,50 lei" in dash and "din care rechizite: 28,00 lei" in dash
    assert "469,50 lei" not in parent.get("/", follow_redirects=True).get_data(as_text=True), "totalul restantelor clasei nu e pentru parinte"
    # pagina elevului: restanta la rechizite (si pentru parinte, doar a copilului lui)
    assert "Restanță la rechizite:" in parent.get("/students/1").get_data(as_text=True)
    assert "12,50 lei" in strip(re.search(r'<p class="owed-line">(.*?)</p>', parent.get("/students/1").get_data(as_text=True), re.S).group(1))
    assert "+ 1 fără preț stabilit" in admin.get("/students/3").get_data(as_text=True)
    assert parent.get("/students/3").status_code == 403
    # export restante: contributii si rechizite
    restante = admin.get("/export/restante.csv").get_data(as_text=True).replace("\r", "")
    assert restante.startswith("\ufeffElev;Contribuție / rechizit;De plătit (lei);Plătit (lei);Rest (lei)")
    assert "Popescu Ana;Excursie;120,50;0,00;120,50" in restante
    assert "Popescu Ana;Rechizit: Caiet dictando;12,50;0,00;12,50" in restante
    assert "Vasile Dan;Rechizit: Caiet mate;3,00;0,00;3,00" in restante
    assert "Vasile Dan;Rechizit: Fara pret (fără preț);;0,00;" in restante
    assert "Engleza" not in restante, "rechizitul platit nu e restanta"

    # --- plata la rechizite apare in Istoric plati (data + suma de la momentul platii)
    today_iso = date.today().isoformat()

    def paid_state(supply_id, student_id):
        return sql("SELECT paid, paid_on, paid_amount FROM supply_tracking WHERE supply_id = ? AND student_id = ?",
                   supply_id, student_id)

    def history_rows(html):
        section = re.search(r"<h2>Istoric plăți</h2>(.*?)</section>", html, re.S).group(1)
        rows = [r for r in re.findall(r"<tr>(.*?)</tr>", section, re.S) if "<td" in r]
        return [[strip(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)] for r in rows]

    assert paid_state(2, 1) == [(1, today_iso, None)], "Engleza (fara pret) platita: data azi, suma necunoscuta"
    ajax(admin, "/supplies/1/track", {"student_id": "2", "chosen": "1", "paid": "1"}, page="/supplies/1")
    assert paid_state(1, 2) == [(1, today_iso, 1250)], "data de azi si pretul din acel moment (12,50)"
    post(admin, "/supplies/1/edit", {"name": "Caiet dictando", "category": "Caiete", "price": "20", "note": "tip II"}, page="/supplies/1/edit")
    assert paid_state(1, 2) == [(1, today_iso, 1250)], "pretul schimbat ulterior nu modifica plata deja facuta"
    c = sqlite3.connect(os.environ["FOND_DB"])
    c.execute("UPDATE supply_tracking SET paid_on = '2026-01-05' WHERE supply_id = 1 AND student_id = 2")   # simulam o plata mai veche
    c.commit()
    c.close()
    ajax(admin, "/supplies/1/track", {"student_id": "2", "chosen": "1", "paid": "1", "received": "1"}, page="/supplies/1")
    assert paid_state(1, 2) == [(1, "2026-01-05", 1250)], "o noua salvare cu Plătit bifat nu schimba data si suma"
    # istoricul: contributii + rechizite, cele mai recente primele
    rows2 = history_rows(admin.get("/students/2").get_data(as_text=True))
    assert [r[:3] for r in rows2] == [["21.09.2026", "cheltuială Cadouri", "10,00 lei din 30,00 lei · 3 elevi"],
                                     ["20.09.2026", "Fond septembrie", "20,00 lei"],
                                     ["05.01.2026", "Rechizit: Caiet dictando", "12,50 lei"]], rows2
    # parintele elevului 1 vede ce a platit (contributie + rechizit), fara butoane de stergere
    parent_history = parent.get("/students/1").get_data(as_text=True)
    assert sorted(r[:3] for r in history_rows(parent_history)) == sorted([
        [date.today().strftime("%d.%m.%Y"), "Rechizit: Engleza", "preț nestabilit"],
        ["20.09.2026", "Fond septembrie", "50,00 lei"],
        ["21.09.2026", "cheltuială Cadouri", "10,00 lei din 30,00 lei · 3 elevi"]])
    assert "Ștergi această plată" not in parent_history and "payment_delete" not in parent_history
    # exportul de plati are si rechizitele
    plati = admin.get("/export/payments.csv").get_data(as_text=True).replace("\r", "")
    assert plati.startswith("\ufeffData;Elev;Contribuție / rechizit;Suma (lei);Observații")
    assert "2026-01-05;Ionescu Mihai;Rechizit: Caiet dictando;12,50;" in plati
    assert f"{today_iso};Popescu Ana;Rechizit: Engleza;;" in plati
    # debifarea Platit sterge data si suma si scoate randul din istoric
    ajax(admin, "/supplies/1/track", {"student_id": "2", "chosen": "1"}, page="/supplies/1")
    assert paid_state(1, 2) == [(0, None, None)]
    assert "Rechizit: Caiet dictando" not in admin.get("/students/2").get_data(as_text=True).split("<h2>Istoric plăți</h2>")[1]
    # un elev cu plati la rechizite nu se poate sterge (s-ar pierde istoricul); dupa anulare se poate
    post(admin, "/students", {"names": "Elev Temp"}, page="/students")
    tid = sql("SELECT id FROM students WHERE name = 'Elev Temp'")[0][0]
    ajax(admin, "/supplies/1/track", {"student_id": str(tid), "chosen": "1", "paid": "1"}, page="/supplies/1")
    r = post(admin, f"/students/{tid}/delete", {}, page=f"/students/{tid}")
    assert "nu poate fi șters" in r.get_data(as_text=True) and sql("SELECT COUNT(*) FROM students WHERE id = ?", tid) == [(1,)]
    ajax(admin, "/supplies/1/track", {"student_id": str(tid)}, page="/supplies/1")
    assert "Elev șters" in post(admin, f"/students/{tid}/delete", {}, page=f"/students/{tid}").get_data(as_text=True)
    assert sql("SELECT COUNT(*) FROM supply_tracking WHERE student_id = ?", tid) == [(0,)]
    # se readuce pretul la valoarea initiala, pentru verificarile de mai jos
    post(admin, "/supplies/1/edit", {"name": "Caiet dictando", "category": "Caiete", "price": "12,50", "note": "tip II"}, page="/supplies/1/edit")
    assert sql("SELECT price FROM supplies WHERE id = 1") == [(1250,)]

    # --- cheltuielile se impart egal intre elevi; partea fiecaruia apare in istoricul lui
    def shares(expense_id):
        return sql("SELECT student_id, amount FROM expense_shares WHERE expense_id = ? ORDER BY student_id", expense_id)

    flori = sql("SELECT id FROM expenses WHERE description = 'Flori'")[0][0]
    assert shares(flori) == [(1, 1000), (2, 1000), (3, 1000)], "30,00 lei / 3 elevi = 10,00 lei fiecare"

    # suma care nu se imparte exact: 100,01 lei / 3 -> 33,34 + 33,34 + 33,33 (totalul ramane exact)
    assert "Cheltuială înregistrată" in post(admin, "/expenses", {"spent_on": "2026-09-23", "category": "Test impartire",
                                                                "amount": "100,01", "description": "rest de bani"}, page="/expenses").get_data(as_text=True)
    eid = sql("SELECT id FROM expenses WHERE category = 'Test impartire'")[0][0]
    assert shares(eid) == [(1, 3334), (2, 3334), (3, 3333)]
    assert sum(a for _, a in shares(eid)) == 10001

    # elevii vad partea lor: elevul 1 -> 33,34, elevul 3 -> 33,33
    assert ["23.09.2026", "cheltuială Test impartire", "33,34 lei din 100,01 lei · 3 elevi"] in \
        [r[:3] for r in history_rows(parent.get("/students/1").get_data(as_text=True))]
    assert ["23.09.2026", "cheltuială Test impartire", "33,33 lei din 100,01 lei · 3 elevi"] in \
        [r[:3] for r in history_rows(admin.get("/students/3").get_data(as_text=True))]
    # parintele nu vede partile altor elevi
    assert "33,33 lei din" not in parent.get("/students/1").get_data(as_text=True)
    assert "Ștergi această plată" not in parent.get("/students/1").get_data(as_text=True)
    me_page = parent.get("/students/1").get_data(as_text=True)
    assert "Partea copilului din cheltuieli, în total:" in me_page and "Nu se adaugă la restanțe" in me_page
    # pagina Cheltuieli si exportul arata cati elevi si cat revine fiecaruia
    exp_page = parent.get("/expenses").get_data(as_text=True)
    assert "Pe elev" in exp_page and "~33,34 lei" in exp_page and "3 elevi" in exp_page
    exp_csv = admin.get("/export/expenses.csv").get_data(as_text=True).replace("\r", "")
    assert "Descriere;Elevi;Parte pe elev (lei)" in exp_csv and "rest de bani;3;33,34" in exp_csv

    # elev dezactivat: nu primeste parte din cheltuielile noi
    post(admin, "/students/3/toggle", {}, page="/students")
    post(admin, "/expenses", {"spent_on": "2026-09-24", "category": "Fara elevul 3", "amount": "10"}, page="/expenses")
    e2 = sql("SELECT id FROM expenses WHERE category = 'Fara elevul 3'")[0][0]
    assert shares(e2) == [(1, 500), (2, 500)], "doar elevii activi de la momentul cheltuielii"
    post(admin, "/students/3/toggle", {}, page="/students")
    assert shares(e2) == [(1, 500), (2, 500)], "reactivarea nu adauga retroactiv parti"

    # editarea sumei recalculeaza partile pentru aceiasi elevi (inclusiv cand un elev e intre timp dezactivat)
    post(admin, "/students/1/toggle", {}, page="/students")     # elevul 1 dezactivat intre timp
    post(admin, f"/expenses/{eid}/edit", {"spent_on": "2026-09-23", "category": "Test impartire", "amount": "200",
                                          "description": "rest de bani"}, page=f"/expenses/{eid}/edit")
    post(admin, "/students/1/toggle", {}, page="/students")
    assert shares(eid) == [(1, 6667), (2, 6667), (3, 6666)], "20000 bani / 3 = 6667 + 6667 + 6666"
    assert sum(a for _, a in shares(eid)) == 20000

    # elev nou: primeste parte doar din cheltuielile de dupa aparitia lui; se poate sterge daca n-are plati
    post(admin, "/students", {"names": "Elev Temp2"}, page="/students")
    tid2 = sql("SELECT id FROM students WHERE name = 'Elev Temp2'")[0][0]
    assert sql("SELECT COUNT(*) FROM expense_shares WHERE student_id = ?", tid2) == [(0,)]
    post(admin, "/expenses", {"spent_on": "2026-09-25", "category": "Cu elev nou", "amount": "4"}, page="/expenses")
    e3 = sql("SELECT id FROM expenses WHERE category = 'Cu elev nou'")[0][0]
    assert [sid for sid, _ in shares(e3)] == [1, 2, 3, tid2]
    assert "Șterge elevul" in admin.get(f"/students/{tid2}").get_data(as_text=True), "partile din cheltuieli nu blocheaza stergerea"
    assert "Elev șters" in post(admin, f"/students/{tid2}/delete", {}, page=f"/students/{tid2}").get_data(as_text=True)
    assert [sid for sid, _ in shares(e3)] == [1, 2, 3]

    # stergerea cheltuielii sterge si partile; se revine la starea initiala pentru verificarile de mai jos
    for e in (eid, e2, e3):
        post(admin, f"/expenses/{e}/delete", {}, page="/expenses")
        assert shares(e) == []
    assert shares(flori) == [(1, 1000), (2, 1000), (3, 1000)]

    # export (admin): cantitatea de comandat si numele elevilor pe coloane
    csv_text = admin.get("/export/supplies.csv").get_data(as_text=True).replace("\r", "")
    assert csv_text.startswith("\ufeffRechizit;Categorie;Preț (lei);De comandat (buc.);Total de comandat (lei);Ales de")
    assert 'Caiet dictando;Caiete;12,50;2;25,00;"Ionescu Mihai; Popescu Ana"' in csv_text, csv_text
    assert "Engleza;Manual;;1;;Popescu Ana;Popescu Ana;" in csv_text, "fara pret: coloanele de pret raman goale"
    assert "Cantitate" not in csv_text and "Status" not in csv_text

    # editare si stergere (bifele se sterg odata cu rechizitul)
    r = post(admin, "/supplies/3/edit", {"name": "Foarfeca mare", "category": "Diverse", "note": "cu varf rotund"}, page="/supplies/3/edit")
    assert "Rechizit actualizat" in r.get_data(as_text=True) and "Foarfeca mare" in r.get_data(as_text=True)
    r = post(admin, "/supplies/1/delete", {}, page="/supplies")
    body = r.get_data(as_text=True)
    assert "Rechizit șters" in body and 'class="item-name" href="/supplies/1"' not in body
    assert sql("SELECT COUNT(*) FROM supply_tracking WHERE supply_id = 1") == [(0,)]

    # --- roluri: administrator (orice), casier (bani si rechizite, fara conturi/setari), parinte
    r = post(admin, "/users", {"role": "casier", "username": "casier1", "password": "parola123"}, page="/users")
    assert "Cont creat" in r.get_data(as_text=True)
    users_page = admin.get("/users").get_data(as_text=True)
    assert "Administrator" in users_page and "Casier" in users_page and "Părinte" in users_page
    assert sql("SELECT role, student_id FROM users WHERE username = 'casier1'") == [("casier", None)]
    cas = fond.app.test_client()
    post(cas, "/login", {"username": "casier1", "password": "parola123"})
    cas_home = cas.get("/").get_data(as_text=True)
    assert "Ultimele plăți" in cas_home and "Rechizite:" in cas_home, "casierul are panoul complet"
    assert menu(cas.get("/").get_data(as_text=True)) == ["Panou", "Elevi", "Contribuții", "Rechizite", "Cheltuieli"]
    for url in ("/students", "/students/1", "/contributions", "/contributions/1", "/expenses", "/supplies", "/supplies/3",
                "/export/payments.csv", "/export/expenses.csv", "/export/restante.csv", "/export/supplies.csv"):
        assert cas.get(url).status_code == 200, url
    # ce face casierul: plati, cheltuieli, bife (inclusiv Platit)
    r = post(cas, "/payments", {"student_id": "3", "contribution_id": "1", "amount": "10", "paid_on": "2026-09-22",
                                "next": "/contributions/1"}, page="/contributions/1")
    assert "Plată înregistrată" in r.get_data(as_text=True)
    r = post(cas, "/expenses", {"spent_on": "2026-09-22", "category": "Materiale", "amount": "5"}, page="/expenses")
    assert "Cheltuială înregistrată" in r.get_data(as_text=True)
    assert ajax(cas, "/supplies/3/track", {"student_id": "3", "chosen": "1", "paid": "1"}, page="/supplies/3").status_code == 200
    assert tracked(3, 3) == [(1, 1, 0)], "casierul poate bifa Platit"
    assert "Rechizit adăugat" in post(cas, "/supplies", {"name": "Radiera"}, page="/supplies").get_data(as_text=True)
    # ce NU face casierul: conturi si setari
    for url in ("/users", "/settings"):
        assert cas.get(url).status_code == 403, url
    for url, data in (("/users", {"role": "admin", "username": "hacker1", "password": "parola123"}),
                      ("/users/1/password", {"password": "parola-noua-1"}), ("/users/1/delete", {}),
                      ("/settings", {"class_name": "X", "opening_balance": "999"})):
        assert cas.post(url, data={**data, "csrf": token(cas, "/supplies")}).status_code == 403, url
    assert sql("SELECT COUNT(*) FROM users WHERE username = 'hacker1'") == [(0,)]
    assert vote(cas, 3, "chosen", "1").status_code == 403, "casierul nu are elev asociat, nu voteaza ca parinte"
    # administratorul poate orice: creeaza alt administrator, care are acces la Conturi si Setari
    r = post(admin, "/users", {"role": "admin", "username": "admin2", "password": "parola123"}, page="/users")
    assert "Cont creat" in r.get_data(as_text=True)
    adm2 = fond.app.test_client()
    post(adm2, "/login", {"username": "admin2", "password": "parola123"})
    assert adm2.get("/users").status_code == 200 and adm2.get("/settings").status_code == 200
    assert menu(adm2.get("/").get_data(as_text=True)) == ["Panou", "Elevi", "Contribuții", "Rechizite", "Cheltuieli", "Conturi", "Setări"]
    # parintele nu are acces la conturi/setari
    assert parent.get("/users").status_code == 403 and parent.get("/settings").status_code == 403
    # ultimul administrator nu se poate sterge (nici de el insusi)
    post(admin, "/users/%s/delete" % sql("SELECT id FROM users WHERE username = 'admin2'")[0][0], {}, page="/users")
    r = post(admin, "/users/1/delete", {}, page="/users")
    assert "ultimul cont de administrator" in r.get_data(as_text=True)

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
