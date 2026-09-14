from PyQt5.QtWidgets import QWidget, QTextEdit, QLabel, QApplication
from PyQt5.QtCore import QTimer


class BaseToolPage(QWidget):
    """所有工具页面的公共基类，提供清空、复制、状态提示等共享方法"""

    def clear_textedits(self, *edits):
        """清空指定的 QTextEdit 控件"""
        for edit in edits:
            if isinstance(edit, QTextEdit):
                edit.clear()

    def copy_to_clipboard(self, edit):
        """将 QTextEdit 内容复制到剪贴板"""
        if isinstance(edit, QTextEdit):
            text = edit.toPlainText()
            if text.strip():
                QApplication.clipboard().setText(text)

    def show_status_tip(self, label, text, duration=3000):
        """在指定 label 显示临时提示文字，duration 毫秒后自动清除"""
        if isinstance(label, QLabel):
            label.setText(text)
            QTimer.singleShot(duration, lambda: label.setText(""))
