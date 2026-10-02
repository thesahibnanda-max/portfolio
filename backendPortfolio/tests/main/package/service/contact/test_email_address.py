import logging
from datetime import timedelta

import pytest

from main.package.service.contact import EmailNormalizer, InvalidContactSettingError, InvalidContactSubmissionError
from tests.main.package.service.contact.fakes import (
    MISSING_DOMAIN,
    NO_MAIL_DOMAIN,
    NULL_MX_DOMAIN,
    SLOW_DOMAIN,
    FakeResolver,
)

TIMEOUT = timedelta(seconds=3)


def _syntax_only() -> EmailNormalizer:
    return EmailNormalizer(check_deliverability=False, dns_timeout=TIMEOUT)


def _checking(resolver: FakeResolver) -> EmailNormalizer:
    return EmailNormalizer(check_deliverability=True, dns_timeout=TIMEOUT, resolver=resolver)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("  Foo.Bar@Example.COM \n", "foo.bar@example.com"),
        ("VISITOR@GMAIL.COM", "visitor@gmail.com"),
        ("\tname+tag@Sub.Domain.Co.UK", "name+tag@sub.domain.co.uk"),
        ("Ünïcode@Bücher.DE", "ünïcode@bücher.de"),
    ],
)
def test_trims_and_lowercases(raw: str, normalized: str) -> None:
    assert _syntax_only().normalize(raw) == normalized


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "plainaddress",
        "a@b",
        "a@@example.com",
        "a b@example.com",
        "Name <a@example.com>",
        '"quoted"@example.com',
        "a@example.com\r\nBcc: x@example.com",
        "user@localhost",
        "user@service.test",
        "user@[192.168.0.1]",
        f"{'x' * 65}@example.com",
        f"a@{'d' * 250}.com",
    ],
)
def test_rejects_invalid_syntax_on_the_email_field(raw: str) -> None:
    with pytest.raises(InvalidContactSubmissionError) as error:
        _syntax_only().normalize(raw)

    assert error.value.field == "email"
    assert "email" in str(error.value).lower()


def test_rejects_non_strings() -> None:
    with pytest.raises(InvalidContactSubmissionError):
        _syntax_only().normalize(None)


def test_deliverable_domain_passes_after_an_mx_lookup() -> None:
    resolver = FakeResolver()

    assert _checking(resolver).normalize("Visitor@Example.com") == "visitor@example.com"
    assert resolver.queries == [("example.com", "MX")]


@pytest.mark.parametrize("domain", [MISSING_DOMAIN, NO_MAIL_DOMAIN, NULL_MX_DOMAIN])
def test_undeliverable_domains_are_rejected(domain: str) -> None:
    with pytest.raises(InvalidContactSubmissionError) as error:
        _checking(FakeResolver()).normalize(f"visitor@{domain}")

    assert error.value.field == "email"
    assert "doesn't accept mail" in str(error.value)


def test_dns_timeout_fails_open_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        normalized = _checking(FakeResolver()).normalize(f"Visitor@{SLOW_DOMAIN}")

    assert normalized == f"visitor@{SLOW_DOMAIN}"
    assert SLOW_DOMAIN in caplog.text


def test_syntax_only_mode_never_queries_dns() -> None:
    normalizer = _syntax_only()

    assert normalizer.normalize(f"visitor@{MISSING_DOMAIN}") == f"visitor@{MISSING_DOMAIN}"
    assert normalizer.checks_deliverability is False


def test_default_resolver_is_built_when_checking() -> None:
    assert EmailNormalizer(check_deliverability=True, dns_timeout=TIMEOUT).checks_deliverability is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"check_deliverability": "yes"},
        {"dns_timeout": timedelta(0)},
        {"dns_timeout": 3},
        {"resolver": object()},
    ],
)
def test_invalid_settings_raise(overrides: dict) -> None:
    settings = {"check_deliverability": True, "dns_timeout": TIMEOUT} | overrides

    with pytest.raises(InvalidContactSettingError):
        EmailNormalizer(**settings)
