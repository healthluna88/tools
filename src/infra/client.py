from __future__ import annotations

import os
import threading

from typing import Optional

import requests


class HttpClient:

    def __init__(self, base_url: str, username: str, password: str, timeout: float = 15.0) -> None:

        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout  = timeout

        self._token: Optional[str] = None
        self._lock = threading.Lock()

    def get(self, url: str, params: Optional[dict] = None) -> dict:
        # 此时 url 如果是相对路径，最好在外面拼好，或者在这里拼
        # 假设外面传入的是完整 url 或者你依然想保持原样
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

        total = int(response.headers.get("Content-Length", 0))

        downloaded = 0

        os.makedirs(os.path.dirname(save_path), exist_ok = True)

        tmp_path = save_path + '.part'

        try:

            with open(tmp_path, "wb") as f:

                for chunk in response.iter_content(1024 * 128):

                    if chunk:

                        f.write(chunk)

                        downloaded += len(chunk)

            os.replace(tmp_path, save_path)

        except Exception as e:

            print(f"Download failed: {e}")

        if total and downloaded != total:

            raise IOError(f"Incomplete download: {downloaded}/{total} bytes")

        return save_path

    def _login(self) -> None:

        with self._lock:

            url = f"{self._base_url}/login"

            payload = \
                {
                    "username": self._username,
                    "password": self._password
                }

            response = requests.post(url, json = payload, timeout = self._timeout)
            response.raise_for_status()

            self._token = response.json().get("token")

    def _get_headers(self) -> dict:

        headers = { }

        if self._token:

            headers["Authorization"] = f"Bearer {self._token}"

        return headers

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:

        headers = kwargs.get("headers", {})
        headers.update(self._get_headers())

        kwargs["headers"] = headers

        if "timeout" not in kwargs:

            kwargs["timeout"] = self._timeout

        response = requests.request(method, url, **kwargs)

        if response.status_code == 403:

            print(f"Encountered 403, attempting auto login...")

            try:

                self._login()

            except Exception as e:

                print(f"Auto-login failed: {e}")

                response.raise_for_status()

            headers["Authorization"] = f"Bearer {self._token}"

            kwargs["headers"] = headers

            response = requests.request(method, url, **kwargs)

        response.raise_for_status()

        return response
