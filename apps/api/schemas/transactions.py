from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    transaction_date: date
    description: str = Field(..., min_length=1)
    amount: float  # positive = credit, negative = debit
    category: Optional[str] = None  # auto-categorised when omitted
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None


class TransactionUpdate(BaseModel):
    transaction_date: Optional[date] = None
    description: Optional[str] = Field(None, min_length=1)
    amount: Optional[float] = None
    category: Optional[str] = None
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None


class Transaction(BaseModel):
    id: UUID
    transaction_date: date
    description: str
    amount: float
    category: Optional[str] = None
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None
    created_at: datetime


class ImportResult(BaseModel):
    parsed: int
    inserted: int
    duplicates_skipped: int


class CategoryTotal(BaseModel):
    category: str
    total: float


class MonthlySummary(BaseModel):
    month: str  # YYYY-MM
    income: float
    expenses: float
    net: float
    by_category: list[CategoryTotal]
