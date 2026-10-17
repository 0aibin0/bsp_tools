"""常用工具 · 显示调试（LCM）

面向屏体调试的常用操作：背光、分辨率、刷新率、DCS 包构造，外加时序/带宽
计算——给一组前后沿就能算出 pixel clock 和每 lane 速率，判断这条 DSI 链路
跑不跑得动。命令在本模块内执行并把输出显示在右侧结果面板，不会把用户弹到
Shell Tools 页。

DCS 直接读写节点和 ESD 重置按钮已按 func-list 移除（屏体写入走 Shell Tools
的自定义命令），这里只负责把字节序列算准。
"""

import math

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QComboBox, QLineEdit, QSlider, QLabel, QCheckBox,
                             QSpinBox, QDoubleSpinBox, QSizePolicy)

import theme
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

#: 背光节点的满量程兜底值。
#:
#: 这两条路径的量程**不一样**，以前共用一个 0..255 的输入框，导致「写节点」
#: 最多只能写到 1023 的 1/4：
#:   - 框架 `settings put system screen_brightness`：Android 默认 0..255
#:   - 节点 `/sys/class/backlight/<node>/brightness`：0..max_brightness
#:     （T820 是 10bit DBV，满量程 1023，即 节点值 = HAL value × 1023）
#: 进页面会自动读一次 max_brightness 覆盖这个兜底值。
NODE_MAX_DEFAULT = 1023
#: 框架侧 screen_brightness 的量程（Android 默认 0..255）
FRAMEWORK_MAX = 255


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


