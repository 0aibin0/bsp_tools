"""设置对话框。

目前主要是「工具链路径」：exe 发给没装 platform-tools 的同事时，这个是能不能
用的分界线——原来全项目写死裸 `adb`，靠 PATH 找，找不到就报 Windows 的
`'adb' is not recognized`，很难自查。
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QLineEdit, QPushButton, QFileDialog,
                             QDialogButtonBox, QFrame, QComboBox)

import app_config
import theme
import toolchain
import ui_widgets as W

THEME_CHOICES = [
    ("system", "跟随系统"),
    ("light", "浅色"),
    ("dark", "深色"),
]


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(620)
        self.setStyleSheet(theme.build_stylesheet())
        self._config = app_config.config()
        self._build()
        self._refresh_status()

    # ---------- 界面 ----------

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        layout.addWidget(W.heading("工具链路径"))
        tip = QLabel(
            "没装 platform-tools 的机器上，这里指定目录（例如 "
            r"D:\01_tools\platform-tools）或 adb.exe 全路径；留空则使用 PATH。",
            self)
        tip.setObjectName("pageSubtitle")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        self.dir_edit = QLineEdit(self._config.get("toolchain_dir", ""), self)
        self.dir_edit.setPlaceholderText("platform-tools 目录（留空 = 用 PATH 里的 adb）")
        self.dir_edit.setMinimumHeight(30)
        self.dir_edit.textChanged.connect(self._refresh_status)
        grid.addWidget(W.field_label("platform-tools", self), 0, 0)
        grid.addWidget(self.dir_edit, 0, 1)

        pick = QPushButton("浏览…", self)
        pick.setMinimumHeight(30)
        pick.clicked.connect(self._pick_dir)
        grid.addWidget(pick, 0, 2)

        detect = QPushButton("自动检测", self)
        detect.setMinimumHeight(30)
        detect.setToolTip("在常见安装位置与 PATH 里找 platform-tools")
        detect.clicked.connect(self._detect)
        grid.addWidget(detect, 0, 3)
        layout.addLayout(grid)

        self.status_box = QFrame(self)
        self.status_box.setObjectName("card")
        status_layout = QVBoxLayout(self.status_box)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(4)
        self.adb_label = QLabel("", self.status_box)
        self.fastboot_label = QLabel("", self.status_box)
        for label in (self.adb_label, self.fastboot_label):
            label.setWordWrap(True)
            label.setProperty("hint", True)
            status_layout.addWidget(label)
        layout.addWidget(self.status_box)

        layout.addWidget(W.separator(self))

        layout.addWidget(W.heading("界面"))
        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        theme_row.addWidget(W.field_label("主题", self))
        self.theme_combo = QComboBox(self)
        self.theme_combo.setMinimumHeight(30)
        self.theme_combo.setMinimumWidth(160)
        for key, label in THEME_CHOICES:
            self.theme_combo.addItem(label, key)
        current = self._config.get("theme", "system")
        index = max(0, [k for k, _ in THEME_CHOICES].index(current)
                    if current in [k for k, _ in THEME_CHOICES] else 0)
        self.theme_combo.setCurrentIndex(index)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        note = QLabel("重启后生效（图标与样式在启动时绘制）", self)
        note.setProperty("hint", True)
        theme_row.addWidget(note)
        layout.addLayout(theme_row)

        layout.addWidget(W.separator(self))

        path_label = QLabel("配置目录：{}".format(app_config.data_dir()), self)
        path_label.setObjectName("pageSubtitle")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------- 交互 ----------

    def _pick_dir(self):
        start = self.dir_edit.text().strip() or app_config.data_dir()
        folder = QFileDialog.getExistingDirectory(self, "选择 platform-tools 目录", start)
        if folder:
            self.dir_edit.setText(os.path.normpath(folder))

    def _detect(self):
        folder = toolchain.detect_platform_tools()
        if folder:
            self.dir_edit.setText(os.path.normpath(folder))
        else:
            self.dir_edit.setText("")
            self.status_box.setToolTip("没找到 platform-tools，请手动指定目录")

    def _refresh_status(self):
        """按当前输入实时试算，避免"保存了才发现路径写错"。"""
        pending = self.dir_edit.text().strip()
        saved = self._config.get("toolchain_dir", "")
        self._config.set("toolchain_dir", pending)
        try:
            for name, label in (("adb", self.adb_label), ("fastboot", self.fastboot_label)):
                ok = toolchain.available(name)
                label.setText("{} {}".format("✓" if ok else "✗", toolchain.describe(name)))
                label.setProperty("tone", "ok" if ok else "bad")
                label.style().unpolish(label)
                label.style().polish(label)
        finally:
            # 只在对话框里试算，不写盘；点了保存才生效
            self._config.set("toolchain_dir", saved)

    # ---------- 结果 ----------

    def values(self):
        return {
            "toolchain_dir": self.dir_edit.text().strip(),
            "theme": self.theme_combo.currentData(),
        }

    def accept(self):
        self._config.update(**self.values())
        super().accept()
