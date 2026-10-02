from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from main.package.ai.common import build_prompt_environment
from main.package.mail import Mailer, MailMessage
from main.package.service.contact.dto import ContactReceipt, ContactSubmission
from main.package.service.contact.email_address import EmailNormalizer
from main.package.service.contact.exceptions import InvalidContactSettingError, InvalidContactSubmissionError

_TEMPLATE = build_prompt_environment(Path(__file__).with_name("templates")).get_template("contact.md")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ContactService:
    def __init__(
        self,
        *,
        mailer: Mailer,
        email_normalizer: EmailNormalizer,
        subject_prefix: str,
        max_subject_chars: int,
        max_message_chars: int,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(mailer, Mailer):
            raise InvalidContactSettingError("mailer must be a Mailer")
        if not isinstance(email_normalizer, EmailNormalizer):
            raise InvalidContactSettingError("email_normalizer must be an EmailNormalizer")
        if not isinstance(subject_prefix, str) or not subject_prefix.strip() or "\n" in subject_prefix or "\r" in subject_prefix:
            raise InvalidContactSettingError("subject_prefix must be a non-blank single line")

        self._mailer = mailer
        self._email_normalizer = email_normalizer
        self._subject_prefix = subject_prefix.strip()
        self._max_subject_chars = self._require_positive("max_subject_chars", max_subject_chars)
        self._max_message_chars = self._require_positive("max_message_chars", max_message_chars)
        self._clock = clock

    @property
    def max_subject_chars(self) -> int:
        return self._max_subject_chars

    @property
    def max_message_chars(self) -> int:
        return self._max_message_chars

    def submit(self, submission: ContactSubmission) -> ContactReceipt:
        if not isinstance(submission, ContactSubmission):
            raise TypeError("submission must be a ContactSubmission")

        email = self._email_normalizer.normalize(submission.email)
        subject = self._validated_subject(submission.subject)
        message = self._validated_message(submission.message)
        submitted_at = self._clock()

        body = _TEMPLATE.render(
            email=email,
            subject=subject,
            message=message,
            submitted_at=submitted_at.isoformat(timespec="seconds"),
            client_ip=submission.client_ip,
        )
        self._mailer.send(
            MailMessage(subject=f"{self._subject_prefix} {subject}", text_body=body, reply_to=email)
        )
        return ContactReceipt(reply_to=email, sent_at=submitted_at)

    def _validated_subject(self, value: str) -> str:
        subject = value.strip()
        if not subject:
            raise InvalidContactSubmissionError("subject must not be empty", field="subject")
        if "\n" in subject or "\r" in subject:
            raise InvalidContactSubmissionError("subject must be a single line", field="subject")
        if len(subject) > self._max_subject_chars:
            raise InvalidContactSubmissionError(
                f"subject must be at most {self._max_subject_chars} characters", field="subject"
            )
        return subject

    def _validated_message(self, value: str) -> str:
        message = value.strip()
        if not message:
            raise InvalidContactSubmissionError("message must not be empty", field="message")
        if len(message) > self._max_message_chars:
            raise InvalidContactSubmissionError(
                f"message must be at most {self._max_message_chars} characters", field="message"
            )
        return message

    @staticmethod
    def _require_positive(name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidContactSettingError(f"{name} must be a positive int")
        return value
