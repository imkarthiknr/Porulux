from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

HoldingType = Literal["STOCK", "MF", "ETF", "BOND", "SGB", "OTHER"]


class HoldingCreate(BaseModel):
    symbol: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    holding_type: HoldingType
    units: float = Field(0, ge=0)
    current_price: Optional[float] = Field(None, ge=0)
    avg_buy_price: Optional[float] = Field(None, ge=0)
    isin: Optional[str] = None


class HoldingUpdate(BaseModel):
    symbol: Optional[str] = Field(None, min_length=1)
    name: Optional[str] = Field(None, min_length=1)
    holding_type: Optional[HoldingType] = None
    units: Optional[float] = Field(None, ge=0)
    current_price: Optional[float] = Field(None, ge=0)
    avg_buy_price: Optional[float] = Field(None, ge=0)
    isin: Optional[str] = None


class Holding(HoldingCreate):
    id: UUID
    source: Optional[str] = None
    last_imported_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
