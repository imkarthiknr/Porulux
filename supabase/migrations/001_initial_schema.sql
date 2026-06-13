CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE salary_records (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    month           SMALLINT        NOT NULL CHECK (month BETWEEN 1 AND 12),
    year            SMALLINT        NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    employer_name   TEXT,
    basic           NUMERIC(14, 2),
    hra             NUMERIC(14, 2),
    special_allowance NUMERIC(14, 2),
    pf_employee     NUMERIC(14, 2),
    pf_employer     NUMERIC(14, 2),
    income_tax      NUMERIC(14, 2),
    professional_tax NUMERIC(14, 2),
    gross_pay       NUMERIC(14, 2),
    net_pay         NUMERIC(14, 2),
    payslip_url     TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, month, year)
);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER salary_records_updated_at
    BEFORE UPDATE ON salary_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE salary_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON salary_records
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "users_insert_own" ON salary_records
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_update_own" ON salary_records
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "users_delete_own" ON salary_records
    FOR DELETE USING (auth.uid() = user_id);
