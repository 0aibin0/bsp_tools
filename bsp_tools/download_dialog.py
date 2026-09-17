"""下载进度框。

为什么单独做一个：原来下载只靠右下角浮层报进度，浮层 1.5 秒就消失，
用户看到的就是"弹窗一闪而过"，不知道到底在下什么、下到哪了。这里是一个
**一直开着**的模态小窗口，百分比 / 已下载字节 / 文件名都写在上面，下载结束
（成功或失败）由调用方关掉它，接着弹结果框。

模态用 open()（非阻塞的 show + 应用级模态），不是 exec_()——下载在 QThread 里
跑，用嵌套事件循环容易把信号顺序搞乱。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QProgressBar, QDialogButtonBox)

import theme
import ui_widgets as W
import update_check


class DownloadDialog(QDialog):
    """下载进度：标题 + 文件名 + 进度条 + 百分比文字。"""

    def __init__(self, filename, total=0, parent=None, title="正在下载新版本"):
        super(DownloadDialog, self).__init__(parent)
        self.filename = filename
        self.total = int(total or 0)
        self._done = 0
        self.setWindowTitle(title)
        self.setStyleSheet(theme.build_stylesheet())
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build()
        self.set_progress(0, self.total)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        self.name_label = QLabel(self.filename, self)
        self.name_label.setWordWrap(True)
        self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.name_label)

        self.bar = QProgressBar(self)
        self.bar.setMinimumHeight(20)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

        self.detail_label = QLabel("", self)
        self.detail_label.setObjectName("pageSubtitle")
        layout.addWidget(self.detail_label)

        hint = QLabel("下载完成后会校验文件完整性（大小 + 可执行文件头）；"
                      "校验不通过会直接丢弃，绝不会拿半截文件去替换正在用的 exe。",
                      self)
        hint.setObjectName("pageSubtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch()
        self.hide_btn = W.soft_button("后台下载", "download", self)
        self.hide_btn.setToolTip("把进度框收起来，下载继续跑；结束后仍会弹结果")
        self.hide_btn.clicked.connect(self.hide)
        row.addWidget(self.hide_btn)

        close_box = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self)
        close_box.button(QDialogButtonBox.Close).setText("隐藏")
        close_box.rejected.connect(self.hide)
        row.addWidget(close_box)
        layout.addLayout(row)

    # ---------- 进度 ----------

    def set_progress(self, done, total):
        self._done = int(done or 0)
        if total:
            self.total = int(total)
            percent = int(self._done * 100 / self.total)
            self.bar.setRange(0, 100)
            self.bar.setValue(max(0, min(100, percent)))
            self.detail_label.setText("{} / {}（{}%）".format(
                update_check.human_size(self._done),
                update_check.human_size(self.total), percent))
        else:
            self.bar.setRange(0, 0)          # 未知总长：来回滚动的忙碌状态
            self.detail_label.setText("已下载 {}".format(
                update_check.human_size(self._done)))

    def percent(self):
        if not self.total:
            return 0
        return int(self._done * 100 / self.total)
