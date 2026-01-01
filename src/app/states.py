# src/app/states.py

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.controller import Controller

logger = logging.getLogger(__name__)


class State:
    def __init__(self, controller: Controller) -> None:
        self.ctx = controller

    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass

    def on_image_selected(self, metadata: dict) -> None:
        logger.warning("Action 'image_selected' ignored in state %s", self.__class__.__name__)

    def on_submit(self) -> None:
        logger.warning("Action 'submit' ignored in state %s", self.__class__.__name__)

    def on_abolish(self) -> None:
        logger.warning("Action 'abolish' ignored in state %s", self.__class__.__name__)

    def handle_result(self, request_id: int, result: object) -> None:
        pass

    def handle_error(self, request_id: int, error: object) -> None:
        pass


class AnnotatingState(State):
    """标注状态（稳定态）。"""

    def enter(self) -> None:
        self.ctx.status_text.emit("就绪")
        self.ctx.freeze_ui.emit(False, "")
        self.ctx.progress.emit(100)

    def on_image_selected(self, metadata: dict) -> None:
        self.ctx.transition_to(SwitchingState(self.ctx, target_metadata = metadata))

    def on_submit(self) -> None:
        if self.ctx.session.current_metadata:
            self.ctx.transition_to(SubmittingState(self.ctx, status = "Submitted"))

    def on_abolish(self) -> None:
        if self.ctx.session.current_metadata:
            self.ctx.transition_to(SubmittingState(self.ctx, status = "Skipped"))


class WorkflowState(State):
    """工作流状态基类（短暂态）。"""

    def enter(self) -> None:
        # 进入状态时冻结 UI
        self._report_status(self.get_message())
        self.ctx.progress.emit(-1)

    def get_message(self) -> str:
        return "正在处理..."

    def _report_status(self, message: str) -> None:
        """同时更新底部状态栏和中央弹窗"""
        self.ctx.status_text.emit(message)
        self.ctx.freeze_ui.emit(True, message)

    def on_image_selected(self, metadata: dict) -> None:
        self.ctx.status_text.emit("系统繁忙，请稍候...")

    def handle_error(self, request_id: int, error: object) -> None:
        self.ctx.show_error.emit(str(error))
        self.ctx.transition_to(AnnotatingState(self.ctx))


class SwitchingState(WorkflowState):
    """切换图片状态。
    逻辑链：(Check Dirty -> Save Old) -> Load New -> Init Segment
    """

    def __init__(self, controller: Controller, target_metadata: dict) -> None:
        super().__init__(controller)
        self.target_metadata = target_metadata
        self.step = "INIT"  # INIT, SAVE, LOAD, SEGMENT
        self._req_id: int | None = None

    def get_message(self) -> str:
        return "准备切换案例..."

    def enter(self) -> None:
        super().enter()
        self._start_sequence()

    def _start_sequence(self) -> None:
        # 1. 检查是否需要保存
        if self.ctx.session.dirty and self.ctx.session.current_metadata:
            self.step = "SAVE"
            self._report_status("正在同步标注数据到服务器...")

            data = self.ctx.workspace.export_remote_annotations()
            meta = self.ctx.session.current_metadata

            def task():
                return self.ctx.project_service.update_annotations(
                    meta.get("project_id"),
                    meta.get("case_id"),
                    meta.get("id", meta.get("image_id")),
                    data,
                    "Annotating",
                )

            token = self.ctx.scheduler.submit(fn = task, generation = 0)
            self._req_id = token.request
        else:
            self._do_load()

    def _do_load(self) -> None:
        self.step = "LOAD"
        self._report_status("正在加载图像资源及元数据...")

        # UI 先切图
        image_path = self.target_metadata["image_path"]
        self.ctx.workspace.load(image_path)

        # 异步加载标注
        meta = self.target_metadata

        def task():
            return self.ctx.project_service.fetch_image_data(
                meta.get("project_id"),
                meta.get("case_id"),
                meta.get("id", meta.get("image_id")),
            )

        token = self.ctx.scheduler.submit(fn = task, generation = 0)
        self._req_id = token.request

    def _do_segment(self, annotations_data: dict) -> None:
        self.step = "SEGMENT"
        self._report_status("正在进行图像编码 (Embedding)...")

        workspace = self.ctx.workspace

        # 加载标注到 workspace
        workspace.load_from(annotations_data)

        # 通知 UI 刷新
        self.ctx.image_selected.emit(workspace)

        if self.ctx.seg_service is None:
            self.ctx.transition_to(AnnotatingState(self.ctx))
            return

        image = workspace.image
        if image is None:
            self.ctx.transition_to(AnnotatingState(self.ctx))
            return

        embedding = workspace.embedding
        emb_path = workspace.embedding_path
        points = workspace.points
        pipeline = workspace.pipeline

        def task():
            return self.ctx.seg_service.segment_image(image, embedding, emb_path, points, pipeline)

        token = self.ctx.scheduler.submit(fn = task, generation = 0)
        self._req_id = token.request

    def handle_result(self, request_id: int, result: object) -> None:
        if request_id != self._req_id:
            return

        if self.step == "SAVE":
            # --- 关键修正：保存操作也会改变状态 ---
            meta = self.ctx.session.current_metadata
            if meta:
                self.ctx.notify_status_update(
                    str(meta.get("project_id")),
                    str(meta.get("case_id")),
                    str(meta.get("id", meta.get("image_id"))),
                    "Annotating" # 保存意味着已开始标注
                )
            # ------------------------------------

            self.ctx.session.dirty = False
            self._do_load()

        elif self.step == "LOAD":
            self.ctx.session.current_metadata = dict(self.target_metadata)
            annotations = result["data"]["annotations"]
            self._do_segment(annotations)

        elif self.step == "SEGMENT":
            self.ctx._handle_segment_image_result(result)
            self.ctx.session.dirty = False
            self.ctx.transition_to(AnnotatingState(self.ctx))


class SubmittingState(WorkflowState):
    """提交/废弃状态。"""

    def __init__(self, controller: Controller, status: str) -> None:
        super().__init__(controller)
        self.target_status = status
        self._req_id: int | None = None

    def get_message(self) -> str:
        action = "提交" if self.target_status == "Submitted" else "废弃"
        return f"正在{action}案例数据..."

    def enter(self) -> None:
        super().enter()

        data = self.ctx.workspace.export_remote_annotations()
        meta = self.ctx.session.current_metadata

        def task():
            return self.ctx.project_service.update_annotations(
                meta.get("project_id"),
                meta.get("case_id"),
                meta.get("id", meta.get("image_id")),
                data,
                self.target_status,
            )

        token = self.ctx.scheduler.submit(fn = task, generation = 0)
        self._req_id = token.request

    def handle_result(self, request_id: int, result: object) -> None:
        if request_id != self._req_id:
            return

        # 获取当前正在操作的 ID，用于通知 Explorer 更新
        meta = self.ctx.session.current_metadata
        if meta:
            self.ctx.notify_status_update(
                str(meta.get("project_id")),
                str(meta.get("case_id")),
                str(meta.get("id", meta.get("image_id"))),
                self.target_status
            )

        self.ctx.session.dirty = False
        self.ctx.transition_to(AnnotatingState(self.ctx))
