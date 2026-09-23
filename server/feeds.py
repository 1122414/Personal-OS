"""Small RSS/Atom reader for user-configured intelligence channels."""

from __future__ import annotations

import ipaddress
import html
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


MAX_FEED_BYTES = 2_000_000


def _public_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("信息源必须是公开的 HTTP(S) RSS/Atom 地址")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("无法解析信息源地址") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("信息源不能指向本机或内网地址")
    return url.strip()


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _public_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch_feed(url: str) -> list[dict[str, str]]:
    url = _public_url(url)
    opener = urllib.request.build_opener(SafeRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "Personal-OS/0.1 RSS reader"})
    with opener.open(request, timeout=12) as response:
        content = response.read(MAX_FEED_BYTES + 1)
    if len(content) > MAX_FEED_BYTES:
        raise ValueError("信息源内容过大")
    return parse_feed(content)


def parse_feed(content: bytes) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("信息源不是有效 RSS/Atom") from exc
    items = []
    entries = root.findall(".//item")
    atom = False
    if not entries:
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        atom = True
    for entry in entries[:100]:
        if atom:
            namespace = "{http://www.w3.org/2005/Atom}"
            title = (entry.findtext(namespace + "title") or "").strip()
            summary = (entry.findtext(namespace + "summary") or entry.findtext(namespace + "content") or "").strip()
            link = next((node.attrib.get("href", "") for node in entry.findall(namespace + "link") if node.attrib.get("rel", "alternate") == "alternate"), "")
            published = entry.findtext(namespace + "published") or entry.findtext(namespace + "updated") or ""
        else:
            title = (entry.findtext("title") or "").strip()
            summary = (entry.findtext("description") or "").strip()
            link = (entry.findtext("link") or "").strip()
            published = entry.findtext("pubDate") or ""
        if title and link:
            plain = html.unescape(re.sub(r"<[^>]+>", " ", summary))
            items.append({"title": html.unescape(title)[:300], "summary": " ".join(plain.split())[:2000], "url": link[:2000], "published": published[:100]})
    return items
