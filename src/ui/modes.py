# src/ui/modes.py

from PySide6.QtCore import QObject, Signal, QSize
from PySide6.QtWidgets import QToolBar, QWidget

from .interactor import SegmentationInteractor, PolygonInteractor
from .pipeline_editor import PipelineEditor


class EditorMode(QObject):
    """所有编辑模式的基类"""

    def __init__(self, name: str, controller, viewer):
        super().__init__()
        self.name = name
        self.controller = controller
        self.viewer = viewer

        # 初始化工具栏
        self._toolbar = QToolBar(name)
        self._toolbar.setIconSize(QSize(64, 64))
        self._toolbar.setFloatable(False)
        self._toolbar.setMovable(False)
        # 透明背景，使其融入主界面，避免产生额外的视觉边框
        self._toolbar.setStyleSheet("QToolBar { border: none; background: transparent; }")

        self.init_toolbar()

    def init_toolbar(self):
        pass

    @property
    def toolbar(self) -> QToolBar:
        return self._toolbar

    @property
    def interactor(self):
        return None

    @property
    def side_widget(self) -> QWidget | None:
        return None

    def enter(self):
        if self.interactor:
            self.viewer.set_interactor(self.interactor)
            self.interactor.attach(self.viewer)

    def exit(self):
        if self.interactor:
            self.interactor.detach()


class SegmentationMode(EditorMode):
    """分割模式：包含 PipelineEditor"""

    def __init__(self, controller, viewer):
        self._interactor = SegmentationInteractor()
        self._pipeline_editor = PipelineEditor()

        super().__init__("Segmentation", controller, viewer)

        self._interactor.points_updated.connect(controller.on_update_points)
        self._pipeline_editor.pipeline_changed.connect(controller.on_update_pipeline)

    def init_toolbar(self):
        self._toolbar.addAction('废弃').triggered.connect(self.controller.on_abolish_current)
        self._toolbar.addSeparator()
        action_gen = self._toolbar.addAction("生成轮廓")
        action_gen.setToolTip("基于当前 Mask 生成轮廓并进入编辑模式")
        action_gen.triggered.connect(self.controller.on_action_generate_polygons)

    @property
    def interactor(self):
        return self._interactor

    @property
    def side_widget(self):
        # 此面板会常驻在 StackedWidget 中，状态（滚动条位置等）会被保留
        return self._pipeline_editor

    @property
    def pipeline_editor(self):
        return self._pipeline_editor


class PolygonMode(EditorMode):
    """轮廓模式：没有侧边工具，使用空占位"""

    request_regenerate = Signal()

    def __init__(self, controller, viewer):
        self._interactor = PolygonInteractor()
        super().__init__("Polygon", controller, viewer)

        self._interactor.polygons_updated.connect(controller.on_update_polygons_from_canvas)

    def init_toolbar(self):
        action_regen = self._toolbar.addAction("重新生成轮廓")
        action_regen.setToolTip("放弃当前编辑，返回 AI 分割模式")
        action_regen.triggered.connect(self.request_regenerate.emit)

        self._toolbar.addSeparator()
        self._toolbar.addAction('提交').triggered.connect(self.controller.on_submit_current)

    @property
    def interactor(self):
        return self._interactor

    @property
    def side_widget(self):
        # 返回 None，指示 Window 切换到空白占位页
        return None
