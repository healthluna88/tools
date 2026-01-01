# src/app/controller.py

from __future__ import annotations

import logging
import base64

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QSettings

from app.session import WorkspaceSession
from app.services import SegmentationService, ProjectService
from app.states import State, AnnotatingState
from app.workspace import Workspace
from core.ai.segmenter import Segmenter
from infra.repository import Repository
from infra.scheduler import Scheduler

logger = logging.getLogger(__name__)


class Controller(QObject):
    image_selected = Signal(object)
    freeze_ui = Signal(bool, str)
    status_text = Signal(str)
    progress = Signal(int)
    show_error = Signal(str)

    # 登录相关信号
    login_success = Signal()
    login_fail = Signal(str)

    # 实体状态更新信号 (project_id, case_id, image_id, new_status)
    entity_status_updated = Signal(str, str, str, str)

    # [NEW] 工作流结束信号 (status: Submitted/Skipped)
    workflow_finished = Signal(str)

    # (rgba_overlay, binary_mask)
    segment_mask = Signal(np.ndarray, np.ndarray)

    generate_polygon = Signal(object, object)
    polygons_generated = Signal()

    DEBOUNCE_MS = 200

    def __init__(
        self,
        workspace: Workspace,
        base_url: str,
        scheduler: Scheduler,
        repo: Repository | None = None,
        segmenter: Segmenter | None = None,
    ) -> None:
        super().__init__()

        self.workspace = workspace
        self.scheduler = scheduler

        real_repo = repo or Repository.build(base_url.rstrip("/"))
        self.project_service = ProjectService(real_repo)

        self.seg_service: SegmentationService | None
        if segmenter:
            self.seg_service = SegmentationService(segmenter)
        else:
            self.seg_service = None
            logger.warning("Segmenter service initialized without model.")

        self.session = WorkspaceSession()
        self._state: State = AnnotatingState(self)

        # 存储
        self._settings = QSettings("CapitalBio", "AnnotationTool")

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_debounce_timeout)

        self.scheduler.task_result.connect(self._on_task_result)
        self.scheduler.task_error.connect(self._on_task_error)

        self._bg_seg_req: int | None = None
        self._bg_poly_req: int | None = None
        self._bg_login_req: int | None = None

        self._cached_mask_sam: np.ndarray | None = None
        self._cached_mask_binary: np.ndarray | None = None

    @property
    def cached_mask_binary(self) -> np.ndarray | None:
        return self._cached_mask_binary

    def notify_status_update(self, project_id: str, case_id: str, image_id: str, status: str) -> None:
        """当状态机完成保存、提交或废弃操作后调用此方法"""
        self.entity_status_updated.emit(project_id, case_id, image_id, status)

        # [NEW] 如果是终态，发出工作流结束信号
        if status in ("Submitted", "Skipped"):
            self.workflow_finished.emit(status)

    # --- 登录逻辑 ---

    def get_saved_credentials(self) -> tuple[str, str] | None:
        user = self._settings.value("auth/user", "")
        pwd_b64 = self._settings.value("auth/token", "")

        pwd = ""
        if pwd_b64:
            try:
                pwd = base64.b64decode(pwd_b64.encode('utf-8')).decode('utf-8')
            except Exception:
                pass

        if user and pwd:
            return user, pwd
        return None

    @Slot(str, str)
    def request_login(self, user, pwd):
        def task():
            self.project_service.login(user, pwd)
            return { "user": user, "pwd": pwd }

        token = self.scheduler.submit(fn = task, generation = 0)
        self._bg_login_req = token.request

    def _save_credentials(self, user, pwd):
        self._settings.setValue("auth/user", user)
        pwd_b64 = base64.b64encode(pwd.encode('utf-8')).decode('utf-8')
        self._settings.setValue("auth/token", pwd_b64)

    # --- 状态机与任务 ---

    def transition_to(self, new_state: State) -> None:
        logger.info("Transition: %s -> %s", self._state.__class__.__name__, new_state.__class__.__name__)
        self._state.exit()
        self._state = new_state
        self._state.enter()

    @Slot(object)
    def on_image_selected(self, metadata: dict) -> None:
        self._state.on_image_selected(metadata)

    @Slot(object)
    def on_submit_current(self) -> None:
        self._state.on_submit()

    @Slot(object)
    def on_abolish_current(self) -> None:
        self._state.on_abolish()

    @Slot()
    def on_action_generate_polygons(self) -> None:
        if not self.seg_service:
            return

        if self._cached_mask_binary is None:
            self.status_text.emit("无法生成：当前无有效 Mask")
            return

        image = self.workspace.image
        mask = self._cached_mask_binary
        if image is None:
            self.status_text.emit("未加载图像")
            return

        self.freeze_ui.emit(True, "正在执行轮廓提取与简化 (DP算法)...")
        self.status_text.emit("正在生成轮廓...")

        def task():
            return self.seg_service.generate_polygons(image, mask)

        token = self.scheduler.submit(fn = task, generation = 0)
        self._bg_poly_req = token.request

    @Slot(int, int, object)
    def _on_task_result(self, request_id: int, generation: int, result: object) -> None:
        try:
            if request_id == self._bg_login_req:
                creds = result
                self._save_credentials(creds['user'], creds['pwd'])
                self.login_success.emit()
                return

            self._state.handle_result(request_id, result)

            if request_id == self._bg_seg_req:
                if isinstance(result, dict):
                    self._handle_segment_common_result(result)

            if request_id == self._bg_poly_req:
                if isinstance(result, dict):
                    self._handle_manual_polygon_result(result)

        except Exception as e:
            logger.exception("Unexpected error in _on_task_result")
            self.show_error.emit(f"Internal System Error: {str(e)}")
            if not isinstance(self._state, AnnotatingState):
                self.transition_to(AnnotatingState(self))
            else:
                self.freeze_ui.emit(False, "")

    @Slot(int, int, object)
    def _on_task_error(self, request_id: int, generation: int, err: object) -> None:
        try:
            if request_id == self._bg_login_req:
                msg = str(err)
                if "401" in msg or "403" in msg:
                    msg = "用户名或密码错误"
                elif "Connection" in msg:
                    msg = "连接服务器失败"
                self.login_fail.emit(msg)
                return

            self._state.handle_error(request_id, err)

            if request_id in (self._bg_seg_req, self._bg_poly_req):
                if request_id == self._bg_poly_req:
                    self.freeze_ui.emit(False, "")
                msg = str(err)
                logger.exception("Background task failed: request_id=%s", request_id)
                self.status_text.emit("操作失败")
                self.show_error.emit(msg)

        except Exception as e:
            logger.exception("Unexpected error in _on_task_error")
            self.show_error.emit(f"Internal System Error: {str(e)}")
            if not isinstance(self._state, AnnotatingState):
                self.transition_to(AnnotatingState(self))
            else:
                self.freeze_ui.emit(False, "")

    def _handle_segment_image_result(self, result: dict) -> None:
        self._cached_mask_sam = result.get("mask_sam")
        self._cached_mask_binary = result.get("mask_binary")

        embedding = result.get("embedding")
        if embedding is not None:
            self.workspace.set_embedding(embedding)

        self.segment_mask.emit(result.get("rgba_mask"), result.get("mask_binary"))

        polygons = result.get("polygons")
        if polygons is not None:
            self.generate_polygon.emit(result.get("image_ref"), polygons)
            self.workspace.set_polygons(polygons)

    def _handle_segment_common_result(self, result: dict) -> None:
        if result.get("mask_sam") is not None:
            self._cached_mask_sam = result["mask_sam"]

        if "mask_binary" in result:
            self._cached_mask_binary = result.get("mask_binary")

        self.segment_mask.emit(result.get("rgba_mask"), result.get("mask_binary"))

        polygons = result.get("polygons") or []
        self.generate_polygon.emit(result.get("image_ref"), polygons)
        self.workspace.set_polygons(polygons)

    def _handle_manual_polygon_result(self, result: dict) -> None:
        polygons = result.get("polygons")
        self.generate_polygon.emit(result.get("image_ref"), polygons)

        if polygons is not None:
            self.workspace.set_polygons(polygons)
            self.session.dirty = True

        self.status_text.emit("轮廓生成完成")
        self.freeze_ui.emit(False, "")
        self.polygons_generated.emit()

    @Slot(list)
    def on_update_points(self, points: list) -> None:
        self.session.dirty = True
        self.workspace.set_points(points)
        self._schedule_segmentation()

    @Slot(object)
    def on_update_pipeline(self, _ = None) -> None:
        self.session.dirty = True
        if self.workspace.image is not None and self._cached_mask_sam is not None:
            self._run_pipeline_segmentation()

    @Slot(object, object)
    def on_update_polygons(self, image, polygons) -> None:
        self.session.dirty = True
        self.workspace.set_polygons(polygons)
        self.generate_polygon.emit(image, polygons)

    @Slot(object)
    def on_update_polygons_from_canvas(self, polygons) -> None:
        self.session.dirty = True
        self.workspace.set_polygons(polygons)

    def _schedule_segmentation(self) -> None:
        self._timer.start(Controller.DEBOUNCE_MS)

    @Slot()
    def _on_debounce_timeout(self) -> None:
        if not self.seg_service:
            return

        if not isinstance(self._state, AnnotatingState):
            return

        image = self.workspace.image
        if image is None:
            return

        points = self.workspace.points
        pipeline = self.workspace.pipeline

        def task():
            return self.seg_service.segment_points(image, points, pipeline, compute_polygons = False)

        token = self.scheduler.submit(fn = task, generation = 0)
        self._bg_seg_req = token.request

    def _run_pipeline_segmentation(self) -> None:
        if not self.seg_service:
            return

        image = self.workspace.image
        if image is None:
            return

        pipeline = self.workspace.pipeline
        mask_sam = self._cached_mask_sam

        def task():
            return self.seg_service.segment_pipeline(image, mask_sam, pipeline, compute_polygons = False)

        token = self.scheduler.submit(fn = task, generation = 0)
        self._bg_seg_req = token.request