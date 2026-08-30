import pytest
from unittest.mock import patch, MagicMock

from app.services.notification_service import notify
from app.models.notification import Notification


@pytest.mark.asyncio
async def test_notify_creates_doc_even_if_sms_fails(test_user):
    """
    A completed-call notification must still produce a notifications doc,
    and the email channel must still be attempted, even if SMS throws.
    """
    with patch(
        "app.services.notification_service.send_sms",
        side_effect=Exception("Twilio down"),
    ) as mock_sms, patch(
        "app.services.notification_service.send_email"
    ) as mock_email, patch(
        "app.services.notification_service.send_push"
    ) as mock_push:

        result = await notify(
            test_user,
            "call_completed",
            "Your vehicle was scanned and called",
            "Duration: 42s",
        )

        assert result.id is not None
        assert result.type == "call_completed"

        doc = await Notification.get(result.id)
        assert doc is not None
        assert doc.title == "Your vehicle was scanned and called"

        mock_sms.assert_called_once()
        mock_email.assert_called_once()  # not blocked by the SMS exception
        mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_get_notifications_only_returns_own(client, test_user, other_user, auth_headers):
    other_notification = Notification(
        user=other_user, type="scan", title="X", message="Y", is_read=False
    )
    await other_notification.insert()

    own_notification = Notification(
        user=test_user, type="scan", title="Owned", message="Y", is_read=False
    )
    await own_notification.insert()

    response = await client.get("/notifications", headers=auth_headers)
    assert response.status_code == 200
    ids = [n["id"] for n in response.json()]
    assert str(own_notification.id) in ids
    assert str(other_notification.id) not in ids


@pytest.mark.asyncio
async def test_mark_read_rejected_for_other_users_notification(
    client, other_user, auth_headers
):
    other_notification = Notification(
        user=other_user, type="scan", title="X", message="Y", is_read=False
    )
    await other_notification.insert()

    response = await client.patch(
        f"/notifications/{other_notification.id}/read", headers=auth_headers
    )
    assert response.status_code == 404