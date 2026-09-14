"""MIPI DSI 时序与带宽计算（含 T820 DPI 分频）。

屏体评估时天天要算的东西：给分辨率和前后沿，算 pixel clock、DSI 总带宽、
每 lane 速率，判断这条链路跑不跑得动。公式集中在这里，界面和自测共用，
避免"界面上算一套、文档里写一套"。

除了通用的时序公式，这里还实现了 `t820-lcm-porch.xlsx` 里那套 **DPI 分频**
逻辑——屏体要的像素时钟往往凑不出整数，得拿 SoC 的 DPI 时钟源去除：

    Dpi_need_clk = (hfp+hbp+hsync+width) × (vfp+vbp+vsync+height) × fps
    dividor      = INT(SRC / need)，若 (SRC - dividor×need) > need/2 则 dividor+1
    实际帧率      = (SRC / dividor) / (h_total × v_total)
    每 lane 需求  = (SRC / dividor) × bpp / 0.9 / lanes

那个 0.9 是 DSI 的带宽效率（协议开销、blanking 期间不能传数据），
所以判定式是 `实际pclk × bpp < phy_freq × lanes × 0.9`。

术语（和屏体 spec 对齐）：
    hfp/hbp/hsw 水平前肩/后肩/同步宽度，vfp/vbp/vsw 垂直方向
    h_total = width + hfp + hbp + hsw
    v_total = height + vfp + vbp + vsw
    pclk    = h_total × v_total × fps
"""

import re

# D-PHY 各版本的单 lane 上限（Gbps）。超过就要靠更高版本或 DSC 压缩。
DPHY_LIMITS = [
    ("D-PHY v1.1", 1.0),
    ("D-PHY v1.2", 1.5),
    ("D-PHY v2.0", 2.5),
    ("D-PHY v2.1/v3.0", 4.5),
]

# DSI 带宽效率：协议开销 + blanking 期间不传数据，只能按九成算
DSI_EFFICIENCY = 0.9

# 常见平台的 DPI 时钟源（Hz），给界面做预设
DPI_SOURCES = [
    ("T820 / 展锐 384 MHz", 384000000),
    ("通用 300 MHz", 300000000),
    ("通用 266 MHz", 266000000),
    ("通用 200 MHz", 200000000),
]

BPP_PRESETS = {
    "RGB888 (24bpp)": 24,
    "RGB666 (18bpp)": 18,
    "RGB565 (16bpp)": 16,
    "DSC 8bpp": 8,
    "DSC 6bpp": 6,
}


def _int(value, fallback=0):
    try:
        return int(round(float(str(value).strip())))
    except (TypeError, ValueError):
        return fallback


