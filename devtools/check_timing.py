"""时序 / 带宽计算与文本解析离线自查。

用法：python devtools/check_timing.py
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from timing import Timing, parse_timing_text, timing_from_text  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print("  {}  {}  {}".format("PASS" if ok else "FAIL", label, detail))
    if not ok:
        FAILED.append(label)


print("[1] 基础公式")
t = Timing(width=1080, height=2400, fps=60,
           hfp=40, hbp=40, hsw=10, vfp=20, vbp=20, vsw=4, bpp=24, lanes=4)
check("h_total = 1080+40+40+10", t.h_total == 1170, str(t.h_total))
check("v_total = 2400+20+20+4", t.v_total == 2444, str(t.v_total))
check("pclk = 1170*2444*60", t.pclk_hz == 1170 * 2444 * 60,
      "{:.2f} MHz".format(t.pclk_hz / 1e6))
check("总速率 = pclk*24", abs(t.bitrate_bps - t.pclk_hz * 24) < 1,
      "{:.3f} Gbps".format(t.bitrate_bps / 1e9))
check("每 lane = 总速率/4", abs(t.per_lane_bps - t.bitrate_bps / 4) < 1,
      "{:.3f} Gbps".format(t.per_lane_bps / 1e9))
check("消隐占比在 0~1 之间", 0 < t.blanking_ratio < 1,
      "{:.1%}".format(t.blanking_ratio))
check("rows() 有 8 行", len(t.rows()) == 8, str(len(t.rows())))

print("\n[1b] 对照 t820-lcm-porch.xlsx 的算例（1200x1920@60, 4 lane, 384MHz）")
sheet = Timing(width=1200, height=1920, fps=60,
               hfp=40, hbp=40, hsw=20, vfp=62, vbp=12, vsw=8,
               bpp=24, lanes=4, dpi_source=384000000)
check("h_total = 1300", sheet.h_total == 1300, str(sheet.h_total))
check("v_total = 2002", sheet.v_total == 2002, str(sheet.v_total))
check("Dpi_need_clk = 156156000（表 F4）",
      sheet.pclk_hz == 156156000, str(sheet.pclk_hz))
divisor, remainder, note = sheet.auto_divisor()
check("自动分频 = 2（表 F5）", divisor == 2, "{} · {}".format(divisor, note))
check("余数 = 71688000（表 H3）", remainder == 71688000, str(remainder))
check("实际 pclk = 192000000（384/2）",
      abs(sheet.actual_pclk_hz - 192000000) < 1,
      "{:.0f}".format(sheet.actual_pclk_hz))
check("实际帧率 73.77 → INT 73（表 H6/F6）",
      int(sheet.actual_fps) == 73, "{:.4f}".format(sheet.actual_fps))
check("每 lane 需求 = 1280000000（表 H11）",
      abs(sheet.per_lane_required_bps - 1280000000) < 1,
      "{:.0f} = {:.0f} Mbps".format(sheet.per_lane_required_bps,
                                    sheet.per_lane_required_bps / 1e6))
check("mipi clk 取整后 1280 M（表 F11）",
      int(sheet.per_lane_required_bps / 1e6) == 1280,
      str(int(sheet.per_lane_required_bps / 1e6)))
check("判定为 D-PHY v1.2 可满足", "1.2" in sheet.dphy_verdict(),
      sheet.dphy_verdict())

print("\n[1c] DPI 分频边界")
manual = Timing(width=1200, height=1920, fps=60, hfp=40, hbp=40, hsw=20,
                vfp=62, vbp=12, vsw=8, dpi_source=384000000, dpi_divisor=3)
check("手动分频优先于自动", manual.divisor == 3, str(manual.divisor))
check("手动分频下实际 pclk = 128 MHz",
      abs(manual.actual_pclk_hz - 128000000) < 1,
      "{:.2f} MHz".format(manual.actual_pclk_hz / 1e6))
check("分频调大后实际帧率下降", manual.actual_fps < sheet.actual_fps,
      "{:.1f} < {:.1f}".format(manual.actual_fps, sheet.actual_fps))

low = Timing(width=1200, height=1920, fps=60, hfp=40, hbp=40, hsw=20,
             vfp=62, vbp=12, vsw=8, dpi_source=100000000)
check("时钟源不足时分频夹到 1", low.divisor == 1, str(low.divisor))
check("时钟源不足时给出提示", "达不到" in low.divisor_note, low.divisor_note)
check("分频永远不为 0", Timing(dpi_source=1).divisor >= 1,
      str(Timing(dpi_source=1).divisor))

# 余数超过半个 pclk 时要 +1：100MHz 源 / 60MHz 需求 → 商 1 余 40M > 30M
edge = Timing(width=1000, height=1000, fps=60, hfp=0, hbp=0, hsw=0,
              vfp=0, vbp=0, vsw=0, dpi_source=100000000)
check("余数超半 → 分频 +1 = 2", edge.divisor == 2,
      "分频 {} · {}".format(edge.divisor, edge.divisor_note))
check("实际帧率随之降到 50fps",
      abs(edge.actual_fps - 50) < 0.01, "{:.2f}".format(edge.actual_fps))

print("\n[2] D-PHY 上限判定")
fast = Timing(width=1440, height=3200, fps=165, bpp=24, lanes=4,
              dpi_source=1200000000, dpi_divisor=1)
check("1440x3200@165 4lane 超过 4.5Gbps/lane",
      fast.per_lane_required_bps / 1e9 > 4.5,
      "{:.2f} Gbps".format(fast.per_lane_required_bps / 1e9))
check("该组合的说明里提示需要压缩",
      "DSC" in dict((r[0], r[2]) for r in fast.rows())["每 lane 需求"],
      dict((r[0], r[2]) for r in fast.rows())["每 lane 需求"])
slow = Timing(width=720, height=1280, fps=60, bpp=24, lanes=4,
              dpi_source=384000000)
check("720x1280@60 4lane 在 1.0Gbps 以内",
      slow.per_lane_required_bps / 1e9 <= 1.0,
      "{:.3f} Gbps".format(slow.per_lane_required_bps / 1e9))
check("每 lane 需求含 0.9 效率因子（比原始负载高）",
      slow.per_lane_required_bps > slow.per_lane_bps,
      "{:.3f} > {:.3f}".format(slow.per_lane_required_bps / 1e9,
                               slow.per_lane_bps / 1e9))
check("效率因子正好是 1/0.9",
      abs((slow.per_lane_required_bps
           / (slow.per_lane_bps / slow.pclk_hz * slow.actual_pclk_hz))
          - 1 / 0.9) < 1e-6,
      "{}".format(slow.per_lane_required_bps
                  / (slow.per_lane_bps / slow.pclk_hz * slow.actual_pclk_hz)))

print("\n[3] 文本解析 —— 键值对写法")
text = """
dsi0: 1080x2400@60
hfp = 40   hbp = 40   hsw = 10
vfp: 20    vbp: 20    vsw: 4
data_lanes = 4
bpp = 24
"""
found = parse_timing_text(text)
for key in ("width", "height", "fps", "hfp", "hbp", "hsw", "vfp", "vbp", "vsw",
            "lanes", "bpp"):
    check("解析出 {}".format(key), key in found, str(found.get(key)))

print("\n[4] 文本解析 —— spec 里的长键名")
spec = """
HORIZONTAL_BACK_PORCH = 0x28
horizontal front porch: 0x28
HSYNC_WIDTH 10
VERTICAL_BACK_PORCH 20
vertical_front_porch 20
VSYNC_WIDTH 4
h_active 1080
v_active 2400
refresh_rate 60
"""
found2 = parse_timing_text(spec)
check("长键名 hbp 解析成 40", found2.get("hbp") == 40, str(found2.get("hbp")))
check("长键名 hfp 解析成 40", found2.get("hfp") == 40, str(found2.get("hfp")))
check("h_active/v_active 解析", (found2.get("width"), found2.get("height")) == (1080, 2400),
      "{}x{}".format(found2.get("width"), found2.get("height")))
check("refresh_rate 解析", found2.get("fps") == 60, str(found2.get("fps")))

print("\n[5] 文本解析 —— dmesg 风格与 1080*2400 写法")
merged, hits = timing_from_text(
    "[  12.345] panel: 1080*2400 hfp=44 hbp=44 hsw=8 vfp=24 vbp=24 vsw=4 lanes=4",
    Timing())
check("从基准上覆盖 hfp", merged.hfp == 44, str(merged.hfp))
check("覆盖 width/height", (merged.width, merged.height) == (1080, 2400),
      "{}x{}".format(merged.width, merged.height))
check("基准里没提到的 fps 保持不变", merged.fps == 60, str(merged.fps))
check("命中的键数量合理", len(hits) >= 8, str(sorted(hits)))

print("\n[5b] 设备树（DTS）片段 —— 用户实际粘贴的格式")
DTS = """\t\t\t\t\t\t\thactive = <1080>;
\t\t\t\t\t\t\tvactive = <2436>;
\t\t\t\t\t\t\thfront-porch = <48>;
\t\t\t\t\t\t\thback-porch = <32>;
\t\t\t\t\t\t\thsync-len = <4>;
\t\t\t\t\t\t\tvfront-porch = <56>;//60hz
\t\t\t\t\t\t\tvback-porch = <20>;
\t\t\t\t\t\t\tvsync-len = <4>;"""
dts = parse_timing_text(DTS)
expect = {"width": 1080, "height": 2436, "hfp": 48, "hbp": 32, "hsw": 4,
          "vfp": 56, "vbp": 20, "vsw": 4, "fps": 60}
for key, want in expect.items():
    check("DTS 解析 {} = {}".format(key, want), dts.get(key) == want,
          "实得 {}".format(dts.get(key)))
check("DTS 片段 9 项全部解析出来", len(dts) >= 9, str(sorted(dts)))

dts_timing, _hits = timing_from_text(DTS, Timing())
check("DTS 参数算出 h_total 1164",
      dts_timing.h_total == 1080 + 48 + 32 + 4, str(dts_timing.h_total))
check("DTS 参数算出 v_total 2516",
      dts_timing.v_total == 2436 + 56 + 20 + 4, str(dts_timing.v_total))

# 连字符 / 尖括号 / 方括号 / 注释 混在一起也要稳
MIXED = """
qcom,mdss-dsi-panel-width = <1440>;
qcom,mdss-dsi-panel-height = <3200>;
hfront_porch = 40;  hback_porch = 40;  hsync-width = 8;
vfront-porch = [62]; vback-porch = "12"; vsync_len = 8;
/* data-lanes = <4>; */ refresh-rate = 120
"""
mixed = parse_timing_text(MIXED)
check("混合写法解析 width/height",
      (mixed.get("width"), mixed.get("height")) == (1440, 3200),
      "{}x{}".format(mixed.get("width"), mixed.get("height")))
check("混合写法解析 hfp/hbp/hsw",
      (mixed.get("hfp"), mixed.get("hbp"), mixed.get("hsw")) == (40, 40, 8),
      "{}/{}/{}".format(mixed.get("hfp"), mixed.get("hbp"), mixed.get("hsw")))
check("方括号与引号里的值也能解析",
      (mixed.get("vfp"), mixed.get("vbp"), mixed.get("vsw")) == (62, 12, 8),
      "{}/{}/{}".format(mixed.get("vfp"), mixed.get("vbp"), mixed.get("vsw")))
check("refresh-rate → fps", mixed.get("fps") == 120, str(mixed.get("fps")))
check("data-lanes → lanes", mixed.get("lanes") == 4, str(mixed.get("lanes")))

# 内核驱动里的结构体写法（LCM 驱动代码里最常见）
KERNEL_C = """
static struct panel_timing t = {
    .h_active        = 1080,
    .v_active        = 2436,
    .h_front_porch   = 48,
    .h_back_porch    = 32,
    .h_sync_width    = 4,
    .v_front_porch   = 56,
    .v_back_porch    = 20,
    .v_sync_width    = 4,
    .lane_num        = 4,
    .refresh_rate    = 60,
};
"""
kernel = parse_timing_text(KERNEL_C)
check("内核结构体：分辨率", (kernel.get("width"), kernel.get("height")) == (1080, 2436),
      "{}x{}".format(kernel.get("width"), kernel.get("height")))
check("内核结构体：水平肩",
      (kernel.get("hfp"), kernel.get("hbp"), kernel.get("hsw")) == (48, 32, 4),
      "{}/{}/{}".format(kernel.get("hfp"), kernel.get("hbp"), kernel.get("hsw")))
check("内核结构体：垂直肩",
      (kernel.get("vfp"), kernel.get("vbp"), kernel.get("vsw")) == (56, 20, 4),
      "{}/{}/{}".format(kernel.get("vfp"), kernel.get("vbp"), kernel.get("vsw")))
check("内核结构体：lane 与刷新率",
      (kernel.get("lanes"), kernel.get("fps")) == (4, 60),
      "{}/{}".format(kernel.get("lanes"), kernel.get("fps")))

# qcom 风格：键名里带厂商前缀，全是连字符
QCOM = """
qcom,mdss-dsi-h-front-porch = <48>;
qcom,mdss-dsi-h-back-porch = <32>;
qcom,mdss-dsi-h-pulse-width = <4>;
qcom,mdss-dsi-v-front-porch = <56>;
qcom,mdss-dsi-v-back-porch = <20>;
qcom,mdss-dsi-v-pulse-width = <4>;
"""
qcom = parse_timing_text(QCOM)
check("qcom 连字符键名：水平肩",
      (qcom.get("hfp"), qcom.get("hbp"), qcom.get("hsw")) == (48, 32, 4),
      "{}/{}/{}".format(qcom.get("hfp"), qcom.get("hbp"), qcom.get("hsw")))
check("qcom 连字符键名：垂直肩",
      (qcom.get("vfp"), qcom.get("vbp"), qcom.get("vsw")) == (56, 20, 4),
      "{}/{}/{}".format(qcom.get("vfp"), qcom.get("vbp"), qcom.get("vsw")))

print("\n[6] 边界")
check("空文本不炸", parse_timing_text("") == {})
check("垃圾文本返回空", parse_timing_text("hello world") == {},
      str(parse_timing_text("hello world")))
check("lanes=0 会被夹到 1", Timing(lanes=0).lanes == 1, str(Timing(lanes=0).lanes))
check("fps 写成 60000 会折成 60",
      parse_timing_text("refresh_rate 60000").get("fps") == 60,
      str(parse_timing_text("refresh_rate 60000").get("fps")))
check("非法数字回退默认", Timing(width="abc").width == 1080, str(Timing(width="abc").width))

print("\n[7] DCS 包构造")
from timing import (build_dcs_sequence, dcs_kind,  # noqa: E402
                    parse_hex_bytes)

check("无参数 → 0x05 短包",
      build_dcs_sequence(0x10, []) == [0x05, 0x78, 0x00, 0x01, 0x10],
      str([hex(b) for b in build_dcs_sequence(0x10, [])]))
check("1 参数 → 0x15 短包",
      build_dcs_sequence(0x51, [0xFF]) == [0x15, 0x00, 0x00, 0x02, 0x51, 0xFF],
      str([hex(b) for b in build_dcs_sequence(0x51, [0xFF])]))
check("3 参数 → 0x39 长包",
      build_dcs_sequence(0x1A, [0x2B, 0x3C]) ==
      [0x39, 0x00, 0x00, 0x03, 0x1A, 0x2B, 0x3C],
      str([hex(b) for b in build_dcs_sequence(0x1A, [0x2B, 0x3C])]))
check("长度字节 = 命令 + 参数个数",
      build_dcs_sequence(0x1A, [0] * 20)[3] == 21,
      str(build_dcs_sequence(0x1A, [0] * 20)[3]))
check("种类判断：长包", "long" in dcs_kind(0x1A, [1, 2]).lower(),
      dcs_kind(0x1A, [1, 2]))
check("十六进制解析（0x 前缀 + 逗号）",
      parse_hex_bytes("0x39,0x00,0x00,0x05,0x1a") == [0x39, 0, 0, 5, 0x1A],
      str([hex(b) for b in parse_hex_bytes("0x39,0x00,0x00,0x05,0x1a")]))
check("十六进制解析（裸两位）",
      parse_hex_bytes("39 00 00 05 1a") == [0x39, 0, 0, 5, 0x1A],
      str([hex(b) for b in parse_hex_bytes("39 00 00 05 1a")]))
check("十六进制解析（方括号 + 换行）",
      parse_hex_bytes("[0x15, 0x00,\n0x00, 0x02]") == [0x15, 0, 0, 2],
      str([hex(b) for b in parse_hex_bytes("[0x15, 0x00,\n0x00, 0x02]")]))
check("垃圾输入返回空", parse_hex_bytes("hello world") == [],
      str(parse_hex_bytes("hello world")))
check("空输入返回空", parse_hex_bytes("") == [])

print("\n" + "=" * 46)
if FAILED:
    print("失败 {} 项：{}".format(len(FAILED), "、".join(FAILED)))
    sys.exit(1)
print("时序计算与解析全部通过")
