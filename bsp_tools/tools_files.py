"""常用工具 · 文件管理

浏览设备目录、上传/下载文件、管理常用路径书签。
"""

import os
import posixpath

from PyQt5.QtCore import Qt, QProcess, QSize
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QListWidgetItem, QLineEdit, QComboBox, QLabel,
                             QFileDialog, QMessageBox, QMenu, QInputDialog,
                             QApplication)

import app_data
import theme
import toolchain
import ui_widgets as W


BOOKMARK_DEFAULTS = [
    "/sdcard/",
    "/sdcard/DCIM/",
    "/sdcard/Pictures/",
    "/sdcard/Download/",
    "/data/local/tmp/",
    "/data/ylog/",
    "/d/",
]


def bookmarks_path():
    """兼容旧名字：书签现在存在本机唯一的数据文件 DisplayTools.json 里。"""
    return app_data.data_path()


class FileManagerSection(QWidget):
    """设备文件管理。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path = "/sdcard/"
        self.entries = []
        self.bookmarks = []
        self._process = None
        self._processes = []          # 上传/下载/删除用的临时进程
        self._build_ui()
        self.load_bookmarks()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---- 路径栏 ----
        bar = W.Card("设备路径")
        row = bar.add_row()

        self.up_btn = W.soft_button("上级", "arrow_left", bar)
        self.up_btn.clicked.connect(self.go_up)
        row.addWidget(self.up_btn)

        self.path_edit = QLineEdit(bar)
        self.path_edit.setPlaceholderText("/sdcard/")
        self.path_edit.returnPressed.connect(self.navigate_to_edit)
        row.addWidget(self.path_edit, 1)

        self.bookmark_combo = QComboBox(bar)
        self.bookmark_combo.setMinimumWidth(160)
        self.bookmark_combo.activated.connect(self.on_bookmark_chosen)
        row.addWidget(self.bookmark_combo)

        self.add_bookmark_btn = W.soft_button("+ 书签", None, bar)
        self.add_bookmark_btn.clicked.connect(self.add_bookmark)
        row.addWidget(self.add_bookmark_btn)

        self.refresh_btn = W.accent_button("刷新", "refresh", bar)
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)

        layout.addWidget(bar)

        # ---- 文件列表 ----
        list_card = W.Card("目录内容")
        self.status_label = QLabel("", list_card)
        self.status_label.setStyleSheet(
            f"color: {theme.TEXT_FAINT}; font-size: 12px; background: transparent;")
        list_card.add_trailing(self.status_label)

        self.filter_edit = QLineEdit(list_card)
        self.filter_edit.setPlaceholderText("过滤文件名…")
        self.filter_edit.textChanged.connect(lambda _t: self.render_entries())
        list_card.add(self.filter_edit)

        self.list_widget = QListWidget(list_card)
        self.list_widget.setIconSize(QSize(16, 16))
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(self.on_item_activated)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        list_card.add(self.list_widget, 1)
        layout.addWidget(list_card, 1)

        # ---- 操作栏 ----
        actions = W.Card("文件操作")
        action_row = actions.add_row()

        self.upload_btn = W.accent_button("上传文件", "upload", actions)
        self.upload_btn.clicked.connect(self.upload_file)
        action_row.addWidget(self.upload_btn)

        self.download_btn = W.soft_button("下载选中", "download", actions)
        self.download_btn.clicked.connect(self.download_selected)
        action_row.addWidget(self.download_btn)

        self.copy_path_btn = W.soft_button("复制路径", "file", actions)
        self.copy_path_btn.clicked.connect(self.copy_selected_path)
        action_row.addWidget(self.copy_path_btn)

        self.delete_btn = W.danger_button("删除选中", "trash", actions)
        self.delete_btn.clicked.connect(self.delete_selected)
        action_row.addWidget(self.delete_btn)

        action_row.addStretch()
        actions.add(W.heading(
            "双击目录进入；右键条目可执行下载 / 删除；上传目标为当前目录。", actions))
        layout.addWidget(actions)

    # ================= 书签 =================

    def load_bookmarks(self):
        """从本机数据文件读书签；文件里没有这一段就用内置默认路径。"""
        section = app_data.data().get_section(app_data.SECTION_BOOKMARKS, None)
        if section is None:
            self.bookmarks = list(BOOKMARK_DEFAULTS)
        elif isinstance(section, list):
            # 空数组就是空（用户全删了，别把默认塞回来）
            self.bookmarks = [str(p) for p in section]
        else:
            self.bookmarks = list(BOOKMARK_DEFAULTS)
        self._refresh_bookmark_combo()

    def save_bookmarks(self):
        """写回数据文件；失败返回 False，由调用方提示。"""
        return app_data.data().set_section(app_data.SECTION_BOOKMARKS, self.bookmarks)

    def _refresh_bookmark_combo(self):
        self.bookmark_combo.blockSignals(True)
        self.bookmark_combo.clear()
        self.bookmark_combo.addItem("常用路径…")
        for path in self.bookmarks:
            self.bookmark_combo.addItem(path)
        self.bookmark_combo.setCurrentIndex(0)
        self.bookmark_combo.blockSignals(False)

    def on_bookmark_chosen(self, index):
        if index <= 0:
            return
        self.navigate_to(self.bookmarks[index - 1])

    def add_bookmark(self):
        path = self.path_edit.text().strip() or self.current_path
        if not path:
            return
        if not path.endswith('/'):
            path += '/'
        if path in self.bookmarks:
            return
        self.bookmarks.append(path)
        self.save_bookmarks()
        self._refresh_bookmark_combo()

    # ================= 导航 =================

    def navigate_to_edit(self):
        self.navigate_to(self.path_edit.text().strip())

    def navigate_to(self, path):
        if not path:
            return
        if not path.endswith('/'):
            path += '/'
        self.current_path = path
        self.path_edit.setText(path)
        self.refresh()

    def go_up(self):
        parent = posixpath.dirname(self.current_path.rstrip('/'))
        if not parent:
            parent = '/'
        self.navigate_to(parent or '/')

    def refresh(self):
        self.status_label.setText("读取中…")
        self.entries = []
        self.list_widget.clear()

        self._process = QProcess(self)
        program, args = toolchain.adb_program_args(
            ["shell", "ls", "-la", self.current_path])
        self._process.setProgram(program)
        self._process.setArguments(args)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.finished.connect(self._on_listing_done)
        self._process.errorOccurred.connect(
            lambda _e: self.status_label.setText("adb 不可用"))
        self._process.start()

    def _on_listing_done(self, _code, _status):
        if self._process is None:
            return
        output = bytes(self._process.readAllStandardOutput()).decode(errors='replace')
        self.entries = self._parse_listing(output)
        self.render_entries()

    @staticmethod
    def _parse_listing(output):
        entries = []
        for line in output.splitlines():
            line = line.rstrip('\r')
            if not line.strip() or line.startswith('total '):
                continue
            if line.startswith('ls:') or 'No such file' in line or 'Permission denied' in line:
                entries.append({"error": line.strip()})
                continue
            parts = line.split(None, 7)
            if len(parts) < 8:
                continue
            perms, _links, _owner, _group, size, _d1, _d2, name = parts
            if name in ('.', '..'):
                continue
            if ' -> ' in name:            # 符号链接，去掉目标
                name = name.split(' -> ')[0]
            is_dir = perms.startswith('d')
            is_link = perms.startswith('l')
            try:
                size_int = int(size)
            except ValueError:
                size_int = 0
            entries.append({
                "name": name,
                "dir": is_dir,
                "link": is_link,
                "perms": perms,
                "size": size_int,
            })
        entries.sort(key=lambda e: (not e.get('dir', False), e.get('name', '').lower()))
        return entries

    def render_entries(self):
        keyword = self.filter_edit.text().strip().lower()
        self.list_widget.clear()
        shown = 0
        for entry in self.entries:
            if 'error' in entry:
                item = QListWidgetItem(theme.icon("info", theme.DANGER, 16, 1.6),
                                       entry['error'])
                self.list_widget.addItem(item)
                continue
            if keyword and keyword not in entry['name'].lower():
                continue
            icon_name = "folder" if entry['dir'] else "file"
            color = theme.PRIMARY if entry['dir'] else theme.TEXT_MUTED
            if entry['link']:
                icon_name, color = "arrow_right", theme.WARNING
            label = entry['name'] + ('/' if entry['dir'] else '')
            size_text = '' if entry['dir'] else f"    {self._human_size(entry['size'])}"
            item = QListWidgetItem(
                theme.icon(icon_name, color, 16, 1.6),
                f"{label}{size_text}    ·    {entry['perms']}")
            item.setData(Qt.UserRole, entry)
            item.setToolTip(f"{entry['name']}\n{entry['perms']}  {entry['size']} B")
            self.list_widget.addItem(item)
            shown += 1
        self.status_label.setText(f"{shown} 项 · {self.current_path}")

    @staticmethod
    def _human_size(size):
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"

    # ================= 条目操作 =================

    def _selected_entry(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        entry = item.data(Qt.UserRole)
        return entry if isinstance(entry, dict) and 'name' in entry else None

    def _selected_device_path(self):
        entry = self._selected_entry()
        if entry is None:
            return None
        return posixpath.join(self.current_path, entry['name'])

    def on_item_activated(self, item):
        entry = item.data(Qt.UserRole)
        if not isinstance(entry, dict) or 'name' not in entry:
            return
        if entry['dir']:
            self.navigate_to(posixpath.join(self.current_path, entry['name']))

    def show_context_menu(self, position):
        item = self.list_widget.itemAt(position)
        if item is None:
            return
        self.list_widget.setCurrentItem(item)
        menu = QMenu(self)
        download = menu.addAction(theme.icon("download", theme.TEXT, 16, 1.6), "下载到本地")
        copy_path = menu.addAction(theme.icon("file", theme.TEXT, 16, 1.6), "复制设备路径")
        menu.addSeparator()
        delete = menu.addAction(theme.icon("trash", theme.DANGER, 16, 1.6), "删除")
        chosen = menu.exec_(self.list_widget.mapToGlobal(position))
        if chosen == download:
            self.download_selected()
        elif chosen == copy_path:
            self.copy_selected_path()
        elif chosen == delete:
            self.delete_selected()

    def copy_selected_path(self):
        path = self._selected_device_path()
        if path:
            QApplication.clipboard().setText(path)

    def _run_adb(self, args, on_done=None, label=""):
        process = QProcess(self)
        program, full_args = toolchain.adb_program_args(args)
        process.setProgram(program)
        process.setArguments(full_args)
        process.setProcessChannelMode(QProcess.MergedChannels)
        self._processes.append(process)

        def finished(code, _status):
            output = bytes(process.readAllStandardOutput()).decode(errors='replace')
            if process in self._processes:
                self._processes.remove(process)
            process.deleteLater()
            if on_done is not None:
                on_done(code, output)

        process.finished.connect(finished)
        process.start()
        return process

    def upload_file(self):
        local, _ = QFileDialog.getOpenFileName(self, "选择要上传的文件", "", "所有文件 (*)")
        if not local:
            return
        window = self.window()
        if hasattr(window, 'toast'):
            window.toast(f"正在上传 {os.path.basename(local)} …", "info")

        def done(code, output):
            if hasattr(window, 'toast'):
                window.toast(
                    f"上传{'完成' if code == 0 else '失败'}：{os.path.basename(local)}",
                    "success" if code == 0 else "error")
            self.refresh()

        self._run_adb(["push", local, self.current_path], done)

    def download_selected(self):
        path = self._selected_device_path()
        if not path:
            return
        entry = self._selected_entry()
        if entry and entry['dir']:
            QMessageBox.information(self, "提示", "请选择文件而不是目录")
            return
        local_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not local_dir:
            return
        window = self.window()
        if hasattr(window, 'toast'):
            window.toast(f"正在下载 {entry['name']} …", "info")

        def done(code, _output):
            if hasattr(window, 'toast'):
                window.toast(
                    f"下载{'完成' if code == 0 else '失败'}：{entry['name']} → {local_dir}",
                    "success" if code == 0 else "error")

        self._run_adb(["pull", path, local_dir], done)

    def delete_selected(self):
        path = self._selected_device_path()
        entry = self._selected_entry()
        if not path or entry is None:
            return
        confirm = QMessageBox.question(
            self, "确认删除", f"确定从设备删除「{entry['name']}」？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        flag = "-rf" if entry['dir'] else "-f"

        def done(code, output):
            window = self.window()
            if hasattr(window, 'toast'):
                window.toast(
                    f"删除{'完成' if code == 0 else '失败'}：{entry['name']}",
                    "success" if code == 0 else "error")
            self.refresh()

        self._run_adb(["shell", "rm", flag, path], done)

    def on_page_shown(self):
        if not self.entries:
            self.refresh()

    def stop_background(self):
        """关闭前收掉所有 QProcess，否则 Qt 会报
        "QProcess: Destroyed while process is still running"。"""
        for process in [self._process] + list(self._processes):
            if process is None:
                continue
            try:
                if process.state() != QProcess.NotRunning:
                    process.kill()
                    process.waitForFinished(1500)
            except Exception:
                pass
        self._processes.clear()
