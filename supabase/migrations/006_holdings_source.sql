-- Which brokerage / depository a holding came from, so re-importing a statement updates the same
-- rows instead of duplicating them. NULL = added by hand.
ALTER TABLE holdings
    ADD COLUMN source           TEXT,
    ADD COLUMN last_imported_at TIMESTAMPTZ;

CREATE INDEX holdings_user_source ON holdings (user_id, source);
