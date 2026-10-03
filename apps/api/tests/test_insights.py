from datetime import date, timedelta

import pytest

from services.loan_math import (
    add_months, build_schedule, emi_for, fy_label, principal_for, summarize,
)
from services.recurring import detect_recurring, merchant_key
from services.xirr import xirr


# ── XIRR ──────────────────────────────────────────────────────────────────────

def test_xirr_matches_excel_documentation_example():
    flows = [
        (date(2008, 1, 1), -10000), (date(2008, 3, 1), 2750), (date(2008, 10, 30), 4250),
        (date(2009, 2, 15), 3250), (date(2009, 4, 1), 2750),
    ]
    assert xirr(flows) == pytest.approx(0.373362535, abs=1e-6)


def test_xirr_simple_one_year_ten_percent():
    assert xirr([(date(2023, 1, 1), -1000), (date(2024, 1, 1), 1100)]) == pytest.approx(0.10, abs=1e-6)


def test_xirr_handles_losses():
    assert xirr([(date(2023, 1, 1), -1000), (date(2024, 1, 1), 800)]) == pytest.approx(-0.20, abs=1e-6)


@pytest.mark.parametrize("flows", [
    [],
    [(date(2023, 1, 1), -1000)],
    [(date(2023, 1, 1), -1000), (date(2023, 6, 1), -500)],          # never any money back
    [(date(2023, 1, 1), -1000), (date(2023, 1, 1), 1200)],          # no time passed
])
def test_xirr_undefined_cases_return_none(flows):
    assert xirr(flows) is None


# ── Loan maths ────────────────────────────────────────────────────────────────

def test_emi_for_fifty_lakh_240_months():
    assert emi_for(5_000_000, 8.5, 240) == pytest.approx(43391.16, abs=0.01)


def test_principal_and_emi_are_inverses():
    emi = emi_for(3_000_000, 9.0, 180)
    assert principal_for(emi, 9.0, 180) == pytest.approx(3_000_000, abs=0.01)


def test_schedule_amortises_to_zero_and_splits_correctly():
    rows = build_schedule(principal=5_000_000, annual_pct=8.5, emi=None, tenure_months=240, start_date=date(2022, 4, 1))
    assert len(rows) == 240 and rows[-1].closing == 0
    assert rows[0].interest == pytest.approx(5_000_000 * 0.085 / 12, abs=0.01)
    assert sum(r.principal for r in rows) == pytest.approx(5_000_000, abs=1)
    assert rows[0].due_date == date(2022, 5, 1)


def test_schedule_can_be_built_from_emi_alone():
    emi = emi_for(2_000_000, 8.0, 120)
    rows = build_schedule(principal=None, annual_pct=8.0, emi=emi, tenure_months=120, start_date=date(2023, 1, 15))
    assert rows[0].opening == pytest.approx(2_000_000, abs=1)


def test_emi_below_interest_is_rejected():
    with pytest.raises(ValueError):
        build_schedule(principal=5_000_000, annual_pct=12, emi=1000, tenure_months=240, start_date=date(2022, 1, 1))


def test_summary_tax_limits_and_fy_labels():
    rows = build_schedule(principal=5_000_000, annual_pct=8.5, emi=None, tenure_months=240, start_date=date(2022, 3, 31))
    s = summarize(rows, today=date(2025, 6, 30))
    assert s["emis_paid"] == 39  # first EMI 30 Apr 2022 ... 30 Jun 2025 inclusive
    assert s["outstanding_principal"] == pytest.approx(5_000_000 - s["principal_paid_to_date"], abs=2)
    fy = {t["financial_year"]: t for t in s["tax_by_year"]}
    assert fy["2023-24"]["interest"] > 200_000            # 50L @ 8.5% pays far more than the cap
    assert fy["2023-24"]["deduction_24b"] == 200_000      # ...so the deduction is capped
    assert fy["2023-24"]["deduction_80c_principal"] <= 150_000
    assert s["current_financial_year"] == "2025-26"


def test_fy_label_boundaries():
    assert fy_label(date(2025, 3, 31)) == "2024-25"
    assert fy_label(date(2025, 4, 1)) == "2025-26"


def test_add_months_clamps_day():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


# ── Recurring payments ────────────────────────────────────────────────────────

def test_merchant_key_ignores_refs_and_rails():
    assert merchant_key("UPI-NETFLIX-netflix@ybl-408812345678") == "netflix"
    assert merchant_key("UPI/NETFLIX/987654321/Payment") == "netflix"
    assert merchant_key("ACH D- HDFC LTD-EMI 0042") == "emi"


def monthly(desc, amount, start=date(2026, 1, 5), n=5, jitter=0):
    return [(start.replace(month=start.month + i) + timedelta(days=(i * jitter) % 3), desc, amount) for i in range(n)]


def test_detects_fixed_subscription_and_sip_and_salary():
    txns = (
        monthly("UPI-NETFLIX-netflix@ybl-1", -649)
        + monthly("ACH D- ZERODHA COIN SIP-77", -10000)
        + monthly("NEFT CR-ACME CORP-SALARY", 150000)
    )
    found = {r.name: r for r in detect_recurring(txns)}
    assert found["Netflix"].direction == "expense" and found["Netflix"].typical_amount == 649
    assert found["Netflix"].frequency == "monthly" and not found["Netflix"].variable
    assert "Zerodha Coin" in found
    income = [r for r in found.values() if r.direction == "income"]
    assert len(income) == 1 and income[0].typical_amount == 150000


def test_frequent_small_purchases_are_not_subscriptions():
    swiggy = [(date(2026, 1, 1) + timedelta(days=3 * i), "UPI-SWIGGY-order", -300) for i in range(30)]
    assert not [r for r in detect_recurring(swiggy) if r.name == "Swiggy"]


def test_two_occurrences_are_not_enough():
    assert detect_recurring(monthly("UPI-HOTSTAR-x", -299, n=2)) == []


def test_variable_bill_is_flagged_variable():
    bills = [(date(2026, m, 10), "BESCOM ELECTRICITY BILL", -a) for m, a in [(1, 1200), (2, 1500), (3, 1100), (4, 1700)]]
    r = next(x for x in detect_recurring(bills) if "Bescom" in x.name)
    assert r.variable and r.monthly_cost > 1000


def test_next_expected_is_a_month_after_last():
    r = detect_recurring(monthly("UPI-NETFLIX-x", -649))[0]
    assert 28 <= (r.next_expected - r.last_date).days <= 33
