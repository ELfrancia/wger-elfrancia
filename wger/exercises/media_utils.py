# -*- coding: utf-8 -*-
"""
Media security utilities for exercise downloads and path management.
Provides SSRF validation, path traversal protection, and safe streaming downloads.
"""

import ipaddress
import os
import re
import socket
import urllib.parse
from typing import Optional
import requests

MAX_MEDIA_BYTES = 50 * 1024 * 1024  # 50 MB


def is_safe_url(url: str) -> bool:
    """
    Validate that a URL is http/https and does not point to local/private/reserved IP addresses (SSRF protection).
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ('http', 'https'):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        hostname_lower = hostname.lower()
        if hostname_lower in ('localhost', '127.0.0.1', '::1') or hostname_lower.endswith('.local') or hostname_lower.endswith('.internal'):
            return False

        # Resolve hostname to all IP addresses
        addr_infos = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


def sanitize_filename(source_id: str) -> str:
    """
    Sanitize source_id or filename to prevent directory traversal and special chars.
    """
    if source_id is None:
        return ""
    return re.sub(r'[^A-Za-z0-9_-]', '', str(source_id))


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """
    Ensure the target path is strictly contained within the base directory.
    """
    try:
        real_base = os.path.realpath(base_dir)
        real_target = os.path.realpath(target_path)
        return real_target.startswith(real_base + os.sep) or real_target == real_base
    except Exception:
        return False


def safe_download_file(
    url: str,
    destination_path: str,
    base_dir: Optional[str] = None,
    max_bytes: int = MAX_MEDIA_BYTES,
    timeout: int = 20,
    headers: Optional[dict] = None
) -> bool:
    """
    Safely download a file via HTTP(S) with SSRF checks, path validation, timeout,
    and a streaming byte cap.
    """
    if not is_safe_url(url):
        return False

    if base_dir and not is_safe_path(base_dir, destination_path):
        return False

    parent_dir = os.path.dirname(destination_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    req_headers = {"User-Agent": "Mozilla/5.0"}
    if headers:
        req_headers.update(headers)

    try:
        with requests.get(url, headers=req_headers, stream=True, timeout=timeout) as response:
            if response.status_code != 200:
                return False

            cl = response.headers.get('content-length')
            if cl and cl.isdigit() and int(cl) > max_bytes:
                return False

            downloaded = 0
            with open(destination_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            f.close()
                            if os.path.exists(destination_path):
                                os.remove(destination_path)
                            return False
                        f.write(chunk)
        return True
    except Exception:
        if os.path.exists(destination_path):
            try:
                os.remove(destination_path)
            except OSError:
                pass
        return False
