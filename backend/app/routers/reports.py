"""
Vehicle reports — the "Report an issue" flow reachable from the public scan
page (no auth), plus admin-only review endpoints.

Notification channel policy (per report_type):
- "accident" / "emergency": push + sms + email, urgent tone. These are the
  two categories where a delay in reaching the owner could matter physically
  (car rolling, fire risk, injury) — every channel gets used.
- everything else ("wrong_parking", "lights_on", "other"): push + email only.
  SMS is deliberately skipped for these — they're real but not urgent, and an
  owner getting a text every time someone reports their lights are on is the
  kind of over-notification that makes people disable notifications entirely,
  which then also numbs them to the accident/emergency ones. Push + email is
  enough to surface it without training the owner to ignore their phone.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from beanie import PydanticObjectId
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.deps import get_current_admin
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.qr_code import QRCode
from app.models.report import Report
from app.models.audit_log import AuditLog
from app.schemas.report import ReportCreate, ReportStatusUpdate
from app.services.notification_service import notify

router = APIRouter(tags=["reports"])
limiter = Limiter(key_func=get_remote_address)

URGENT_TYPES = {"accident", "emergency"}


@router.post("/reports")
@limiter.limit("10/hour")
async def create_report(
    request: Request,
    payload: ReportCreate,
    background_tasks: BackgroundTasks,
):
    # Same generic-404 rule as /vehicle/{token} and /calls/initiate — don't
    # distinguish "no such token" from "inactive"/"expired" for a public caller.
    qr = await QRCode.find_one(QRCode.token == payload.token)
    if qr is None or not qr.is_active:
        raise HTTPException(status_code=404, detail="This QR code is no longer active")

    vehicle = await Vehicle.get(qr.vehicle.ref.id)
    if vehicle is None or not vehicle.is_active:
        raise HTTPException(status_code=404, detail="This QR code is no longer active")

    owner = await User.get(vehicle.owner.ref.id)

    report = Report(
        vehicle=vehicle,
        report_type=payload.report_type,
        message=payload.message,
        reporter_contact=payload.reporter_contact,
        status="open",
    )
    await report.insert()

    if payload.report_type in URGENT_TYPES:
        background_tasks.add_task(
            notify,
            owner,
            "report",
            "Urgent: an issue was reported about your vehicle",
            f"{payload.report_type.replace('_', ' ').title()} reported: {payload.message}",
            ["push", "sms", "email"],
        )
    else:
        background_tasks.add_task(
            notify,
            owner,
            "report",
            "An issue was reported about your vehicle",
            f"{payload.report_type.replace('_', ' ').title()}: {payload.message}",
            ["push", "email"],
        )

    return {"status": "submitted", "report_id": str(report.id)}


@router.get("/reports")
async def list_reports(
    status: str | None = Query(None),
    vehicle_id: PydanticObjectId | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: User = Depends(get_current_admin),
):
    query_filters = {}
    if status is not None:
        query_filters["status"] = status

    find_query = Report.find(query_filters) if query_filters else Report.find_all()

    if vehicle_id is not None:
        find_query = find_query.find(Report.vehicle.id == vehicle_id)

    reports = (
        await find_query.sort(-Report.created_at).skip(skip).limit(limit).to_list()
    )
    return reports


@router.patch("/reports/{report_id}")
async def update_report_status(
    report_id: PydanticObjectId,
    payload: ReportStatusUpdate,
    current_admin: User = Depends(get_current_admin),
):
    report = await Report.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = payload.status
    await report.save()

    audit_entry = AuditLog(
        admin_user=current_admin,
        action="update_report_status",
        target_type="report",
        target_id=str(report.id),
        meta={"new_status": payload.status},
    )
    await audit_entry.insert()

    return report