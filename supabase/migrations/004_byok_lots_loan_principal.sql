-- Bring-your-own AI key: one row per user, key encrypted by the API (Fernet) before it is stored.
-- RLS is enabled with NO policies: browsers using the anon key can never read this table;
-- only the backend's service-role key can.
CREATE TABLE user_ai_keys (
    user_id         UUID            PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    provider        TEXT            NOT NULL CHECK (provider IN ('gemini', 'anthropic')),
    encrypted_key   TEXT            NOT NULL,
    key_last4       TEXT            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TRIGGER user_ai_keys_updated_at
    BEFORE UPDATE ON user_ai_keys
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE user_ai_keys ENABLE ROW LEVEL SECURITY;

-- Buy/sell lots per holding; these are the dated cash flows XIRR needs.
CREATE TABLE holding_lots (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    holding_id      UUID            NOT NULL REFERENCES holdings(id) ON DELETE CASCADE,
    lot_date        DATE            NOT NULL,
    lot_type        TEXT            NOT NULL DEFAULT 'BUY' CHECK (lot_type IN ('BUY', 'SELL')),
    units           NUMERIC(18, 6)  NOT NULL CHECK (units > 0),
    price           NUMERIC(14, 4)  NOT NULL CHECK (price >= 0),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX holding_lots_holding ON holding_lots (holding_id, lot_date);

ALTER TABLE holding_lots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON holding_lots FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON holding_lots FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON holding_lots FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON holding_lots FOR DELETE USING (auth.uid() = user_id);

-- Original loan amount, so the EMI schedule (and tax benefit per financial year) can be reproduced.
ALTER TABLE loans ADD COLUMN principal_amount NUMERIC(14, 2);
