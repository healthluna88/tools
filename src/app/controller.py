from __future__ import annotations
import copy
import logging
import threading
import cv2

import numpy as np

from PySide6.QtCore import QObject, Signal, Slot, QTimer

from app.workspace_object import WorkspaceObject
from app.session import WorkspaceSession, SessionPhase
from infra.scheduler import TaskScheduler
from infra.repository import Repository
from core.ai.segmenter import Segmenter


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

    def __init__(
        self,
        workspace: WorkspaceObject,
        base_url: str,
        scheduler: TaskScheduler,
        repo: Repository | None = None,
        segmenter: Segmenter | None = None
        ) -> None:

        super().__init__()

        self._workspace = workspace
        self._base_url = base_url.rstrip('/')
        self._repo = repo or Repository.build(self._base_url)
        self._scheduler = scheduler

        # Segmenter is now injected. It might be None if initialization failed.
        self._segmenter = segmenter

        # We STILL need a lock because tasks run in threads and Segmenter (SAM) is stateful.
        self._segmenter_lock = threading.Lock()

        # Local cache for segmentation state
        self._cached_mask_sam: np.ndarray | None = None

        # scheduler routing
        self._req_kind: dict[int, str] = { }

        self._active_submit_req: int | None = None
        self._active_submit_gen: int | None = None

        # Track active segmentation request
        self._active_seg_req: int | None = None

        self._scheduler.task_result.connect(self._on_task_result)
        self._scheduler.task_error.connect(self._on_task_error)

        # Central application state
        self._session = WorkspaceSession(phase = SessionPhase.IDLE)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_debounce_timeout)
        self._timer: QTimer = timer

        # Segmenter service wiring (runs in its own long-lived thread) -> Removed in favor of direct injection
        # self._segmenter.status.connect... (Removed)

    def close(self) -> None:
        pass

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

        # Immediate pipeline update if we have cached SAM mask
        if self._workspace.image is not None and self._cached_mask_sam is not None:
            self._run_pipeline_segmentation()

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
        """Called by debounce timer for point updates."""
        workspace = self._workspace

        if self._segmenter is None:
            logger.warning("Segmenter not available, skipping segmentation.")
            return

        params = {
            "image":    workspace.image,
            "points":   workspace.points,
            "pipeline": workspace.pipeline
        }

        def task():
            return self._task_segment_points(params)

        token = self._scheduler.submit(generation = 0, fn = task)
        self._req_kind[token.request] = "segment_points"
        self._active_seg_req = token.request

    # --- Event Handlers ---

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

    # --- Helper: Visualization ---

    @staticmethod
    def _render_overlay(mask: np.ndarray) -> np.ndarray:
        height, width = mask.shape
        rgba_overlay = np.zeros((height, width, 4), dtype = np.uint8)
        rgba_overlay[mask] = (0, 255, 0, 100)
        return rgba_overlay

    @staticmethod
    def _generate_polygons(image: np.ndarray, mask: np.ndarray) -> list:
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        polygons = []
        for cnt in contours:
            epsilon = 0.01 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            approx = approx.squeeze(1)
            polygons.append(approx)
        return polygons

    # --- Task Functions (Run in background) ---

    def _task_segment_image(self, params: dict) -> dict:
        """
        Executed in thread pool.
        """
        image = params["image"]
        embedding = params["embedding"]
        embedding_path = params["embedding_path"]
        points = params["points"]
        pipeline = params["pipeline"]
        skip_polygons = params.get("skip_polygons", False)

        with self._segmenter_lock:
            seg = self._segmenter

            if seg is None:
                raise RuntimeError("Segmenter model is not initialized (check startup logs).")

            if embedding is None:
                embedding = seg.set_image(image, None)
                if embedding_path:
                    np.save(embedding_path, embedding)
            else:
                seg.set_image(image, embedding)

            mask_sam = None
            mask_pipeline = None
            rgba_mask = None
            polygons = None

            if any(p["label"] == 1 for p in points):
                mask_sam = seg.predict(points).astype(np.uint8) * 255
                mask_pipeline = pipeline.process(image, mask_sam)
                rgba_mask = Controller._render_overlay(mask_pipeline > 0)

                if not skip_polygons:
                    polygons = Controller._generate_polygons(image, mask_pipeline)

        return {
            "type":          "image",
            "embedding":     embedding,
            "mask_sam":      mask_sam,
            "rgba_mask":     rgba_mask,
            "polygons":      polygons,
            "skip_polygons": skip_polygons,
            "image_ref":     image
        }

    def _task_segment_points(self, params: dict) -> dict:
        image = params["image"]
        points = params["points"]
        pipeline = params["pipeline"]

        with self._segmenter_lock:
            seg = self._segmenter

            if seg is None:
                # Silent return or throw? Throwing is handled by task_error
                raise RuntimeError("Segmenter model is not initialized.")

            mask_sam = None
            mask_pipeline = None
            rgba_mask = None
            polygons = None

            if any(p["label"] == 1 for p in points):
                mask_sam = seg.predict(points).astype(np.uint8) * 255
                mask_pipeline = pipeline.process(image, mask_sam)
                rgba_mask = Controller._render_overlay(mask_pipeline > 0)
                polygons = Controller._generate_polygons(image, mask_pipeline)

        return {
            "type":      "points",
            "mask_sam":  mask_sam,
            "rgba_mask": rgba_mask,
            "polygons":  polygons,
            "image_ref": image
        }

    def _task_segment_pipeline(self, params: dict) -> dict:
        # Pipeline processing typically doesn't need the Segmenter(SAM) model,
        # so we might not need the lock unless Pipeline is unsafe.
        # Assuming Pipeline is safe/stateless.
        image = params["image"]
        mask_sam = params["mask_sam"]
        pipeline = params["pipeline"]

        mask_pipeline = pipeline.process(image, mask_sam)
        rgba_mask = Controller._render_overlay(mask_pipeline > 0)
        polygons = Controller._generate_polygons(image, mask_pipeline)

        return {
            "type":      "pipeline",
            "rgba_mask": rgba_mask,
            "polygons":  polygons,
            "image_ref": image
        }

    def _start_update(self, meta: dict, data: dict, status: str) -> None:
        project_id = meta.get("project_id", "")
        case_id = meta.get("case_id", "")
        image_id = meta.get("id", meta.get("image_id", ""))

        self.freeze_ui.emit(True, "Updating image ...")
        self.status_text.emit("Updating ...")
        self.progress.emit(-1)

        self._session.phase = SessionPhase.SAVING
        gen = self._session.generation
        self._active_submit_gen = gen

        def fn() -> dict:
            return self._repo.update(
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
            case_id = metadata.get("case_id", "")
            image_id = metadata.get("id", metadata.get("image_id", ""))
            return self._repo.get_image(project_id = project_id, case_id = case_id, image_id = image_id)

        gen = self._session.generation
        self._active_submit_gen = gen

        tok = self._scheduler.submit(generation = gen, fn = do_load)
        self._req_kind[tok.request] = "load"
        self._active_submit_req = tok.request

    def _run_pipeline_segmentation(self):
        workspace = self._workspace

        params = {
            "image":    workspace.image,
            "mask_sam": self._cached_mask_sam,
            "pipeline": workspace.pipeline
        }

        def task():
            return self._task_segment_pipeline(params)

        token = self._scheduler.submit(generation = 0, fn = task)
        self._req_kind[token.request] = "segment_pipeline"

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

            # --- Load Finished ---
            metadata = self._session.pending_metadata
            self._session.current_metadata = dict(metadata)
            self._session.phase = SessionPhase.ANNOTATING

            workspace = self._workspace
            workspace.load_from(result["data"]["annotations"])
            self.image_selected.emit(workspace)

            # --- Trigger Initial Segmentation ---
            if self._segmenter is None:
                self.show_error.emit("Segmentation model failed to load. Annotation features are disabled.")
                return

            skip_polygons = bool(workspace.polygons)

            params = {
                'image':          workspace.image,
                'embedding':      workspace.embedding,
                'embedding_path': workspace.embedding_path,
                'points':         workspace.points,
                'pipeline':       workspace.pipeline,
                'skip_polygons':  skip_polygons
            }

            def task():
                return self._task_segment_image(params)

            token = self._scheduler.submit(generation = 0, fn = task)
            self._req_kind[token.request] = "segment_image"

            self._cached_mask_sam = None

            if skip_polygons:
                self.generate_polygon.emit(workspace.image, workspace.polygons)

            self._session.pending_metadata = None
            self._session.dirty = False

        elif kind == "segment_image":
            self._cached_mask_sam = result["mask_sam"]

            if result.get("embedding") is not None:
                self._workspace.set_embedding(result["embedding"])

            self.segment_mask.emit(result["rgba_mask"])

            if not result["skip_polygons"]:
                self.generate_polygon.emit(result["image_ref"], result["polygons"])
                if result["polygons"] is not None:
                    self._workspace.set_polygons(result["polygons"])

        elif kind == "segment_points":
            if self._active_seg_req and self._active_seg_req != request_id:
                return

            self._cached_mask_sam = result["mask_sam"]
            self.segment_mask.emit(result["rgba_mask"])
            self.generate_polygon.emit(result["image_ref"], result["polygons"])

        elif kind == "segment_pipeline":
            self.segment_mask.emit(result["rgba_mask"])
            self.generate_polygon.emit(result["image_ref"], result["polygons"])

    @Slot(int, int, object)
    def _on_task_error(self, request_id: int, generation: int, err: object) -> None:
        kind = self._req_kind.get(request_id, "")

        logger.error(f"Task error ({kind}): {err}")

        if kind in ("update", "load"):
            if self._active_submit_req == request_id and self._active_submit_gen == generation:
                self._on_submit_failed(str(err))
                self._on_submit_finished()

        elif kind.startswith("segment"):
            self.status_text.emit(f"Segmentation Error: {err}")