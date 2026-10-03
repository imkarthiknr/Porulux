from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from core.auth import AuthUser, get_auth_user
from core.supabase import get_supabase_client

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])

BUCKET = "avatars"
MAX_AVATAR_BYTES = 2 * 1024 * 1024
SIGNED_URL_SECONDS = 3600
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class ProfileIn(BaseModel):
    full_name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, pattern=r"^\+?[0-9 ()\-]{7,20}$")
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9 \-]{3,10}$")
    country: Optional[str] = Field(None, max_length=100)


class ProfileOut(ProfileIn):
    email: Optional[str] = None
    avatar_url: Optional[str] = None


def sniff_image(data: bytes) -> str | None:
    """Trust the bytes, not the filename or the client's Content-Type."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def signed_avatar_url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        res = get_supabase_client().storage.from_(BUCKET).create_signed_url(path, SIGNED_URL_SECONDS)
    except Exception:
        return None
    url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url") if isinstance(res, dict) else None
    if not url:
        return None
    if url.startswith("/"):
        url = f"{os.environ.get('SUPABASE_URL', '').rstrip('/')}/storage/v1{url}"
    return url


def _row(user_id: str) -> dict | None:
    rows = get_supabase_client().table("profiles").select("*").eq("user_id", user_id).limit(1).execute().data
    return rows[0] if rows else None


def _out(user: AuthUser, row: dict | None, email: str | None = None) -> ProfileOut:
    row = row or {}
    fields = {k: row.get(k) for k in ProfileIn.model_fields}
    fields["country"] = fields.get("country") or "India"
    return ProfileOut(**fields, email=email, avatar_url=signed_avatar_url(row.get("avatar_path")))


def _email(user: AuthUser) -> str | None:
    return getattr(user, "email", None)


@router.get("", response_model=ProfileOut)
async def get_profile(user: AuthUser = Depends(get_auth_user)):
    return _out(user, _row(user.id), _email(user))


@router.put("", response_model=ProfileOut)
async def save_profile(payload: ProfileIn, user: AuthUser = Depends(get_auth_user)):
    data = {k: (v.strip() if isinstance(v, str) and v.strip() else None) for k, v in payload.model_dump().items()}
    data["country"] = data.get("country") or "India"
    data["user_id"] = user.id
    get_supabase_client().table("profiles").upsert(data, on_conflict="user_id").execute()
    return _out(user, _row(user.id), _email(user))


@router.post("/avatar", response_model=ProfileOut)
async def upload_avatar(file: UploadFile = File(...), user: AuthUser = Depends(get_auth_user)):
    data = await file.read()
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Photo must be 2 MB or smaller.")
    mime = sniff_image(data)
    if not mime:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a JPEG, PNG or WebP image.")

    client = get_supabase_client()
    old = (_row(user.id) or {}).get("avatar_path")
    # New key each time so the browser never shows a stale cached photo.
    path = f"{user.id}/avatar-{int(time.time())}.{_EXT[mime]}"
    try:
        client.storage.from_(BUCKET).upload(path, data, {"content-type": mime})
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Could not store the photo. Try again.")
    client.table("profiles").upsert({"user_id": user.id, "avatar_path": path}, on_conflict="user_id").execute()
    if old and old != path:
        try:
            client.storage.from_(BUCKET).remove([old])
        except Exception:
            pass  # orphaned file is harmless
    return _out(user, _row(user.id), _email(user))


@router.delete("/avatar", response_model=ProfileOut)
async def delete_avatar(user: AuthUser = Depends(get_auth_user)):
    client = get_supabase_client()
    old = (_row(user.id) or {}).get("avatar_path")
    if old:
        client.table("profiles").update({"avatar_path": None}).eq("user_id", user.id).execute()
        try:
            client.storage.from_(BUCKET).remove([old])
        except Exception:
            pass
    return _out(user, _row(user.id), _email(user))
