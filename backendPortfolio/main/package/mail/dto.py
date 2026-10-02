from datetime import datetime
from email.utils import parseaddr
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, ValidationError

from main.package.mail.exceptions import InvalidMailMessageError

_LINE_BREAKS = ("\r", "\n")


def _require_single_line(value: str) -> str:
    if any(character in value for character in _LINE_BREAKS):
        raise ValueError("must not contain line breaks")

    return value


def require_address(value: str) -> str:
    _require_single_line(value)
    name, address = parseaddr(value)
    local, _, domain = address.rpartition("@")
    if name or address != value.strip() or not local or "." not in domain or " " in address:
        raise ValueError("must be a plain email address like name@example.com")

    return address


def _require_text(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")

    return value


EmailAddress = Annotated[str, AfterValidator(require_address)]
SingleLine = Annotated[str, AfterValidator(_require_single_line), AfterValidator(_require_text)]
Text = Annotated[str, AfterValidator(_require_text)]


class SmtpSecurity(StrEnum):
    STARTTLS = "starttls"
    SSL = "ssl"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SmtpAccount(_FrozenModel):
    host: Annotated[str, Field(min_length=1)]
    port: Annotated[int, Field(strict=True, ge=1, le=65535)]
    security: SmtpSecurity
    username: EmailAddress
    password: SecretStr

    @property
    def domain(self) -> str:
        return self.username.rpartition("@")[2]


class MailMessage(_FrozenModel):
    subject: SingleLine
    text_body: Text
    html_body: Text | None = None
    reply_to: EmailAddress | None = None

    @classmethod
    def create(cls, **fields: Any) -> Self:
        try:
            return cls(**fields)
        except ValidationError as error:
            raise InvalidMailMessageError(f"Invalid mail message: {error.error_count()} problem(s)") from error


class MailReceipt(_FrozenModel):
    message_id: str
    account: str
    recipient: str
    sent_at: datetime
