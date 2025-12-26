from __future__ import annotations

from dataclasses import dataclass
from typing      import Any, Dict, List

from infra.client import HttpClient


@dataclass(frozen = True)
class Repository:

    base_url: str

    client: HttpClient

    @staticmethod
    def build(base_url: str, timeout: float = 15.0) -> Repository:

        client = HttpClient(base_url, "user", "pL5vY8sJcT3eGbU6", timeout)

        return Repository(base_url = base_url.rstrip("/"), client = client)

    def list_projects(self, status: list | None = None) -> dict:

        if status:

            param = '?' + '&'.join([f'status={s}' for s in status])

        else:

            param = ''

        url = f"{self.base_url}/annotation/project{param}"

        return self.client.get(url)

    def list_cases(self, project_id: str, status: list | None = None) -> dict:

        if status:

            param = '?' + '&'.join([f'status={s}' for s in status])

        else:

            param = ''

        url = f"{self.base_url}/annotation/project/{project_id}/case{param}"

        return self.client.get(url)

    def list_images(self, project_id: str, case_id: str, status: list | None = None) -> dict:

        if status:

            param = '?' + '&'.join([f'status={s}' for s in status])

        else:

            param = ''

        url = f"{self.base_url}/annotation/project/{project_id}/case/{case_id}/image{param}"
        return self.client.get(url)

    def download_image(self, image_id: str, save_path: str):

        url = f"{self.base_url}/annotation/image?id={image_id}"

        self.client.download(url, save_path)

    def update(self, *, project_id: str, case_id: str, image_id: str, data: dict, status) -> Dict[str, Any]:

        url = f"{self.base_url}/annotation/project/{project_id}/case/{case_id}/image/{image_id}"

        payload = { "annotations": data, "status": status }

        return self.client.put(url, payload)

    def get_image(self, *, project_id: str, case_id: str, image_id: str) -> Dict[str, Any]:

        url = f"{self.base_url}/annotation/project/{project_id}/case/{case_id}/image/{image_id}"

        return self.client.get(url)

    @staticmethod
    def _as_list(data: Any) -> List[dict]:

        if isinstance(data, list):

            return data

        if isinstance(data, dict):

            for key in ("data", "items", "results"):

                v = data.get(key)

                if isinstance(v, list):

                    return v

        return []
