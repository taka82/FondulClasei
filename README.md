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

Deschide http://127.0.0.1:5000. La prima pornire (local) se cere crearea contului de administrator.

**Pentru acces de oriunde** (părinții de pe telefon, de acasă) aplicația se pune online: vezi **[DEPLOY.md](DEPLOY.md)**, ghid pas cu pas pentru PythonAnywhere. Pe server, contul de casier se creează din consolă cu `create_admin.py`, iar pagina `/setup` din browser e dezactivată.

Pentru acces din rețeaua locală (ex: părinții de pe telefon, în aceeași rețea): `set FOND_HOST=0.0.0.0` înainte de pornire. Pentru acces prin internet, pune aplicația în spatele unui reverse proxy cu HTTPS.

Variabile opționale: `FOND_HOST`, `FOND_PORT`, `FOND_DB` (calea fișierului SQLite).

## Roluri

| Rol | Poate |
|---|---|
| **Administrator** | Tot, inclusiv **Conturi** (creează/șterge conturi, resetează parole) și **Setări** |
| **Casier** | Tot ce ține de bani și rechizite: elevi, contribuții, plăți, cheltuieli, rechizite (inclusiv „Plătit”), exporturi. **Nu** vede Conturi și Setări |
| **Părinte** | Vede **doar situația propriului copil** (contribuții, plăți, rechizite), plus lista de rechizite și cheltuielile clasei. **Nu vede Panoul** (soldul, totalul încasat, restanțele clasei). La Rechizite poate bifa „Ales” și „Primit” pentru copilul lui (nu și „Plătit”) |

Părinții nu văd plățile altor elevi.

## Cum se folosește

1. **Elevi** → adaugă lista clasei (un nume pe rând).
2. **Contribuții** → creează „Fond septembrie”, „Excursie” etc. cu suma per elev.
3. Deschide o contribuție și apasă **Plătit** în dreptul elevului (sau modifică suma pentru plăți parțiale).
4. **Cheltuieli** → înregistrează ce s-a cheltuit, cu categorie.
5. **Conturi** (doar administratorul) → creează conturi de părinte (legate de un elev), de casier sau de administrator.
6. **Setări** → numele clasei și soldul reportat din anul anterior.

### Rechizite

Pagina **Rechizite** ține lista de rechizite ale clasei (denumire, categorie, preț, observații) și, pentru fiecare, bifele per elev:

- **Ales**: elevul votează rechizitul (se oferă să îl cumpere)
- **Plătit**: a achitat suma
- **Primit**: rechizitul a ajuns la elev

**Cât trebuie comandat** rezultă din voturi: fiecare elev activ care a bifat „Ales” înseamnă o bucată. Coloana *De comandat* din listă arată numărul de voturi (din totalul de elevi). În pagina *detalii* a rechizitului (link „Bifează”) bifezi fiecare elev, iar bifele se salvează imediat. Există căutare, filtre pe categorie și pe voturi (cu / fără), sortare pe coloane și export CSV (cu numele elevilor și „De comandat”).

**Prețul** (în lei, per bucată) e opțional și se completează de casier la „Adaugă rechizit” sau „Modifică”. Îl văd toți: în listă, în pagina rechizitului și, la părinte, în „Situația mea”. Casierul vede în pagina rechizitului și **totalul de comandat** (preț × voturi), care se actualizează la fiecare bifă; exportul CSV are coloanele „Preț” și „Total de comandat”. Prețul este **informativ**: nu intră în soldul fondului și nu creează plăți.

**Restanțe la rechizite:** pagina **Elevi** arată pentru fiecare elev *Plătit* (contribuții), *Restanță* împărțită în *Contribuții*, *Rechizite* și *Total*, plus un rând de totaluri. Restanța la rechizite = rechizitele **alese** (bifa „Ales”) și încă **neplătite** (bifa „Plătit” lipsește), la prețul lor; cele fără preț nu se pot socoti și apar marcate „+N fără preț”. Același total apare pe pagina elevului („Situația mea” la părinte), în cardul **Restanțe** de pe Panou (cu mențiunea „din care rechizite”) și în exportul `restante.csv`, care listează acum și rechizitele.

**Cine poate bifa ce:**

| | Ales | Plătit | Primit |
|---|---|---|---|
| **Administrator / Casier** | da, pentru orice elev | da | da |
| **Părinte** | da, **doar pentru copilul lui** | nu | da, **doar pentru copilul lui** |

Părintele bifează „Ales” (vrea rechizitul) și „Primit” (l-a primit) direct din lista de rechizite sau din pagina rechizitului, iar bifele se salvează imediat. „Plătit” îl bifează doar casierul. Cât timp rechizitul e plătit sau primit, părintele nu poate retrage votul „Ales” (dacă „Primit” l-a bifat el, îl debifează întâi; dacă e plătit, discută cu casierul). Elevul se stabilește din contul părintelui, nu din cerere, așa că nu se poate vota pentru alt copil. La nivel de elev, părinții văd **doar bifele copilului lor**, plus totalurile (câți au votat, plătit, primit).

Tabelul `supplies` mai are coloanele vechi `qty` și `bought` (cantitate, cumpărat); nu se mai folosesc și nu se afișează.

Un elev transferat se **dezactivează**: nu mai apare la restanțe, dar plățile lui rămân în sold. Elevii și contribuțiile cu plăți înregistrate nu pot fi șterse.

## Aspect

Interfața are stilul site-ului colegiului (moisilbrasov.ro): antet bleumarin cu numele colegiului, bară de meniu neagră cu linkuri majuscule, accent albastru, fonturi Open Sans / Roboto și temă închisă automată dacă dispozitivul o folosește. Culorile sunt variabile CSS la începutul lui `static/style.css`.

Fonturile se încarcă doar dacă sunt instalate pe dispozitiv (altfel se folosește fontul sistemului); nu se descarcă nimic de pe servere externe (Google Fonts), ca să nu se trimită adresele IP ale părinților către terți.

**Sigla:** dacă ai acordul colegiului să o folosești, pune fișierul `static/logo.png` (recomandat: sigla albă pe fundal transparent, se potrivește pe antetul bleumarin, înălțime ~150 px). Apare automat în antet.

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

## Copii de siguranță

```
python backup_db.py
```

Creează o copie verificată în `instance/backups/` (se păstrează ultimele 14). Pe server se rulează zilnic ca sarcină programată (vezi DEPLOY.md).

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
.venv\Scripts\python.exe test_deploy.py
```

`test_app.py` rulează un flux complet (configurare, plăți, cheltuieli, sold, drepturile părinților, CSRF, export). `test_migrations.py` verifică migrările: bază nouă, bază veche cu date, coloană nouă, migrare defectă, backup. `test_deploy.py` simulează producția (`wsgi.py`): fără `/setup` public, cont creat din consolă, cookie sigur/HTTPS, limită de încercări pe IP-ul real, copii de siguranță.
