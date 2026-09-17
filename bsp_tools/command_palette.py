"""命令面板（Ctrl+K）。

面板和「常用工具 · 命令收藏」共用同一份数据（command_store → 本机唯一的
数据文件 `DisplayTools.json` 的 commands 段）：

- 搜索框里敲的关键字同时匹配名称和命令，收藏页里加的命令这里马上搜得到；
- 列表选中一条回车/双击 → 在 Shell Tools 页执行；
- 输入框里现敲/粘贴的命令也能直接执行（列表最后会多一条「直接执行：…」）；
- 「存为收藏」把当前命令写进 DisplayTools.json，命令收藏页立刻能看到。

对话框只负责「选命令 / 存命令」，执行和跳转由外部信号处理，
这样 selftest 能不弹模态窗口就把逻辑跑一遍。
"""

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QListWidget, QListWidgetItem, QLabel, QInputDialog)

import theme
import ui_widgets as W


def default_label(command):
    """列表里显示用的短标签，太长就截断——命令本身在 tooltip 里。"""
    return command if len(command) <= 40 else command[:37] + "…"


class CommandPaletteDialog(QDialog):
    """命令面板。"""

    #: 用户选中了一条命令要执行：(command, label)
    commandChosen = pyqtSignal(str, str)
    #: 用户点了「管理收藏」
    manageRequested = pyqtSignal()
    #: 新命令已存进收藏：(name, 是否新增)
    commandSaved = pyqtSignal(str, bool)

    def __init__(self, store, parent=None, ask=None):
        """ask: 可选的提问回调 (title, label, default) -> (text, ok)。

        默认弹 QInputDialog；测试时注入一个假回调就不会卡在模态框上。
        """
        super(CommandPaletteDialog, self).__init__(parent)
        self.store = store
        self._ask = ask or self._ask_with_dialog
        self.setWindowTitle("命令面板")
        self.setMinimumSize(620, 460)
        self.setStyleSheet(theme.build_stylesheet())
        self._build_ui()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hint = QLabel("输入关键字过滤，回车在 Shell Tools 执行；「存为收藏」写进命令"
                      "收藏（与命令收藏页同一份文件）", self)
        hint.setObjectName("pageSubtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("搜索命令…（例如 root / gpio / 温度），也可直接粘贴一条命令")
        self.search.setMinimumHeight(34)
        layout.addWidget(self.search)

        self.listing = QListWidget(self)
        self.listing.setIconSize(QSize(16, 16))
        layout.addWidget(self.listing, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.run_btn = W.accent_button("执行", "terminal", self)
        self.run_btn.clicked.connect(self.run_current)
        buttons.addWidget(self.run_btn)

        self.save_btn = W.soft_button("存为收藏", "star", self)
        self.save_btn.setToolTip("写进命令收藏（DisplayTools.json 的 commands 段），命令收藏页里马上能看到")
        self.save_btn.clicked.connect(self.save_current)
        buttons.addWidget(self.save_btn)

        manage_btn = W.soft_button("管理收藏", "settings", self)
        manage_btn.setToolTip("打开「常用工具 · 命令收藏」页，批量增删改")
        manage_btn.clicked.connect(self._on_manage)
        buttons.addWidget(manage_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.run_current)
        self.listing.itemActivated.connect(lambda _i: self.run_current())

    # ================= 数据 → 列表 =================

    def filter(self, keyword=""):
        """按关键字刷新列表；关键字本身也能当命令执行（列表最后那条）。"""
        self.listing.clear()
        for _index, item in self.store.search(keyword):
            entry = QListWidgetItem(
                theme.icon("terminal", theme.PRIMARY, 16, 1.6),
                f"{item['name']}    ·    {item['command']}")
            entry.setData(Qt.UserRole, item['command'])
            entry.setToolTip(f"{item['group']} · {item['command']}")
            self.listing.addItem(entry)

        typed = (keyword or "").strip()
        if typed:
            entry = QListWidgetItem(
                theme.icon("arrow_right", theme.TEXT_MUTED, 16, 1.6),
                f"直接执行：{typed}")
            entry.setData(Qt.UserRole, typed)
            entry.setToolTip("执行输入框里的这条命令（不写入收藏）")
            self.listing.addItem(entry)

        if self.listing.count():
            self.listing.setCurrentRow(0)
        return self.listing.count()

    def current_command(self):
        item = self.listing.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.UserRole) or "")

    # ================= 动作 =================

    def run_current(self):
        command = self.current_command().strip()
        if not command:
            return ""
        self.accept()
        self.commandChosen.emit(command, default_label(command))
        return command

    def save_current(self):
        """把当前命令写进收藏；返回 (是否新增, 名称)。"""
        command = self.current_command().strip() or self.search.text().strip()
        if not command:
            return False, ""
        default_name = command if len(command) <= 24 else command[:21] + "…"
        name, ok = self._ask("存为收藏", f"给这条命令起个名字：\n{command}", default_name)
        if not ok or not name.strip():
            return False, ""
        group, group_ok = self._ask("存为收藏", "放到哪个分组？（常用 / 调试 / 显示 / 系统）",
                                    "常用")
        if not group_ok:
            return False, ""
        name = name.strip()
        added, _index = self.store.add(name, command, group or "常用")
        self.commandSaved.emit(name, added)
        self.filter(self.search.text())
        self.search.setFocus()
        return added, name

    def _on_manage(self):
        self.accept()
        self.manageRequested.emit()

    @staticmethod
    def _ask_with_dialog(title, label, default):
        text, ok = QInputDialog.getText(None, title, label, QLineEdit.Normal, default)
        return text, ok
