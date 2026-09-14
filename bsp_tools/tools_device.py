"""常用工具 · 设备信息看板

一次性拉取设备型号、系统版本、屏幕参数、存储内存、温度电量等信息，
用指标卡展示，并支持复制摘要 / 导出 Markdown 报告。
"""

import os
import re
import subprocess
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPlainTextEdit, QFileDialog, QLabel, QApplication)

import theme
import toolchain
import ui_widgets as W


QUERIES = [
    ("型号", "getprop ro.product.model"),
    ("品牌", "getprop ro.product.brand"),
    ("系统版本", "getprop ro.build.version.release"),
    ("SDK", "getprop ro.build.version.sdk"),
    ("构建指纹", "getprop ro.build.fingerprint"),
    ("内核版本", "uname -r"),
    ("屏幕分辨率", "wm size"),
    ("屏幕密度", "wm density"),
    ("刷新率", "dumpsys display | grep -m1 -o 'fps=[0-9.]*'"),
    ("CPU 温度", "cat /sys/class/thermal/thermal_zone0/temp"),
    ("电池", "dumpsys battery"),
    ("内存", "cat /proc/meminfo"),
    ("存储", "df /data"),
    ("运行时长", "cat /proc/uptime"),
    ("Panel", "getprop ro.product.display"),
]

TEMP_WARN = 55.0
TEMP_BAD = 70.0


class QueryWorker(QThread):
    """串行执行多条 adb 命令，逐条回传结果。"""

    result = pyqtSignal(str, str)   # key, output
    done = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, queries, parent=None):
        super().__init__(parent)
        self.queries = queries
        self._stop = False

    def run(self):
        for key, command in self.queries:
            if self._stop:
                break
            try:
                out = subprocess.run(
                    f'{toolchain.adb_shell()} shell "{command}"', shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    timeout=12).stdout.decode(errors='replace')
            except subprocess.TimeoutExpired:
                out = "(超时)"
            except Exception as e:
                self.failed.emit(f"{key}: {e}")
                continue
            self.result.emit(key, out.strip())
        self.done.emit()

    def stop(self):
        self._stop = True


