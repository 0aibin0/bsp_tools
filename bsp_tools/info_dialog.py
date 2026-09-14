"""固定尺寸 + 可滚动的说明对话框（帮助 / 更新日志 / 崩溃日志 / 关于）。

为什么不用 QMessageBox：它的正文是 QLabel，文字一长对话框就跟着变长，
屏幕上放不下的部分**直接看不到**，也没法滚动——更新日志就是这么变成
"看不全"的。这里改成固定大小，正文放进只读文本区，滚轮 / 方向键 /
PageUp·PageDown / 拖动滚动条都能翻。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
                             QPushButton, QDialogButtonBox, QApplication)

import theme

# 默认尺寸：够放一屏更新日志，又不会顶到小屏的边
DEFAULT_WIDTH = 820
DEFAULT_HEIGHT = 620
# 小屏兜底：留出边距，别让对话框比屏幕还大
MIN_WIDTH = 480
MIN_HEIGHT = 320
SCREEN_MARGIN = 80


def fit_to_screen(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT):
    """按当前屏幕可用区域收一下尺寸，避免小屏上对话框超出屏幕。"""
    screen = QApplication.primaryScreen()
    if screen is None:
        return width, height
    available = screen.availableGeometry()
    return (max(MIN_WIDTH, min(width, available.width() - SCREEN_MARGIN)),
            max(MIN_HEIGHT, min(height, available.height() - SCREEN_MARGIN)))


class InfoDialog(QDialog):
    """固定尺寸的说明框：正文可滚动，可选若干额外操作按钮。

    actions: [(按钮文字, 回调), ...]，回调返回 True 表示点了之后要关掉对话框
             （例如"检查更新"触发后台任务后就可以关掉）。
    """

    def __init__(self, title, text, parent=None, actions=None,
                 width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(theme.build_stylesheet())
        self._clicked_action = None

        width, height = fit_to_screen(width, height)
        # 固定尺寸：内容再长也不撑大窗口，靠滚动看
        self.setFixedSize(width, height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        self.view = QPlainTextEdit(self)
        self.view.setObjectName("infoView")
        self.view.setReadOnly(True)
        self.view.setPlainText(text or "")
        self.view.setFont(theme.app_font())
        # 光标默认落在开头，打开就能从头读；滚轮/方向键直接可用
        self.view.moveCursor(self.view.textCursor().Start)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(self.view, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)

        self._action_buttons = []
        for label, callback in (actions or []):
            btn = QPushButton(label, self)
            btn.setMinimumHeight(28)
            btn.clicked.connect(lambda _c=False, cb=callback, name=label:
                                self._run_action(name, cb))
            buttons.addButton(btn, QDialogButtonBox.ActionRole)
            self._action_buttons.append((label, btn))
        layout.addWidget(buttons)

        # 关闭按钮放最右，符合习惯
        close_btn = buttons.button(QDialogButtonBox.Close)
        if close_btn is not None:
            close_btn.setDefault(True)

    def _run_action(self, name, callback):
        self._clicked_action = name
        keep_open = False
        if callable(callback):
            try:
                keep_open = bool(callback())
            except Exception:                              # noqa: BLE001
                keep_open = False
        if not keep_open:
            self.accept()

    def clicked_action(self):
        """哪个额外按钮被点了（没点返回 None），给调用方判断用。"""
        return self._clicked_action

    def is_scrollable(self):
        """正文是不是超出可视区域了（给自测用）。"""
        bar = self.view.verticalScrollBar()
        return bar.maximum() > bar.minimum()

    def scroll_to_bottom(self):
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
