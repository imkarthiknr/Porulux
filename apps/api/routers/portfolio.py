from core.crud import make_crud_router
from schemas.epf_nps import EpfNps, EpfNpsCreate, EpfNpsUpdate
from schemas.holdings import Holding, HoldingCreate, HoldingUpdate
from schemas.loans import Loan, LoanCreate, LoanUpdate

holdings_router = make_crud_router(
    prefix="/api/v1/holdings", tag="holdings", table="holdings",
    create_schema=HoldingCreate, update_schema=HoldingUpdate, read_schema=Holding,
)
loans_router = make_crud_router(
    prefix="/api/v1/loans", tag="loans", table="loans",
    create_schema=LoanCreate, update_schema=LoanUpdate, read_schema=Loan,
)
epf_nps_router = make_crud_router(
    prefix="/api/v1/epf-nps", tag="epf-nps", table="epf_nps_balances",
    create_schema=EpfNpsCreate, update_schema=EpfNpsUpdate, read_schema=EpfNps,
)
