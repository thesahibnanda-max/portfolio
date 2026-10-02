from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ContactSubmission(_FrozenModel):
    email: str
    subject: str
    message: str
    client_ip: str | None = None


class ContactReceipt(_FrozenModel):
    reply_to: str
    sent_at: datetime
