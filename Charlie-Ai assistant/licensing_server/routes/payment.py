"""
licensing_server/routes/payment.py — Payment webhook handler and checkout endpoints.

Payment verification is SERVER-SIDE ONLY. Desktop cannot fake payment status.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from licensing_server.database import UserDB, get_db
from licensing_server.middleware.auth_middleware import get_current_user
from licensing_server.services.payment_service import PaymentService

router = APIRouter(prefix="/payment", tags=["Payment"])
payment_service = PaymentService()


class CreateOrderRequest(BaseModel):
    plan: str
    amount_paise: int | None = None


class VerifyPaymentRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str
    plan: str


@router.get("/plan-registry")
def plan_registry():
    """Authoritative public plan catalog with pricing, billing intervals, and feature flags."""
    return {"success": True, "data": payment_service.get_plan_registry()}


@router.post("/create-order")
def create_order(
    req: CreateOrderRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate secure checkout with server-side price authority."""
    ok, msg, data = payment_service.create_order(db, str(user.id), req.plan, req.amount_paise)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg, "data": data}



@router.post("/verify")
def verify_payment(
    req: VerifyPaymentRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify Razorpay payment signature and activate subscription."""
    verified = payment_service.verify_razorpay_signature(req.order_id, req.payment_id, req.signature)
    if not verified:
        return {"success": False, "error": "Payment verification failed."}

    # Authoritative database lookup prevents plan tier forgery
    from licensing_server.database import PaymentDB
    payment = db.query(PaymentDB).filter(
        PaymentDB.order_id == req.order_id,
        PaymentDB.user_id == user.id,
    ).first()
    if not payment:
        return {"success": False, "error": "Order not found or unauthorized."}

    user_id_str = str(getattr(user, "id", ""))
    plan_str = str(getattr(payment, "plan", ""))
    amount_paise_val = int(getattr(payment, "amount_paise", 0))

    ok, msg = payment_service.activate_subscription(
        db, user_id_str, plan_str, req.order_id, req.payment_id, amount_paise_val
    )
    return {"success": ok, "message": msg}


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Razorpay webhook endpoint. No JWT required — authenticated via webhook signature."""
    body = await request.body()
    ok, data = payment_service.verify_razorpay_webhook(body, x_razorpay_signature)
    if not ok:
        return {"success": False, "error": data.get("error", "Webhook verification failed.")}

    # Process webhook event
    event_type = data.get("event", "")
    if event_type == "payment.captured":
        payload = data.get("payload", {}).get("payment", {}).get("entity", {})
        notes = payload.get("notes", {})
        user_id = notes.get("user_id")
        plan = notes.get("plan")
        if user_id and plan:
            payment_service.activate_subscription(
                db, user_id, plan,
                payload.get("order_id", ""),
                payload.get("id", ""),
                payload.get("amount", 0),
            )

    return {"success": True, "message": "Webhook processed."}


class DeductCreditRequest(BaseModel):
    feature: str
    model: str | None = None
    provider: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@router.get("/wallet")
def get_wallet(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve user's authoritative AI credit balance and billing cycle."""
    from licensing_server.services.credit_service import CreditService
    credit_service = CreditService()
    wallet = credit_service.get_or_create_wallet(db, str(user.id))
    return {
        "success": True,
        "data": {
            "plan_tier": wallet.plan_tier,
            "subscription_credits": wallet.subscription_credits,
            "purchased_credits": wallet.purchased_credits,
            "total_credits": (wallet.subscription_credits or 0) + (wallet.purchased_credits or 0),
            "credits_used": wallet.credits_used,
            "daily_messages_used": wallet.daily_messages_used,
            "billing_cycle_start": wallet.billing_cycle_start.isoformat() if wallet.billing_cycle_start else None,
            "billing_cycle_end": wallet.billing_cycle_end.isoformat() if wallet.billing_cycle_end else None,
        }
    }


@router.post("/deduct-credit")
def deduct_credit(
    req: DeductCreditRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authoritative server-side credit deduction for AI operations."""
    from licensing_server.services.credit_service import CreditService
    credit_service = CreditService()
    ok, msg, cost = credit_service.deduct_credits(
        db,
        str(user.id),
        req.feature,
        req.model,
        req.provider,
        req.input_tokens,
        req.output_tokens,
    )
    return {"success": ok, "message": msg, "credits_deducted": cost}
