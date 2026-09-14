"""常用工具 · 现场包（一键抓取现场证据）。

LCM/屏体问题复现窗口很短，等人手点十几次、逐条复制，现场早就过去了。
这里把「出问题时该留什么」固化成一个按钮：属性、dmesg、logcat（含 crash
buffer）、dumpsys 各子系统、显示/背光 sysfs 节点、中断、挂载……全部抓下来
打包成一个带型号和时间的 zip，直接发给屏厂或贴进问题单。

设计取舍：
- 抓取项是**固定清单**而不是自由命令：现场不该再花时间想要抓什么；
- 单项失败不中断（老平台没有 /d/gpio、没有 dsi 节点很正常），失败也写进
  meta.txt——"哪个节点不存在"本身就是信息；
- 全部输出都落盘，不在界面上堆几 MB 文本。
"""

import os
import re
import subprocess
import zipfile
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLineEdit, QLabel, QCheckBox, QProgressBar,
                             QFileDialog, QPlainTextEdit)

import app_config
import theme
import toolchain
import ui_widgets as W
# 背光节点路径与"按顺序试"的命令只有一处定义（显示调试模块），
# 这里直接复用，免得两边各写一份又走岔
from tools_display import (ACTUAL_BRIGHTNESS_READ,  # noqa: E402
                           BRIGHTNESS_READ, MAX_BRIGHTNESS_READ)
# (key, 界面名, 文件名, 设备端命令, 超时秒)
# 命令写成裸的设备端命令，由 build_command() 统一补 adb shell
PACK_ITEMS = [
    ("props", "系统属性", "getprop.txt", "getprop", 30),
    ("props_display", "显示相关属性", "props_display.txt",
     "getprop | grep -i -E 'display|lcm|panel|dsi|backlight'", 20),
    ("dmesg", "内核日志 dmesg", "dmesg.txt", "dmesg", 60),
    ("logcat", "logcat 全量", "logcat.txt", "logcat -d -v threadtime", 90),
    ("logcat_crash", "logcat 崩溃", "logcat_crash.txt",
     "logcat -d -b crash -v threadtime", 45),
    ("display", "dumpsys display", "dumpsys_display.txt", "dumpsys display", 45),
    ("sf", "SurfaceFlinger", "dumpsys_surfaceflinger.txt",
     "dumpsys SurfaceFlinger", 60),
    ("battery", "电池", "dumpsys_battery.txt", "dumpsys battery", 25),
    ("input", "输入子系统", "dumpsys_input.txt", "dumpsys input", 45),
    ("meminfo", "内存", "meminfo.txt", "cat /proc/meminfo", 20),
    ("interrupts", "中断统计", "interrupts.txt", "cat /proc/interrupts", 20),
    ("cmdline", "内核 cmdline", "cmdline.txt", "cat /proc/cmdline", 15),
    ("mount", "挂载信息", "mount.txt", "mount", 20),
    ("ps", "进程列表", "ps.txt", "ps -A", 30),
    ("sysfs_display", "显示/背光节点", "sysfs_display.txt",
     "ls -l /sys/class/display/ /sys/class/backlight/ /sys/class/leds/", 20),
    # 背光节点路径跟平台有关：panel0-backlight（通用/高通）或
    # sprd_backlight（展锐 T820）。原来写死的 /sys/class/leds/lcd-backlight
    # 在 T820 上不存在（实测 /sys/class/leds/ 下只有 mmc0:: / mmc1::）。
    ("brightness", "背光亮度", "brightness.txt",
     "echo '--- dirs ---'; ls /sys/class/backlight/; "
     "echo '--- brightness ---'; " + BRIGHTNESS_READ + "; "
     "echo '--- max_brightness ---'; " + MAX_BRIGHTNESS_READ + "; "
     "echo '--- actual_brightness ---'; " + ACTUAL_BRIGHTNESS_READ + "; "
     "echo '--- settings ---'; settings get system screen_brightness", 20),
    ("gpio", "GPIO 状态", "gpio.txt", "cat /d/gpio", 20),
    ("wm", "分辨率/密度", "wm.txt", "wm size; wm density", 20),
]

DEFAULT_ON = {"props", "props_display", "dmesg", "logcat", "logcat_crash",
              "display", "sf", "battery", "sysfs_display", "brightness", "wm"}

# 这些命令带管道/分号，必须整体交给设备端 shell 解析
_SHELL_CHARS = re.compile(r"[|><&;]")


def build_command(device_command, serial=None):
    """设备端命令 → 可执行的 adb 命令行。

    serial 显式给定时用它（现场包的「每台设备各抓一份」），否则用全局选中的
    设备（toolchain.adb_shell() 已经带了 -s），两边不能叠加，否则会出现
    `adb -s A -s B`。
    """
    if serial:
        adb = "{} -s {}".format(toolchain.shell_exe("adb"), serial)
    else:
        adb = toolchain.adb_shell()
    if _SHELL_CHARS.search(device_command):
        return '{} shell "{}"'.format(adb, device_command)
    return "{} shell {}".format(adb, device_command)


