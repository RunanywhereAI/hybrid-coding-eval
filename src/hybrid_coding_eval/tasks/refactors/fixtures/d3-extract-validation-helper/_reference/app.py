"""Orders API — validation duplication removed.

Every route now delegates to :mod:`validate`, which owns the canonical
rules for email / quantity / sku.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from validate import validate_email, validate_order_payload

app = FastAPI()


class CreateOrder(BaseModel):
    customer_email: str
    quantity: int
    sku: str


class UpdateOrder(BaseModel):
    order_id: str
    quantity: int
    customer_email: str
    sku: str


class CancelOrder(BaseModel):
    order_id: str
    customer_email: str


@app.post("/orders")
def create_order(req: CreateOrder) -> dict:
    validate_order_payload(
        email=req.customer_email, quantity=req.quantity, sku=req.sku
    )
    return {"ok": True, "action": "created", "sku": req.sku, "qty": req.quantity}


@app.put("/orders")
def update_order(req: UpdateOrder) -> dict:
    validate_order_payload(
        email=req.customer_email, quantity=req.quantity, sku=req.sku
    )
    if not req.order_id:
        raise HTTPException(status_code=400, detail="order_id is required")
    return {"ok": True, "action": "updated", "order_id": req.order_id}


@app.post("/orders/cancel")
def cancel_order(req: CancelOrder) -> dict:
    validate_email(req.customer_email)
    if not req.order_id:
        raise HTTPException(status_code=400, detail="order_id is required")
    return {"ok": True, "action": "cancelled", "order_id": req.order_id}
