from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status

from core.auth import AuthUser, get_auth_user
from core.supabase import get_supabase_client
from services import keyvault
from services.ai import PROVIDER_LABELS, AIKeyError, Credentials

# Prefixes the web app looks for to send people to Settings.
KEY_REQUIRED = "AI_KEY_REQUIRED"
KEY_INVALID = "AI_KEY_INVALID"


def _cutoff() -> datetime | None:
    """Accounts created before this instant keep using the owner's shared key.
    Unset means nobody is grandfathered."""
    raw = os.getenv("SHARED_KEY_CUTOFF")
    if not raw:
        return None
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_grandfathered(user: AuthUser) -> bool:
    cutoff = _cutoff()
    created = user.created_at
    if cutoff is None or created is None or not os.getenv("GEMINI_API_KEY"):
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created < cutoff


def stored_key_row(user_id: str) -> dict | None:
    rows = (
        get_supabase_client().table("user_ai_keys").select("provider,encrypted_key,key_last4")
        .eq("user_id", user_id).limit(1).execute()
    ).data
    return rows[0] if rows else None


async def resolve_credentials(user: AuthUser = Depends(get_auth_user)) -> Credentials:
    """Own key if the user saved one; the owner's key for pre-existing accounts; otherwise blocked."""
    row = stored_key_row(user.id)
    if row:
        try:
            return Credentials(row["provider"], keyvault.decrypt(row["encrypted_key"]))
        except keyvault.KeyVaultError:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Your saved key could not be read. Please save it again in Settings.")
    if is_grandfathered(user):
        return Credentials("gemini", os.environ["GEMINI_API_KEY"], shared=True)
    raise HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail=f"{KEY_REQUIRED}: Add your own Gemini or Claude API key in Settings to use document extraction.",
    )


def key_rejected_error(exc: AIKeyError) -> HTTPException:
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail=f"{KEY_INVALID}: Your saved {PROVIDER_LABELS.get(exc.provider, exc.provider)} API key was rejected. Check or replace it in Settings.",
    )
