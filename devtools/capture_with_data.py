"""带真实数据的视觉效果验证。

空界面看不出问题（长日志行、长型号名、多行表格只有在有数据时才会
暴露裁切/溢出）。这里往各子功能灌入贴近真机的样本数据再截图。

用法：
    python devtools/capture_with_data.py [输出目录]
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtWidgets import QApplication          # noqa: E402

import theme                                       # noqa: E402
import tools_page                                  # noqa: E402
from mainwindow import MainWindow                  # noqa: E402

SAMPLE_LOG = [
    "01-01 10:00:00.123  1234  1234 I ActivityManager: Start proc 5678:com.android.settings/u0a12 for activity",
    "01-01 10:00:00.456  1234  1234 D SurfaceFlinger: Display[0] activeMode=1220x2712@120.00",
    "01-01 10:00:01.789  2345  2345 E DisplayManager: failed to set display mode 1080x2400 for display 0",
    "01-01 10:00:02.012  3456  3456 W dsi_panel: dsi_panel_set_backlight: level=128 max=2047",
    "01-01 10:00:03.345  3456  3456 E dsi_panel: dsi write timeout, cmd=0x39 0x00 0x00 0x05 0x1a 0x2b",
    "01-01 10:00:04.678  4567  4567 I lcm_driver: lcm_probe success, panel=nt36672c, lanes=4",
    "01-01 10:00:05.901  5678  5678 D WindowManager: addWindow token=android.os.BinderProxy",
    "01-01 10:00:06.234  6789  6789 E thermal: thermal_zone0 temp=78500, throttling level 2",
    "01-01 10:00:07.567  7890  7890 I chatty: uid=1000(system) expire 12 lines",
    "01-01 10:00:08.890  8901  8901 F libc: Fatal signal 11 (SIGSEGV), code 1, fault addr 0x0 in tid 8901",
]

SAMPLE_DEVICE = {
    "型号": "MTP-DisplayTest-Engineering-Sample-Long-Name",
    "品牌": "Unisoc",
    "系统版本": "14",
    "SDK": "34",
    "构建指纹": "Unisoc/sl8541e_1h10/sl8541e_1h10:14/UP1A.231005.007/eng.test.20260912:userdebug/test-keys",
    "内核版本": "5.15.149-android13-8-g3f2a1b0c9d8e-abi",
    "屏幕分辨率": "Physical size: 1220x2712",
    "屏幕密度": "Physical density: 480",
    "刷新率": "fps=120.0",
    "CPU 温度": "52400",
    "电池": "  level: 87\n  scale: 100\n  voltage: 4231",
    "内存": "MemTotal:        7854320 kB\nMemFree:          902144 kB\nMemAvailable:    3145728 kB",
    "存储": "/dev/block/dm-5 110000000 95000000 15000000 91% /data",
    "运行时长": "179384.20 700000.00",
    "Panel": "nt36672c_amoled_1220x2712",
}


def fill_data(window):
    tools = window.pages["tools"]

    # 日志分析
    log = tools.sections["log"]
    log._buffer = list(SAMPLE_LOG)
    log.render()

    # 设备信息
    dev = tools.sections["device"]
    for key, value in SAMPLE_DEVICE.items():
        dev._values[key] = value
        dev.raw_view.appendPlainText(f"── {key}\n{value}\n")
        dev._apply(key, value)
    dev.status_label.setText("更新于 18:52:07")

    # 文件管理
    files = tools.sections["files"]
    files.current_path = "/sdcard/DCIM/Camera/"
    files.path_edit.setText(files.current_path)
    files.entries = files._parse_listing(
        "total 25840\n"
        "drwxrwx--x 2 root sdcard_rw 4096 2026-09-12 10:11 .thumbnails\n"
        "-rw-rw---- 1 root sdcard_rw 2847362 2026-09-12 10:11 IMG_20260912_101122.jpg\n"
        "-rw-rw---- 1 root sdcard_rw 1938472 2026-09-12 10:12 IMG_20260912_101205.jpg\n"
        "-rw-rw---- 1 root sdcard_rw 41239843 2026-09-12 10:15 VID_20260912_101520.mp4\n"
        "-rw-rw---- 1 root sdcard_rw 128 2026-09-12 10:16 log.txt\n"
        "lrwxrwxrwx 1 root root 21 2026-09-12 10:16 latest -> /sdcard/DCIM/Camera/IMG_20260912_101205.jpg\n"
    )
    files.render_entries()

    # 性能监控：铺一段曲线 + 表格
    perf = tools.sections["perf"]
    perf.reset()
    import math
    for i in range(40):
        sample = {
            "time": f"18:{i // 60:02d}:{i % 60:02d}",
            "cpu": 60 + 35 * math.sin(i / 4.0) + (10 if i % 7 == 0 else 0),
            "mem": 62 + 6 * math.sin(i / 11.0),
            "temp": 48 + 12 * math.sin(i / 9.0),
            "bat": 95 - i * 0.15,
            "fps": 58 if i % 13 else 41,
            "df": 82 + 4 * math.sin(i / 15.0),
        }
        perf.samples.append(sample)
        for key, _label, _color in __import__("tools_perf").SERIES_DEFS:
            perf.chart.append(key, sample.get(key))
        perf._update_cards(sample)
        perf._append_table(sample)
    perf.chart.update()
    perf.start_btn.setText("停止监控")
    perf.start_btn.setProperty("accent", False)
    perf.start_btn.setProperty("danger", True)
    perf.status_label.setText("监控中 · 40 个采样点 · 掉帧累计 68 fps")

    # Shell Tools 日志区
    shell = window.pages["shell"]
    for line in SAMPLE_LOG[:6]:
        shell.textBrowser.insertPlainText(line + "\n")
    shell.flash_img_path.setText(r"D:\images\sl8541e\uboot_a_signed.img")
    shell.ylogpath_2.setText("Z002")
    shell.ylogpath_3.setText("LCM-20260912")
    shell.apk1_path.setText(r"D:\00_project\lcm_test_apk\Display-Tester_1.apk")
    shell.scrcpy_path.setText(r"D:\01_tools\scrcpy-win64-v2.6.1\scrcpy.exe")

    # 电池调试：填卡片 + 采样记录
    battery = tools.sections["battery"]
    for index in range(6):
        battery._apply_dumpsys(
            "  AC powered: false\n"
            "  USB powered: true\n"
            f"  status: 2\n  health: 2\n  level: {87 - index}\n  scale: 100\n"
            f"  voltage: {4231 - index * 3}\n  temperature: {356 + index * 5}\n"
            f"  current now: {-450000 + index * 12000}\n")

    # 触摸调试 / 系统调试：填输入值，让界面有内容
    touch = tools.sections["touch"]
    touch.tap_x.setValue(540)
    touch.tap_y.setValue(1200)
    touch.key_input.setText("KEYCODE_HOME")

    system = tools.sections["system"]
    system.prop_combo.setCurrentText("ro.product.model")
    system.prop_value.setText("MTP-Test")
    system.gov_combo.setCurrentText("schedutil")
    system.freq_edit.setText("1800000")

    # 共享输出面板：塞一段真实感输出
    tools.runner.panel.append_command("adb shell dumpsys battery", "读取电池状态")
    tools.runner.panel.append_result(
        0,
        "Current Battery Service state:\n"
        "  AC powered: false\n  USB powered: true\n  status: 2\n  health: 2\n"
        "  level: 87\n  voltage: 4231\n  temperature: 356\n  current now: -450000",
        "读取电池状态")


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "devtools", "shots_data")
    os.makedirs(out_dir, exist_ok=True)

    app = QApplication(sys.argv)
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())

    window = MainWindow()
    window.show()
    app.processEvents()
    fill_data(window)

    def grab(name):
        for _ in range(6):
            app.processEvents()
        path = os.path.join(out_dir, f"{name}.png")
        window.grab().save(path)
        print("saved", name, flush=True)

    window.nav.select("shell")
    grab("data_shell")

    window.nav.select("tools")
    tools = window.pages["tools"]
    for key, _label, _icon, _cls in tools_page.SECTIONS:
        tools.show_section(key)
        grab(f"data_{key}")

    tools.stop_background()
    app.processEvents()
    window.close()
    print("done ->", out_dir, flush=True)


if __name__ == "__main__":
    main()
