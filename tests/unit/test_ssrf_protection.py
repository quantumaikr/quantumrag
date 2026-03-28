"""Tests for SSRF protection in the URL connector (E1.4)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from quantumrag.connectors.url import URLConnector, _is_private_ip, _validate_url
from quantumrag.core.errors import ConnectorError


class TestIsPrivateIp:
    """Unit tests for _is_private_ip helper."""

    def _mock_getaddrinfo(self, ip: str):
        """Return a mock getaddrinfo result for a single IPv4 address."""
        return [(2, 1, 6, "", (ip, 0))]

    def test_loopback_127(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("127.0.0.1")
            assert _is_private_ip("evil.example.com") is True

    def test_loopback_127_other(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("127.0.0.2")
            assert _is_private_ip("evil.example.com") is True

    def test_ten_network(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("10.0.0.1")
            assert _is_private_ip("internal.example.com") is True

    def test_172_16_network(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("172.16.5.4")
            assert _is_private_ip("internal.example.com") is True

    def test_192_168_network(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("192.168.1.1")
            assert _is_private_ip("router.local") is True

    def test_link_local(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("169.254.169.254")
            assert _is_private_ip("metadata.example.com") is True

    def test_zero_address(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("0.0.0.0")
            assert _is_private_ip("zero.example.com") is True

    def test_ipv6_loopback(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = [(10, 1, 6, "", ("::1", 0, 0, 0))]
            assert _is_private_ip("ipv6-loopback.example.com") is True

    def test_ipv6_link_local(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = [(10, 1, 6, "", ("fe80::1", 0, 0, 0))]
            assert _is_private_ip("ipv6-ll.example.com") is True

    def test_public_ip(self) -> None:
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = self._mock_getaddrinfo("93.184.216.34")
            assert _is_private_ip("example.com") is False

    def test_dns_failure_returns_false(self) -> None:
        import socket

        with patch(
            "quantumrag.connectors.url.socket.getaddrinfo",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            assert _is_private_ip("nonexistent.invalid") is False

    def test_multiple_results_one_private(self) -> None:
        """If any resolved address is private, return True."""
        with patch("quantumrag.connectors.url.socket.getaddrinfo") as mock:
            mock.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 0)),
                (2, 1, 6, "", ("127.0.0.1", 0)),
            ]
            assert _is_private_ip("dual.example.com") is True


class TestValidateUrl:
    """Tests for _validate_url."""

    def test_ftp_scheme_blocked(self) -> None:
        with pytest.raises(ConnectorError, match="Blocked URL scheme"):
            _validate_url("ftp://example.com/file.txt")

    def test_file_scheme_blocked(self) -> None:
        with pytest.raises(ConnectorError, match="Blocked URL scheme"):
            _validate_url("file:///etc/passwd")

    def test_gopher_scheme_blocked(self) -> None:
        with pytest.raises(ConnectorError, match="Blocked URL scheme"):
            _validate_url("gopher://evil.com/")

    def test_no_hostname(self) -> None:
        with pytest.raises(ConnectorError, match="no hostname"):
            _validate_url("http://")

    def test_private_ip_blocked(self) -> None:
        with (
            patch("quantumrag.connectors.url._is_private_ip", return_value=True),
            pytest.raises(ConnectorError, match="SSRF protection"),
        ):
            _validate_url("https://internal-service.local/api")

    def test_public_url_allowed(self) -> None:
        with patch("quantumrag.connectors.url._is_private_ip", return_value=False):
            _validate_url("https://example.com/page")  # should not raise

    def test_http_scheme_allowed(self) -> None:
        with patch("quantumrag.connectors.url._is_private_ip", return_value=False):
            _validate_url("http://example.com/page")  # should not raise


class TestURLConnectorSSRF:
    """Integration-level tests for SSRF checks in URLConnector."""

    def test_connect_rejects_private_url(self) -> None:
        with patch("quantumrag.connectors.url._is_private_ip", return_value=True):
            connector = URLConnector(urls=["https://internal.local/secret"])
            with pytest.raises(ConnectorError, match="SSRF protection"):
                connector.connect()

    def test_fetch_rejects_private_url(self) -> None:
        with patch("quantumrag.connectors.url._is_private_ip", return_value=True):
            connector = URLConnector()
            with pytest.raises(ConnectorError, match="SSRF protection"):
                connector.fetch("https://169.254.169.254/latest/meta-data/")

    def test_connect_rejects_bad_scheme(self) -> None:
        connector = URLConnector(urls=["ftp://evil.com/file"])
        with pytest.raises(ConnectorError, match="Blocked URL scheme"):
            connector.connect()
