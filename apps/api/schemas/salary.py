from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SalaryCreate(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2100)
    employer_name: Optional[str] = None
    basic: Optional[float] = None
    hra: Optional[float] = None
    special_allowance: Optional[float] = None
    pf_employee: Optional[float] = None
    pf_employer: Optional[float] = None
    income_tax: Optional[float] = None
    professional_tax: Optional[float] = None
    gross_pay: Optional[float] = None
    net_pay: Optional[float] = None
    payslip_url: Optional[str] = None


class SalaryRecord(SalaryCreate):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
