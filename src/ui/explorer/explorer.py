# src/ui/explorer/explorer.py

import os
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel, QProgressBar, QListWidget, QListWidgetItem, QToolBar, QSizePolicy
from .widget import ProjectItemWidget, CaseItemWidget, ImageItemWidget


class Explorer(QWidget):

    # 向外发送的业务信号
    image_selected = Signal(dict)

    # 向 Controller 发送的请求信号
    fetch_requested = Signal(str, dict, list)  # level, params, status_filters

    download_requested = Signal(str, str)  # image_id, save_path

    def __init__(self, base_cache_dir, parent = None):
        super().__init__(parent)

        self.base_cache_dir = base_cache_dir

        # 内部状态
        self.history_stack = []
        self.current_level = "root"
        self.current_params = { }
        self.current_project_id = ""
        self.current_case_id = ""
        self.current_case_name = ""

        self._query_status_pending = True
        self._query_status_annotating = True
        self._query_status_submitted = False
        self._query_status_skipped = False

        # --- UI 构建 ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        toolbar = QToolBar()
        toolbar.setFloatable(False)
        toolbar.setMovable(False)

        action = toolbar.addAction('未开始')
        action.setCheckable(True)
        action.setChecked(True)
        action.toggled.connect(self._on_query_status_pending_changed)

        action = toolbar.addAction('标注中')
        action.setCheckable(True)
        action.setChecked(True)
        action.toggled.connect(self._on_query_status_annotating_changed)

        action = toolbar.addAction('已提交')
        action.setCheckable(True)
        action.toggled.connect(self._on_query_status_skipped_submitted)

        action = toolbar.addAction('已废弃')
        action.setCheckable(True)
        action.toggled.connect(self._on_query_status_skipped_changed)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addSeparator()

        toolbar.addAction('返回上一级', self.on_back)
        layout.addWidget(toolbar)

        area = QVBoxLayout()
        area.setContentsMargins(4, 4, 4, 4)
        self.lbl_title = QLabel("加载中...")
        area.addWidget(self.lbl_title)
        layout.addLayout(area)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        area.addWidget(self.progress)

        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QListWidget.Shape.NoFrame)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # 映射 image_id -> ImageItemWidget
        self._image_item_map = { }

    def start(self):
        """初始化启动"""
        self.navigate_to("project", title = "资源库")

    def navigate_to(self, level, params: dict | None = None, title: str = ""):

        if self.current_level != "root":

            state = {
                "level":  self.current_level,
                "params": self.current_params,
                "title":  self.lbl_title.text()
            }

            self.history_stack.append(state)

        self.current_level = level
        self.current_params = params if params else { }
        self.lbl_title.setText(title)
        self.execute_request()

    def on_back(self):
        if not self.history_stack:
            return
        prev_state = self.history_stack.pop()
        self.current_level = prev_state["level"]
        self.current_params = prev_state["params"]
        self.lbl_title.setText(prev_state["title"])

        self.execute_request()

    def _on_query_status_pending_changed(self, checked: bool):
        self._query_status_pending = checked
        self.execute_request()

    def _on_query_status_annotating_changed(self, checked: bool):
        self._query_status_annotating = checked
        self.execute_request()

    def _on_query_status_skipped_submitted(self, checked: bool):
        self._query_status_submitted = checked
        self.execute_request()

    def _on_query_status_skipped_changed(self, checked: bool):
        self._query_status_skipped = checked
        self.execute_request()

    def execute_request(self):
        """触发当前级别的列表请求"""
        self.list_widget.clear()
        self._image_item_map.clear()
        self.progress.show()
        self.list_widget.setEnabled(False)

        # 收集过滤条件
        filters = []
        if self._query_status_pending:
            filters.append("Pending")
        if self._query_status_annotating:
            filters.append("Annotating")
        if self._query_status_submitted:
            filters.append("Submitted")
        if self._query_status_skipped:
            filters.append("Skipped")

        # 发送请求信号
        self.fetch_requested.emit(self.current_level, self.current_params, filters)

    @Slot(str, dict, dict)
    def on_data_loaded(self, req_type, response, request_params):

        if req_type != self.current_level:
            return

        self.progress.hide()
        self.list_widget.setEnabled(True)

        if response.get("code", 0) != 200:
            item = QListWidgetItem(f"Error: {response.get('msg')}")
            self.list_widget.addItem(item)
            return

        data_list = response.get("data", { }).get("items", [])
        if not data_list:
            item = QListWidgetItem("暂无数据")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)
            return

        for entry in data_list:
            item = QListWidgetItem(self.list_widget)

            if req_type == "project":
                widget = ProjectItemWidget(entry)
                item.setData(Qt.ItemDataRole.UserRole, entry)

            elif req_type == "case":
                widget = CaseItemWidget(entry)
                item.setData(Qt.ItemDataRole.UserRole, entry)

            elif req_type == "image":
                file_name = entry["name"]
                cache_dir = os.path.join(self.base_cache_dir, str(self.current_project_id), str(self.current_case_name))
                local_path = os.path.join(cache_dir, file_name)

                widget = ImageItemWidget(entry)

                if os.path.exists(local_path):
                    widget.set_image(local_path)
                else:
                    widget.set_downloading()
                    self.download_requested.emit(str(entry['id']), local_path)

                entry["image_path"] = local_path
                item.setData(Qt.ItemDataRole.UserRole, entry)

                # 记录映射
                self._image_item_map[str(entry['id'])] = widget

            else:
                continue

            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)

    @Slot(str)
    def on_data_error(self, err_msg):
        self.progress.hide()
        item = QListWidgetItem(f"网络错误: {err_msg}")
        item.setForeground(Qt.GlobalColor.red)
        self.list_widget.addItem(item)

    @Slot(str, str)
    def on_thumbnail_ready(self, image_id, local_path):
        widget = self._image_item_map.get(image_id)
        if widget:
            widget.set_image(local_path)

    @Slot(str, str, str, str)
    def on_entity_updated(self, project_id, case_id, image_id, status):
        """
        响应 Controller 的状态更新信号。
        不再进行本地 Item 状态修补，而是重新拉取列表，确保数据与服务器一致。
        """
        refresh_needed = False

        # 1. 如果当前正在查看该 Case 下的图片列表 -> 刷新 (图片状态变了)
        if self.current_level == "image" and str(self.current_case_id) == str(case_id):
            refresh_needed = True

        # 2. 如果当前正在查看该 Project 下的 Case 列表 -> 刷新 (Case 的统计/状态可能变了)
        elif self.current_level == "case" and str(self.current_project_id) == str(project_id):
            refresh_needed = True

        # 3. 如果正在查看 Project 列表 -> 刷新 (Project 的统计/状态可能变了)
        elif self.current_level == "project":
            refresh_needed = True

        if refresh_needed:
            self.execute_request()

    def on_item_double_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        if self.current_level == "project":
            project_id = data["id"]
            self.current_project_id = project_id
            self.current_case_id = ""
            self.current_case_name = ""
            self.navigate_to("case", params = { "project_id": project_id }, title = data["name"])

        elif self.current_level == "case":
            project_id = self.current_project_id
            case_id = data["id"]
            self.current_case_id = case_id
            self.current_case_name = data["attachment"]
            title = data["attachment"]
            title = title[:15] + "..." + title[-6:]
            self.navigate_to("image", params = { "project_id": project_id, "case_id": case_id }, title = title)

        elif self.current_level == "image":
            data = dict(data)
            data["project_id"] = self.current_project_id
            data["case_id"] = self.current_case_id
            data["case_name"] = self.current_case_name
            self.image_selected.emit(data)