class DeviceInfoSection(QWidget):
    """设备信息看板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._values = {}
        self._build_ui()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        bar = W.Card("设备概览")
        row = bar.add_row()
        self.refresh_btn = W.accent_button("刷新信息", "refresh", bar)
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)

        self.copy_btn = W.soft_button("复制摘要", "file", bar)
        self.copy_btn.clicked.connect(self.copy_summary)
        row.addWidget(self.copy_btn)

        self.export_btn = W.soft_button("导出报告", "download", bar)
        self.export_btn.clicked.connect(self.export_report)
        row.addWidget(self.export_btn)

        row.addStretch()
        self.status_label = QLabel("尚未刷新", bar)
        self.status_label.setStyleSheet(
            f"color: {theme.TEXT_FAINT}; font-size: 12px; background: transparent;")
        row.addWidget(self.status_label)
        layout.addWidget(bar)

        # ---- 指标卡 ----
        cards_card = W.Card("关键指标")
        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(10)
        cards_card.add_layout(self.stats_grid)

        self.cards = {}
        stat_defs = [
            ("model", "型号", ""),
            ("android", "系统版本", ""),
            ("kernel", "内核版本", ""),
            ("resolution", "分辨率", ""),
            ("density", "屏幕密度", ""),
            ("fps", "刷新率", " Hz"),
            ("temp", "CPU 温度", " °C"),
            ("battery", "电量", " %"),
            ("memory", "内存占用", " %"),
            ("storage", "Data 占用", " %"),
            ("uptime", "运行时长", ""),
            ("panel", "Panel", ""),
        ]
        for index, (key, label, unit) in enumerate(stat_defs):
            card = W.StatCard(label, "--", unit, cards_card)
            self.cards[key] = card
            self.stats_grid.addWidget(card, index // 4, index % 4)
        for col in range(4):
            self.stats_grid.setColumnStretch(col, 1)
        layout.addWidget(cards_card)

        # ---- 原始输出 ----
        raw_card = W.Card("原始输出")
        raw_copy = W.soft_button("复制", None, raw_card)
        raw_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self.raw_view.toPlainText()))
        raw_card.add_trailing(raw_copy)
        self.raw_view = QPlainTextEdit(raw_card)
        self.raw_view.setObjectName("logView")
        self.raw_view.setReadOnly(True)
        self.raw_view.setFont(theme.mono_font(9))
        self.raw_view.setPlaceholderText("点击「刷新信息」后在此查看原始返回…")
        self.raw_view.setMinimumHeight(120)
        raw_card.add(self.raw_view, 1)
        layout.addWidget(raw_card, 1)

    # ================= 数据抓取 =================

    def refresh(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("读取中…")
        self._values = {}
        self.raw_view.clear()

        worker = QueryWorker(QUERIES, self)
        worker.result.connect(self._on_result)
        worker.failed.connect(self._on_failed)
        worker.done.connect(self._on_done)
        # 线程结束后清掉引用，避免 QThread 在运行中被回收
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_worker_finished(self):
        self._worker = None

    def _on_result(self, key, output):
        self._values[key] = output
        self.raw_view.appendPlainText(f"── {key}\n{output}\n")
        self._apply(key, output)

    def _on_failed(self, message):
        self.raw_view.appendPlainText(f"[错误] {message}")

    def _on_done(self):
        self.refresh_btn.setEnabled(True)
        connected = bool(self._values.get("型号"))
        if connected:
            self.status_label.setText(f"更新于 {datetime.now():%H:%M:%S}")
        else:
            self.status_label.setText("未获取到设备信息，请确认 adb 连接")
        window = self.window()
        if hasattr(window, 'set_device_status'):
            window.set_device_status(
                f"设备：{self._values.get('型号') or '未连接'}", connected)

    # ================= 解析 =================

    def _apply(self, key, output):
        if key == "型号":
            self.cards["model"].set_value(output.splitlines()[0][:28] if output else "--",
                                          "ok" if output else "bad")
        elif key == "系统版本":
            sdk = self._values.get("SDK", "")
            self.cards["android"].set_value(
                f"{output}" + (f" (API {sdk})" if sdk else ""))
        elif key == "内核版本":
            self.cards["kernel"].set_value(output[:22] if output else "--")
        elif key == "屏幕分辨率":
            match = re.search(r"(\d+x\d+)", output)
            self.cards["resolution"].set_value(match.group(1) if match else output[:18])
        elif key == "屏幕密度":
            match = re.search(r"(\d+)", output)
            self.cards["density"].set_value(match.group(1) if match else "--")
        elif key == "刷新率":
            match = re.search(r"fps=([\d.]+)", output)
            self.cards["fps"].set_value(match.group(1) if match else "--")
        elif key == "CPU 温度":
            self._apply_temp(output)
        elif key == "电池":
            self._apply_battery(output)
        elif key == "内存":
            self._apply_memory(output)
        elif key == "存储":
            self._apply_storage(output)
        elif key == "运行时长":
            self._apply_uptime(output)
        elif key == "Panel":
            self.cards["panel"].set_value(output[:20] or "--")

    def _apply_temp(self, output):
        try:
            millis = float(re.search(r"(\d+)", output).group(1))
            temp = millis / 1000.0 if millis > 1000 else millis
        except Exception:
            self.cards["temp"].set_value("--", "muted")
            return
        tone = "bad" if temp >= TEMP_BAD else ("warn" if temp >= TEMP_WARN else "ok")
        self.cards["temp"].set_value(f"{temp:.1f}", tone)

    def _apply_battery(self, output):
        match = re.search(r"level:\s*(\d+)", output)
        level = int(match.group(1)) if match else None
        tone = None
        if level is not None:
            tone = "bad" if level <= 15 else ("warn" if level <= 30 else "ok")
        self.cards["battery"].set_value(str(level) if level is not None else "--", tone)

    def _apply_memory(self, output):
        def kb(name):
            m = re.search(rf"{name}:\s*(\d+)", output)
            return int(m.group(1)) if m else 0
        total, available = kb("MemTotal"), kb("MemAvailable")
        if total:
            used = (total - available) / total * 100
            tone = "bad" if used >= 90 else ("warn" if used >= 75 else "ok")
            self.cards["memory"].set_value(f"{used:.0f}", tone)

    def _apply_storage(self, output):
        # df 有时只输出一行数据（overlay 挂载时为两行：Filesystem + /data），
        # 因此逐行倒着找第一行含百分比的记录，而不是硬性要求两行。
        for line in reversed([ln for ln in output.splitlines() if ln.strip()]):
            percent_text = next(
                (tok for tok in line.split() if tok.endswith('%')), None)
            if percent_text is None:
                continue
            try:
                percent = int(percent_text.rstrip('%'))
            except ValueError:
                continue
            tone = "bad" if percent >= 90 else ("warn" if percent >= 75 else "ok")
            self.cards["storage"].set_value(str(percent), tone)
            return

    def _apply_uptime(self, output):
        try:
            seconds = float(output.split()[0])
        except (IndexError, ValueError):
            return
        hours, minutes = divmod(int(seconds) // 60, 60)
        days, hours = divmod(hours, 24)
        text = f"{days}d{hours}h" if days else f"{hours}h{minutes}m"
        self.cards["uptime"].set_value(text)

    # ================= 导出 =================

    def summary_lines(self):
        if not self._values:
            return []
        pairs = [
            ("型号", "型号"), ("品牌", "品牌"), ("系统版本", "系统版本"),
            ("构建指纹", "构建指纹"), ("内核版本", "内核版本"),
            ("Panel", "Panel"), ("屏幕分辨率", "屏幕分辨率"), ("屏幕密度", "屏幕密度"),
            ("刷新率", "刷新率"), ("CPU 温度", "CPU 温度"), ("运行时长", "运行时长"),
        ]
        lines = []
        for title, key in pairs:
            value = self._values.get(key)
            if value:
                lines.append(f"{title}: {value.splitlines()[0]}")
        return lines

    def copy_summary(self):
        lines = self.summary_lines()
        if not lines:
            return
        QApplication.clipboard().setText("\n".join(lines))

    def export_report(self):
        if not self._values:
            return
        default = os.path.join(
            os.path.expanduser("~"),
            f"device_report_{datetime.now():%Y%m%d_%H%M%S}.md")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出设备报告", default, "Markdown (*.md);;文本文件 (*.txt)")
        if not path:
            return
        lines = ["# 设备信息报告", "",
                 f"导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}", ""]
        for title, _command in QUERIES:
            value = self._values.get(title)
            if value:
                lines.append(f"## {title}\n```\n{value}\n```\n")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
        except Exception:
            return
        window = self.window()
        if hasattr(window, 'toast'):
            window.toast(f"设备报告已导出到 {path}", "success")

    def on_page_shown(self):
        if not self._values and (self._worker is None or not self._worker.isRunning()):
            self.refresh()

    def stop(self):
        """停止抓取（窗口关闭前调用）：置停止位并等待线程真正结束。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(4000)
