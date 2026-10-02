from collections.abc import Sequence


class MailError(Exception):
    pass


class InvalidMailSettingError(MailError):
    pass


class InvalidMailMessageError(MailError):
    pass


class MailRecipientRejectedError(MailError):
    def __init__(self, message: str, *, recipient: str) -> None:
        super().__init__(message)
        self.recipient = recipient


class MailDeliveryError(MailError):
    def __init__(self, message: str, *, attempts: Sequence[tuple[str, str]]) -> None:
        super().__init__(message)
        self.attempts = tuple(attempts)
