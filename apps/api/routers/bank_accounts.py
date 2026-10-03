from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth import get_current_user
from core.crud import make_crud_router
from core.supabase import get_supabase_client
from schemas.banking import BankAccount, BankAccountCreate, BankAccountUpdate

accounts_crud = make_crud_router(
    prefix="/api/v1/bank-accounts", tag="bank-accounts", table="bank_accounts",
    create_schema=BankAccountCreate, update_schema=BankAccountUpdate, read_schema=BankAccount,
)

router = APIRouter(prefix="/api/v1/bank-accounts", tags=["bank-accounts"])


def own_account(user_id: str, account_id: str) -> dict:
    rows = (
        get_supabase_client().table("bank_accounts").select("*")
        .eq("id", account_id).eq("user_id", user_id).limit(1).execute()
    ).data
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    return rows[0]


@router.get("/summary")
async def accounts_summary(user_id: str = Depends(get_current_user)):
    """Each account with its balance (sum of its transactions, incl. any opening-balance row),
    plus how many transactions are not assigned to any account yet."""
    client = get_supabase_client()
    accounts = client.table("bank_accounts").select("*").eq("user_id", user_id).execute().data
    txns = (
        client.table("bank_transactions").select("account_id,amount,transaction_date")
        .eq("user_id", user_id).limit(20000).execute()
    ).data

    agg = defaultdict(lambda: {"balance": 0.0, "count": 0, "last": None})
    for t in txns:
        a = agg[t.get("account_id")]
        a["balance"] += float(t["amount"])
        a["count"] += 1
        if a["last"] is None or t["transaction_date"] > a["last"]:
            a["last"] = t["transaction_date"]

    out = []
    for acc in sorted(accounts, key=lambda a: (a["bank_name"], a["last4"])):
        a = agg.get(acc["id"], {"balance": 0.0, "count": 0, "last": None})
        out.append({**acc, "balance": round(a["balance"], 2), "transaction_count": a["count"], "last_transaction_date": a["last"]})
    un = agg.get(None, {"balance": 0.0, "count": 0, "last": None})
    return {
        "accounts": out,
        "total_balance": round(sum(a["balance"] for a in agg.values()), 2),
        "unassigned": {"count": un["count"], "balance": round(un["balance"], 2)},
    }


@router.post("/{account_id}/assign-unassigned")
async def assign_unassigned(account_id: str, user_id: str = Depends(get_current_user)):
    """Move every transaction that has no account yet onto this account."""
    acc = own_account(user_id, account_id)
    res = (
        get_supabase_client().table("bank_transactions")
        .update({"account_id": acc["id"], "bank_name": acc["bank_name"], "account_last4": acc["last4"]})
        .eq("user_id", user_id).is_("account_id", "null").execute()
    )
    return {"assigned": len(res.data)}
