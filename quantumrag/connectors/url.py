"""URL connector for fetching web pages."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from quantumrag.core.errors import ConnectorError
from quantumrag.core.ingest.parser.text import strip_html_tags
from quantumrag.core.logging import get_logger
from quantumrag.core.models import Document, DocumentMetadata, SourceType

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/32"),
]


def _is_private_ip(host: str) -> bool:
    """Check if *host* resolves to a private or reserved IP address.

    Performs DNS resolution and checks ALL returned addresses against the
    blocked ranges.  Returns ``True`` if **any** resolved address is private.
    """
    try:
        addr_infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Cannot resolve – treat as not private (the actual request will fail later).
        return False

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                return True
    return False


def _validate_url(url: str) -> None:
    """Raise :class:`ConnectorError` if *url* targets a private/reserved IP or uses a disallowed scheme."""
    parsed = urlparse(url)

    # Scheme check
    if parsed.scheme not in ("http", "https"):
        raise ConnectorError(
            f"Blocked URL scheme '{parsed.scheme}': only http and https are allowed",
            source=url,
            suggestion="Use an http:// or https:// URL.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise ConnectorError(
            "URL has no hostname",
            source=url,
            suggestion="Provide a valid URL with a hostname.",
        )

    if _is_private_ip(hostname):
        raise ConnectorError(
            f"SSRF protection: URL targets a private/reserved IP ({hostname})",
            source=url,
            suggestion="Only publicly-routable URLs are allowed.",
        )


class URLConnector:
    """Connector that fetches web pages via httpx and extracts text.

    Usage:
        connector = URLConnector(["https://example.com"])
        connector.connect()
        doc = connector.fetch("https://example.com")
    """

    def __init__(
        self,
        urls: list[str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the URL connector.

        Args:
            urls: List of URLs to make available as sources.
            timeout: HTTP request timeout in seconds.
        """
        self._urls: list[str] = list(urls) if urls else []
        self._timeout = timeout

    def connect(self) -> None:
        """Validate URLs (format + SSRF check)."""
        for url in self._urls:
            _validate_url(url)
        logger.info("url_connector_connected", url_count=len(self._urls))

    def list_sources(self) -> list[str]:
        """Return the list of configured URLs."""
        return list(self._urls)

    def add_url(self, url: str) -> None:
        """Add a URL to the source list."""
        self._urls.append(url)

    def fetch(self, source_id: str) -> Document:
        """Fetch a URL and extract text content.

        Args:
            source_id: The URL to fetch.

        Returns:
            Parsed Document with extracted text.

        Raises:
            ConnectorError: If fetching or parsing fails.
        """
        import httpx

        _validate_url(source_id)

        try:
            response = httpx.get(
                source_id,
                timeout=self._timeout,
                follow_redirects=True,
                headers={"User-Agent": "QuantumRAG/0.1"},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ConnectorError(
                f"Failed to fetch URL: {e}",
                source=source_id,
            ) from e

        html_content = response.text

        # Extract metadata
        title = _extract_title(html_content) or source_id
        description = _extract_meta_description(html_content)

        # Convert HTML to clean text
        clean_text = strip_html_tags(html_content)

        custom: dict[str, str] = {"url": source_id}
        if description:
            custom["description"] = description

        return Document(
            content=clean_text,
            metadata=DocumentMetadata(
                source_type=SourceType.URL,
                title=title,
                custom=custom,
            ),
            raw_bytes=response.content,
        )


def _extract_title(html_content: str) -> str | None:
    """Extract <title> from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    if match:
        import html

        return html.unescape(match.group(1)).strip()
    return None


def _extract_meta_description(html_content: str) -> str | None:
    """Extract meta description from HTML."""
    match = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        html_content,
        re.IGNORECASE,
    )
    if match:
        import html

        return html.unescape(match.group(1)).strip()
    return None
