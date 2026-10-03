import pytest

from services.bank_import import ImportError_, parse_amount, parse_csv, parse_date
from services.categorizer import categorize

HDFC_STYLE = b"""HDFC BANK Ltd.
Account Statement
Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/04/24,UPI-SWIGGY-swiggy@icici,0001,01/04/24,"1,250.50",,98749.50
02/04/24,NEFT CR-ACME CORP-SALARY APR,0002,02/04/24,,"1,50,000.00",248749.50
03/04/24,ACH D- HDFC LTD-EMI,0003,03/04/24,"42,000.00",,206749.50
Total,,,,,,
"""

SIGNED_STYLE = b"""Transaction Date,Description,Amount,Dr/Cr
2024-04-05,AMAZON PAY,499.00,DR
2024-04-06,INTEREST CREDIT,12.34,CR
"""


def test_parse_hdfc_style_with_preamble_and_split_columns():
    txns = parse_csv(HDFC_STYLE)
    assert [(t.transaction_date.isoformat(), t.amount) for t in txns] == [
        ("2024-04-01", -1250.50),
        ("2024-04-02", 150000.00),
        ("2024-04-03", -42000.00),
    ]


def test_parse_signed_amount_with_dr_cr_column():
    txns = parse_csv(SIGNED_STYLE)
    assert [t.amount for t in txns] == [-499.00, 12.34]


def test_missing_header_raises():
    with pytest.raises(ImportError_):
        parse_csv(b"foo,bar\n1,2\n")


def test_parse_amount_variants():
    assert parse_amount("1,23,456.78") == 123456.78
    assert parse_amount("₹ 500") == 500
    assert parse_amount("(250.00)") == -250
    assert parse_amount("100.00Dr") == -100
    assert parse_amount("-") is None


def test_parse_date_variants():
    assert parse_date("05 Apr 2024").isoformat() == "2024-04-05"
    assert parse_date("5-Apr-24").isoformat() == "2024-04-05"
    assert parse_date("garbage") is None


@pytest.mark.parametrize(
    "desc,amount,expected",
    [
        ("UPI-SWIGGY-order", -300, "Food"),
        ("NEFT CR-ACME-SALARY", 150000, "Salary"),
        ("ACH D- HDFC LTD-EMI", -42000, "EMI"),
        ("ZERODHA BROKING", -5000, "Investments"),
        ("UPI-RANDOM PERSON", -100, "Transfer"),
        ("SOMETHING ELSE", -10, "Other"),
        ("SALARY ADVANCE RECOVERY", -5000, "Other"),
    ],
)
def test_categorize(desc, amount, expected):
    assert categorize(desc, amount) == expected


def test_opening_balance_derived_from_running_balance():
    from services.bank_import import derive_opening_balance
    txns = parse_csv(HDFC_STYLE)
    # first row: -1,250.50 leaving 98,749.50 -> opened at 100,000.00
    assert derive_opening_balance(txns) == 100000.00


def test_opening_balance_handles_newest_first_statements():
    from services.bank_import import derive_opening_balance
    csv = b"Date,Narration,Debit,Credit,Balance\n03/04/24,B,,50.00,150.00\n02/04/24,A,20.00,,100.00\n"
    assert derive_opening_balance(parse_csv(csv)) == 120.00
