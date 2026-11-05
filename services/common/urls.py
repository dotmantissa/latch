"""Public URL and DNS validation shared with the dependency-free worker proxy."""

import ipaddress
import re
from urllib.parse import unquote, urlsplit


def public_https_url(value: str) -> str:
    if len(value) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ValueError("Invalid public source address")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Only public HTTPS URLs without credentials or queries are supported")
    host = parsed.hostname
    if host.endswith(".") or "%" in host or ":" in host:
        raise ValueError("Noncanonical hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literal sources are unsupported")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
        raise ValueError("Noncanonical hostname")
    # Numeric alternate address encodings and local-only names are not supplier hosts.
    if "." not in host or all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", x) for x in host.split(".")):
        raise ValueError("Public DNS hostname required")
    if host.endswith((".local", ".localhost", ".internal", ".test", ".invalid", ".example")):
        raise ValueError("Reserved hostname")
    decoded = unquote(parsed.path)
    if "%" in decoded or re.search(r"[\\\x00-\x1f\x7f]", decoded):
        raise ValueError("Encoded navigation is unsupported")
    if any(part in (".", "..") for part in decoded.split("/")):
        raise ValueError("Noncanonical source path")
    return f"https://{host}{parsed.path or '/'}"


def require_public_addresses(addresses: list[str]) -> tuple[str, ...]:
    """The proxy must apply this to every DNS answer and pin at socket connection."""
    if not addresses:
        raise ValueError("No resolved address")
    normalized = []
    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if parsed.version == 6 and parsed.ipv4_mapped:
            parsed = parsed.ipv4_mapped
        if not parsed.is_global:
            raise ValueError("Private or reserved destination denied")
        normalized.append(str(parsed))
    return tuple(normalized)

