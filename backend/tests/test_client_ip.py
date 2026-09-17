import unittest
from unittest.mock import MagicMock

from app.core.client_ip import get_client_ip


def _fake_request(headers: dict[str, str] | None = None, client_host: str | None = "127.0.0.1"):
    request = MagicMock()
    request.headers = headers or {}
    request.client = MagicMock(host=client_host) if client_host else None
    return request


class GetClientIpTest(unittest.TestCase):
    def test_prefers_cf_connecting_ip_header(self) -> None:
        request = _fake_request({"cf-connecting-ip": "203.0.113.9"}, client_host="10.0.0.1")
        self.assertEqual(get_client_ip(request), "203.0.113.9")

    def test_falls_back_to_x_forwarded_for_first_value(self) -> None:
        request = _fake_request({"x-forwarded-for": "203.0.113.5, 10.0.0.1"}, client_host="10.0.0.1")
        self.assertEqual(get_client_ip(request), "203.0.113.5")

    def test_falls_back_to_direct_client_when_no_proxy_headers(self) -> None:
        request = _fake_request({}, client_host="127.0.0.1")
        self.assertEqual(get_client_ip(request), "127.0.0.1")

    def test_returns_unknown_when_nothing_available(self) -> None:
        request = _fake_request({}, client_host=None)
        self.assertEqual(get_client_ip(request), "unknown")

    def test_cf_header_wins_over_x_forwarded_for(self) -> None:
        request = _fake_request(
            {"cf-connecting-ip": "203.0.113.9", "x-forwarded-for": "198.51.100.1"},
            client_host="10.0.0.1",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.9")


if __name__ == "__main__":
    unittest.main()
