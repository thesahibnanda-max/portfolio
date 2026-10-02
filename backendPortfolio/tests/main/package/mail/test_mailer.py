import email
import email.policy
import logging
import random
import smtplib
import socket
from datetime import timedelta
from functools import partial

import pytest

from main.package.mail import (
    InvalidMailMessageError,
    InvalidMailSettingError,
    MailDeliveryError,
    Mailer,
    MailError,
    MailMessage,
    MailRecipientRejectedError,
    SmtpAccount,
    SmtpSecurity,
)
from tests.main.package.mail.fakes import PASSWORD, FakeConnector, account
from tests.support import ConcurrentRunner

TIMEOUT = timedelta(seconds=15)
RECIPIENT = "owner@example.com"
MESSAGE = MailMessage(subject="Hello", text_body="Someone reached out.")


class InOrder(random.Random):
    def sample(self, population, k, *, counts=None):
        return list(population)[:k]


def _mailer(connector: FakeConnector, count: int = 3, randomizer: random.Random | None = None) -> Mailer:
    return Mailer(
        accounts=[account(index) for index in range(1, count + 1)],
        recipient=RECIPIENT,
        sender_name="Sahib Nanda · Portfolio",
        timeout=TIMEOUT,
        connector=connector,
        randomizer=randomizer or InOrder(),
    )


def _parsed(connector: FakeConnector) -> email.message.EmailMessage:
    raw = connector.connections[-1].sent[-1].as_bytes()
    return email.message_from_bytes(raw, policy=email.policy.default)


def test_text_mail_has_the_expected_headers() -> None:
    connector = FakeConnector()
    receipt = _mailer(connector).send(MailMessage(subject="Hi", text_body="Body", reply_to="me@example.com"))

    parsed = _parsed(connector)
    assert parsed["From"] == "Sahib Nanda · Portfolio <sender1@example.com>"
    assert parsed["To"] == RECIPIENT
    assert parsed["Subject"] == "Hi"
    assert parsed["Reply-To"] == "me@example.com"
    assert parsed["Date"] is not None
    assert parsed["Message-ID"].endswith("@example.com>")
    assert parsed.get_content_type() == "text/plain"
    assert parsed.get_content().strip() == "Body"
    assert (receipt.account, receipt.recipient) == ("sender1@example.com", RECIPIENT)
    assert receipt.message_id == parsed["Message-ID"]
    assert connector.timeouts == [TIMEOUT]
    assert connector.connections[-1].closed


def test_html_mail_is_multipart_alternative_with_text_first() -> None:
    connector = FakeConnector()
    _mailer(connector).send(MESSAGE.model_copy(update={"html_body": "<p>Thanks</p>"}))

    parsed = _parsed(connector)
    assert parsed.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in parsed.iter_parts()] == ["text/plain", "text/html"]
    assert "Reply-To" not in parsed


def test_unicode_subject_and_body_survive_encoding() -> None:
    connector = FakeConnector()
    _mailer(connector).send(MailMessage(subject="Namaste 🙏 — ñ", text_body="Über café ✓"))

    parsed = _parsed(connector)
    assert parsed["Subject"] == "Namaste 🙏 — ñ"
    assert parsed.get_content().strip() == "Über café ✓"


def test_accounts_are_picked_in_a_random_order() -> None:
    connector = FakeConnector()
    accounts = [account(index) for index in (1, 2, 3)]
    expected_first = random.Random(7).sample(accounts, 3)[0].username
    mailer = _mailer(connector, randomizer=random.Random(7))

    receipts = [mailer.send(MESSAGE) for _ in range(30)]

    assert receipts[0].account == expected_first
    assert {receipt.account for receipt in receipts} == {account.username for account in accounts}
    assert mailer.accounts == ("sender1@example.com", "sender2@example.com", "sender3@example.com")
    assert mailer.recipient == RECIPIENT


def test_default_randomizer_draws_a_full_order() -> None:
    connector = FakeConnector(open_errors={f"sender{index}@example.com": OSError("down") for index in (1, 2, 3)})
    mailer = Mailer(
        accounts=[account(index) for index in (1, 2, 3)],
        recipient=RECIPIENT,
        sender_name="Sahib",
        timeout=TIMEOUT,
        connector=connector,
    )

    with pytest.raises(MailDeliveryError):
        mailer.send(MESSAGE)

    assert sorted(connector.opened) == ["sender1@example.com", "sender2@example.com", "sender3@example.com"]


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPAuthenticationError(535, b"bad credentials"),
        smtplib.SMTPConnectError(421, b"busy"),
        smtplib.SMTPServerDisconnected("gone"),
        socket.timeout("timed out"),
        ConnectionRefusedError("refused"),
    ],
)
def test_failed_login_or_connection_fails_over(error: BaseException, caplog: pytest.LogCaptureFixture) -> None:
    connector = FakeConnector(open_errors={"sender1@example.com": error})

    with caplog.at_level(logging.WARNING):
        receipt = _mailer(connector).send(MESSAGE)

    assert receipt.account == "sender2@example.com"
    assert connector.opened == ["sender1@example.com", "sender2@example.com"]
    assert "sender1@example.com" in caplog.text
    assert PASSWORD not in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPSenderRefused(550, b"quota exceeded", "sender1@example.com"),
        smtplib.SMTPDataError(452, b"try later"),
    ],
)
def test_send_failures_fail_over_and_close_the_connection(error: BaseException) -> None:
    connector = FakeConnector(send_errors={"sender1@example.com": error})

    receipt = _mailer(connector).send(MESSAGE)

    assert receipt.account == "sender2@example.com"
    assert connector.connections[0].closed