def screen_dpi(width_px, height_px, diagonal_in=0.0,
               phys_w_mm=0.0, phys_h_mm=0.0):
    """按物理尺寸算屏幕 DPI（PPI），物理尺寸给对角线或宽×高都行。

    注意这里的 DPI 是「每英寸像素数」，和下面时序卡里的「DPI 时钟分频」
    不是一回事——后者是显示控制器像素时钟的整数分频。

    规则：
    - 给了对角线（inch）就直接用，同时按分辨率比例反推物理宽高；
    - 只给了物理宽或高时，按分辨率比例补齐另一边；
    - 都没有（或像素尺寸非法）返回 None。

    PPI = sqrt(w² + h²) ÷ 对角线(inch)，点距 = 25.4 ÷ PPI。
    """
    width_px = max(int(width_px), 0)
    height_px = max(int(height_px), 0)
    if width_px <= 0 or height_px <= 0:
        return None

    diag_px = math.hypot(width_px, height_px)
    phys_w = float(phys_w_mm or 0)
    phys_h = float(phys_h_mm or 0)
    if phys_w > 0 and phys_h <= 0:
        phys_h = phys_w * height_px / width_px
    elif phys_h > 0 and phys_w <= 0:
        phys_w = phys_h * width_px / height_px

    if diagonal_in and float(diagonal_in) > 0:
        diag_in = float(diagonal_in)
        if phys_w <= 0 or phys_h <= 0:
            phys_w = diag_in * 25.4 * width_px / diag_px
            phys_h = diag_in * 25.4 * height_px / diag_px
    elif phys_w > 0 and phys_h > 0:
        diag_in = math.hypot(phys_w, phys_h) / 25.4
    else:
        return None

    if diag_in <= 0:
        return None

    dpi = diag_px / diag_in
    divisor = math.gcd(width_px, height_px) or 1
    return {
        "dpi": dpi,
        "dot_pitch_mm": 25.4 / dpi if dpi else 0.0,
        "diagonal_in": diag_in,
        "phys_w_mm": phys_w,
        "phys_h_mm": phys_h,
        "aspect": "{}:{}".format(width_px // divisor, height_px // divisor),
    }


def screen_size_for_ppi(width_px, height_px, target_ppi):
    """已知分辨率与目标 PPI，反推需要的物理尺寸（选屏/评估用）。

    由 `PPI = 对角线像素 ÷ 对角线(inch)` 得 对角线 = 对角线像素 ÷ 目标 PPI，
    再交给 `screen_dpi()` 按分辨率比例分摊出物理宽高。
    """
    width_px = max(int(width_px), 0)
    height_px = max(int(height_px), 0)
    if width_px <= 0 or height_px <= 0 or not target_ppi or target_ppi <= 0:
        return None
    diag_px = math.hypot(width_px, height_px)
    return screen_dpi(width_px, height_px,
                      diagonal_in=diag_px / float(target_ppi))


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

        # 滑块按**节点量程**走（默认 1023，进页面读到 max_brightness 会更正）：
        # 「写节点」要能直接填 818 这种真实 DBV 值，0..255 根本到不了。
        self.node_max = NODE_MAX_DEFAULT

        row = card.add_row()
        row.addWidget(W.field_label("亮度", card))
        self.bright_slider = QSlider(Qt.Horizontal, card)
        self.bright_slider.setRange(0, self.node_max)
        self.bright_slider.setValue(self.node_max // 2)
        self.bright_slider.setMinimumHeight(28)
        self.bright_slider.setToolTip(
            "节点亮度（0..max_brightness）；「设置」会折算成框架的 0..{}".format(
                FRAMEWORK_MAX))
        self.bright_slider.valueChanged.connect(self._on_bright_changed)
        row.addWidget(self.bright_slider, 1)

        self.bright_value = QLineEdit(card)
        self.bright_value.setText(str(self.node_max // 2))
        self.bright_value.setAlignment(Qt.AlignCenter)
        self.bright_value.setFixedWidth(58)
        self.bright_value.setToolTip("节点值，可直接填 818 这类 DBV 值")
        self.bright_value.returnPressed.connect(self._on_bright_typed)
        row.addWidget(self.bright_value)

        self.bright_set_btn = W.accent_button("设置", None, card)
        self.bright_set_btn.setToolTip(
            "走框架：settings put system screen_brightness（按 {}:{} 折算）".format(
                FRAMEWORK_MAX, self.node_max))
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
        get_btn.setToolTip("读 settings 值 + 背光节点的 brightness / max_brightness")
        get_btn.clicked.connect(self.get_brightness)
        row2.addWidget(get_btn)

        self.bright_max_check = QCheckBox("读 actual", card)
        self.bright_max_check.setToolTip(
            "勾选后额外读 actual_brightness（max_brightness 每次都会读，用来对齐量程）")
        row2.addWidget(self.bright_max_check)

        # 量程提示必须单行：横排里放自动换行标签会把行高顶起来（本月踩过）
        self.bright_hint = QLabel("", card)
        self.bright_hint.setStyleSheet(
            "color: {}; font-size: 12px; background: transparent;".format(
                theme.TEXT_FAINT))
        row2.addWidget(self.bright_hint)
        row2.addStretch()
        self._update_bright_hint()

        # 亮度表生成/校验：放**标题行**里（add_trailing 不占卡片高度）。
        # 之前单独加一行，把背光卡顶高 39px → 整页超过 721 → 结果网格又被压扁。
        map_btn = W.soft_button("亮度表…", "grid", card)
        map_btn.setToolTip(
            "生成 / 校验 screenBrightnessMap：value 与 nits 必须非递减，"
            "HBM 要并进顶层表——写错会导致整表被丢弃、system_server 崩溃重启")
        map_btn.clicked.connect(self.open_brightness_map)
        card.add_trailing(map_btn)

        card.add(W.heading(
            "节点路径按平台不同：「设置」走框架 settings（0..{0}），"
            "「写节点」直接写 sysfs（0..{1}，改的是真实 PWM 值，需要 root）。".format(
                FRAMEWORK_MAX, self.node_max), card))
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
        # 行距从默认 9 收到 7：这张卡现在要放「屏体参数 + 屏幕 DPI + 时钟分频
        # + 8 项结果」四段，默认行距会把整页顶到 721 视口之外——一旦超出，
        # Qt 会先压结果网格（标签从 17px 压到 12px，看着就是糊成一团）
        card.body.setSpacing(7)

        def spin(value, low, high, width=52, suffix=""):
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

        def dspin(value, low, high, width, suffix, step=0.1, decimals=1):
            """带小数与单位后缀的输入框（屏幕 DPI 用）。"""
            box = QDoubleSpinBox(card)
            box.setRange(low, high)
            box.setDecimals(decimals)
            box.setSingleStep(step)
            box.setValue(value)
            box.setSuffix(suffix)
            box.setFixedWidth(width)
            box.setMinimumHeight(28)
            box.setAlignment(Qt.AlignCenter)
            box.valueChanged.connect(self._recalc_dpi)
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

        # ---- 屏幕 DPI：按物理尺寸换算 ----
        # 像素尺寸直接复用上面的「分辨率」，这里只需要再给一个物理尺寸：
        # 对角线（inch）或宽×高（mm），两种填法随模式切换。
        dpi_calc = card.add_row()
        dpi_calc.setSpacing(4)
        dpi_calc.addWidget(W.field_label("屏幕 DPI", card))

        self.dpi_mode = QComboBox(card)
        self.dpi_mode.addItem("对角线 (in)", "diag")
        self.dpi_mode.addItem("宽 × 高 (mm)", "wh")
        self.dpi_mode.addItem("目标 PPI", "ppi")
        self.dpi_mode.setFixedWidth(128)
        self.dpi_mode.setMinimumHeight(28)
        self.dpi_mode.currentIndexChanged.connect(self._on_dpi_mode_changed)
        dpi_calc.addWidget(self.dpi_mode)
        dpi_calc.addSpacing(6)

        self.dpi_diag = dspin(6.40, 0.5, 40.0, 82, " in", 0.1, 2)
        self.dpi_diag.setToolTip("屏体物理对角线长度，例如手机 6.4 英寸")
        dpi_calc.addWidget(self.dpi_diag)

        self.dpi_phys_w = dspin(68.0, 1.0, 1200.0, 84, " mm", 1.0, 1)
        self.dpi_phys_w.setToolTip("屏体物理宽度（毫米），例如 68.0")
        dpi_calc.addWidget(self.dpi_phys_w)

        self.dpi_times = QLabel("×", card)
        dpi_calc.addWidget(self.dpi_times)

        self.dpi_phys_h = dspin(151.0, 1.0, 1200.0, 84, " mm", 1.0, 1)
        self.dpi_phys_h.setToolTip("屏体物理高度（毫米），例如 151.0")
        dpi_calc.addWidget(self.dpi_phys_h)

        # 反算模式：给定目标 PPI，求需要多大的屏
        self.dpi_target = dspin(400.0, 50.0, 1200.0, 84, " ppi", 10.0, 0)
        self.dpi_target.setToolTip(
            "想要达到的像素密度；用来反推需要多大的对角线 / 物理尺寸")
        dpi_calc.addWidget(self.dpi_target)

        self.dpi_calc_label = QLabel("--", card)
        self.dpi_calc_label.setObjectName("kvValue")
        self.dpi_calc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dpi_calc.addWidget(self.dpi_calc_label)
        dpi_calc.addStretch()

        # 默认按对角线；切换模式时把另一组输入框藏起来（隐藏控件不占布局）
        self._on_dpi_mode_changed()

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
        # 标题也必须单行：这行右侧挤着 3 个按钮，自动换行时它会被压成
        # 「DPI 时钟分」/「频」两行，既难看又把行高顶上去
        dpi_title = W.heading("DPI 时钟分频", card)
        dpi_title.setWordWrap(False)
        dpi_title.setMinimumWidth(96)
        dpi_head.addWidget(dpi_title)
        dpi_head.addSpacing(10)
        # 这行说明必须**单行省略**：放在横排里的自动换行标签高度会随宽度变，
        # 而 QHBoxLayout 不处理 heightForWidth——窄窗口时它从 30px 涨到 60px，
        # 多出来的高度是从下面的结果网格抢的（标签 17 → 12，数值被压扁）。
        # 完整说明放 tooltip。
        self.dpi_note_label = W.ElidedLabel("", card)
        self.dpi_note_label.setStyleSheet(
            "color: {}; font-size: 12px; background: transparent;".format(
                theme.TEXT_FAINT))
        self.dpi_note_label.setMinimumWidth(64)
        self.dpi_note_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        dpi_head.addWidget(self.dpi_note_label, 1)
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

        # 以前这里还有一行 timing_hint（"实际 pclk × bpp ÷ 0.9 ÷ N lane"）：
        # 它和「每 lane 需求」数值的 tooltip 完全重复，而它也是自动换行标签，
        # 放在纵向布局里同样会抢高度，已经删掉。
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
            value = int(self.bright_value.text())
        except ValueError:
            self.bright_value.setText(str(self.bright_slider.value()))
            return
        self.bright_slider.setValue(max(0, min(self.node_max, value)))

    def _on_bright_changed(self, value):
        """滑块是节点量程：同步输入框与「节点/百分比/框架」提示。"""
        self.bright_value.setText(str(value))
        self._update_bright_hint()

    def _percent(self, value):
        return value / self.node_max * 100.0 if self.node_max else 0.0

    def _to_framework(self, value):
        """节点值 → 框架 screen_brightness 的 0..255。"""
        if not self.node_max:
            return 0
        return int(round(value / self.node_max * FRAMEWORK_MAX))

    def _to_node(self, framework):
        """框架 0..255 → 节点值。"""
        return int(round(framework / FRAMEWORK_MAX * self.node_max))

    def _update_bright_hint(self):
        """一行量程提示：节点值 / 满量程 / 百分比 / 折算出的框架值。"""
        if not getattr(self, "bright_hint", None):
            return
        value = self.bright_slider.value()
        self.bright_hint.setText("{}/{} · {:.0f}% · 框架 {}".format(
            value, self.node_max, self._percent(value),
            self._to_framework(value)))

    def _apply_node_max(self):
        """按 max_brightness 重置滑块量程（保留位置：按百分比迁移）。"""
        old_max = getattr(self, "node_max", NODE_MAX_DEFAULT) or NODE_MAX_DEFAULT
        percent = self.bright_slider.value() / old_max if old_max else 0.0
        self.bright_slider.blockSignals(True)
        self.bright_slider.setRange(0, self.node_max)
        self.bright_slider.setValue(int(round(percent * self.node_max)))
        self.bright_slider.blockSignals(False)
        self.bright_value.setText(str(self.bright_slider.value()))
        self._update_bright_hint()

    @staticmethod
    def _last_int(text):
        """从命令输出里取最后一个纯整数行。

        `cat a || cat b` 失败的那条会把 "No such file" 写进输出，成功那条的
        数字在最后，所以倒着找。
        """
        for line in reversed((text or "").splitlines()):
            line = line.strip()
            if line.isdigit():
                return int(line)
        return None

    def _on_node_max(self, _code, output):
        value = self._last_int(output)
        if value and value > 0 and value != self.node_max:
            self.node_max = value
            self._apply_node_max()

    def _on_brightness(self, _code, output):
        value = self._last_int(output)
        if value is not None:
            self.bright_slider.setValue(max(0, min(self.node_max, value)))

    def open_brightness_map(self):
        """打开亮度表（screenBrightnessMap）生成/校验对话框。"""
        import brightness_map_dialog          # 延迟导入：只在点按钮时才建对话框
        brightness_map_dialog.BrightnessMapDialog(self).exec_()

    def refresh_from_device(self, quiet=True):
        """静默读一次设备当前状态（进页面时调，不写结果面板也不弹 toast）。

        亮度/分辨率是进来第一眼就要看的，以前必须手动点「读取」。
        """
        runner = getattr(self, "runner", None)
        if runner is None:
            return
        runner.run(MAX_BRIGHTNESS_READ, "读取 max_brightness",
                   quiet=quiet, on_result=self._on_node_max)
        runner.run(BRIGHTNESS_READ, "读取 brightness",
                   quiet=quiet, on_result=self._on_brightness)
        runner.run("wm size", "读取分辨率", quiet=quiet,
                   on_result=self._on_wm_size)

    def _on_wm_size(self, _code, output):
        """把 wm size 读到的分辨率填进下拉框（优先 Override，其次 Physical）。"""
        override = physical = None
        for line in (output or "").splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            head, _, value = line.partition(":")
            value = value.strip()
            if "x" not in value.lower():
                continue
            if "override" in head.lower():
                override = value
            elif "physical" in head.lower():
                physical = value
        value = override or physical
        if value:
            self.res_combo.setCurrentText(value)

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
        # 屏幕 DPI 的物理尺寸也一起复位（模式回到「按对角线」）
        self.dpi_mode.setCurrentIndex(0)
        self.dpi_diag.setValue(6.40)
        self.dpi_phys_w.setValue(68.0)
        self.dpi_phys_h.setValue(151.0)
        self.dpi_target.setValue(400.0)
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
        # 分辨率改了，屏幕 DPI 也要跟着更新
        self._recalc_dpi()

    # ---------- 屏幕 DPI ----------

    def _on_dpi_mode_changed(self, *_args):
        """切换三种模式：隐藏的输入不占布局宽度。"""
        mode = self.dpi_mode.currentData()
        self.dpi_diag.setVisible(mode == "diag")
        self.dpi_phys_w.setVisible(mode == "wh")
        self.dpi_times.setVisible(mode == "wh")
        self.dpi_phys_h.setVisible(mode == "wh")
        self.dpi_target.setVisible(mode == "ppi")
        self._recalc_dpi()

    def _recalc_dpi(self, *_args):
        """按当前分辨率 + 物理尺寸算 PPI；反算模式下由目标 PPI 求物理尺寸。"""
        if not getattr(self, "dpi_calc_label", None):
            return
        width_px, height_px = self.t_w.value(), self.t_h.value()
        mode = self.dpi_mode.currentData()
        if mode == "diag":
            info = screen_dpi(width_px, height_px,
                              diagonal_in=self.dpi_diag.value())
        elif mode == "wh":
            info = screen_dpi(width_px, height_px,
                              phys_w_mm=self.dpi_phys_w.value(),
                              phys_h_mm=self.dpi_phys_h.value())
        else:
            info = screen_size_for_ppi(width_px, height_px,
                                       self.dpi_target.value())

        if info is None:
            self.dpi_calc_label.setText("--")
            self.dpi_calc_label.setToolTip("")
            return

        if mode == "ppi":
            self.dpi_calc_label.setText(
                "需对角线 {:.2f} in · 物理 {:.1f}×{:.1f} mm".format(
                    info["diagonal_in"], info["phys_w_mm"], info["phys_h_mm"]))
        else:
            self.dpi_calc_label.setText(
                "{:.1f} dpi · 点距 {:.4f} mm · {:.2f} in".format(
                    info["dpi"], info["dot_pitch_mm"], info["diagonal_in"]))
        self.dpi_calc_label.setToolTip(
            "{}×{} px · 物理 {:.1f}×{:.1f} mm · 对角线 {:.2f} in · "
            "宽高比 {} · {:.1f} dpi\n"
            "PPI = sqrt(宽² + 高²) ÷ 对角线；点距 = 25.4 ÷ PPI".format(
                width_px, height_px, info["phys_w_mm"], info["phys_h_mm"],
                info["diagonal_in"], info["aspect"], info["dpi"]))

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
        # 负载 = 1 个命令字节 + N 个参数，而长度字节只有 1 字节（上限 255），
        # 所以参数最多 254 个。以前判的是 > 0xFF（允许 255 个），payload 会变成
        # 256，长度字节被格式化成 0x100（三位十六进制），整条序列不可用。
        if len(params) > 0xFE:
            self._toast("参数最多 254 个（负载 = 命令 + 参数 ≤ 255 字节）",
                        "error", 3200)
            self.dcs_kind_label.setText("参数过多：最多 254 个（负载上限 255 字节）")
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

    def _current_node_value(self):
        """当前要下发的节点值：输入框优先（用户可能敲完没按回车）。"""
        text = self.bright_value.text().strip()
        if text.isdigit():
            return max(0, min(self.node_max, int(text)))
        return self.bright_slider.value()

    def set_brightness(self):
        """走框架设置亮度（会被系统的亮度曲线处理）。

        输入框是**节点量程**（0..max_brightness），这里折算成框架的 0..255
        再下发——两条路径量程不同，以前直接把节点值当框架值发，等于写错了。
        """
        value = self._current_node_value()
        framework = self._to_framework(value)
        self.runner.run(
            'settings put system screen_brightness {}'.format(framework),
            "背光设置为 {}（节点 {} / {}，{:.0f}%）".format(
                framework, value, self.node_max, self._percent(value)))

    def set_brightness_node(self):
        """直接写背光 sysfs 节点（真实 PWM 值，需要 root）。

        节点位置跟平台有关，所以按 panel0-backlight → sprd_backlight 顺序试，
        第一个写成功就停；写不进去（没有节点 / 没 root）时错误信息会留在输出面板。
        写的是节点原值，不做折算。
        """
        value = self._current_node_value()
        self.runner.run(
            _write_all("brightness", value),
            "写背光节点 {} / {}（{:.0f}%）（{}）".format(
                value, self.node_max, self._percent(value),
                " 或 ".join(BACKLIGHT_DIRS)))

    def get_brightness(self):
        """读当前亮度：框架值 + 节点值（两个来源经常不一致，都看才知道谁在生效）。

        max_brightness 每次都会读——节点量程要靠它对，不能只在勾选时才读。
        """
        self.runner.run('settings get system screen_brightness',
                        "读取 settings 亮度")
        self.runner.run(BRIGHTNESS_READ, "读取背光节点 brightness",
                        on_result=self._on_brightness)
        self.runner.run(MAX_BRIGHTNESS_READ, "读取 max_brightness",
                        on_result=self._on_node_max)
        if self.bright_max_check.isChecked():
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
        """进页面就静默读一次设备状态：亮度量程、当前亮度、分辨率。

        以前这里只 setFocus，用户每次进来都得手动点「读取」。
        """
        self.bright_slider.setFocus()
        self.refresh_from_device(quiet=True)

    def stop_background(self):
        """用的是共享 runner，由 CommonToolsPage 统一停止。"""
        pass
