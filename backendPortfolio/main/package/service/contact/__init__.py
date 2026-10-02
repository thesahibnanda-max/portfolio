"""
The "Contact me" flow: a visitor's email, subject and message are validated
and mailed to the owner's fixed inbox, so contact messages need no storage.

Exports:
    ContactService: validates a submission and mails it.
    EmailNormalizer: validates and normalizes the visitor's email.
    ContactSubmission, ContactReceipt: the DTOs.
    ContactError and its subclasses: the errors described under Errors.

submit(submission) -> ContactReceipt:
    1. The email is validated and normalized by EmailNormalizer (see below).
    2. Validation, after trimming: subject is non-empty, one line, at most
       max_subject_chars; message is non-empty, at most max_message_chars.
       A failure raises InvalidContactSubmissionError with the field name, so
       the API can point the form at it.
    3. The body is rendered from templates/contact.md (plain-text Jinja,
       StrictUndefined; the wording lives only in that file) with the
       normalized email, subject, message, the UTC time and the client IP.
    4. main.package.mail.Mailer sends it to the configured recipient with the
       subject "<subject_prefix> <subject>" and Reply-To set to the
       normalized email, so replying in the inbox answers the visitor.
    ContactReceipt has reply_to (the normalized email) and sent_at (UTC).
    Spam is held back by the API's rate limit, not by this service.

EmailNormalizer(*, check_deliverability, dns_timeout, resolver=None):
    normalize(raw) -> str, using email-validator (the library behind
    pydantic's EmailStr):
        1. Surrounding whitespace is trimmed; blank raises.
        2. Syntax: display names, brackets, inner spaces or line breaks,
           quoted local parts, IP-literal domains, special-use domains
           (localhost, .test, .invalid ...), a domain without a dot and
           over-long addresses (strict mode: over 64 characters before the @,
           or over 254 in all) are rejected. Unicode (IDN) is allowed and
           normalized to NFC.
        3. Deliverability (when check_deliverability): the domain must have
           an MX record (or an A/AAAA fallback) and no null MX or "v=spf1
           -all" policy; a missing domain is rejected. A DNS timeout or
           unreachable nameservers fail open: the address is accepted and a
           warning is logged, so a DNS hiccup never blocks a real visitor.
           Lookups use a cached dnspython resolver with dns_timeout.
        4. The library's normalized form (domain lowercased) is lowercased
           completely, local part included, giving one canonical address.
    Every rejection raises InvalidContactSubmissionError(field="email") with
    a friendly message. resolver lets tests inject a fake dnspython
    resolver; a bad setting raises InvalidContactSettingError.

Construction:
    ContactService(*, mailer, email_normalizer, subject_prefix, max_subject_chars, max_message_chars, clock=...)
    mailer: a main.package.mail.Mailer. email_normalizer: an EmailNormalizer.
    subject_prefix: one non-blank line.
    The limits are positive ints. All come from main.config.AppConfig.mail
    and AppConfig.contact. A bad setting raises InvalidContactSettingError.

Errors (all in exceptions.py, all subclasses of ContactError):
    InvalidContactSettingError: a constructor setting is invalid.
    InvalidContactSubmissionError: a field is invalid; has field.
    Mail errors (MailDeliveryError, MailRecipientRejectedError) pass through
    unwrapped for the API's status mapping.

Thread safety:
    The service holds only immutable settings, a compiled template and the
    thread-safe Mailer, so one instance serves every thread.
"""

from .contact_service import ContactService
from .dto import ContactReceipt, ContactSubmission
from .email_address import EmailNormalizer
from .exceptions import ContactError, InvalidContactSettingError, InvalidContactSubmissionError

__all__ = [
    "ContactService",
    "EmailNormalizer",
    "ContactSubmission",
    "ContactReceipt",
    "ContactError",
    "InvalidContactSettingError",
    "InvalidContactSubmissionError",
]
