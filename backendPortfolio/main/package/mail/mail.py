import logging
import random
import smtplib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from main.package.mail.connection import SmtpConnector, SmtplibConnector
from main.package.mail.dto import MailMessage, MailReceipt, SmtpAccount, require_address
from main.package.mail.exceptions import InvalidMailSettingError, MailDeliveryError, MailRecipientRejectedError

_LOGGER = logging.getLogger(__name__)


class Mailer:
    def __init__(
        self,
        *,
        accounts: Sequence[SmtpAccount],
        recipient: str,
        sender_name: str,
        timeout: timedelta,
        connector: SmtpConnector | None = None,
        randomizer: random.Random | None = None,
    ) -> None:
        self._accounts = self._require_accounts(accounts)
        self._recipient = self._require_recipient(recipient)

        if not isinstance(sender_name, str) or not sender_name.strip() or "\n" in sender_name or "\r" in sender_name:
            raise InvalidMailSettingError("sender_name must be a non-blank single line")

        if not isinstance(timeout, timedelta) or timeout <= timedelta(0):
            raise InvalidMailSettingError("timeout must be a positive timedelta")

        if connector is not None and not isinstance(connector, SmtpConnector):
            raise InvalidMailSettingError("connector must be an SmtpConnector")

        if randomizer is not None and not isinstance(randomizer, random.Random):
            raise InvalidMailSettingError("randomizer must be a random.Random")

        self._sender_name = sender_name.strip()
        self._timeout = timeout
        self._connector = connector or SmtplibConnector()
        self._randomizer = randomizer or random.SystemRandom()

    @property
    def accounts(self) -> tuple[str, ...]:
        return tuple(account.username for account in self._accounts)

    @property
    def recipient(self) -> str:
        return self._recipient

    def send(self, message: MailMessage) -> MailReceipt:
        if not isinstance(message, MailMessage):
            raise TypeError("message must be a MailMessage")

        attempts: list[tuple[str, str]] = []
        last_error: BaseException | None = None

        for account in self._attempt_order():
            try:
                return self._send_with(account, message)
            except smtplib.SMTPRecipientsRefused as error:
                raise MailRecipientRejectedError(
                    f"The mail server refused the recipient {self._recipient}",
                    recipient=self._recipient,
                ) from error
            except (smtplib.SMTPException, OSError) as error:
                attempts.append((account.username, type(error).__name__))
                last_error = error
                _LOGGER.warning("Mail via %s failed with %s; trying the next account", account.username, type(error).__name__)

        raise MailDeliveryError(
            f"Mail could not be sent through any of {len(self._accounts)} account(s)",
            attempts=attempts,
        ) from last_error

    def _attempt_order(self) -> list[SmtpAccount]:
        return self._randomizer.sample(self._accounts, len(self._accounts))

    def _send_with(self, account: SmtpAccount, message: MailMessage) -> MailReceipt:
        email = self._build(account, message)
        connection = self._connector.open(account, timeout=self._timeout)
        try:
            connection.send_message(email)
        finally:
            self._close(connection)

        return MailReceipt(
            message_id=str(email["Message-ID"]),
            account=account.username,
            recipient=self._recipient,
            sent_at=datetime.now(UTC),
        )

    def _build(self, account: SmtpAccount, message: MailMessage) -> EmailMessage:
        email = EmailMessage()
        email["From"] = formataddr((self._sender_name, account.username))
        email["To"] = self._recipient
        email["Subject"] = message.subject
        email["Date"] = formatdate(usegmt=True)
        email["Message-ID"] = make_msgid(domain=account.domain)
        if message.reply_to is not None:
            email["Reply-To"] = message.reply_to

        email.set_content(message.text_body)
        if message.html_body is not None:
            email.add_alternative(message.html_body, subtype="html")

        return email

    @staticmethod
    def _close(connection: smtplib.SMTP) -> None:
        try:
            connection.quit()
        except (smtplib.SMTPException, OSError):
            connection.close()

    @staticmethod
    def _require_recipient(recipient: str) -> str:
        if not isinstance(recipient, str):
            raise InvalidMailSettingError("recipient must be an email address string")
        try:
            return require_address(recipient)
        except ValueError as error:
            raise InvalidMailSettingError(f"recipient {error}") from error

    @staticmethod
    def _require_accounts(accounts: Sequence[SmtpAccount]) -> tuple[SmtpAccount, ...]:
        if isinstance(accounts, str | bytes) or not isinstance(accounts, Sequence) or not accounts:
            raise InvalidMailSettingError("accounts must be a non-empty sequence of SmtpAccount")

        if not all(isinstance(account, SmtpAccount) for account in accounts):
            raise InvalidMailSettingError("every account must be an SmtpAccount")

        usernames = [account.username for account in accounts]
        if len(set(usernames)) != len(usernames):
            raise InvalidMailSettingError("account usernames must be unique")

        return tuple(accounts)
