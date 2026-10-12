-- Loan account statements and the transactions read from them.
-- Amounts are always positive; `kind` says which way the money moved.
--   disbursement  loan paid out to you (balance goes up)
--   emi           instalment paid (split into principal and interest where known)
--   prepayment    part-payment / foreclosure, all principal
--   interest      interest charged or recovered on its own line
--   principal     principal repaid on its own line
--   charge        fees, penalties, GST, insurance
--   other         anything not recognised (kept for display, ignored in totals)
CREATE TABLE loan_statements (
    id               UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    loan_id          UUID            NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    statement_date   DATE            NOT NULL,
    period_start     DATE,
    period_end       DATE,
    opening_balance  NUMERIC(14, 2),
    closing_balance  NUMERIC(14, 2),
    source           TEXT            NOT NULL DEFAULT 'upload',
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (loan_id, statement_date)
);

CREATE INDEX loan_statements_loan ON loan_statements (loan_id, statement_date DESC);

ALTER TABLE loan_statements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_select_own" ON loan_statements FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON loan_statements FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON loan_statements FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON loan_statements FOR DELETE USING (auth.uid() = user_id);

CREATE TABLE loan_transactions (
    id               UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    loan_id          UUID            NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    statement_id     UUID            REFERENCES loan_statements(id) ON DELETE CASCADE,
    txn_date         DATE            NOT NULL,
    line_no          INT             NOT NULL DEFAULT 0,
    description      TEXT            NOT NULL,
    kind             TEXT            NOT NULL CHECK (kind IN ('disbursement', 'emi', 'prepayment', 'interest', 'principal', 'charge', 'other')),
    amount           NUMERIC(14, 2)  NOT NULL,
    principal_amount NUMERIC(14, 2),
    interest_amount  NUMERIC(14, 2),
    charges_amount   NUMERIC(14, 2),
    balance_after    NUMERIC(14, 2),
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX loan_transactions_loan ON loan_transactions (loan_id, txn_date DESC, line_no DESC);

ALTER TABLE loan_transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_select_own" ON loan_transactions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON loan_transactions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON loan_transactions FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON loan_transactions FOR DELETE USING (auth.uid() = user_id);
