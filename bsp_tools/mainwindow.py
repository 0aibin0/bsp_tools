"""DisplayTools 主窗口。

v3.1.0 起改为「左侧边栏导航 + 右侧卡片内容区」的现代桌面工具布局：
- 侧边栏切换页面（替代原顶部 Tab）
- 顶部标题栏显示当前页面说明 + 全局操作
- 状态栏显示设备状态、时钟
- Ctrl+K 打开命令面板，快速执行常用命令
"""

import os
import sys

from PyQt5.QtCore import (Qt, QTimer, QDateTime, QPropertyAnimation, QEasingCurve,
                          QRect, QUrl)
from PyQt5.QtGui import QIcon, QKeySequence, QDesktopServices
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel,
                             QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QStackedWidget, QFrame, QShortcut, QSizePolicy,
                             QComboBox)

import app_config
import app_runtime
import command_palette
import command_store
import info_dialog
import theme
import toolchain
import ui_widgets
import update_check
from sidebar import Sidebar

from initcode_builder import InitcodeBuilderPage
from lk_to_kernel import LkToKernelPage
from kernel_to_lk import KernelToLkPage
from lk_to_bat import LkToBatPage
from shell_tools import ShellToolsPage
from tools_page import CommonToolsPage


# 页面注册表：key -> (标题, 副标题, 构造类, 侧边栏分组, 图标)
PAGE_DEFS = [
    ("tools", "常用工具", "日志 · 设备 · 显示 · 现场包 · 触摸 · 系统 · 性能 · 文件 · 收藏",
     CommonToolsPage, "常用", "grid"),
    ("shell", "Shell Tools", "adb / fastboot 设备控制与调试",
     ShellToolsPage, "调试工具", "terminal"),
    ("initcode", "Initcode Builder", "把寄存器读写描述转换成 initcode",
     InitcodeBuilderPage, "转换工具", "code"),
    ("lk2kernel", "LK → Kernel", "LK 十六进制序列转内核格式",
     LkToKernelPage, "转换工具", "arrow_right"),
    ("kernel2lk", "Kernel → LK", "内核十六进制序列转 LK 格式",
     KernelToLkPage, "转换工具", "arrow_left"),
    ("lk2bat", "LK → BAT", "生成 DCS 写入批处理脚本",
     LkToBatPage, "转换工具", "bat"),
]

# 命令面板的可选命令清单已并入 command_store（与「常用工具 · 命令收藏」
# 共用 DisplayTools.json 的 commands 段）：面板里能搜、能新增、能改。


def resource_path(*parts):
    """兼容 PyInstaller 打包后的资源路径。"""
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


