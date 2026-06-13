from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError

from core.auth import get_current_user
from core.supabase import get_supabase_client
from schemas.salary import SalaryCreate, SalaryRecord

router = APIRouter(prefix="/api/v1/salary", tags=["salary"])

_TABLE = "salary_records"


@router.post("/", response_model=SalaryRecord, status_code=status.HTTP_201_CREATED)
async def create_salary_record(
    payload: SalaryCreate,
    user_id: str = Depends(get_current_user),
):
    client = get_supabase_client()
    data = payload.model_dump(exclude_none=True)
    data["user_id"] = user_id
    try:
        response = client.table(_TABLE).insert(data).execute()
    except APIError as exc:
        if exc.code == "23505":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Salary record for {payload.month}/{payload.year} already exists",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return response.data[0]


@router.get("/", response_model=list[SalaryRecord])
async def list_salary_records(user_id: str = Depends(get_current_user)):
    client = get_supabase_client()
    response = (
        client.table(_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .order("year", desc=True)
        .order("month", desc=True)
        .execute()
    )
    return response.data


@router.get("/{record_id}", response_model=SalaryRecord)
async def get_salary_record(
    record_id: str,
    user_id: str = Depends(get_current_user),
):
    client = get_supabase_client()
    response = (
        client.table(_TABLE)
        .select("*")
        .eq("id", record_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if response.data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return response.data


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_salary_record(
    record_id: str,
    user_id: str = Depends(get_current_user),
):
    client = get_supabase_client()
    response = (
        client.table(_TABLE)
        .delete()
        .eq("id", record_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
