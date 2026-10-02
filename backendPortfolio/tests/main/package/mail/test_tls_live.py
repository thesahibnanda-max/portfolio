import smtplib

import pytest

from main.package.mail import tls_context

pytestmark = pytest.mark.live


@pytest.mark.parametrize(("host", "port"), [("smtp.gmail.com", 587)])
def test_starttls_handshake_verifies_a_real_server(host: str, port: int) -> None:
    with smtplib.SMTP(host, port, timeout=15) as connection:
        connection.ehlo()
        code, _ = connection.starttls(context=tls_context())
        connection.ehlo()

    assert code == 220
