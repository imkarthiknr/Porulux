from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

LoanType = Literal["HOME_LOAN", "PERSONAL_LOAN", "VEHICLE_LOAN", "CREDIT_CARD", "OTHER"]


class LoanCreate(BaseModel):
    loan_type: LoanType
    lender_name: Optional[str] = None
    outstanding_amount: float = Field(0, ge=0)
    emi_amount: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0, le=100)
    tenure_months: Optional[int] = Field(None, ge=0)
    start_date: Optional[date] = None
    principal_amount: Optional[float] = Field(None, ge=0)  # original loan amount


class LoanUpdate(BaseModel):
    loan_type: Optional[LoanType] = None
    lender_name: Optional[str] = None
    outstanding_amount: Optional[float] = Field(None, ge=0)
    emi_amount: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0, le=100)
    tenure_months: Optional[int] = Field(None, ge=0)
    start_date: Optional[date] = None
    principal_amount: Optional[float] = Field(None, ge=0)  # original loan amount


class Loan(LoanCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime
