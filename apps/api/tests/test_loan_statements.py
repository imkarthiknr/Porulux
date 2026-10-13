import io
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import main
from core import crud
from core.auth import AuthUser, get_auth_user
from routers import loan_statements
from services import ai, credentials
from services.loan_statements import LoanTxn, classify, fill_components, normalize_ai_result, summarize_account
from tests.fakedb import FakeDB

ME = "00000000-0000-0000-0000-00000000000a"
OTHER = "00000000-0000-0000-0000-00000000000c"
LOAN_ID = "11111111-1111-1111-1111-111111111111"
OTHER_LOAN = "22222222-2222-2222-2222-222222222222"
USER = AuthUser(ME, datetime(2026, 9, 1, tzinfo=timezone.utc), "me@example.com")
LOAN = {"id": LOAN_ID, "user_id": ME, "loan_type": "HOME_LOAN", "lender_name": "HDFC", "outstanding_amount": 900000.0}


def pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(200, 200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def boot(monkeypatch, **tables):
    db = FakeDB(**tables)
    for mod in (crud, loan_statements, credentials):
        monkeypatch.setattr(mod, "get_supabase_client", lambda: db)
    monkeypatch.setenv("SHARED_KEY_CUTOFF", "2026-10-03T00:00:00Z")
    monkeypatch.setenv("GEMINI_API_KEY", "shared")
    main.app.dependency_overrides[get_auth_user] = lambda: USER
    return TestClient(main.app), db


@pytest.fixture(autouse=True)
def _clean():
    yield
    main.app.dependency_overrides.clear()


# 12% p.a. loan of 10,00,000, EMI 20,000 (so the first month is 10,000 interest).
AI_RESULT = (
    '{"statement_date":"2026-09-30","period_start":"2026-07-01","period_end":"2026-09-30",'
    '"opening_balance":1000000,"closing_balance":919199,"transactions":['
    '{"date":"2026-07-05","description":"EMI 1","kind":"emi","amount":20000,"balance":990000},'
    '{"date":"2026-08-05","description":"EMI 2","kind":"emi","amount":20000,"balance":979900},'
    '{"date":"2026-08-20","description":"Part payment","kind":"prepayment","amount":50000,"balance":929900},'
    '{"date":"2026-09-05","description":"EMI 3","kind":"emi","amount":20000,"balance":919199},'
    '{"date":"2026-09-06","description":"Processing fee incl GST","kind":"charge","amount":590}]}'
)


def fake_ai(monkeypatch, text=AI_RESULT):
    async def fake_generate(*a, **k):
        return text
    monkeypatch.setattr(ai, "generate", fake_generate)


def upload(c, name="s.pdf", data=None, ctype="application/pdf"):
    return c.post(f"/api/v1/loans/{LOAN_ID}/statements/import", files={"file": (name, data if data is not None else pdf(), ctype)})


def test_classify_narrations():
    assert classify("LOAN DISBURSEMENT") == "disbursement"
    assert classify("PART PAYMENT RECEIVED") == "prepayment"
    assert classify("EMI BOUNCE CHARGES") == "charge"       # charge wins over emi
    assert classify("GST on interest") == "charge"
    assert classify("EMI 12/240 RECOVERED") == "emi"
    assert classify("Interest debited") == "interest"
    assert classify("Principal component") == "principal"
    assert classify("NEFT 123") == "other"


def test_split_derived_from_balance_drop():
    rows = [LoanTxn(None, "EMI", "emi", 20000, balance=990000), LoanTxn(None, "EMI", "emi", 20000, balance=979900)]
    fill_components(rows, 1_000_000)
    assert (rows[0].principal, rows[0].interest) == (10000, 10000)
    assert (rows[1].principal, rows[1].interest) == (10100, 9900)


def test_first_emi_stays_unsplit_without_opening_balance():
    rows = [LoanTxn(None, "EMI", "emi", 20000, balance=990000), LoanTxn(None, "EMI", "emi", 20000, balance=979900)]
    fill_components(rows, None)
    assert rows[0].principal is None and rows[0].interest is None
    assert (rows[1].principal, rows[1].interest) == (10100, 9900)   # previous balance now known


def test_given_components_win_and_single_component_completes():
    both = LoanTxn(None, "EMI", "emi", 20000, principal=12000, interest=8000, balance=1)
    only_interest = LoanTxn(None, "EMI", "emi", 20000, interest=9000, charges=500)
    fill_components([both, only_interest], 100)
    assert (both.principal, both.interest) == (12000, 8000)
    assert only_interest.principal == 10500   # 20000 - 9000 - 500 fee


def test_bad_balance_drop_is_not_trusted():
    t = LoanTxn(None, "EMI", "emi", 20000, balance=900000)   # drop of 1,00,000 can't come from a 20,000 EMI
    fill_components([t], 1_000_000)
    assert t.principal is None and t.interest is None


def test_normalize_rejects_empty_and_fixes_bad_kind():
    with pytest.raises(ValueError):
        normalize_ai_result({"transactions": []})
    parsed = normalize_ai_result({"transactions": [{"date": "2026-01-05", "description": "Late payment penalty", "kind": "weird", "amount": -500}]})
    assert parsed.transactions[0].kind == "charge" and parsed.transactions[0].amount == 500 and parsed.statement_date.isoformat() == "2026-01-05"


def test_ai_import_totals_and_account_view(monkeypatch):
    c, db = boot(monkeypatch, loans=[LOAN])
    fake_ai(monkeypatch)
    res = upload(c)
    assert res.status_code == 201, res.text
    assert res.json()["transactions_inserted"] == 5

    acct = c.get(f"/api/v1/loans/{LOAN_ID}/account").json()
    s = acct["summary"]
    assert s["interest_paid"] == 29199 and s["principal_paid"] == 80801 and s["charges_paid"] == 590
    assert s["total_paid"] == 110590 and s["prepaid"] == 50000 and s["emis_paid"] == 3 and s["unsplit_emis"] == 0
    assert s["balance"] == 919199 and s["balance_as_of"] == "2026-09-05"
    assert acct["transactions"][0]["description"] == "Processing fee incl GST"   # newest first
    assert len(acct["statements"]) == 1 and acct["statements"][0]["closing_balance"] == 919199
    assert db.tables["loans"][0]["outstanding_amount"] == 900000.0   # never changed behind the user's back


def test_same_statement_twice_is_409_and_overlap_skips_duplicates(monkeypatch):
    c, db = boot(monkeypatch, loans=[LOAN])
    fake_ai(monkeypatch)
    assert upload(c).status_code == 201
    assert upload(c).status_code == 409

    # A later, overlapping statement repeats the Sep EMI and adds October's.
    fake_ai(monkeypatch, '{"statement_date":"2026-10-31","opening_balance":929900,"transactions":['
                         '{"date":"2026-09-05","description":"EMI 3","kind":"emi","amount":20000,"balance":919199},'
                         '{"date":"2026-10-05","description":"EMI 4","kind":"emi","amount":20000,"balance":908391}]}')
    res = upload(c)
    assert res.json()["transactions_inserted"] == 1 and res.json()["duplicates_skipped"] == 1
    assert len(db.tables["loan_transactions"]) == 6
    assert c.get(f"/api/v1/loans/{LOAN_ID}/account").json()["summary"]["balance"] == 908391


def test_csv_import_splits_from_running_balance(monkeypatch):
    c, db = boot(monkeypatch, loans=[LOAN])
    csv = (b"Date,Narration,Debit,Credit,Balance\n"
           b"05/07/26,EMI RECOVERED,20000.00,,990000.00\n"
           b"05/08/26,EMI RECOVERED,20000.00,,979900.00\n"
           b"06/08/26,Bounce charges,590.00,,979900.00\n")
    res = upload(c, "l.csv", csv, "text/csv")
    assert res.status_code == 201, res.text
    s = c.get(f"/api/v1/loans/{LOAN_ID}/account").json()["summary"]
    assert s["unsplit_emis"] == 1                         # no opening balance, so EMI 1 can't be split
    assert s["interest_paid"] == 9900 and s["principal_paid"] == 10100 and s["charges_paid"] == 590
    assert s["balance"] == 979900


def test_isolation_and_delete(monkeypatch):
    sid = "66666666-6666-6666-6666-666666666666"
    mine = "77777777-7777-7777-7777-777777777777"
    c, db = boot(monkeypatch, loans=[LOAN, {**LOAN, "id": OTHER_LOAN, "user_id": OTHER}],
                 loan_statements=[
                     {"id": sid, "user_id": OTHER, "loan_id": OTHER_LOAN, "statement_date": "2026-09-30"},
                     {"id": mine, "user_id": ME, "loan_id": LOAN_ID, "statement_date": "2026-09-30"},
                 ])
    assert c.get(f"/api/v1/loans/{OTHER_LOAN}/account").status_code == 404
    assert c.post(f"/api/v1/loans/{OTHER_LOAN}/statements/import", files={"file": ("l.csv", b"x", "text/csv")}).status_code == 404
    assert c.delete(f"/api/v1/loans/statements/{sid}").status_code == 404
    assert c.delete(f"/api/v1/loans/statements/{mine}").status_code == 204
    assert [s["id"] for s in db.tables["loan_statements"]] == [sid]


def test_unusable_inputs(monkeypatch):
    c, _ = boot(monkeypatch, loans=[LOAN])
    assert upload(c, "x.zip", b"hi", "application/zip").status_code == 415
    fake_ai(monkeypatch, '{"transactions":[]}')
    assert upload(c).status_code == 422


def test_summary_balance_falls_back_to_statement_closing():
    s = summarize_account([], [{"statement_date": "2026-09-30", "closing_balance": 500000.0}])
    assert s["balance"] == 500000 and s["transaction_count"] == 0 and s["interest_paid"] == 0


def test_yearly_statements_with_same_generation_date_both_import(monkeypatch):
    """Lenders print the day the PDF was generated as the statement date, so PDFs downloaded together share it
    even though they cover different years. That must not make the second one look like a duplicate."""
    c, db = boot(monkeypatch, loans=[LOAN])
    year = lambda y, bal: (  # noqa: E731
        '{"statement_date":"2026-10-12","period_start":"%d-04-01","period_end":"%d-03-31","opening_balance":%d,'
        '"transactions":[{"date":"%d-05-05","description":"EMI","kind":"emi","amount":20000,"balance":%d}]}' % (y, y + 1, bal + 10000, y, bal)
    )
    fake_ai(monkeypatch, year(2024, 990000))
    first = upload(c)
    fake_ai(monkeypatch, year(2025, 980000))
    second = upload(c)
    assert first.status_code == 201 and second.status_code == 201, second.text
    assert sorted(s["statement_date"] for s in db.tables["loan_statements"]) == ["2025-03-31", "2026-03-31"]   # period end, not the print date
    assert c.get(f"/api/v1/loans/{LOAN_ID}/account").json()["summary"]["balance"] == 980000    # latest period wins


def test_reuploading_the_same_period_is_still_blocked(monkeypatch):
    c, db = boot(monkeypatch, loans=[LOAN])
    fake_ai(monkeypatch)
    assert upload(c).status_code == 201
    again = upload(c)
    assert again.status_code == 409 and "already imported" in again.json()["detail"]
    assert len(db.tables["loan_statements"]) == 1


def test_statement_with_nothing_new_is_rejected_without_leaving_a_row(monkeypatch):
    c, db = boot(monkeypatch, loans=[LOAN])
    fake_ai(monkeypatch)
    assert upload(c).status_code == 201
    # Same transactions, but the model reported no period this time, so only the transactions can tell.
    fake_ai(monkeypatch, '{"transactions":[{"date":"2026-09-05","description":"EMI 3","kind":"emi","amount":20000,"balance":919199}]}')
    res = upload(c)
    assert res.status_code == 409 and len(db.tables["loan_statements"]) == 1
