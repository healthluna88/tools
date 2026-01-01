# src/ui/window.py

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QDialog,
    QFrame,
    QLabel,
    QProgressBar,
)

from app.controller import Controller
from app.explorer_controller import ExplorerController
from app.services import ProjectService
from app.workspace import Workspace
from infra.repository import Repository
from infra.scheduler import Scheduler
from ui.explorer.explorer import Explorer
from ui.modes import PolygonMode, SegmentationMode
from ui.util import roi_with_margin
from ui.viewer import Viewer
from ui.login import LoginWidget


class BusyPopup(QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(320, 140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet(
            """
            QFrame {
                background-color: #383838;
                border: 1px solid #555555;
                border-radius: 10px;
            }
            QLabel {
                color: #E0E0E0;
                font-size: 14px;
                font-weight: 500;
            }
            QProgressBar {
                background-color: #2b2b2b;
                border: none;
                height: 4px;
                border-radius: 2px;
                margin-top: 10px;
            }
            QProgressBar::chunk {
                background-color: #1890ff;
                border-radius: 2px;
            }
        """
        )

        inner_layout = QVBoxLayout(self.frame)
        inner_layout.setContentsMargins(30, 30, 30, 30)
        inner_layout.setSpacing(10)

        self.label = QLabel("正在处理...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        inner_layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        inner_layout.addWidget(self.progress)

        layout.addWidget(self.frame)

    def show_message(self, message: str):
        self.label.setText(message)
        if not self.isVisible():
            self.show()


class Window(QMainWindow):
    def __init__(self, base_cache_dir: str, base_url: str, segmenter):
        super().__init__()

        self.setMinimumSize(1200, 800)
        self.setWindowTitle("CapitalBio AI Annotation Tool")

        # --- 核心服务初始化 ---
        workspace = Workspace()
        threadpool = QThreadPool.globalInstance()
        self._scheduler = Scheduler(threadpool = threadpool)
        self._repo = Repository.build(base_url)
        project_service = ProjectService(self._repo)

        controller = Controller(
            workspace,
            base_url = base_url,
            scheduler = self._scheduler,
            repo = self._repo,
            segmenter = segmenter,
        )
        self._controller = controller
        self._workspace = workspace

        # --- 弹窗与 Viewer 初始化 ---
        self._busy_popup = BusyPopup(self)
        self._editor_viewer = Viewer()
        self._preview_viewer = Viewer()
        self._preview_viewer.setMinimumHeight(200)

        # --- Modes 初始化 ---
        self._seg_mode = SegmentationMode(controller, self._editor_viewer)
        self._poly_mode = PolygonMode(controller, self._editor_viewer)
        self._current_mode = None

        # --- 信号连接: Controller -> Window ---
        controller.image_selected.connect(self._on_image_selected)
        controller.segment_mask.connect(self._on_segment_mask)
        controller.generate_polygon.connect(self._on_polygon_generated)
        controller.polygons_generated.connect(self._on_manual_polygons_ready)

        controller.freeze_ui.connect(self._on_freeze_ui)
        controller.status_text.connect(self._on_status_text)
        controller.progress.connect(self._on_progress)
        controller.show_error.connect(self._on_error)

        # 登录信号
        controller.login_success.connect(self._on_login_success)
        controller.login_fail.connect(self._on_login_fail)

        # --- 信号连接: Mode -> Window ---
        self._poly_mode.request_regenerate.connect(self._on_req_regenerate)
        self._poly_mode.interactor.final_mask.connect(self._on_final_mask)

        # --- Explorer (左侧 Dock) ---
        self._explorer_ctrl = ExplorerController(project_service, self._scheduler)
        self._explorer = Explorer(base_cache_dir)
        self._init_explorer(self._explorer, self._explorer_ctrl)

        # 初始隐藏 Dock，登录后显示
        self._dock_explorer.hide()

        # --- Central Widget (堆叠布局：登录页 / 工作区) ---
        central_stack = QStackedWidget()
        self.setCentralWidget(central_stack)
        self._central_stack = central_stack

        # 1. 登录页
        self._login_widget = LoginWidget()
        self._login_widget.login_requested.connect(controller.request_login)
        central_stack.addWidget(self._login_widget)

        # 2. 工作区 Widget
        self._workspace_widget = QWidget()
        self._init_workspace_ui(self._workspace_widget)
        central_stack.addWidget(self._workspace_widget)

        # 预填充凭证（如果存在），但不自动登录
        creds = controller.get_saved_credentials()
        if creds:
            self._login_widget.set_values(creds[0], creds[1])

        # 始终停留在登录页，等待用户点击
        central_stack.setCurrentWidget(self._login_widget)

    def _init_workspace_ui(self, container: QWidget):
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._toolbar_stack = QStackedWidget()
        self._toolbar_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._toolbar_stack.addWidget(self._seg_mode.toolbar)
        self._toolbar_stack.addWidget(self._poly_mode.toolbar)
        main_layout.addWidget(self._toolbar_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._editor_viewer)

        right_panel = QWidget()
        right_panel.setMaximumWidth(450)

        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(1)

        right_panel_layout.addWidget(self._preview_viewer, stretch = 1)

        self._side_panel_stack = QStackedWidget()
        self._empty_side_panel = QWidget()
        self._side_panel_stack.addWidget(self._empty_side_panel)

        if self._seg_mode.side_widget:
            self._side_panel_stack.addWidget(self._seg_mode.side_widget)

        right_panel_layout.addWidget(self._side_panel_stack, stretch = 2)

        splitter.addWidget(right_panel)
        splitter.setSizes([900, 300])

        main_layout.addWidget(splitter)

        self._switch_mode(self._seg_mode)

    def _init_explorer(self, explorer: Explorer, explorer_ctrl: ExplorerController) -> None:
        explorer.fetch_requested.connect(explorer_ctrl.fetch_list)
        explorer.download_requested.connect(explorer_ctrl.download_thumbnail)

        explorer_ctrl.file_list_loaded.connect(explorer.on_data_loaded)
        explorer_ctrl.file_list_error.connect(explorer.on_data_error)
        explorer_ctrl.thumbnail_ready.connect(explorer.on_thumbnail_ready)

        explorer.image_selected.connect(self._controller.on_image_selected)

        # 新增连接：Controller 状态更新 -> Explorer 刷新列表
        self._controller.entity_status_updated.connect(explorer.on_entity_updated)

        dock_res = QDockWidget(self)
        dock_res.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock_res.setWindowTitle("资源库")
        dock_res.setWidget(explorer)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_res)
        self._dock_explorer = dock_res  # 保存引用以便控制显隐

    def _switch_mode(self, mode) -> None:
        if self._current_mode == mode:
            return

        if self._current_mode:
            self._current_mode.exit()

        self._current_mode = mode
        mode.enter()

        self._toolbar_stack.setCurrentWidget(mode.toolbar)

        new_side = mode.side_widget
        if new_side:
            if self._side_panel_stack.indexOf(new_side) == -1:
                self._side_panel_stack.addWidget(new_side)
            self._side_panel_stack.setCurrentWidget(new_side)
        else:
            self._side_panel_stack.setCurrentWidget(self._empty_side_panel)

        self._refresh_preview_for_mode(mode)

    def _refresh_preview_for_mode(self, mode) -> None:
        self._preview_viewer.set_image(None)

        if mode == self._seg_mode:
            mask = self._controller.cached_mask_binary
            if mask is not None:
                self._on_segment_mask(None, mask)

        elif mode == self._poly_mode:
            if hasattr(mode.interactor, "force_update"):
                mode.interactor.force_update()

    # --- 登录相关槽函数 ---

    @Slot()
    def _on_login_success(self):
        """登录成功，切换到工作区"""
        self._central_stack.setCurrentWidget(self._workspace_widget)
        self._dock_explorer.show()
        # 触发 Explorer 加载数据
        self._explorer.start()

    @Slot(str)
    def _on_login_fail(self, msg):
        """登录失败，停留在登录页显示错误"""
        self._central_stack.setCurrentWidget(self._login_widget)
        self._login_widget.show_error(msg)
        self._dock_explorer.hide()

    # --- 现有槽函数 ---

    @Slot()
    def _on_manual_polygons_ready(self) -> None:
        self._switch_mode(self._poly_mode)

    @Slot()
    def _on_req_regenerate(self) -> None:
        res = QMessageBox.warning(
            self,
            "重新生成确认",
            "返回 AI 分割模式将丢失当前对轮廓的所有手动修改。\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if res == QMessageBox.StandardButton.Yes:
            self._switch_mode(self._seg_mode)

    @Slot(object)
    def _on_image_selected(self, workspace) -> None:
        self._preview_viewer.set_image(None)

        self._editor_viewer.set_image(workspace.image)

        self._seg_mode.interactor.set_points(workspace.points)
        self._seg_mode.interactor.set_mask(None)
        self._seg_mode.pipeline_editor.set_pipeline(workspace.pipeline)

        self._poly_mode.interactor.set_polygons(workspace.polygons)

        self._editor_viewer.fit()

        if workspace.polygons:
            self._switch_mode(self._poly_mode)
        else:
            self._switch_mode(self._seg_mode)

    @Slot(np.ndarray, np.ndarray)
    def _on_segment_mask(self, rgba_mask, binary_mask) -> None:
        if rgba_mask is not None:
            self._seg_mode.interactor.set_mask(rgba_mask)

        if self._current_mode == self._seg_mode:
            if binary_mask is not None and binary_mask.any():
                try:
                    x1, x2, y1, y2 = roi_with_margin(binary_mask, margin = 10)
                    roi_mask = binary_mask[y1:y2, x1:x2]
                    display_mask = (roi_mask > 0).astype(np.uint8) * 255
                    self._preview_viewer.set_image(display_mask)
                except Exception:
                    self._preview_viewer.set_image(None)
            else:
                self._preview_viewer.set_image(None)

    @Slot(object, object)
    def _on_polygon_generated(self, image, polygons) -> None:
        self._poly_mode.interactor.set_polygons(polygons)

    @Slot(np.ndarray, np.ndarray)
    def _on_final_mask(self, image, mask) -> None:
        if self._current_mode != self._poly_mode:
            return

        if image is not None and mask is not None and mask.any():
            try:
                x1, x2, y1, y2 = roi_with_margin(mask, margin = 10)

                mask_bool = mask > 0
                height, width = mask.shape

                rgba_segmentation = np.zeros((height, width, 4), dtype = np.uint8)
                rgba_segmentation[mask_bool, :3] = image[mask_bool]
                rgba_segmentation[mask_bool, 3] = 255

                roi_rgba = rgba_segmentation[y1:y2, x1:x2]
                self._preview_viewer.set_image(roi_rgba)
            except Exception:
                self._preview_viewer.set_image(None)
        else:
            self._preview_viewer.set_image(None)

    @Slot(bool, str)
    def _on_freeze_ui(self, frozen: bool, message: str) -> None:
        """响应 UI 冻结信号。支持动态更新弹窗文字。"""
        if frozen:
            self.setEnabled(False)
            self._busy_popup.show_message(message)
        else:
            self._busy_popup.hide()
            self.setEnabled(True)

    @Slot(str)
    def _on_status_text(self, text: str) -> None:
        self.statusBar().showMessage(text)

    @Slot(int)
    def _on_progress(self, _v: int) -> None:
        return

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._on_freeze_ui(False, "")
        QMessageBox.critical(self, "系统错误", msg)