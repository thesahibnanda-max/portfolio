import smtplib
import ssl
from abc import ABC, abstractmethod
from datetime import timedelta

import certifi

from main.package.mail.dto import SmtpAccount, SmtpSecurity


def tls_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


class SmtpConnector(ABC):
    @abstractmethod
    def open(self, account: SmtpAccount, *, timeout: timedelta) -> smtplib.SMTP:
        ...


class SmtplibConnector(SmtpConnector):
    def open(self, account: SmtpAccount, *, timeout: timedelta) -> smtplib.SMTP:
        seconds = timeout.total_seconds()
        context = tls_context()

        if account.security is SmtpSecurity.SSL:
            connection: smtplib.SMTP = smtplib.SMTP_SSL(account.host, account.port, timeout=seconds, context=context)
        else:
            connection = smtplib.SMTP(account.host, account.port, timeout=seconds)

        try:
            if account.security is SmtpSecurity.STARTTLS:
                connection.ehlo()
                connection.starttls(context=context)
                connection.ehlo()
            connection.login(account.username, account.password.get_secret_value())
        except BaseException:
            connection.close()
            raise

        return connection
