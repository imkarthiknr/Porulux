from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import defaultdict, deque
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth import AuthUser, get_auth_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

KIND_LABELS = {"issue": "bug", "idea": "enhancement", "question": "question"}
KIND_TITLES = {"issue": "Issue", "idea": "Idea", "question": "Question"}

# Per-process limit; enough to stop a single user spamming the repo with issues.
_MAX_PER_HOUR = 5
_recent: dict[str, deque[float]] = defaultdict(deque)


class FeedbackIn(BaseModel):
    kind: Literal["issue", "idea", "question"]
    message: str = Field(..., min_length=10, max_length=4000)
    page: str | None = Field(None, max_length=200)


class FeedbackOut(BaseModel):
    ok: bool
    issue_number: int


def _rate_limit(user_id: str) -> None:
    now = time.monotonic()
    q = _recent[user_id]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= _MAX_PER_HOUR:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You've sent a lot of feedback in the last hour. Please try again later.")
    q.append(now)


def _title(kind: str, message: str) -> str:
    first = " ".join(message.split())
    first = first if len(first) <= 70 else first[:67].rstrip() + "..."
    return f"[{KIND_TITLES[kind]}] {first}"


def _body(user: AuthUser, payload: FeedbackIn) -> str:
    # The repo may be public, so identify the user by a short one-way hash, never email or raw id.
    ref = hashlib.sha256(user.id.encode()).hexdigest()[:10]
    lines = [payload.message.strip(), "", "---", f"Submitted from the portal by user `{ref}`."]
    if payload.page:
        lines.append(f"Page: `{payload.page}`")
    return "\n".join(lines)


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_feedback(payload: FeedbackIn, user: AuthUser = Depends(get_auth_user)):
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")  # "owner/name"
    if not token or not repo:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Feedback isn't set up yet.")
    _rate_limit(user.id)

    body = {
        "title": _title(payload.kind, payload.message),
        "body": _body(user, payload),
        "labels": ["customer-feedback", KIND_LABELS[payload.kind]],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"https://api.github.com/repos/{repo}/issues",
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
    except httpx.HTTPError:
        logger.exception("GitHub issue creation failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Couldn't send your feedback right now. Please try again.")
    if res.status_code != 201:
        logger.error("GitHub returned %s: %s", res.status_code, res.text[:300])
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Couldn't send your feedback right now. Please try again.")
    return FeedbackOut(ok=True, issue_number=res.json()["number"])
