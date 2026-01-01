from PySide6.QtCore    import Signal
from PySide6.QtGui     import QAction
from PySide6.QtWidgets import QVBoxLayout, QToolBar, QMenu, QWidget, QListWidget, QListWidgetItem

import core.process.algorithm

from core.process.processor import Processor
from .processor_editor import ProcessorEditor


class PipelineEditor(QWidget):

    pipeline_changed = Signal()

    def __init__(self):

        super().__init__()

        self.setMinimumWidth(260)

        self._pipeline = None

        toolbar = QToolBar()

        for name, class_type in Processor.Registry.items():

            action = QAction(f'+ {class_type["label"]}', self)
            action.triggered.connect(lambda checked, n = name: self._add_processor(n))

            toolbar.addAction(action)

        list_widget = QListWidget()
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        list_widget.model().rowsMoved.connect(self._on_rows_moved)
        # list_widget.setStyleSheet \
        #     (
        #         """
        #         QListWidget::item
        #         {
        #             background-color: #F0F0F0;
        #             border: none;
        #             padding: 8;
        #         }
        #
        #         QListWidget::item:selected
        #         {
        #             background-color: #F9F9F9;
        #             outline: none;
        #         }
        #         """
        #     )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(list_widget)

        self.setLayout(layout)

        self.toolbar = toolbar

        self.list_widget = list_widget

    def set_pipeline(self, pipeline):

        self._pipeline = pipeline

        self._reload_list()

    def _reload_list(self):

        self.list_widget.clear()

        for p in self._pipeline.processors():

            self._add_processor_widget(p)

    def _add_processor_widget(self, processor):

        item = QListWidgetItem()

        widget = ProcessorEditor(processor)

        item.setSizeHint(widget.sizeHint())

        widget.param_changed.connect(lambda name, value, p = processor: self._on_param_changed(p.name, name, value))
        widget.enabled_changed.connect(lambda enabled, p = processor: self._on_enabled_changed(p.name, enabled))
        widget.remove_requested.connect(lambda p = processor: self._on_remove_processor(p.name))

        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)

    def _show_add_menu(self):

        menu = QMenu(self)

        for name in Processor.Registry.keys():

            action = QAction(name, self)
            action.triggered.connect(lambda checked, n = name: self._add_processor(n))

            menu.addAction(action)

        menu.exec(self.toolbar.mapToGlobal(self.toolbar.rect().bottomLeft()))

    def _add_processor(self, class_name):

        if self._pipeline:

            p = Processor.create(class_name)

            self._pipeline.add(p)

            self._add_processor_widget(p)

            self.pipeline_changed.emit()

    def _on_remove_processor(self, processor_name):

        self._pipeline.remove(processor_name)

        self._reload_list()

        self.pipeline_changed.emit()

    def _on_param_changed(self, processor_name, parameter_name, value):

        self.pipeline_changed.emit()

    def _on_enabled_changed(self, name, enabled):

        self.pipeline_changed.emit()

    def _on_rows_moved(self, *args):

        names = []

        for i in range(self.list_widget.count()):

            item   = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)

            editor: ProcessorEditor = widget

            names.append(editor.processor.name)

        self._pipeline.reorder_by(names)

        self.pipeline_changed.emit()
