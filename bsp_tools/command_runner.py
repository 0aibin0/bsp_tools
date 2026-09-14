"""常用工具各模块共用的命令执行器与结果面板。

原来各模块点按钮后会把用户弹到 Shell Tools 页看输出，操作被打断。
这里把"执行命令 + 显示结果"收回到模块内部：每个模块调用 page.run_command()，
输出落在模块自己的结果面板里，页面不跳转。

Shell Tools 页的日志区仍然保留（那边是主动操作设备的主界面），
但常用工具页不再依赖它。
"""

import os
import re
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
                             QApplication, QSizePolicy)

import theme
import toolchain
import ui_widgets as W

CMD_TIMEOUT = 25

# 设备端命令：这些是跑在 Android 里的，不是 Windows 命令，
# 直接执行会报 "'dumpsys' is not recognized as an internal or external command"。
# 所以统一由 device_cmd() 补上 adb shell 前缀。
DEVICE_COMMANDS = {
    "dumpsys", "getprop", "setprop", "cat", "ls", "lsmod", "mount", "df", "du",
    "top", "ps", "uname", "date", "service", "settings", "wm", "input",
    "getevent", "sendevent", "logcat", "dmesg", "ifconfig", "ip", "netstat",
    "screencap", "screenrecord", "pm", "am", "svc", "stop", "start", "sync",
    "chmod", "chown", "mkdir", "rm", "cp", "mv", "touch", "echo", "id", "whoami",
    "getenforce", "setenforce", "reboot", "timeout", "sh", "sleep",
}

# 需要交给设备端 shell 解析的字符（管道、重定向、逻辑连接）
_DEVICE_SHELL_CHARS = re.compile(r"[|><&;]")

# cmd.exe 即使在双引号内也会把 & 当分隔符，执行前先换掉
_AMP_PLACEHOLDER = "\x01AMP\x01"


def device_cmd(command):
    """把设备端命令补全成 `adb shell "..."`。

    - 已经是 adb/fastboot 命令的，只把程序名换成配置好的可执行文件
    - 单个设备命令（dumpsys battery）→ adb shell dumpsys battery
    - 带管道/重定向的（dumpsys display | grep …）→ adb shell "…"，
      整条交给设备端 shell 解析，避免管道被 Windows 的 cmd.exe 吃掉

    Windows 的 cmd.exe 会把双引号内的 & 也当成命令分隔符，所以这里先把
    & 换成占位符，执行完再换回来（见 CommandWorker.run）。

    adb 本体走 `toolchain.adb_shell()`：用户没配路径时就是裸 `adb`（命令串
    要显示给用户看，保持可读），配了 platform-tools 才换成全路径。
    """
    text = (command or "").strip()
    if not text:
        return text

    parts = text.split(None, 1)
    first = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if first in ("adb", "adb.exe"):
        return "{} {}".format(toolchain.adb_shell(), rest).strip()
    if first in ("fastboot", "fastboot.exe"):
        return "{} {}".format(toolchain.fastboot_shell(), rest).strip()

    if first not in DEVICE_COMMANDS:
        return text

    if _DEVICE_SHELL_CHARS.search(text):
        if os.name == "nt" and "&" in text:
            text = text.replace("&", _AMP_PLACEHOLDER)
        return '{} shell "{}"'.format(toolchain.adb_shell(), text)
    return "{} shell {}".format(toolchain.adb_shell(), text)


def kill_process_tree(process):
    """杀掉进程及其子进程。

    shell=True 时 Popen 拿到的是 cmd.exe，真正干活的是它的子进程
    （ping / adb / dumpsys）。只 kill cmd.exe 的话子进程还攥着 stdout
    管道，communicate() 会一直阻塞到它自己跑完——表现就是「点了停止没
    反应」，超时路径也一样卡住。所以 Windows 上用 taskkill /T 杀整棵树。
    """
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)
        else:
            process.kill()
        process.wait(timeout=3)
    except Exception:                                      # noqa: BLE001
        try:
            process.kill()
        except Exception:                                  # noqa: BLE001
            pass


