import os

from PySide6.QtCore    import Qt, Slot
from PySide6.QtGui     import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QLabel

from infra.repository import Repository
from infra.scheduler import TaskScheduler


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

    """显示 Case 信息的自定义组件"""

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

    def __init__(self, metadata, repository: Repository, scheduler: TaskScheduler, cache_dir):

        super().__init__()

        self._scheduler_kind: dict[int, str] = { }

        scheduler.task_result.connect(self._on_scheduler_result)
        scheduler.task_error .connect(self._on_scheduler_error )

        self.data = metadata
        self.repository = repository
        self.scheduler = scheduler
        self.cache_dir = cache_dir  # 传入这一层对应的缓存文件夹路径

        file_name = metadata["name"]

        # 构造保存路径： 传入的目录/文件名
        self.local_path = os.path.join(self.cache_dir, file_name)

        # --- 布局 ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 1. 图片容器 (Label)
        self.img_label = QLabel()
        self.img_label.setFixedSize(120, 80)  # 缩略图固定大小
        self.img_label.setStyleSheet("background-color: #eee; border: 1px solid #ccc;")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.img_label)

        # 2. 信息区域
        info_layout = QVBoxLayout()
        name_lbl = QLabel(metadata.get('name', 'Unknown.jpg'))
        name_lbl.setStyleSheet("font-size: 12px; font-weight: bold;")

        status = metadata.get('status', 'Pending')
        status_lbl = QLabel(status)
        color = "#52c41a" if status == 'Annotating' else "#999"
        status_lbl.setStyleSheet(f"color: {color}; font-size: 10px;")

        info_layout.addWidget(name_lbl)
        info_layout.addWidget(status_lbl)
        layout.addLayout(info_layout)

        # --- 启动加载逻辑 ---
        self.load_image()

    def load_image(self):

        if os.path.exists(self.local_path):

            self.set_image(self.local_path)

        else:

            self.img_label.setText("Downloading...")

            def download():

                image_id  = self.data.get('id')
                save_path = str(self.local_path)

                self.repository.download_image(image_id, save_path)

                return save_path

            token = self.scheduler.submit(generation = 0, fn = download)

            self._scheduler_kind[token.request] = 'download'

    def set_image(self, file_path):

        pixmap = QPixmap(file_path)

        if not pixmap.isNull():

            # 缩放图片以适应 Label (保持比例)
            scaled_pix = pixmap.scaled(self.img_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.img_label.setPixmap(scaled_pix)
            self.img_label.setText("")  # 清空文字
        else:
            self.img_label.setText("Error")

    @Slot(int, int, object)
    def _on_scheduler_result(self, request: int, generation: int, result: object) -> None:

        kind = self._scheduler_kind.get(request, "")

        if kind == "download":

            self.set_image(result)

    @Slot(int, int, object)
    def _on_scheduler_error(self, request: int, generation: int, error: object) -> None:

        kind = self._scheduler_kind.get(request, "")

        if kind == "download":

            return

