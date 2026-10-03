-- ── Profiles ─────────────────────────────────────────────────────────────────
CREATE TABLE profiles (
    user_id         UUID            PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name       TEXT,
    phone           TEXT,
    address_line1   TEXT,
    address_line2   TEXT,
    city            TEXT,
    state           TEXT,
    postal_code     TEXT,
    country         TEXT            NOT NULL DEFAULT 'India',
    avatar_path     TEXT,           -- key inside the private 'avatars' bucket
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_select_own" ON profiles FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON profiles FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON profiles FOR UPDATE USING (auth.uid() = user_id);

-- Private bucket; the API (service role) uploads and hands out short-lived signed URLs.
-- No storage policies are created, so browsers cannot read or write it directly.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('avatars', 'avatars', false, 2097152, ARRAY['image/jpeg', 'image/png', 'image/webp'])
ON CONFLICT (id) DO NOTHING;

-- ── Savings / current bank accounts ──────────────────────────────────────────
CREATE TABLE bank_accounts (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    bank_name       TEXT            NOT NULL,
    account_type    TEXT            NOT NULL DEFAULT 'SAVINGS' CHECK (account_type IN ('SAVINGS', 'CURRENT', 'SALARY')),
    last4           TEXT            NOT NULL CHECK (last4 ~ '^[0-9]{4}$'),
    nickname        TEXT,
    ifsc            TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, bank_name, last4)
);

CREATE TRIGGER bank_accounts_updated_at
    BEFORE UPDATE ON bank_accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE bank_accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_select_own" ON bank_accounts FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON bank_accounts FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON bank_accounts FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON bank_accounts FOR DELETE USING (auth.uid() = user_id);

-- Link transactions to the account they belong to (NULL = not assigned yet).
-- Deleting an account keeps its transactions, just unassigned.
ALTER TABLE bank_transactions
    ADD COLUMN account_id UUID REFERENCES bank_accounts(id) ON DELETE SET NULL;
CREATE INDEX bank_transactions_account ON bank_transactions (account_id, transaction_date DESC);

-- ── Credit cards, statements, card transactions ──────────────────────────────
CREATE TABLE credit_cards (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    bank_name       TEXT            NOT NULL,
    card_name       TEXT,           -- e.g. "Regalia", "Millennia"
    network         TEXT            CHECK (network IN ('VISA', 'MASTERCARD', 'AMEX', 'RUPAY', 'DINERS', 'OTHER')),
    last4           TEXT            NOT NULL CHECK (last4 ~ '^[0-9]{4}$'),
    credit_limit    NUMERIC(14, 2)  CHECK (credit_limit >= 0),
    statement_day   SMALLINT        CHECK (statement_day BETWEEN 1 AND 31),
    due_day         SMALLINT        CHECK (due_day BETWEEN 1 AND 31),
    annual_fee      NUMERIC(12, 2)  CHECK (annual_fee >= 0),
    interest_rate   NUMERIC(5, 2)   CHECK (interest_rate >= 0),   -- % per annum
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, bank_name, last4)
);

CREATE TRIGGER credit_cards_updated_at
    BEFORE UPDATE ON credit_cards
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE credit_cards ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_select_own" ON credit_cards FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON credit_cards FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON credit_cards FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON credit_cards FOR DELETE USING (auth.uid() = user_id);

CREATE TABLE card_statements (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    card_id         UUID            NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    statement_date  DATE            NOT NULL,
    period_start    DATE,
    period_end      DATE,
    due_date        DATE,
    total_due       NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    minimum_due     NUMERIC(14, 2),
    credit_limit    NUMERIC(14, 2),
    paid            BOOLEAN         NOT NULL DEFAULT FALSE,
    source          TEXT            NOT NULL DEFAULT 'upload',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (card_id, statement_date)
);

CREATE INDEX card_statements_card ON card_statements (card_id, statement_date DESC);

ALTER TABLE card_statements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_select_own" ON card_statements FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON card_statements FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON card_statements FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON card_statements FOR DELETE USING (auth.uid() = user_id);

-- amount: positive = purchase/fee/interest (money you owe), negative = payment or refund
CREATE TABLE card_transactions (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    card_id         UUID            NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    statement_id    UUID            REFERENCES card_statements(id) ON DELETE CASCADE,
    txn_date        DATE            NOT NULL,
    description     TEXT            NOT NULL,
    amount          NUMERIC(14, 2)  NOT NULL,
    category        TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX card_transactions_card ON card_transactions (card_id, txn_date DESC);

ALTER TABLE card_transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_select_own" ON card_transactions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON card_transactions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON card_transactions FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON card_transactions FOR DELETE USING (auth.uid() = user_id);

-- Net worth log gains a column for card dues (liabilities).
ALTER TABLE networth_log ADD COLUMN credit_cards NUMERIC(14, 2) NOT NULL DEFAULT 0;
