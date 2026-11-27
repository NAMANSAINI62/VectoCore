"""Read-only Web Fetch MCP server (`fetch__get_page`) with strict SSRF & DNS-rebinding protection."""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("fetch")

_MAX_BYTES = 2_097_152
_TIMEOUT_SEC = 10.0
_MAX_REDIRECTS = 5
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


def _strip_html_fragment(fragment: str, *, strip_chrome: bool = True, strip_header: bool = True) -> str:
    cleaned = re.sub(r"<!--.*?-->", " ", fragment, flags=re.DOTALL)
    cleaned = re.sub(
        r"<(script|style|noscript|template|svg|iframe)[^>]*>.*?</\1>",
        " ",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if strip_chrome:
        chrome_tags = "nav|header|footer|aside" if strip_header else "nav|footer|aside"
        cleaned = re.sub(
            rf"<({chrome_tags})[^>]*>.*?</\1>",
            " ",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_meta_description(raw_html: str) -> str:
    patterns = (
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
    )
    for pat in patterns:
        m = re.search(pat, raw_html, re.IGNORECASE)
        if m:
            desc = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
            if len(desc) >= 20:
                return desc[:400]
    return ""


def _html_to_text(raw_html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", html.unescape(title_match.group(1))).strip() if title_match else ""
    meta_desc = _extract_meta_description(raw_html)

    body_text = ""
    for tag in ("main", "article"):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", raw_html, re.IGNORECASE | re.DOTALL)
        if m:
            candidate = _strip_html_fragment(m.group(1), strip_chrome=True, strip_header=False)
            if len(candidate) >= 200:
                body_text = candidate
                break

    if not body_text:
        body_text = _strip_html_fragment(raw_html, strip_chrome=True, strip_header=True)
    if len(body_text) < 200:
        fallback_text = _strip_html_fragment(raw_html, strip_chrome=True, strip_header=False)
        if len(fallback_text) > len(body_text):
            body_text = fallback_text
    if len(body_text) < 120:
        plain_text = _strip_html_fragment(raw_html, strip_chrome=False)
        if len(plain_text) > len(body_text):
            body_text = plain_text

    if meta_desc and meta_desc.lower() not in body_text[:600].lower():
        body_text = f"{meta_desc} — {body_text}" if body_text else meta_desc

    return title[:120], body_text


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
                headers={
                    "Host": parsed.netloc,
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                    "Accept-Language": "en-US,en;q=0.9",
                },
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
                    remaining = _MAX_BYTES - total
                    if remaining <= 0:
                        break
                    if len(chunk) > remaining:
                        chunks.append(chunk[:remaining])
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                raw_text = b"".join(chunks).decode("utf-8", errors="ignore")
                title, text = _html_to_text(raw_text) if ctype == "text/html" else (hostname, raw_text.strip())
                return {"source_url": current_url, "title": title or hostname, "content": text[:3500]}

    raise ValueError("Too many redirects.")


@mcp.tool()
async def get_page(url: str) -> str:
    """Fetch and return readable text from a public HTTP/HTTPS web page."""
    try:
        data = await fetch_public_page(url)
        return json.dumps(data, ensure_ascii=False)
    except PermissionError as exc:
        raise ToolError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        reason = exc.response.reason_phrase or "Error"
        raise ToolError(f"HTTP {code} {reason}: target site rejected automated fetch.") from exc
    except httpx.TimeoutException as exc:
        raise ToolError("Request timed out while fetching the page.") from exc
    except (ValueError, httpx.HTTPError) as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
