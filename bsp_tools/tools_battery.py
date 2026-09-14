"""常用工具 · 电池调试 —— **已下线**。

按 func-list.md 的标记（编号 23 = 否）本模块不再挂进常用工具页。
文件保留是为了把这一行加回 tools_page.SECTIONS（以及 _inject_runner）
就能恢复，不用翻 git 历史。

---- 以下为原说明 ----

查看电池状态、健康度、温度、电压电流，切换充电/测试模式，
以及 dumpsys batterystats 等功耗分析入口。
"""

import re
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QCheckBox, QFrame, QLabel,
                             QSizePolicy)

import theme
import ui_widgets as W
from command_runner import CommandRunner


BATTERY_QUERY = "dumpsys battery"

# 注意：这些都是「设备端」命令，不带 adb shell 前缀，
# 由 command_runner.device_cmd() 统一补全成 adb shell "..."。
POWER_QUERIES = [
    ("电池统计", "dumpsys batterystats | head -80"),
    ("功耗明细", "dumpsys batterystats --charged | head -60"),
    ("电池信息", "dumpsys battery"),
    ("充电器状态", "dumpsys charger"),
    ("电源管理", "dumpsys power | head -60"),
    ("唤醒锁", "dumpsys power | grep -i -A3 'wake lock'"),
    ("温度分区", "cat /sys/class/thermal/thermal_zone0/temp"),
    ("电流节点", "cat /sys/class/power_supply/battery/current_now"),
]

HEALTH_MAP = {1: "未知", 2: "良好", 3: "过热", 4: "已损坏",
              5: "过压", 6: "未指定故障", 7: "过冷"}

TEMP_WARN = 42.0
TEMP_BAD = 48.0


