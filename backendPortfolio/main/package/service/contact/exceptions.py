class ContactError(Exception):
    pass


class InvalidContactSettingError(ContactError):
    pass


class InvalidContactSubmissionError(ContactError):
    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.field = field
