from dotenv import load_dotenv

load_dotenv()

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from services.ai import PROVIDER_LABELS, AIKeyError, AIQuotaError
from routers import cards, documents, holdings_import, insights, networth, profile, salary, settings, transactions
from routers.bank_accounts import accounts_crud
from routers.bank_accounts import router as bank_accounts_router
from routers.portfolio import epf_nps_router, holdings_router, loans_router

app = FastAPI(title="Porulux API", version="0.1.0", redirect_slashes=False)


class StripTrailingSlash:
    """Treat /x/ and /x as the same route. Proxies (Next rewrites) may drop the slash, and a
    redirect from here would point the browser at this service's internal host."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and len(scope["path"]) > 1 and scope["path"].endswith("/"):
            scope = {**scope, "path": scope["path"].rstrip("/"), "raw_path": scope.get("raw_path", b"").rstrip(b"/")}
        await self.inner(scope, receive, send)


app.add_middleware(StripTrailingSlash)

_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(salary.router)
app.include_router(networth.router)
app.include_router(documents.router)
def _wait_text(seconds: int | None) -> str:
    if not seconds:
        return "a while"
    h, m = divmod(seconds // 60, 60)
    return f"about {h}h {m}m" if h else f"about {max(m, 1)} min"


@app.exception_handler(AIQuotaError)
async def ai_quota_handler(_: Request, exc: AIQuotaError):
    who = PROVIDER_LABELS.get(exc.provider, exc.provider)
    if exc.shared:
        detail = (
            f"AI_QUOTA: The shared {who} allowance for today is used up (it resets in {_wait_text(exc.retry_seconds)}). "
            "To keep going now, add your own free key in Settings."
        )
    else:
        detail = (
            f"AI_QUOTA: Your {who} key has hit its rate or daily limit (resets in {_wait_text(exc.retry_seconds)}). "
            "Wait, or check the plan and billing for that key."
        )
    return JSONResponse(status_code=429, content={"detail": detail})


@app.exception_handler(AIKeyError)
async def ai_key_handler(_: Request, exc: AIKeyError):
    who = PROVIDER_LABELS.get(exc.provider, exc.provider)
    return JSONResponse(status_code=402, content={"detail": f"AI_KEY_INVALID: Your saved {who} API key was rejected. Check or replace it in Settings."})


app.include_router(profile.router)
app.include_router(bank_accounts_router)
app.include_router(accounts_crud)
app.include_router(cards.router)
app.include_router(cards.cards_crud)
app.include_router(holdings_import.router)
app.include_router(insights.router)
app.include_router(settings.router)
app.include_router(transactions.router)
app.include_router(holdings_router)
app.include_router(loans_router)
app.include_router(epf_nps_router)


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}
