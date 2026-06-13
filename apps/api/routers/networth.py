from datetime import date

from fastapi import APIRouter, Depends
from supabase import Client

from core.auth import get_current_user
from core.supabase import get_supabase_client
from schemas.networth import NetWorthBreakdown, NetWorthHistoryEntry, NetWorthSnapshot

router = APIRouter(prefix="/api/v1/networth", tags=["networth"])


def _compute_snapshot(client: Client, user_id: str) -> NetWorthSnapshot:
    holdings = (
        client.table("holdings")
        .select("units,current_price")
        .eq("user_id", user_id)
        .execute()
    ).data
    investments = sum((r["units"] or 0) * (r["current_price"] or 0) for r in holdings)

    epf_nps_rows = (
        client.table("epf_nps_balances")
        .select("balance")
        .eq("user_id", user_id)
        .execute()
    ).data
    epf_nps = sum(r["balance"] or 0 for r in epf_nps_rows)

    # Positive = credit, negative = debit; running sum is the balance estimate
    txn_rows = (
        client.table("bank_transactions")
        .select("amount")
        .eq("user_id", user_id)
        .execute()
    ).data
    bank_balance = sum(r["amount"] or 0 for r in txn_rows)

    loan_rows = (
        client.table("loans")
        .select("outstanding_amount")
        .eq("user_id", user_id)
        .execute()
    ).data
    loans = sum(r["outstanding_amount"] or 0 for r in loan_rows)

    total_assets = round(investments + epf_nps + bank_balance, 2)
    total_liabilities = round(loans, 2)

    return NetWorthSnapshot(
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=round(total_assets - total_liabilities, 2),
        breakdown=NetWorthBreakdown(
            investments=round(investments, 2),
            epf_nps=round(epf_nps, 2),
            bank_balance=round(bank_balance, 2),
            loans=round(loans, 2),
        ),
    )


@router.get("/snapshot", response_model=NetWorthSnapshot)
async def get_networth_snapshot(user_id: str = Depends(get_current_user)):
    return _compute_snapshot(get_supabase_client(), user_id)


@router.post("/snapshot", response_model=NetWorthSnapshot, status_code=201)
async def save_networth_snapshot(user_id: str = Depends(get_current_user)):
    client = get_supabase_client()
    snapshot = _compute_snapshot(client, user_id)

    client.table("networth_log").upsert(
        {
            "user_id": user_id,
            "snapshot_date": date.today().isoformat(),
            "total_assets": snapshot.total_assets,
            "total_liabilities": snapshot.total_liabilities,
            "net_worth": snapshot.net_worth,
            "investments": snapshot.breakdown.investments,
            "epf_nps": snapshot.breakdown.epf_nps,
            "bank_balance": snapshot.breakdown.bank_balance,
            "loans": snapshot.breakdown.loans,
        },
        on_conflict="user_id,snapshot_date",
    ).execute()

    return snapshot


@router.get("/history", response_model=list[NetWorthHistoryEntry])
async def get_networth_history(user_id: str = Depends(get_current_user)):
    response = (
        get_supabase_client()
        .table("networth_log")
        .select("*")
        .eq("user_id", user_id)
        .order("snapshot_date", desc=True)
        .limit(12)
        .execute()
    )
    return [NetWorthHistoryEntry.model_validate(row) for row in response.data]
