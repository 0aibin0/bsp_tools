"""常用工具 · 性能 / 稳定性监控

定时采样 CPU 负载、内存占用、温度、电量、帧率与磁盘占用，绘制趋势曲线，
并统计掉帧与采样异常，用于长时间压测时快速判断设备状态。
"""

import re

from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QComboBox, QCheckBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QLabel, QAbstractItemView)

import theme
import toolchain
import ui_widgets as W


SAMPLE_COMMAND = (
    "echo CPU:$(cat /proc/loadavg); "
    "echo MEM:$(cat /proc/meminfo | head -3 | tr '\\n' ' '); "
    "echo TEMP:$(cat /sys/class/thermal/thermal_zone0/temp); "
    "echo BAT:$(dumpsys battery | grep level); "
    "echo FPS:$(dumpsys display | grep -m1 -o 'fps=[0-9.]*'); "
    "echo DF:$(df /data)"
)

SAMPLE_INTERVALS = [("2 秒", 2000), ("5 秒", 5000), ("10 秒", 10000)]
MAX_SAMPLES = 180

SERIES_DEFS = [
    ("cpu", "CPU Load", theme.PRIMARY),
    ("mem", "内存 %", "#7c5cff"),
    ("temp", "温度 °C", theme.DANGER),
    ("bat", "电量 %", theme.SUCCESS),
]


