import os
from datetime import timedelta

import pytest

from main.package.mail import Mailer, MailMessage, SmtpAccount, SmtpSecurity

REQUIRED = ("MAIL_ACCOUNT_1_USERNAME", "MAIL_ACCOUNT_1_PASSWORD", "RECIPIENT_MAIL")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not all(os.environ.get(name) for name in REQUIRED), reason=f"set {', '.join(REQUIRED)}"),
]


def test_sends_a_real_mail() -> None:
    mailer = Mailer(
        accounts=[
            SmtpAccount(
                host=os.environ.get("MAIL_LIVE_HOST", "smtp.gmail.com"),
                port=int(os.environ.get("MAIL_LIVE_PORT", "587")),
                security=SmtpSecurity(os.environ.get("MAIL_LIVE_SECURITY", "starttls")),
                username=os.environ["MAIL_ACCOUNT_1_USERNAME"],
                password=os.environ["MAIL_ACCOUNT_1_PASSWORD"],
            )
        ],
        recipient=os.environ["RECIPIENT_MAIL"],
        sender_name="Portfolio live test",
        timeout=timedelta(seconds=20),
    )

    receipt = mailer.send(
        MailMessage(
            subject="Portfolio mailer live test ✓",
            text_body="If you can read this, the portfolio mailer works.",
            html_body="<p>If you can read this, the <strong>portfolio mailer</strong> works.</p>",
        )
    )

    assert receipt.recipient == os.environ["RECIPIENT_MAIL"]
