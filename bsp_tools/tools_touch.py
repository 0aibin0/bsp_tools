"""常用工具 · 触摸调试

触摸事件实时抓取、点击/滑动注入、按键注入、触摸可视化开关（划线界面 /
指针位置）。输入设备枚举与 dumpsys input 那组查询按钮已按 func-list 移除
（纯查询，命令面板里搜得到）。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QComboBox, QLineEdit, QCheckBox, QSpinBox)

import theme
import ui_widgets as W
from command_runner import CommandRunner


# 触摸可视化开关（系统设置项，1 开 0 关，不需要 root）
TOUCH_SWITCHES = [
    ("show_touches", "划线界面", "触摸时显示白色圆圈轨迹"),
    ("pointer_location", "指针位置", "屏幕顶部显示实时坐标"),
]

TAP_PRESETS = [
    ("中心点", "540 1200"),
    ("左上角", "50 50"),
    ("右上角", "1030 50"),
    ("左下角", "50 2350"),
    ("右下角", "1030 2350"),
]


class TouchSection(QWidget):
    """触摸 / 输入调试。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.runner = CommandRunner(self, title="命令输出")
        self._build_ui()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._build_tap_card(), 1)
        top.addWidget(self._build_swipe_card(), 1)
        layout.addLayout(top)

        layout.addWidget(self._build_key_card())
        layout.addWidget(self._build_switch_card())
        layout.addWidget(self._build_query_card())
        layout.addWidget(self.runner, 1)

    def _build_tap_card(self):
        card = W.Card("点击测试")

        row = card.add_row()
        row.addWidget(W.field_label("坐标 X", card))
        self.tap_x = QSpinBox(card)
        self.tap_x.setRange(0, 9999)
        self.tap_x.setValue(540)
        self.tap_x.setMinimumHeight(28)
        row.addWidget(self.tap_x)

        row.addWidget(W.field_label("Y", card))
        self.tap_y = QSpinBox(card)
        self.tap_y.setRange(0, 9999)
        self.tap_y.setValue(1200)
        self.tap_y.setMinimumHeight(28)
        row.addWidget(self.tap_y)

        tap_btn = W.accent_button("点击", None, card)
        tap_btn.clicked.connect(self.do_tap)
        row.addWidget(tap_btn)
        row.addStretch()

        preset_row = card.add_row()
        preset_row.addWidget(W.field_label("快捷位置", card))
        preset_grid = QGridLayout()
        preset_grid.setSpacing(6)
        for index, (label, coords) in enumerate(TAP_PRESETS):
            btn = W.soft_button(label, None, card)
            btn.clicked.connect(lambda _c=False, l=label, c=coords: self.tap_preset(l, c))
            preset_grid.addWidget(btn, index // 3, index % 3)
        for col in range(3):
            preset_grid.setColumnStretch(col, 1)
        preset_row.addLayout(preset_grid, 1)

        card.add(W.heading("用 input tap 注入点击，适合在没有触摸屏或需要脚本化验证时使用。", card))
        return card

    def _build_swipe_card(self):
        card = W.Card("滑动测试")

        # 坐标两两一行：四个数字框挤在一行会把卡片撑到 600px 以上，
        # 并排布局时会顶出横向滚动条
        coord_grid = QGridLayout()
        coord_grid.setSpacing(6)
        for index, (label, default, attr) in enumerate(
                (("X1", 540, "sw_x1"), ("Y1", 1800, "sw_y1"),
                 ("X2", 540, "sw_x2"), ("Y2", 600, "sw_y2"))):
            coord_grid.addWidget(W.field_label(label, card), index // 2, (index % 2) * 2)
            box = QSpinBox(card)
            box.setRange(0, 9999)
            box.setValue(default)
            box.setMinimumHeight(32)
            box.setMinimumWidth(78)
            setattr(self, attr, box)
            coord_grid.addWidget(box, index // 2, (index % 2) * 2 + 1)
        for col in range(4):
            coord_grid.setColumnStretch(col, 1)
        card.add_layout(coord_grid)

        row = card.add_row()
        row.addWidget(W.field_label("时长ms", card))
        self.sw_duration = QSpinBox(card)
        self.sw_duration.setRange(50, 5000)
        self.sw_duration.setValue(300)
        self.sw_duration.setMinimumHeight(32)
        self.sw_duration.setMinimumWidth(84)
        row.addWidget(self.sw_duration)

        swipe_btn = W.accent_button("滑动", None, card)
        swipe_btn.clicked.connect(self.do_swipe)
        row.addWidget(swipe_btn)
        row.addStretch()

        dir_row = card.add_row()
        dir_row.addWidget(W.field_label("方向", card))
        dir_grid = QGridLayout()
        dir_grid.setSpacing(6)
        for index, (label, coords) in enumerate(
                (("上滑", (540, 1800, 540, 600)),
                 ("下滑", (540, 600, 540, 1800)),
                 ("左滑", (900, 1200, 200, 1200)),
                 ("右滑", (200, 1200, 900, 1200)))):
            btn = W.soft_button(label, None, card)
            btn.clicked.connect(lambda _c=False, c=coords: self.swipe_direction(c))
            dir_grid.addWidget(btn, index // 4, index % 4)
        for col in range(4):
            dir_grid.setColumnStretch(col, 1)
        dir_row.addLayout(dir_grid, 1)
        return card

    def _build_key_card(self):
        card = W.Card("按键注入")

        row = card.add_row()
        row.addWidget(W.field_label("keyevent", card))
        self.key_input = QLineEdit(card)
        self.key_input.setPlaceholderText("键名或键码，例如 HOME / 26")
        self.key_input.setMinimumHeight(28)
        self.key_input.setMaximumWidth(220)
        self.key_input.returnPressed.connect(self.send_key)
        row.addWidget(self.key_input)

        send_btn = W.accent_button("发送", None, card)
        send_btn.clicked.connect(self.send_key)
        row.addWidget(send_btn)
        row.addStretch()

        # 常用键排成 2 行网格：7 个挤一行会把模块撑到 495px
        key_grid = QGridLayout()
        key_grid.setSpacing(6)
        for index, (label, key) in enumerate(
                (("返回", "KEYCODE_BACK"), ("主页", "KEYCODE_HOME"),
                 ("菜单", "KEYCODE_MENU"), ("电源", "KEYCODE_POWER"),
                 ("音量+", "KEYCODE_VOLUME_UP"), ("音量-", "KEYCODE_VOLUME_DOWN"),
                 ("唤醒", "KEYCODE_WAKEUP"))):
            btn = W.soft_button(label, None, card)
            btn.clicked.connect(lambda _c=False, k=key: self.send_key(k))
            key_grid.addWidget(btn, index // 4, index % 4)
        for col in range(4):
            key_grid.setColumnStretch(col, 1)
        card.add_layout(key_grid)
        return card

    def _build_switch_card(self):
        """触摸可视化开关：划线界面 / 指针位置。

        这两个是系统 settings，开完立刻在设备屏幕上生效，调试触摸时很常用。
        按钮排成网格（5 个挤一行会把模块撑到 765px）。
        """
        card = W.Card("触摸可视化")

        grid = QGridLayout()
        grid.setSpacing(6)

        # 开关按钮按行摆：打开/关闭 一行，省横向空间
        for index, (key, label, tip) in enumerate(TOUCH_SWITCHES):
            block = QHBoxLayout()
            block.setSpacing(5)
            on_btn = W.accent_button(f"打开{label}", None, card)
            on_btn.setToolTip(f"{tip}\nsettings put system {key} 1")
            on_btn.clicked.connect(
                lambda _c=False, k=key, l=label: self.set_touch_switch(k, l, True))
            block.addWidget(on_btn)
            off_btn = W.soft_button(f"关闭{label}", None, card)
            off_btn.setToolTip(f"settings put system {key} 0")
            off_btn.clicked.connect(
                lambda _c=False, k=key, l=label: self.set_touch_switch(k, l, False))
            block.addWidget(off_btn)
            grid.addLayout(block, index, 0)

        read_btn = W.soft_button("读取状态", "refresh", card)
        read_btn.setToolTip("读取两个开关的当前值")
        read_btn.clicked.connect(self.read_touch_switches)
        grid.addWidget(read_btn, 0, 1, 2, 1)
        grid.setColumnStretch(0, 1)
        card.add_layout(grid)

        card.add(W.heading(
            "划线界面 = show_touches（触摸显示圆圈），"
            "指针位置 = pointer_location（顶部显示坐标）；"
            "调试完记得关闭，否则会影响正常使用。", card))
        return card

    def _build_query_card(self):
        """只留事件抓取；输入设备枚举 / dumpsys input 那组按钮按 func-list
        移除（编号 51）——都是纯查询，命令面板里搜得到。"""
        card = W.Card("触摸事件抓取")

        row = card.add_row()
        self.event_btn = W.accent_button("抓取事件 (5s)", "activity", card)
        self.event_btn.setToolTip("getevent 监听 5 秒后自动结束，用于确认触摸是否上报")
        self.event_btn.clicked.connect(self.capture_events)
        row.addWidget(self.event_btn)

        self.axis_check = QCheckBox("只看 ABS_MT 轴", card)
        self.axis_check.setChecked(True)
        self.axis_check.setToolTip("只抓 ABS_MT 触摸轴与 SYN_REPORT")
        row.addWidget(self.axis_check)
        row.addStretch()

        card.add(W.heading(
            "抓取期间请在设备上触摸屏幕；没有事件输出说明触摸未上报到内核。", card))
        return card

    # ================= 行为 =================

    def do_tap(self):
        x, y = self.tap_x.value(), self.tap_y.value()
        self.runner.run(f'input tap {x} {y}', f"点击 ({x}, {y})")

    def tap_preset(self, label, coords):
        x, y = coords.split()
        self.tap_x.setValue(int(x))
        self.tap_y.setValue(int(y))
        self.runner.run(f'input tap {x} {y}', f"点击{label} ({x}, {y})")

    def do_swipe(self):
        x1, y1 = self.sw_x1.value(), self.sw_y1.value()
        x2, y2 = self.sw_x2.value(), self.sw_y2.value()
        duration = self.sw_duration.value()
        self.runner.run(
            f'input swipe {x1} {y1} {x2} {y2} {duration}',
            f"滑动 ({x1},{y1})→({x2},{y2})")

    def swipe_direction(self, coords):
        x1, y1, x2, y2 = coords
        self.sw_x1.setValue(x1)
        self.sw_y1.setValue(y1)
        self.sw_x2.setValue(x2)
        self.sw_y2.setValue(y2)
        self.do_swipe()

    def send_key(self, key=None):
        value = key if isinstance(key, str) and key else self.key_input.text().strip()
        if not value:
            return
        self.runner.run(f'input keyevent {value}', f"按键 {value}")

    def capture_events(self):
        seconds = 5
        if self.axis_check.isChecked():
            command = f"timeout {seconds} getevent -lt | grep -E 'ABS_MT|SYN_REPORT'"
            label = f"抓取触摸事件 {seconds}s（仅 ABS_MT）"
        else:
            command = f"timeout {seconds} getevent -lt"
            label = f"抓取触摸事件 {seconds}s（全部）"
        self.runner.run(command, label)

    # ---------- 触摸可视化开关 ----------

    def set_touch_switch(self, key, label, enabled):
        value = 1 if enabled else 0
        self.runner.run(
            f"settings put system {key} {value}",
            f"{'打开' if enabled else '关闭'}{label}")

    def read_touch_switches(self):
        # settings get 一次只接一个键，所以两个开关分别读
        for key, label, _tip in TOUCH_SWITCHES:
            self.runner.run(f"settings get system {key}", f"读取{label}状态")

    def on_page_shown(self):
        self.tap_x.setFocus()
