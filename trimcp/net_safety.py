"""
Outbound URL guards for bridges — mitigates SSRF from misconfiguration or poisoned cursors.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

log = logging.getLogger("trimcp.net_safety")

# Explicit IPv6 CIDR denylist for SSRF (defense in depth next to ipaddress is_* flags).
_SSRF_DENIED_IPV6_NETWORKS: tuple[ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(c)  # type: ignore[misc]
    for c in (
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "2001:db8::/32",
        "100::/64",
    )
)


class BridgeURLValidationError(ValueError):
    """Raised when a bridge-related URL fails safety checks."""


def _parse_ip_from_getaddrinfo(
    sockaddr_ip: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """
    Parse the host portion of a ``getaddrinfo`` sockaddr tuple.

    Normalizes IPv6 literals: optional ``[...]`` wrapping and zone identifiers
    (``fe80::1%eth0``) which ``ipaddress.ip_address`` does not accept verbatim.
    """
    s = sockaddr_ip.strip()
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        s = s[1:-1]
    if "%" in s:
        s = s.split("%", 1)[0]
    return ipaddress.ip_address(s)


def _resolve_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    out: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise BridgeURLValidationError(f"cannot resolve host {hostname!r}: {e}") from e
    for item in infos:
        sockaddr = item[4]
        ip_str = sockaddr[0]
        try:
            out.append(_parse_ip_from_getaddrinfo(ip_str))  # type: ignore[arg-type]
        except ValueError:
            continue
    if not out:
        raise BridgeURLValidationError(f"no usable IP addresses for host {hostname!r}")
    return out


def _all_loopback(ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address]) -> bool:
    return bool(ips) and all(ip.is_loopback for ip in ips)


def _ipv6_in_explicit_denylist(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    if ip.version != 6:
        return False
    return any(ip in net for net in _SSRF_DENIED_IPV6_NETWORKS)


def _any_non_public(ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address]) -> bool:
    for ip in ips:
        if _ipv6_in_explicit_denylist(ip):
            return True
        if (
            ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_loopback
        ):
            return True
    return False


def validate_bridge_webhook_base_url(raw: str) -> str:
    """
    Validate ``BRIDGE_WEBHOOK_BASE_URL`` for Microsoft/Google webhook registration.

    - Requires a valid http(s) URL with a host.
    - Rejects hosts whose *non-loopback* resolution includes private/link-local space.
    - Allows ``http`` only when the host resolves exclusively to loopback (local dev).
    - For internet-facing hosts, requires ``https``.
    """
    base = (raw or "").strip().rstrip("/")
    if not base:
        raise BridgeURLValidationError("BRIDGE_WEBHOOK_BASE_URL is empty")

    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https"):
        raise BridgeURLValidationError(
            f"BRIDGE_WEBHOOK_BASE_URL must use http or https (got scheme={parsed.scheme!r})"
        )
    host = parsed.hostname
    if not host:
        raise BridgeURLValidationError("BRIDGE_WEBHOOK_BASE_URL is missing a hostname")

    ips = _resolve_ips(host)
    if _all_loopback(ips):
        if parsed.scheme != "http" and parsed.scheme != "https":
            pass  # unreachable
        return base

    if _any_non_public(ips):
        raise BridgeURLValidationError(
            f"BRIDGE_WEBHOOK_BASE_URL host {host!r} resolves to a non-public address "
            "(private/link-local/reserved/multicast are not allowed)"
        )

    if parsed.scheme != "https":
        raise BridgeURLValidationError(
            "BRIDGE_WEBHOOK_BASE_URL must use https for non-loopback hosts"
        )

    return base


def assert_url_allowed_prefix(
    url: str, allowed_prefixes: tuple[str, ...], *, what: str
) -> None:
    """
    Ensure ``url`` is strictly under one of ``allowed_prefixes`` (character prefix match after
    normalisation). Used for delta / pagination links stored in Redis.
    """
    u = (url or "").strip()
    if not u:
        raise BridgeURLValidationError(f"{what}: empty URL")
    parsed = urlparse(u)
    if parsed.scheme not in ("https",):
        raise BridgeURLValidationError(
            f"{what}: only https URLs are allowed (got {parsed.scheme!r})"
        )
    host = (parsed.hostname or "").lower()
    if host:
        try:
            ips = _resolve_ips(host)
            if _any_non_public(ips) and not _all_loopback(ips):
                raise BridgeURLValidationError(
                    f"{what}: host {host!r} resolves to a non-public address"
                )
        except BridgeURLValidationError:
            raise
        except Exception as e:
            log.warning("%s: resolution check failed for %r: %s", what, host, e)

    ok = any(u.startswith(p) for p in allowed_prefixes)
    if not ok:
        raise BridgeURLValidationError(
            f"{what}: URL must start with one of {allowed_prefixes!r} (got {u[:120]!r}...)"
        )


# ---------------------------------------------------------------------------
# Extractor URL validation — SSRF guard for ingestion extractor outbound calls
# ---------------------------------------------------------------------------


def validate_extractor_url(url: str, *, what: str = "extractor") -> str:
    """
    Validate a URL before an extractor makes an outbound HTTP request.

    Extractor engines (Miro, Lucidchart, etc.) accept a ``base_url`` parameter
    that an attacker could point at internal network resources.  This guard
    rejects URLs that resolve to private, loopback, link-local, reserved,
    multicast, or AWS/cloud metadata IPs before any bytes leave the machine.

    Returns *url* unchanged on success.  Raises ``BridgeURLValidationError``
    on failure.
    """
    raw = (url or "").strip()
    if not raw:
        raise BridgeURLValidationError(f"{what}: empty URL")

    parsed = urlparse(raw)
    if parsed.scheme not in ("https",):
        raise BridgeURLValidationError(
            f"{what}: only https URLs are allowed (got scheme={parsed.scheme!r})"
        )
    host = parsed.hostname
    if not host:
        raise BridgeURLValidationError(f"{what}: URL missing hostname: {raw!r}")

    try:
        ips = _resolve_ips(host)
    except BridgeURLValidationError:
        raise
    except Exception as e:
        log.warning("%s: DNS resolution failed for %r: %s", what, host, e)
        raise BridgeURLValidationError(
            f"{what}: could not resolve host {host!r}: {e}"
        ) from e

    if _any_non_public(ips):
        raise BridgeURLValidationError(
            f"{what}: host {host!r} resolves to a non-public address "
            f"(private/link-local/reserved/multicast/loopback)"
        )

    return raw


# ---------------------------------------------------------------------------
# Webhook payload URL validation — SSRF guard for incoming webhook payloads
# ---------------------------------------------------------------------------

# Known-safe Microsoft Graph resource path prefixes
GRAPH_RESOURCE_PREFIXES = (
    "/sites/",
    "/users/",
    "/groups/",
    "/drives/",
    "/me/",
)

ALLOWED_WEBHOOK_URL_PREFIXES = (
    "https://graph.microsoft.com/",
    "https://www.googleapis.com/",
    "https://content.dropboxapi.com/",
    "https://api.dropbox.com/",
)


def validate_webhook_payload_url(
    url: str,
    *,
    field_name: str = "resource",
) -> str:
    """
    Validate a URL extracted from a webhook notification payload against SSRF
    attacks.  Accepts either a fully-qualified URL or a resource path.

    *Fully-qualified URLs* must use HTTPS and must not resolve to private,
    loopback, link-local, reserved, or multicast IP addresses.

    *Resource paths* (relative, no scheme) must match a known-safe Microsoft
    Graph resource prefix (``/sites/``, ``/users/``, ``/groups/``, ``/drives/``,
    ``/me/``).

    Returns the validated URL on success.  Raises ``BridgeURLValidationError``
    with a descriptive message on failure.
    """
    raw = (url or "").strip()
    if not raw:
        raise BridgeURLValidationError(f"webhook {field_name}: empty URL")

    parsed = urlparse(raw)

    # Relative resource path — validate against known-safe prefixes
    if not parsed.scheme and not parsed.hostname:
        ok_prefix = any(raw.startswith(p) for p in GRAPH_RESOURCE_PREFIXES)
        if not ok_prefix:
            raise BridgeURLValidationError(
                f"webhook {field_name}: resource path {raw!r} does not match "
                f"any known-safe prefix {GRAPH_RESOURCE_PREFIXES!r}"
            )
        return raw

    # Fully-qualified URL — enforce HTTPS and SSRF IP checks
    if parsed.scheme not in ("https",):
        raise BridgeURLValidationError(
            f"webhook {field_name}: only https URLs are allowed, got scheme={parsed.scheme!r}"
        )
    host = parsed.hostname
    if not host:
        raise BridgeURLValidationError(
            f"webhook {field_name}: URL missing hostname: {raw!r}"
        )
    try:
        ips = _resolve_ips(host)
        # Webhook payload URLs come from external sources — always reject
        # loopback, private, link-local, reserved, and multicast IPs.
        if _any_non_public(ips):
            raise BridgeURLValidationError(
                f"webhook {field_name}: host {host!r} resolves to a non-public "
                f"address (private/link-local/reserved/multicast/loopback)"
            )
    except BridgeURLValidationError:
        raise
    except Exception as e:
        log.warning(
            "webhook %s: DNS resolution check failed for %r: %s",
            field_name,
            host,
            e,
        )

    # Also verify against allowed URL prefixes
    ok_prefix = any(raw.startswith(p) for p in ALLOWED_WEBHOOK_URL_PREFIXES)
    if not ok_prefix:
        raise BridgeURLValidationError(
            f"webhook {field_name}: URL must start with one of "
            f"{ALLOWED_WEBHOOK_URL_PREFIXES!r} (got {raw[:120]!r}...)"
        )
    return raw
