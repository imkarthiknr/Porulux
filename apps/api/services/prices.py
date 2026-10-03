from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; Porulux/1.0)"}

# Types we can price automatically. Bonds, SGBs and "other" stay manual.
PRICEABLE = {"STOCK", "ETF", "MF"}


@dataclass(frozen=True)
class Quote:
    price: float
    source: str  # e.g. "yahoo", "amfi 01-Oct-2026"


class PriceProvider(Protocol):
    async def stock_quote(self, symbol: str) -> Quote | None: ...
    async def nav_quote(self, isin: str | None, name: str | None) -> Quote | None: ...


# ── Symbol / name helpers ─────────────────────────────────────────────────────

_SERIES = re.compile(r"-(BE|EQ|SM|BZ|ST|N\d|GB|GS)$", re.I)


def yahoo_tickers(symbol: str) -> list[str]:
    """NSE first, then BSE. Brokers append series suffixes (-BE, -EQ) that Yahoo does not use."""
    s = _SERIES.sub("", symbol.strip().upper())
    if not s or " " in s:
        return []
    if s.isdigit():  # BSE scrip code
        return [f"{s}.BO"]
    return [f"{s}.NS", f"{s}.BO"]


_NAME_NOISE = {"plan", "option", "scheme", "the", "of", "and", "fund", "mutual"}


def name_key(name: str) -> frozenset[str]:
    """'Parag Parikh Flexi Cap Fund Direct Plan Growth' and Groww's 'Parag Parikh Flexi Cap Fund Direct
    Growth' reduce to the same token set. Direct vs Regular and Growth vs IDCW stay distinguishing."""
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    tokens = ["growth" if t in ("g", "gr") else t for t in tokens]
    return frozenset(t for t in tokens if t not in _NAME_NOISE)


def parse_amfi(text: str) -> tuple[dict[str, tuple[float, str]], dict[frozenset[str], tuple[float, str] | None]]:
    """AMFI NAVAll.txt -> ({isin: (nav, date)}, {name_token_set: (nav, date) or None if ambiguous})."""
    by_isin: dict[str, tuple[float, str]] = {}
    by_name: dict[frozenset[str], tuple[float, str] | None] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 8 or not parts[0].isdigit():
            continue
        try:
            nav = float(parts[6])
        except ValueError:
            continue
        date = parts[7]
        for isin in (parts[1], parts[2]):
            if re.fullmatch(r"INF[A-Z0-9]{9}", isin):
                by_isin[isin] = (nav, date)
        key = name_key(f"{parts[3]} {parts[4]} {parts[5]}")
        by_name[key] = (nav, date) if key not in by_name else None  # two schemes collide -> refuse to guess
    return by_isin, by_name


# ── Default provider: Yahoo Finance (stocks/ETFs) + AMFI (mutual funds) ───────

class LiveProvider:
    _amfi: tuple[dict, dict] | None = None
    _amfi_at: float = 0.0
    _AMFI_TTL = 6 * 3600
    _lock = asyncio.Lock()

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def stock_quote(self, symbol: str) -> Quote | None:
        for ticker in yahoo_tickers(symbol):
            try:
                r = await self.client.get(YAHOO_URL.format(symbol=quote(ticker, safe=".-")), headers=_UA)
                if r.status_code != 200:
                    continue
                meta = r.json()["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice")
                if meta.get("currency") == "INR" and isinstance(price, (int, float)) and price > 0:
                    return Quote(float(price), "yahoo")
            except Exception:
                logger.debug("yahoo quote failed for %s", ticker, exc_info=True)
        return None

    async def _amfi_tables(self):
        cls = type(self)
        async with cls._lock:
            if cls._amfi is None or time.time() - cls._amfi_at > cls._AMFI_TTL:
                try:
                    r = await self.client.get(AMFI_URL, headers=_UA, follow_redirects=True, timeout=25.0)
                    r.raise_for_status()
                    cls._amfi, cls._amfi_at = parse_amfi(r.text), time.time()
                except Exception:
                    logger.warning("AMFI NAV download failed", exc_info=True)
        return cls._amfi

    async def nav_quote(self, isin: str | None, name: str | None) -> Quote | None:
        tables = await self._amfi_tables()
        if not tables:
            return None
        by_isin, by_name = tables
        hit = by_isin.get(isin.upper()) if isin else None
        if hit is None and name:
            hit = by_name.get(name_key(name))
        return Quote(hit[0], f"amfi {hit[1]}") if hit else None


