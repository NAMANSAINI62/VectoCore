"""Read-only Web Fetch MCP server (`fetch__get_page`) with strict SSRF & DNS-rebinding protection."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("fetch")

_MAX_BYTES = 1_048_576
_TIMEOUT_SEC = 10.0
_MAX_REDIRECTS = 3
_USER_AGENT = "VectoCoreBot/1.0 (+https://github.com/NAMANSAINI62/VectoCore)"


def validate_public_ip(ip_str: str) -> None:
    """Raise PermissionError if an IP address is private, loopback, link-local, multicast, or unspecified."""
    addr = ipaddress.ip_address(ip_str)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
        or addr.is_reserved
    ):
        raise PermissionError(f"SSRF blocked: non-public IP '{ip_str}' is not allowed.")


def resolve_and_validate_host(hostname: str) -> str:
    """Resolve hostname and validate all returned IPs; return the first safe IP."""
    if not hostname or hostname.lower() in ("localhost", "localhost.localdomain"):
        raise PermissionError(f"SSRF blocked: host '{hostname}' is not allowed.")
    infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    if not infos:
        raise PermissionError(f"SSRF blocked: could not resolve '{hostname}'.")
    safe_ips: list[str] = []
    for info in infos:
        ip_str = str(info[4][0])
        validate_public_ip(ip_str)
        safe_ips.append(ip_str)
    return safe_ips[0]


def _html_to_text(raw_html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    cleaned = re.sub(r"<!--.*?-->", " ", raw_html, flags=re.DOTALL)
    cleaned = re.sub(r"<(script|style|noscript|template)[^>]*>.*?</\1>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return title[:120], cleaned


async def fetch_public_page(url: str) -> dict[str, str]:
    """Fetch a public http/https page with DNS-rebinding & redirect SSRF checks."""
    current_url = url.strip()
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current_url)
        if parsed.scheme not in ("http", "https"):
            raise PermissionError(f"Scheme '{parsed.scheme}' is not allowed.")
        hostname = parsed.hostname or ""
        checked_ip = resolve_and_validate_host(hostname)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        netloc = f"[{checked_ip}]:{port}" if ":" in checked_ip else f"{checked_ip}:{port}"
        connect_url = parsed._replace(netloc=netloc).geturl()

        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC, follow_redirects=False) as client:
            async with client.stream(
                "GET",
                connect_url,
                headers={"Host": parsed.netloc, "User-Agent": _USER_AGENT},
                extensions={"sni_hostname": hostname} if parsed.scheme == "https" else None,
            ) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        raise ValueError("Redirect without Location header.")
                    current_url = urljoin(current_url, loc)
                    continue
                resp.raise_for_status()
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if ctype not in ("text/html", "text/plain"):
                    raise PermissionError(f"Disallowed content-type '{ctype}'.")
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_BYTES:
                        raise ValueError("Response exceeded 1 MB download limit.")
                    chunks.append(chunk)
                raw_text = b"".join(chunks).decode("utf-8", errors="ignore")
                title, text = _html_to_text(raw_text) if ctype == "text/html" else (hostname, raw_text.strip())
                return {"source_url": current_url, "title": title or hostname, "content": text[:1600]}

    raise ValueError("Too many redirects.")


@mcp.tool()
async def get_page(url: str) -> str:
    """Fetch and return readable text from a public HTTP/HTTPS web page."""
    data = await fetch_public_page(url)
    return json.dumps(data)


if __name__ == "__main__":
    mcp.run()
