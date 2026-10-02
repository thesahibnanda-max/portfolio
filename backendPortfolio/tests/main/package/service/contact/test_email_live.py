import secrets
from datetime import timedelta

import pytest

from main.package.service.contact import EmailNormalizer, InvalidContactSubmissionError

pytestmark = pytest.mark.live


def test_real_dns_accepts_a_mail_domain_and_rejects_a_missing_one() -> None:
    normalizer = EmailNormalizer(check_deliverability=True, dns_timeout=timedelta(seconds=5))

    assert normalizer.normalize("  Someone@GMAIL.com ") == "someone@gmail.com"
    with pytest.raises(InvalidContactSubmissionError):
        normalizer.normalize(f"someone@no-such-domain-{secrets.token_hex(8)}.com")
