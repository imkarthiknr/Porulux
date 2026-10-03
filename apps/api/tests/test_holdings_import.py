import io

import pytest
from openpyxl import Workbook

from services.holdings_import import (
    guess_source, infer_type, merge_duplicates, normalize_ai_result, parse_tabular, reconcile,
)

ZERODHA_CSV = b"""Instrument,Qty.,Avg. cost,LTP,Invested,Cur. val,P&L,Net chg.,Day chg.
INFY,10,1450.50,1500.00,14505.00,15000.00,495.00,3.41%,0.5%
RELIANCE,5,2400,2500,12000,12500,500,4.17%,0.3%
NIFTYBEES,100,250.10,262.00,25010,26200,1190,4.7%,0.1%
"""

GROWW_STOCKS = b"""Name,Karthik N R
Unique Client Code,12345

Holdings statement for 02-10-2026
Stock Name,ISIN,Quantity,Average buy price,Buy value,Closing price,Closing value,Unrealised P&L
HDFC BANK LTD,INE040A01034,15,1620.40,24306.00,1700.00,25500.00,1194.00
TATA MOTORS LTD,INE155A01022,"1,200",640,"7,68,000",900,"10,80,000","3,12,000"
Total,,,,"7,92,306",,"11,05,500",
"""

GROWW_MF = b"""Scheme Name,AMC,Category,Sub-category,Folio No.,Source,Units,Invested Value,Current Value,Returns,XIRR
Parag Parikh Flexi Cap Fund Direct Growth,PPFAS Mutual Fund,Equity,Flexi Cap,12345,Direct,100.5,50000,72000,22000,18.5%
Nippon India ETF Gold BeES,Nippon,Commodity,Gold,67890,Direct,500,30000,33000,3000,10%
"""

ICICI = b"""Stock Symbol,Company Name,ISIN Code,Qty,Average Cost Price,Current Market Price,Value At Market Price
ITC,ITC LTD,INE154A01025,200,410.5,430.25,86050
"""


def by_symbol(res):
    return {h.symbol: h for h in res.holdings}


def test_zerodha_csv_and_type_inference():
    r = parse_tabular(ZERODHA_CSV, "holdings.csv")
    h = by_symbol(r)
    assert set(h) == {"INFY", "RELIANCE", "NIFTYBEES"}
    assert (h["INFY"].units, h["INFY"].avg_buy_price, h["INFY"].current_price) == (10, 1450.5, 1500.0)
    assert h["INFY"].holding_type == "STOCK" and h["NIFTYBEES"].holding_type == "ETF"


def test_groww_stocks_skips_preamble_total_row_and_parses_indian_commas():
    r = parse_tabular(GROWW_STOCKS, "Holdings_Statement.csv")
    h = by_symbol(r)
    assert list(h) == ["HDFC BANK LTD", "TATA MOTORS LTD"] or set(h) == {"HDFC BANK LTD", "TATA MOTORS LTD"}
    tm = next(x for x in r.holdings if "TATA" in x.name)
    assert tm.units == 1200 and tm.avg_buy_price == 640 and tm.current_price == 900 and tm.isin == "INE155A01022"
    assert len(r.holdings) == 2          # the "Total" row is not a holding


def test_groww_mutual_funds_derive_prices_from_values():
    r = parse_tabular(GROWW_MF, "mf.csv")
    ppfas = next(x for x in r.holdings if "Parag" in x.name)
    assert ppfas.holding_type == "MF" and ppfas.units == 100.5
    assert ppfas.avg_buy_price == pytest.approx(50000 / 100.5, abs=1e-3)
    assert ppfas.current_price == pytest.approx(72000 / 100.5, abs=1e-3)
    assert ppfas.symbol                         # NOT NULL in the database: falls back to a trimmed name
    gold = next(x for x in r.holdings if "Gold" in x.name)
    assert gold.holding_type == "ETF"


def test_icici_direct_headers():
    r = parse_tabular(ICICI, "icici.csv")
    h = r.holdings[0]
    assert (h.symbol, h.name, h.isin, h.units, h.avg_buy_price, h.current_price) == ("ITC", "ITC LTD", "INE154A01025", 200, 410.5, 430.25)


def test_zerodha_xlsx_two_sheets_and_pledged_quantities_are_included():
    wb = Workbook()
    eq = wb.active
    eq.title = "Equity"
    eq.append(["Client ID", "AB1234"])
    eq.append([])
    eq.append(["Symbol", "ISIN", "Sector", "Quantity Available", "Quantity Discrepant", "Quantity Long Term",
               "Quantity Pledged (Margin)", "Quantity Pledged (Loan)", "Average Price", "Previous Closing Price"])
    eq.append(["INFY", "INE009A01021", "IT", 8, 0, 8, 2, 0, 1450.5, 1500])
    mf = wb.create_sheet("Mutual Funds")
    mf.append(["Symbol", "ISIN", "Quantity Available", "Average Price", "Previous Closing Price"])
    mf.append(["PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN - GROWTH", "INF879O01027", 250.5, 55.2, 80.1])
    buf = io.BytesIO()
    wb.save(buf)

    r = parse_tabular(buf.getvalue(), "holdings-AB1234.xlsx")
    infy = next(h for h in r.holdings if h.symbol == "INFY")
    assert infy.units == 10                      # 8 available + 2 pledged
    fund = next(h for h in r.holdings if h.isin == "INF879O01027")
    assert fund.holding_type == "MF" and fund.units == 250.5 and fund.symbol == "INF879O01027"


