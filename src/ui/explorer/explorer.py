import os

from PySide6.QtCore import Qt, Signal, Slot

from PySide6.QtWidgets import QVBoxLayout, QWidget, QLabel, QProgressBar, QListWidget, QListWidgetItem, QToolBar, QSizePolicy

from infra.repository import Repository
from infra.scheduler  import TaskScheduler

from .widget import ProjectItemWidget, CaseItemWidget, ImageItemWidget


class Explorer(QWidget):

    image_selected = Signal(dict)

    def __init__(self, base_cache_dir, base_url, scheduler: TaskScheduler, repo: Repository, parent = None):

        super().__init__(parent)

        self.base_cache_dir = base_cache_dir
        self.base_url = base_url

        scheduler.task_result.connect(self._on_sched_result)
        scheduler.task_error.connect(self._on_sched_error)

        self._scheduler = scheduler
        self.repo = repo

        # --- 内部状态 ---

        self.history_stack = []  # 导航栈 [{"level":..., "params":..., "title":...}]
        self.current_level = "root"
        self.current_params = { }
        self.current_project_id = ""
        self.current_case_id = ""
        self.current_case_name = ""

        self._sched_req_kind = { }

        self._query_status_pending    = True
        self._query_status_annotating = True
        self._query_status_submitted  = False
        self._query_status_skipped    = False

        # 构建 UI
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
        toolbar.addAction('刷新', self.on_refresh)
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

        # 3. 列表区域
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QListWidget.Shape.NoFrame)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # 初始加载
        self.navigate_to("project", title = "资源库")

    def navigate_to(self, level, params: dict | None = None, title: str = ""):

        """前往新页面"""

        # 如果不是在根目录，记录当前状态到栈里

        if self.current_level != "root":

            state = \
                {
                    "level":  self.current_level,
                    "params": self.current_params,
                    "title":  self.lbl_title.text()
                }

            self.history_stack.append(state)
            # self.btn_back.show()

        # 更新当前状态

        self.current_level = level
        self.current_params = params if params else { }

        self.lbl_title.setText(title)

        # 执行请求
        self.execute_request()

    def on_back(self):

        """返回上一级"""

        if not self.history_stack:

            return

        # 弹出上一个状态
        prev_state = self.history_stack.pop()

        self.current_level = prev_state["level"]
        self.current_params = prev_state["params"]

        self.lbl_title.setText(prev_state["title"])

        # if not self.history_stack:
        #
        #     self.btn_back.hide()

        self.execute_request()

    def on_refresh(self):

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

        """根据 current_level 发起网络请求。

        step7: 彻底 repo 化列表请求：Explorer 不再构造 URL，不再直接依赖 NetworkWorker 来拉列表。
        """

        self.list_widget.clear()
        self.progress.show()
        self.list_widget.setEnabled(False)

        req_type = self.current_level
        params = dict(self.current_params or { })

        # if self._scheduler is not None and self.repo is not None:

        def do_call() -> dict:

            query_status = []

            if self._query_status_pending:

                query_status.append("Pending")

            if self._query_status_annotating:

                query_status.append("Annotating")

            if self._query_status_submitted:

                query_status.append("Submitted")

            if self._query_status_skipped:

                query_status.append("Skipped")

            if req_type == "project":

                return self.repo.list_projects(query_status)

            if req_type == "case":

                pid = str(params.get("project_id"))

                return self.repo.list_cases(pid, query_status)

            if req_type == "image":

                pid = str(params.get("project_id"))
                cid = str(params.get("case_id"))

                return self.repo.list_images(pid, cid, query_status)

            return { "code": 200, "data": [] }

        token = self._scheduler.submit(generation = 0, fn = do_call)

        self._sched_req_kind[token.request] = req_type

    # --- 数据处理 ---

    def handle_data(self, response, req_type, params):

        if response.get("code", 0) != 200:
            # 可以显示一个 Error Item 在列表中
            item = QListWidgetItem(f"Error: {response.get('msg')}")
            self.list_widget.addItem(item)
            return

        data = response.get("data", { })
        data_list = data.get("items", [])

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

                cache_dir = os.path.join(self.base_cache_dir, str(self.current_project_id), str(self.current_case_name))

                widget = ImageItemWidget(entry, self.repo, self._scheduler, cache_dir)

                entry["image_path"] = widget.local_path

                item.setData(Qt.ItemDataRole.UserRole, entry)

            else:

                continue

            item.setSizeHint(widget.sizeHint())

            self.list_widget.setItemWidget(item, widget)

    def handle_error(self, err_msg):
        item = QListWidgetItem(f"网络错误: {err_msg}")
        item.setForeground(Qt.GlobalColor.red)
        self.list_widget.addItem(item)

    def handle_finished(self):
        self.progress.hide()
        self.list_widget.setEnabled(True)

    # --- 交互事件 ---

    def on_item_double_clicked(self, item: QListWidgetItem):

        data = item.data(Qt.ItemDataRole.UserRole)

        if not data:

            return  # 可能是 Error Item

        if self.current_level == "project":

            # 逻辑：进入下一级 (Case 列表)

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

            # 逻辑：进入下一级 (Image 列表)
            title = data["attachment"]
            title = title[:15] + "..." + title[-6:]

            self.navigate_to("image", params = { "project_id": project_id, "case_id": case_id }, title = title)

        elif self.current_level == "image":

            # 逻辑：到达末梢，发射信号给外部主程序
            # 补齐当前层级上下文，便于上层做强一致提交/切换
            data = dict(data)
            data["project_id"] = self.current_project_id
            data["case_id"] = self.current_case_id
            data["case_name"] = self.current_case_name

            self.image_selected.emit(data)

    @Slot(int, int, object)
    def _on_sched_result(self, request_id: int, generation: int, result: object) -> None:

        kind = self._sched_req_kind.get(request_id, "")

        if kind not in ("project", "case", "image"):

            return

        # result should be a dict shaped like backend response: {code, data, msg...}

        self.handle_data(result, kind, dict(self.current_params))
        self.handle_finished()

    @Slot(int, int, object)
    def _on_sched_error(self, request_id: int, generation: int, err: object) -> None:
        kind = self._sched_req_kind.get(request_id, "")
        if kind not in ("project", "case", "image"):
            return
        self.handle_error(str(err))
        self.handle_finished()
