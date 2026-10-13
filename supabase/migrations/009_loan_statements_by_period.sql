-- A loan statement is identified by the period it covers, not by its printed date. PDFs downloaded together
-- share the day they were generated, so one-statement-per-date wrongly rejected the second year's PDF.
ALTER TABLE loan_statements DROP CONSTRAINT IF EXISTS loan_statements_loan_id_statement_date_key;

-- Rows imported before this change may carry the print date; the end of the period is what it should mean.
UPDATE loan_statements SET statement_date = period_end WHERE period_end IS NOT NULL;
