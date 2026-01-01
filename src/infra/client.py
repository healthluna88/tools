# src/infra/client.py

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        # 初始为空，等待 set_credentials
        self._username = ""
        self._password = ""
        self._timeout = timeout

        self._token: Optional[str] = None
        self._lock = threading.Lock()

    def set_credentials(self, username: str, password: str) -> None:
        with self._lock:
            self._username = username
            self._password = password
            self._token = None  # 重置 token

    def login(self) -> None:
        """公开的登录接口，用于 UI 显式调用"""
        self._login()

    def get(self, url: str, params: Optional[dict] = None) -> dict:
        response = self._request("GET", url, params = params)
        return response.json()

    def post(self, url: str, payload: dict) -> dict:
        response = self._request("POST", url, json = payload)
        try:
            return response.json()
        except Exception:
            return { }

    def put(self, url: str, payload: dict) -> dict:
        response = self._request("PUT", url, json = payload)
        try:
            return response.json()
        except Exception:
            return { }

    def download(self, url: str, save_path: str) -> str:
        response = self._request("GET", url, stream = True)

        total = response.headers.get("Content-Length")
        total_bytes = int(total) if total and total.isdigit() else None

        downloaded = 0
        os.makedirs(os.path.dirname(save_path), exist_ok = True)

        tmp_path = save_path + ".part"

        try:
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(256 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

            os.replace(tmp_path, save_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

        if total_bytes is not None and downloaded != total_bytes:
            raise IOError(f"Incomplete download: {downloaded}/{total_bytes} bytes")

        return save_path

    def _login(self) -> None:
        with self._lock:
            if not self._username or not self._password:
                raise ValueError("Credentials not set")

            url = f"{self._base_url}/login"
            payload = { "username": self._username, "password": self._password }

            # 登录请求通常不需要 Token Header，避免死循环
            response = requests.post(url, json = payload, timeout = self._timeout)
            response.raise_for_status()

            data = response.json()
            token = data.get("token")
            if not token:
                raise ValueError("Login failed: No token received")

            self._token = token

    def _get_headers(self) -> dict:
        headers: dict[str, str] = { }
        with self._lock:
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = dict(kwargs.get("headers", { }) or { })
        headers.update(self._get_headers())
        kwargs["headers"] = headers

        kwargs.setdefault("timeout", self._timeout)

        response = requests.request(method, url, **kwargs)

        # 403/401 触发一次自动登录并重试
        if response.status_code in (401, 403):
            logger.info("Auth required (%s). Trying auto-login.", response.status_code)
            try:
                self._login()
            except Exception:
                # 自动重新登录失败，抛出原始 401/403，由上层捕获处理（例如踢回登录页）
                response.raise_for_status()
                raise

            # 重试
            with self._lock:
                headers["Authorization"] = f"Bearer {self._token}"
            kwargs["headers"] = headers
            response = requests.request(method, url, **kwargs)

        response.raise_for_status()
        return response