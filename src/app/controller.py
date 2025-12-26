from __future__ import annotations
import copy
import logging

import numpy as np

from PySide6.QtCore import QObject, Signal, Slot, QTimer

from app.workspace_object import WorkspaceObject
from app.session import WorkspaceSession, SessionPhase
from infra.scheduler import TaskScheduler
from infra.segmenter_service import SegmenterService
from infra.repository import Repository

logger = logging.getLogger(__name__)


class Controller(QObject):

    image_selected = Signal(object)

    freeze_ui = Signal(bool, str)  # frozen, message
    status_text = Signal(str)
    progress = Signal(int)  # -1 indeterminate, else 0..100
    show_error = Signal(str)

    # Legacy workflow signals (kept for compatibility)
    submission_started = Signal(dict)
    submission_succeeded = Signal(dict)
    submission_failed = Signal(str)
    submission_finished = Signal()

    segment_mask = Signal(np.ndarray)

    generate_polygon = Signal(object, object)

    DEBOUNCE_MS = 200

    def __init__(self, workspace: WorkspaceObject, base_url: str, scheduler: TaskScheduler, segmenter: SegmenterService, repo: Repository | None = None) -> None:

        super().__init__()

        self._workspace = workspace
        self._base_url = base_url.rstrip('/')
        self._repo = repo or Repository.build(self._base_url)
        self._scheduler = scheduler
        self._segmenter = segmenter

        # scheduler routing
        self._req_kind: dict[int, str] = { }

        self._active_submit_req: int | None = None
        self._active_submit_gen: int | None = None

        self._scheduler.task_result.connect(self._on_task_result)
        self._scheduler.task_error.connect(self._on_task_error)

        # Central application state
        self._session = WorkspaceSession(phase = SessionPhase.IDLE)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_debounce_timeout)

        # Segmenter service wiring (runs in its own long-lived thread)
        self._segmenter.status.connect(lambda status: logger.info("%s", status))
        self._segmenter.generate_embedding.connect(lambda embedding: workspace.set_embedding(embedding))
        self._segmenter.segment_mask.connect(self.segment_mask)

        self._segmenter.generate_polygon.connect(self.on_update_polygons)

        self._timer: QTimer = timer

    def close(self) -> None:

        self._workspace.save()

        self._segmenter.close()

    @Slot(object)
    def on_image_selected(self, metadata: dict):

        if self._session.phase == SessionPhase.SUBMITTING:

            return

        self._session.pending_metadata = dict(metadata)

        print('dirty', self._session.dirty)

        if self._session.current_metadata is None or not self._session.dirty:

            print('直接读取')
            self._apply_switch(self._session.pending_metadata)

            return

        print('先保存')

        data = self._workspace.export_remote_annotations()

        self._session.last_submit_metadata = dict(self._session.current_metadata)
        self._session.last_submit_annotations = dict(data)

        self._start_update(self._session.last_submit_metadata, self._session.last_submit_annotations, "Annotating")

    @Slot(object)
    def on_submit_current(self):

        if self._session.current_metadata is not None:

            data = self._workspace.export_remote_annotations()

            self._session.last_submit_metadata = dict(self._session.current_metadata)
            self._session.last_submit_annotations = dict(data)

            self._start_update(self._session.last_submit_metadata, self._session.last_submit_annotations, "Submitted")

    @Slot(object)
    def on_abolish_current(self):

        if self._session.current_metadata is not None:

            data = self._workspace.export_remote_annotations()

            self._session.last_submit_metadata = dict(self._session.current_metadata)
            self._session.last_submit_annotations = dict(data)

            self._start_update(self._session.last_submit_metadata, self._session.last_submit_annotations, "Skipped")

    def _start_update(self, meta: dict, data: dict, status: str) -> None:

        project_id = meta.get("project_id", "")
        case_id    = meta.get("case_id", "")
        image_id   = meta.get("id", meta.get("image_id", ""))

        self.freeze_ui.emit(True, "Updating image ...")
        self.status_text.emit("Updating ...")
        self.progress.emit(-1)

        # self.submission_started.emit(dict(meta))  # legacy

        self._session.phase = SessionPhase.SAVING
        gen = self._session.generation
        self._active_submit_gen = gen

        def fn() -> dict:

            return self._repo.update \
                (
                    project_id = project_id,
                    case_id = case_id,
                    image_id = image_id,
                    data = data,
                    status = status
                )

        token = self._scheduler.submit(generation = gen, fn = fn)

        self._req_kind[token.request] = "update"
        self._active_submit_req = token.request

    def _on_submit_failed(self, err: str) -> None:

        self.submission_failed.emit(err)

    def _on_submit_finished(self) -> None:
        self._session.phase = SessionPhase.ANNOTATING
        self.submission_finished.emit()
        self.freeze_ui.emit(False, "")
        self.progress.emit(100)
        self.status_text.emit("Ready")

    def _apply_switch(self, metadata: dict) -> None:

        image_path = metadata["image_path"]

        workspace = self._workspace
        workspace.load(image_path)

        def do_load() -> dict:

            project_id = metadata.get("project_id", "")
            case_id    = metadata.get("case_id", "")
            image_id   = metadata.get("id", metadata.get("image_id", ""))

            return self._repo.get_image(project_id = project_id, case_id = case_id, image_id = image_id)

        gen = self._session.generation
        self._active_submit_gen = gen

        tok = self._scheduler.submit(generation = gen, fn = do_load)

        self._req_kind[tok.request] = "load"
        self._active_submit_req = tok.request

    @Slot(list)
    def on_update_points(self, points):

        print('on_update_points')

        self._session.dirty = True

        self._workspace.set_points(copy.deepcopy(points))

        self._schedule_segmentation()

    @Slot(object)
    def on_update_pipeline(self):

        print('on_update_pipeline')

        self._session.dirty = True

        self._segmenter.update_pipeline({ 'pipeline': self._workspace.pipeline })

    # todo 调整
    #  on_update_polygons 不应该带着 image，需要独立出去
    #  on_update_polygons_from_canvas 临时解决

    @Slot(object, object)
    def on_update_polygons(self, image, polygons):

        print('on_update_polygons')

        self._session.dirty = True

        self._workspace.set_polygons(polygons)

        self.generate_polygon.emit(image, polygons)

    @Slot(object, object)
    def on_update_polygons_from_canvas(self, polygons):

        self._session.dirty = True

        self._workspace.set_polygons(polygons)

    @Slot()
    def run_segmentation(self):

        workspace = self._workspace

        self._segmenter.update_points \
            (
                {
                    'points':   workspace.points,
                    'pipeline': workspace.pipeline
                }
            )

    def _schedule_segmentation(self):

        self._timer.start(Controller.DEBOUNCE_MS)

    @Slot()
    def _on_debounce_timeout(self):

        self.run_segmentation()

    @Slot(int, int, object)
    def _on_task_result(self, request_id: int, generation: int, result: object) -> None:

        kind = self._req_kind.get(request_id, "")

        if kind == "update":

            if self._active_submit_req != request_id or self._active_submit_gen != generation:

                return

            self._session.dirty = False

            self._on_submit_finished()

            if self._session.pending_metadata is not None:

                self._apply_switch(self._session.pending_metadata)

        elif kind == "load":

            if self._active_submit_req != request_id or self._active_submit_gen != generation:

                return

            # 远程数据加载完成

            # 修改 session 相关

            metadata = self._session.pending_metadata

            self._session.current_metadata = dict(metadata)

            self._session.phase = SessionPhase.ANNOTATING

            # 数据放入 workspace

            workspace = self._workspace

            workspace.load_from(result["data"]["annotations"])

            self.image_selected.emit(workspace)

            # 根据 points 分割，生成 / 修饰 mask
            # 条件生成 polygons

            skip_polygons = bool(workspace.polygons)

            self._segmenter.update_image \
                (
                    {
                        'image':          workspace.image,
                        'embedding':      workspace.embedding,
                        'embedding_path': workspace.embedding_path,
                        'points':         workspace.points,
                        'pipeline':       workspace.pipeline,
                        'skip_polygons':  skip_polygons
                    }
                )

            if skip_polygons:

                self.generate_polygon.emit(workspace.image, workspace.polygons)

            self._session.pending_metadata = None

            self._session.dirty = False  # 直接加载，无修改

    @Slot(int, int, object)
    def _on_task_error(self, request_id: int, generation: int, err: object) -> None:

        kind = self._req_kind.get(request_id, "")

        if kind == "update":

            if self._active_submit_req != request_id or self._active_submit_gen != generation:

                return

            self._on_submit_failed(str(err))
            self._on_submit_finished()

        elif kind == "load":

            if self._active_submit_req != request_id or self._active_submit_gen != generation:

                return

            self._on_submit_failed(str(err))
            self._on_submit_finished()