def test_a_refused_recipient_is_not_retried() -> None:
    refused = {RECIPIENT: (550, b"no such user")}
    connector = FakeConnector(send_errors={"sender1@example.com": smtplib.SMTPRecipientsRefused(refused)})

    with pytest.raises(MailRecipientRejectedError) as error:
        _mailer(connector).send(MESSAGE)

    assert error.value.recipient == RECIPIENT
    assert connector.opened == ["sender1@example.com"]
    assert isinstance(error.value.__cause__, smtplib.SMTPRecipientsRefused)


def test_every_account_failing_raises_with_all_attempts() -> None:
    failure = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    usernames = ("sender1@example.com", "sender2@example.com", "sender3@example.com")
    connector = FakeConnector(open_errors=dict.fromkeys(usernames, failure))

    with pytest.raises(MailDeliveryError) as error:
        _mailer(connector).send(MESSAGE)

    assert error.value.attempts == tuple((username, "SMTPAuthenticationError") for username in usernames)
    assert error.value.__cause__ is failure
    assert isinstance(error.value, MailError)
    assert PASSWORD not in str(error.value)


def test_a_failing_quit_still_closes_the_connection() -> None:
    connector = FakeConnector(quit_error=smtplib.SMTPServerDisconnected("gone"))

    receipt = _mailer(connector).send(MESSAGE)

    assert receipt.account == "sender1@example.com"
    assert connector.connections[0].closed


def _send_many(mailer: Mailer, count: int) -> int:
    for _ in range(count):
        mailer.send(MESSAGE)
    return count


def test_concurrent_sends_use_every_account() -> None:
    connector = FakeConnector()
    mailer = _mailer(connector, randomizer=random.SystemRandom())

    runner = ConcurrentRunner(partial(_send_many, mailer, 6)).run()

    counts = [connector.sent_by(f"sender{index}@example.com") for index in (1, 2, 3)]
    assert runner.errors == []
    assert sum(counts) == 96
    assert all(count > 0 for count in counts)


def test_send_rejects_non_messages() -> None:
    with pytest.raises(TypeError):
        _mailer(FakeConnector()).send({"subject": "Hi"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"accounts": []},
        {"accounts": "sender1@example.com"},
        {"accounts": [object()]},
        {"accounts": [account(1), account(1)]},
        {"recipient": "not-an-address"},
        {"recipient": "owner@example.com\r\nBcc: x@example.com"},
        {"recipient": None},
        {"sender_name": "  "},
        {"sender_name": "Sahib\nBcc: everyone@example.com"},
        {"sender_name": 5},
        {"timeout": timedelta(0)},
        {"timeout": 15},
        {"connector": object()},
        {"randomizer": object()},
    ],
)
def test_invalid_settings_raise(overrides: dict) -> None:
    settings = {"accounts": [account(1)], "recipient": RECIPIENT, "sender_name": "Sahib", "timeout": TIMEOUT} | overrides

    with pytest.raises(InvalidMailSettingError):
        Mailer(**settings)


@pytest.mark.parametrize(
    "fields",
    [
        {"to": ("a@example.com",)},
        {"reply_to": "Name <a@example.com>"},
        {"reply_to": "a@example.com\r\nBcc: x@example.com"},
        {"reply_to": "a@localhost"},
        {"subject": "Hi\r\nBcc: x@example.com"},
        {"subject": "   "},
        {"text_body": "  "},
        {"html_body": " "},
        {"reply_to": "nope"},
        {"cc": ("a@example.com",)},
    ],
)
def test_invalid_messages_are_rejected(fields: dict) -> None:
    base = {"subject": "Hi", "text_body": "Body"}

    with pytest.raises(InvalidMailMessageError):
        MailMessage.create(**(base | fields))


def test_create_builds_a_valid_message() -> None:
    message = MailMessage.create(subject="Hi", text_body="Body")

    assert (message.subject, message.html_body, message.reply_to) == ("Hi", None, None)


def test_account_password_is_hidden() -> None:
    sender = account(1)

    assert PASSWORD not in repr(sender)
    assert PASSWORD not in str(sender.model_dump())
    assert sender.domain == "example.com"
    assert SmtpSecurity("ssl") is SmtpSecurity.SSL


def test_account_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        SmtpAccount(host="", port=587, security="starttls", username="a@example.com", password="p")
    with pytest.raises(ValueError):
        SmtpAccount(host="h", port=0, security="starttls", username="a@example.com", password="p")
    with pytest.raises(ValueError):
        SmtpAccount(host="h", port=587, security="plain", username="a@example.com", password="p")
