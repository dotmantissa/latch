"""Adversarial proxy admission checks. No live provider/source result is mocked."""

from datetime import UTC, datetime, timedelta

import pytest

from services.supervisor.egress import Denied, EgressPolicy, parse_headers, public_socket


def policy():
    return EgressPolicy({
        "pages": ["https://vendor.example.com/offer"],
        "asset_origins": ["https://assets.example.com"],
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    })


@pytest.mark.parametrize("authority", [
    "169.254.169.254:443", "127.0.0.1:443", "vendor.example.com:22",
    "vendor.example.com:443@10.0.0.1", "vendor.example.com.:443", "[::1]:443",
])
def test_connect_cannot_reach_unreviewed_host_or_port(authority):
    with pytest.raises(Denied):
        policy().connect_host(authority)


@pytest.mark.parametrize("method,target,extra", [
    ("POST", "/offer", {}), ("GET", "/other", {}), ("GET", "/offer?secret=x", {}),
    ("GET", "//169.254.169.254/", {}), ("GET", "/%252e%252e/offer", {}),
    ("GET", "/offer", {"authorization": "policy-only"}),
    ("GET", "/offer", {"cookie": "policy-only"}),
    ("GET", "/offer", {"content-length": "2"}),
    ("GET", "/offer", {"transfer-encoding": "chunked"}),
    ("GET", "/offer", {"host": "other.example.com"}),
    ("GET", "/offer", {"upgrade": "websocket"}),
])
def test_request_denies_authority_body_and_path_expansion(method, target, extra):
    with pytest.raises(Denied):
        policy().request("vendor.example.com", method, target,
                         {"host": "vendor.example.com", **extra})


def test_exact_page_and_bounded_asset_are_admitted():
    value = policy()
    assert value.connect_host("vendor.example.com:443") == "vendor.example.com"
    assert value.request("vendor.example.com", "GET", "/offer",
                         {"host": "vendor.example.com"}).endswith("/offer")
    assert value.request("assets.example.com", "GET", "/style.css",
                         {"host": "assets.example.com", "sec-fetch-dest": "style"})
    with pytest.raises(Denied):
        value.request("assets.example.com", "GET", "/style.css",
                      {"host": "assets.example.com", "sec-fetch-dest": "document"})


@pytest.mark.parametrize("raw_headers", [
    b"GET /offer HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n",
    b"GET /offer HTTP/1.1\r\n Host: a\r\n\r\n",
    b"GET /offer HTTP/1.1\r\nHost : a\r\n\r\n",
    b"GET /offer HTTP/1.1\r\nHost: a\x00b\r\n\r\n",
    b"GET /offer HTTP/1.1\r\nHost: a\x7fb\r\n\r\n",
    b"GET  /offer HTTP/1.1\r\nHost: a\r\n\r\n",
    b"GET /offer HTTP/1.0\r\nHost: a\r\n\r\n",
    b"GET /offer HTTP/1.1\nHost: a\n\n",
    b"GET /offer HTTP/1.1\r\nHost: a\r\n" + b"x" * 16384 + b"\r\n\r\n",
])
def test_ambiguous_or_oversized_http_headers_are_denied(raw_headers):
    with pytest.raises(Denied):
        parse_headers(raw_headers)


def test_normal_connect_headers_parse_and_expired_policy_stops_requests():
    assert parse_headers(b"CONNECT vendor.example.com:443 HTTP/1.1\r\n"
                         b"Host: vendor.example.com:443\r\n\r\n") == (
        "CONNECT", "vendor.example.com:443", {"host": "vendor.example.com:443"}
    )
    value = policy()
    value.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(Denied):
        value.connect_host("vendor.example.com:443")


def test_expired_connection_budget_is_rejected_before_dns_or_socket():
    with pytest.raises(Denied, match="CONNECTION_DEADLINE"):
        public_socket("vendor.example.com", 0)
