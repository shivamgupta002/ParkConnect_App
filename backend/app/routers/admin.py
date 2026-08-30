"""
Admin panel API. Every endpoint here requires get_current_admin.

Note on GET /admin/vehicles: this is the one place in the entire codebase
where owner-vehicle linkage (owner email alongside vehicle details) is
intentionally exposed via the API. That's fine HERE because this is an
internal admin tool behind get_current_admin, not a publicly reachable
endpoint. Do NOT copy this pattern into any scanner-facing or otherwise
public route — the privacy boundary established in Phase 4's
GET /vehicle/{token} (no owner info, ever) is deliberate and must stay that
way. This admin endpoint is the exception, not a precedent.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from beanie import PydanticObjectId
from beanie.operators import Or, RegEx

from app.core.deps import get_current_admin
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.qr_code import QRCode
from app.models.call import Call
from app.models.report import Report
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.audit_log import AuditLog
from app.schemas.admin import RenewSubscriptionRequest, SuspendUserRequest
from app.services import razorpay_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(get_current_admin),
):
    query = User.find_all()
    if search:
        pattern = re.escape(search)
        query = User.find(
            Or(
                RegEx(User.email, pattern, options="i"),
                RegEx(User.full_name, pattern, options="i"),
                RegEx(User.phone_number, pattern, options="i"),
            )
        )

    users = await query.skip(skip).limit(limit).sort(-User.created_at).to_list()

    results = []
    for user in users:
        subscription = await Subscription.find_one(Subscription.user.id == user.id)
        results.append(
            {
                "id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "phone_number": user.phone_number,
                "is_verified": user.is_verified,
                "is_premium": user.is_premium,
                "is_suspended": user.is_suspended,
                "created_at": user.created_at,
                "subscription_status": subscription.status if subscription else None,
                "subscription_plan": subscription.plan if subscription else None,
            }
        )
    return results


@router.patch("/users/{user_id}/suspend")
async def suspend_user(
    user_id: PydanticObjectId,
    payload: SuspendUserRequest,
    current_admin: User = Depends(get_current_admin),
):
    user = await User.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_suspended = payload.suspended
    await user.save()

    audit_entry = AuditLog(
        admin_user=current_admin,
        action="suspend_user" if payload.suspended else "unsuspend_user",
        target_type="user",
        target_id=str(user.id),
        meta={"suspended": payload.suspended},
    )
    await audit_entry.insert()

    return {"id": str(user.id), "is_suspended": user.is_suspended}


@router.patch("/users/{user_id}/renew-subscription")
async def renew_user_subscription(
    user_id: PydanticObjectId,
    payload: RenewSubscriptionRequest,
    current_admin: User = Depends(get_current_admin),
):
    """
    Admin override to manually renew/grant a user's subscription — e.g. to
    fix a missed/failed Razorpay webhook, extend a trial, or comp an
    account, without the user going through checkout again. Every use is
    written to audit_logs since this directly grants paid access.
    """
    if payload.plan not in ("free", "premium"):
        raise HTTPException(status_code=400, detail="plan must be 'free' or 'premium'")

    user = await User.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)
    subscription = await Subscription.find_one(Subscription.user.id == user.id, fetch_links=False)

    if payload.plan == "premium":
        end_date = now + timedelta(days=payload.days)
        if subscription is None:
            subscription = Subscription(
                user=user, plan="premium", status="active", start_date=now, end_date=end_date
            )
        else:
            subscription.plan = "premium"
            subscription.status = "active"
            subscription.start_date = now
            subscription.end_date = end_date
        await subscription.save()
        # Reuse the same "clear expiry on this user's active QR codes" logic
        # the Razorpay webhook uses on a real payment — an admin-granted
        # premium renewal should behave identically to a paid one.
        await razorpay_service.reactivate_qr_codes_for_user(user)
    else:
        if subscription is None:
            subscription = Subscription(user=user, plan="free", status="active", start_date=now)
        else:
            subscription.plan = "free"
            subscription.status = "active"
        await subscription.save()
        await razorpay_service.deactivate_qr_codes_for_user(user)

    audit_entry = AuditLog(
        admin_user=current_admin,
        action="renew_subscription",
        target_type="user",
        target_id=str(user.id),
        meta={
            "plan": payload.plan,
            "days": payload.days if payload.plan == "premium" else None,
            "reason": payload.reason,
            "new_end_date": subscription.end_date.isoformat() if subscription.end_date else None,
        },
    )
    await audit_entry.insert()

    return {
        "id": str(user.id),
        "plan": subscription.plan,
        "status": subscription.status,
        "start_date": subscription.start_date,
        "end_date": subscription.end_date,
    }


@router.get("/vehicles")
async def list_vehicles(
    is_active: Optional[bool] = Query(None),
    vehicle_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(get_current_admin),
):
    filters = {}
    if is_active is not None:
        filters["is_active"] = is_active
    if vehicle_type is not None:
        filters["vehicle_type"] = vehicle_type

    query = Vehicle.find(filters) if filters else Vehicle.find_all()
    vehicles = await query.skip(skip).limit(limit).sort(-Vehicle.created_at).to_list()

    results = []
    for vehicle in vehicles:
        owner = await User.get(vehicle.owner.ref.id)
        results.append(
            {
                "id": str(vehicle.id),
                "vehicle_type": vehicle.vehicle_type,
                "vehicle_number": vehicle.vehicle_number,
                "brand": vehicle.brand,
                "model": vehicle.model,
                "color": vehicle.color,
                "is_active": vehicle.is_active,
                "created_at": vehicle.created_at,
                # Intentional admin-only exposure — see module docstring above.
                "owner_email": owner.email if owner else None,
            }
        )
    return results


@router.get("/analytics")
async def get_analytics(current_admin: User = Depends(get_current_admin)):
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = await User.find_all().count()
    total_vehicles = await Vehicle.find(Vehicle.is_active == True).count()  # noqa: E712
    total_calls = await Call.find_all().count()
    calls_last_30_days = await Call.find(Call.created_at >= thirty_days_ago).count()
    total_reports_open = await Report.find(Report.status == "open").count()
    premium_subscriber_count = await Subscription.find(
        Subscription.plan == "premium", Subscription.status == "active"
    ).count()

    # total_scans: sum of qr_codes.scan_count via aggregation, not Python-side sum
    scan_agg = await QRCode.aggregate(
        [{"$group": {"_id": None, "total": {"$sum": "$scan_count"}}}]
    ).to_list()
    total_scans = scan_agg[0]["total"] if scan_agg else 0

    revenue_agg = await Payment.aggregate(
        [
            {
                "$match": {
                    "status": "paid",
                    "created_at": {"$gte": month_start},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
    ).to_list()
    revenue_this_month = revenue_agg[0]["total"] if revenue_agg else 0

    return {
        "total_users": total_users,
        "total_vehicles": total_vehicles,
        "total_scans": total_scans,
        "total_calls": total_calls,
        "calls_last_30_days": calls_last_30_days,
        "total_reports_open": total_reports_open,
        "premium_subscriber_count": premium_subscriber_count,
        "revenue_this_month": revenue_this_month,
    }


@router.get("/audit-logs")
async def list_audit_logs(
    admin_user: Optional[PydanticObjectId] = Query(None),
    target_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(get_current_admin),
):
    filters = {}
    if target_type is not None:
        filters["target_type"] = target_type

    query = AuditLog.find(filters) if filters else AuditLog.find_all()
    if admin_user is not None:
        query = query.find(AuditLog.admin_user.id == admin_user)

    logs = await query.sort(-AuditLog.created_at).skip(skip).limit(limit).to_list()
    return logs
