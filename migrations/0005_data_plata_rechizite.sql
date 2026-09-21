-- Cand casierul bifeaza "Platit" la un rechizit se retin data si suma (pretul de atunci),
-- ca plata sa apara in istoricul de plati al elevului. Platile bifate inainte raman fara data (NULL).

ALTER TABLE supply_tracking ADD COLUMN paid_on TEXT;
ALTER TABLE supply_tracking ADD COLUMN paid_amount INTEGER;
