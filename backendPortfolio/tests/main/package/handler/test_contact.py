from http import HTTPStatus
from pathlib import Path

import pytest

from tests.conftest import FAKE_MAIL_USERNAME, FAKE_MAIL_USERNAME_2
from tests.main.package.handler.fakes import Harness
from tests.main.package.service.contact.fakes import MISSING_DOMAIN
from tests.main.package.mail.fakes import FakeConnector

VALID = {"email": "visitor@example.com", "subject": "Hiring?", "message": "Let's talk."}


@pytest.fixture
def harness(config_env: str, tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_contact_is_mailed_and_answers_sent(harness: Harness) -> None:
    with harness.client() as client:
        response = client.post("/contact", json=VALID, headers={"X-Forwarded-For": "203.0.113.7"})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["status"] == HTTPStatus.OK
    assert body["data"]["status"] == "SENT"
    assert body["data"]["reply_to"] == "visitor@example.com"
    sent = harness.smtp.connections[-1].sent[-1]
    assert sent["Reply-To"] == "visitor@example.com"
    assert sent["Subject"] == "[Portfolio] Hiring?"
    assert "203.0.113.7" in sent.get_content()


def test_email_is_normalized_before_sending(harness: Harness) -> None:
    with harness.client() as client:
        response = client.post("/contact", json=VALID | {"email": "  Visitor@Example.COM \t"})

    assert response.json()["data"]["reply_to"] == "visitor@example.com"
    assert harness.smtp.connections[-1].sent[-1]["Reply-To"] == "visitor@example.com"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"email": "visitor@example.com", "subject": "Hi"}, "body.message"),
        (VALID | {"extra": 1}, "body.extra"),
        (VALID | {"website": "http://spam.example"}, "body.website"),
        (VALID | {"email": f"visitor@{MISSING_DOMAIN}"}, "body.email"),
        (VALID | {"subject": 5}, "body.subject"),
        (VALID | {"email": "nope"}, "body.email"),
        (VALID | {"subject": "x" * 151}, "body.subject"),
        (VALID | {"message": "x" * 5001}, "body.message"),
        (VALID | {"message": "   "}, "body.message"),
    ],
)
def test_invalid_contact_is_400_with_the_field(harness: Harness, body: dict, field: str) -> None:
    with harness.client() as client:
        response = client.post("/contact", json=body)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    error = response.json()
    assert error["error"] == "VALIDATION_ERROR"
    assert field in [detail["field"] for detail in error["details"]]
    assert harness.smtp.opened == []


def test_contact_is_rate_limited_per_ip(harness: Harness) -> None:
    with harness.client() as client:
        statuses = [client.post("/contact", json=VALID).status_code for _ in range(3)]
        refused = client.post("/contact", json=VALID)

    assert statuses == [HTTPStatus.OK] * 3
    assert refused.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert 1 <= int(refused.headers["retry-after"]) <= 3600


def test_all_accounts_failing_is_503(harness: Harness) -> None:
    harness.smtp = FakeConnector(
        open_errors={username: OSError("smtp down") for username in (FAKE_MAIL_USERNAME, FAKE_MAIL_USERNAME_2)}
    )

    with harness.client() as client:
        response = client.post("/contact", json=VALID)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["error"] == "MAIL_UNAVAILABLE"
    assert "smtp down" not in response.text
