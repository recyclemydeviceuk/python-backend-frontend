from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime


class FeedLog(Document):
    endpoint: str
    source_ip: str
    user_agent: Optional[str] = None
    partner_name: Optional[str] = None
    rows_returned: int = 0
    query_params: Optional[str] = None
    response_time_ms: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "feed_logs"
        indexes = [
            [("created_at", -1)],
            "partner_name",
            "endpoint",
            "source_ip"
        ]