class TrendChart(QWidget):
    """轻量趋势图：自绘折线，避免引入额外图表依赖。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = {key: [] for key, _label, _color in SERIES_DEFS}
        self.visible = {key: True for key, _label, _color in SERIES_DEFS}
        self.setMinimumHeight(120)
        self.setStyleSheet(
            f"background: {theme.SURFACE}; border: 1px solid {theme.BORDER};"
            f" border-radius: {theme.RADIUS_SM}px;")

    def set_visible(self, key, shown):
        self.visible[key] = shown
        self.update()

    def append(self, key, value):
        if value is None:
            return
        self.series[key].append(value)
        if len(self.series[key]) > MAX_SAMPLES:
            self.series[key] = self.series[key][-MAX_SAMPLES:]

    def clear(self):
        for key in self.series:
            self.series[key] = []
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(10, 10, -10, -18)
        if rect.width() <= 10 or rect.height() <= 10:
            return

        # ---- 网格 ----
        grid_pen = QPen(QColor(theme.BORDER))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        for i in range(5):
            y = rect.top() + rect.height() * i / 4
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))

        # ---- 轴标签 ----
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_FAINT))
        for i in range(5):
            value = 100 - i * 25
            y = rect.top() + rect.height() * i / 4
            painter.drawText(int(rect.left()) + 2, int(y) - 3, f"{value}")

        values = [v for key in self.series if self.visible.get(key)
                  for v in self.series[key]]
        if not values:
            painter.setPen(QColor(theme.TEXT_FAINT))
            painter.drawText(rect, Qt.AlignCenter, "开始监控后显示趋势曲线")
            return

        total = max(len(self.series[key]) for key in self.series)
        if total < 2:
            total = 2

        def point_x(index):
            return rect.left() + rect.width() * index / (total - 1)

        def point_y(value):
            clamped = max(0.0, min(100.0, value))
            return rect.bottom() - rect.height() * clamped / 100.0

        # ---- 曲线 ----
        for key, _label, color in SERIES_DEFS:
            if not self.visible.get(key):
                continue
            data = self.series[key]
            if len(data) < 2:
                continue
            pen = QPen(QColor(color))
            pen.setWidth(2)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            offset = total - len(data)
            points = [(point_x(offset + i), point_y(v)) for i, v in enumerate(data)]
            for i in range(1, len(points)):
                painter.drawLine(
                    int(points[i - 1][0]), int(points[i - 1][1]),
                    int(points[i][0]), int(points[i][1]))


class PerfSection(QWidget):
    """性能监控面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._running = False
        self.samples = []
        self.total_frames_gap = 0.0
        self.anomalies = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sample)
        self._build_ui()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---- 控制栏 ----
        bar = W.Card("采样控制")
        row = bar.add_row()

        self.start_btn = W.accent_button("开始监控", "activity", bar)
        self.start_btn.clicked.connect(self.toggle)
        row.addWidget(self.start_btn)

        self.reset_btn = W.soft_button("清空数据", "trash", bar)
        self.reset_btn.clicked.connect(self.reset)
        row.addWidget(self.reset_btn)

        row.addWidget(W.field_label("间隔", bar))
        self.interval_combo = QComboBox(bar)
        for label, _ms in SAMPLE_INTERVALS:
            self.interval_combo.addItem(label)
        self.interval_combo.setCurrentIndex(1)
        row.addWidget(self.interval_combo)

        row.addStretch()
        self.status_label = QLabel("未开始", bar)
        self.status_label.setStyleSheet(
            f"color: {theme.TEXT_FAINT}; font-size: 12px; background: transparent;")
        row.addWidget(self.status_label)

        # 曲线开关单独一行：和上方按钮挤在一行会把模块撑到 900px 以上
        series_row = bar.add_row()
        series_row.addWidget(W.field_label("曲线", bar))
        self.series_checks = {}
        for key, label, color in SERIES_DEFS:
            check = QCheckBox(label, bar)
            check.setChecked(True)
            check.setStyleSheet(f"color: {color}; font-weight: 600;")
            check.stateChanged.connect(
                lambda state, k=key: self.chart.set_visible(k, state == Qt.Checked))
            self.series_checks[key] = check
            series_row.addWidget(check)
        series_row.addStretch()
        layout.addWidget(bar)

        # ---- 指标卡 ----
        stats_card = W.Card("实时指标")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards = {}
        card_defs = [
            ("cpu", "CPU 负载", ""),
            ("mem", "内存", " %"),
            ("temp", "温度", " °C"),
            ("bat", "电量", " %"),
            ("fps", "帧率", " fps"),
            ("df", "Data", " %"),
            ("gap", "掉帧", " 帧"),
            ("samples", "采样点", ""),
        ]
        for index, (key, label, unit) in enumerate(card_defs):
            card = W.StatCard(label, "--", unit, stats_card)
            self.cards[key] = card
            grid.addWidget(card, index // 4, index % 4)
        for col in range(4):
            grid.setColumnStretch(col, 1)
        stats_card.add_layout(grid)
        layout.addWidget(stats_card)

        # ---- 趋势图 ----
        chart_card = W.Card("趋势")
        chart_card.add_trailing(W.heading("最多保留 180 个采样点", chart_card))
        self.chart = TrendChart(chart_card)
        chart_card.add(self.chart, 1)
        layout.addWidget(chart_card, 3)

        # ---- 历史 ----
        history_card = W.Card("采样记录")
        self.table = QTableWidget(0, 7, history_card)
        self.table.setHorizontalHeaderLabels(
            ["时间", "CPU", "内存 %", "温度 °C", "电量 %", "帧率", "Data %"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(96)
        history_card.add(self.table, 1)
        layout.addWidget(history_card, 2)

    # ================= 采样 =================

    def toggle(self):
        if self._running:
            self.stop()
        else:
            self.start()

    def start(self):
        self._running = True
        self.start_btn.setText("停止监控")
        self.start_btn.setProperty("accent", False)
        self.start_btn.setProperty("danger", True)
        self._restyle(self.start_btn)
        interval = SAMPLE_INTERVALS[self.interval_combo.currentIndex()][1]
        self._timer.start(interval)
        self._sample()

    def stop(self):
        self._running = False
        self._timer.stop()
        self.start_btn.setText("开始监控")
        self.start_btn.setProperty("danger", False)
        self.start_btn.setProperty("accent", True)
        self._restyle(self.start_btn)
        self.status_label.setText(f"已停止 · 共 {len(self.samples)} 个采样点")

    @staticmethod
    def _restyle(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def reset(self):
        self.samples = []
        self.total_frames_gap = 0.0
        self.anomalies = 0
        self.chart.clear()
        self.table.setRowCount(0)
        for card in self.cards.values():
            card.set_value("--", "muted")
        self.status_label.setText("已清空")

    def _sample(self):
        from PyQt5.QtCore import QProcess
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            return
        self._process = QProcess(self)
        program, args = toolchain.adb_program_args(["shell", SAMPLE_COMMAND])
        self._process.setProgram(program)
        self._process.setArguments(args)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.finished.connect(self._on_sample_done)
        self._process.start()
    def _on_sample_done(self, _code, _status):
        if self._process is None:
            return
        output = bytes(self._process.readAllStandardOutput()).decode(errors='replace')
        sample = self._parse(output)
        if sample is None:
            self.anomalies += 1
            connected = self.anomalies < 3
            self.status_label.setText(
                "读取失败，请确认 adb 连接" if not connected else "等待设备…")
            if self.anomalies >= 3 and self._running:
                self.stop()
            return

        self.anomalies = 0
        self.samples.append(sample)
        if len(self.samples) > MAX_SAMPLES:
            self.samples = self.samples[-MAX_SAMPLES:]

        for key, _label, _color in SERIES_DEFS:
            self.chart.append(key, sample.get(key))
        self.chart.update()

        self._update_cards(sample)
        self._append_table(sample)
        self.status_label.setText(
            f"监控中 · {len(self.samples)} 个采样点 · 掉帧累计 "
            f"{self.total_frames_gap:.0f} 帧")

    # ================= 解析 =================

    def _parse(self, output):
        if not output.strip():
            return None
        sample = {
            "time": self._now(),
            "cpu": None, "mem": None, "temp": None,
            "bat": None, "fps": None, "df": None,
        }

        load = re.search(r"CPU:\s*([\d.]+)", output)
        if load:
            sample["cpu"] = min(float(load.group(1)) * 100.0, 100.0 * 4)

        mem_total = re.search(r"MemTotal:\s*(\d+)", output)
        mem_avail = re.search(r"MemAvailable:\s*(\d+)", output)
        if mem_total and mem_avail:
            total = int(mem_total.group(1))
            available = int(mem_avail.group(1))
            if total:
                sample["mem"] = (total - available) / total * 100.0

        temp = re.search(r"TEMP:\s*(\d+)", output)
        if temp:
            raw = float(temp.group(1))
            sample["temp"] = raw / 1000.0 if raw > 1000 else raw

        bat = re.search(r"level:\s*(\d+)", output)
        if bat:
            sample["bat"] = float(bat.group(1))

        fps = re.search(r"FPS:\s*fps=([\d.]+)", output)
        if fps:
            sample["fps"] = float(fps.group(1))

        df_lines = [ln for ln in output.splitlines() if ln.startswith('/data') or ' /data' in ln]
        if df_lines:
            parts = df_lines[-1].split()
            try:
                sample["df"] = float(parts[4].rstrip('%'))
            except (IndexError, ValueError):
                pass

        if all(sample[k] is None for k in ("cpu", "mem", "temp", "bat", "fps", "df")):
            return None
        return sample

    @staticmethod
    def _now():
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def _update_cards(self, sample):
        cpu = sample.get("cpu")
        if cpu is not None:
            load1 = cpu / 100.0
            tone = "bad" if load1 >= 3.0 else ("warn" if load1 >= 1.5 else "ok")
            self.cards["cpu"].set_value(f"{load1:.2f}", tone)

        mem = sample.get("mem")
        if mem is not None:
            tone = "bad" if mem >= 90 else ("warn" if mem >= 75 else "ok")
            self.cards["mem"].set_value(f"{mem:.0f}", tone)

        temp = sample.get("temp")
        if temp is not None:
            tone = "bad" if temp >= 70 else ("warn" if temp >= 55 else "ok")
            self.cards["temp"].set_value(f"{temp:.1f}", tone)

        bat = sample.get("bat")
        if bat is not None:
            tone = "bad" if bat <= 15 else ("warn" if bat <= 30 else "ok")
            self.cards["bat"].set_value(f"{bat:.0f}", tone)

        fps = sample.get("fps")
        if fps is not None:
            self.cards["fps"].set_value(f"{fps:.0f}", "ok" if fps >= 55 else "warn")
            if fps < 55:
                self.total_frames_gap += (60.0 - fps)
            self.cards["gap"].set_value(f"{self.total_frames_gap:.0f}",
                                        "bad" if self.total_frames_gap > 120 else
                                        ("warn" if self.total_frames_gap > 30 else "ok"))
        df = sample.get("df")
        if df is not None:
            tone = "bad" if df >= 90 else ("warn" if df >= 75 else "ok")
            self.cards["df"].set_value(f"{df:.0f}", tone)

        self.cards["samples"].set_value(str(len(self.samples)))

    def _append_table(self, sample):
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            sample.get("time", ""),
            f"{sample['cpu'] / 100.0:.2f}" if sample.get("cpu") is not None else "--",
            f"{sample['mem']:.0f}" if sample.get("mem") is not None else "--",
            f"{sample['temp']:.1f}" if sample.get("temp") is not None else "--",
            f"{sample['bat']:.0f}" if sample.get("bat") is not None else "--",
            f"{sample['fps']:.0f}" if sample.get("fps") is not None else "--",
            f"{sample['df']:.0f}" if sample.get("df") is not None else "--",
        ]
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)
        self.table.scrollToBottom()
        while self.table.rowCount() > MAX_SAMPLES:
            self.table.removeRow(0)

    def on_page_shown(self):
        if not self.samples:
            self.status_label.setText("未开始 · 点击「开始监控」采集数据")

    def stop_sampling(self):
        self.stop()
        # 采样用的 QProcess 也要收掉，否则退出时会报
        # "QProcess: Destroyed while process is still running"
        process = getattr(self, "_process", None)
        if process is not None:
            try:
                from PyQt5.QtCore import QProcess
                if process.state() != QProcess.NotRunning:
                    process.kill()
                    process.waitForFinished(1500)
            except Exception:
                pass