import smtplib
import ssl
from datetime import timedelta

import pytest

from main.package.mail import Mailer, MailMessage, SmtplibConnector, SmtpSecurity, tls_context
from tests.main.package.mail.fakes import account


class RecordingSmtp:
    instances: list["RecordingSmtp"] = []

    def __init__(self, host: str, port: int, timeout: float, context: ssl.SSLContext | None = None) -> None:
        self.calls: list[tuple] = [("connect", host, port, timeout, context)]
        self.login_error: BaseException | None = None
        RecordingSmtp.instances.append(self)

    def ehlo(self) -> None:
        self.calls.append(("ehlo",))

    def starttls(self, context: ssl.SSLContext) -> None:
        self.calls.append(("starttls", context))

    def login(self, username: str, password: str) -> None:
        self.calls.append(("login", username, password))
        if self.login_error is not None:
            raise self.login_error

    def close(self) -> None:
        self.calls.append(("close",))

    def send_message(self, message: object) -> dict:
        self.calls.append(("send_message", message))
        return {}

    def quit(self) -> None:
        self.calls.append(("quit",))


class FailingLoginSmtp(RecordingSmtp):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.login_error = smtplib.SMTPAuthenticationError(535, b"bad")


@pytest.fixture(autouse=True)
def recording(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingSmtp.instances = []
    monkeypatch.setattr(smtplib, "SMTP", RecordingSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", RecordingSmtp)


def test_starttls_upgrades_before_login_with_a_verifying_context() -> None:
    sender = account(1, SmtpSecurity.STARTTLS)

    SmtplibConnector().open(sender, timeout=timedelta(seconds=12))

    calls = RecordingSmtp.instances[0].calls
    assert calls[0][:4] == ("connect", "smtp1.example.com", 587, 12.0)
    assert [call[0] for call in calls] == ["connect", "ehlo", "starttls", "ehlo", "login"]
    context = calls[2][1]
    assert context.verify_mode is ssl.CERT_REQUIRED and context.check_hostname
    assert context.cert_store_stats()["x509_ca"] > 0
    assert calls[4] == ("login", "sender1@example.com", sender.password.get_secret_value())


def test_ssl_uses_implicit_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", None)

    SmtplibConnector().open(account(2, SmtpSecurity.SSL), timeout=timedelta(seconds=5))

    calls = RecordingSmtp.instances[0].calls
    assert calls[0][:4] == ("connect", "smtp2.example.com", 465, 5.0)
    assert calls[0][4].verify_mode is ssl.CERT_REQUIRED
    assert calls[0][4].cert_store_stats()["x509_ca"] > 0
    assert [call[0] for call in calls] == ["connect", "login"]


def test_failed_login_closes_the_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", FailingLoginSmtp)

    with pytest.raises(smtplib.SMTPAuthenticationError):
        SmtplibConnector().open(account(1), timeout=timedelta(seconds=5))

    assert RecordingSmtp.instances[0].calls[-1] == ("close",)


def test_mailer_sends_through_smtplib_by_default() -> None:
    mailer = Mailer(accounts=[account(1)], recipient="owner@example.com", sender_name="Sahib", timeout=timedelta(seconds=5))

    receipt = mailer.send(MailMessage(subject="Hi", text_body="Body"))

    assert [call[0] for call in RecordingSmtp.instances[0].calls] == [
        "connect",
        "ehlo",
        "starttls",
        "ehlo",
        "login",
        "send_message",
        "quit",
    ]
    assert receipt.account == "sender1@example.com"


def test_tls_context_trusts_certifi_even_when_the_system_store_is_empty() -> None:
    context = tls_context()

    assert context.cert_store_stats()["x509_ca"] > 0
    assert (context.verify_mode, context.check_hostname) == (ssl.CERT_REQUIRED, True)
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
