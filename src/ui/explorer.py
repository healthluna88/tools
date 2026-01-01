# src/ui/explorer/explorer.py

import os
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QVBoxLayout, QWidget, QLabel, QProgressBar, QListWidget,
    QListWidgetItem, QToolBar, QSizePolicy, QHBoxLayout
)


class Explorer(QWidget):

    class ProjectItemWidget(QWidget):
        def __init__(self, data):
            super().__init__()
            self.data = data
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            name_lbl = QLabel(f"{data.get('name', 'Unknown')}")
            status_lbl = QLabel(data.get('status', 'Pending'))
            time_str = data.get('updated_at', '').replace('T', ' ').split('.')[0]
            time_lbl = QLabel(f"更新于: {time_str}")

            layout_info = QHBoxLayout()
            layout_info.setContentsMargins(0, 0, 0, 0)
            layout_info.addWidget(status_lbl)
            layout_info.addStretch()
            layout_info.addWidget(time_lbl)

            layout.addWidget(name_lbl)
            layout.addLayout(layout_info)

    class CaseItemWidget(QWidget):
        def __init__(self, data):
            super().__init__()
            self.data = data

            layout = QVBoxLayout(self)
            layout.setContentsMargins(5, 5, 5, 5)
            layout.setSpacing(2)

            # 附件名
            att = data.get('attachment', 'No File')
            display_name = (att if len(att) < 20 else att[:15] + "..." + att[-6:])
            file_lbl = QLabel(display_name)

            # 底部信息
            bot_layout = QHBoxLayout()
            id_lbl = QLabel(f"ID: {data.get('id')}")

            status_lbl = QLabel(data.get('status', 'Pending'))

            bot_layout.addWidget(id_lbl)
            bot_layout.addStretch()
            bot_layout.addWidget(status_lbl)

            layout.addWidget(file_lbl)
            layout.addLayout(bot_layout)

    class ImageItemWidget(QWidget):
        def __init__(self, metadata):
            super().__init__()

            self.data = metadata

            layout = QHBoxLayout(self)
            layout.setContentsMargins(5, 5, 5, 5)

            # 1. 图片容器
            self.img_label = QLabel()
            self.img_label.setFixedSize(120, 80)
            self.img_label.setStyleSheet("background-color: #eee; border: 1px solid #ccc;")
            self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.img_label)

            # 2. 信息区域
            info_layout = QVBoxLayout()
            name_lbl = QLabel(metadata.get('name', 'Unknown.jpg'))
            name_lbl.setStyleSheet("font-size: 12px; font-weight: bold;")

            status = metadata.get('status', 'Pending')
            status_lbl = QLabel(status)

            # 根据状态设置颜色
            color = "#999"  # Default/Pending
            if status == 'Annotating':
                color = "#1890ff"  # Blue
            elif status == 'Submitted':
                color = "#52c41a"  # Green
            elif status == 'Skipped':
                color = "#ff4d4f"  # Red

            status_lbl.setStyleSheet(f"color: {color}; font-size: 10px;")

            info_layout.addWidget(name_lbl)
            info_layout.addWidget(status_lbl)
            layout.addLayout(info_layout)

            # 初始状态
            self.set_loading()

        def set_loading(self):
            self.img_label.setText("Waiting...")

        def set_downloading(self):
            self.img_label.setText("Downloading...")

        def set_error(self):
            self.img_label.setText("Error")

        def set_image(self, file_path):
            """由 Explorer 外部调用此方法来更新显示"""
            if not os.path.exists(file_path):
                self.set_error()
                return

            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                scaled_pix = pixmap.scaled(self.img_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.img_label.setPixmap(scaled_pix)
                self.img_label.setText("")
            else:
                self.img_label.setText("Invalid")

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

        # [FIX] 请求序列号，解决并发响应导致的列表重复/状态错乱问题
        self._req_sequence = 0

        # UI Filters (用户手动操作时的状态)
        self._query_status_pending = True
        self._query_status_annotating = True
        self._query_status_submitted = False
        self._query_status_skipped = False

        # --- Auto Load Logic ---
        self._auto_mode = True
        self._is_searching = False
        self._auto_skip_ids = set()

        # --- UI 构建 ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        toolbar = QToolBar()
        toolbar.setFloatable(False)
        toolbar.setMovable(False)

        # 自动跳转开关
        self.action_auto = toolbar.addAction("自动加载")
        self.action_auto.setCheckable(True)
        self.action_auto.setChecked(True)
        self.action_auto.toggled.connect(self._on_auto_mode_toggled)

        toolbar.addSeparator()

        self.action_pending = toolbar.addAction('未开始')
        self.action_pending.setCheckable(True)
        self.action_pending.setChecked(True)
        self.action_pending.toggled.connect(self._on_query_status_pending_changed)

        self.action_annotating = toolbar.addAction('标注中')
        self.action_annotating.setCheckable(True)
        self.action_annotating.setChecked(True)
        self.action_annotating.toggled.connect(self._on_query_status_annotating_changed)

        self.action_submitted = toolbar.addAction('已提交')
        self.action_submitted.setCheckable(True)
        self.action_submitted.toggled.connect(self._on_query_status_submitted)

        self.action_skipped = toolbar.addAction('已废弃')
        self.action_skipped.setCheckable(True)
        self.action_skipped.toggled.connect(self._on_query_status_skipped)

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

    def try_auto_load(self):
        """外部（如Controller）触发自动跳转。仅在 Auto Mode 开启时生效。"""
        if not self._auto_mode:
            return

        # 标记进入搜索状态。此状态下 execute_request 会使用专用过滤条件
        self._is_searching = True
        self.lbl_title.setText("正在查找任务...")

        # 触发当前层级的刷新。在 on_data_loaded 中会处理跳转逻辑
        self.execute_request()

    def navigate_to(self, level, params: dict | None = None, title: str = ""):
        if self.current_level != "root":
            state = {
                "level":      self.current_level,
                "params":     self.current_params,
                "title":      self.lbl_title.text(),
                "project_id": self.current_project_id,
                "case_id":    self.current_case_id,
                "case_name":  self.current_case_name
            }
            self.history_stack.append(state)

        self.current_level = level
        self.current_params = params if params else { }
        self.lbl_title.setText(title)
        self.execute_request()

    def on_back(self):
        if not self.history_stack:
            return

        # 如果是自动模式下回退，意味着子节点为空，需要记录当前子节点ID以跳过
        if self._is_searching:
            if self.current_level == "image" and self.current_case_id:
                self._auto_skip_ids.add(str(self.current_case_id))
            elif self.current_level == "case" and self.current_project_id:
                self._auto_skip_ids.add(str(self.current_project_id))

        prev_state = self.history_stack.pop()
        self.current_level = prev_state["level"]
        self.current_params = prev_state["params"]
        self.current_project_id = prev_state.get("project_id", "")
        self.current_case_id = prev_state.get("case_id", "")
        self.current_case_name = prev_state.get("case_name", "")
        self.lbl_title.setText(prev_state["title"])

        self.execute_request()

    def _on_auto_mode_toggled(self, checked: bool):
        self._auto_mode = checked

        # 切换开关不再影响 UI 控件的状态 (Enable/Disable)
        # 如果开启了自动模式，重置搜索黑名单并尝试开始
        if checked:
            self._auto_skip_ids.clear()
            self.try_auto_load()

    def _on_query_status_pending_changed(self, checked: bool):
        self._query_status_pending = checked
        # 仅当不在自动搜索过程中时，UI 操作才触发刷新
        if not self._is_searching:
            self.execute_request()

    def _on_query_status_annotating_changed(self, checked: bool):
        self._query_status_annotating = checked
        if not self._is_searching:
            self.execute_request()

    def _on_query_status_submitted(self, checked: bool):
        self._query_status_submitted = checked
        if not self._is_searching:
            self.execute_request()

    def _on_query_status_skipped(self, checked: bool):
        self._query_status_skipped = checked
        if not self._is_searching:
            self.execute_request()

    def execute_request(self):
        """触发当前级别的列表请求"""
        # [FIX] 清空列表是必要的，防止重复。
        self.list_widget.clear()
        self._image_item_map.clear()
        self.progress.show()
        self.list_widget.setEnabled(False)

        # [FIX] 递增序列号，并混入请求参数中
        self._req_sequence += 1
        req_params = dict(self.current_params)
        req_params["_req_seq"] = self._req_sequence

        # 分离查询条件构造
        filters = []
        if self._is_searching:
            # 自动加载模式：强制构造独立的查询条件
            filters = ["Pending", "Annotating"]
        else:
            # 用户浏览模式：完全尊重 UI 设置
            if self._query_status_pending:
                filters.append("Pending")
            if self._query_status_annotating:
                filters.append("Annotating")
            if self._query_status_submitted:
                filters.append("Submitted")
            if self._query_status_skipped:
                filters.append("Skipped")

        # 发送请求信号
        self.fetch_requested.emit(self.current_level, req_params, filters)

    @Slot(str, dict, dict)
    def on_data_loaded(self, req_type, response, request_params):
        if req_type != self.current_level:
            return

        # [FIX] 核心修复：过期响应丢弃
        # 如果这个响应的序列号不等于当前最新的序列号，说明它是旧的请求，直接丢弃
        resp_seq = request_params.get("_req_seq", -1)
        if resp_seq != self._req_sequence:
            return

        self.progress.hide()
        self.list_widget.setEnabled(True)

        if response.get("code", 0) != 200:
            if self._is_searching:
                self.lbl_title.setText(f"自动加载出错: {response.get('msg')}")
                self._is_searching = False

            item = QListWidgetItem(f"Error: {response.get('msg')}")
            self.list_widget.addItem(item)
            return

        raw_items = response.get("data", { }).get("items", [])

        # 如果在自动搜索模式，我们需要处理数据并决定下一步
        if self._is_searching:
            self._handle_auto_load_logic(req_type, raw_items)
            return

        # --- 以下为常规显示逻辑 ---
        if not raw_items:
            item = QListWidgetItem("暂无数据")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)
            return

        for entry in raw_items:
            item = QListWidgetItem(self.list_widget)

            if req_type == "project":
                widget = Explorer.ProjectItemWidget(entry)
                item.setData(Qt.ItemDataRole.UserRole, entry)

            elif req_type == "case":
                widget = Explorer.CaseItemWidget(entry)
                item.setData(Qt.ItemDataRole.UserRole, entry)

            elif req_type == "image":
                file_name = entry["name"]
                cache_dir = os.path.join(self.base_cache_dir, str(self.current_project_id), str(self.current_case_name))
                local_path = os.path.join(cache_dir, file_name)

                widget = Explorer.ImageItemWidget(entry)

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

    def _handle_auto_load_logic(self, req_type, items):
        """处理自动跳转的递归查找逻辑"""

        # 过滤掉已知的死胡同ID (Project/Case)
        valid_items = []
        for it in items:
            if str(it['id']) not in self._auto_skip_ids:
                valid_items.append(it)

        # 1. 如果当前层级没有有效数据 -> 回退上一级
        if not valid_items:
            if self.history_stack:
                self.on_back()  # 回退会触发上一级的 execute_request，继续循环
            else:
                # 已经回退到根节点(Project)且无数据，说明真的没有任务了
                self._is_searching = False
                self.lbl_title.setText("当前无待办任务")
                item = QListWidgetItem("当前无待办任务")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.list_widget.addItem(item)
            return

        # 2. 如果有数据，取第一个
        target = valid_items[0]

        if req_type == "image":
            # 找到图片 -> 选中 -> 结束搜索
            self._is_searching = False
            self.lbl_title.setText(self.current_case_name)  # 恢复标题

            # 构造完整数据进行发射
            data = dict(target)

            # 计算路径用于加载
            file_name = data["name"]
            cache_dir = os.path.join(self.base_cache_dir, str(self.current_project_id), str(self.current_case_name))
            local_path = os.path.join(cache_dir, file_name)
            data["image_path"] = local_path

            if not os.path.exists(local_path):
                self.download_requested.emit(str(data['id']), local_path)

            data["project_id"] = self.current_project_id
            data["case_id"] = self.current_case_id
            data["case_name"] = self.current_case_name

            self.image_selected.emit(data)

            # 刷新一下列表UI显示当前这一项
            # [FIX] 这里调用 execute_request 会生成新的 seq，从而使之前的任何延迟响应无效化
            self.execute_request()

        elif req_type == "case":
            # 找到 Case -> 进入 Case -> 继续搜图
            case_id = target["id"]
            self.current_case_id = case_id
            self.current_case_name = target["attachment"]
            title = self.current_case_name
            title = title[:15] + "..." + title[-6:]
            self.navigate_to("image", params = { "project_id": self.current_project_id, "case_id": case_id }, title = title)

        elif req_type == "project":
            # 找到 Project -> 进入 Project -> 继续搜 Case
            project_id = target["id"]
            self.current_project_id = project_id
            self.current_case_id = ""
            self.current_case_name = ""
            self.navigate_to("case", params = { "project_id": project_id }, title = target["name"])

    @Slot(str)
    def on_data_error(self, err_msg):
        self.progress.hide()
        if self._is_searching:
            self._is_searching = False
            self.lbl_title.setText("自动加载中断")

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
        如果是自动模式且正在自动搜索中，忽略常规刷新，由搜索逻辑主导。
        如果不是搜索中，才刷新列表。
        """
        if self._is_searching:
            return

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