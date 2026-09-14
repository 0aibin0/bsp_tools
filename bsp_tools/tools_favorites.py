"""常用工具 · 命令收藏夹

把日常反复敲的 adb 命令存成可点击的快捷项，支持增删改、分组、搜索，
持久化到程序目录下的 favorites.json。
"""

import json
import os
import sys

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QListWidgetItem, QLineEdit, QComboBox, QLabel,
                             QMessageBox, QSplitter)

import theme
import ui_widgets as W


DEFAULT_FAVORITES = [
    {"group": "常用", "name": "列出设备", "command": "adb devices"},
    {"group": "常用", "name": "获取 root", "command": "adb root"},
    {"group": "常用", "name": "重新挂载", "command": "adb remount"},
    {"group": "常用", "name": "重启设备", "command": "adb reboot"},
    {"group": "常用", "name": "挂载 debugfs", "command": "adb shell mount -t debugfs none /d"},
    {"group": "调试", "name": "dmesg 内核日志", "command": "adb shell dmesg | tail -200"},
    {"group": "调试", "name": "logcat 错误", "command": "adb logcat -d *:E"},
    {"group": "调试", "name": "I2C 设备列表", "command": "adb shell ls /sys/bus/i2c/devices/"},
    {"group": "调试", "name": "GPIO 状态", "command": "adb shell cat /d/gpio"},
    {"group": "调试", "name": "printk 等级", "command": "adb shell cat /proc/sys/kernel/printk"},
    {"group": "显示", "name": "屏幕分辨率", "command": "adb shell wm size"},
    {"group": "显示", "name": "屏幕密度", "command": "adb shell wm density"},
    {"group": "显示", "name": "显示子系统", "command": "adb shell dumpsys display"},
    {"group": "显示", "name": "当前背光", "command": "adb shell settings get system screen_brightness"},
    {"group": "显示", "name": "DCS 回读", "command": "adb shell cat /sys/class/display/dsi0/dcs_read"},
    {"group": "系统", "name": "启动参数", "command": "adb shell cat /proc/cmdline"},
    {"group": "系统", "name": "CPU 温度", "command": "adb shell cat /sys/class/thermal/thermal_zone0/temp"},
    {"group": "系统", "name": "电池状态", "command": "adb shell dumpsys battery"},
    {"group": "系统", "name": "内存占用", "command": "adb shell cat /proc/meminfo | head -3"},
    {"group": "系统", "name": "系统属性", "command": "adb shell getprop | grep ro.product"},
]


def favorites_path():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'favorites.json')


