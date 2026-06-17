"""Shared validation helpers for the orders API.

Every endpoint that accepts an email / quantity / sku delegates here so the
rules stay in one place. The helpers raise ``HTTPException(400)`` directly
— they replace inline ``if ...: raise HTTPException`` blocks in the route
handlers, so the call-site remains a single function call.
"""

from __future__ import annotations

from fastapi import HTTPException

MAX_EMAIL_LEN = 254
MAX_QUANTITY = 1000
MAX_SKU_LEN = 32


def validate_email(email: str) -> None:
    """Raise HTTPException(400) if *email* is missing, malformed, or too long."""
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="invalid email")
    if len(email) > MAX_EMAIL_LEN:
        raise HTTPException(status_code=400, detail="email too long")


def validate_quantity(quantity: int) -> None:
    """Raise HTTPException(400) if *quantity* is not in ``(0, MAX_QUANTITY]``."""
    if quantity is None or quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if quantity > MAX_QUANTITY:
        raise HTTPException(
            status_code=400, detail=f"quantity exceeds max {MAX_QUANTITY}"
        )


def validate_sku(sku: str) -> None:
    """Raise HTTPException(400) if *sku* is missing, blank, or too long."""
    if not sku or not sku.strip():
        raise HTTPException(status_code=400, detail="sku is required")
    if len(sku) > MAX_SKU_LEN:
        raise HTTPException(status_code=400, detail="sku too long")


def validate_order_payload(*, email: str, quantity: int, sku: str) -> None:
    """Validate the full order payload (email + quantity + sku)."""
    validate_email(email)
    validate_quantity(quantity)
    validate_sku(sku)
