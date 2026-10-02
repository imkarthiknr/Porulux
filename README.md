# Porulux

*Track wealth. Not just expenses.* A personal finance tracker for salaried professionals in India: one place for net worth, salary, investments, bank statements, loans, EPF and NPS, with AI-assisted document import.

## Stack

| Layer | Choice |
|---|---|
| Web | Next.js 14 + Tailwind (`apps/web`) |
| API | FastAPI (`apps/api`) |
| DB / Auth | Supabase Postgres + RLS (`supabase/migrations`) |
| AI extraction | Claude API (model via `ANTHROPIC_MODEL`) |

## Running locally

```bash
# API
cd apps/api && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # fill in Supabase + Anthropic keys
uvicorn main:app --reload
pytest                 # unit tests (no network needed)

# Web
cd apps/web && npm install && cp .env.local.example .env.local && npm run dev
```

Apply `supabase/migrations/*.sql` in order to your Supabase project.

## Roadmap and status

**Month 1 — Foundation**
- [x] Auth (email + password) — Google login still to do
- [x] Net worth dashboard (snapshot, history, asset breakdown)
- [x] Manual entry for holdings, loans, EPF/NPS (`/dashboard/accounts`)
- [x] Salary records + payslip upload with AI extraction
- [x] Bank statement import: CSV (local parser) and PDF/image (Claude), auto-categorisation, duplicate skipping
- [x] Monthly cash flow and spend-by-category view (`/dashboard/transactions`)
- [ ] Budgets per category, spend trend charts, recurring payment detection

**Month 2 — Investments and loans**
- [ ] CAS import and portfolio (XIRR), broker note parsing
- [ ] Home loan tracker with 80C / 24B benefits, credit card statement import
- [ ] EPF / NPS statement import

**Month 3 — Automation and polish**
- [ ] Unified AI document hub, Form 16 import
- [ ] Net worth trend polish, mobile polish, notifications

**Out of scope for v1:** email auto-import, property valuation, ITR filing, family accounts, UPI sync.

## Known gaps
- Bank balance in net worth is the sum of imported transactions, so it ignores any opening balance.
- Only payslips can be saved from the upload page; Form 16, CAS and statement summaries are extract-only.
- Uploaded files are not yet persisted (`documents` table is unused).

## Deploying (Firebase + Cloud Run, free tier)

- **API** → Cloud Run (`asia-south1`, min instances 0): `gcloud run deploy porulux-api --source apps/api --region asia-south1 --allow-unauthenticated --min-instances 0 --max-instances 2 --memory 512Mi`. Keep `SUPABASE_SERVICE_ROLE_KEY` and `ANTHROPIC_API_KEY` in Secret Manager.
- **Web** → Firebase App Hosting, root directory `apps/web`, live branch `main`; config in `apps/web/apphosting.yaml`.
- The web app proxies `/api/*` to the Cloud Run service (`API_URL`), so the browser only ever talks to one origin and no CORS is needed. Firebase Hosting rewrites are not used because Hosting strips Supabase's `sb-*` auth cookies.
- In Supabase → Authentication → URL Configuration, add the App Hosting URL and `/callback` as redirect URLs.
