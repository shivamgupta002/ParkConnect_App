from fastapi import APIRouter, Depends, HTTPException, Query
from beanie import PydanticObjectId

from app.core.deps import get_current_user
from app.models.user import User
from app.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    notifications = (
        await Notification.find(Notification.user.id == current_user.id)
        .sort(-Notification.created_at)
        .skip(skip)
        .limit(limit)
        .to_list()
    )
    return notifications


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: PydanticObjectId,
    current_user: User = Depends(get_current_user),
):
    notification = await Notification.get(notification_id, fetch_links=True)

    # Ownership check: 404 whether it's missing or belongs to someone else,
    # same "don't leak existence" pattern used elsewhere (e.g. Phase 3 vehicles).
    if notification is None or notification.user.id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await notification.save()
    return notification