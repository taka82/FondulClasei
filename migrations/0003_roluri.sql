-- Roluri: administrator (poate orice), casier (bani si rechizite, fara conturi si setari), parinte.
-- Conturile existente cu rolul 'admin' raman administratori.
-- SQLite nu poate modifica o constrangere CHECK pe loc, deci tabelul se reface (procedura recomandata de SQLite).
-- Migrarile ruleaza cu verificarea cheilor straine oprita, deci nimic nu se sterge in cascada.

CREATE TABLE users_new (
    id             INTEGER PRIMARY KEY,
    username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('admin', 'casier', 'parent')),
    student_id     INTEGER REFERENCES students(id) ON DELETE SET NULL
);

INSERT INTO users_new (id, username, password_hash, role, student_id)
    SELECT id, username, password_hash, role, student_id FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
