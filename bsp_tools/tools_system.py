"""常用工具 · 系统调试

属性读写、CPU 调频、内存与进程、挂载与存储、SELinux、时间设置等
系统层面的常用调试入口。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLineEdit, QComboBox)

import theme
import ui_widgets as W
from command_runner import CommandRunner


SYSTEM_QUERIES = [
    ("系统属性", "getprop | grep -E 'ro.product|ro.build'"),
    ("CPU 频率", "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"),
    ("CPU 可用频率", "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies"),
    ("CPU 调频策略", "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
    ("内存详情", "cat /proc/meminfo | head -8"),
    ("进程 TOP20", "top -n 1 -b -o %CPU | head -25"),
    ("挂载信息", "mount | head -30"),
    ("存储占用", "df -h /data /system /cache"),
    ("SELinux 状态", "getenforce"),
    ("内核版本", "uname -a"),
    ("运行时长", "cat /proc/uptime"),
    ("已加载模块", "lsmod | head -30"),
    ("服务列表", "service list | head -40"),
    ("系统时间", "date"),
]

GOVERNORS = ["performance", "powersave", "schedutil", "interactive", "ondemand", "userspace"]

COMMON_PROPS = [
    "ro.product.model", "ro.build.version.release", "ro.build.fingerprint",
    "ro.debuggable", "persist.sys.locale", "ro.sf.lcd_density",
]

CPU_PATHS = [
    "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor",
    "/sys/devices/system/cpu/cpu4/cpufreq/scaling_governor",
]

# 「重启设备」（adb reboot）已按 func-list 移除：侧边栏「快捷操作 → 重启设备」
# 与 Ctrl+K 命令面板里都有，这里不再重复一个入口。
REBOOT_MODES = [
    ("进入 bootloader", "adb reboot bootloader"),
    ("进入 recovery", "adb reboot recovery"),
]


class SystemSection(QWidget):
    """系统属性 / 调频 / 内存 / 存储调试。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.runner = CommandRunner(self, title="命令输出")
        self._build_ui()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 系统属性 / CPU 调频上下排列：并排会把模块最小宽度推到 699px，
        # 在默认窗口下内容区放不下（内容区纵向可滚动，堆叠没有副作用）
        layout.addWidget(self._build_property_card())
        layout.addWidget(self._build_cpu_card())
        layout.addWidget(self._build_action_card())
        layout.addWidget(self._build_query_card())
        layout.addWidget(self.runner, 1)

    def _build_property_card(self):
        card = W.Card("系统属性")

        row = card.add_row()
        row.addWidget(W.field_label("属性名", card))
        self.prop_combo = QComboBox(card)
        self.prop_combo.setEditable(True)
        self.prop_combo.addItems(COMMON_PROPS)
        self.prop_combo.setMinimumHeight(28)
        row.addWidget(self.prop_combo, 1)

        get_btn = W.accent_button("读取", None, card)
        get_btn.clicked.connect(self.get_property)
        row.addWidget(get_btn)

        row2 = card.add_row()
        row2.addWidget(W.field_label("设置值", card))
        self.prop_value = QLineEdit(card)
        self.prop_value.setPlaceholderText("写入值，留空则删除该属性")
        self.prop_value.setMinimumHeight(28)
        self.prop_value.returnPressed.connect(self.set_property)
        row2.addWidget(self.prop_value, 1)

        set_btn = W.soft_button("写入", None, card)
        set_btn.clicked.connect(self.set_property)
        row2.addWidget(set_btn)

        card.add(W.heading(
            "写入属性需要 root；ro.* 开头的只读属性无法修改。", card))
        return card

    def _build_cpu_card(self):
        card = W.Card("CPU 调频")

        row = card.add_row()
        row.addWidget(W.field_label("调频策略", card))
        self.gov_combo = QComboBox(card)
        self.gov_combo.setEditable(True)
        self.gov_combo.addItems(GOVERNORS)
        self.gov_combo.setMinimumHeight(28)
        row.addWidget(self.gov_combo, 1)

        apply_btn = W.accent_button("应用", None, card)
        apply_btn.clicked.connect(self.apply_governor)
        row.addWidget(apply_btn)

        read_btn = W.soft_button("读取当前", "refresh", card)
        read_btn.clicked.connect(self.read_governor)
        row.addWidget(read_btn)

        row2 = card.add_row()
        row2.addWidget(W.field_label("最大频率", card))
        self.freq_edit = QLineEdit(card)
        self.freq_edit.setPlaceholderText("例如 1800000（kHz）")
        self.freq_edit.setMinimumHeight(28)
        self.freq_edit.returnPressed.connect(self.apply_max_freq)
        row2.addWidget(self.freq_edit, 1)

        freq_btn = W.soft_button("应用", None, card)
        freq_btn.clicked.connect(self.apply_max_freq)
        row2.addWidget(freq_btn)

        card.add(W.heading(
            "调频改动会影响功耗与温度；测试完建议恢复原策略。", card))
        return card

    def _build_action_card(self):
        card = W.Card("系统操作")

        # 重启 / 挂载各占一行：分组清楚，也避免一行塞太多按钮把模块撑宽。
        # 「挂载 debugfs」已移除——侧边栏「快捷操作」里有同一个入口。
        row = card.add_row()
        row.addWidget(W.field_label("重启", card))
        for label, command in REBOOT_MODES:
            btn = W.soft_button(label, None, card)
            btn.clicked.connect(
                lambda _c=False, cmd=command, l=label: self.runner.run(cmd, l))
            row.addWidget(btn)
        row.addStretch()

        row2 = card.add_row()
        row2.addWidget(W.field_label("挂载", card))
        for label, command in (("remount", "adb remount"),
                               ("挂载 system 读写", "adb shell mount -o rw,remount /system")):
            btn = W.soft_button(label, None, card)
            btn.clicked.connect(
                lambda _c=False, cmd=command, l=label: self.runner.run(cmd, l))
            row2.addWidget(btn)
        row2.addStretch()
        return card

    def _build_query_card(self):
        card = W.Card("系统信息查询")

        grid = QGridLayout()
        grid.setSpacing(8)
        for index, (label, command) in enumerate(SYSTEM_QUERIES):
            btn = W.soft_button(label, None, card)
            btn.clicked.connect(
                lambda _c=False, cmd=command, l=label: self.runner.run(cmd, l))
            # 4 列网格：14 个按钮排 4 行，模块最小宽度可控
            grid.addWidget(btn, index // 4, index % 4)
        for col in range(4):
            grid.setColumnStretch(col, 1)
        card.add_layout(grid)
        return card

    # ================= 行为 =================

    def get_property(self):
        name = self.prop_combo.currentText().strip()
        if not name:
            return
        self.runner.run(f'getprop {name}', f"读取 {name}")

    def set_property(self):
        name = self.prop_combo.currentText().strip()
        if not name:
            return
        value = self.prop_value.text().strip()
        if value:
            self.runner.run(f'setprop {name} {value}', f"设置 {name}={value}")
        else:
            self.runner.run(f'setprop {name} ""', f"清空 {name}")

    def apply_governor(self):
        governor = self.gov_combo.currentText().strip()
        if not governor:
            return
        for path in CPU_PATHS:
            self.runner.run(
                f'echo {governor} > {path} 2>/dev/null',
                f"设置调频策略 {governor}")

    def read_governor(self):
        for path in CPU_PATHS:
            self.runner.run(f'cat {path} 2>/dev/null', f"读取 {path}")

    def apply_max_freq(self):
        freq = self.freq_edit.text().strip()
        if not freq:
            return
        self.runner.run(
            "echo %s > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq" % freq,
            f"设置最大频率 {freq}")

    def on_page_shown(self):
        self.prop_combo.setFocus()
