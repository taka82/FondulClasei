-- Modulul Rechizite: lista de rechizite si urmarirea per elev (ales / platit / primit).

CREATE TABLE supplies (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL DEFAULT 'General',
    qty       INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 1),
    bought    INTEGER NOT NULL DEFAULT 0 CHECK (bought >= 0),
    note      TEXT
);

CREATE TABLE supply_tracking (
    supply_id   INTEGER NOT NULL REFERENCES supplies(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    chosen      INTEGER NOT NULL DEFAULT 0,  -- elevul s-a oferit sa cumpere
    paid        INTEGER NOT NULL DEFAULT 0,  -- a achitat suma
    received    INTEGER NOT NULL DEFAULT 0,  -- rechizitul a ajuns la elev
    PRIMARY KEY (supply_id, student_id)
);
CREATE INDEX idx_supply_tracking_student ON supply_tracking(student_id);
