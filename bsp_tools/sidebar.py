"""左侧边栏导航组件。

替代原来的 QTabWidget，提供更现代的分区导航体验：
- 深色背景 + 选中态高亮
- 分组小标题
- 矢量线性图标
"""

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QButtonGroup, QSizePolicy)

import theme


class NavButton(QPushButton):
    """侧边栏导航按钮：图标 + 文案，可选中。"""

    def __init__(self, key, text, icon_name, parent=None):
        super().__init__(text, parent)
        self.key = key
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumHeight(38)
        self._icon_name = icon_name
        self._refresh_icon()

    def _refresh_icon(self):
        color = "#ffffff" if self.isChecked() else theme.SIDEBAR_TEXT
        self.setIcon(theme.icon(self._icon_name, color, 18, 1.7))

    def setChecked(self, checked):
        super().setChecked(checked)
        self._refresh_icon()


class Sidebar(QFrame):
    """应用侧边栏。"""

    pageSelected = pyqtSignal(str)
    quickAction = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(theme.SIDEBAR_WIDTH)

        self._buttons = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._current = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 14)
        layout.setSpacing(4)

        layout.addWidget(self._build_brand())
        layout.addSpacing(10)
        layout.addWidget(self._make_separator())
        layout.addSpacing(8)

        self._nav_layout = layout
        self._footer_spacer = None

    # ---------- 构建 ----------

    def _build_brand(self):
        box = QWidget(self)
        row = QHBoxLayout(box)
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(10)

        logo = QLabel(box)
        logo.setFixedSize(34, 34)
        logo.setPixmap(theme.icon("monitor", "#ffffff", 22, 1.8).pixmap(22, 22))
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"background: {theme.PRIMARY}; border-radius: 9px;")
        row.addWidget(logo)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(0)
        title = QLabel(theme.APP_NAME, box)
        title.setObjectName("brandTitle")
        sub = QLabel(f"BSP 调试工具集 · {theme.APP_VERSION}", box)
        sub.setObjectName("brandSub")
        texts.addWidget(title)
        texts.addWidget(sub)
        row.addLayout(texts)
        row.addStretch()
        return box

    def _make_separator(self):
        line = QFrame(self)
        line.setObjectName("sidebarSep")
        line.setFrameShape(QFrame.NoFrame)
        line.setFixedHeight(1)
        return line

    # ---------- 公开 API ----------

    def add_section(self, title):
        """添加一个分组小标题。"""
        label = QLabel(title.upper(), self)
        label.setObjectName("navSection")
        label.setContentsMargins(6, 0, 0, 0)
        self._nav_layout.addSpacing(8)
        self._nav_layout.addWidget(label)
        self._nav_layout.addSpacing(2)

    def add_page(self, key, text, icon_name):
        """添加一个导航项。"""
        btn = NavButton(key, text, icon_name, self)
        btn.clicked.connect(lambda: self.select(key))
        self._group.addButton(btn)
        self._buttons[key] = btn
        self._nav_layout.addWidget(btn)
        return btn

    def add_quick_actions(self, title, actions):
        """在底部添加一组紧凑的快捷操作按钮。

        actions: [(key, 文案, 图标名), ...]
        """
        self._quick_layout = QVBoxLayout()
        self._quick_layout.setContentsMargins(0, 0, 0, 0)
        self._quick_layout.setSpacing(3)

        label = QLabel(title.upper(), self)
        label.setObjectName("navSection")
        label.setContentsMargins(6, 0, 0, 0)
        self._quick_layout.addWidget(label)
        self._quick_layout.addSpacing(2)

        self._quick_buttons = {}
        for key, text, icon_name in actions:
            btn = QPushButton(text, self)
            btn.setObjectName("quickAction")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(theme.icon(icon_name, theme.SIDEBAR_TEXT, 15, 1.6))
            btn.setIconSize(QSize(15, 15))
            btn.setMinimumHeight(30)
            btn.clicked.connect(lambda _c=False, k=key: self.quickAction.emit(k))
            self._quick_buttons[key] = btn
            self._quick_layout.addWidget(btn)

        self._nav_layout.addStretch(1)
        self._nav_layout.addLayout(self._quick_layout)
        return self._quick_buttons

    def add_footer(self):
        """在底部添加版权信息。"""
        self._nav_layout.addSpacing(8)
        self._nav_layout.addWidget(self._make_separator())
        self._nav_layout.addSpacing(8)

        footer = QLabel(f"by {theme.APP_AUTHOR}", self)
        footer.setObjectName("sidebarFooter")
        footer.setAlignment(Qt.AlignCenter)
        self._nav_layout.addWidget(footer)

    def select(self, key, emit=True):
        """选中指定导航项。"""
        btn = self._buttons.get(key)
        if btn is None:
            return
        btn.setChecked(True)
        if btn.isChecked():
            self._current = key
        # 刷新其它按钮图标颜色
        for k, b in self._buttons.items():
            if k != key:
                b.setChecked(False)
                b._refresh_icon()
        if emit:
            self.pageSelected.emit(key)

    def current_key(self):
        return self._current