class CommandWorker(QThread):
    """后台执行一条命令，避免阻塞界面。"""

    done = pyqtSignal(int, str, str)      # exit_code, output, label

    def __init__(self, command, label, timeout=CMD_TIMEOUT, parent=None):
        super().__init__(parent)
        self.command = command
        self.label = label
        self.timeout = timeout
        self._process = None
        self._stopped = False

    def run(self):
        try:
            self._process = subprocess.Popen(
                self.command.replace(_AMP_PLACEHOLDER, "&"),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                shell=True)
            out, _ = self._process.communicate(timeout=self.timeout)
            text = re.sub(r'\r+\n', '\n', out.decode(errors='replace'))
            if self._stopped:
                # 被用户停掉的命令，退出码是 kill 留下的（Windows 上是 1），
                # 直接透出去会被当成「命令失败」，这里统一报 -1
                self.done.emit(-1, text.rstrip() + "\n[已停止]", self.label)
            else:
                self.done.emit(self._process.returncode, text, self.label)
        except subprocess.TimeoutExpired:
            self._kill()
            self.done.emit(-1, f"[超时] 命令 {self.timeout}s 未返回: {self.command}",
                           self.label)
        except Exception as exc:                       # noqa: BLE001
            self.done.emit(-1, f"[错误] {exc}", self.label)

    def _kill(self):
        """杀掉命令，Windows 上要连子进程一起杀，理由见 kill_process_tree。"""
        kill_process_tree(self._process)

    def stop(self):
        self._stopped = True
        self._kill()
        self.quit()
        self.wait(1500)