class FavoritesSection(QWidget):
    """命令收藏夹。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.editing_index = None
        self._rendered = []
        self._build_ui()
        self.load()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_card())
        splitter.addWidget(self._build_editor_card())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([620, 420])
        layout.addWidget(splitter, 1)

    def _build_list_card(self):
        card = W.Card("已收藏命令")

        self.count_label = QLabel("", card)
        self.count_label.setStyleSheet(
            f"color: {theme.TEXT_FAINT}; font-size: 12px; background: transparent;")
        card.add_trailing(self.count_label)

        search_row = card.add_row()
        self.search_edit = QLineEdit(card)
        self.search_edit.setPlaceholderText("搜索名称或命令…")
        self.search_edit.textChanged.connect(lambda _t: self.render_list())
        search_row.addWidget(self.search_edit, 1)

        self.group_filter = QComboBox(card)
        self.group_filter.setMinimumWidth(110)
        self.group_filter.currentIndexChanged.connect(lambda _i: self.render_list())
        search_row.addWidget(self.group_filter)

        self.list_widget = QListWidget(card)
        self.list_widget.setIconSize(QSize(16, 16))
        self.list_widget.itemDoubleClicked.connect(lambda _i: self.run_selected())
        card.add(self.list_widget, 1)

        action_row = card.add_row()
        self.run_btn = W.accent_button("执行选中", "terminal", card)
        self.run_btn.clicked.connect(self.run_selected)
        action_row.addWidget(self.run_btn)

        edit_btn = W.soft_button("编辑", "code", card)
        edit_btn.clicked.connect(self.edit_selected)
        action_row.addWidget(edit_btn)

        delete_btn = W.danger_button("删除", "trash", card)
        delete_btn.clicked.connect(self.delete_selected)
        action_row.addWidget(delete_btn)

        action_row.addStretch()

        reset_btn = W.soft_button("恢复默认", "refresh", card)
        reset_btn.clicked.connect(self.reset_defaults)
        action_row.addWidget(reset_btn)

        return card

    def _build_editor_card(self):
        card = W.Card("新增 / 编辑")

        card.body.addWidget(W.field_label("名称", card))
        self.name_edit = QLineEdit(card)
        self.name_edit.setPlaceholderText("例如：查看背光")
        card.add(self.name_edit)

        card.body.addWidget(W.field_label("命令", card))
        self.command_edit = QLineEdit(card)
        self.command_edit.setPlaceholderText("例如：adb shell settings get system screen_brightness")
        self.command_edit.returnPressed.connect(self.save_entry)
        card.add(self.command_edit)

        card.body.addWidget(W.field_label("分组", card))
        self.group_combo = QComboBox(card)
        self.group_combo.setEditable(True)
        self.group_combo.addItems(["常用", "调试", "显示", "系统"])
        card.add(self.group_combo)

        card.body.addWidget(W.separator(card))

        row = card.add_row()
        self.save_btn = W.accent_button("保存", None, card)
        self.save_btn.clicked.connect(self.save_entry)
        row.addWidget(self.save_btn)

        self.cancel_btn = W.soft_button("取消编辑", None, card)
        self.cancel_btn.clicked.connect(self.clear_editor)
        row.addWidget(self.cancel_btn)
        row.addStretch()

        hint = W.heading(
            "提示：双击左侧条目可直接执行；命令会连同输出显示在 Shell Tools 的日志区。", card)
        hint.setWordWrap(True)
        card.add(hint)
        card.body.addStretch()

        return card

    # ================= 数据 =================

    def load(self):
        path = favorites_path()
        data = None
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = None
        if not isinstance(data, list) or not data:
            data = list(DEFAULT_FAVORITES)
        self.items = [d for d in data if isinstance(d, dict) and d.get('command')]
        self._refresh_groups()
        self.render_list()

    def save(self):
        try:
            with open(favorites_path(), 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _refresh_groups(self):
        current = self.group_filter.currentText()
        groups = []
        for item in self.items:
            group = item.get('group', '常用')
            if group not in groups:
                groups.append(group)
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("全部分组")
        for group in sorted(groups):
            self.group_filter.addItem(group)
        index = self.group_filter.findText(current)
        self.group_filter.setCurrentIndex(index if index >= 0 else 0)
        self.group_filter.blockSignals(False)

    def render_list(self):
        keyword = self.search_edit.text().strip().lower()
        group = self.group_filter.currentText()

        self.list_widget.clear()
        self._rendered = []
        for index, item in enumerate(self.items):
            if group and group != "全部分组" and item.get('group') != group:
                continue
            if keyword and keyword not in item['name'].lower() \
                    and keyword not in item['command'].lower():
                continue
            entry = QListWidgetItem(
                theme.icon("star", theme.PRIMARY, 16, 1.6),
                f"{item['name']}\n{item['command']}")
            entry.setData(Qt.UserRole, index)
            entry.setToolTip(item['command'])
            self.list_widget.addItem(entry)
            self._rendered.append(index)
        self.count_label.setText(f"{self.list_widget.count()} 条")

    def _selected_index(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._rendered):
            return None
        return self._rendered[row]

    # ================= 操作 =================

    def run_selected(self):
        """执行选中的命令。

        输出落到本页底部的共享结果面板，不再跳转到 Shell Tools 页
        （原来会 nav.select('shell')，用户点一下就离开当前页，体验被打断）。
        """
        index = self._selected_index()
        if index is None:
            return
        item = self.items[index]
        runner = getattr(self, "runner", None)
        if runner is None:
            return
        runner.run(item['command'], item['name'])

    def edit_selected(self):
        index = self._selected_index()
        if index is None:
            return
        item = self.items[index]
        self.editing_index = index
        self.name_edit.setText(item['name'])
        self.command_edit.setText(item['command'])
        self.group_combo.setCurrentText(item.get('group', '常用'))
        self.save_btn.setText("更新")
        self.name_edit.setFocus()

    def delete_selected(self):
        index = self._selected_index()
        if index is None:
            return
        item = self.items[index]
        confirm = QMessageBox.question(
            self, "确认删除", f"确定删除「{item['name']}」？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.items.pop(index)
        self.save()
        self._refresh_groups()
        self.render_list()
        self.clear_editor()

    def save_entry(self):
        name = self.name_edit.text().strip()
        command = self.command_edit.text().strip()
        group = self.group_combo.currentText().strip() or "常用"
        if not name or not command:
            QMessageBox.warning(self, "信息不完整", "名称和命令都不能为空")
            return

        if self.editing_index is not None and 0 <= self.editing_index < len(self.items):
            self.items[self.editing_index] = {
                "group": group, "name": name, "command": command}
        else:
            self.items.append({"group": group, "name": name, "command": command})

        self.save()
        self._refresh_groups()
        self.render_list()
        self.clear_editor()
        window = self.window()
        if hasattr(window, 'toast'):
            window.toast(f"已保存命令「{name}」", "success")

    def clear_editor(self):
        self.editing_index = None
        self.name_edit.clear()
        self.command_edit.clear()
        self.save_btn.setText("保存")

    def reset_defaults(self):
        confirm = QMessageBox.question(
            self, "恢复默认", "将丢弃当前收藏并恢复内置命令，确定继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.items = [dict(d) for d in DEFAULT_FAVORITES]
        self.save()
        self._refresh_groups()
        self.render_list()
        self.clear_editor()
