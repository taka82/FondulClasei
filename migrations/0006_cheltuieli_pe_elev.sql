-- Fiecare cheltuiala se imparte egal intre elevii activi; partea fiecaruia se retine explicit,
-- ca sa apara in istoricul lui si ca totalul partilor sa fie exact (restul de bani se distribuie).
-- Informativ: nu modifica soldul fondului si nu adauga restante.

CREATE TABLE expense_shares (
    expense_id  INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    amount      INTEGER NOT NULL CHECK (amount >= 0),   -- in bani
    PRIMARY KEY (expense_id, student_id)
);
CREATE INDEX idx_expense_shares_student ON expense_shares(student_id);

-- Cheltuielile deja existente se impart intre elevii activi de acum:
-- suma // n pentru fiecare, iar primii (suma % n) elevi (dupa id) primesc cate un ban in plus.
INSERT INTO expense_shares (expense_id, student_id, amount)
SELECT e.id, s.id,
       e.amount / n.cnt + CASE WHEN ROW_NUMBER() OVER (PARTITION BY e.id ORDER BY s.id) <= e.amount % n.cnt THEN 1 ELSE 0 END
FROM expenses e
CROSS JOIN students s
CROSS JOIN (SELECT COUNT(*) AS cnt FROM students WHERE active = 1) n
WHERE s.active = 1;
