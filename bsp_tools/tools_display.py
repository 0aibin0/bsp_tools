"""常用工具 · 显示调试（LCM）

面向屏体调试的常用操作：背光、分辨率、刷新率、DCS 包构造，外加时序/带宽
计算——给一组前后沿就能算出 pixel clock 和每 lane 速率，判断这条 DSI 链路
跑不跑得动。命令在本模块内执行并把输出显示在右侧结果面板，不会把用户弹到
Shell Tools 页。

DCS 直接读写节点和 ESD 重置按钮已按 func-list 移除（屏体写入走 Shell Tools
的自定义命令），这里只负责把字节序列算准。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QComboBox, QLineEdit, QSlider, QLabel, QCheckBox,
                             QSpinBox)

import timing as timing_mod
import ui_widgets as W


# 背光节点：屏体背光在 sysfs 里的位置跟平台有关，别写死一个。
#
# 注意这里**不是** /sys/class/leds/lcd-backlight —— 那个路径在 T820 上根本
# 不存在（/sys/class/leds/ 下只有 mmc0:: / mmc1:: 这类），实测踩过。
BACKLIGHT_DIRS = [
    "/sys/class/backlight/panel0-backlight",   # 通用 / 高通平台
    "/sys/class/backlight/sprd_backlight",     # 展锐 T820
]


def _cat_first(name):
    """拼一条"按顺序试"的读取命令：cat a || cat b。

    只有一个能读到时不会报错，读不到的那条错误信息会留在输出面板里，
    方便确认这台设备到底暴露了哪个节点。
    """
    return " || ".join("cat {}/{}".format(d, name) for d in BACKLIGHT_DIRS)


def _write_all(name, value):
    """拼一条"逐个尝试"的写入命令：写第一个成功的。"""
    return " || ".join(
        "echo {} > {}/{}".format(value, d, name) for d in BACKLIGHT_DIRS)


BRIGHTNESS_READ = _cat_first("brightness")
MAX_BRIGHTNESS_READ = _cat_first("max_brightness")
ACTUAL_BRIGHTNESS_READ = _cat_first("actual_brightness")

REFRESH_RATES = ["60", "90", "120", "144"]
RESOLUTIONS = ["1080x2400", "1220x2712", "1260x2800", "1440x3200"]
DENSITIES = ["240", "280", "320", "360", "400", "420", "440", "480"]

# 显示子系统查询：原来是 Shell Tools 的 adb 卡（wm size / dumpsys / device info），
# 按「侧边栏有 = 页面上不重复」的原则收拢到显示调试里
PANEL_QUERIES = [
    ("显示信息", "dumpsys display"),
    ("SurfaceFlinger", "dumpsys SurfaceFlinger | head -60"),
    ("分辨率/密度", "wm size; wm density"),
    ("显示相关属性", "getprop | grep -i -E 'display|lcm|panel|dsi'"),
    ("背光节点", "ls /sys/class/backlight/"),
    ("DSI 节点", "ls /sys/class/display/"),
]


class DisplayDebugSection(QWidget):
    """显示 / LCM 调试区。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # runner 由 CommonToolsPage 在 _inject_runner 中注入（本页共享的输出面板）
        self._build_ui()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._build_backlight_card(), 1)
        top.addWidget(self._build_mode_card(), 1)
        layout.addLayout(top)

        # DCS 构造 与 Panel 信息 并排：两张都是"窄工具卡"，叠着放会把模块顶到
        # 813px（视口只有 741），并排后总高降到 ~690。按最小宽度 4:3 分列
        mid = QHBoxLayout()
        mid.setSpacing(10)
        mid.addWidget(self._build_dcs_card(), 4)
        mid.addWidget(self._build_panel_info_card(), 3)
        layout.addLayout(mid)

        layout.addWidget(self._build_timing_card())
        layout.addStretch()

    def _build_backlight_card(self):
        card = W.Card("背光 / 亮度")

        row = card.add_row()
        row.addWidget(W.field_label("亮度", card))
        self.bright_slider = QSlider(Qt.Horizontal, card)
        self.bright_slider.setRange(0, 255)
        self.bright_slider.setValue(128)
        self.bright_slider.setMinimumHeight(28)
        self.bright_slider.valueChanged.connect(
            lambda v: self.bright_value.setText(str(v)))
        row.addWidget(self.bright_slider, 1)

        self.bright_value = QLineEdit(card)
        self.bright_value.setText("128")
        self.bright_value.setAlignment(Qt.AlignCenter)
        self.bright_value.setFixedWidth(58)
        self.bright_value.returnPressed.connect(self._on_bright_typed)
        row.addWidget(self.bright_value)

        self.bright_set_btn = W.accent_button("设置", None, card)
        self.bright_set_btn.setToolTip("走框架：settings put system screen_brightness")
        # 定宽：不定宽的话按钮会把滑块挤到 100px 以下（按钮的 sizeHint 也能吸收空白）
        self.bright_set_btn.setFixedWidth(62)
        self.bright_set_btn.clicked.connect(self.set_brightness)
        row.addWidget(self.bright_set_btn)

        # 直接写背光节点：框架那层有亮度曲线，值会被改写；调屏体时经常要
        # 直接改 PWM 节点看真实效果
        self.bright_node_btn = W.soft_button("写节点", "upload", card)
        # 带图标，80px 放不下（check_layout 会报"文字裁切"），给到 96
        self.bright_node_btn.setFixedWidth(96)
        self.bright_node_btn.setToolTip(
            "直接写 {}（按顺序试）".format(" / ".join(BACKLIGHT_DIRS)))
        self.bright_node_btn.clicked.connect(self.set_brightness_node)
        row.addWidget(self.bright_node_btn)

        row2 = card.add_row()
        get_btn = W.soft_button("读取", "refresh", card)
        get_btn.setToolTip("读 settings 值 + 背光节点的 brightness")
        get_btn.clicked.connect(self.get_brightness)
        row2.addWidget(get_btn)

        self.bright_max_check = QCheckBox("读 max/actual", card)
        self.bright_max_check.setToolTip(
            "勾选后额外读 max_brightness 与 actual_brightness（不勾只读 brightness）")
        row2.addWidget(self.bright_max_check)
        row2.addStretch()

        card.add(W.heading(
            "节点路径按平台不同：「设置」走框架 settings，「写节点」直接写 sysfs"
            "（改的是真实 PWM 值，需要 root）。", card))
        return card

    def _build_mode_card(self):
        """分辨率 / 密度 / 刷新率。

        这三个是同一类东西（显示模式参数），原来散在 Shell Tools 的 adb 卡里
        （wm size）和系统调试里，现在收拢到这里：
        - 分辨率：wm size 读/应用/复位
        - 密度：  wm density 读/应用/复位
        - 刷新率：settings 读写

        版式上每行只放「读取 / 应用」两个按钮，复位收成底下一颗——三行各挂三颗
        按钮时，行最小宽度 340px，比下拉框内容宽度（112px）还吃紧，窗口一窄
        下拉框就被压到 72px 显示成「2400×10…」（check_layout 会报"宽度不足"）。
        两按钮后整张卡 324px，下拉框任何窗口尺寸下都能完整显示。
        """
        card = W.Card("分辨率 / 密度 / 刷新率")

        row = card.add_row()
        row.addWidget(W.field_label("分辨率", card))
        self.res_combo = QComboBox(card)
        self.res_combo.setEditable(True)
        self.res_combo.addItems(RESOLUTIONS)
        self.res_combo.setCurrentText("")
        self.res_combo.setToolTip("填 宽x高，例如 1080x2400")
        row.addWidget(self.res_combo, 1)

        read_res = W.soft_button("读取", "refresh", card)
        read_res.setToolTip("wm size")
        read_res.clicked.connect(self.read_resolution)
        row.addWidget(read_res)

        apply_res = W.soft_button("应用", None, card)
        apply_res.clicked.connect(self.apply_resolution)
        row.addWidget(apply_res)

        row2 = card.add_row()
        row2.addWidget(W.field_label("密度", card))
        self.density_combo = QComboBox(card)
        self.density_combo.setEditable(True)
        self.density_combo.addItems(DENSITIES)
        self.density_combo.setCurrentText("")
        self.density_combo.setToolTip("dpi 数值，例如 320")
        row2.addWidget(self.density_combo, 1)

        read_density = W.soft_button("读取", "refresh", card)
        read_density.setToolTip("wm density")
        read_density.clicked.connect(self.read_density)
        row2.addWidget(read_density)

        apply_density = W.soft_button("应用", None, card)
        apply_density.clicked.connect(self.apply_density)
        row2.addWidget(apply_density)

        row3 = card.add_row()
        row3.addWidget(W.field_label("刷新率", card))
        self.fps_combo = QComboBox(card)
        self.fps_combo.setEditable(True)
        self.fps_combo.addItems(REFRESH_RATES)
        self.fps_combo.setCurrentText("")
        self.fps_combo.setToolTip("设备支持的刷新率，例如 60 / 90 / 120")
        row3.addWidget(self.fps_combo, 1)

        read_fps = W.soft_button("读取", "refresh", card)
        read_fps.setToolTip("读设备的刷新率；需要设备支持 fps 节点，"
                            "部分平台返回为空属正常")
        read_fps.clicked.connect(self.read_refresh_rate)
        row3.addWidget(read_fps)

        apply_fps = W.soft_button("应用", None, card)
        apply_fps.clicked.connect(self.apply_refresh_rate)
        row3.addWidget(apply_fps)

        row4 = card.add_row()
        reset_btn = W.soft_button("复位", None, card)
        reset_btn.setToolTip("wm size reset + wm density reset：分辨率与密度恢复设备默认"
                             "（刷新率没有对应的 reset 节点，不受影响）")
        reset_btn.clicked.connect(self.reset_mode)
        row4.addWidget(reset_btn)
        row4.addStretch()
        return card

    def reset_mode(self):
        """分辨率 + 密度一起复位（wm size reset / wm density reset）。"""
        self.runner.run("wm size reset", "分辨率已复位")
        self.runner.run("wm density reset", "密度已复位")

    def _build_panel_info_card(self):
        """Panel / 显示子系统查询：这些命令以前散在 Shell Tools 的 adb 卡里。"""
        card = W.Card("Panel / 显示信息")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        # 两列排 3 行：这张卡只占半宽，三列会把按钮压得放不下字
        for index, (label, command) in enumerate(PANEL_QUERIES):
            btn = W.soft_button(label, None, card)
            btn.setToolTip(command)
            btn.clicked.connect(
                lambda _c=False, cmd=command, l=label: self.runner.run(cmd, l))
            grid.addWidget(btn, index // 2, index % 2)
        for col in range(2):
            grid.setColumnStretch(col, 1)
        card.add_layout(grid)
        return card

    def _build_dcs_card(self):
        """DCS 包构造：只负责算出字节序列，不往设备写。

        按屏体 spec 手敲 `0x39,0x00,0x00,0x0N` 前缀很容易错一个字节，
        这里给命令和参数就够，前导码和长度字节自动算；结果可复制去贴代码
        或贴 spec。
        """
        card = W.Card("DCS 包构造")

        row = card.add_row()
        row.addWidget(W.field_label("命令", card))
        self.dcs_cmd = QLineEdit(card)
        self.dcs_cmd.setPlaceholderText("如 0x1a")
        self.dcs_cmd.setFixedWidth(84)
        self.dcs_cmd.returnPressed.connect(self.build_dcs)
        row.addWidget(self.dcs_cmd)

        row.addWidget(W.field_label("参数", card))
        self.dcs_params = QLineEdit(card)
        self.dcs_params.setPlaceholderText("空格分隔，如 0x2b 0x3c")
        # 这张卡只占半宽，最小宽度给 110 就够；给 160 会把模块顶出视口
        self.dcs_params.setMinimumWidth(110)
        self.dcs_params.returnPressed.connect(self.build_dcs)
        row.addWidget(self.dcs_params, 1)

        build_btn = W.accent_button("生成", "package", card)
        build_btn.setToolTip("按参数个数自动选短包(0x05)/带参短包(0x15)/长包(0x39)")
        build_btn.clicked.connect(self.build_dcs)
        row.addWidget(build_btn)

        result_row = card.add_row()
        result_row.addWidget(W.field_label("字节序列", card))
        self.dcs_data = QLineEdit(card)
        self.dcs_data.setReadOnly(True)
        self.dcs_data.setPlaceholderText("生成后显示，可直接复制")
        self.dcs_data.setMinimumWidth(110)
        result_row.addWidget(self.dcs_data, 1)
        copy_btn = W.soft_button("复制", None, card)
        copy_btn.setToolTip("复制字节序列到剪贴板")
        copy_btn.clicked.connect(self.copy_dcs)
        result_row.addWidget(copy_btn)

        self.dcs_kind_label = W.heading(
            "DCS 短包/长包按参数个数自动判定，生成后可直接复制；"
            "要下发就用 Shell Tools 的自定义命令写节点。", card)
        card.add(self.dcs_kind_label)
        return card

    def _build_timing_card(self):
        """时序 / 带宽计算：给一组参数算 pclk 与每 lane 速率。

        输入框用 QSpinBox 而不是下拉框——屏体 spec 给的数值千奇百怪，
        下拉框选不到。所有数值改动都即时重算，不需要再点一次「计算」。

        版式分三段（对应 t820-lcm-porch.xlsx 的算表）：
          1. 屏体参数：分辨率/刷新率/格式/lane + 水平与垂直共 6 个 porch
          2. DPI 分频：时钟源 + 自动或手动分频 → 实际 pclk 与实际帧率
          3. 结果：8 项派生量，4 列 × 2 行
        """
        card = W.Card("时序 / 带宽计算")

        def spin(value, low, high, width=48, suffix=""):
            box = QSpinBox(card)
            box.setRange(low, high)
            box.setValue(value)
            box.setFixedWidth(width)
            box.setMinimumHeight(28)
            # 去掉箭头后数字居中更好看，也让一列数字对得齐
            box.setAlignment(Qt.AlignCenter)
            if suffix:
                box.setSuffix(suffix)
            box.valueChanged.connect(self._recalc_timing)
            return box

        # 宽度按"最多几位数字 + 单位后缀"给：箭头收掉后不需要再留那 18px，
        # 上限也用 9999（4 位数）——5 位数会把最小宽度顶到 80px，窄窗口下
        # 会把整行挤成"被压缩"状态
        self.t_w = spin(1080, 1, 9999, 58)
        self.t_h = spin(2400, 1, 9999, 58)
        self.t_fps = spin(60, 1, 480, 62, " Hz")
        self.t_hfp = spin(40, 0, 4096)
        self.t_hbp = spin(40, 0, 4096)
        self.t_hsw = spin(10, 0, 4096)
        self.t_vfp = spin(20, 0, 4096)
        self.t_vbp = spin(20, 0, 4096)
        self.t_vsw = spin(4, 0, 4096)

        # ---- 第 1 段：屏体参数 ----
        # 不再给这段加分组标题：字段名（分辨率/水平/垂直）本身已经说明结构，
        # 加一行标题 + 分隔线要多占 30px，模块就会顶出纵向滚动条
        row1 = card.add_row()
        # 同 porch 行：字段多、默认 8px 行距白占宽度，4px + 组间 addSpacing(10)
        # 的层次反而更清楚，也把这张卡的最小宽度压回模块视口之内
        row1.setSpacing(4)
        row1.addWidget(W.field_label("分辨率", card))
        row1.addWidget(self.t_w)
        row1.addWidget(QLabel("×", card))
        row1.addWidget(self.t_h)
        row1.addSpacing(10)
        row1.addWidget(W.field_label("刷新率", card))
        row1.addWidget(self.t_fps)
        row1.addSpacing(10)
        row1.addWidget(W.field_label("像素格式", card))
        self.t_bpp = QComboBox(card)
        self.t_bpp.setMinimumHeight(28)
        for label, value in timing_mod.BPP_PRESETS.items():
            self.t_bpp.addItem(label, value)
        self.t_bpp.currentIndexChanged.connect(self._recalc_timing)
        row1.addWidget(self.t_bpp)
        row1.addSpacing(10)
        row1.addWidget(W.field_label("Lane", card))
        self.t_lanes = QComboBox(card)
        self.t_lanes.setMinimumHeight(28)
        for value in ("1", "2", "3", "4", "8"):
            self.t_lanes.addItem(value, int(value))
        self.t_lanes.setCurrentText("4")
        self.t_lanes.currentIndexChanged.connect(self._recalc_timing)
        row1.addWidget(self.t_lanes)
        row1.addStretch()

        # 六个 porch 一行：HFP/HBP/HSW 是水平、VFP/VBP/VSW 是垂直，前缀已经说明
        # 方向，不再额外加「水平 / 垂直」两个分组词——那两个词占 56px，而这张卡
        # 的最小宽度正好卡在模块视口边上（多了就出横向滚动条）
        row_h = card.add_row()
        # 这一行有 12 个控件，默认 8px 行距会白吃掉 ~90px，把最小宽度顶到视口
        # 之外（窗口拉到 1300 就出横向滚动条）。4px 已经足够分辨「标签+输入框」
        # 这一组，组内 4px、组间 12px 的层次也还看得出来。
        row_h.setSpacing(4)
        for label, box in (("HFP", self.t_hfp), ("HBP", self.t_hbp),
                           ("HSW", self.t_hsw)):
            row_h.addWidget(W.field_label(label, card))
            row_h.addWidget(box)
            row_h.addSpacing(4)
        row_h.addSpacing(12)
        for label, box in (("VFP", self.t_vfp), ("VBP", self.t_vbp),
                           ("VSW", self.t_vsw)):
            row_h.addWidget(W.field_label(label, card))
            row_h.addWidget(box)
            row_h.addSpacing(4)
        row_h.addStretch()

        card.add(W.separator(card))

        # ---- 第 2 段：DPI 分频（标题行右侧放操作按钮，省一行高度）----
        dpi_head = card.add_row()
        dpi_head.addWidget(W.heading("DPI 时钟分频", card))
        dpi_head.addSpacing(10)
        self.dpi_note_label = W.heading("", card)
        dpi_head.addWidget(self.dpi_note_label)
        dpi_head.addStretch()

        # 按钮名从「从剪贴板解析 / 从设备读取」缩短：这两个名字加起来占了
        # 235px，是这张卡最小宽度的主要来源，而模块宽度刚好卡在视口边上
        paste_btn = W.soft_button("剪贴板解析", "download", card)
        paste_btn.setToolTip("把屏体 spec / dmesg / DTS 片段粘进剪贴板，自动填好上面的参数")
        paste_btn.clicked.connect(self.parse_timing_clipboard)
        dpi_head.addWidget(paste_btn)
        grab_btn = W.soft_button("设备读取", "refresh", card)
        grab_btn.setToolTip("执行 dumpsys display 并尝试解析分辨率与刷新率")
        grab_btn.clicked.connect(self.grab_timing_from_device)
        dpi_head.addWidget(grab_btn)
        reset_btn = W.soft_button("复位", None, card)
        reset_btn.setToolTip("恢复成 1080x2400@60 / RGB888 / 4 lane 的默认值")
        reset_btn.clicked.connect(self.reset_timing)
        dpi_head.addWidget(reset_btn)

        dpi_row = card.add_row()
        dpi_row.addWidget(W.field_label("时钟源", card))
        self.t_dpi_src = QSpinBox(card)
        self.t_dpi_src.setRange(1, 4000)
        self.t_dpi_src.setValue(384)
        self.t_dpi_src.setSuffix(" MHz")
        self.t_dpi_src.setFixedWidth(78)
        self.t_dpi_src.setMinimumHeight(28)
        self.t_dpi_src.setAlignment(Qt.AlignCenter)
        self.t_dpi_src.setToolTip(
            "SoC 的 DPI 时钟源频率；T820 是 384 MHz。\n"
            "屏体需求的 pclk 由它整数分频得到，凑不出整数就会掉帧。")
        self.t_dpi_src.valueChanged.connect(self._recalc_timing)
        dpi_row.addWidget(self.t_dpi_src)

        self.t_dpi_auto = QCheckBox("自动分频", card)
        self.t_dpi_auto.setChecked(True)
        self.t_dpi_auto.setToolTip(
            "按 INT(源/需求) 取整数商；余数超过半个像素时钟时商 +1")
        self.t_dpi_auto.stateChanged.connect(self._on_dpi_auto_toggled)
        dpi_row.addWidget(self.t_dpi_auto)

        dpi_row.addWidget(W.field_label("分频", card))
        self.t_dpi_div = QSpinBox(card)
        self.t_dpi_div.setRange(1, 255)
        self.t_dpi_div.setValue(1)
        self.t_dpi_div.setFixedWidth(52)
        self.t_dpi_div.setMinimumHeight(28)
        self.t_dpi_div.setAlignment(Qt.AlignCenter)
        self.t_dpi_div.setEnabled(False)
        self.t_dpi_div.valueChanged.connect(self._recalc_timing)
        dpi_row.addWidget(self.t_dpi_div)

        dpi_row.addSpacing(12)
        self.dpi_result_label = QLabel("--", card)
        self.dpi_result_label.setObjectName("kvValue")
        self.dpi_result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dpi_row.addWidget(self.dpi_result_label)
        dpi_row.addStretch()

        card.add(W.separator(card))

        # ---- 第 3 段：结果（8 项 4 列 × 2 行）----
        result_grid = QGridLayout()
        result_grid.setHorizontalSpacing(10)
        result_grid.setVerticalSpacing(4)
        self.timing_values = {}
        for index, (name, _value, _note) in enumerate(self._timing_rows_placeholder()):
            name_label = W.field_label(name, card)
            value_label = QLabel("--", card)
            value_label.setObjectName("kvValue")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.timing_values[name] = value_label
            result_grid.addWidget(name_label, index // 4 * 2, index % 4)
            result_grid.addWidget(value_label, index // 4 * 2 + 1, index % 4)
        for col in range(4):
            result_grid.setColumnStretch(col, 1)
        card.add_layout(result_grid)

        self.timing_hint = W.heading("", card)
        card.add(self.timing_hint)

        self._recalc_timing()
        return card

    @staticmethod
    def _timing_rows_placeholder():
        """先按最终行名建一遍标签，数值后面再填。"""
        return timing_mod.Timing().rows()

    # 「Panel 参数查询」卡片已按 func-list 移除（编号 38）：
    # 那 6 个按钮都是纯查询命令，Ctrl+K 命令面板里搜得到，不必占一块版面。

    # ================= 交互 =================

    def _on_bright_typed(self):
        try:
            value = max(0, min(255, int(self.bright_value.text())))
        except ValueError:
            return
        self.bright_slider.setValue(value)

    # ---------- 时序 / 带宽 ----------

    def current_timing(self):
        return timing_mod.Timing(
            width=self.t_w.value(), height=self.t_h.value(), fps=self.t_fps.value(),
            hfp=self.t_hfp.value(), hbp=self.t_hbp.value(), hsw=self.t_hsw.value(),
            vfp=self.t_vfp.value(), vbp=self.t_vbp.value(), vsw=self.t_vsw.value(),
            bpp=self.t_bpp.currentData(), lanes=self.t_lanes.currentData(),
            dpi_source=self.t_dpi_src.value() * 1000000,
            dpi_divisor=0 if self.t_dpi_auto.isChecked() else self.t_dpi_div.value())

    @staticmethod
    def _retone(label, tone):
        label.setProperty("tone", tone)
        label.style().unpolish(label)
        label.style().polish(label)

    def _on_dpi_auto_toggled(self, _state):
        """自动分频时把分频框锁上，并显示当前自动算出来的值。"""
        self._recalc_timing()

    def reset_timing(self):
        """回到默认屏体参数。"""
        for box, value in ((self.t_w, 1080), (self.t_h, 2400), (self.t_fps, 60),
                           (self.t_hfp, 40), (self.t_hbp, 40), (self.t_hsw, 10),
                           (self.t_vfp, 20), (self.t_vbp, 20), (self.t_vsw, 4)):
            box.setValue(value)
        self.t_bpp.setCurrentIndex(0)
        self.t_lanes.setCurrentText("4")
        self.t_dpi_src.setValue(384)
        self.t_dpi_auto.setChecked(True)
        self._recalc_timing()
        self._toast("时序参数已复位", "info", 1800)

    def _recalc_timing(self, *_args):
        if not getattr(self, "timing_values", None):
            return
        timing = self.current_timing()

        # --- DPI 分频区：自动时把算出来的分频填进框里（只读展示）---
        divisor = timing.divisor
        if self.t_dpi_auto.isChecked():
            if self.t_dpi_div.value() != divisor:
                self.t_dpi_div.blockSignals(True)
                self.t_dpi_div.setValue(divisor)
                self.t_dpi_div.blockSignals(False)
            self.t_dpi_div.setEnabled(False)
        else:
            self.t_dpi_div.setEnabled(True)

        self.dpi_result_label.setText(
            "实际 pclk {:.2f} MHz · {:.1f} fps".format(
                timing.actual_pclk_hz / 1e6, timing.actual_fps))
        # 实际帧率比需求低 5% 以上就值得看一眼：屏体可能会闪或者被上层限帧
        fps_error = (timing.actual_fps - timing.fps) / timing.fps if timing.fps else 0
        self._retone(self.dpi_result_label,
                     "ok" if fps_error > -0.05 else "warn")
        self.dpi_note_label.setText(timing.divisor_note)
        self.dpi_note_label.setToolTip(
            "需求 pclk {:.2f} MHz ÷ 时钟源 {:.0f} MHz = {:.3f}\n"
            "取整后的余数决定分频比：余数超过半个像素时钟就商 +1。".format(
                timing.pclk_hz / 1e6, timing.dpi_source / 1e6,
                timing.pclk_hz / timing.dpi_source if timing.dpi_source else 0))

        # --- 结果区 ---
        for name, value, note in timing.rows():
            label = self.timing_values.get(name)
            if label is None:
                continue
            label.setText(value)
            # 每 lane 超限时标色：这是"链路跑不跑得动"的结论
            tone = "default"
            if name == "每 lane 需求":
                tone = timing.per_lane_tone()
            elif name == "实际帧率":
                tone = "ok" if fps_error > -0.05 else "warn"
            label.setToolTip(note)
            self._retone(label, tone)
        self.timing_hint.setText("　".join(
            note for name, _v, note in timing.rows() if name == "每 lane 需求"))

    # 解析结果的中文名：给用户看"解析到了什么"，比一堆英文键名有用
    TIMING_FIELD_NAMES = {
        "width": "分辨率宽", "height": "分辨率高", "fps": "刷新率",
        "hfp": "水平前肩", "hbp": "水平后肩", "hsw": "水平同步",
        "vfp": "垂直前肩", "vbp": "垂直后肩", "vsw": "垂直同步",
        "bpp": "像素格式", "lanes": "lane 数",
    }
    # 这几项缺了就算"没解析成功"，其余缺项只是保留原值
    TIMING_REQUIRED = ("width", "height", "hfp", "hbp", "hsw", "vfp", "vbp", "vsw")

    def parse_timing_clipboard(self):
        """从剪贴板解析时序，解析到几个就填几个。"""
        from PyQt5.QtWidgets import QApplication

        text = QApplication.clipboard().text()
        if not text.strip():
            self._toast("剪贴板是空的", "warning")
            return {}
        found = timing_mod.parse_timing_text(text)
        if not found:
            self._toast("没从剪贴板里认出时序参数——可以贴 DTS 片段、"
                        "spec 表格或 dumpsys 输出", "warning", 4200)
            return {}
        self._fill_timing(found)
        names = [self.TIMING_FIELD_NAMES.get(k, k) for k in sorted(found)]
        missing = [self.TIMING_FIELD_NAMES[k] for k in self.TIMING_REQUIRED
                   if k not in found]
        if missing:
            # 只认出一半时要说清楚缺什么，否则用户以为界面没反应
            self._toast("解析到 {} 项：{}；缺 {}".format(
                len(found), "、".join(names), "、".join(missing)),
                "warning", 5200)
        else:
            self._toast("解析到 {} 项：{}".format(len(found), "、".join(names)),
                        "success", 4200)
        return found

    def grab_timing_from_device(self):
        """抓 dumpsys display，能解析出分辨率/刷新率就直接填上。"""
        def on_result(_code, output):
            hits = timing_mod.parse_timing_text(output or "")
            if not hits:
                self._toast("dumpsys display 里没找到可解析的时序字段", "warning", 3600)
                return
            self._fill_timing(hits)

        self.runner.run("dumpsys display", "读取显示时序", on_result=on_result)

    def _fill_timing(self, found):
        """把解析结果填进输入框（剪贴板与设备读取共用）。"""
        mapping = {
            "width": self.t_w, "height": self.t_h, "fps": self.t_fps,
            "hfp": self.t_hfp, "hbp": self.t_hbp, "hsw": self.t_hsw,
            "vfp": self.t_vfp, "vbp": self.t_vbp, "vsw": self.t_vsw,
        }
        for key, box in mapping.items():
            if key in found:
                box.setValue(max(box.minimum(), min(box.maximum(), found[key])))
        if "bpp" in found:
            index = self.t_bpp.findData(found["bpp"])
            if index >= 0:
                self.t_bpp.setCurrentIndex(index)
        if "lanes" in found:
            index = self.t_lanes.findData(found["lanes"])
            if index >= 0:
                self.t_lanes.setCurrentIndex(index)
        self._recalc_timing()

    def build_dcs(self):
        """按参数个数自动选 DCS 短包/长包，生成字节序列。"""
        command = timing_mod.parse_hex_bytes(self.dcs_cmd.text())
        if len(command) != 1:
            self._toast("命令要正好 1 个字节，例如 0x1a", "error", 3200)
            self.dcs_kind_label.setText("命令要正好 1 个字节，例如 0x1a")
            return None
        params = timing_mod.parse_hex_bytes(self.dcs_params.text())
        if len(params) > 0xFF:
            self._toast("参数过多（长包负载最长 255 字节）", "error", 3200)
            self.dcs_kind_label.setText("参数过多：长包负载最长 255 字节")
            return None
        sequence = timing_mod.build_dcs_sequence(command[0], params)
        text = " ".join("0x{:02x}".format(b) for b in sequence)
        self.dcs_data.setText(text)
        kind = timing_mod.dcs_kind(command[0], params)
        self.dcs_kind_label.setText("{} · 共 {} 字节（{} 字节负载 + 4 字节包头）"
                                    .format(kind, len(sequence), len(params) + 1))
        self._toast("已生成 {} 字节（{}）".format(len(sequence), kind),
                    "success", 2600)
        return sequence

    def copy_dcs(self):
        text = self.dcs_data.text().strip()
        if not text:
            self._toast("先点「生成」", "warning", 2000)
            return None
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self._toast("字节序列已复制", "success", 1800)
        return text

    def _toast(self, message, kind="info", duration=2200):
        window = self.window()
        if hasattr(window, "toast"):
            window.toast(message, kind, duration)

    def set_brightness(self):
        """走框架设置亮度（会被系统的亮度曲线处理）。"""
        value = self.bright_value.text().strip()
        if not value:
            return
        self.runner.run(
            f'settings put system screen_brightness {value}',
            f"背光设置为 {value}")

    def set_brightness_node(self):
        """直接写背光 sysfs 节点（真实 PWM 值，需要 root）。

        节点位置跟平台有关，所以按 panel0-backlight → sprd_backlight 顺序试，
        第一个写成功就停；写不进去（没有节点 / 没 root）时错误信息会留在输出面板。
        """
        value = self.bright_value.text().strip()
        if not value:
            return
        if not value.isdigit():
            self._toast("亮度值要是数字", "warning", 2600)
            return
        self.runner.run(
            _write_all("brightness", value),
            "写背光节点 {}（{}）".format(value, " 或 ".join(BACKLIGHT_DIRS)))

    def get_brightness(self):
        """读当前亮度：框架值 + 节点值（两个来源经常不一致，都看才知道谁在生效）。"""
        self.runner.run('settings get system screen_brightness',
                        "读取 settings 亮度")
        self.runner.run(BRIGHTNESS_READ, "读取背光节点 brightness")
        if self.bright_max_check.isChecked():
            self.runner.run(MAX_BRIGHTNESS_READ, "读取 max_brightness")
            self.runner.run(ACTUAL_BRIGHTNESS_READ, "读取 actual_brightness")

    def read_resolution(self):
        """读当前分辨率（wm size 的 Physical/Override 两行都读出来）。"""
        self.runner.run("wm size", "读取分辨率")

    def apply_resolution(self):
        value = self.res_combo.currentText().strip()
        if value:
            self.runner.run(f'wm size {value}', f"分辨率设置为 {value}")

    def read_density(self):
        self.runner.run("wm density", "读取屏幕密度")

    def apply_density(self):
        value = self.density_combo.currentText().strip()
        if not value:
            return
        if not value.isdigit():
            self._toast("密度要是数字（dpi），例如 320", "warning", 2800)
            return
        self.runner.run(f'wm density {value}', f"密度设置为 {value}")

    def apply_refresh_rate(self):
        value = self.fps_combo.currentText().strip()
        if value:
            self.runner.run(
                f'settings put system peak_refresh_rate {value}',
                f"刷新率设置为 {value}")

    def read_refresh_rate(self):
        self.runner.run(
            "dumpsys display | grep -m1 -o 'fps=[0-9.]*'",
            "读取刷新率")

    # DCS 读写节点与 ESD 重置已按 func-list 移除（编号 31/32/33）：
    # 屏体写入现在统一走 Shell Tools 的自定义命令，这边只负责算字节序列。

    def on_page_shown(self):
        self.bright_slider.setFocus()

    def stop_background(self):
        """用的是共享 runner，由 CommonToolsPage 统一停止。"""
        pass
