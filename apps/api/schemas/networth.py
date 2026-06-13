from __future__ import annotations
from datetime import date
from uuid import UUID

from pydantic import BaseModel, model_validator


class NetWorthBreakdown(BaseModel):
    investments: float
    epf_nps: float
    bank_balance: float
    loans: float


class NetWorthSnapshot(BaseModel):
    total_assets: float
    total_liabilities: float
    net_worth: float
    breakdown: NetWorthBreakdown


class NetWorthHistoryEntry(BaseModel):
    id: UUID
    snapshot_date: date
    total_assets: float
    total_liabilities: float
    net_worth: float
    breakdown: NetWorthBreakdown

    @model_validator(mode="before")
    @classmethod
    def _build_breakdown(cls, data: dict) -> dict:
        if isinstance(data, dict) and "breakdown" not in data:
            data["breakdown"] = {
                "investments": data.pop("investments", 0),
                "epf_nps": data.pop("epf_nps", 0),
                "bank_balance": data.pop("bank_balance", 0),
                "loans": data.pop("loans", 0),
            }
        return data
