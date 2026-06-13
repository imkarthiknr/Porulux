-- Investment holdings (stocks, MF, ETF, bonds, SGB)
CREATE TABLE holdings (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol          TEXT            NOT NULL,
    name            TEXT            NOT NULL,
    holding_type    TEXT            NOT NULL CHECK (holding_type IN ('STOCK', 'MF', 'ETF', 'BOND', 'SGB', 'OTHER')),
    units           NUMERIC(18, 6)  NOT NULL DEFAULT 0,
    current_price   NUMERIC(14, 2),
    avg_buy_price   NUMERIC(14, 2),
    isin            TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TRIGGER holdings_updated_at
    BEFORE UPDATE ON holdings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE holdings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON holdings FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON holdings FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON holdings FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON holdings FOR DELETE USING (auth.uid() = user_id);

-- EPF and NPS account balances
CREATE TABLE epf_nps_balances (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    account_type    TEXT            NOT NULL CHECK (account_type IN ('EPF', 'NPS_TIER1', 'NPS_TIER2')),
    balance         NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    as_of_date      DATE            NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TRIGGER epf_nps_balances_updated_at
    BEFORE UPDATE ON epf_nps_balances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE epf_nps_balances ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON epf_nps_balances FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON epf_nps_balances FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON epf_nps_balances FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON epf_nps_balances FOR DELETE USING (auth.uid() = user_id);

-- Bank transactions; positive amount = credit, negative = debit
-- Running SUM(amount) per user is the bank balance estimate
CREATE TABLE bank_transactions (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    transaction_date    DATE            NOT NULL,
    description         TEXT            NOT NULL,
    amount              NUMERIC(14, 2)  NOT NULL,
    category            TEXT,
    bank_name           TEXT,
    account_last4       TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

ALTER TABLE bank_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON bank_transactions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON bank_transactions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON bank_transactions FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON bank_transactions FOR DELETE USING (auth.uid() = user_id);

-- Loans and liabilities
CREATE TABLE loans (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    loan_type           TEXT            NOT NULL CHECK (loan_type IN ('HOME_LOAN', 'PERSONAL_LOAN', 'VEHICLE_LOAN', 'CREDIT_CARD', 'OTHER')),
    lender_name         TEXT,
    outstanding_amount  NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    emi_amount          NUMERIC(14, 2),
    interest_rate       NUMERIC(6, 4),
    tenure_months       INT,
    start_date          DATE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TRIGGER loans_updated_at
    BEFORE UPDATE ON loans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE loans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON loans FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON loans FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON loans FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON loans FOR DELETE USING (auth.uid() = user_id);

-- Monthly net worth snapshots
CREATE TABLE networth_log (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    snapshot_date       DATE            NOT NULL DEFAULT CURRENT_DATE,
    total_assets        NUMERIC(14, 2)  NOT NULL,
    total_liabilities   NUMERIC(14, 2)  NOT NULL,
    net_worth           NUMERIC(14, 2)  NOT NULL,
    investments         NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    epf_nps             NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    bank_balance        NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    loans               NUMERIC(14, 2)  NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, snapshot_date)
);

ALTER TABLE networth_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON networth_log FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON networth_log FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON networth_log FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON networth_log FOR DELETE USING (auth.uid() = user_id);
