import smtplib
import threading
from collections.abc import Mapping
from datetime import timedelta
from email.message import EmailMessage

from main.package.mail import SmtpAccount, SmtpConnector, SmtpSecurity

PASSWORD = "super-secret-app-password"


def account(index: int, security: SmtpSecurity = SmtpSecurity.STARTTLS) -> SmtpAccount:
    return SmtpAccount(
        host=f"smtp{index}.example.com",
        port=587 if security is SmtpSecurity.STARTTLS else 465,
        security=security,
        username=f"sender{index}@example.com",
        password=f"{PASSWORD}-{index}",
    )


class FakeSmtp:
    def __init__(self, username: str, send_error: BaseException | None, refused: Mapping[str, tuple[int, bytes]]) -> None:
        self.username = username
        self._send_error = send_error
        self._refused = dict(refused)
        self.sent: list[EmailMessage] = []
        self.quit_error: BaseException | None = None
        self.closed = False

    def send_message(self, message: EmailMessage) -> dict[str, tuple[int, bytes]]:
        if self._send_error is not None:
            raise self._send_error
        self.sent.append(message)
        return self._refused

    def quit(self) -> None:
        if self.quit_error is not None:
            raise self.quit_error
        self.closed = True

    def close(self) -> None:
        self.closed = True


class FakeConnector(SmtpConnector):
    def __init__(
        self,
        *,
        open_errors: Mapping[str, BaseException] | None = None,
        send_errors: Mapping[str, BaseException] | None = None,
        refused: Mapping[str, tuple[int, bytes]] | None = None,
        quit_error: BaseException | None = None,
    ) -> None:
        self._open_errors = dict(open_errors or {})
        self._send_errors = dict(send_errors or {})
        self._refused = dict(refused or {})
        self._quit_error = quit_error
        self._lock = threading.Lock()
        self.opened: list[str] = []
        self.connections: list[FakeSmtp] = []
        self.timeouts: list[timedelta] = []

    def open(self, account: SmtpAccount, *, timeout: timedelta) -> smtplib.SMTP:
        with self._lock:
            self.opened.append(account.username)
            self.timeouts.append(timeout)
        error = self._open_errors.get(account.username)
        if error is not None:
            raise error
        connection = FakeSmtp(account.username, self._send_errors.get(account.username), self._refused)
        connection.quit_error = self._quit_error
        with self._lock:
            self.connections.append(connection)
        return connection

    def sent_by(self, username: str) -> int:
        return sum(len(connection.sent) for connection in self.connections if connection.username == username)
