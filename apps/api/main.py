from dotenv import load_dotenv

load_dotenv()

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import documents, insights, networth, salary, settings, transactions
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
app.include_router(insights.router)
app.include_router(settings.router)
app.include_router(transactions.router)
app.include_router(holdings_router)
app.include_router(loans_router)
app.include_router(epf_nps_router)


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}