def safe_name(text, fallback="device"):
    """型号/序列号里可能有空格、斜杠、冒号，不能直接当文件名。"""
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", (text or "").strip())
    return cleaned.strip("_") or fallback


class Collector(QThread):
    """逐个执行抓取项；单项失败不中断，结果全部回传给界面。"""

    step = pyqtSignal(int, int, str)            # 已完成数, 总数, 当前项名
    line = pyqtSignal(str, str)                 # 级别(ok/warn), 文本
    finished_pack = pyqtSignal(bool, str)       # 成功?, 结果路径或错误

    def __init__(self, items, out_dir, note="", serial=None, parent=None):
        super().__init__(parent)
        self.items = items                       # [(key, label, filename, cmd, timeout)]
        self.out_dir = out_dir
        self.note = note
        self.serial = serial
        self._stop = False
        self._process = None

    def stop(self):
        self._stop = True
        from command_runner import kill_process_tree
        kill_process_tree(self._process)

    def run(self):
        tmp_dir = os.path.join(
            self.out_dir,
            "_sitepack_tmp_{}".format(datetime.now().strftime("%H%M%S%f")))
        try:
            os.makedirs(tmp_dir, exist_ok=True)
        except Exception as exc:                           # noqa: BLE001
            self.finished_pack.emit(False, "无法创建临时目录：{}".format(exc))
            return

        meta = []
        collected = 0
        total = len(self.items)
        for index, (key, label, filename, command, timeout) in enumerate(self.items, 1):
            if self._stop:
                self.finished_pack.emit(False, "已取消")
                _cleanup(tmp_dir)
                return
            self.step.emit(index - 1, total, label)
            started = datetime.now()
            exit_code, output = self._run_one(build_command(command, self.serial),
                                              timeout)
            elapsed = (datetime.now() - started).total_seconds()
            try:
                with open(os.path.join(tmp_dir, filename), "w",
                          encoding="utf-8", errors="replace") as handle:
                    handle.write(output or "")
            except Exception as exc:                       # noqa: BLE001
                self.line.emit("warn", "{} 写入失败：{}".format(label, exc))
                continue
            collected += 1
            ok = exit_code == 0 and bool((output or "").strip())
            meta.append((label, filename, command, exit_code, elapsed,
                         len(output or "")))
            self.line.emit("ok" if ok else "warn",
                           "{} · {} 行 · {:.1f}s{}".format(
                               label, len((output or "").splitlines()), elapsed,
                               "" if ok else "（退出码 {}，可能该平台不支持）".format(exit_code)))

        meta_path = os.path.join(tmp_dir, "meta.txt")
        self._meta_rows = meta
        self._write_meta(meta_path, self.out_dir, self.note, self.serial)
        if self._stop:
            self.finished_pack.emit(False, "已取消")
            _cleanup(tmp_dir)
            return
        try:
            pack_path = self._zip(tmp_dir)
        except Exception as exc:                           # noqa: BLE001
            self.finished_pack.emit(False, "打包失败：{}".format(exc))
            _cleanup(tmp_dir)
            return
        _cleanup(tmp_dir)
        self.step.emit(total, total, "完成")
        self.finished_pack.emit(True, pack_path)

    # ---------- 内部 ----------

    def _run_one(self, command, timeout):
        """执行一条命令，返回 (exit_code, 文本)。"""
        try:
            self._process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                shell=True)
            out, _ = self._process.communicate(timeout=timeout)
            text = re.sub(r"\r+\n", "\n", out.decode(errors="replace"))
            return self._process.returncode, text
        except subprocess.TimeoutExpired:
            from command_runner import kill_process_tree
            kill_process_tree(self._process)
            return -1, "[超时] {}s 未返回".format(timeout)
        except Exception as exc:                           # noqa: BLE001
            return -1, "[错误] {}".format(exc)
        finally:
            self._process = None

    def _zip(self, tmp_dir):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        model = safe_name(self._read_device("ro.product.model"), "device")
        serial = self.serial or self._read_device("ro.serialno")
        suffix = "_{}".format(safe_name(self.note)) if self.note.strip() else ""
        name = "{}_{}{}_{}.zip".format(model, safe_name(serial, "noserial"),
                                       suffix, stamp)
        path = os.path.join(self.out_dir, name)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in sorted(os.listdir(tmp_dir)):
                archive.write(os.path.join(tmp_dir, entry), entry)
        return path

    def _read_device(self, prop):
        try:
            out = subprocess.run(
                build_command("getprop {}".format(prop), self.serial),
                shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=10).stdout.decode(errors="replace")
            return out.strip()
        except Exception:                                  # noqa: BLE001
            return ""

    def _write_meta(self, path, out_dir, note, serial):
        device_serial = serial or self._read_device("ro.serialno")
        lines = [
            "# DisplayTools 现场包",
            "抓取时间：{}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "工具版本：{}".format(theme.APP_VERSION),
            "adb 路径：{}".format(toolchain.exe_path("adb")),
            "设备序列号：{}".format(device_serial or "(默认设备)"),
            "备注：{}".format(note or "(无)"),
            "",
            "## 设备概况",
        ]
        for prop in ("ro.product.model", "ro.product.brand", "ro.build.display.id",
                     "ro.build.version.release", "ro.build.version.sdk",
                     "ro.hardware", "ro.board.platform"):
            lines.append("{:<28} {}".format(prop, self._read_device(prop) or "(空)"))
        lines += ["", "## 抓取清单", ""]
        lines.append("{:<18} {:<26} {:>6} {:>7} {:>9}".format(
            "项目", "文件", "退出码", "耗时(s)", "字节数"))
        for label, filename, command, code, elapsed, size in self._meta_rows:
            lines.append("{:<18} {:<26} {:>6} {:>7.1f} {:>9}".format(
                label, filename, code, elapsed, size))
        lines += ["", "## 命令原文"]
        for label, filename, command, *_rest in self._meta_rows:
            lines.append("{:<18} adb shell {}".format(label, command))
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        except Exception:                                  # noqa: BLE001
            pass


