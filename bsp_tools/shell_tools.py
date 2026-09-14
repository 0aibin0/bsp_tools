import os
import re
import sys
import subprocess

from PyQt5.QtCore import QProcess, QUrl, QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QComboBox, QMessageBox, QFileDialog, QInputDialog,
                             QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QWidget)

import app_config
import theme
import toolchain
from command_runner import kill_process_tree
from ui_shell_tools import Ui_ShellTools
from base_tool_page import BaseToolPage

DEFAULT_SCRCPY = r"D:\01_tools\scrcpy-win64-v2.6.1\scrcpy.exe"
DEFAULT_APK = r"D:\00_project\lcm_test_apk\Display-Tester_1.apk"
CMD_TIMEOUT = 30

# 右侧 Log 面板的固定默认宽度（分隔条分配值）。
# 分组框左右各 23px 内边距，286 - 46 = 240px —— 里面文本框实测就是 240，
# 和常用工具页「执行结果」面板（270 → 文本框 240）是同一个约定。
LOG_PANEL_WIDTH = 286


class CommandThread(QThread):
    finished = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, command, timeout=CMD_TIMEOUT, parent=None):
        super().__init__(parent)
        self.command = command
        self.timeout = timeout
        self._process = None

    def run(self):
        try:
            self._process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
            )
            out, _ = self._process.communicate(timeout=self.timeout)
            out = out.decode(errors='replace')
            out = re.sub(r'\r+\n', r'\n', out)
            self.finished.emit(self._process.returncode, out)
        except subprocess.TimeoutExpired:
            self._kill()
            self.error.emit(f"命令超时 ({self.timeout}s): {self.command}")
        except FileNotFoundError:
            self.error.emit(f"命令未找到: {self.command.split()[0]}")
        except Exception as e:
            self.error.emit(f"执行异常: {str(e)}")

    def kill(self):
        self._kill()
        self.quit()
        self.wait(2000)

    def _kill(self):
        # 必须连子进程一起杀：shell=True 时只杀 cmd.exe 的话，
        # 子进程还攥着管道，communicate() 会一直阻塞到它自己跑完
        kill_process_tree(self._process)


class StreamThread(QThread):
    """后台流式执行命令，逐行输出"""
    output_line = pyqtSignal(str)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self._process = None
        self._running = False

    def run(self):
        try:
            self._process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
            )
            self._running = True
            for line in iter(self._process.stdout.readline, b''):
                if not self._running:
                    break
                self.output_line.emit(line.decode(errors='replace'))
            self._process.stdout.close()
            self.finished.emit(self._process.wait())
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        # 同 CommandThread._kill：dmesg -w / logcat 这类流式命令必须杀进程树
        self._running = False
        kill_process_tree(self._process)