def test_duplicate_lines_merge_with_weighted_average_cost():
    csv = b"Symbol,ISIN,Qty,Avg cost,LTP\nINFY,INE009A01021,10,1000,1500\nINFY,INE009A01021,30,2000,1500\n"
    (h,) = parse_tabular(csv, "x.csv").holdings
    assert h.units == 40 and h.avg_buy_price == 1750.0


def test_unrecognised_file_yields_nothing():
    assert parse_tabular(b"foo,bar\n1,2\n", "x.csv").holdings == []


def test_rows_without_quantity_are_warned_not_imported():
    r = parse_tabular(b"Instrument,Qty.,Avg. cost,LTP\nINFY,0,1,1\nTCS,5,3000,3100\n", "x.csv")
    assert [h.symbol for h in r.holdings] == ["TCS"] and any("INFY" in w for w in r.warnings)


@pytest.mark.parametrize("name,isin,expected", [
    ("Infosys Ltd", "INE009A01021", "STOCK"),
    ("Nippon India ETF Nifty BeES", "INF204KB14I2", "ETF"),
    ("Parag Parikh Flexi Cap Fund Direct Growth", "INF879O01027", "MF"),
    ("SGB 2.50% Gold Bond 2028", None, "SGB"),
    ("7.26% GOI Bond 2033", None, "BOND"),
    ("Some Scheme IDCW", None, "MF"),
])
def test_infer_type(name, isin, expected):
    assert infer_type(name, isin) == expected


def test_ai_result_normalisation_and_bad_input():
    raw = {"source": "NSDL CAS", "holdings": [
        {"name": "Axis Bluechip Fund - Direct - Growth", "isin": "INF846K01DP8", "units": 1234.567, "invested_value": 100000, "current_value": 150000, "type": "MF"},
        {"name": "Infosys Ltd", "symbol": "INFY", "isin": "bad-isin", "units": 10, "average_cost": 1400, "current_price": 1500},
        {"name": "No units", "units": 0},
    ]}
    r = normalize_ai_result(raw)
    assert r.source_hint == "NSDL CAS" and len(r.holdings) == 2
    fund = next(h for h in r.holdings if h.holding_type == "MF")
    assert fund.avg_buy_price == pytest.approx(100000 / 1234.567, abs=1e-3)
    assert next(h for h in r.holdings if h.symbol == "INFY").isin is None      # invalid ISIN dropped, not trusted
    with pytest.raises(ValueError):
        normalize_ai_result({"nope": 1})


def test_guess_source_from_filename():
    assert guess_source("Zerodha_holdings_2026.xlsx") == "Zerodha"
    assert guess_source("CAMS-statement.pdf") == "CAMS"
    assert guess_source("statement.csv") is None


# ── reconcile against existing holdings ───────────────────────────────────────

def _existing():
    return [
        {"id": "m1", "symbol": "INFY", "isin": None, "units": 10, "avg_buy_price": 1450.5, "current_price": 1400, "source": None},   # added by hand
        {"id": "z1", "symbol": "RELIANCE", "isin": None, "units": 5, "avg_buy_price": 2400, "current_price": 2500, "source": "Zerodha"},
        {"id": "z2", "symbol": "SOLDSTOCK", "isin": None, "units": 3, "avg_buy_price": 10, "current_price": 11, "source": "Zerodha"},
        {"id": "g1", "symbol": "TCS", "isin": None, "units": 1, "avg_buy_price": 1, "current_price": 1, "source": "Groww"},
    ]


def test_reconcile_new_update_unchanged_adopted_and_missing():
    parsed = parse_tabular(ZERODHA_CSV, "z.csv").holdings
    entries, missing = reconcile(parsed, _existing(), "Zerodha")
    act = {e["symbol"]: e for e in entries}
    assert act["INFY"]["action"] == "update" and act["INFY"]["existing_id"] == "m1"      # hand-added row adopted, price moved
    assert act["INFY"]["changes"]["current_price"] == {"from": 1400, "to": 1500.0}
    assert act["RELIANCE"]["action"] == "unchanged"
    assert act["NIFTYBEES"]["action"] == "new" and act["NIFTYBEES"]["existing_id"] is None
    assert [m["symbol"] for m in missing] == ["SOLDSTOCK"]                               # sold since; Groww's TCS is not touched


def test_reconcile_never_matches_another_brokers_holding():
    parsed = parse_tabular(b"Instrument,Qty.,Avg. cost,LTP\nTCS,2,3000,3100\n", "z.csv").holdings
    entries, missing = reconcile(parsed, _existing(), "Zerodha")
    assert entries[0]["action"] == "new" and entries[0]["existing_id"] is None
    assert not [m for m in missing if m["symbol"] == "TCS"]


def test_merge_helper_keeps_distinct_keys():
    a = parse_tabular(ZERODHA_CSV, "z.csv").holdings
    assert len(merge_duplicates(a + a)) == len(a)