class BatterySection(QWidget):
    """电池状态与功耗分析。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.runner = CommandRunner(self, title="命令输出")
        self.samples = []
        self._build_ui()
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(5000)
        self._auto_timer.timeout.connect(self.refresh)

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_toolbar())
        self.warn_bar = self._build_warning_bar()
        layout.addWidget(self.warn_bar)
        layout.addWidget(self._build_stats())
        layout.addWidget(self._build_timeline(), 1)
        layout.addWidget(self.runner, 2)

    def _build_toolbar(self):
        card = W.Card("电池操作")

        row = card.add_row()
        self.refresh_btn = W.accent_button("刷新状态", "refresh", card)
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)

        self.auto_check = QCheckBox("每 5 秒自动刷新", card)
        self.auto_check.stateChanged.connect(self._on_auto_toggled)
        row.addWidget(self.auto_check)
        row.addStretch()
        self.status_label = W.heading("尚未读取", card)
        row.addWidget(self.status_label)

        # 充放电操作单独一行：6 个控件挤一行会把模块撑到 593px
        row2 = card.add_row()
        row2.addWidget(W.field_label("充放电", card))
        self.charge_btn = W.soft_button("恢复充电", None, card)
        self.charge_btn.clicked.connect(
            lambda: self.runner.run('dumpsys battery reset', '恢复充电'))
        row2.addWidget(self.charge_btn)

        self.discharge_btn = W.soft_button("模拟放电", None, card)
        self.discharge_btn.setToolTip("dumpsys battery unplug，仅用于功耗测试")
        self.discharge_btn.clicked.connect(
            lambda: self.runner.run('dumpsys battery unplug', '模拟放电'))
        row2.addWidget(self.discharge_btn)

        self.test_btn = W.danger_button("测试模式", None, card)
        self.test_btn.setToolTip("dumpsys battery set ac/usb 0，会真的停止充电，测试完记得恢复")
        self.test_btn.clicked.connect(self.enable_test_mode)
        row2.addWidget(self.test_btn)
        row2.addStretch()
        return card

    def _build_warning_bar(self):
        """电池服务被改过时的醒目提示。

        「模拟放电 / 测试模式」会让系统停止上报电池状态（dumpsys 里出现
        UPDATES STOPPED），这时电量会一直掉，必须 reset 才能恢复，所以给一条
        显眼的横幅 + 一键恢复，避免忘记。
        """
        bar = QFrame(self)
        bar.setObjectName("warnBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        self.stopped_label = QLabel(
            "⚠ 电池状态上报已停止（测试模式/模拟放电的副作用），电量会持续下降，"
            "请点右侧按钮恢复", bar)
        self.stopped_label.setWordWrap(True)
        self.stopped_label.setMinimumWidth(120)
        self.stopped_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(self.stopped_label, 1)

        fix_btn = W.danger_button("立即恢复", None, bar)
        fix_btn.clicked.connect(
            lambda: self.runner.run('dumpsys battery reset', '恢复充电'))
        row.addWidget(fix_btn)

        bar.setVisible(False)
        return bar
    def _build_stats(self):
        card = W.Card("电池状态")
        grid = QGridLayout()
        grid.setSpacing(10)

        self.cards = {}
        defs = [
            ("level", "电量", " %"),
            ("health", "健康度", ""),
            ("temp", "温度", " °C"),
            ("voltage", "电压/充电上限", ""),
            ("current", "电流/充电上限", ""),
            ("charging", "充电状态", ""),
            ("ac", "AC 充电", ""),
            ("usb", "USB 充电", ""),
        ]
        for index, (key, label, unit) in enumerate(defs):
            stat = W.StatCard(label, "--", unit, card)
            self.cards[key] = stat
            grid.addWidget(stat, index // 4, index % 4)
        for col in range(4):
            grid.setColumnStretch(col, 1)

        card.add_layout(grid)
        return card

    def _build_timeline(self):
        card = W.Card("采样记录")
        self.count_label = W.heading("0 条", card)
        card.add_trailing(self.count_label)

        self.table = QTableWidget(0, 6, card)
        self.table.setHorizontalHeaderLabels(
            ["时间", "电量 %", "温度 °C", "电压 mV", "电流 mA", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(140)
        card.add(self.table, 1)
        return card

    # ================= 行为 =================

    def _on_auto_toggled(self, state):
        if state == Qt.Checked:
            self._auto_timer.start()
            self.refresh()
        else:
            self._auto_timer.stop()

    def refresh(self):
        if self.runner.busy():
            return
        self.runner.run(BATTERY_QUERY, "读取电池状态", on_result=self._on_battery_result)

    def _on_battery_result(self, exit_code, output):
        if exit_code == 0:
            self._apply_dumpsys(output)

    # ================= 解析 =================

    @staticmethod
    def parse_battery(output):
        """解析 dumpsys battery 输出。"""
        value = {}

        def grab(pattern, cast=str):
            # re.M 让 ^ 匹配每一行行首，避免 "Max charging voltage" 顶替 "voltage"
            match = re.search(pattern, output, re.I | re.M)
            if not match:
                return None
            try:
                return cast(match.group(1))
            except (TypeError, ValueError):
                return None

        value["level"] = grab(r"^[ \t]*level:\s*(\d+)", int)
        health = grab(r"^[ \t]*health:\s*(\d+)", int)
        value["health"] = HEALTH_MAP.get(health, "未知") if health is not None else None
        raw_temp = grab(r"^[ \t]*temperature:\s*(-?\d+)", int)
        value["temp"] = raw_temp / 10.0 if raw_temp is not None else None

        # 必须按行首匹配：dumpsys 里还有 "Max charging voltage: 12000000"，
        # 用松散的 voltage: 会先命中它，把上限当成实时电压。
        voltage = grab(r"^[ \t]*voltage:\s*(-?\d+)", int)
        value["voltage_is_max"] = False
        if not voltage:
            # 设备不上报实时电压（平板/开发板常见，返回 0）时用充电上限兜底，
            # 并在卡片上标「上限」，避免看起来像在乱报电压
            voltage = grab(r"^[ \t]*Max charging voltage:\s*(-?\d+)", int)
            value["voltage_is_max"] = voltage is not None
        # 不同平台单位不一致：多数返回 mV（约 4000），少数返回 µV（约 4000000）。
        # 统一换算成 mV 显示，避免出现 5000000 mV 这种看着像错的数字。
        if voltage is not None and voltage > 10000:
            voltage = voltage // 1000
        value["voltage"] = voltage

        current = grab(r"^[ \t]*current now:\s*(-?\d+)", int)
        if current is None:
            current = grab(r"^[ \t]*current_now:\s*(-?\d+)", int)
        if current is None or current == 0:
            # 部分平台不报实时电流，只有充电上限；用它兜底，别让卡片空着
            fallback = grab(r"^[ \t]*Max charging current:\s*(-?\d+)", int)
            if fallback:
                current = fallback
                value["current_is_max"] = True
        # 单位归一：多数平台 mA（几百~几千），部分平台 µA（几十万）。
        # 超过 20000 视作 µA，换算成 mA，否则会显示成「几百安培」。
        if current is not None and abs(current) > 20000:
            current = current // 1000
        value["current"] = current

        value["ac"] = grab(r"^[ \t]*AC powered:\s*(\w+)")
        value["usb"] = grab(r"^[ \t]*USB powered:\s*(\w+)")
        status = grab(r"^[ \t]*status:\s*(\d+)", int)
        value["status"] = status
        if status == 2:
            value["charging"] = "充电中"
        elif status == 3:
            value["charging"] = "放电中"
        elif status == 5:
            value["charging"] = "已充满"
        elif status == 4:
            value["charging"] = "未充电"
        elif status is not None:
            value["charging"] = f"状态 {status}"
        else:
            value["charging"] = None
        return value

    def _apply_dumpsys(self, output):
        parsed = self.parse_battery(output)
        if parsed.get("level") is None:
            self.status_label.setText("解析失败，请确认设备已连接")
            return

        # dumpsys 里出现这段，说明电池上报被改过（模拟放电 / 测试模式），
        # 不 reset 的话电量会一直掉，所以给醒目提示 + 一键恢复。
        self._set_stopped_warning("UPDATES STOPPED" in output)

        level = parsed.get("level")
        level_tone = "bad" if level <= 15 else ("warn" if level <= 30 else "ok")
        self.cards["level"].set_value(str(level), level_tone)

        health = parsed.get("health")
        self.cards["health"].set_value(
            health or "--", "ok" if health == "良好" else
            ("bad" if health in ("过热", "已损坏", "过压", "过冷") else "warn"))

        temp = parsed.get("temp")
        if temp is not None:
            tone = "bad" if temp >= TEMP_BAD else ("warn" if temp >= TEMP_WARN else "ok")
            self.cards["temp"].set_value(f"{temp:.1f}", tone)

        voltage = parsed.get("voltage")
        if voltage is not None:
            suffix = "（上限）" if parsed.get("voltage_is_max") else ""
            self.cards["voltage"].set_value(
                f"{voltage} mV{suffix}",
                "muted" if parsed.get("voltage_is_max") else
                ("warn" if voltage < 3400 else "ok"))

        current = parsed.get("current")
        if current is not None:
            suffix = "（上限）" if parsed.get("current_is_max") else ""
            self.cards["current"].set_value(
                f"{current} mA{suffix}", "ok" if current >= 0 else "muted")

        self.cards["charging"].set_value(parsed.get("charging") or "--")
        self.cards["ac"].set_value(parsed.get("ac") or "--",
                                   "ok" if parsed.get("ac") == "true" else "muted")
        self.cards["usb"].set_value(parsed.get("usb") or "--",
                                    "ok" if parsed.get("usb") == "true" else "muted")

        self._append_sample(parsed)
        self.status_label.setText(f"更新于 {datetime.now():%H:%M:%S}")

    def _set_stopped_warning(self, stopped):
        """显示/隐藏「电池上报已停止」横幅。

        用 setVisible 会被所在 QStackedWidget 页面的可见性掩盖，
        所以统一走 setHidden，状态判断也更直接。
        """
        self._stopped = bool(stopped)
        self.warn_bar.setHidden(not self._stopped)

    def _append_sample(self, parsed):
        self.samples.append(parsed)
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            datetime.now().strftime("%H:%M:%S"),
            str(parsed.get("level", "--")),
            f"{parsed['temp']:.1f}" if parsed.get("temp") is not None else "--",
            str(parsed.get("voltage", "--")),
            str(parsed.get("current", "--")),
            parsed.get("charging") or "--",
        ]
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)
        self.table.scrollToBottom()
        while self.table.rowCount() > 200:
            self.table.removeRow(0)
        self.count_label.setText(f"{len(self.samples)} 条")

    # ================= 操作 =================

    def enable_test_mode(self):
        for command, label in [
            ('dumpsys battery set ac 0', '关闭 AC 充电'),
            ('dumpsys battery set usb 0', '关闭 USB 充电'),
        ]:
            self.runner.run(command, label)

    def on_page_shown(self):
        if not self.samples:
            self.refresh()

    def stop_background(self):
        self._auto_timer.stop()
        self.runner.stop_all()
