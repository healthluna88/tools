# src/ui/login.py

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QProgressBar, QFrame, QSizePolicy
)


class LoginWidget(QWidget):

    # 信号：用户名, 密码
    login_requested = Signal(str, str)

    def __init__(self, parent = None):
        super().__init__(parent)

        # 主布局，用于居中
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 容器 Frame
        self.container = QFrame()
        self.container.setFixedWidth(320)
        # self.container.setStyleSheet(
        #     """
        #     QFrame {
        #         background-color: #383838;
        #         border: 1px solid #555555;
        #         border-radius: 8px;
        #     }
        #     QLabel {
        #         color: #E0E0E0;
        #         font-size: 14px;
        #     }
        #     QLineEdit {
        #         background-color: #2b2b2b;
        #         color: #FFFFFF;
        #         border: 1px solid #555555;
        #         border-radius: 4px;
        #         padding: 8px;
        #         font-size: 14px;
        #     }
        #     QLineEdit:focus {
        #         border: 1px solid #1890ff;
        #     }
        #     QPushButton {
        #         background-color: #1890ff;
        #         color: white;
        #         border: none;
        #         border-radius: 4px;
        #         padding: 8px;
        #         font-size: 14px;
        #         font-weight: bold;
        #     }
        #     QPushButton:hover {
        #         background-color: #40a9ff;
        #     }
        #     QPushButton:pressed {
        #         background-color: #096dd9;
        #     }
        #     QPushButton:disabled {
        #         background-color: #555555;
        #         color: #888888;
        #     }
        # """
        #     )

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(30, 40, 30, 40)
        layout.setSpacing(20)

        # 标题
        title = QLabel("登录")
        # title.setStyleSheet("font-size: 20px; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 输入框
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("用户名")
        layout.addWidget(self.input_user)

        self.input_pwd = QLineEdit()
        self.input_pwd.setPlaceholderText("密码")
        self.input_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pwd.returnPressed.connect(self._on_submit)  # 回车登录
        layout.addWidget(self.input_pwd)

        # 按钮
        self.btn_login = QPushButton("登 录")
        self.btn_login.clicked.connect(self._on_submit)
        layout.addWidget(self.btn_login)

        # 错误信息
        # 预留空间策略：设置 retainSizeWhenHidden 和最小高度
        self.lbl_error = QLabel("")
        # self.lbl_error.setStyleSheet("color: #ff4d4f; border: none; font-size: 12px; min-height: 20px;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setWordWrap(True)

        sp_error = self.lbl_error.sizePolicy()
        sp_error.setRetainSizeWhenHidden(True)
        self.lbl_error.setSizePolicy(sp_error)
        self.lbl_error.hide()

        layout.addWidget(self.lbl_error)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)  # 忙碌模式

        # self.progress.setStyleSheet(
        #     """
        #     QProgressBar { border: none; background: transparent; }
        #     QProgressBar::chunk { background-color: #1890ff; }
        # """
        #     )

        # 预留空间策略：设置 retainSizeWhenHidden
        sp_progress = self.progress.sizePolicy()
        sp_progress.setRetainSizeWhenHidden(True)
        self.progress.setSizePolicy(sp_progress)
        self.progress.hide()

        layout.addWidget(self.progress)

        main_layout.addWidget(self.container)

    def _on_submit(self):
        user = self.input_user.text().strip()
        pwd = self.input_pwd.text().strip()
        if not user or not pwd:
            self.show_error("请输入用户名和密码")
            return

        self.set_loading(True)
        self.login_requested.emit(user, pwd)

    def set_loading(self, loading: bool):
        self.input_user.setEnabled(not loading)
        self.input_pwd.setEnabled(not loading)
        self.btn_login.setEnabled(not loading)
        if loading:
            self.progress.show()
            self.lbl_error.hide()
            self.btn_login.setText("登录中...")
        else:
            self.progress.hide()
            self.btn_login.setText("登 录")

    def show_error(self, msg: str):
        self.set_loading(False)
        self.lbl_error.setText(msg)
        self.lbl_error.show()

    def set_values(self, user, pwd):
        self.input_user.setText(user)
        self.input_pwd.setText(pwd)
