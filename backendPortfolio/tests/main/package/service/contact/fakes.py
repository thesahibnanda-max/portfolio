from dataclasses import dataclass

import dns.exception
import dns.resolver

NO_MAIL_DOMAIN = "no-mail.example.org"
MISSING_DOMAIN = "gmial.con"
SLOW_DOMAIN = "slow.example.org"
NULL_MX_DOMAIN = "null-mx.example.org"


@dataclass(frozen=True)
class MxRecord:
    preference: int
    exchange: str


class FakeResolver(dns.resolver.Resolver):
    def __init__(self) -> None:
        super().__init__(configure=False)
        self.queries: list[tuple[str, str]] = []

    def resolve(self, qname: str, rdtype: str = "A", *args: object, **kwargs: object) -> list[MxRecord]:
        domain = str(qname)
        self.queries.append((domain, str(rdtype)))
        if domain == MISSING_DOMAIN:
            raise dns.resolver.NXDOMAIN()
        if domain == SLOW_DOMAIN:
            raise dns.exception.Timeout()
        if domain == NO_MAIL_DOMAIN:
            raise dns.resolver.NoAnswer()
        if domain == NULL_MX_DOMAIN:
            return [MxRecord(preference=0, exchange=".")]
        return [MxRecord(preference=10, exchange=f"mx.{domain}.")]
