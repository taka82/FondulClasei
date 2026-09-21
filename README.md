# Fondul clasei

Aplicație web pentru administrarea fondului clasei: elevi, contribuții (cotizații, excursii etc.), plăți, cheltuieli, sold și restanțe.

**Stack:** Python 3 · Flask · SQLite (fără alte servicii externe).

## Pornire

```
start.bat
```

sau manual:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Deschide http://127.0.0.1:5000. La prima pornire se cere crearea contului de casier.

Pentru acces din rețeaua locală (ex: părinții de pe telefon, în aceeași rețea): `set FOND_HOST=0.0.0.0` înainte de pornire. Pentru acces prin internet, pune aplicația în spatele unui reverse proxy cu HTTPS.

Variabile opționale: `FOND_HOST`, `FOND_PORT`, `FOND_DB` (calea fișierului SQLite).

## Roluri

| Rol | Poate |
|---|---|
| **Casier** | Tot: elevi, contribuții, plăți, cheltuieli, conturi, setări, exporturi |
| **Părinte** | Doar citire: soldul, cheltuielile clasei și situația plăților propriului copil |

Părinții nu văd plățile altor elevi.

## Cum se folosește

1. **Elevi** → adaugă lista clasei (un nume pe rând).
2. **Contribuții** → creează „Fond septembrie”, „Excursie” etc. cu suma per elev.
3. Deschide o contribuție și apasă **Plătit** în dreptul elevului (sau modifică suma pentru plăți parțiale).
4. **Cheltuieli** → înregistrează ce s-a cheltuit, cu categorie.
5. **Conturi** → creează conturi de părinte, legate de un elev.
6. **Setări** → numele clasei și soldul reportat din anul anterior.

Un elev transferat se **dezactivează**: nu mai apare la restanțe, dar plățile lui rămân în sold. Elevii și contribuțiile cu plăți înregistrate nu pot fi șterse.

## Date și backup

Toate datele sunt în `instance/fond.db` (nu intră în git). Copiază acest fișier periodic ca backup. Fișierul `instance/secret_key` semnează sesiunile; nu îl partaja.

La fiecare migrare aplicată pe o bază existentă, aplicația face automat o copie în `instance/backups/` (se păstrează ultimele 10, numele arată versiunea structurii: `fond-v2-20260921-101500.db`).

## Modificarea bazei de date (coloane/tabele noi)

Structura bazei e definită prin **migrări**: fișiere SQL numerotate în `migrations/`. La pornire, aplicația aplică singură migrările care lipsesc și reține versiunea în baza de date (`PRAGMA user_version`). Datele existente nu se ating.

Ca să adaugi o coloană, creezi un fișier nou, cu următorul număr:

```sql
-- migrations/0002_chitanta.sql
ALTER TABLE expenses ADD COLUMN receipt TEXT;
```

Reguli:
- Nume: `NNNN_descriere.sql` (patru cifre, fără duplicate). Se aplică în ordinea numerelor.
- **Nu modifica niciodată o migrare deja publicată** (nici `0001_initial.sql`): scrie una nouă.
- Fiecare migrare rulează într-o tranzacție: dacă o instrucțiune eșuează, se anulează toată migrarea și aplicația nu pornește (eroarea indică fișierul).
- `ADD COLUMN` și `CREATE TABLE/INDEX` sunt simple. Pentru redenumiri/ștergeri de coloane SQLite are `RENAME COLUMN` / `DROP COLUMN`; schimbările mai complexe (tip, constrângeri) cer recrearea tabelului.
- O coloană nouă `NOT NULL` trebuie să aibă `DEFAULT`, altfel migrarea eșuează pe rândurile existente.

## Publicarea actualizărilor (git + PythonAnywhere)

Pe calculatorul tău: modifici codul, rulezi testele, apoi:

```
git add -A
git commit -m "Descriere"
git push
```

Pe server (consola Bash din PythonAnywhere):

```
cd ~/fond && git pull
```

Apoi apeși **Reload** în tab-ul Web. Migrările noi se aplică automat la Reload, cu backup înainte.

## Teste

```
.venv\Scripts\python.exe test_app.py
.venv\Scripts\python.exe test_migrations.py
```

`test_app.py` rulează un flux complet (configurare, plăți, cheltuieli, sold, drepturile părinților, CSRF, export). `test_migrations.py` verifică migrările: bază nouă, bază veche cu date, coloană nouă, migrare defectă, backup.
