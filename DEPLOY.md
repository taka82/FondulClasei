# Punerea aplicației online (părinții intră de oriunde)

Ghid pentru **PythonAnywhere** (plan gratuit): rulează Flask și păstrează fișierul bazei de date, primești HTTPS și o adresă de forma `https://UTILIZATOR.eu.pythonanywhere.com`. Durează aproximativ 20 de minute și se face o singură dată.

Ai nevoie de: un cont PythonAnywhere (îl creezi tu) și codul publicat pe GitHub.

## 1. Publică codul (pe calculatorul tău)

În `C:\Moisil`:

```
git push
```

Verifică pe https://github.com/taka82/FondulClasei că apare ultimul commit.

## 2. Cont PythonAnywhere

Creează un cont **Beginner** (gratuit) pe **https://eu.pythonanywhere.com**, site-ul european: serverele sunt în Frankfurt (UE), deci datele copiilor rămân în Uniunea Europeană. Pe site-ul global (`pythonanywhere.com`) datele ar fi în SUA.

**Numele de utilizator nu se mai poate schimba** după creare și devine adresa site-ului (`https://UTILIZATOR.eu.pythonanywhere.com`), pe care o primesc toți părinții. Alege-l cu grijă: scurt, ușor de dictat, neutru (fără numele copiilor). De exemplu `fondclasa5`.

Dacă ai greșit, nu se poate redenumi: creezi un cont nou (poți refolosi același email) și repeți pașii; codul e pe GitHub, iar baza de date se copiază din `instance/fond.db`. Un domeniu propriu (ex. `fondclasa.ro`) cere un plan plătit (vezi pasul 8).

## 3. Cod și cont de casier (consola Bash)

Din tab-ul **Consoles** pornește o consolă **Bash** și rulează, pe rând (înlocuiește `python3.12` cu versiunea de Python pe care o alegi la pasul 4; folosește aceeași peste tot):

```
git clone https://github.com/taka82/FondulClasei.git ~/fond
cd ~/fond
python3.12 create_admin.py
```

Scriptul cere utilizatorul, numele clasei și parola (nu se vede la tastare) și creează contul de **administrator** (poate face orice). Pe server, pagina `/setup` din browser e dezactivată intenționat: altfel primul vizitator care ar găsi adresa ar putea crea el contul.

Dacă apare `ModuleNotFoundError: flask`, rulează `python3.12 -m pip install --user -r requirements.txt` și repetă comanda.

## 4. Aplicația web (tab-ul Web)

1. **Add a new web app** → **Next** → **Manual configuration** → alege Python 3.12 (sau cea mai nouă) → **Next**.
2. La secțiunea **Code**, deschide fișierul **WSGI configuration file**, șterge tot ce conține și pune (cu utilizatorul tău în loc de `UTILIZATOR`):
   ```python
   import sys
   sys.path.insert(0, '/home/UTILIZATOR/fond')
   from wsgi import application
   ```
   Salvează (**Save**).
3. La **Static files** adaugă: URL `/static/` → Directory `/home/UTILIZATOR/fond/static`.
4. La **Security** pornește **Force HTTPS**.
5. Apasă butonul verde **Reload**, apoi deschide `https://UTILIZATOR.eu.pythonanywhere.com`. Ar trebui să vezi pagina de autentificare. Intră cu contul de administrator.

Dacă vezi o eroare, deschide **Error log** (link în tab-ul Web); ultimele linii spun ce lipsește.

## 5. Configurează clasa (din browser, ca administrator)

1. **Elevi** → lipește lista clasei (un nume pe rând). Numele copiilor se introduc doar aici: nu intră în git.
2. **Conturi** → creează, dacă vrei, un cont de **casier** (bani și rechizite, fără conturi și setări) și câte un cont de părinte, legat de elev. Trimite fiecărui părinte adresa, utilizatorul și parola inițială, pe un canal privat (nu în grupul clasei), cu rugămintea să o schimbe la prima intrare.
3. **Contribuții** și **Rechizite** → adaugă ce ai de colectat.

## 6. Copii de siguranță zilnice

Datele sunt în `/home/UTILIZATOR/fond/instance/fond.db`. Pornește o copie automată zilnică: tab-ul **Tasks** → **Scheduled tasks** → alege o oră (ex. 03:00) și comanda:

```
python3.12 /home/UTILIZATOR/fond/backup_db.py
```

Copiile ajung în `instance/backups/` (ultimele 14 zile). Din când în când descarcă din tab-ul **Files** cel mai recent fișier de acolo și păstrează-l pe calculatorul tău: o copie pe același server nu te apără dacă serverul se pierde.

## 7. Actualizări

Pe calculator: modifici codul, rulezi testele, apoi `git push`. Pe server, în consola Bash:

```
cd ~/fond && git pull
```

Apoi **Reload** în tab-ul Web. Migrările bazei de date se aplică singure, cu o copie de siguranță înainte. Datele (`instance/`) nu se ating.

## 8. Reînnoirea (plan gratuit)

La fiecare **3 luni**, în tab-ul Web apasă butonul **Run until 3 months from today**; primești email de reamintire cu o săptămână înainte. Dacă uiți, site-ul se oprește (datele rămân) și se repornește la fel. Un plan plătit (**Developer, 10 €/lună** pe site-ul european; pe cel global 10 $) elimină restricția și permite un domeniu propriu, pe care îl cumperi separat de la un registrar. Prețurile pot fi schimbate: verifică pe pagina Pricing.

## Dacă un părinte uită parola

Administratorul o schimbă din **Conturi** (coloana „Parolă nouă”). Casierii și părinții nu pot schimba parolele altora. Dacă **tu, administratorul,** ai uitat-o, în consola Bash:

```
cd ~/fond && python3.12 create_admin.py --reset NUMELE_TAU
```

## Securitate și date personale

- Site-ul cere autentificare peste tot, folosește HTTPS, parole stocate hashuite, protecție CSRF, limită de încercări de autentificare și nu e indexat de motoarele de căutare. Adresa nu e însă secretă: oricine o află vede pagina de autentificare.
- Părinții văd doar situația propriului copil (contribuții, plăți, bife la rechizite), plus lista de rechizite și cheltuielile clasei. Panoul cu soldul, totalul încasat și restanțele clasei e doar pentru administrator și casier.
- Pe server ajung nume de copii și sume plătite. Pe site-ul european (`eu.pythonanywhere.com`) datele stau în Frankfurt, în UE. Informează părinții și obține acordul lor; dacă vrei mai puțină expunere, folosește nume + inițială.
- Repo-ul de pe GitHub e public și conține doar codul: nici baza de date, nici parole, nici cheia secretă (`instance/` e exclus din git). Îl poți face privat din GitHub → Settings → Change visibility; atunci serverul are nevoie de o *deploy key* pentru `git pull`.
- Nu partaja fișierul `instance/secret_key` și nu-l pune în git.
