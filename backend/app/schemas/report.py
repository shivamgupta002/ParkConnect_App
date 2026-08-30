from typing import Literal, Optional
from pydantic import BaseModel, Field

ReportType = Literal["wrong_parking", "lights_on", "accident", "emergency", "other"]
ReportStatus = Literal["open", "reviewed", "resolved"]


class ReportCreate(BaseModel):
    token: str
    report_type: ReportType
    message: str = Field(..., min_length=1, max_length=1000)
    reporter_contact: Optional[str] = None


class ReportStatusUpdate(BaseModel):
    status: Literal["reviewed", "resolved"]