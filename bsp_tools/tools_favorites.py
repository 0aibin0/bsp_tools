"""常用工具 · 命令收藏夹

把日常反复敲的 adb 命令存成可点击的快捷项，支持增删改、分组、搜索。

数据源是 command_store：命令存在本机唯一的数据文件 `DisplayTools.json` 里
（和设置、路径书签同一个文件），Ctrl+K 命令面板读的也是这一份。增删改**立即
落盘**——删一条文件里就少一条，加一条就多一条，重启不会变回去；写盘失败会
弹提示，不会默默当成功。
"""

import os

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QListWidgetItem, QLineEdit, QComboBox, QLabel,
                             QMessageBox, QSplitter)

import theme
import ui_widgets as W
from command_store import store as store_singleton


class FavoritesSection(QWidget):
    """命令收藏夹。"""

    def __init__(self, parent=None, store=None):
        """store 可注入（测试用）；默认拿进程单例，和命令面板是同一份。"""
        super().__init__(parent)
        self.store = store or store_singleton()
        self.editing_index = None
        self._rendered = []
        self._build_ui()
        self.reload()

    @property
    def items(self):
        """直接指向共享 store 的清单，页面与命令面板永远是同一份。"""
        return self.store.items

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
            "提示：双击左侧条目直接执行，输出落在右侧「执行结果」面板；增删改会立即"
            "写进 {}（Ctrl+K 命令面板共用同一份）。".format(
                os.path.basename(self.store.path)), card)
        hint.setWordWrap(True)
        card.add(hint)
        card.body.addStretch()

        return card

    # ================= 数据 =================

    def reload(self):
        """从共享 store 重新读一遍（命令面板里新增/删除后也要调）。"""
        self.store.load()
        self._refresh_groups()
        self.render_list()

    def notify_changed(self):
        """把改动同步给命令面板（同一进程共享 store，这里只是让面板下次打开刷新）。"""
        window = self.window()
        hook = getattr(window, "on_commands_changed", None)
        if callable(hook):
            hook()

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
        """按搜索框 + 分组过滤渲染。过滤逻辑统一走 store.search，避免两处不一致。"""
        self.list_widget.clear()
        self._rendered = []
        for index, item in self.store.search(
                self.search_edit.text(), self.group_filter.currentText()):
            entry = QListWidgetItem(
                theme.icon("star", theme.PRIMARY, 16, 1.6),
                f"{item['name']}\n{item['command']}")
            entry.setData(Qt.UserRole, index)
            entry.setToolTip(f"{item['group']} · {item['command']}")
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
            self, "确认删除", f"确定删除「{item['name']}」？\n\n删掉后会立即从本地"
            f"数据文件里移除（重启不会回来）。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        saved = self.store.remove(index)
        self._refresh_groups()
        self.render_list()
        self.clear_editor()
        self.notify_changed()
        self._report_saved(saved, f"已删除「{item['name']}」")

    def save_entry(self):
        name = self.name_edit.text().strip()
        command = self.command_edit.text().strip()
        group = self.group_combo.currentText().strip() or "常用"
        if not name or not command:
            QMessageBox.warning(self, "信息不完整", "名称和命令都不能为空")
            return

        existing = self.store.find_by_command(command)
        if self.editing_index is not None and 0 <= self.editing_index < len(self.items):
            saved = self.store.update(self.editing_index, name, command, group)
            message = f"已更新命令「{name}」"
        elif existing is not None:
            # 同一条命令不在收藏里放两遍，直接改成新名字
            saved = self.store.update(existing, name, command, group)
            message = f"已更新命令「{name}」"
        else:
            _added, index = self.store.add(name, command, group)
            saved = index is not None
            message = f"已保存命令「{name}」"

        self._refresh_groups()
        self.render_list()
        self.clear_editor()
        self.notify_changed()
        self._report_saved(saved, message)

    def _report_saved(self, saved, message):
        """统一提示写入结果：写失败必须说出来，不能默默当成功。"""
        window = self.window()
        if saved is False:
            detail = "写不进 {}".format(self.store.path)
            if hasattr(window, 'toast'):
                window.toast(f"保存失败：{detail}", "error", 6000)
            else:
                QMessageBox.warning(self, "保存失败",
                                    f"{message}，但写文件失败：\n{detail}")
            return
        if hasattr(window, 'toast'):
            window.toast(message, "success")

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
        saved = self.store.reset()
        self._refresh_groups()
        self.render_list()
        self.clear_editor()
        self.notify_changed()
        self._report_saved(saved, "已恢复内置命令")
