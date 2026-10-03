from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth import AuthUser, get_auth_user
from core.supabase import get_supabase_client
from services import ai, keyvault
from services.ai import PROVIDER_LABELS, AIKeyError
from services.credentials import is_grandfathered, stored_key_row

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class AISettings(BaseModel):
    # own = user saved a key; shared = pre-existing account on the owner's key; none = must add a key
    mode: Literal["own", "shared", "none"]
    provider: Optional[str] = None
    key_last4: Optional[str] = None


class SaveKey(BaseModel):
    provider: Literal["gemini", "anthropic"]
    api_key: str = Field(..., min_length=20, max_length=300)


@router.get("/ai", response_model=AISettings)
async def get_ai_settings(user: AuthUser = Depends(get_auth_user)):
    row = stored_key_row(user.id)
    if row:
        return AISettings(mode="own", provider=row["provider"], key_last4=row["key_last4"])
    if is_grandfathered(user):
        return AISettings(mode="shared", provider="gemini")
    return AISettings(mode="none")


@router.put("/ai-key", response_model=AISettings)
async def save_ai_key(payload: SaveKey, user: AuthUser = Depends(get_auth_user)):
    key = payload.api_key.strip()
    try:
        await ai.validate_key(payload.provider, key)
    except AIKeyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"{PROVIDER_LABELS[payload.provider]} rejected that API key. Check it and try again.",
        )
    except Exception:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach {PROVIDER_LABELS[payload.provider]} to verify the key. Try again in a moment.",
        )
    try:
        encrypted = keyvault.encrypt(key)
    except keyvault.KeyVaultError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Key storage is not configured on the server.")

    get_supabase_client().table("user_ai_keys").upsert(
        {
            "user_id": user.id,
            "provider": payload.provider,
            "encrypted_key": encrypted,
            "key_last4": keyvault.last4(key),
        },
        on_conflict="user_id",
    ).execute()
    return AISettings(mode="own", provider=payload.provider, key_last4=keyvault.last4(key))


@router.delete("/ai-key", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_key(user: AuthUser = Depends(get_auth_user)):
    get_supabase_client().table("user_ai_keys").delete().eq("user_id", user.id).execute()
