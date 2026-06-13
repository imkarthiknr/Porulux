-- Document upload history: metadata + AI extraction results
-- Storage (S3/Supabase) holds the raw file; storage_path is the bucket key.
-- When a document is saved to a domain table, linked_record_id + linked_table
-- let us show "already saved" state without a JOIN fan-out.

CREATE TABLE documents (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    doc_type            TEXT            NOT NULL
                        CHECK (doc_type IN ('payslip', 'bank_statement', 'form16', 'cas_statement', 'unknown')),
    original_filename   TEXT,
    mime_type           TEXT,
    file_size_bytes     INT,
    storage_path        TEXT,           -- Supabase Storage key (null until file is persisted)
    status              TEXT            NOT NULL DEFAULT 'extracted'
                        CHECK (status IN ('uploading', 'processing', 'extracted', 'saved', 'failed')),
    extracted_data      JSONB,
    confidence          TEXT            CHECK (confidence IN ('high', 'low')),
    linked_table        TEXT,           -- 'salary_records' | 'bank_transactions' | 'loans' | ...
    linked_record_id    UUID,           -- PK in the linked table
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE INDEX documents_user_created ON documents (user_id, created_at DESC);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own" ON documents FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own" ON documents FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own" ON documents FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "users_delete_own" ON documents FOR DELETE USING (auth.uid() = user_id);