class Timing:
    """一组显示时序参数及其派生量。"""

    def __init__(self, width=1080, height=2400, fps=60,
                 hfp=40, hbp=40, hsw=10, vfp=20, vbp=20, vsw=4,
                 bpp=24, lanes=4,
                 dpi_source=384000000, dpi_divisor=0):
        self.width = _int(width, 1080)
        self.height = _int(height, 2400)
        self.fps = _int(fps, 60)
        self.hfp = _int(hfp, 0)
        self.hbp = _int(hbp, 0)
        self.hsw = _int(hsw, 0)
        self.vfp = _int(vfp, 0)
        self.vbp = _int(vbp, 0)
        self.vsw = _int(vsw, 0)
        self.bpp = _int(bpp, 24)
        self.lanes = max(1, _int(lanes, 4))
        self.dpi_source = _int(dpi_source, 384000000)
        # 0 = 自动分频，非 0 = 用户手动指定
        self.dpi_divisor = max(0, _int(dpi_divisor, 0))

    # ---------- 派生量 ----------

    @property
    def h_total(self):
        return self.width + self.hfp + self.hbp + self.hsw

    @property
    def v_total(self):
        return self.height + self.vfp + self.vbp + self.vsw

    @property
    def pclk_hz(self):
        """屏体需求的像素时钟。"""
        return self.h_total * self.v_total * self.fps

    @property
    def bitrate_bps(self):
        return self.pclk_hz * self.bpp

    @property
    def per_lane_bps(self):
        """按需求时钟算的每 lane 原始负载（不含 0.9 效率）。"""
        return self.bitrate_bps / self.lanes

    @property
    def blanking_ratio(self):
        total = self.h_total * self.v_total
        active = self.width * self.height
        return 1.0 - (active / total) if total else 0.0

    # ---------- DPI 分频（T820 那套） ----------

    def auto_divisor(self):
        """按 xlsx 的规则选分频比，返回 (分频, 余数, 说明)。

        `INT(SRC/need)` 拿到整数商；余数超过半个像素时钟时说明 SRC 更接近
        下一个整数倍，于是商 +1（实际帧率会低于需求，是安全方向）。
        """
        need = self.pclk_hz
        if need <= 0:
            return 1, 0, "需求时钟为 0，分频取 1"
        quotient = int(self.dpi_source // need)
        if quotient < 1:
            divisor = 1
            return (divisor, self.dpi_source - divisor * need,
                    "时钟源低于需求，分频夹到 1——实际帧率达不到 {:.0f} fps".format(self.fps))
        remainder = self.dpi_source - quotient * need
        if need / 2.0 > remainder:
            return quotient, remainder, "余数 {:.2f} MHz < 半个像素时钟，取整数商".format(
                remainder / 1e6)
        divisor = quotient + 1
        return (divisor, self.dpi_source - divisor * need,
                "余数 {:.2f} MHz > 半个像素时钟，商 +1（实际帧率略低于需求）".format(
                    remainder / 1e6))

    @property
    def divisor(self):
        if self.dpi_divisor:
            return self.dpi_divisor
        return self.auto_divisor()[0]

    @property
    def divisor_note(self):
        if self.dpi_divisor:
            return "手动指定分频 {}".format(self.dpi_divisor)
        return self.auto_divisor()[2]

    @property
    def actual_pclk_hz(self):
        """分频后实际跑出来的像素时钟。"""
        return self.dpi_source / self.divisor if self.divisor else 0.0

    @property
    def actual_fps(self):
        total = self.h_total * self.v_total
        return self.actual_pclk_hz / total if total else 0.0

    @property
    def per_lane_required_bps(self):
        """每 lane 需要的 PHY 速率：实际 pclk × bpp / 0.9 / lane 数。"""
        return self.actual_pclk_hz * self.bpp / DSI_EFFICIENCY / self.lanes

    def per_lane_tone(self):
        """每 lane 需求的健康档：ok / warn / bad。

        阈值直接取 D-PHY 版本表，避免界面上的颜色和文字说明两套标准：
        1.0Gbps 以内随便跑（ok）；到 4.5Gbps 还能靠 D-PHY 2.1/3.0（warn）；
        再高就必须上 DSC 压缩了（bad）。
        """
        per_lane = self.per_lane_required_bps / 1e9
        if per_lane <= DPHY_LIMITS[0][1]:
            return "ok"
        if per_lane <= DPHY_LIMITS[-1][1]:
            return "warn"
        return "bad"

    def dphy_verdict(self):
        per_lane = self.per_lane_required_bps / 1e9
        for name, limit in DPHY_LIMITS:
            if per_lane <= limit:
                return "{} 可满足（上限 {:.1f} Gbps/lane）".format(name, limit)
        return "超过所有 D-PHY 上限，需要 DSC 压缩或增加 lane"

    # ---------- 展示 ----------

    def rows(self):
        """给界面结果网格用的 (项目, 数值, 说明)，固定 8 项。"""
        fps_error = (self.actual_fps - self.fps) / self.fps if self.fps else 0.0
        return [
            ("水平总计 h_total", "{} px".format(self.h_total),
             "width {} + hfp {} + hbp {} + hsw {}".format(
                 self.width, self.hfp, self.hbp, self.hsw)),
            ("垂直总计 v_total", "{} px".format(self.v_total),
             "height {} + vfp {} + vbp {} + vsw {}".format(
                 self.height, self.vfp, self.vbp, self.vsw)),
            ("需求 pclk", "{:.2f} MHz".format(self.pclk_hz / 1e6),
             "h_total × v_total × {} Hz".format(self.fps)),
            ("实际 pclk", "{:.2f} MHz".format(self.actual_pclk_hz / 1e6),
             "时钟源 {:.0f} MHz ÷ {}".format(self.dpi_source / 1e6, self.divisor)),
            ("实际帧率", "{:.1f} fps".format(self.actual_fps),
             "实际 pclk ÷ (h_total × v_total)；与需求差 {:+.1%}".format(fps_error)),
            ("DSI 负载", "{:.3f} Gbps".format(
                self.actual_pclk_hz * self.bpp / 1e9),
             "实际 pclk × {} bpp（原始负载）".format(self.bpp)),
            ("每 lane 需求", "{:.3f} Gbps".format(
                self.per_lane_required_bps / 1e9),
             "实际 pclk × bpp ÷ {} ÷ {} lane · {}".format(
                 DSI_EFFICIENCY, self.lanes, self.dphy_verdict())),
            ("消隐占比", "{:.1%}".format(self.blanking_ratio),
             "消隐区占整帧比例，过高说明前后沿偏大"),
        ]

    def summary(self):
        return ("{}x{} @{}Hz · {}bpp · {}lane · 需求 {:.1f}MHz · "
                "实际 {:.1f}MHz/{}fps · {:.2f}Gbps/lane").format(
            self.width, self.height, self.fps, self.bpp, self.lanes,
            self.pclk_hz / 1e6, self.actual_pclk_hz / 1e6,
            round(self.actual_fps), self.per_lane_required_bps / 1e9)


# ================= 文本解析 =================

# 屏体 spec、dmesg、debugfs、设备树（DTS）、内核驱动里键名的写法五花八门，
# 这里都收进来。两个维度都要松：
#
# 1) 分隔符：下划线 / 空格 / 连字符
#      HORIZONTAL_BACK_PORCH = 0x28    ← 屏体 spec
#      horizontal back porch: 0x28     ← 口语化文档
#      hback-porch = <32>;             ← 设备树
#      qcom,mdss-dsi-h-pulse-width = <4>;  ← 高通风格，词序还不一样
# 2) 值的包法：裸数字 / DTS 尖括号 / 方括号 / 引号
#      hfp = 40 / hfp: 40 / hactive = <1080>; / "width" = [0x438]
#
# 所以键名用「词根 + 分隔符」拼装，而不是写死几种字符串。
_SEP = r"[_\s\-]?"
_H = r"(?:horizontal|horizon|h)"
_V = r"(?:vertical|vert|v)"
# 同步宽度的各种叫法：width / len（DTS）/ pulse（qcom）
_SYNC_W = r"(?:width|len|pulse|pw)"


def _k(*parts):
    """把词根用「下划线 / 空格 / 连字符」拼成键名模式。

    _k("h", "front", "porch") → ``h[_\\s-]?front[_\\s-]?porch``
    """
    return _SEP.join(parts)


_FIELDS = {
    "hfp": r"(?:hfp|{}|{})".format(
        _k(_H, "front", "porch"), _k("h", "sync", "front")),
    "hbp": r"(?:hbp|{}|{})".format(
        _k(_H, "back", "porch"), _k("h", "sync", "back")),
    "hsw": r"(?:hsw|hsa|{}|{})".format(
        _k("h", "sync", _SYNC_W), _k("h", "pulse", "width")),
    "vfp": r"(?:vfp|{}|{})".format(
        _k(_V, "front", "porch"), _k("v", "sync", "front")),
    "vbp": r"(?:vbp|{}|{})".format(
        _k(_V, "back", "porch"), _k("v", "sync", "back")),
    "vsw": r"(?:vsw|vsa|{}|{})".format(
        _k("v", "sync", _SYNC_W), _k("v", "pulse", "width")),
    "width": r"(?:{}|width|xres)".format(_k("h", "active")),
    "height": r"(?:{}|height|yres)".format(_k("v", "active")),
    "fps": r"(?:fps|{}|{})".format(_k("refresh", "rate"), _k("frame", "rate")),
    "bpp": r"(?:bpp|{}|{})".format(_k("bits", "per", "pixel"),
                                   _k("color", "depth")),
    # lane 数：lane_num / num_lanes / data-lanes / lanes 都算
    "lanes": r"(?:lanes?|{}|{}|{}|{}|{})".format(
        _k("data", "lanes?"), _k("lane", "num"), _k("lane", "count"),
        _k("lane", "number"), _k("num", "lanes?")),
}

# 十六进制必须排在前面：否则 "0x28" 会被 [0-9]+ 先吃掉 "0"
_NUMBER = r"(0x[0-9a-fA-F]+|[0-9]+(?:\.[0-9]+)?)"
# 数字外面可能包的括号：DTS 的 <1080>、少数 dump 的 [1080]、引号
_OPEN = r"[<\[\{\"']?"
_CLOSE = r"[>\]\}\"']?"


def _to_int(text):
    text = str(text).strip()
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(round(float(text)))
    except (TypeError, ValueError):
        return None


def parse_timing_text(text):
    """从任意文本里抠时序参数（spec 片段 / dmesg / debugfs 输出都行）。

    找到什么返回什么，缺失的键不出现——调用方负责决定哪些是必填。
    """
    found = {}
    if not text:
        return found
    for key, name in _FIELDS.items():
        # key = value / key: value / key=value / "key" = <value>; / key = [value]
        # 外层 (?:...) 不能省：键名里有 | 分支，不包住的话 \b 和取值部分
        # 只会作用在最后一个分支上
        pattern = r"[\"']?\b(?:{})\b[\"']?\s*[:=]?\s*{}{}{}".format(
            name, _OPEN, _NUMBER, _CLOSE)
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = _to_int(match.group(1))
        if value is None:
            continue
        if key == "fps" and value > 1000:
            # 少部分 dump 里刷新率写成 60000（毫赫兹）
            value = int(round(value / 1000.0))
        found[key] = value

    # 分辨率常见写法：1080x2400 / 1080*2400 / "1080 x 2400"
    if "width" not in found or "height" not in found:
        match = re.search(r"\b(\d{3,5})\s*[x*×]\s*(\d{3,5})\b", text)
        if match:
            found.setdefault("width", int(match.group(1)))
            found.setdefault("height", int(match.group(2)))

    # 刷新率常见写法：@60 / @ 60Hz / 60fps（跟在分辨率后面）
    if "fps" not in found:
        match = re.search(r"@\s*(\d{2,3}(?:\.\d+)?)\s*(?:hz|fps)?", text, re.I)
        if match:
            found["fps"] = int(round(float(match.group(1))))

    # 兜底：DTS 里刷新率常常只写在注释里，例如 `vfront-porch = <56>;//60hz`
    if "fps" not in found:
        match = re.search(r"\b(\d{2,3})\s*hz\b", text, re.I)
        if match:
            found["fps"] = int(match.group(1))
    return found


def timing_from_text(text, base=None):
    """按文本里找到的值覆盖到一组基准时序上。"""
    timing = base or Timing()
    found = parse_timing_text(text)
    for key, value in found.items():
        if hasattr(timing, key):
            setattr(timing, key, value)
    if "lanes" in found:
        timing.lanes = max(1, found["lanes"])
    return timing, found


# ================= DCS 包构造 =================
#
# 写入节点要的是「前导码 + 长度 + 负载」的字节串。手敲前缀很容易错
# （0x39 长包、0x15 带一个参数的短包、0x05 无参数短包），这里按参数个数
# 自动选。前导码后两个字节是 DCS 的 0x00 0x00（无参数），长度字节 = 负载长度。

DCS_SHORT_NO_PARAM = 0x05
DCS_SHORT_ONE_PARAM = 0x15
DCS_LONG_WRITE = 0x39

_HEX_TOKEN = re.compile(r"0x[0-9a-fA-F]{1,2}|[0-9a-fA-F]{2}|\b\d{1,3}\b")


def parse_hex_bytes(text):
    """把 `0x39,0x00 00 05 1a` / `39 00 00 05` 这类写法吃成字节列表。

    接受 0x 前缀、裸两位十六进制、以及不带前缀的十进制（>0x99 的按十进制解释）。
    """
    if not text:
        return []
    cleaned = re.sub(r"[,;\[\]{}()]", " ", str(text))
    out = []
    for token in cleaned.split():
        token = token.strip()
        if not token:
            continue
        try:
            if token.lower().startswith("0x"):
                value = int(token, 16)
            elif re.fullmatch(r"[0-9a-fA-F]{1,2}", token):
                value = int(token, 16)
            else:
                value = int(token, 10)
        except ValueError:
            continue
        out.append(value & 0xFF)
    return out


def dcs_kind(command, params):
    """这批负载会走哪种 DCS 包。"""
    count = len(params) + 1
    if count == 1:
        return "DCS short write（无参数，0x05）"
    if count == 2:
        return "DCS short write（1 参数，0x15）"
    return "DCS long write（0x39，{} 字节负载）".format(count)


def build_dcs_sequence(command, params):
    """(命令, 参数) → DCS 字节序列（前导码 + 长度 + 负载）。"""
    payload = [command & 0xFF] + [p & 0xFF for p in params]
    count = len(payload)
    if count == 1:
        prefix = [DCS_SHORT_NO_PARAM, 0x78, 0x00]
    elif count == 2:
        prefix = [DCS_SHORT_ONE_PARAM, 0x00, 0x00]
    else:
        prefix = [DCS_LONG_WRITE, 0x00, 0x00]
    return prefix + [count] + payload
