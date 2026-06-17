"""Small FastAPI app with three endpoints. Each endpoint re-implements the
same input-validation logic inline. Refactor target: extract the validation
into a shared helper in a new ``validate.py`` module and update every
callsite to use it. Preserve behaviour.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
    # --- inline validation (block A) ---
    if not req.customer_email or "@" not in req.customer_email:
        raise HTTPException(status_code=400, detail="invalid email")
    if len(req.customer_email) > 254:
        raise HTTPException(status_code=400, detail="email too long")
    if req.quantity is None or req.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if req.quantity > 1000:
        raise HTTPException(status_code=400, detail="quantity exceeds max 1000")
    if not req.sku or not req.sku.strip():
        raise HTTPException(status_code=400, detail="sku is required")
    if len(req.sku) > 32:
        raise HTTPException(status_code=400, detail="sku too long")
    # --- end inline validation ---

    return {"ok": True, "action": "created", "sku": req.sku, "qty": req.quantity}


@app.put("/orders")
def update_order(req: UpdateOrder) -> dict:
    # --- inline validation (block B) ---
    if not req.customer_email or "@" not in req.customer_email:
        raise HTTPException(status_code=400, detail="invalid email")
    if len(req.customer_email) > 254:
        raise HTTPException(status_code=400, detail="email too long")
    if req.quantity is None or req.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if req.quantity > 1000:
        raise HTTPException(status_code=400, detail="quantity exceeds max 1000")
    if not req.sku or not req.sku.strip():
        raise HTTPException(status_code=400, detail="sku is required")
    if len(req.sku) > 32:
        raise HTTPException(status_code=400, detail="sku too long")
    # --- end inline validation ---

    if not req.order_id:
        raise HTTPException(status_code=400, detail="order_id is required")

    return {"ok": True, "action": "updated", "order_id": req.order_id}


@app.post("/orders/cancel")
def cancel_order(req: CancelOrder) -> dict:
    # --- inline validation (block C, email-only subset) ---
    if not req.customer_email or "@" not in req.customer_email:
        raise HTTPException(status_code=400, detail="invalid email")
    if len(req.customer_email) > 254:
        raise HTTPException(status_code=400, detail="email too long")
    # --- end inline validation ---

    if not req.order_id:
        raise HTTPException(status_code=400, detail="order_id is required")

    return {"ok": True, "action": "cancelled", "order_id": req.order_id}
