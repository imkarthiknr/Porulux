from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

AccountType = Literal["EPF", "NPS_TIER1", "NPS_TIER2"]


class EpfNpsCreate(BaseModel):
    account_type: AccountType
    balance: float = Field(0, ge=0)
    as_of_date: Optional[date] = None


class EpfNpsUpdate(BaseModel):
    account_type: Optional[AccountType] = None
    balance: Optional[float] = Field(None, ge=0)
    as_of_date: Optional[date] = None


class EpfNps(BaseModel):
    id: UUID
    account_type: AccountType
    balance: float
    as_of_date: date
    created_at: datetime
    updated_at: datetime
