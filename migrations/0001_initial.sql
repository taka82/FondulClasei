-- Schema initiala. Toate instructiunile sunt IF NOT EXISTS, deci sunt sigure si pe o baza
-- de date creata inainte sa existe migrarile.
-- NU modifica acest fisier dupa ce aplicatia ruleaza pe server: adauga o migrare noua (0002_...sql).

CREATE TABLE IF NOT EXISTS students (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    active  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY,
    username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('admin', 'parent')),
    student_id     INTEGER REFERENCES students(id) ON DELETE SET NULL
);

-- sumele sunt stocate in bani (1 leu = 100 bani) ca sa evitam erorile de rotunjire
CREATE TABLE IF NOT EXISTS contributions (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    amount    INTEGER NOT NULL CHECK (amount > 0),
    due_date  TEXT,
    note      TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id               INTEGER PRIMARY KEY,
    student_id       INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    contribution_id  INTEGER NOT NULL REFERENCES contributions(id) ON DELETE RESTRICT,
    amount           INTEGER NOT NULL CHECK (amount > 0),
    paid_on          TEXT NOT NULL,
    note             TEXT,
    created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id, contribution_id);

CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY,
    spent_on     TEXT NOT NULL,
    category     TEXT NOT NULL,
    amount       INTEGER NOT NULL CHECK (amount > 0),
    description  TEXT,
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- cat are fiecare elev de platit pentru fiecare contributie
CREATE VIEW IF NOT EXISTS balances AS
SELECT s.id AS student_id,
       c.id AS contribution_id,
       c.amount AS amount,
       COALESCE((SELECT SUM(p.amount) FROM payments p
                 WHERE p.student_id = s.id AND p.contribution_id = c.id), 0) AS paid
FROM students s CROSS JOIN contributions c;