class ShellToolsPage(BaseToolPage, Ui_ShellTools):
    def __init__(self, parent=None):
        super(ShellToolsPage, self).__init__(parent)

        # 页面整体套一层滚动区：窗口被缩得比内容最小尺寸还小时，
        # 出现滚动条而不是把控件压到互相重叠。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(self.scroll)

        self.content = QWidget()
        self.scroll.setWidget(self.content)
        self.setupUi(self.content)

        self._busy = False
        self._threads = []
        self._pending_callback = None

        self._setup_textbrowser_style()
        self._setup_partitions()
        self._setup_printk()
        self._setup_connections()
        self.load_config()

    def _setup_textbrowser_style(self):
        self.textBrowser.setObjectName("logView")
        self.textBrowser.setFont(theme.mono_font(10))

    def _setup_partitions(self):
        partitions = ['uboot_a', 'uefi_a', 'xbl_config_a', 'dcp_a',
                      'aop_config_a', 'dtbo_a']
        self.flash_partition.addItems(partitions)
        self.flash_partition.setCurrentText('')

    def _setup_printk(self):
        for i in range(9):
            self.debug_printk_level.addItem(str(i))
        self.debug_printk_level.setCurrentText('8')

    def _setup_connections(self):
        # adb（devices / root / debugfs / reboot 四个按钮已按 func-list 精简）
        self.adb_remount.clicked.connect(self.on_remount)
        self.adb_wm_size.clicked.connect(self.on_wm_size)
        self.adb_cmdline.clicked.connect(self.on_cmdline)
        self.adb_dumpsys.clicked.connect(self.on_dumpsys)
        self.adb_deviceinfo.clicked.connect(self.on_deviceinfo)
        # Download Mode
        self.dl_autodloader.clicked.connect(self.adbrebootautodloader_fun)
        self.dl_edl.clicked.connect(self.on_edl)
        # ylog
        self.pushButton_5.clicked.connect(self.ylog_fun)
        self.ylogpath.setPlaceholderText(r"默认路径为D:\Desktop\allylog")
        # fastboot flash
        self.flash_browse.clicked.connect(self.on_flash_browse)
        self.flash_btn.clicked.connect(self.on_flash)
        self.fb_mode.clicked.connect(self.adbrebootbootloader)
        self.fb_reboot.clicked.connect(self.fastbootreboot)
        # func（背光滑块与 pull 按钮已移除：pull 与侧边栏「截图并保存」重复）
        self.func_power.clicked.connect(self.on_power)
        self.func_screencap.clicked.connect(self.on_screencap)
        self.func_rec_start.clicked.connect(self.on_rec_start)
        self.func_rec_stop.clicked.connect(self.on_rec_stop)
        self.gpio_check.clicked.connect(self.on_gpio_check)
        self.gpio_num.returnPressed.connect(self.on_gpio_check)
        # APK & Tools
        self.apk1_browse.clicked.connect(self.on_apk_browse)
        self.apk1_install.clicked.connect(self.on_apk_install)
        self.scrcpy_browse.clicked.connect(self.on_scrcpy_browse)
        self.scrcpy_start.clicked.connect(self.on_scrcpy_start)
        # Debug
        self.debug_shell_run.clicked.connect(self.on_shell_run)
        self.debug_shell_cmd.lineEdit().returnPressed.connect(self.on_shell_run)
        self.debug_shell_stop.clicked.connect(self.on_shell_stop)
        # push / pull 按钮已下线：常用工具页的「文件管理」是超集（浏览 + 上传 +
        # 下载 + 删除 + 路径书签），方法保留以便想恢复时只改 UI
        self.debug_density_get.clicked.connect(self.on_density_get)
        self.debug_density_set.clicked.connect(self.on_density_set)
        # I2C/SPI 按钮也已下线（板级一次性确认，需要时用上面的自定义命令跑）
        self.debug_printk_get.clicked.connect(self.on_printk_get)
        self.debug_printk_set.clicked.connect(self.on_printk_set)
        # Log
        self.pushButton_clear_log.clicked.connect(self.on_clear_log)
        self.pushButton_copy_log.clicked.connect(self.on_copy_log)

    # === 异步命令执行 ===

    def _set_busy(self, busy):
        self._busy = busy
        self.setCursor(Qt.WaitCursor if busy else Qt.ArrowCursor)
        window = self.window()
        if hasattr(window, 'set_busy'):
            window.set_busy(busy)
        status = getattr(self, "log_status", None)
        if status is not None:
            status.setText("执行中…" if busy else "就绪")

    # === 对外接口（供主窗口命令面板 / 常用工具页调用）===

    def notify(self, message, kind="info"):
        """通过主窗口浮层提示，非主窗口环境下静默忽略。"""
        window = self.window()
        if hasattr(window, 'toast'):
            window.toast(message, kind)

    def run_command(self, command, label=None, failure_message=None):
        """执行一条 adb 命令并把结果显示到日志区。

        供命令面板和侧边栏快捷操作复用，避免每个页面各自维护一套线程逻辑。
        设备端命令（dumpsys battery / cat /proc/... ）会自动补 adb shell 前缀，
        否则会被 Windows 当成命令执行并报「不是内部或外部命令」。
        """
        from command_runner import device_cmd

        label = label or command
        command = device_cmd(command)
        self._pending_notify = (label, failure_message or f"{label} 失败")
        self.textBrowser.clear()
        self._exec_with_result(command, f"{label} 完成")

    def check_device_connected(self):
        """查询设备连接状态，返回 (是否在线, 描述)。

        adb 可能是 PATH 里的，也可能是设置里指定的全路径（同事机器上没装
        platform-tools 时靠这个），所以统一走 toolchain。
        """
        try:
            out = subprocess.run(
                f'{toolchain.adb_shell()} devices', shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=6).stdout.decode(errors='replace')
        except Exception as e:
            return False, f"adb 不可用（{e}）"
        devices = [ln for ln in out.splitlines()[1:]
                   if ln.strip() and not ln.startswith('*')]
        if not devices:
            return False, "未连接设备"
        names = [ln.split('\t')[0].strip() for ln in devices]
        return True, f"{names[0]}" + (f" +{len(names) - 1}" if len(names) > 1 else "")

    def _on_command_done(self, exit_code, output):
        self._set_busy(False)
        label_notify = getattr(self, '_pending_notify', None)
        self._pending_notify = None
        if self._pending_callback:
            self._pending_callback(exit_code, output)
            self._pending_callback = None
        if label_notify:
            label, fail_text = label_notify
            if exit_code == 0:
                self.notify(f"{label} 完成", "success")
            else:
                self.notify(f"{fail_text}（退出码 {exit_code}）", "error")

    def _run_async(self, command, on_finish):
        self._pending_callback = on_finish
        thread = CommandThread(command, parent=self)
        thread.finished.connect(self._on_command_done)
        thread.error.connect(self._on_command_error)
        thread.finished.connect(lambda: self._cleanup_thread(thread))
        thread.error.connect(lambda msg: self._cleanup_thread(thread))
        self._threads.append(thread)
        thread.start()

    def _on_command_error(self, msg):
        self._set_busy(False)
        self.append_text(f"[错误] {msg}\n")
        self._pending_callback = None
        pending = getattr(self, '_pending_notify', None)
        self._pending_notify = None
        if pending:
            self.notify(f"{pending[0]} 失败：{msg}", "error")

    def _cleanup_thread(self, thread):
        if thread in self._threads:
            self._threads.remove(thread)

    def append_text(self, msg):
        self.textBrowser.insertPlainText(msg)
        self.textBrowser.moveCursor(QTextCursor.End)
        self._write_log(msg)

    def _write_log(self, msg):
        log_file_path = os.path.join(self._get_base_dir(), 'adb_commands.log')
        try:
            with open(log_file_path, 'a', encoding='utf-8') as f:
                f.write(msg)
        except Exception:
            pass

    def _exec_with_result(self, command, success_msg):
        if self._busy:
            return
        self._set_busy(True)
        self._last_command = command
        self.textBrowser.clear()
        self.append_text(f"执行命令: {command}\n")
        self.append_text("运行中...\n")

        def on_done(exit_code, output):
            self.textBrowser.clear()
            self.append_text(f"执行命令: {command}\n")
            self.append_text(f"结果:\n{output}\n")
            if exit_code == 0:
                self.append_text(f"{success_msg}\n")
            else:
                self.append_text(f"[警告] 命令退出码: {exit_code}\n")

        self._run_async(command, on_done)

    def _exec_chain(self, commands, success_msg):
        if self._busy:
            return
        self._set_busy(True)
        self.textBrowser.clear()
        self._commands_queue = list(commands)
        self._commands_output = []
        self._commands_success_msg = success_msg
        self.append_text("运行中...\n")
        self._run_next_in_chain()

    def _run_next_in_chain(self):
        if not self._commands_queue:
            self._set_busy(False)
            self.textBrowser.clear()
            for cmd, out in self._commands_output:
                self.append_text(f"执行命令: {cmd}\n")
                self.append_text(f"结果:\n{out}\n")
                self.append_text(f"{'-' * 40}\n")
            self.append_text(f"{self._commands_success_msg}\n")
            return

        cmd = self._commands_queue.pop(0)

        def on_done(exit_code, output):
            self._commands_output.append((cmd, output))
            self._run_next_in_chain()

        def on_error(msg):
            self._commands_output.append((cmd, f"[错误] {msg}"))
            self._run_next_in_chain()

        thread = CommandThread(cmd, parent=self)
        thread.finished.connect(on_done)
        thread.error.connect(on_error)
        thread.finished.connect(lambda: self._cleanup_thread(thread))
        thread.error.connect(lambda msg: self._cleanup_thread(thread))
        self._threads.append(thread)
        thread.start()

    # === adb 命令 ===
    #
    # 下面三个方法对应的按钮（adb devices / adb root / adb reboot）已按
    # func-list 从界面移除：设备列表与 root 在侧边栏「快捷操作」和 Ctrl+K
    # 命令面板里都有，reboot 属于危险操作不该挨着常用按钮。方法保留是为了
    # 想恢复时只改 UI 一处。

    def adbdevices_fun(self):
        self._exec_with_result('adb devices', "设备列表获取完成")

    def adbroot_fun(self):
        self._exec_with_result('adb root', "设备已进入 root 模式")

    def adbreboot_fun(self):
        self._exec_with_result('adb reboot', "设备重启成功")

    def lcmapkinstall_1(self):
        path = self.apk1_path.text().strip()
        if not path:
            QMessageBox.warning(self, "参数缺失", "请先选择 APK 路径")
            return
        self._exec_with_result(f'adb install "{path}"', "APK 安装成功")

    def adbrebootbootloader(self):
        self._exec_with_result('adb reboot bootloader', "设备已进入 bootloader 模式")

    def fastbootreboot(self):
        self._exec_with_result('fastboot reboot', "设备重启成功")

    def adbrebootautodloader_fun(self):
        self._exec_with_result('adb reboot autodloader', "设备已进入 Download 模式")

    # === func 命令 ===

    def on_power(self):
        self._exec_with_result('adb shell input keyevent 26', "电源键按下")

    def on_edl(self):
        self._exec_with_result('adb reboot edl', "设备已进入 EDL 模式")

    def on_screencap(self):
        self._exec_with_result(
            'adb shell screencap -p /sdcard/screenshot.png',
            "截图已保存到 /sdcard/screenshot.png")

    def on_sc_pull(self):
        local = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not local:
            return
        caps = [
            'adb shell screencap -p /sdcard/screenshot.png',
            f'adb pull /sdcard/screenshot.png "{local}"',
        ]
        self._exec_chain(caps, f"截图已保存到 {local}")

    # 背光滑块相关方法（_on_bl_slider / _on_bl_val_changed / on_bl_set）已按
    # func-list 移除：常用工具页的「显示调试」模块里有更完整的背光控制。

    def on_gpio_check(self):
        num = self.gpio_num.text().strip()
        if num:
            cmd = f'"cat /d/gpio | grep gpio{num}"'
        else:
            cmd = '"cat /d/gpio"'
        self._exec_with_result(f'adb shell {cmd}', "GPIO 状态获取完成")

    def on_rec_start(self):
        self._exec_with_result(
            'adb shell screenrecord /sdcard/demo.mp4 --time-limit 180',
            "录屏已启动 (最长3分钟)，点击 rec stop 停止")

    def on_rec_stop(self):
        self._exec_with_result(
            'adb shell pkill -SIGINT screenrecord',
            "录屏已停止，文件: /sdcard/demo.mp4")

    # === 配置持久化 ===
    #
    # 统一走 app_config（同一个 config.ini）。原来这里自己 new 一个
    # ConfigParser 读写，和主窗口存窗口尺寸时是两个写入者，后写的会把
    # 对方刚存的键覆盖掉。

    def _get_base_dir(self):
        return app_config.data_dir()

    def _get_config_path(self):
        return app_config.config_path()

    def load_config(self):
        config = app_config.config()
        try:
            self.ylogpath.setText(config.get('base_path', ''))
            self.ylogpath_2.setText(config.get('project', ''))
            self.ylogpath_3.setText(config.get('sub_name', ''))
            self.apk1_path.setText(config.get('apk_path', DEFAULT_APK))
            self.scrcpy_path.setText(config.get('scrcpy_path', DEFAULT_SCRCPY))
            self.flash_partition.setCurrentText(config.get('flash_partition', ''))
            self.flash_img_path.setText(config.get('flash_img', ''))
            self.debug_density_val.setText(config.get('density_val', ''))
            self.debug_printk_level.setCurrentText(config.get('printk_level', '8'))
            self.debug_shell_cmd.setCurrentText(config.get('shell_cmd', ''))
            shell_history = config.get('shell_history', '')
            if shell_history:
                for cmd in shell_history.split('\n')[:10]:
                    if cmd.strip():
                        self.debug_shell_cmd.addItem(cmd.strip())
            self.debug_shell_cmd.setCurrentText('')
        except Exception as e:
            print(f"加载配置失败: {e}")

    def save_config(self):
        app_config.config().update(
            base_path=self.ylogpath.text().strip(),
            project=self.ylogpath_2.text().strip(),
            sub_name=self.ylogpath_3.text().strip(),
            apk_path=self.apk1_path.text().strip(),
            scrcpy_path=self.scrcpy_path.text().strip(),
            flash_partition=self.flash_partition.currentText().strip(),
            flash_img=self.flash_img_path.text().strip(),
            density_val=self.debug_density_val.text().strip(),
            printk_level=self.debug_printk_level.currentText().strip(),
            shell_cmd=self.debug_shell_cmd.currentText().strip(),
            shell_history='\n'.join(
                [self.debug_shell_cmd.itemText(i)
                 for i in range(self.debug_shell_cmd.count())]),
        )

    def ylog_fun(self):
        self.save_config()
        base_path = self.ylogpath.text().strip() or r"D:\Desktop\allylog"
        project = self.ylogpath_2.text().strip()
        sub_name = self.ylogpath_3.text().strip()

        if not all([project, sub_name]):
            QMessageBox.warning(self, "参数缺失", "必须填写Project和Sub-Name")
            return

        full_path = os.path.normpath(os.path.join(base_path, project, sub_name))

        try:
            os.makedirs(full_path, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "操作失败", str(e))
            return

        if self._busy:
            return
        self._set_busy(True)
        adb_cmd = f'adb pull /data/ylog/ap "{full_path}"'
        self._last_command = adb_cmd
        self.textBrowser.clear()
        self.append_text(f"执行命令: {adb_cmd}\n")
        self.append_text("运行中...\n")

        def on_done(exit_code, output):
            self.textBrowser.clear()
            if exit_code == 0:
                try:
                    file_list = "\n".join(os.listdir(full_path)[:5])
                except Exception:
                    file_list = "(无法列出文件)"
                self.textBrowser.setOpenExternalLinks(False)
                uri_path = QUrl.fromLocalFile(full_path)
                html = (
                    f"<span style='color:green'>v</span> ylog抓取成功!<br/>"
                    f"<b>存储路径:</b><a href='{uri_path.toString()}' style='color:blue;'>"
                    f"{full_path}</a><br/>"
                    f"<b>文件列表:</b><br/>{file_list}"
                )
                self.textBrowser.setHtml(html)
                try:
                    self.textBrowser.anchorClicked.disconnect()
                except TypeError:
                    pass
                self.textBrowser.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))
            else:
                self.append_text(f"执行命令: {adb_cmd}\n")
                self.append_text(f"结果:\n{output}\n")
                self.append_text("[错误] ylog 抓取失败\n")

        self._run_async(adb_cmd, on_done)

    # === fastboot flash ===

    def on_flash_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择镜像文件", "", "All Files (*)")
        if path:
            self.flash_img_path.setText(path)
            self.save_config()
            self.flash_partition.setFocus()

    def on_flash(self):
        partition = self.flash_partition.currentText().strip()
        img_path = self.flash_img_path.text().strip()

        if not partition:
            QMessageBox.warning(self, "参数缺失", "请输入分区名")
            return
        if not img_path:
            QMessageBox.warning(self, "参数缺失", "请选择镜像文件")
            return

        self.save_config()
        erase_cmd = f'fastboot erase {partition}'
        flash_cmd = f'fastboot flash {partition} "{img_path}"'
        self._exec_chain([erase_cmd, flash_cmd], f"{partition} 烧录完成")

    # === APK & Tools ===

    def on_apk_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 APK", "", "APK Files (*.apk);;All Files (*)")
        if path:
            self.apk1_path.setText(path)
            self.save_config()

    def on_apk_install(self):
        self.lcmapkinstall_1()

    def on_scrcpy_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 scrcpy", "", "Executable (*.exe);;All Files (*)")
        if path:
            self.scrcpy_path.setText(path)
            self.save_config()

    def on_scrcpy_start(self):
        path = self.scrcpy_path.text().strip()
        if not path:
            QMessageBox.warning(self, "参数缺失", "请先选择 scrcpy 路径")
            return
        self.save_config()
        self._exec_with_result('adb devices', "设备列表获取完成")
        self.process = QProcess(self)
        self.process.start(path)

    # === Debug 命令 ===

    def on_shell_run(self):
        cmd = self.debug_shell_cmd.currentText().strip()
        if not cmd or self._busy:
            return

        idx = self.debug_shell_cmd.findText(cmd)
        if idx >= 0:
            self.debug_shell_cmd.removeItem(idx)
        self.debug_shell_cmd.insertItem(0, cmd)
        self.debug_shell_cmd.setCurrentIndex(0)
        while self.debug_shell_cmd.count() > 10:
            self.debug_shell_cmd.removeItem(10)
        self.save_config()

        self.on_shell_stop()

        self._set_busy(True)
        self.textBrowser.clear()
        self.append_text(f"> adb shell {cmd}\n")
        self.append_text(f"{'-' * 40}\n")

        shell_cmd = f'adb shell "{cmd}"'
        self._stream_thread = StreamThread(shell_cmd, self)
        self._stream_thread.output_line.connect(self._on_stream_line)
        self._stream_thread.finished.connect(self._on_stream_end)
        self._stream_thread.error.connect(self._on_stream_err)
        self._stream_thread.start()

    def _on_stream_line(self, line):
        self.append_text(line)

    def _on_stream_end(self, code):
        self.append_text(f"\n{'=' * 40}\n命令已结束 (exit={code})\n")
        self._set_busy(False)

    def _on_stream_err(self, msg):
        self.append_text(f"\n[错误] {msg}\n")
        self._set_busy(False)

    def on_shell_stop(self):
        stopped = False
        t = getattr(self, '_stream_thread', None)
        if t and t.isRunning():
            t.stop()
            t.wait(2000)
            stopped = True
        for t in self._threads:
            if t.isRunning():
                t.kill()
                stopped = True
        if stopped:
            self.append_text("\n[已手动停止]\n")
            self._set_busy(False)

    def on_logcat(self):
        self._exec_with_result('adb logcat -d', "logcat 抓取完成")

    def on_dmesg(self):
        self._exec_with_result('adb shell dmesg', "dmesg 抓取完成")

    def on_cmdline(self):
        self._exec_with_result('adb shell cat /proc/cmdline', "cmdline 获取完成")

    def on_remount(self):
        self._exec_with_result('adb remount', "remount 完成")

    def _input_with_history(self, title, label_text, history_key, placeholder='', max_items=10):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(label_text))
        combo = QComboBox()
        combo.setEditable(True)
        combo.setMinimumHeight(26)
        combo.lineEdit().setPlaceholderText(placeholder)
        history = app_config.config().get(history_key, '');
        if history:
            for item in history.split('\n')[:max_items]:
                if item.strip():
                    combo.addItem(item.strip())
        combo.setCurrentText('')
        layout.addWidget(combo)
        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        okBtn = QPushButton('确定')
        cancelBtn = QPushButton('取消')
        btnLayout.addWidget(okBtn)
        btnLayout.addWidget(cancelBtn)
        layout.addLayout(btnLayout)
        okBtn.clicked.connect(dlg.accept)
        cancelBtn.clicked.connect(dlg.reject)
        combo.lineEdit().returnPressed.connect(dlg.accept)

        if dlg.exec_() != QDialog.Accepted:
            return None

        text = combo.currentText().strip()
        if not text:
            return None
        idx = combo.findText(text)
        if idx >= 0:
            combo.removeItem(idx)
        combo.insertItem(0, text)
        while combo.count() > max_items:
            combo.removeItem(max_items)
        app_config.config().update(
            **{history_key: '\n'.join(
                [combo.itemText(i) for i in range(combo.count())])})
        return text

    def on_push(self):
        """推送文件到设备（按钮已下线，方法保留）。

        常用工具页的「文件管理」是超集：浏览设备目录 + 上传 + 下载 + 删除 +
        路径书签，还带当前目录作为上传目标。新代码请走那边。
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要推送的文件", "", "All Files (*)")
        if not path:
            return
        remote = self._input_with_history(
            "推送目标", "输入设备上的目标路径:", "device_path_history",
            "/data/local/tmp/")
        if not remote:
            return
        self._exec_with_result(f'adb push "{path}" "{remote}"', "push 完成")

    def on_wm_size(self):
        self._exec_with_result('adb shell wm size', "屏幕分辨率获取完成")

    def on_density_get(self):
        self._exec_with_result('adb shell wm density', "屏幕密度获取完成")

    def on_density_set(self):
        val = self.debug_density_val.text().strip()
        if not val:
            QMessageBox.warning(self, "参数缺失", "请输入密度值 (如 320)")
            return
        self.save_config()
        self._exec_with_result(f'adb shell wm density {val}', f"屏幕密度已设置为 {val}")

    def on_dumpsys(self):
        self._exec_with_result('adb shell dumpsys display', "显示信息获取完成")

    def on_dumpsys_input(self):
        self._exec_with_result('adb shell dumpsys input', "触摸/输入信息获取完成")

    def on_i2c_check(self):
        """检测 I2C / SPI 设备（按钮已下线，方法保留）。

        这是板级一次性确认，需要时用 Debug 卡的「自定义命令」跑同一条命令。
        """
        i2c_cmd = (
            '"echo ===== I2C Devices =====; '
            'cat /sys/bus/i2c/devices/*/name 2>/dev/null || echo no i2c; '
            'echo ===== I2C Addresses =====; '
            'ls /sys/bus/i2c/devices/ 2>/dev/null; '
            'echo ===== SPI Devices =====; '
            'ls /sys/bus/spi/devices/ 2>/dev/null || echo no spi"'
        )
        self._exec_with_result(f'adb shell {i2c_cmd}', "I2C/SPI 设备检测完成")

    def on_deviceinfo(self):
        info_cmd = (
            '"echo ===== Fingerprint =====; getprop ro.build.fingerprint; '
            'echo ===== Android =====; getprop ro.build.version.release; '
            'echo ===== Kernel =====; uname -r; '
            'echo ===== Product =====; getprop ro.product.name; '
            'echo ===== Panel =====; getprop ro.product.display; '
            'echo ===== Resolution =====; wm size; '
            'echo ===== Density =====; wm density"'
        )
        self._exec_with_result(f'adb shell {info_cmd}', "设备信息获取完成")

    def on_mount_debugfs(self):
        """挂载 debugfs（按钮已下线，方法保留；侧边栏快捷操作走的是 run_command）。"""
        self._exec_with_result('adb shell mount -t debugfs none /d', "debugfs 挂载完成")

    def on_printk_get(self):
        self._exec_with_result('adb shell cat /proc/sys/kernel/printk', "printk 等级获取完成")

    def on_printk_set(self):
        level = self.debug_printk_level.currentText().strip()
        self.save_config()
        self._exec_with_result(
            f'adb shell "echo {level} > /proc/sys/kernel/printk"',
            f"printk 等级已设置为 {level}")

    def on_pull(self):
        """从设备拉取文件（按钮已下线，方法保留，理由同 on_push）。"""
        remote = self._input_with_history(
            "拉取文件", "输入设备上的文件路径:", "device_path_history",
            "/data/local/tmp/")
        if not remote:
            return
        local = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not local:
            return
        self._exec_with_result(f'adb pull "{remote}" "{local}"', "pull 完成")

    def on_page_shown(self):
        """页面被主窗口切换到时刷新设备状态。"""
        self._apply_split_sizes()
        if not self._busy:
            ok, desc = self.check_device_connected()
            window = self.window()
            if hasattr(window, 'set_device_status'):
                window.set_device_status(f"设备：{desc}", ok)

    def showEvent(self, event):
        """页面第一次真正显示时再补一次分栏。

        为什么需要：程序会记住上次打开的页面，如果上次就停在 Shell Tools，
        那么 on_page_shown() 是在 MainWindow 构造期被调用的——那时布局还没算，
        splitter 宽度是 QSplitter 的默认值（100 左右），_apply_split_sizes()
        会因为宽度太小直接返回；而页面之后不会再触发 on_page_shown，
        日志面板就一直是 setupUi 里的兜底值。用户量到的文本框不是 240 就是这么来的。

        这里在真正 show 之后补一次；QTimer 是为了让布局先算完再量。
        """
        super().showEvent(event)
        if not getattr(self, "_split_sized", False):
            QTimer.singleShot(0, self._apply_split_sizes)

    def _apply_split_sizes(self):
        """首次真正显示时再设一次分隔比例。

        控件在 setupUi 阶段还没有真实尺寸，setSizes 会被布局重算覆盖，
        这里补一次。窗口不够宽时优先压低日志面板宽度（最小 240），
        保证左侧控制区的 2 列网格不被挤到横向滚动。
        """
        if getattr(self, "_split_sized", False):
            return
        split = getattr(self, "split", None)
        if split is None or split.width() < 200:
            return
        self._split_sized = True
        total = split.width()
        handle = split.handleWidth()
        available = total - handle
        # 日志面板固定 286px：分组框左右各有 23px 内边距，286 - 46 = 240px，
        # 正好和常用工具页「执行结果」面板（固定 270 → 文本框 240）对齐。
        #
        # 这里刻意**不按比例**：原先按可用宽度的 25% 算，窗口最大化到 1920 时
        # 会涨到 400px（文本框 354），和「240」这个约定就对不上了；而且程序会
        # 记住上次窗口尺寸，用户下次启动看到的宽度会跟着变。
        # 想加宽直接拖分隔条。
        log_width = LOG_PANEL_WIDTH
        left = available - log_width
        # 左侧至少要放得下 2 列网格（约 760），放不下时先从日志面板扣
        min_left = 760
        if left < min_left and log_width > 240:
            take = min(min_left - left, log_width - 240)
            left += take
            log_width -= take
        split.setSizes([left, log_width])

    def on_clear_log(self):
        self.textBrowser.clear()

    def on_copy_log(self):
        self.copy_to_clipboard(self.textBrowser)
