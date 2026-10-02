import email
import email.policy
import random
from datetime import UTC, datetime, timedelta

import pytest

from main.package.mail import MailDeliveryError, Mailer
from main.package.service.contact import (
    ContactError,
    ContactReceipt,
    ContactService,
    ContactSubmission,
    EmailNormalizer,
    InvalidContactSettingError,
    InvalidContactSubmissionError,
)
from tests.main.package.mail.fakes import FakeConnector, account
from tests.main.package.service.contact.fakes import MISSING_DOMAIN, FakeResolver

NOW = datetime(2026, 10, 2, 9, 30, tzinfo=UTC)
OWNER = "owner@example.com"


def _clock() -> datetime:
    return NOW


def _mailer(connector: FakeConnector) -> Mailer:
    return Mailer(
        accounts=[account(1), account(2)],
        recipient=OWNER,
        sender_name="Portfolio",
        timeout=timedelta(seconds=5),
        connector=connector,
        randomizer=random.Random(1),
    )


def _service(connector: FakeConnector, **overrides: object) -> ContactService:
    settings = {
        "mailer": _mailer(connector),
        "email_normalizer": EmailNormalizer(
            check_deliverability=True, dns_timeout=timedelta(seconds=3), resolver=FakeResolver()
        ),
        "subject_prefix": "[Portfolio]",
        "max_subject_chars": 20,
        "max_message_chars": 50,
        "clock": _clock,
    } | overrides
    return ContactService(**settings)


def _submission(**fields: object) -> ContactSubmission:
    base = {"email": " Visitor@Example.COM ", "subject": " Hiring? ", "message": " Let's talk. ", "client_ip": "203.0.113.7"}
    return ContactSubmission(**(base | fields))


def _sent(connector: FakeConnector) -> email.message.EmailMessage:
    return email.message_from_bytes(connector.connections[-1].sent[-1].as_bytes(), policy=email.policy.default)


def test_valid_submission_is_mailed_to_the_owner() -> None:
    connector = FakeConnector()

    receipt = _service(connector).submit(_submission())

    mail = _sent(connector)
    body = mail.get_content()
    assert receipt == ContactReceipt(reply_to="visitor@example.com", sent_at=NOW)
    assert mail["To"] == OWNER
    assert mail["Subject"] == "[Portfolio] Hiring?"
    assert mail["Reply-To"] == "visitor@example.com"
    assert "From: visitor@example.com" in body
    assert "Subject: Hiring?" in body
    assert "Let's talk." in body
    assert "IP: 203.0.113.7" in body
    assert "2026-10-02T09:30:00+00:00" in body


def test_missing_client_ip_is_left_out() -> None:
    connector = FakeConnector()

    _service(connector).submit(_submission(client_ip=None))

    assert "IP:" not in _sent(connector).get_content()


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"email": "not-an-email"}, "email"),
        ({"email": "a@b.com\r\nBcc: x@y.com"}, "email"),
        ({"email": f"visitor@{MISSING_DOMAIN}"}, "email"),
        ({"subject": "   "}, "subject"),
        ({"subject": "line one\nline two"}, "subject"),
        ({"subject": "x" * 21}, "subject"),
        ({"message": "  "}, "message"),
        ({"message": "x" * 51}, "message"),
    ],
)
def test_invalid_fields_name_the_field(fields: dict, field: str) -> None:
    connector = FakeConnector()

    with pytest.raises(InvalidContactSubmissionError) as error:
        _service(connector).submit(_submission(**fields))

    assert error.value.field == field
    assert isinstance(error.value, ContactError)
    assert connector.opened == []


def test_limits_apply_after_trimming() -> None:
    connector = FakeConnector()

    _service(connector).submit(_submission(subject=f"  {'x' * 20}  ", message=f"\n{'y' * 50}\n"))

    assert _sent(connector)["Subject"] == f"[Portfolio] {'x' * 20}"


def test_mail_errors_pass_through() -> None:
    connector = FakeConnector(open_errors={"sender1@example.com": OSError("down"), "sender2@example.com": OSError("down")})

    with pytest.raises(MailDeliveryError):
        _service(connector).submit(_submission())


def test_limits_are_exposed() -> None:
    service = _service(FakeConnector())

    assert (service.max_subject_chars, service.max_message_chars) == (20, 50)


def test_submit_rejects_other_types() -> None:
    with pytest.raises(TypeError):
        _service(FakeConnector()).submit({"email": "a@example.com"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"mailer": object()},
        {"email_normalizer": object()},
        {"subject_prefix": "  "},
        {"subject_prefix": "[A]\nBcc: x"},
        {"subject_prefix": 5},
        {"max_subject_chars": 0},
        {"max_message_chars": True},
    ],
)
def test_invalid_settings_raise(overrides: dict) -> None:
    with pytest.raises(InvalidContactSettingError):
        _service(FakeConnector(), **overrides)


def test_default_clock_is_utc_now() -> None:
    connector = FakeConnector()
    service = ContactService(
        mailer=_mailer(connector),
        email_normalizer=EmailNormalizer(check_deliverability=False, dns_timeout=timedelta(seconds=3)),
        subject_prefix="[P]",
        max_subject_chars=10,
        max_message_chars=10,
    )

    receipt = service.submit(_submission(subject="Hi", message="Hello"))

    assert receipt.sent_at.tzinfo is UTC
    assert abs(datetime.now(UTC) - receipt.sent_at) < timedelta(seconds=5)
