import numpy as np

from PySide6.QtCore import Qt, Slot, QThreadPool

from infra.scheduler import TaskScheduler
from infra.segmenter_service import SegmenterService
from infra.repository import Repository
from PySide6.QtWidgets import QGridLayout, QWidget, QMainWindow, QDockWidget, QMessageBox, QProgressDialog, QHBoxLayout, QLabel, QToolBar

from .canvas import Canvas

from app.controller import Controller
from .explorer.explorer import Explorer
from .pipeline_editor import PipelineEditor
from .annotator import Annotator
from .viewer import Viewer
from app.workspace_object import WorkspaceObject


class Window(QMainWindow):

    def __init__(self, base_cache_dir: str, base_url: str):

        super().__init__()

        self.setMinimumSize(1200, 800)

        workspace = WorkspaceObject()

        threadpool = QThreadPool.globalInstance()

        self._scheduler = TaskScheduler(threadpool = threadpool)
        self._segmenter = SegmenterService()
        self._repo = Repository.build(base_url)

        controller = Controller(workspace, base_url = base_url, scheduler = self._scheduler, segmenter = self._segmenter, repo = self._repo)
        controller.image_selected.connect(self._on_image_selected)
        controller.segment_mask.connect(self._on_segment_mask)
        controller.generate_polygon.connect(self._on_polygon_generated)

        # step5 unified UI orchestration
        controller.freeze_ui.connect(self._on_freeze_ui)
        controller.status_text.connect(self._on_status_text)
        controller.progress.connect(self._on_progress)
        controller.show_error.connect(self._on_error)

        # legacy submission signals (kept, but no longer required)
        # controller.submission_started.connect(self._on_submission_started)
        controller.submission_failed.connect(self._on_submission_failed)
        controller.submission_finished.connect(self._on_submission_finished)

        toolbar = QToolBar()
        toolbar.setFloatable(False)
        toolbar.setMovable(False)
        toolbar.addAction('提交').triggered.connect(controller.on_submit_current)
        toolbar.addAction('废弃').triggered.connect(controller.on_abolish_current)
        self.addToolBar(toolbar)

        explorer = Explorer(base_cache_dir, base_url, scheduler = self._scheduler, repo = self._repo)
        explorer.image_selected.connect(controller.on_image_selected)

        dock = QDockWidget(self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        # title_bar = QWidget()
        # title_bar.setLayout(QHBoxLayout())
        # title_bar.layout().setContentsMargins(8, 8, 8, 8)
        # title_bar.layout().addWidget(QLabel('资源库'))
        # dock.setTitleBarWidget(title_bar)
        dock.setWindowTitle('资源库')
        dock.setWidget(explorer)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        editor = PipelineEditor()
        editor.pipeline_changed.connect(controller.on_update_pipeline)

        dock = QDockWidget(self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setWidget(editor)

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        annotator = Annotator()
        annotator.points_updated.connect(controller.on_update_points)

        viewer = Viewer()

        canvas = Canvas()
        canvas.final_mask.connect(self._on_final_mask)
        canvas.polygons_updated.connect(controller.on_update_polygons_from_canvas)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        grid.addWidget(annotator, 0, 0)
        grid.addWidget(canvas, 0, 1)
        grid.addWidget(viewer, 1, 0, 1, 2)

        central = QWidget()
        central.setLayout(grid)

        self.setCentralWidget(central)

        self._controller = controller

        self._annotator = annotator
        self._canvas = canvas
        self._viewer = viewer
        self._editor = editor

        self._workspace = workspace

    def closeEvent(self, event):

        self._controller.close()

        event.accept()

    @Slot(object)
    def _on_image_selected(self, workspace):

        self._annotator.set_image(workspace.image)
        self._annotator.set_mask(None)
        self._annotator.set_points(workspace.points)
        self._annotator.fit()

        self._editor.set_pipeline(workspace.pipeline)

        self._viewer.set_image(workspace.image)
        self._viewer.fit()

    @Slot(np.ndarray)
    def _on_segment_mask(self, rgba_mask):

        self._annotator.set_mask(rgba_mask)

    @Slot(np.ndarray, list)
    def _on_polygon_generated(self, image, polygons):

        self._canvas.set_image(image)
        self._canvas.set_polygons(polygons)

    @Slot(np.ndarray, np.ndarray)
    def _on_final_mask(self, image, mask):

        if image is not None and mask is not None:

            mask = mask > 0

            height, width = mask.shape

            rgba_segmentation = np.zeros((height, width, 4), dtype = np.uint8)

            rgba_segmentation[mask, :3] = image[mask]
            rgba_segmentation[mask, 3] = 255

            self._viewer.set_image(rgba_segmentation)

        else:

            self._viewer.set_image(None)

    def _set_interactive_enabled(self, enabled: bool) -> None:
        # Keep modal dialogs functional by disabling only interactive regions.
        if self.centralWidget() is not None:
            self.centralWidget().setEnabled(enabled)
        for dock in self.findChildren(QDockWidget):
            dock.setEnabled(enabled)
        self.menuBar().setEnabled(enabled)

    def _ensure_progress_dialog(self) -> QProgressDialog:
        if getattr(self, "_progress_dialog", None) is None:
            dlg = QProgressDialog("Submitting annotations…", None, 0, 0, None)
            dlg.setWindowTitle("Please wait")
            dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
            dlg.setMinimumDuration(0)
            dlg.setCancelButton(None)
            dlg.setAutoClose(False)
            dlg.setAutoReset(False)
            self._progress_dialog = dlg
        return self._progress_dialog

    @Slot(dict)
    def _on_submission_started(self, _meta: dict):
        self._set_interactive_enabled(False)
        dlg = self._ensure_progress_dialog()
        dlg.setLabelText("Submitting annotations…")
        dlg.show()

    @Slot(str)
    def _on_submission_failed(self, err: str):

        dlg = self._ensure_progress_dialog()
        dlg.hide()

        self._set_interactive_enabled(True)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Submit failed")
        box.setText("Failed to submit operation to the remote service.\n关掉此弹窗后再次尝试刚才的操作。")
        box.setInformativeText(err)

        retry_btn = box.addButton("", QMessageBox.ButtonRole.AcceptRole)
        # cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        box.setDefaultButton(retry_btn)
        box.exec()

        if box.clickedButton() == retry_btn:
            # Controller will freeze UI again via submission_started.
            # self._controller.retry_last_submission()
            pass
        else:
            # Stay on current workspace.
            pass

    @Slot()
    def _on_submission_finished(self):
        dlg = self._ensure_progress_dialog()
        dlg.hide()
        self._set_interactive_enabled(True)

    @Slot(bool, str)
    def _on_freeze_ui(self, frozen: bool, message: str) -> None:
        # Conservative: disable the whole window except status dialog
        self.setEnabled(not frozen)
        if message:
            self.statusBar().showMessage(message)

    @Slot(str)
    def _on_status_text(self, text: str) -> None:
        self.statusBar().showMessage(text)

    @Slot(int)
    def _on_progress(self, v: int) -> None:
        # If you have a progress widget, connect it here. Keeping no-op is safe.
        pass

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        # Reuse existing error dialog
        try:
            self._on_submission_failed(msg)
        except Exception:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", msg)
