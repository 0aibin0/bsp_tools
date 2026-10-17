"""亮度表（screenBrightnessMap）生成与校验对话框。

从「显示调试 · 背光 / 亮度」卡片打开：左边填采样点，右边出校验结论与 XML，
避免手写 XML 时把 value/nits 写成递减——那会让 system_server 崩溃重启。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPlainTextEdit, QPushButton, QApplication)

import brightness_map
import theme

DEFAULT_WIDTH = 860
DEFAULT_HEIGHT = 560

SAMPLE = """\
# 一行一个点：value(0..1)  nits   [最后一列写 HBM 表示高亮区起点]
0.000000    1.000000
0.050000    3.000000
0.200000   14.000000
0.500000  120.000000
0.800000  800.000000
1.000000 1200.000000  HBM
"""


class BrightnessMapDialog(QDialog):
    """亮度表编辑 + 校验 + 生成。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("亮度表 · screenBrightnessMap")
        self.setStyleSheet(theme.build_stylesheet())
        self.setMinimumSize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        title = QLabel("亮度表（screenBrightnessMap）", self)
        title.setStyleSheet(
            "color: %s; font-size: 14px; font-weight: 600; background: transparent;"
            % theme.TEXT)
        layout.addWidget(title)

        hint = QLabel(
            "value 与 nits 都必须「非递减」，否则整张表会被丢弃、system_server 崩溃重启。"
            "HBM 不能内嵌（会被静默跳过），要并进顶层表并把最后一段标成 HBM；"
            "transitionPoint = 最后一个非 HBM 点的 value。", self)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: %s; font-size: 12px; background: transparent;" % theme.TEXT_MUTED)
        layout.addWidget(hint)

        columns = QHBoxLayout()
        columns.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(self._label("采样点（value  nits  [HBM]）"))
        self.input_edit = QPlainTextEdit(self)
        self.input_edit.setPlainText(SAMPLE)
        self.input_edit.setMinimumWidth(320)
        left.addWidget(self.input_edit)
        columns.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(self._label("生成结果 / 校验结论"))
        self.output_edit = QPlainTextEdit(self)
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumWidth(380)
        right.addWidget(self.output_edit)
        columns.addLayout(right, 1)

        layout.addLayout(columns, 1)

        self.status = QLabel("点「校验」检查单调性与 HBM 分段", self)
        self.status.setWordWrap(True)
        self.status.setStyleSheet(
            "color: %s; font-size: 12px; background: transparent;" % theme.TEXT_MUTED)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.check_button = QPushButton("校验", self)
        self.check_button.setProperty("accent", True)
        self.check_button.setMinimumHeight(30)
        self.check_button.clicked.connect(self.on_check)
        buttons.addWidget(self.check_button)

        self.build_button = QPushButton("生成 XML", self)
        self.build_button.setMinimumHeight(30)
        self.build_button.clicked.connect(self.on_build)
        buttons.addWidget(self.build_button)

        self.copy_button = QPushButton("复制 XML", self)
        self.copy_button.setMinimumHeight(30)
        self.copy_button.clicked.connect(self.on_copy)
        buttons.addWidget(self.copy_button)

        buttons.addStretch()
        close_button = QPushButton("关闭", self)
        close_button.setMinimumHeight(30)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _label(self, text):
        label = QLabel(text, self)
        label.setStyleSheet(
            "color: %s; font-size: 12px; background: transparent;" % theme.TEXT_MUTED)
        return label

    # ---------- 动作 ----------

    def _set_status(self, text, tone="muted"):
        colors = {"ok": theme.SUCCESS, "warn": theme.WARNING,
                  "bad": theme.DANGER, "muted": theme.TEXT_MUTED}
        self.status.setText(text)
        self.status.setStyleSheet(
            "color: %s; font-size: 12px; background: transparent;"
            % colors.get(tone, theme.TEXT_MUTED))

    def _parse(self):
        """解析 + 校验，返回 (points, problems)。"""
        points, problems = brightness_map.parse_points(
            self.input_edit.toPlainText())
        if problems:
            return points, problems
        return points, brightness_map.validate_points(points)

    def on_check(self):
        """只校验，不生成（输出区显示结论）。"""
        points, problems = self._parse()
        if problems:
            self.output_edit.setPlainText(
                "发现 {} 处问题：\n{}".format(
                    len(problems), "\n".join("- " + p for p in problems)))
            self._set_status("有 {} 处问题，先修好再生成".format(len(problems)),
                             "bad")
            return False, points, problems
        self.output_edit.setPlainText(
            "校验通过。\n{}\n{}".format(
                brightness_map.summary(points),
                self._transition_note(points)))
        self._set_status("校验通过", "ok")
        return True, points, problems

    def on_build(self):
        """校验通过后生成 XML。"""
        ok, points, problems = self.on_check()
        if not ok:
            return None
        xml = brightness_map.to_xml(points)
        self.output_edit.setPlainText(
            "{}\n\n{}".format(xml, self._transition_note(points)))
        self._set_status("已生成 XML（{} 个点）".format(len(points)), "ok")
        return xml

    def on_copy(self):
        """复制输出区（优先复制纯 XML 部分）。"""
        text = self.output_edit.toPlainText()
        if not text.strip():
            self._set_status("先点「生成 XML」", "warn")
            return ""
        QApplication.clipboard().setText(text)
        self._set_status("已复制到剪贴板", "ok")
        return text

    @staticmethod
    def _transition_note(points):
        tp = brightness_map.transition_point(points)
        if tp is None:
            return "没有非 HBM 点，算不出 transitionPoint（至少要留一段 HBM off 区间）"
        return ("transitionPoint = {:.6f}（节点 {}）——写到外层 "
                "<highBrightnessMode> 上，不要内嵌进 screenBrightnessMap".format(
                    tp, brightness_map.value_to_dbv(tp)))
