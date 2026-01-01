import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget, QLabel


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
