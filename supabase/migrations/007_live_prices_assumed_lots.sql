-- When and where each holding's current_price last came from (live refresh from Yahoo / AMFI).
ALTER TABLE holdings
    ADD COLUMN price_updated_at TIMESTAMPTZ,
    ADD COLUMN price_source     TEXT;

-- A lot created from "held since (approx.)" at import time rather than from a real transaction date.
-- Real lots always win: adding one removes the assumed lot for that holding.
ALTER TABLE holding_lots
    ADD COLUMN assumed BOOLEAN NOT NULL DEFAULT FALSE;
