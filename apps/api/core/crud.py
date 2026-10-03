# NOTE: no `from __future__ import annotations` here. The handlers below are annotated with
# schema classes held in closure variables; FastAPI can only resolve those if annotations are real objects.

from typing import Type

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel

from core.auth import get_current_user
from core.supabase import get_supabase_client


def make_crud_router(
    *,
    prefix: str,
    tag: str,
    table: str,
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    read_schema: Type[BaseModel],
    order_by: str = "created_at",
) -> APIRouter:
    """Per-user CRUD router. The service-role client bypasses RLS, so every
    query is scoped by user_id here."""
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("", response_model=list[read_schema])  # type: ignore[valid-type]
    async def list_items(user_id: str = Depends(get_current_user)):
        res = (
            get_supabase_client()
            .table(table)
            .select("*")
            .eq("user_id", user_id)
            .order(order_by, desc=True)
            .execute()
        )
        return res.data

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)  # type: ignore[valid-type]
    async def create_item(payload: create_schema, user_id: str = Depends(get_current_user)):  # type: ignore[valid-type]
        data = payload.model_dump(exclude_none=True, mode="json")
        data["user_id"] = user_id
        try:
            res = get_supabase_client().table(table).insert(data).execute()
        except APIError as exc:
            if exc.code == "23505":
                raise HTTPException(status.HTTP_409_CONFLICT, detail="That entry already exists.")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message)
        return res.data[0]

    @router.patch("/{item_id}", response_model=read_schema)  # type: ignore[valid-type]
    async def update_item(
        item_id: str,
        payload: update_schema,  # type: ignore[valid-type]
        user_id: str = Depends(get_current_user),
    ):
        data = payload.model_dump(exclude_unset=True, mode="json")
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No fields to update")
        try:
            res = (
                get_supabase_client()
                .table(table)
                .update(data)
                .eq("id", item_id)
                .eq("user_id", user_id)
                .execute()
            )
        except APIError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.message)
        if not res.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Record not found")
        return res.data[0]

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_item(item_id: str, user_id: str = Depends(get_current_user)):
        res = (
            get_supabase_client()
            .table(table)
            .delete()
            .eq("id", item_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Record not found")

    return router
