from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    success: bool = True
    doc_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[str] = None   # "high" | "low"
    raw_extraction: Optional[str] = None
