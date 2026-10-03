import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
from core import crud
from core.auth import AuthUser, get_auth_user
from routers import holdings_import, insights, networth
from services import prices
from services.prices import Quote, name_key, parse_amfi, refresh_holdings, ttl_for, yahoo_tickers
from tests.fakedb import FakeDB

ME = "00000000-0000-0000-0000-00000000000a"
OTHER = "00000000-0000-0000-0000-00000000000c"
USER = AuthUser(ME, datetime(2026, 9, 1, tzinfo=timezone.utc), "me@example.com")

AMFI = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

PPFAS Mutual Fund

122639;INF879O01027;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth;88.2569;01-Oct-2026
122640;INF879O01035;INF879O01043;Parag Parikh Flexi Cap Fund;Regular Plan;IDCW;55.10;01-Oct-2026
100001;INF000A00001;-;Twin Scheme;Direct Plan;Growth;10.0;01-Oct-2026
100002;INF000A00002;-;Twin Scheme;Direct Plan;Growth;11.0;01-Oct-2026
bad line without enough fields
"""


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_yahoo_tickers_handle_series_suffix_bse_codes_and_garbage():
    assert yahoo_tickers("INFY") == ["INFY.NS", "INFY.BO"]
    assert yahoo_tickers("tatamotors-BE") == ["TATAMOTORS.NS", "TATAMOTORS.BO"]
    assert yahoo_tickers("500325") == ["500325.BO"]
    assert yahoo_tickers("M&M") == ["M&M.NS", "M&M.BO"]
    assert yahoo_tickers("PARAG PARIKH FUND") == [] and yahoo_tickers("") == []


def test_amfi_parse_matches_by_isin_and_by_groww_style_name_and_refuses_ambiguity():
    by_isin, by_name = parse_amfi(AMFI)
    assert by_isin["INF879O01027"] == (88.2569, "01-Oct-2026") and by_isin["INF879O01043"][0] == 55.10
    assert by_name[name_key("Parag Parikh Flexi Cap Fund Direct Growth")] == (88.2569, "01-Oct-2026")
    assert by_name[name_key("Parag Parikh Flexi Cap Fund - Regular Plan - IDCW")][0] == 55.10   # direct != regular
    assert by_name[name_key("Twin Scheme Direct Growth")] is None                                # two schemes collide


def test_freshness_window_depends_on_market_hours():
    open_ = datetime(2026, 10, 5, 10, 0, tzinfo=prices.IST)      # Monday 10:00 IST
    night = datetime(2026, 10, 5, 22, 0, tzinfo=prices.IST)
    sunday = datetime(2026, 10, 4, 11, 0, tzinfo=prices.IST)
    assert ttl_for(open_) == timedelta(minutes=10)
    assert ttl_for(night) == timedelta(hours=4) and ttl_for(sunday) == timedelta(hours=4)


# ── refresh logic with a fake provider ────────────────────────────────────────

class FakeProvider:
    def __init__(self, stocks=None, navs=None, fail=False, slow=0.0):
        self.stocks, self.navs, self.fail, self.slow = stocks or {}, navs or {}, fail, slow
        self.calls = []

    async def stock_quote(self, symbol):
        self.calls.append(("stock", symbol))
        if self.slow:
            await asyncio.sleep(self.slow)
        if self.fail:
            raise RuntimeError("provider down")
        p = self.stocks.get(symbol)
        return Quote(p, "yahoo") if p else None

    async def nav_quote(self, isin, name):
        self.calls.append(("nav", isin or name))
        p = self.navs.get(isin) or self.navs.get(name)
        return Quote(p, "amfi 01-Oct-2026") if p else None


def hold(id_, symbol, typ="STOCK", price=100.0, updated=None, isin=None, name=None):
    return {"id": id_, "user_id": ME, "symbol": symbol, "name": name or symbol, "holding_type": typ, "isin": isin,
            "current_price": price, "price_updated_at": updated, "price_source": "old"}


NOW = datetime(2026, 10, 5, 11, 0, tzinfo=prices.IST)          # during market hours


def run(db, holdings, provider, **kw):
    return asyncio.run(refresh_holdings(db, ME, holdings, provider=provider, now=NOW, **kw))


def test_stale_prices_are_fetched_stored_and_reported_live():
    rows = [hold("h1", "INFY", updated=(NOW - timedelta(hours=2)).isoformat())]
    db = FakeDB(holdings=[dict(r) for r in rows])
    rep = run(db, rows, FakeProvider(stocks={"INFY": 1500.5}))
    assert rep["h1"] == {"status": "live", "price": 1500.5, "source": "yahoo"}
    stored = db.tables["holdings"][0]
    assert stored["current_price"] == 1500.5 and stored["price_source"] == "yahoo" and stored["price_updated_at"] == NOW.isoformat()


def test_fresh_prices_are_not_refetched_unless_forced():
    rows = [hold("h1", "INFY", updated=(NOW - timedelta(minutes=3)).isoformat())]
    p = FakeProvider(stocks={"INFY": 999})
    assert run(FakeDB(holdings=[dict(r) for r in rows]), rows, p)["h1"]["status"] == "cached" and p.calls == []
    assert run(FakeDB(holdings=[dict(r) for r in rows]), rows, p, force=True)["h1"]["status"] == "live" and p.calls


def test_provider_failure_keeps_the_stored_price_and_never_raises():
    rows = [hold("h1", "INFY", price=1234.0), hold("h2", "TCS", price=3000.0)]
    db = FakeDB(holdings=[dict(r) for r in rows])
    rep = run(db, rows, FakeProvider(fail=True))
    assert rep["h1"]["status"] == "stale" and rep["h1"]["price"] == 1234.0
    assert [h["current_price"] for h in db.tables["holdings"]] == [1234.0, 3000.0]      # nothing overwritten


def test_unknown_symbol_is_stale_and_unsupported_types_are_manual():
    rows = [hold("h1", "NOPE"), hold("h2", "SGB2028", typ="SGB"), hold("h3", "GOI", typ="BOND")]
    p = FakeProvider(stocks={})
    rep = run(FakeDB(holdings=[dict(r) for r in rows]), rows, p)
    assert rep["h1"]["status"] == "stale" and rep["h2"]["status"] == "manual" and rep["h3"]["status"] == "manual"
    assert all(c[1] == "NOPE" for c in p.calls)                                          # manual types never hit a provider


def test_mutual_funds_use_nav_by_isin_then_by_name_and_etf_falls_back_to_nav():
    rows = [
        hold("f1", "INF879O01027", typ="MF", isin="INF879O01027"),
        hold("f2", "PPFAS", typ="MF", name="Parag Parikh Flexi Cap Fund Direct Growth"),
        hold("e1", "GOLDBEES", typ="ETF", isin="INF204KB17I5"),
    ]
    db = FakeDB(holdings=[dict(r) for r in rows])
    p = FakeProvider(navs={"INF879O01027": 88.25, "Parag Parikh Flexi Cap Fund Direct Growth": 88.25, "INF204KB17I5": 70.0})
    rep = run(db, rows, p)
    assert rep["f1"]["price"] == 88.25 and rep["f1"]["source"].startswith("amfi")
    assert rep["f2"]["price"] == 88.25
    assert rep["e1"]["price"] == 70.0                                                    # Yahoo had nothing, AMFI NAV used
    assert ("stock", "INF879O01027") not in p.calls                                      # funds never go to the stock API


def test_a_slow_provider_cannot_exceed_the_time_budget():
    rows = [hold("h1", "INFY"), hold("h2", "TCS")]
    rep = run(FakeDB(holdings=[dict(r) for r in rows]), rows, FakeProvider(stocks={"INFY": 1}, slow=5.0), budget_seconds=0.2)
    assert {r["status"] for r in rep.values()} == {"stale"}                              # gave up, kept stored prices


# ── endpoints ─────────────────────────────────────────────────────────────────

def boot(monkeypatch, **tables):
    db = FakeDB(**tables)
    for mod in (insights, holdings_import, crud, networth):
        monkeypatch.setattr(mod, "get_supabase_client", lambda: db)
    main.app.dependency_overrides[get_auth_user] = lambda: USER
    return TestClient(main.app), db


@pytest.fixture(autouse=True)
def _clean():
    yield
    main.app.dependency_overrides.clear()


def full_holding(id_, **kw):
    return {"id": id_, "user_id": ME, "symbol": "INFY", "name": "Infosys", "holding_type": "STOCK", "units": 10,
            "avg_buy_price": 1000.0, "current_price": 1000.0, "isin": None, "source": "Zerodha",
            "price_updated_at": None, "price_source": None, **kw}


def test_returns_refreshes_prices_so_gain_and_xirr_move_with_the_market(monkeypatch):
    hid = "11111111-1111-1111-1111-111111111111"
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    c, db = boot(monkeypatch, holdings=[full_holding(hid)],
                 holding_lots=[{"id": "l1", "user_id": ME, "holding_id": hid, "lot_date": year_ago, "lot_type": "BUY", "units": 10, "price": 1000, "assumed": False}])

    async def fake_refresh(client, user_id, force=False, budget_seconds=8.0):
        db.tables["holdings"][0].update(current_price=1200.0, price_updated_at="2026-10-05T05:30:00+00:00", price_source="yahoo")
        return {hid: {"status": "live", "price": 1200.0, "source": "yahoo"}}

    monkeypatch.setattr(insights, "refresh_for_user", fake_refresh)

    off = c.get("/api/v1/investments/returns?refresh=off").json()
    assert off["holdings"][0]["gain"] == 0 and off["holdings"][0]["price_status"] == "cached"

    live = c.get("/api/v1/investments/returns").json()
    h = live["holdings"][0]
    assert h["current_value"] == 12000 and h["gain"] == 2000 and h["price_status"] == "live" and h["price_source"] == "yahoo"
    assert h["xirr_pct"] == pytest.approx(20.0, abs=0.1) and h["xirr_approx"] is False
    assert live["prices"]["live"] == 1 and live["prices"]["updated_at"]


def test_returns_survives_a_failing_price_refresh(monkeypatch):
    c, _ = boot(monkeypatch, holdings=[full_holding("11111111-1111-1111-1111-111111111111")])

    async def boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(insights, "refresh_for_user", boom)
    res = c.get("/api/v1/investments/returns")
    assert res.status_code == 200 and res.json()["holdings"][0]["current_value"] == 10000


def test_dashboard_snapshot_refresh_is_bounded_and_non_fatal(monkeypatch):
    c, _ = boot(monkeypatch, holdings=[], epf_nps_balances=[], bank_transactions=[], loans=[], card_statements=[])

    async def boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(networth, "refresh_for_user", boom)
    assert c.post("/api/v1/networth/snapshot").status_code == 201


def test_import_with_held_since_date_creates_approximate_lots_and_xirr(monkeypatch):
    c, db = boot(monkeypatch, holdings=[], holding_lots=[])
    rows = [{"name": "Infosys", "symbol": "INFY", "holding_type": "STOCK", "units": 10, "avg_buy_price": 1000, "current_price": 1200},
            {"name": "NoCost", "symbol": "NOCOST", "holding_type": "STOCK", "units": 5, "avg_buy_price": None, "current_price": 50}]
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    res = c.post("/api/v1/investments/import/confirm", json={"source": "Zerodha", "rows": rows, "assumed_buy_date": year_ago})
    assert res.status_code == 200 and res.json()["assumed_lots"] == 1                      # no cost basis -> nothing to place
    lot = db.tables["holding_lots"][0]
    assert lot["assumed"] is True and lot["units"] == 10 and lot["price"] == 1000 and lot["lot_date"] == year_ago

    data = c.get("/api/v1/investments/returns?refresh=off").json()
    infy = next(h for h in data["holdings"] if h["symbol"] == "INFY")
    assert infy["xirr_pct"] == pytest.approx(20.0, abs=0.1) and infy["xirr_approx"] is True and data["portfolio"]["xirr_approx"] is True


def test_assumed_lot_never_overrides_real_lots_and_is_replaced_on_reimport(monkeypatch):
    hid = "11111111-1111-1111-1111-111111111111"
    c, db = boot(monkeypatch, holdings=[full_holding(hid)],
                 holding_lots=[{"id": "real", "user_id": ME, "holding_id": hid, "lot_date": "2024-01-01", "lot_type": "BUY", "units": 10, "price": 900, "assumed": False}])
    row = {"name": "Infosys", "symbol": "INFY", "holding_type": "STOCK", "units": 10, "avg_buy_price": 1000, "current_price": 1100, "existing_id": hid}
    c.post("/api/v1/investments/import/confirm", json={"source": "Zerodha", "rows": [row], "assumed_buy_date": "2025-01-01"})
    assert [l["id"] for l in db.tables["holding_lots"]] == ["real"]                       # real lot wins

    db.tables["holding_lots"].clear()
    c.post("/api/v1/investments/import/confirm", json={"source": "Zerodha", "rows": [row], "assumed_buy_date": "2025-01-01"})
    c.post("/api/v1/investments/import/confirm", json={"source": "Zerodha", "rows": [{**row, "units": 12}], "assumed_buy_date": "2025-06-01"})
    lots = db.tables["holding_lots"]
    assert len(lots) == 1 and lots[0]["units"] == 12 and lots[0]["lot_date"] == "2025-06-01"   # replaced, not stacked


def test_real_lot_replaces_the_assumed_one(monkeypatch):
    hid = "11111111-1111-1111-1111-111111111111"
    c, db = boot(monkeypatch, holdings=[full_holding(hid)],
                 holding_lots=[{"id": "a1", "user_id": ME, "holding_id": hid, "lot_date": "2025-01-01", "lot_type": "BUY", "units": 10, "price": 1000, "assumed": True}])
    res = c.post(f"/api/v1/holdings/{hid}/lots", json={"lot_date": "2024-03-01", "lot_type": "BUY", "units": 10, "price": 950})
    assert res.status_code == 201
    assert [(l["lot_date"], l.get("assumed", False)) for l in db.tables["holding_lots"]] == [("2024-03-01", False)]


@pytest.mark.parametrize("bad", ["2999-01-01", "1900-01-01"])
def test_held_since_must_be_a_sensible_past_date(monkeypatch, bad):
    c, _ = boot(monkeypatch, holdings=[])
    row = {"name": "A", "symbol": "A", "holding_type": "STOCK", "units": 1, "avg_buy_price": 1, "current_price": 1}
    assert c.post("/api/v1/investments/import/confirm", json={"source": "Z", "rows": [row], "assumed_buy_date": bad}).status_code == 422
