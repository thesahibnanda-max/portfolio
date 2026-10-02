import logging
from datetime import timedelta

import dns.resolver
from email_validator import EmailSyntaxError, EmailUndeliverableError, caching_resolver, validate_email

from main.package.service.contact.exceptions import InvalidContactSettingError, InvalidContactSubmissionError

_LOGGER = logging.getLogger(__name__)
_FIELD = "email"
_MISSING_MESSAGE = "Enter your email address."
_SYNTAX_MESSAGE = "Enter a valid email address, like name@example.com."
_UNDELIVERABLE_MESSAGE = "That email domain doesn't accept mail. Check it for typos."


class EmailNormalizer:
    def __init__(
        self,
        *,
        check_deliverability: bool,
        dns_timeout: timedelta,
        resolver: dns.resolver.Resolver | None = None,
    ) -> None:
        if not isinstance(check_deliverability, bool):
            raise InvalidContactSettingError("check_deliverability must be a bool")
        if not isinstance(dns_timeout, timedelta) or dns_timeout <= timedelta(0):
            raise InvalidContactSettingError("dns_timeout must be a positive timedelta")
        if resolver is not None and not isinstance(resolver, dns.resolver.Resolver):
            raise InvalidContactSettingError("resolver must be a dns.resolver.Resolver")

        self._check_deliverability = check_deliverability
        self._resolver = self._build_resolver(check_deliverability, dns_timeout, resolver)

    @property
    def checks_deliverability(self) -> bool:
        return self._check_deliverability

    def normalize(self, raw: str) -> str:
        if not isinstance(raw, str) or not raw.strip():
            raise InvalidContactSubmissionError(_MISSING_MESSAGE, field=_FIELD)

        try:
            result = validate_email(
                raw.strip(),
                strict=True,
                check_deliverability=self._check_deliverability,
                dns_resolver=self._resolver,
            )
        except EmailUndeliverableError as error:
            raise InvalidContactSubmissionError(_UNDELIVERABLE_MESSAGE, field=_FIELD) from error
        except EmailSyntaxError as error:
            raise InvalidContactSubmissionError(_SYNTAX_MESSAGE, field=_FIELD) from error

        if self._check_deliverability and getattr(result, "mx", None) is None:
            _LOGGER.warning("Could not confirm mail delivery for %s; accepting it", result.domain)

        return result.normalized.lower()

    @staticmethod
    def _build_resolver(
        check_deliverability: bool,
        dns_timeout: timedelta,
        resolver: dns.resolver.Resolver | None,
    ) -> dns.resolver.Resolver | None:
        if not check_deliverability:
            return None
        return caching_resolver(timeout=dns_timeout.total_seconds(), dns_resolver=resolver)
