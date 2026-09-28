"""Explicit, bounded material extraction. Saved originals are never replaced."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .workspace import web_url

MAX_TEXT = 80000


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.hidden += 1
        if tag in ("p", "div", "h1", "h2", "h3", "li", "br", "article") and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def fetch_page(url):
    """Pin a validated public IP for every request, including redirects."""
    for _ in range(5):
        parsed = urlsplit(web_url(url))
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError("资料链接不能读取本机、内网或特殊网络地址")
        sock = socket.create_connection((addresses[0][4][0], port), timeout=12)
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=12)
        try:
            if parsed.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
            connection.sock = sock
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request("GET", target, headers={"User-Agent": "Personal-OS/0.2 material reader", "Accept": "text/html,text/plain"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("网页重定向缺少目标地址")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f"网页读取失败（HTTP {response.status}）")
            mime = response.getheader("Content-Type", "").lower()
            if not any(kind in mime for kind in ("text/html", "text/plain", "application/xhtml+xml")):
                raise ValueError("链接不是可提取的网页正文；PDF 请保存原文件，视频仅保留链接")
            body = response.read(2_000_001)
            encoding = response.headers.get_content_charset() or "utf-8"
            try:
                text = body[:2_000_000].decode(encoding, errors="replace")
            except LookupError:
                text = body[:2_000_000].decode("utf-8", errors="replace")
            if "text/plain" not in mime:
                parser = PageText(); parser.feed(text)
                text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
            if not text.strip():
                raise ValueError("未提取到正文，网页可能依赖登录或 JavaScript")
            return {"status": "partial", "note": f"已提取网页静态文字（{min(len(text), MAX_TEXT)} 字）；不含动态内容、视频或完整页面语义",
                    "pages": [{"page": None, "text": text[:MAX_TEXT]}], "url": url,
                    "fingerprint": hashlib.sha256(body).hexdigest()}
        finally:
            connection.close()
            sock.close()
    raise ValueError("网页重定向过多")


def extract_pdf(body):
    root = Path(__file__).resolve().parent
    executable = next((path for path in (root / "PersonalOSPDF", root.parent / "build" / "PersonalOSPDF") if path.is_file()), None)
    if executable is None:
        raise ValueError("PDF 解析器尚未构建；原文件已保留，可下载查看或运行 Mac 构建脚本")
    with tempfile.TemporaryDirectory(prefix="personal-os-pdf-") as folder:
        path = Path(folder) / "original.pdf"
        path.write_bytes(body)
        process = subprocess.run([str(executable), str(path)], capture_output=True, text=True, timeout=25)
        if process.returncode:
            raise ValueError("PDF 无法解析，可能已加密或文件损坏；原件仍可查看")
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError:
            raise ValueError("PDF 解析器返回格式无效；原件未改动") from None
    pages = []
    remaining = MAX_TEXT
    for page in result.get("pages", []):
        text = page["text"][:remaining]
        if text.strip():
            pages.append({"page": page["page"], "text": text})
            remaining -= len(text)
        if remaining <= 0:
            break
    if not pages:
        raise ValueError("PDF 没有可提取文字，可能是扫描件；首版不做 OCR，原件已保留")
    partial = result.get("truncated") or len(pages) < result["page_count"] or remaining <= 0
    return {"status": "partial" if partial else "parsed", "pages": pages, "page_count": result["page_count"],
            "note": f"已提取 {len(pages)}/{result['page_count']} 页文字；保留页码，不含图表视觉与 OCR" + ("；存在空白、扫描或截断部分" if partial else ""),
            "fingerprint": hashlib.sha256(body).hexdigest()}
