"""常用页面的可复用 UI 组件：卡片、统计格、表单行等。"""

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QWidget, QSizePolicy, QScrollArea)

import theme


class Card(QFrame):
    """带标题的白色圆角卡片。"""

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(9)

        self.header = None
        self.title_label = None
        if title is not None:
            self.header = QHBoxLayout()
            self.header.setContentsMargins(0, 0, 0, 0)
            self.header.setSpacing(8)
            self.title_label = QLabel(title, self)
            self.title_label.setStyleSheet(
                "color: %s; font-size: 13px; font-weight: 600;"
                " background: transparent;" % theme.TEXT)
            self.header.addWidget(self.title_label)
            self.header.addStretch()
            self.body.addLayout(self.header)

    def add_trailing(self, widget):
        """把控件放到卡片标题右侧。"""
        if self.header is None:
            self.body.addWidget(widget)
        else:
            self.header.addWidget(widget)
        return widget

    def add(self, widget, stretch=0):
        self.body.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout, stretch=0):
        self.body.addLayout(layout, stretch)
        return layout

    def add_row(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.body.addLayout(row)
        return row


class ElidedLabel(QLabel):
    """放不下时自动显示省略号的标签。

    指标卡里会出现设备型号、内核版本这类不定长文本，直接用 QLabel 会被
    硬生生截断（看起来像丢了字），这里按控件宽度做中间省略。
    """

    def __init__(self, text="", parent=None, mode=Qt.ElideMiddle):
        super().__init__(text, parent)
        self._full_text = text
        self._mode = mode

    def setText(self, text):
        self._full_text = text or ""
        super().setText(self._full_text)
        self.setToolTip(self._full_text if len(self._full_text) > 12 else "")
        self._apply_elide()

    def fullText(self):
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        if not self._full_text:
            return
        width = max(self.width() - 2, 10)
        shown = self.fontMetrics().elidedText(self._full_text, self._mode, width)
        if shown != super().text():
            QLabel.setText(self, shown)


class StatCard(QFrame):
    """指标卡：上方数值，下方说明。"""

    def __init__(self, label, value="--", unit="", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumWidth(116)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(1)

        self.value_label = ElidedLabel(value, self)
        self.value_label.setObjectName("statValue")
        self.unit = unit
        self.label = QLabel(label, self)
        self.label.setObjectName("statLabel")

        layout.addWidget(self.value_label)
        layout.addWidget(self.label)

    def set_value(self, value, tone=None):
        text = f"{value}{self.unit}" if value not in (None, "") else "--"
        self.value_label.setText(text)
        self.value_label.setProperty("tone", tone or "default")
        self.value_label.style().unpolish(self.value_label)
        self.value_label.style().polish(self.value_label)
        self.value_label.update()


def heading(text, parent=None):
    """小号分组说明文字。

    必须开启自动换行：QLabel 不换行时 minimumSizeHint 就是整句文字宽度，
    会把所在卡片（进而整个模块）撑得很宽——大屏看不出来，窄窗口就会横向滚动。
    尺寸策略保持默认，不要用 Ignored：那会让右对齐的小标签（如「0 条」）
    被布局压到最小宽度以下而露出边界。
    """
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setMinimumWidth(64)
    label.setStyleSheet(
        f"color: {theme.TEXT_FAINT}; font-size: 12px; background: transparent;")
    return label


def field_label(text, parent=None):
    label = QLabel(text, parent)
    label.setStyleSheet(
        f"color: {theme.TEXT_MUTED}; font-size: 12px; background: transparent;")
    return label


def accent_button(text, icon_name=None, parent=None):
    btn = QPushButton(text, parent)
    btn.setProperty("accent", True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(30)
    if icon_name:
        btn.setIcon(theme.icon(icon_name, "#ffffff", 16, 1.7))
        btn.setIconSize(QSize(16, 16))
    return btn


def soft_button(text, icon_name=None, parent=None):
    btn = QPushButton(text, parent)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(30)
    if icon_name:
        btn.setIcon(theme.icon(icon_name, theme.TEXT_MUTED, 16, 1.7))
        btn.setIconSize(QSize(16, 16))
    return btn


def danger_button(text, icon_name=None, parent=None):
    btn = QPushButton(text, parent)
    btn.setProperty("danger", True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(30)
    if icon_name:
        btn.setIcon(theme.icon(icon_name, theme.DANGER, 16, 1.7))
        btn.setIconSize(QSize(16, 16))
    return btn


def separator(parent=None):
    line = QFrame(parent)
    line.setObjectName("hline")
    line.setFrameShape(QFrame.NoFrame)
    line.setFixedHeight(1)
    return line


def scrollable(inner, parent=None):
    """把控件包进竖向滚动区，窗口变小时依然可用。"""
    area = QScrollArea(parent)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(inner)
    return area
