"""Domain normalization: user input -> canonical registrable host (e.g. `example.com`)."""

import ipaddress
import re
from urllib.parse import urlsplit

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class InvalidDomainError(ValueError):
    pass


def normalize_domain(raw: str) -> str:
    """Strip scheme, credentials, port, path, `www.`; lowercase; IDN -> punycode.

    >>> normalize_domain("HTTPS://WWW.Example.com:443/path?x=1")
    'example.com'
    """
    value = raw.strip()
    if not value:
        raise InvalidDomainError("empty domain")
    if "://" not in value:
        value = "http://" + value
    host = urlsplit(value).hostname
    if not host:
        raise InvalidDomainError(f"cannot parse domain from {raw!r}")
    host = host.rstrip(".").lower()
    if host.startswith("www."):
        host = host[4:]

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise InvalidDomainError("IP addresses are not supported")

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidDomainError(f"invalid internationalized domain {raw!r}") from exc

    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        raise InvalidDomainError(f"not a valid public domain: {raw!r}")
    if labels[-1] in {"localhost", "local", "internal", "test", "invalid"}:
        raise InvalidDomainError("reserved domain")
    return host
