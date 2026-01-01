from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.services import ProjectService
from infra.scheduler import Scheduler

logger = logging.getLogger(__name__)


class ExplorerController(QObject):
    """资源浏览器的 Controller：仅负责调度异步任务与把结果回传给 View。"""

    # 信号定义：完全不包含 Repo/Task 等底层对象
    file_list_loaded = Signal(str, dict, dict)  # level(req_type), response_data, request_params
    file_list_error = Signal(str)

    thumbnail_ready = Signal(str, str)  # image_id, local_path
    thumbnail_error = Signal(str)

    def __init__(self, service: ProjectService, scheduler: Scheduler):
        super().__init__()
        self._service = service
        self._scheduler = scheduler

        self._scheduler.task_result.connect(self._on_task_result)
        self._scheduler.task_error.connect(self._on_task_error)

        # request_id -> (type, context_data)
        self._req_map: dict[int, tuple[str, dict]] = { }

    @Slot(str, dict, list)
    def fetch_list(self, level: str, params: dict, status_filters: list) -> None:
        """View 请求加载列表数据。"""

        def task():
            if level == "project":
                return self._service.list_projects(status_filters)
            if level == "case":
                return self._service.list_cases(str(params.get("project_id")), status_filters)
            if level == "image":
                return self._service.list_images(
                    str(params.get("project_id")),
                    str(params.get("case_id")),
                    status_filters,
                )
            return { "code": 200, "data": [] }

        token = self._scheduler.submit(fn = task, generation = 0)
        self._req_map[token.request] = (level, params)

    @Slot(str, str)
    def download_thumbnail(self, image_id: str, save_path: str) -> None:
        """View 请求下载缩略图。"""

        def task():
            return self._service.download_image(image_id, save_path)

        token = self._scheduler.submit(fn = task, generation = 0)
        self._req_map[token.request] = ("download", { "image_id": image_id })

    @Slot(int, int, object)
    def _on_task_result(self, request_id: int, generation: int, result: object) -> None:
        if request_id not in self._req_map:
            return

        req_type, context = self._req_map.pop(request_id)

        if req_type == "download":
            image_id = context.get("image_id")
            self.thumbnail_ready.emit(image_id, result)
        else:
            self.file_list_loaded.emit(req_type, result, context)

    @Slot(int, int, object)
    def _on_task_error(self, request_id: int, generation: int, err: object) -> None:
        if request_id not in self._req_map:
            return

        req_type, _context = self._req_map.pop(request_id)
        logger.exception("ExplorerController task failed: req_type=%s", req_type)

        if req_type == "download":
            self.thumbnail_error.emit(str(err))
        else:
            self.file_list_error.emit(str(err))