# ── Freshness ─────────────────────────────────────────────────────────────────

def market_open(now: datetime) -> bool:
    ist = now.astimezone(IST)
    return ist.weekday() < 5 and (9, 0) <= (ist.hour, ist.minute) <= (15, 45)


def ttl_for(now: datetime) -> timedelta:
    """Prices barely move outside market hours, so don't hammer the providers then."""
    return timedelta(minutes=10) if market_open(now) else timedelta(hours=4)


def _is_fresh(h: dict, now: datetime) -> bool:
    ts = h.get("price_updated_at")
    if not ts or h.get("current_price") is None:
        return False
    try:
        updated = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    return now - updated < ttl_for(now)


async def refresh_holdings(
    db, user_id: str, holdings: list[dict], *, provider: PriceProvider, now: datetime | None = None,
    force: bool = False, budget_seconds: float = 8.0, concurrency: int = 8,
) -> dict[str, dict]:
    """Bring each holding's current_price up to date and persist it. Never raises and never exceeds the time
    budget: a holding whose price can't be fetched keeps its stored price and is reported 'stale'.

    Returns {holding_id: {"status": live|cached|stale|manual, "price", "source"}}."""
    now = now or datetime.now(timezone.utc)
    report: dict[str, dict] = {}
    sem = asyncio.Semaphore(concurrency)

    async def one(h: dict) -> None:
        hid = str(h["id"])
        if h.get("holding_type") not in PRICEABLE:
            report[hid] = {"status": "manual", "price": h.get("current_price"), "source": h.get("price_source")}
            return
        if not force and _is_fresh(h, now):
            report[hid] = {"status": "cached", "price": h.get("current_price"), "source": h.get("price_source")}
            return
        q: Quote | None = None
        async with sem:
            try:
                if h["holding_type"] == "MF":
                    q = await provider.nav_quote(h.get("isin"), h.get("name"))
                else:
                    q = await provider.stock_quote(h["symbol"])
                    if q is None and h.get("isin") and h["holding_type"] == "ETF":
                        q = await provider.nav_quote(h["isin"], h.get("name"))  # last resort for ETFs
            except Exception:
                logger.warning("price lookup failed for %s", h.get("symbol"), exc_info=True)
        if q is None:
            report[hid] = {"status": "stale", "price": h.get("current_price"), "source": h.get("price_source")}
            return
        try:
            db.table("holdings").update(
                {"current_price": round(q.price, 4), "price_updated_at": now.isoformat(), "price_source": q.source}
            ).eq("id", hid).eq("user_id", user_id).execute()
        except Exception:
            logger.warning("could not store price for %s", hid, exc_info=True)
            report[hid] = {"status": "stale", "price": h.get("current_price"), "source": h.get("price_source")}
            return
        h["current_price"], h["price_updated_at"], h["price_source"] = round(q.price, 4), now.isoformat(), q.source
        report[hid] = {"status": "live", "price": round(q.price, 4), "source": q.source}

    try:
        await asyncio.wait_for(asyncio.gather(*(one(h) for h in holdings)), timeout=budget_seconds)
    except asyncio.TimeoutError:
        logger.warning("price refresh hit the %.0fs budget", budget_seconds)
    for h in holdings:  # anything still unreported (timed out) keeps its stored price
        report.setdefault(str(h["id"]), {"status": "stale", "price": h.get("current_price"), "source": h.get("price_source")})
    return report


async def refresh_for_user(db, user_id: str, *, force: bool = False, budget_seconds: float = 8.0) -> dict[str, dict]:
    """Convenience wrapper: load the user's holdings, refresh with the live provider."""
    holdings = (
        db.table("holdings")
        .select("id,symbol,name,isin,holding_type,current_price,price_updated_at,price_source")
        .eq("user_id", user_id).limit(2000).execute()
    ).data
    if not holdings:
        return {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=3.0)) as client:
        return await refresh_holdings(db, user_id, holdings, provider=LiveProvider(client), force=force, budget_seconds=budget_seconds)
