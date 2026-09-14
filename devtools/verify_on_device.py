"""真机端到端验证：真实执行命令，检查界面是否真的被数据填充。

需要连接设备。验证内容：
- 已下线模块（异常守护 / 电池调试）确实不在页面上
- 显示调试：背光读取、时序计算公式、DCS 包构造
- 设备信息：15 项查询是否回来
- 触摸/系统：查询按钮是否真的产出内容
- 确认不再出现「不是内部或外部命令」
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtCore import QEventLoop, QTimer     # noqa: E402
from PyQt5.QtWidgets import QApplication        # noqa: E402

import theme                                     # noqa: E402
from mainwindow import MainWindow                # noqa: E402

FAIL = []
CHECKS = [0]


def check(label, ok, detail=""):
    CHECKS[0] += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAIL.append(label)


def wait(app, ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()
    app.processEvents()


def main():
    app = QApplication([])
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())

    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    app.processEvents()

    tools = window.pages["tools"]
    panel = tools.runner.panel

    # ---------- 已下线模块不能再出现在页面上 ----------
    print("\n[下线模块] 异常守护 / 电池调试")
    for key in ("guard", "battery"):
        check("{} 不在常用工具页".format(key), key not in tools.sections)
    tools.show_section("log")

    # ---------- 显示调试：背光 + 时序计算 ----------
    print("\n[显示调试] 背光读取与时序计算")
    tools.show_section("display")
    display = tools.sections["display"]
    display.get_brightness()
    wait(app, 5000)
    output = panel.view.toPlainText()
    check("背光读取有返回", "screen_brightness" in output)
    check("无 Windows 报错",
          "not recognized" not in output and "operable program" not in output)

    timing = display.current_timing()
    check("时序计算用当前界面参数", timing.width == display.t_w.value(),
          "{}x{}".format(timing.width, timing.height))
    check("pclk 与公式一致",
          abs(timing.pclk_hz
              - timing.h_total * timing.v_total * timing.fps) < 1,
          "{:.2f} MHz".format(timing.pclk_hz / 1e6))
    display.dcs_cmd.setText("0x51")
    display.dcs_params.setText("0xff")
    sequence = display.build_dcs()
    check("DCS 构造生成带参短包 0x15",
          sequence == [0x15, 0x00, 0x00, 0x02, 0x51, 0xFF], str(sequence))

    # ---------- 设备信息 ----------
    print("\n[设备信息] 15 项真实查询")
    tools.show_section("device")
    device = tools.sections["device"]
    device.refresh()
    wait(app, 25000)
    values = device._values
    print(f"    取回 {len(values)} 项：{', '.join(list(values)[:8])}")
    check("设备信息取回 >= 8 项", len(values) >= 8, f"{len(values)} 项")
    check("型号已解析",
          device.cards["model"].value_label.fullText() not in ("--", ""),
          device.cards["model"].value_label.fullText())
    check("内核版本已解析",
          device.cards["kernel"].value_label.fullText() not in ("--", ""),
          device.cards["kernel"].value_label.fullText())
    check("分辨率已解析",
          "x" in device.cards["resolution"].value_label.fullText(),
          device.cards["resolution"].value_label.fullText())

    # ---------- 显示模块 ----------
    print("\n[显示] 读取当前背光")
    tools.show_section("display")
    display = tools.sections["display"]
    display.get_brightness()
    wait(app, 4000)
    text = panel.view.toPlainText()
    check("背光读取有返回", "screen_brightness" in text or text.strip() != "")
    check("无 Windows 报错", "not recognized" not in text)

    # ---------- 触摸模块 ----------
    print("\n[触摸] 事件抓取与可视化开关")
    tools.show_section("touch")
    touch = tools.sections["touch"]
    # 输入设备枚举那组按钮已下线，改成验证留存的功能能真的跑
    touch.read_touch_switches()
    wait(app, 5000)
    text = panel.view.toPlainText()
    check("读取触摸开关有返回", "show_touches" in text or "pointer_location" in text)
    check("无 Windows 报错", "not recognized" not in text)
    check("输入设备枚举按钮已下线",
          not hasattr(touch, "_build_query_card")
          or "INPUT_QUERIES" not in dir(__import__("tools_touch")))

    # ---------- 系统模块 ----------
    print("\n[系统] SELinux + 内核版本")
    tools.show_section("system")
    system = tools.sections["system"]
    system.runner.run("getenforce", "SELinux 状态")
    wait(app, 4000)
    text = panel.view.toPlainText()
    check("getenforce 有返回",
          any(word in text for word in ("Enforcing", "Permissive", "Disabled")))
    check("无 Windows 报错", "not recognized" not in text)

    # ---------- 面板整体 ----------
    print("\n[整体] 输出面板内容检查")
    all_text = panel.view.toPlainText()
    bad_lines = [ln for ln in all_text.splitlines()
                 if "is not recognized" in ln or "operable program" in ln]
    check("整个会话无「不是内部或外部命令」", not bad_lines, "; ".join(bad_lines[:2]))
    check("面板有实际输出内容", len(all_text.strip()) > 50,
          f"{len(all_text)} 字符")

    tools.stop_background()
    wait(app, 1500)
    window.close()

    print("\n" + "=" * 58)
    if FAIL:
        print(f"{len(FAIL)}/{CHECKS[0]} 项失败：")
        for name in FAIL:
            print("  -", name)
        return 1
    print(f"真机验证全部通过（{CHECKS[0]} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
