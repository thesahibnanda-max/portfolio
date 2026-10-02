"""
Sends mail over SMTP to one fixed recipient (the owner's inbox, from
config) through one or more sending accounts, rotating between them and
failing over when one cannot send.

Exports:
    Mailer: builds and sends a MailMessage.
    SmtpAccount, SmtpSecurity, MailMessage, MailReceipt: the DTOs.
    SmtpConnector, SmtplibConnector: how a logged-in connection is opened.
    tls_context: the verifying SSL context every connection uses.
    MailError and its subclasses: the errors described under Errors.

Accounts (SmtpAccount, one per config entry):
    host, port (1 to 65535), security, username and password (a SecretStr,
    never shown in a repr, log or error). username is a plain email address
    and is also the From address, so each account sends as itself.
    security is always encrypted:
        STARTTLS: connect in plain text, upgrade with STARTTLS before login
        (usually port 587).
        SSL: implicit TLS from the first byte (usually port 465).
    Both use ssl.create_default_context(cafile=certifi.where()), so
    certificates and host names are verified against certifi's Mozilla CA
    bundle (the same trust store httpx uses) rather than the operating
    system's. Some Python builds, such as the python.org macOS framework
    build, ship with an empty system store, which would make every
    handshake fail with CERTIFICATE_VERIFY_FAILED. There is no unencrypted
    mode and verification is never turned off.

Random selection and failover:
    Each send tries the accounts in a fresh random order, so the first one is
    picked at random and quota spreads across accounts. The default
    randomizer is random.SystemRandom (OS entropy, no shared mutable state);
    tests pass a seeded random.Random to make the order deterministic.
    If an attempt fails with an SMTP or network error (login refused,
    connection or timeout, disconnect, sender refused, data rejected, quota),
    the next account is tried, until every account has had one attempt.
    Each failover logs a warning with the account and the error type.
    A refusal of the recipient is not retried: another account cannot fix a
    bad address, so MailRecipientRejectedError is raised at once.
    Every attempt opens its own connection and closes it afterwards.

Messages (MailMessage):
    There is no "to": every mail goes to the Mailer's fixed recipient.
    subject: a single non-blank line.
    text_body: required, non-blank. html_body: optional; when set the mail is
    multipart/alternative with the text part first, so text-only clients
    still read it. reply_to: an optional address.
    Line breaks are rejected in the subject and reply_to (no header
    injection). MailMessage.create(**fields) raises InvalidMailMessageError
    instead of pydantic's ValidationError.
    Each mail gets From ("sender_name <account>"), To (the recipient),
    Subject, Date (UTC),
    Message-ID (on the account's domain) and Reply-To when given. Non-ASCII
    subjects and bodies are encoded by the standard email package.

send(message) -> MailReceipt:
    message_id, account (the username that sent it), recipient and sent_at
    (UTC).

Construction:
    Mailer(*, accounts, recipient, sender_name, timeout, connector=None, randomizer=None)
    accounts: non-empty sequence of SmtpAccount with unique usernames.
    recipient: the one plain email address every mail is sent to.
    sender_name: the display name on From, one non-blank line.
    timeout: positive timedelta for connecting and each SMTP command.
    connector: an SmtpConnector; the default SmtplibConnector uses smtplib.
    randomizer: a random.Random; defaults to random.SystemRandom().
    A bad setting raises InvalidMailSettingError. All values come from
    main.config.AppConfig.mail:
        Mailer(
            accounts=[SmtpAccount(**account.model_dump()) for account in config.mail.accounts],
            recipient=config.mail.recipient_mail,
            sender_name=config.mail.sender_name,
            timeout=config.mail.timeout,
        )

Errors (all in exceptions.py, all subclasses of MailError):
    InvalidMailSettingError: a constructor setting is invalid.
    InvalidMailMessageError: MailMessage.create was given invalid fields.
    MailRecipientRejectedError: the server refused the recipient; has
    recipient.
    MailDeliveryError: every account failed; attempts holds
    (username, error type) pairs and the last error is chained as __cause__.

Thread safety:
    One Mailer can serve every thread on the free-threaded Python 3.14t
    build. Nothing mutable is shared: the attempt order is drawn per send,
    sending holds no lock and every attempt uses its own connection. smtplib, ssl
    and email are standard library and keep the GIL disabled.

Example:
    receipt = mailer.send(
        MailMessage.create(
            subject="New portfolio message",
            text_body="Someone asked about your Codeforces rating.",
        )
    )
"""

from .connection import SmtpConnector, SmtplibConnector, tls_context
from .dto import MailMessage, MailReceipt, SmtpAccount, SmtpSecurity
from .exceptions import (
    InvalidMailMessageError,
    InvalidMailSettingError,
    MailDeliveryError,
    MailError,
    MailRecipientRejectedError,
)
from .mail import Mailer

__all__ = [
    "Mailer",
    "SmtpAccount",
    "SmtpSecurity",
    "MailMessage",
    "MailReceipt",
    "SmtpConnector",
    "SmtplibConnector",
    "tls_context",
    "MailError",
    "InvalidMailSettingError",
    "InvalidMailMessageError",
    "MailRecipientRejectedError",
    "MailDeliveryError",
]
