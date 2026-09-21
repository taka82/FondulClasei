# 🎒 Foldul Clasei – Rechizite

Aplicație web pentru evidența rechizitelor clasei, cu tracking per-elev (ales / plătit / primit).

---

## Configurare Firebase (sincronizare în timp real)

Urmează acești pași **o singură dată**. Durată estimată: **5-7 minute**.

---

### Pasul 1 – Creează un proiect Firebase

1. Deschide [https://console.firebase.google.com](https://console.firebase.google.com)
2. Conectează-te cu un cont Google
3. Click **"Add project"** (sau **"Adaugă proiect"**)
4. Dă un nume proiectului, ex: `foldul-clasei`
5. Dezactivează Google Analytics (nu e necesar) → **Create project**

---

### Pasul 2 – Activează Realtime Database

1. În meniul din stânga, click **Build → Realtime Database**
2. Click **"Create Database"**
3. Alege regiunea **Europe-west1 (Belgium)** → Next
4. La **Security rules**, alege **"Start in test mode"** → Enable

   > ⚠️ Test mode permite oricine să citească/scrie timp de 30 de zile.
   > După configurare, poți seta reguli mai stricte (vezi Pasul 5).

---

### Pasul 3 – Obține configurarea aplicației

1. În consola Firebase, click pe **⚙️ Project settings** (roată din stânga sus)
2. Scroll jos la secțiunea **"Your apps"**
3. Click pe iconița **`</>`** (Web)
4. La "App nickname" pune `foldul-clasei-web` → **Register app**
5. Vei vedea un bloc de cod de forma:

```js
const firebaseConfig = {
  apiKey: "AIzaSy...",
  authDomain: "foldul-clasei.firebaseapp.com",
  databaseURL: "https://foldul-clasei-default-rtdb.europe-west1.firebasedatabase.app",
  projectId: "foldul-clasei",
  storageBucket: "foldul-clasei.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abc123"
};
```

6. **Copiază aceste valori** — le vei pune în `index.html`

---

### Pasul 4 – Pune valorile în index.html

Deschide `index.html` într-un editor de text (Notepad, VS Code, etc.) și caută blocul:

```js
const firebaseConfig = {
  apiKey:            "INLOCUIESTE_API_KEY",
  authDomain:        "INLOCUIESTE.firebaseapp.com",
  databaseURL:       "https://INLOCUIESTE-default-rtdb.europe-west1.firebasedatabase.app",
  projectId:         "INLOCUIESTE",
  storageBucket:     "INLOCUIESTE.appspot.com",
  messagingSenderId: "INLOCUIESTE",
  appId:             "INLOCUIESTE"
};
```

Înlocuiește fiecare valoare `"INLOCUIESTE..."` cu valorile reale din Pasul 3. Salvează fișierul.

---

### Pasul 5 – (Recomandat) Setează reguli de securitate

În consola Firebase → **Realtime Database → Rules**, înlocuiește regulile cu:

```json
{
  "rules": {
    ".read": true,
    ".write": true
  }
}
```

> Aceasta permite oricui cu link-ul să modifice datele — potrivit pentru un grup mic de părinți/profesori care au primit link-ul direct. Dacă vrei restricții suplimentare, contactează un dezvoltator.

Publică regulile cu **"Publish"**.

---

### Pasul 6 – Deploy pe Netlify (gratuit, 30 secunde)

1. Deschide [https://app.netlify.com/drop](https://app.netlify.com/drop)
2. **Trage fișierul `index.html`** pe pagina Netlify Drop
3. Vei primi instant un link de forma: `https://random-name-123.netlify.app`
4. Trimite link-ul părinților / profesorilor

> 💡 Opțional: în contul Netlify poți personaliza link-ul, ex: `clasa4b.netlify.app`

---

## Cum funcționează sincronizarea

- Orice modificare (rechizit adăugat, checkbox bifat etc.) apare **instant** la toți utilizatorii conectați
- Nu este nevoie de reload al paginii
- Un punct verde 🟢 în header confirmă că ești conectat la Firebase
- Dacă Firebase **nu e configurat**, aplicația funcționează normal dar datele sunt salvate **local** în browser (nu se sincronizează)

---

## Structura datelor în Firebase

```
/
├── className        → "Clasa a IV-a B"
├── pupils/
│   ├── {id}        → { id, name }
│   └── ...
├── items/
│   ├── {id}        → { id, name, cat, qty, bought, note }
│   └── ...
└── tracking/
    └── {itemId}/
        └── {pupilId} → { ales, platit, primit }
```

---

## Întrebări frecvente

**Pot folosi aplicația fără internet?**
Da, dar fără sincronizare. Modificările nu se vor trimite la Firebase și nu le vor vedea ceilalți utilizatori.

**Cât costă Firebase?**
Gratuit pentru volume mici. Planul Spark (gratuit) include 1 GB stocare și 10 GB transfer/lună — mai mult decât suficient pentru o clasă.

**Cum resetez toate datele?**
În consola Firebase → Realtime Database → click pe 🗑️ lângă nodul rădăcină `/`.
