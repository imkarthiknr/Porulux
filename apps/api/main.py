from dotenv import load_dotenv

load_dotenv()

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import documents, networth, salary, transactions
from routers.portfolio import epf_nps_router, holdings_router, loans_router

app = FastAPI(title="Porulux API", version="0.1.0")

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
app.include_router(transactions.router)
app.include_router(holdings_router)
app.include_router(loans_router)
app.include_router(epf_nps_router)


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}