class ResultPanel(QWidget):
    """命令结果面板（在常用工具页里放右侧，纵向铺满）。

    「停止」不是装饰：dumpsys / logcat -d 这类命令在慢设备上能跑满超时，
    没有停止按钮用户只能干等 25 秒。停止走 CommandRunner.stop_all()，
    由面板把请求转出去（面板自己不知道 worker 在哪）。
    """

    stop_requested = pyqtSignal()
    export_requested = pyqtSignal()

    def __init__(self, title="执行结果", parent=None, max_lines=2000):
        super().__init__(parent)
        self._running = False
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        card = W.Card(title)
        self.status_label = W.heading("就绪", card)
        card.add_trailing(self.status_label)

        self.view = QPlainTextEdit(card)
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setFont(theme.mono_font(9))
        self.view.setMaximumBlockCount(max_lines)
        self.view.setMinimumHeight(120)
        self.view.setPlaceholderText("命令输出会显示在这里…")
        card.add(self.view, 1)

        buttons = card.add_row()
        self.copy_btn = W.soft_button("复制", None, card)
        self.copy_btn.setToolTip("把面板里的全部内容复制到剪贴板")
        self.copy_btn.clicked.connect(self.copy_all)
        buttons.addWidget(self.copy_btn)

        self.export_btn = W.soft_button("导出", None, card)
        self.export_btn.setToolTip("把本次会话（命令 + 输出）存成 txt")
        self.export_btn.clicked.connect(self.export_requested.emit)
        buttons.addWidget(self.export_btn)

        buttons.addStretch()
        self.stop_btn = W.danger_button("停止", None, card)
        self.stop_btn.setToolTip("中断正在执行的命令")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._request_stop)
        buttons.addWidget(self.stop_btn)

        layout.addWidget(card, 1)

    # ---------- 输出 ----------

    def clear(self):
        self.view.clear()
        self.status_label.setText("就绪")

    def set_running(self, label):
        self._running = True
        self.status_label.setText(f"执行中：{label}")
        self.stop_btn.setEnabled(True)

    def _request_stop(self):
        self.stop_btn.setEnabled(False)
        self.status_label.setText("正在停止…")
        self.stop_requested.emit()

    def append_command(self, command, label=None):
        if self.view.blockCount() > 1 or self.view.toPlainText().strip():
            self.view.appendPlainText("")
        self.view.appendPlainText(f"$ {command}" + (f"    # {label}" if label else ""))

    def append_result(self, exit_code, output, label=None):
        self._running = False
        self.stop_btn.setEnabled(False)
        text = (output or "").rstrip()
        if text:
            self.view.appendPlainText(text)
        if exit_code == 0:
            self.status_label.setText(f"完成：{label}" if label else "完成")
        elif exit_code == -1:
            self.status_label.setText(f"已停止：{label}" if label else "已停止")
            self.view.appendPlainText("[已停止]")
        else:
            self.status_label.setText(f"退出码 {exit_code}：{label}" if label else
                                      f"退出码 {exit_code}")
            self.view.appendPlainText(f"[退出码 {exit_code}]")
        self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum())

    def copy_all(self):
        text = self.view.toPlainText()
        if text.strip():
            QApplication.clipboard().setText(text)
            return True
        return False

    def session_text(self, title="执行结果"):
        """给「导出」用：带时间戳头的纯文本。"""
        from datetime import datetime
        body = self.view.toPlainText().rstrip()
        header = "# {} 会话记录\n# 导出时间：{}\n\n".format(
            title, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return header + body + "\n"


class CommandRunner(QWidget):
    """把执行 + 展示打包在一起，供模块直接调用。

    用法：
        self.runner = CommandRunner()
        self.runner.run("adb devices", "列出设备")
    """

    def __init__(self, parent=None, title="执行结果", show_panel=True):
        super().__init__(parent)
        self._workers = []
        self._pending = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.panel = None
        if show_panel:
            self.panel = ResultPanel(title, self)
            self.panel.stop_requested.connect(self.stop_all)
            self.panel.export_requested.connect(self.export_session)
            layout.addWidget(self.panel)

    # ---------- 执行 ----------

    def run(self, command, label=None, echo=True, on_result=None):
        """执行一条命令。

        command 可以说设备端命令（dumpsys battery），会自动补 adb shell 前缀；
        on_result: 可选回调 on_result(exit_code, output)，用于模块解析输出。
        """
        label = label or command
        full_command = device_cmd(command)
        self.last_command = full_command
        if self.panel is not None:
            if echo:
                self.panel.append_command(full_command, label)
            self.panel.set_running(label)

        worker = CommandWorker(full_command, label, parent=self)
        if on_result is not None:
            worker.done.connect(on_result)
        worker.done.connect(self._on_done)
        worker.finished.connect(lambda w=worker: self._cleanup(w))
        self._workers.append(worker)
        worker.start()
        return worker

    def run_sequence(self, commands, label=None):
        """顺序执行多条命令，结果依次写入面板。"""
        for index, command in enumerate(commands):
            is_last = index == len(commands) - 1
            step_label = label if is_last else None
            self.run(command, step_label)

    def _on_done(self, exit_code, output, label):
        if self.panel is not None:
            self.panel.append_result(exit_code, output, label)
        self._notify(exit_code, output, label)

    def _cleanup(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)

    # ---------- 通知宿主 ----------

    def _notify(self, exit_code, output, label):
        window = self.window()
        if hasattr(window, 'toast'):
            if exit_code == 0:
                window.toast(f"{label} 完成", "success")
            elif exit_code == -1:
                window.toast(f"{label} 已停止", "warning")
            else:
                window.toast(f"{label} 失败（退出码 {exit_code}）", "error")

    def busy(self):
        return any(w.isRunning() for w in self._workers)

    def stop_all(self):
        stopped = False
        for worker in list(self._workers):
            if worker.isRunning():
                worker.stop()
                stopped = True
        self._workers.clear()
        return stopped

    # ---------- 导出 ----------

    def export_session(self):
        """把本次会话（命令 + 输出）存成 txt，方便贴进问题单。"""
        from datetime import datetime

        from PyQt5.QtWidgets import QFileDialog

        if self.panel is None:
            return None
        text = self.panel.session_text()
        if not text.strip():
            self._toast("面板里还没有内容可导出", "warning")
            return None

        default_name = "session_{}.txt".format(datetime.now().strftime("%Y%m%d-%H%M%S"))
        path, _ = QFileDialog.getSaveFileName(
            self, "导出执行会话", default_name, "文本文件 (*.txt)")
        if not path:
            return None
        try:
            # utf-8-sig：Windows 记事本不加 BOM 会把中文显示成乱码
            with open(path, "w", encoding="utf-8-sig") as handle:
                handle.write(text)
        except Exception as exc:                           # noqa: BLE001
            self._toast(f"导出失败：{exc}", "error")
            return None
        self._toast(f"已导出到 {os.path.basename(path)}", "success")
        return path

    def _toast(self, message, kind="info"):
        window = self.window()
        if hasattr(window, 'toast'):
            window.toast(message, kind)


class ModuleRunnerMixin:
    """给模块混入一个懒加载的 runner。

    模块自己管结果面板（放在模块内部），不需要时传 show_panel=False
    就退化成"只执行不展示"。
    """

    def runner_for(self, title="执行结果", show_panel=True):
        runner = getattr(self, "_runner", None)
        if runner is None:
            runner = CommandRunner(self, title=title, show_panel=show_panel)
            self._runner = runner
        return runner

    def run_command(self, command, label=None):
        return self.runner_for().run(command, label)

    def stop_background(self):
        runner = getattr(self, "_runner", None)
        if runner is not None:
            runner.stop_all()
