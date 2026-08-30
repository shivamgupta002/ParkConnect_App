"""
Beanie Document models, re-exported here so other modules (database.py,
routers, tests) can do `from app.models import User, Vehicle, ...` without
worrying about the internal circular-import resolution between Vehicle and
QRCode.

Import order matters: user -> vehicle (imports user) -> qr_code (imports
vehicle, then vehicle.py rebuilds itself against qr_code at the bottom of
vehicle.py). Everything else is a straightforward one-way dependency.
"""
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.qr_code import QRCode
from app.models.call import Call
from app.models.report import Report
from app.models.notification import Notification
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.audit_log import AuditLog

__all__ = [
    "User",
    "Vehicle",
    "QRCode",
    "Call",
    "Report",
    "Notification",
    "Subscription",
    "Payment",
    "AuditLog",
]