def _cleanup(tmp_dir):
    try:
        for entry in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, entry))
        os.rmdir(tmp_dir)
    except Exception:                                      # noqa: BLE001
        pass


class SitePackSection(QWidget):
    """现场包抓取区。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collector = None
        self._build_ui()

    # ---------- 界面 ----------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_main_card())
        layout.addWidget(self._build_progress_card(), 1)

    def _build_main_card(self):
        card = W.Card("一键抓取现场包")
        hint = W.heading(
            "出问题时点一下：属性 / dmesg / logcat（含崩溃）/ dumpsys / "
            "显示节点 / 中断 一次性抓全，打包成 zip 直接发给屏厂或贴问题单。")
        card.add(hint)

        row = card.add_row()
        row.addWidget(W.field_label("保存到", card))
        self.out_edit = QLineEdit(card)
        self.out_edit.setMinimumHeight(30)
        self.out_edit.setText(app_config.config().get("sitepack_dir", ""))
        self.out_edit.setPlaceholderText("默认保存到 exe 同目录的 sitepack 文件夹")
        row.addWidget(self.out_edit, 1)
        browse = W.soft_button("浏览…", None, card)
        browse.clicked.connect(self._pick_dir)
        row.addWidget(browse)
        open_btn = W.soft_button("打开目录", "folder", card)
        open_btn.clicked.connect(self._open_dir)
        row.addWidget(open_btn)

        note_row = card.add_row()
        note_row.addWidget(W.field_label("备注", card))
        self.note_edit = QLineEdit(card)
        self.note_edit.setMinimumHeight(30)
        self.note_edit.setPlaceholderText("可选，会拼进文件名，例如 闪屏 / 花屏 / ESD")
        note_row.addWidget(self.note_edit, 1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.boxes = {}
        for index, (key, label, _filename, _command, _timeout) in enumerate(PACK_ITEMS):
            box = QCheckBox(label, card)
            box.setChecked(key in DEFAULT_ON)
            box.setToolTip("adb shell {}".format(_command))
            self.boxes[key] = box
            grid.addWidget(box, index // 4, index % 4)
        for col in range(4):
            grid.setColumnStretch(col, 1)
        card.add_layout(grid)

        actions = card.add_row()
        self.start_btn = W.accent_button("开始抓取", "package", card)
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self.start)
        actions.addWidget(self.start_btn)
        self.stop_btn = W.danger_button("取消", None, card)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        actions.addWidget(self.stop_btn)
        self.all_devices_check = QCheckBox("每台在线设备各抓一份", card)
        self.all_devices_check.setToolTip(
            "多设备工位用：对每台已连接设备分别抓一次，文件名带各自序列号")
        actions.addWidget(self.all_devices_check)
        self.select_all = W.soft_button("全选", None, card)
        self.select_all.clicked.connect(lambda: self._check_all(True))
        actions.addWidget(self.select_all)
        self.select_none = W.soft_button("全不选", None, card)
        self.select_none.clicked.connect(lambda: self._check_all(False))
        actions.addWidget(self.select_none)
        actions.addStretch()
        return card

    def _build_progress_card(self):
        card = W.Card("抓取进度")
        self.progress = QProgressBar(card)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMinimumHeight(18)
        self.progress.setTextVisible(True)
        card.add(self.progress)

        self.status_label = W.heading("就绪", card)
        card.add(self.status_label)

        self.detail = QPlainTextEdit(card)
        self.detail.setObjectName("logView")
        self.detail.setReadOnly(True)
        self.detail.setFont(theme.mono_font(9))
        self.detail.setPlaceholderText("抓取明细会显示在这里…")
        self.detail.setMinimumHeight(120)
        card.add(self.detail, 1)
        return card

    # ---------- 交互 ----------

    def _check_all(self, checked):
        for box in self.boxes.values():
            box.setChecked(checked)

    def _target_dir(self):
        path = self.out_edit.text().strip()
        if not path:
            path = os.path.join(app_config.data_dir(), "sitepack")
        return os.path.normpath(path)

    def _pick_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", self._target_dir())
        if folder:
            self.out_edit.setText(os.path.normpath(folder))

    def _open_dir(self):
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        path = self._target_dir()
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def selected_items(self):
        return [item for item in PACK_ITEMS if self.boxes[item[0]].isChecked()]

    def start(self):
        if self._collector is not None and self._collector.isRunning():
            return
        items = self.selected_items()
        if not items:
            self._toast("至少选一项要抓的内容", "warning")
            return
        out_dir = self._target_dir()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as exc:                           # noqa: BLE001
            self._toast("目录不可用：{}".format(exc), "error")
            return
        app_config.config().update(sitepack_dir=self.out_edit.text().strip())

        self.detail.clear()
        self.progress.setValue(0)
        self.status_label.setText("开始抓取…")
        self._set_busy(True)

        collector = Collector(items, out_dir, self.note_edit.text(),
                              serial=self._target_serial())
        collector.step.connect(self._on_step)
        collector.line.connect(self._on_line)
        collector.finished_pack.connect(self._on_finished)
        self._collector = collector
        collector.start()

    def _target_serial(self):
        """勾了「每台设备各抓一份」就逐台抓，否则只抓当前选中的那台。

        返回 None 表示用 adb 默认设备（唯一设备时就是它）。
        """
        if not self.all_devices_check.isChecked():
            return toolchain.selected_serial() or None
        if not getattr(self, "_queue", None):
            devices = toolchain.online_devices()
            if not devices:
                return toolchain.selected_serial() or None
            self._queue = list(devices)
            self.detail.appendPlainText(
                "多设备模式：{} 台（{}）".format(len(self._queue), "、".join(self._queue)))
        return self._queue[0]

    def stop(self):
        if self._collector is not None and self._collector.isRunning():
            self.status_label.setText("正在取消…")
            self._collector.stop()

    def _set_busy(self, busy):
        self.start_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        for box in self.boxes.values():
            box.setEnabled(not busy)

    # ---------- 回调 ----------

    def _on_step(self, done, total, label):
        percent = int(done * 100 / total) if total else 0
        self.progress.setValue(percent)
        self.status_label.setText("({}/{}) {}".format(done + 1, total, label))

    def _on_line(self, level, text):
        prefix = "✓" if level == "ok" else "!"
        self.detail.appendPlainText("{} {}".format(prefix, text))

    def _on_finished(self, ok, path):
        # 多设备模式：一台抓完接着抓下一台
        queue = getattr(self, "_queue", None)
        if queue:
            finished = getattr(self._collector, "serial", None)
            if finished and finished in queue:
                queue.remove(finished)
            else:
                queue.pop(0)
            if queue and ok:
                self.detail.appendPlainText(
                    "\n--- 继续抓下一台：{} ---".format(queue[0]))
                self._collector = None
                QTimer.singleShot(200, self.start)
                return
            self._queue = None

        self._set_busy(False)
        if ok:
            self.progress.setValue(100)
            size = os.path.getsize(path) / 1024.0 if os.path.isfile(path) else 0
            self.status_label.setText("完成：{}（{:.0f} KB）".format(
                os.path.basename(path), size))
            self.detail.appendPlainText("\n现场包：{}".format(path))
            self._toast("现场包已生成：{}".format(os.path.basename(path)), "success", 4200)
            self._last_pack = path
        else:
            self.status_label.setText("未完成：{}".format(path))
            self.detail.appendPlainText("\n[未完成] {}".format(path))
            self._toast("现场包未生成：{}".format(path), "warning", 3600)
        self._collector = None

    def _toast(self, message, kind="info", duration=2200):
        window = self.window()
        if hasattr(window, "toast"):
            window.toast(message, kind, duration)

    # ---------- 生命周期 ----------

    def stop_background(self):
        if self._collector is not None and self._collector.isRunning():
            self._collector.stop()
            self._collector.wait(3000)