class Toast(QLabel):
    """右下角浮层提示。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.hide()
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, text, kind="info", duration=2200):
        palette = {
            "info": (theme.SURFACE, theme.TEXT, theme.BORDER_STRONG),
            "success": (theme.SUCCESS_SOFT, "#0b7a3d", "#bfe6cd"),
            "warning": (theme.WARNING_SOFT, "#8a5a10", "#f0dcb4"),
            "error": (theme.DANGER_SOFT, "#b3383c", "#f3c5c6"),
        }[kind if kind in ("info", "success", "warning", "error") else "info"]
        bg, fg, border = palette
        self.setStyleSheet(
            f"QLabel#toast {{ background: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: 10px;"
            f" padding: 10px 16px; font-size: 13px; }}")
        self.setText(text)
        self.adjustSize()
        width = min(max(self.width() + 8, 200), max(self.parent().width() - 40, 200))
        height = self.height()
        self.setFixedSize(width, height)
        self._reposition()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(QRect(self.x(), self.y() + 14, width, height))
        self._anim.setEndValue(QRect(self.x(), self.y(), width, height))
        self._anim.start()
        self._hide_timer.start(duration)

    def _reposition(self):
        parent = self.parent()
        if parent is None:
            return
        x = parent.width() - self.width() - 22
        y = parent.height() - self.height() - 60
        self.move(max(x, 10), max(y, 10))


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setWindowTitle(f"{theme.APP_NAME} {theme.APP_VERSION}")
        icon_path = resource_path('icon_img', 'classification.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(1360, 880)

        self.pages = {}
        self._toast = None

        self._build_ui()
        self._build_shortcuts()
        self._start_clock()

        # 最小尺寸跟随内容：Shell Tools 的三列网格在更小的窗口里会互相
        # 重叠，所以这里量一遍所有页面的真实最小需求。
        # 注意：QStackedWidget.minimumSizeHint() 只算当前页，必须临时切到
        # 每个页面量一遍，否则会漏掉 Shell Tools 的高度需求。
        current = self.stack.currentWidget()
        max_w = max_h = 0
        for page in self.pages.values():
            self.stack.setCurrentWidget(page)
            self.stack.adjustSize()
            hint = page.minimumSizeHint()
            max_w = max(max_w, hint.width())
            max_h = max(max_h, hint.height())
        self.stack.setCurrentWidget(current)

        # 默认 1360x840：执行结果面板固定 240px + 内容区最宽模块 600px
        # 需要这个宽度，再窄内容区会出现横向滚动条（最小 1300 是底线）。
        self.content_min_width = max_w + theme.SIDEBAR_WIDTH + 20
        self.content_min_height = max_h + 96
        self.setMinimumSize(1300, 700)
        self._restore_geometry()

        self.nav.select(self._restore_page(), emit=True)
        QTimer.singleShot(300, self.refresh_device_status)
        QTimer.singleShot(400, self._startup_selfcheck)
        QTimer.singleShot(1200, self._notify_last_crash)

    # ================= 配置读写 =================

    def _restore_geometry(self):
        """恢复上次窗口位置与大小；没有记录或超出屏幕就退回默认尺寸。"""
        config = app_config.config()
        width = config.get_int("window_width", 0)
        height = config.get_int("window_height", 0)
        if width >= 1300 and height >= 700:
            screen = QApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                # 拔掉外接屏后原来的坐标可能落在屏幕外，那就只恢复尺寸不恢复位置
                if not available.intersects(QRect(
                        config.get_int("window_x", 0), config.get_int("window_y", 0),
                        width, height)):
                    self.resize(width, height)
                    return
            self.resize(width, height)
            x = config.get_int("window_x", -1)
            y = config.get_int("window_y", -1)
            if x >= 0 and y >= 0:
                self.move(x, y)
            return

        self.resize(min(max(1360, self.content_min_width), 1700),
                    min(max(840, self.content_min_height), 1000))

    def _restore_page(self):
        key = app_config.config().get("last_page", "tools")
        return key if key in self.pages else "tools"

    def _save_geometry(self):
        config = app_config.config()
        normal = self.normalGeometry()
        config.update(
            window_width=normal.width(),
            window_height=normal.height(),
            window_x=normal.x(),
            window_y=normal.y(),
            last_page=self._current_page_key(),
            toolchain_dir=config.get("toolchain_dir", ""),
        )

    def _current_page_key(self):
        current = self.stack.currentWidget()
        for key, page in self.pages.items():
            if page is current:
                return key
        return "tools"

    # ================= 启动自检 =================

    def _startup_selfcheck(self):
        """adb 找不到就得马上说，否则用户点任何按钮都只看到一句系统报错。"""
        missing = [name for name, ok in toolchain.detect_report().items() if not ok]
        if not missing:
            return
        names = " / ".join(missing)
        self.toolchainLabel.setText("⚠ 未找到 {}".format(names))
        self.toolchainLabel.setToolTip(
            "{}。点击这里指定 platform-tools 目录。".format(
                "\n".join(toolchain.describe(n) for n in missing)))
        self.toolchainLabel.setProperty("tone", "bad")
        self.toolchainLabel.style().unpolish(self.toolchainLabel)
        self.toolchainLabel.style().polish(self.toolchainLabel)
        self.toolchainLabel.show()
        self.toast("未找到 {}，点状态栏提示可设置路径".format(names), "error", 4200)

    def _notify_last_crash(self):
        """上次运行崩过就提示一次，并把 crash.log 归档。"""
        notice = app_runtime.take_crash_notice()
        if not notice:
            return
        self.toast("上次运行异常退出，详情见 crash.log", "warning", 3600)
        self.crash_notice = notice

    def show_toolchain_help(self):
        self.show_settings()

    def show_settings(self):
        from settings_dialog import SettingsDialog

        before = app_config.config().get("toolchain_dir", "")
        dialog = SettingsDialog(self)
        if dialog.exec_() != dialog.Accepted:
            return
        after = app_config.config().get("toolchain_dir", "")
        if after != before:
            ok = toolchain.available("adb")
            self.toolchainLabel.setVisible(not ok)
            if ok:
                self.toast("adb 已找到：{}".format(toolchain.adb()), "success", 3200)
            else:
                self.toast("这个路径下没找到 adb，请再确认", "error", 3200)
        else:
            self.toast("设置已保存", "success", 1800)

    def show_crash_log(self):
        path = app_config.crash_log_path()
        if not os.path.isfile(path):
            self._info_box("崩溃日志", "没有崩溃记录。")
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()[-2000:]
        except Exception as exc:                           # noqa: BLE001
            content = "读取失败：{}".format(exc)
        self._info_box("崩溃日志", "文件位置：{}\n\n{}".format(path, content))

    def refresh_device_status(self):
        """后台查询 adb 设备连接状态，避免阻塞界面启动。"""
        shell_page = self.pages.get("shell")
        if shell_page is None or getattr(shell_page, "_busy", False):
            return
        try:
            ok, desc = shell_page.check_device_connected()
        except Exception:
            return
        self.set_device_status(f"设备：{desc}", ok)
        self._refresh_device_combo()

    def _refresh_device_combo(self):
        """把在线设备填进下拉框，保持当前选择不丢。"""
        try:
            devices = toolchain.online_devices()
        except Exception:                                  # noqa: BLE001
            devices = []
        current = toolchain.selected_serial()
        self.deviceCombo.blockSignals(True)
        self.deviceCombo.clear()
        self.deviceCombo.addItem("默认设备（不指定 -s）", "")
        for serial in devices:
            self.deviceCombo.addItem(serial, serial)
        index = self.deviceCombo.findData(current)
        self.deviceCombo.setCurrentIndex(index if index >= 0 else 0)
        self.deviceCombo.blockSignals(False)

        # 选了具体设备但它已经掉线：退回默认并提示，避免命令全打到空气里
        if current and current not in devices:
            toolchain.set_serial("")
            self.toast("设备 {} 已离线，已切回默认设备".format(current), "warning", 3600)
            self.deviceCombo.setCurrentIndex(0)

    def _on_device_changed(self, _index):
        serial = self.deviceCombo.currentData() or ""
        if serial == toolchain.selected_serial():
            return
        toolchain.set_serial(serial)
        app_config.config().update(device_serial=serial)
        if serial:
            self.toast("已切换到设备 {}".format(serial), "success", 2600)
        else:
            self.toast("已切回默认设备", "info", 2000)
        # 状态栏跟着显示当前设备
        self.set_device_status("设备：{}".format(serial or "默认设备"), True)

    # ================= 界面搭建 =================

    def _build_ui(self):
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---- 侧边栏 ----
        self.nav = Sidebar(root)
        self.nav.pageSelected.connect(self.on_nav_selected)
        self._populate_nav()

        # ---- 右侧内容区 ----
        content = QWidget(root)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        content_layout.addWidget(self._build_header())

        self.stack = QStackedWidget(content)
        self.stack.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.stack, 1)

        for key, title, subtitle, cls, _section, _icon in PAGE_DEFS:
            page = cls()
            page.setObjectName(f"page_{key}")
            self.pages[key] = page
            self.stack.addWidget(page)

        root_layout.addWidget(self.nav)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        # ---- 状态栏 ----
        self._build_statusbar()

        self._toast = Toast(root)

    def _populate_nav(self):
        current_section = None
        for key, _title, _subtitle, _cls, section, icon_name in PAGE_DEFS:
            if section != current_section:
                self.nav.add_section(section)
                current_section = section
            self.nav.add_page(key, _title, icon_name)

        self.nav.add_quick_actions("快捷操作", [
            ("devices", "列出设备", "terminal"),
            ("sitepack", "抓现场包", "package"),
            ("root", "获取 root", "refresh"),
            ("remount", "remount", "upload"),
            ("debugfs", "挂载 debugfs", "folder"),
            ("cmdline", "启动参数", "file"),
            ("screencap", "截图并保存", "monitor"),
            ("reboot", "重启设备", "history"),
        ])
        self.nav.quickAction.connect(self.on_quick_action)
        self.nav.add_footer()

    def on_quick_action(self, key):
        """侧边栏快捷操作。"""
        shell_page = self.pages.get("shell")
        if key == "screencap":
            self.nav.select("shell")
            shell_page.on_sc_pull()
            return
        if key == "sitepack":
            # 抓现场包是「出问题了赶紧留证据」，不给它埋进二级导航里
            self.nav.select("tools")
            self.pages["tools"].show_section("sitepack")
            return
        command, label = {
            "devices": ("adb devices", "列出设备"),
            "root": ("adb root", "获取 root"),
            "remount": ("adb remount", "remount"),
            "debugfs": ("adb shell mount -t debugfs none /d", "挂载 debugfs"),
            "cmdline": ("cat /proc/cmdline", "读取启动参数"),
            "reboot": ("adb reboot", "重启设备"),
        }.get(key, (None, None))
        if command is None:
            return
        self.nav.select("shell")
        shell_page.run_command(command, label)

    def _build_header(self):
        bar = QWidget(self)
        bar.setObjectName("headerBar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 16, 10)
        layout.setSpacing(10)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(1)
        self.pageTitle = QLabel("常用工具", bar)
        self.pageTitle.setObjectName("pageTitle")
        self.pageSubtitle = QLabel("", bar)
        self.pageSubtitle.setObjectName("pageSubtitle")
        texts.addWidget(self.pageTitle)
        texts.addWidget(self.pageSubtitle)
        layout.addLayout(texts)
        layout.addStretch()

        self.paletteBtn = self._header_button("命令面板", "search", "Ctrl+K 快速执行常用命令")
        self.paletteBtn.clicked.connect(self.show_command_palette)
        layout.addWidget(self.paletteBtn)

        self.helpBtn = self._header_button("帮助", "help", "查看各功能说明")
        self.helpBtn.clicked.connect(self.show_help)
        layout.addWidget(self.helpBtn)

        self.changelogBtn = self._header_button("更新日志", "history", "查看版本更新记录")
        self.changelogBtn.clicked.connect(self.show_changelog)
        layout.addWidget(self.changelogBtn)

        self.aboutBtn = self._header_button("关于", "info", "关于本工具")
        self.aboutBtn.clicked.connect(self.show_about)
        layout.addWidget(self.aboutBtn)

        self.settingsBtn = self._header_button("设置", "settings", "工具链路径 / 主题")
        self.settingsBtn.clicked.connect(self.show_settings)
        layout.addWidget(self.settingsBtn)

        return bar

    def _header_button(self, text, icon_name, tooltip):
        btn = QPushButton(text, self)
        btn.setIcon(theme.icon(icon_name, theme.TEXT_MUTED, 16, 1.6))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("compact", True)
        btn.setProperty("ghost", True)
        btn.setToolTip(tooltip)
        return btn

    def _build_statusbar(self):
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)

        self.deviceLabel = QLabel("设备：检测中…", self)
        self.deviceLabel.setObjectName("statusChip")
        bar.addWidget(self.deviceLabel)

        # 多设备切换：工位上常同时插着几台板子，不加 -s 时 adb 会随机挑一台，
        # 调试结果对不上号。这里选一次，之后所有命令（含 QProcess 的）都带 -s。
        self.deviceCombo = QComboBox(self)
        self.deviceCombo.setObjectName("deviceCombo")
        self.deviceCombo.setMinimumHeight(22)
        self.deviceCombo.setMinimumWidth(150)
        self.deviceCombo.setToolTip("选择要操作的设备（切换后所有命令都会带上 -s）")
        self.deviceCombo.currentIndexChanged.connect(self._on_device_changed)
        bar.addWidget(self.deviceCombo)

        self.refreshDevicesBtn = QPushButton("刷新", self)
        self.refreshDevicesBtn.setProperty("compact", True)
        self.refreshDevicesBtn.setProperty("ghost", True)
        self.refreshDevicesBtn.setToolTip("重新扫描已连接设备")
        self.refreshDevicesBtn.setCursor(Qt.PointingHandCursor)
        self.refreshDevicesBtn.clicked.connect(self.refresh_device_status)
        bar.addWidget(self.refreshDevicesBtn)

        self.busyLabel = QLabel("", self)
        self.busyLabel.setObjectName("statusChip")
        bar.addWidget(self.busyLabel)

        # adb 没找到时才显示，点了直接进设置——否则用户只会看到一堆
        # 「不是内部或外部命令」，不知道该改什么
        self.toolchainLabel = QLabel("", self)
        self.toolchainLabel.setObjectName("statusChip")
        self.toolchainLabel.setCursor(Qt.PointingHandCursor)
        self.toolchainLabel.hide()
        self.toolchainLabel.mousePressEvent = lambda _e: self.show_settings()
        bar.addWidget(self.toolchainLabel)

        self.clockLabel = QLabel("", self)
        self.clockLabel.setObjectName("statusChip")
        bar.addPermanentWidget(self.clockLabel)

        self.authorLabel = QLabel(theme.APP_AUTHOR, self)
        self.authorLabel.setObjectName("statusChip")
        bar.addPermanentWidget(self.authorLabel)

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+K"), self, self.show_command_palette)
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.nav.select("tools"))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.nav.select("shell"))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.nav.select("initcode"))
        QShortcut(QKeySequence("Ctrl+4"), self, lambda: self.nav.select("lk2kernel"))
        QShortcut(QKeySequence("Ctrl+5"), self, lambda: self.nav.select("kernel2lk"))
        QShortcut(QKeySequence("Ctrl+6"), self, lambda: self.nav.select("lk2bat"))

    def _start_clock(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_clock)
        self.timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = QDateTime.currentDateTime()
        self.clockLabel.setText(now.toString("yyyy-MM-dd HH:mm:ss"))

    # ================= 导航 =================

    def on_nav_selected(self, key):
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        for pkey, title, subtitle, _cls, _section, _icon in PAGE_DEFS:
            if pkey == key:
                self.pageTitle.setText(title)
                self.pageSubtitle.setText(subtitle)
                break
        if hasattr(page, "on_page_shown"):
            page.on_page_shown()

    # ================= 全局提示 =================

    def toast(self, message, kind="info", duration=2200):
        if self._toast is not None:
            self._toast.show_message(message, kind, duration)

    def set_device_status(self, text, ok=True):
        # 序列号很长（如 99022393342169），状态栏在 1400px 窗口下会被挤，
        # 超过 12 字符时截断显示，完整值放 tooltip。
        if len(text) > 14:
            text = text[:12] + "…"
        self.deviceLabel.setText(f"● {text}")
        self.deviceLabel.setToolTip(text)
        self.deviceLabel.setProperty("tone", "ok" if ok else "muted")
        self.deviceLabel.style().unpolish(self.deviceLabel)
        self.deviceLabel.style().polish(self.deviceLabel)

    def set_busy(self, busy):
        self.busyLabel.setText("执行中…" if busy else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._toast is not None:
            self._toast._reposition()

    def closeEvent(self, event):
        """关闭前停掉后台抓取线程，避免 QThread 在运行中被销毁。"""
        try:
            self._save_geometry()
        except Exception:
            pass
        for page in self.pages.values():
            for name in ('stop_background', 'stop'):
                hook = getattr(page, name, None)
                if callable(hook):
                    try:
                        hook()
                    except Exception:
                        pass
                    break
        super().closeEvent(event)

    # ================= 命令面板 =================

    def show_command_palette(self):
        """命令面板（Ctrl+K）。

        数据源和「常用工具 · 命令收藏」是同一份数据（command_store → DisplayTools.json）：
        面板里搜得到收藏页里加的命令；面板里现敲的命令也能直接存进收藏。
        """
        dlg = command_palette.CommandPaletteDialog(command_store.store(), self)
        dlg.commandChosen.connect(self._run_on_shell)
        dlg.manageRequested.connect(self._open_favorites)
        dlg.commandSaved.connect(self._on_command_saved)
        dlg.exec_()
        return dlg

    def _on_command_saved(self, name, added):
        if added:
            self.toast(f"已收藏命令「{name}」", "success")
        else:
            self.toast("这条命令已经在收藏里了", "info")
        self.on_commands_changed()

    def _open_favorites(self):
        """跳到常用工具的「命令收藏」页。"""
        self.nav.select("tools")
        page = self.pages.get("tools")
        if page is not None:
            page.show_section("favorites")

    def on_commands_changed(self):
        """命令收藏有任何增删改时调用：让命令收藏页刷新，两处始终一致。"""
        page = self.pages.get("tools")
        section = getattr(page, "sections", {}).get("favorites") if page else None
        if section is not None and hasattr(section, "reload"):
            section.reload()

    def _run_on_shell(self, command, label):
        page = self.pages.get("shell")
        if page is None:
            return
        self.nav.select("shell")
        page.run_command(command, label)
        self.toast(f"已在 Shell Tools 执行：{label}", "info")

    # ================= 对话框 =================

    def _info_box(self, title, text, width=None, height=None):
        """说明框：固定尺寸 + 正文可滚动。

        以前用 QMessageBox.setText()，正文是 QLabel，文字一长对话框就跟着长，
        超出屏幕的部分完全看不到（更新日志就是这么"看不全"的）。
        """
        dialog = info_dialog.InfoDialog(
            title, text, self,
            **({} if width is None else {"width": width}),
            **({} if height is None else {"height": height}))
        dialog.exec_()
        return dialog

    def show_changelog(self):
        self._info_box("更新日志",
                       "v3.2.14 (当前)\n"
                       "  - 本机文件从三个合成一个：原来 exe 同目录有 config.ini（设置）、\n"
                       "    favorites.json（命令收藏）、path_bookmarks.json（路径书签），\n"
                       "    现在只有 DisplayTools.json 一个，里面分 config / commands /\n"
                       "    path_bookmarks 三段。首次运行会自动把老文件并进来，并把老文件\n"
                       "    改名成 *.migrated（不删数据，确认没用可以自己删）。\n"
                       "  - 命令收藏的增删改一律**立即写回文件**，并补上两个坑：\n"
                       "      · 以前「把命令全删光」后重启会变回内置默认清单（空数组被\n"
                       "        当成没数据）——现在段不存在才用默认，空数组就是空；\n"
                       "      · 写盘失败（exe 放在只读目录等）以前是静默吞掉，现在会弹\n"
                       "        提示，不会让你以为存上了。\n"
                       "  - 「设置」里新增「本机数据文件」：显示完整路径 + 三个段各有多少\n"
                       "    项，带「打开所在文件夹 / 复制路径」。程序是绿色版，数据文件\n"
                       "    跟着 exe 走——从源码跑和从 exe 跑用的是两个目录的文件，\n"
                       "    这里能看到当前到底在用哪个。\n"
                       "  - 「关于」里的目录信息同样改成显示数据文件全名。\n"
                       "  - selftest 189 项：新增老文件迁移（三合一、幂等、只剩一个活文件）、\n"
                       "    段语义（缺段用默认 / 空数组就是空）、界面删除后文件里也没有。\n\n"
                       "v3.2.13 (2026-09-16)\n"
                       "  - 显示调试收拢显示模式参数：dumpsys display / wm size / wm density\n"
                       "    从 Shell Tools 的 adb 卡搬进「分辨率 / 密度 / 刷新率」卡片，\n"
                       "    三行各留「读取 / 应用」，复位收成底下一颗（wm size reset +\n"
                       "    wm density reset）。三行各挂三颗按钮时行宽 340px，比下拉框\n"
                       "    内容宽度（112px）还紧，窗口一窄下拉框就被压成「2400×10…」；\n"
                       "    两按钮后整张卡 324px，任何窗口尺寸下都能完整显示。\n"
                       "  - Shell Tools 去掉 adb 框（命令都已在侧边栏快捷操作 / 命令面板里），\n"
                       "    控制区按卡片高度重新配对：GPIO + Download Mode（87/87）、\n"
                       "    Debug + ylog（155/160）、fastboot flash 整宽，右边只留 Log。\n"
                       "  - 侧边栏「重新挂载」改叫 remount（和命令名一致，一看就知道敲什么）。\n"
                       "  - 命令面板（Ctrl+K）与「命令收藏」统一成一份数据：\n"
                       "    面板里搜得到收藏页加的命令，面板里现敲的命令也能「存为收藏」\n"
                       "    直接落盘；多了「管理收藏」跳转，重复命令不会收两遍。\n"
                       "  - 打包产物统一叫 DisplayTools.exe（不带版本号）：版本号只在\n"
                       "    theme.APP_VERSION 和 git tag 里；旧的带版本号 spec 全部删掉，\n"
                       "    只留 DisplayTools.spec（单文件）与 DisplayTools_onedir.spec（目录版）。\n"
                       "  - 检查更新能直接下载新版本：优先 Release 附件，没有 Release 就\n"
                       "    从仓库 bsp_tools/dist 里拿提交好的 exe（仓库是公开的，无需 token）。\n"
                       "    下载到 exe 同目录，文件名带版本号（免得顶掉正在运行的自己，\n"
                       "    也留着旧版方便回退），下完可一键打开所在文件夹。\n"
                       "  - 常用工具页修掉「切到任何模块都多一条纵向滚动条」：QStackedWidget\n"
                       "    的尺寸提示按所有模块里最高的那个算（763px），内容区被撑高。\n"
                       "    改成按当前模块的需求定尺（放得下就不出滚动条），9 个模块在\n"
                       "    1360x840 下全部无滚动条。\n"
                       "  - selftest 从 140 项加到 170 项：命令面板/收藏共用一份数据、\n"
                       "    更新检查的附件挑选与真实下载（本地 HTTP 服务跑通全流程）。\n\n"
                       "v3.2.12 (2026-09-16)\n"
                       "  - remount 与 cmdline 也移到侧边栏「快捷操作」（现在 8 项）：\n"
                       "    这两个是「随手敲一下」的命令，侧边栏点一下就走，不必先进\n"
                       "    Shell Tools 页。Shell Tools 的 adb 卡只剩 wm size / dumpsys /\n"
                       "    device info 三个查询。\n"
                       "  - adb 卡从 5 个按钮变 3 个后底下空出 68px，顺势把控制区网格按\n"
                       "    卡片高度重新配对：adb + GPIO（都是 adb shell 查询，87/87）、\n"
                       "    Debug + ylog（155/164）、Download Mode + fastboot flash\n"
                       "    （都是刷机相关，87/121）。空白从 68px 降到 43px。\n"
                       "  - adb 卡三个按钮与 Download Mode 的两个按钮改成撑满整行宽度，\n"
                       "    不再右边空一截。\n"
                       "  - selftest 增加侧边栏断言（快捷操作放得下、按钮没被挤掉）。\n\n"
                       "v3.2.11 (2026-09-16)\n"
                       "  - 修背光节点路径：原来读 /sys/class/leds/lcd-backlight，\n"
                       "    实测 T820 上 /sys/class/leds/ 下只有 mmc0:: / mmc1::，\n"
                       "    该节点根本不存在。正确的是 /sys/class/backlight/panel0-backlight/\n"
                       "    （通用/高通）或 /sys/class/backlight/sprd_backlight/（展锐），\n"
                       "    现在按顺序试，读不到会继续试下一个。\n"
                       "  - 背光卡片新增「写节点」：直接写 sysfs 的 brightness（真实 PWM 值，\n"
                       "    需要 root），和走框架的「设置」区分开；「读取」改成同时读\n"
                       "    settings 值与节点值（两者经常不一致，都看才知道谁在生效）；\n"
                       "    勾选框从 max_brightness 扩成 max / actual。\n"
                       "  - ylog 的 Project / Sub-Name 改各占一行：原来挤一行且各限死宽度，\n"
                       "    双双被压到 70px（Sub-Name 只看得到四五个字）；现在各约 260-290px。\n"
                       "  - 现场包的背光项跟着换节点，并一次把 dirs / brightness /\n"
                       "    max_brightness / actual_brightness / settings 都抓进 brightness.txt\n"
                       "  - 顺带修 verify_commands.py：它引用的 INPUT_QUERIES / PANEL_QUERIES\n"
                       "    在早先精简模块时已删除，脚本一直在 AttributeError（只在真机模式\n"
                       "    下跑，所以没暴露）\n\n"
                       "v3.2.10 (2026-09-15)\n"
                       "  - 帮助 / 更新日志 / 关于 / 崩溃日志改用固定尺寸的说明框：\n"
                       "    以前用 QMessageBox.setText()，正文是 QLabel，文字一长对话框\n"
                       "    就跟着长，超出屏幕的部分完全看不到、也没法滚——更新日志\n"
                       "    就是这么「看不全」的。现在窗口尺寸固定（820x620，小屏自动收），\n"
                       "    正文放进只读文本区，滚轮 / 方向键 / PageUp·PageDown / 拖滚动条都能翻。\n"
                       "  - 「关于」里的检查更新 / 打开仓库 / 崩溃日志 三个按钮保留\n"
                       "  - 新增 check_info_dialog.py：断言对话框真的固定尺寸、长文本可滚、\n"
                       "    尺寸不超过屏幕\n\n"
                       "v3.2.9 (2026-09-14)\n"
                       "  - 真正修好 Log 面板宽度：上一版改了算法，但启动就停在\n"
                       "    Shell Tools 时（程序记住了上次页面），分栏是在窗口构造期算的——\n"
                       "    那会儿布局还没算完、splitter 只有 100px 宽，_apply_split_sizes()\n"
                       "    会因太窄直接返回，而页面之后不会再触发，日志框就一直是兜底值：\n"
                       "    360px → 文本框 314px。现在页面 showEvent 里补算一次（sizes 变\n"
                       "    [左, 286]，文本框 240）。\n"
                       "  - ui_shell_tools 里的兜底分栏从 [780, 360] 改成 [800, 286]：\n"
                       "    兜底值必须和约定一致，否则一旦补算没跑成就直接暴露给用户。\n"
                       "  - check_panel_width.py 增加「启动即停在 Shell Tools」回归场景\n\n"
                       "v3.2.8 (2026-09-14)\n"
                       "  - Shell Tools 的 Log 面板改回固定宽度：分隔条分配 286px，\n"
                       "    文本框实测 240px，和常用工具页的「执行结果」面板（270 → 240）\n"
                       "    对齐。原先按窗口宽度的 25% 算，最大化到 1920 时会涨到 400px\n"
                       "    （文本框 354），加上程序会记住窗口尺寸，下次启动就更宽了。\n"
                       "  - 新增 check_panel_width.py：在 6 种窗口尺寸下断言两个面板的\n"
                       "    文本框都是 240px，防止这个约定再被改回去\n\n"
                       "v3.2.7 (2026-09-14)\n"
                       "  - Debug 卡去掉 push / pull（「文件管理」是超集：浏览 + 上传 +\n"
                       "    下载 + 删除 + 路径书签）与 I2C/SPI（板级一次性确认，\n"
                       "    需要时用上面的自定义命令跑），从 4 行收到 3 行\n"
                       "  - Debug 卡重新排版：density / dpi / Set 三等分撑满整行，\n"
                       "    不再挤在左边留一截空白\n"
                       "  - GPIO 卡重新排版：输入框撑满剩余宽度（64px 定宽 → 自适应）\n"
                       "  - 顺带效果：adb 卡的行高落差从 67px 降到 33px\n\n"
                       "v3.2.6 (2026-09-14)\n"
                       "  - 按「侧边栏已有 = 页面上就是重复入口」的原则清掉 3 处：\n"
                       "  · Shell Tools · func 的 pull（截图+拉取）——侧边栏「截图并保存」\n"
                       "    调的是同一个 on_sc_pull()；只截图不拉取的 screencap 保留\n"
                       "  · 常用工具 · 系统调试 →「重启设备」——侧边栏已有\n"
                       "  · 常用工具 · 系统调试 →「挂载 debugfs」——侧边栏已有\n"
                       "  - func 卡剩 4 个按钮改排一行（高 123 → 87）\n\n"
                       "v3.2.5 (2026-09-14)\n"
                       "  - Shell Tools 继续精简：\n"
                       "  · adb 卡片去掉 adb devices / adb root / debugfs / adb reboot 四个按钮，\n"
                       "    剩 remount / wm size / cmdline / dumpsys / device info 排两行\n"
                       "    （前三个在侧边栏「快捷操作」和 Ctrl+K 命令面板里都有，\n"
                       "      reboot 属于危险操作，不该挨着常用按钮放）\n"
                       "  · func 卡片去掉背光滑块（常用工具页的「显示调试」里有更完整的）\n"
                       "  - 按钮行改为垂直居中：这一行高度由旁边的 Debug 决定，按钮少了两行后\n"
                       "    底部会空出来，居中比顶对齐更像刻意留白\n\n"
                       "v3.2.4 (2026-09-14)\n"
                       "  - 修「从剪贴板解析」认不出设备树（DTS）片段的问题：\n"
                       "  · 键名分隔符补上连字符（hfront-porch / hback-porch /\n"
                       "    hsync-len，以及 qcom 的 h-pulse-width 这类词序）\n"
                       "  · 值支持尖括号 <1080>、方括号 [62]、引号 \"12\"\n"
                       "  · 同步宽度补上 len / pulse 两种叫法，lane 数补上 lane_num\n"
                       "  · 刷新率只在注释里时（vfront-porch = <56>;//60hz）也能认\n"
                       "  - 解析反馈改成中文逐项列出，只认出一部分时明确提示缺哪些\n\n"
                       "v3.2.3 (2026-09-14)\n"
                       "  - 数字输入框去掉上下调节小箭头（时序计算十来个框、触摸坐标等都受影响）：\n"
                       "    箭头一排排立着既占宽度又碎；数字照样能手输、滚轮调、上下键调\n"
                       "  - 时序计算的输入框随之收窄一档（70/74/96 → 54/58/78），数字居中更整齐\n\n"
                       "v3.2.2 (2026-09-14)\n"
                       "  - 时序/带宽计算按 t820-lcm-porch.xlsx 的算表重写并重排 UI\n"
                       "  · 新增 DPI 时钟分频：给时钟源（T820 = 384MHz）自动算整数分频比\n"
                       "    ——「需求 pclk ÷ 时钟源」取整，余数超过半个像素时钟就商 +1\n"
                       "  · 新增「实际 pclk」与「实际帧率」：分频凑不出整数时屏体实际跑\n"
                       "    多少帧一目了然（例：1200x1920@60 实际 73.8fps）\n"
                       "  · 每 lane 速率改为「每 lane 需求」，补上 DSI 的 0.9 带宽效率\n"
                       "    （对应表的 H11：实际pclk×bpp÷0.9÷lane），判定式与表一致\n"
                       "  · 界面重排为三段：屏体参数（水平/垂直分两行）→ DPI 时钟分频\n"
                       "    → 结果 8 项 4 列网格；操作按钮移到 DPI 行右侧\n"
                       "  · 新增「复位」按钮；手动分频与自动分频可切换（自动时锁住输入框）\n"
                       "  · 实测与表格逐格对齐：156156000 / 2 / 73 / 1280000000\n\n"
                       "v3.2.1 (2026-09-14)\n"
                       "  - 按 func-list 精简：下线 2 个模块、精简 3 处卡片\n"
                       "  · 异常守护（ESD 不做，其余规则与日志分析/现场包重叠）\n"
                       "  · 电池调试（本阶段用不到）\n"
                       "  · 显示调试里的 DCS 读/写节点与 ESD 重置按钮\n"
                       "  · 显示调试里的 Panel 参数查询卡片（命令面板可替代）\n"
                       "  · 触摸调试里的输入设备枚举/属性查询按钮\n"
                       "  - DCS 卡片改为纯「DCS 包构造」：只算字节序列 + 一键复制，\n"
                       "    不再直接写节点\n"
                       "  - 常用工具：11 → 9 个模块\n\n"
                       "v3.2.0 (2026-09-14)\n"
                       "  【交付健壮性】\n"
                       "  - 新增「设置」：可指定 platform-tools 目录，不再只能靠 PATH\n"
                       "    （发给没装 adb 的同事时这是能不能用的分界线）\n"
                       "  - 启动自检 adb/fastboot，找不到时状态栏给出可点击提示\n"
                       "  - 单实例：重复启动会激活已有窗口，不再两个实例抢设备锁\n"
                       "  - 记住窗口位置/大小与上次打开的页面\n"
                       "  - 崩溃写 crash.log（含 Qt/Python 版本），下次启动提示一次\n"
                       "  - 「关于」里可检查更新（读 GitHub tag）\n"
                       "  【新增功能】\n"
                       "  - 现场包：一键抓属性/dmesg/logcat/dumpsys/显示节点/中断，\n"
                       "    打包成带型号与序列号的 zip，可对每台在线设备各抓一份\n"
                       "  - 异常守护：实时盯 ESD / DSI 超时 / underrun / panic 等关键字，\n"
                       "    命中记录自动合并重复项并可导出\n"
                       "  - 时序 / 带宽计算：算 pclk、DSI 总速率、每 lane 速率，\n"
                       "    支持从剪贴板或 dumpsys 解析参数，超 D-PHY 上限会标红\n"
                       "  - DCS 包构造：给命令和参数自动生成短包/长包字节序列\n"
                       "  - Initcode 反向解析：从字节序列还原 DCS 命令，\n"
                       "    可转回 WriteAddr / Write / Rxx / GEN_WR 四种格式\n"
                       "  - 多设备：状态栏可切换设备，所有命令自动带 -s\n"
                       "  - 日志「高亮关键字」：不隐藏上下文，只标记命中\n"
                       "  【修复】\n"
                       "  - 结果面板新增「停止」与「导出会话」；修正 shell=True 下\n"
                       "    只杀 cmd.exe 导致子进程继续占管道、停止无反应的 bug\n"
                       "  - 深色主题：设置里可切浅色/深色/跟随系统（重启生效）\n\n"
                       "v3.1.2 (2026-09-14)\n"
                       "  - Shell Tools 重排：原布局左列留了 320px 空白，现改为\n"
                       "    两列等高网格，控制区最小需求 989px → 721px\n"
                       "  - 日志面板默认宽度对齐常用工具的「执行结果」面板（240px）\n"
                       "  - 修复电池电压误读：dumpsys 里 “Max charging voltage” 排在\n"
                       "    “voltage” 之前，被当成实时电压显示成 12000 mV；现在按行首\n"
                       "    匹配，设备不上报时改用充电上限并标注「（上限）」\n"
                       "  - 修复电流为 0 时不回退到充电上限的问题\n"
                       "  - fastboot 分区下拉框加占位提示，不再显示为空白\n"
                       "  - 全页面复查：5 种窗口尺寸下均无重叠 / 压缩 / 越界\n\n"
                       "v3.1.1 (2026-09-14)\n"
                       "  - 修复点击常用工具里的按钮会跳到 Shell Tools 页的问题\n"
                       "    （原因：显示调试/收藏夹调用了 nav.select('shell')，\n"
                       "      现在命令输出统一显示在常用工具页底部面板，不再跳转）\n"
                       "  - 新增 3 个调试模块：触摸调试、电池调试、系统调试\n"
                       "  - 常用工具改为「左侧模块导航 + 底部输出面板」，共 9 个模块\n"
                       "  - 修复 Shell Tools 界面控件挤在一起的问题\n"
                       "    （原因：原布局最小高度需求 989px，普通窗口只有约 774px）\n"
                       "  - 重排 Shell Tools：adb 按钮 3 列网格、Debug 合并为 3 行、\n"
                       "    fastboot/func 双列；按钮内边距收紧\n"
                       "  - 各页面加滚动兜底：窗口缩小时滚动查看，不再压扁控件\n"
                       "  - 设备信息的型号/内核/Panel 等长文本改为中途省略并带完整 tooltip\n"
                       "  - 修复「掉帧累计」单位错误显示为 fps（应为帧数）\n\n"
                       "v3.1.0 (2026-09-12)\n"
                       "  - 全新界面：左侧边栏导航 + 卡片式布局 + 矢量图标\n"
                       "  - 新增「常用工具」页：日志分析、设备信息、收藏夹、文件管理、显示调试、性能监控\n"
                       "  - 新增命令面板（Ctrl+K）：一键执行常用 adb 命令\n"
                       "  - 统一设计系统 theme.py，配色/间距/圆角全局一致\n"
                       "  - 状态栏新增设备连接状态指示\n"
                       "  - 操作结果以浮层提示反馈\n\n"
                       "v3.0.2 (2026-07-07)\n"
                       "  - 修复 adb push/pull 设备路径历史丢失问题\n"
                       "  - save_config 增量更新，不再覆盖历史键\n"
                       "  - 修复按钮点击红框（focus outline）\n"
                       "  - 导出 ylog 按钮高度与输入框齐平\n"
                       "  - 作者名 AIBIN 改为 a1bin\n\n"
                       "v3.0.1 (2026-07-02)\n"
                       "  - 新增更新日志面板\n"
                       "  - adb push/pull 设备路径共享历史（10条）\n"
                       "  - 修复 dmesg -w 闪退问题，Stop 可终止所有命令\n"
                       "  - 优化布局：ylog/APK 高度缩减，Log 区域增大\n"
                       "  - 删除菜单栏，关于/Help/更新日志移至顶部\n"
                       "  - 新增 fastboot flash 路径记忆、GPIO 状态查询\n\n"
                       "v3.0.0 (2026-06-27)\n"
                       "  - 全面重构 UI：单窗口 Tab 切换，全局样式\n"
                       "  - Shell Tools 新增：adb/fastboot/Debug/func/Download Mode\n"
                       "  - 自定义 shell 输入：支持流式输出、管道命令、历史记录\n"
                       "  - fastboot flash：分区烧录（erase + flash）\n"
                       "  - Debug：density、printk、I2C/SPI 检测\n\n"
                       "v2.2.0 (2026-06-23)\n"
                       "  - 首版 Shell Tools 集成\n"
                       "  - adb/fastboot 基本操作\n"
                       "  - ylog 导出、APK 安装、投屏")

    def show_help(self):
        lines = [
            '【常用工具】9 个模块，命令输出显示在右侧面板（不会跳页）',
            '  日志分析   - 抓取 logcat/dmesg/ylog，关键字过滤/高亮、错误提取、导出',
            '  设备信息   - 设备型号 / 系统 / 屏幕 / 温度 / 电量，可导出报告',
            '  显示调试   - 背光、分辨率、刷新率、DCS 包构造、时序/带宽计算（含 DPI 分频）',
            '  现场包     - 一键抓全现场证据并打包 zip（可对每台设备各抓一份）',
            '  触摸调试   - 点击/滑动/按键注入、触摸可视化开关、getevent 抓取',
            '  系统调试   - 属性读写、CPU 调频、内存/进程/挂载、SELinux、重启到 bootloader',
            '  性能监控   - CPU/内存/温度/帧率采样、趋势曲线与采样记录',
            '  文件管理   - 浏览设备目录、上传下载、常用路径书签',
            '  命令收藏   - 常用命令增删改查，双击直接执行',
            '',
            '【Shell Tools】',
            '  adb        - wm size / dumpsys / device info（其余命令见左侧「快捷操作」）',
            '  Download Mode - UNISOC autodloader、QCOM EDL',
            '  Debug      - 自定义命令、density/dpi、printk 读写',
            '  fastboot   - 分区烧录（erase + flash）、bootloader / reboot',
            '  func       - 电源键、截图、录屏开始·停止',
            '  GPIO       - 查询 GPIO 状态（留空查全部）',
            '  ylog / APK - 导出日志、安装 APK、投屏',
            '',
            '  注：侧边栏「快捷操作」是这些命令的常驻入口——',
            '      adb devices / root / remount / debugfs / reboot / cmdline、截图并保存',
            '      都在那儿，页面上不再重复放按钮；背光在常用工具页的「显示调试」里。',
            '      func 的 pull（截图+拉取）与系统调试的「重启设备 / 挂载 debugfs」',
            '      同理下线：侧边栏已有同一入口，不再重复。',
            '      Debug 的 push/pull 也下线了——「文件管理」是超集（浏览 + 上传 +',
            '      下载 + 删除 + 路径书签），文件传输统一走那边。',
            '',
            '【转换工具】',
            '  Initcode Builder - 寄存器读写描述 ↔ initcode 字节序列（双向）',
            '  LK / Kernel 互转 - 两种十六进制序列互转',
            '  LK → BAT         - 生成 DCS 写入批处理',
            '',
            '【多设备】状态栏下拉框选设备，之后所有命令都会带 -s',
            '',
            '【快捷键】',
            '  Ctrl+K  命令面板      Ctrl+1~6  切换页面',
            '  左侧边栏「快捷操作」会在 Shell Tools 页执行并显示',
            '',
            '【设置】顶部「设置」按钮',
            '  工具链路径 - 没装 platform-tools 的机器在这里指定目录或 adb.exe',
            '  主题       - 跟随系统 / 浅色 / 深色（重启后生效）',
            '  崩溃日志   - 异常退出会写到 exe 同目录的 crash.log',
        ]
        self._info_box("使用说明", chr(10).join(lines))

    def show_about(self):
        crash = getattr(self, "crash_notice", None)
        extra = ""
        if crash:
            extra = "\n\n⚠ 上次运行异常退出，最近一次堆栈末行：\n{}".format(
                crash.strip().splitlines()[-1][:160])
        text = (
            "{}\n"
            "版本：{}\n"
            "作者：{}\n\n"
            "adb：{}\n"
            "fastboot：{}\n"
            "数据目录：{}\n"
            "数据文件：{}（设置 / 命令收藏 / 路径书签都在这一个文件里，{}\n"
            "          命令收藏与 Ctrl+K 命令面板共用它）\n\n"
            "常用工具：日志分析 | 设备信息 | 显示调试 | 现场包 | 触摸调试 |\n"
            "          系统调试 | 性能监控 | 文件管理 | 命令收藏\n"
            "Shell 工具：fastboot 控制 | 自定义命令 | density | printk |\n"
            "            烧录 | 截图录屏 | ylog | APK | 投屏\n"
            "转换工具：Initcode 构建（双向） | LK↔Kernel 互转 | LK→BAT{}".format(
                "{} - BSP-LCM 调试工具集".format(theme.APP_NAME),
                theme.APP_VERSION, theme.APP_AUTHOR,
                toolchain.describe("adb"), toolchain.describe("fastboot"),
                app_config.data_dir(), os.path.basename(app_config.config_path()),
                "程序是绿色版，数据跟着 exe 走；从源码跑和从 exe 跑是两个目录",
                extra))
        # 关于框不需要那么高，内容短
        dialog = info_dialog.InfoDialog(
            "关于", text, self, width=760, height=460,
            actions=[("检查更新", self.check_updates),
                     ("打开仓库", self._open_repo),
                     ("崩溃日志", self._open_crash_log)])
        dialog.exec_()

    def _open_repo(self):
        QDesktopServices.openUrl(QUrl(update_check.repo_url()))
        return False            # 点完就关掉关于框

    def _open_crash_log(self):
        self.show_crash_log()
        return False

    # ================= 更新检查 =================

    def check_updates(self):
        """手动触发一次版本检查（后台线程，失败只提示不弹窗）。

        查到新版本时，如果 release 里带了可下载的附件，就直接问要不要下载；
        没有附件（或只有 tag）就退回提示 + 打开发布页。
        """
        if getattr(self, "_update_checker", None) is not None \
                and self._update_checker.isRunning():
            self.toast("正在检查更新…", "info", 1500)
            return
        self.toast("正在检查更新…", "info", 1500)

        checker = update_check.UpdateChecker(self)

        def done(kind, message):
            if kind == "newer":
                self._offer_update(message)
            else:
                self.toast(message, "success" if kind == "ok" else "error", 5200)

        checker.finished_with.connect(done)
        checker.finished.connect(lambda: setattr(self, "_update_checker", None))
        self._update_checker = checker
        checker.start()

    def _offer_update(self, message):
        """发现新版本：列出说明和附件大小，给「下载 / 打开发布页」两个按钮。"""
        result = getattr(self._update_checker, "result", {}) or {}
        tag = result.get("tag") or ""
        asset = result.get("asset") or {}
        lines = [message, ""]
        if asset:
            where = "仓库" if result.get("source") == "repo" else "Release 附件"
            if asset.get("path"):
                where = "{}里的 {}".format(where, asset["path"])
            lines.append("下载来源：{}".format(where))
            lines.append("附件：{}（{}）".format(
                asset.get("name") or "-", update_check.human_size(asset.get("size"))))
            lines.append("保存到：{}".format(os.path.join(
                update_check.download_dir(),
                update_check.default_download_name(tag, asset))))
            lines.append("下载文件名带版本号：正在运行的 DisplayTools.exe 是锁着的，"
                         "覆盖不了，也留着它方便回退。")
        else:
            lines.append("这个版本没有可下载的安装包，点「打开发布页」在浏览器里下载。")
        if result.get("notes"):
            lines.extend(["", "本次更新说明：", result["notes"].strip()])
        lines.extend(["", "发布页：{}".format(result.get("html_url") or update_check.releases_url())])

        actions = [("打开发布页", self._open_release)]
        if asset:
            actions.insert(0, ("下载新版本", lambda: self.download_update(result)))
        dialog = info_dialog.InfoDialog("发现新版本 {}".format(tag or ""),
                                        chr(10).join(lines), self,
                                        width=760, height=480, actions=actions)
        dialog.exec_()

    def _open_release(self):
        result = getattr(self._update_checker, "result", {}) or {}
        QDesktopServices.openUrl(QUrl(result.get("html_url")
                                      or update_check.releases_url()))
        return False

    def download_update(self, result=None):
        """后台把新版本下载到本地（先写 .part，好了再改名）。"""
        result = result or (getattr(self, "_update_checker", None).result or {})
        asset = result.get("asset") or {}
        if not asset:
            self.toast("这个版本没有可下载的附件，请打开发布页下载", "warning", 5000)
            return False
        tag = result.get("tag") or ""
        dest = os.path.join(update_check.download_dir(),
                            update_check.default_download_name(tag, asset))
        if getattr(self, "_update_downloader", None) is not None \
                and self._update_downloader.isRunning():
            self.toast("正在下载…", "info", 1500)
            return True

        downloader = update_check.UpdateDownloader(asset, dest, self)
        self._update_downloader = downloader
        self._download_reported = 0

        def on_progress(done, total):
            # 每 10% 报一次，免得浮层刷屏
            if not total:
                return
            percent = int(done * 100 / total)
            if percent >= self._download_reported + 10 or percent >= 100:
                self._download_reported = percent
                self.toast("正在下载新版本… {}%".format(percent), "info", 1500)

        def on_done(kind, message):
            self._update_downloader = None
            if kind != "ok":
                self.toast(message, "error", 6000)
                return
            self.toast("新版本已下载：{}".format(os.path.basename(message)), "success", 6000)
            dialog = info_dialog.InfoDialog(
                "下载完成",
                "新版本已保存到：\n{}\n\n"
                "用法：退出当前程序，把新文件改名成 DisplayTools.exe 覆盖旧的即可"
                "（旧文件建议先留着，新版本起不来能马上回退）。".format(message),
                self, width=620, height=360,
                actions=[("打开所在文件夹", lambda: (self._open_folder(message), False)[1])])
            dialog.exec_()

        downloader.progress.connect(on_progress)
        downloader.finished_with.connect(on_done)
        downloader.start()
        self.toast("开始下载：{}".format(os.path.basename(dest)), "info", 3000)
        return True

    @staticmethod
    def _open_folder(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(os.path.abspath(path))))


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)

    # 主题必须在任何控件之前定下来：图标是按当时颜色画好的 QIcon，
    # 控件的内联样式也在构造时就把颜色烤进去了
    theme.set_mode(app_config.config().get("theme", "system"))
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())

    # 上次选中的设备要恢复：多设备工位上每次启动都重选很烦
    toolchain.set_serial(app_config.config().get("device_serial", ""))

    # 异常兜底要在建窗口之前装上：窗口构造期崩了同样是"什么都没留下"
    app_runtime.install_excepthook()

    window = MainWindow()

    # 单实例：两个实例会互抢 adb server 与设备锁，第二个直接激活第一个
    guard = app_runtime.SingleInstance(
        on_activate=lambda: (window.showNormal(), window.raise_(),
                             window.activateWindow()))
    if not guard.acquire():
        print("DisplayTools 已在运行，已激活原窗口。")
        return 0
    window._single_instance = guard          # 保住引用，否则会被回收

    window.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
