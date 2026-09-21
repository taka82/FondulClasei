-- Pretul unui rechizit, in bani, per bucata (NULL = nespecificat).
-- Este informativ: nu intra in soldul fondului si nu creeaza plati.

ALTER TABLE supplies ADD COLUMN price INTEGER CHECK (price IS NULL OR price >= 0);
