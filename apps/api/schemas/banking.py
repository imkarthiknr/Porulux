from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

Last4 = Field(..., pattern=r"^[0-9]{4}$")
AccountType = Literal["SAVINGS", "CURRENT", "SALARY"]
CardNetwork = Literal["VISA", "MASTERCARD", "AMEX", "RUPAY", "DINERS", "OTHER"]


class BankAccountCreate(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=80)
    account_type: AccountType = "SAVINGS"
    last4: str = Last4
    nickname: Optional[str] = Field(None, max_length=60)
    ifsc: Optional[str] = Field(None, pattern=r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")


class BankAccountUpdate(BaseModel):
    bank_name: Optional[str] = Field(None, min_length=2, max_length=80)
    account_type: Optional[AccountType] = None
    last4: Optional[str] = Field(None, pattern=r"^[0-9]{4}$")
    nickname: Optional[str] = Field(None, max_length=60)
    ifsc: Optional[str] = Field(None, pattern=r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")


class BankAccount(BankAccountCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime


class CreditCardCreate(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=80)
    card_name: Optional[str] = Field(None, max_length=80)
    network: Optional[CardNetwork] = None
    last4: str = Last4
    credit_limit: Optional[float] = Field(None, ge=0)
    statement_day: Optional[int] = Field(None, ge=1, le=31)
    due_day: Optional[int] = Field(None, ge=1, le=31)
    annual_fee: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0, le=100)


class CreditCardUpdate(BaseModel):
    bank_name: Optional[str] = Field(None, min_length=2, max_length=80)
    card_name: Optional[str] = Field(None, max_length=80)
    network: Optional[CardNetwork] = None
    last4: Optional[str] = Field(None, pattern=r"^[0-9]{4}$")
    credit_limit: Optional[float] = Field(None, ge=0)
    statement_day: Optional[int] = Field(None, ge=1, le=31)
    due_day: Optional[int] = Field(None, ge=1, le=31)
    annual_fee: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0, le=100)


class CreditCard(CreditCardCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime
