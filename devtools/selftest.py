"""功能自测：不依赖真机，用合成数据验证第 6 页各子功能的逻辑。

用法（仓库根目录）：
    .venv\\Scripts\\python.exe devtools\\selftest.py
"""

import os
import sys
import posixpath

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bsp_tools"))

from PyQt5.QtWidgets import QApplication          # noqa: E402

import theme                                       # noqa: E402
import tools_page                                  # noqa: E402
from mainwindow import MainWindow                  # noqa: E402
from tools_log import LogAnalyzerSection, LEVEL_PATTERNS  # noqa: E402
from tools_device import DeviceInfoSection         # noqa: E402
from tools_files import FileManagerSection         # noqa: E402
from tools_perf import PerfSection                 # noqa: E402

FAILURES = []
CHECKS = [0]


def check(label, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        FAILURES.append(label)


def main():
    app = QApplication([])
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())
    window = MainWindow()
    window.resize(1480, 920)
    window.show()
    app.processEvents()

    print("\n[1] 日志分析：抓取结果 + 过滤 + 等级着色")
    log = LogAnalyzerSection()
    log.resize(1000, 600)
    log._buffer = [
        "01-01 10:00:00.000  1234  1234 I ActivityManager: Start proc",
        "01-01 10:00:01.000  1234  1234 E DisplayManager: failed to set mode",
        "01-01 10:00:02.000  1234  1234 W SurfaceFlinger: duplicate frame",
        "01-01 10:00:03.000  1234  1234 E dsi_panel: dsi write timeout",
        "01-01 10:00:04.000  1234  1234 I lcm: backlight set 128",
    ]
    log.render()
    check("全量渲染 5 行", "5 / 5" in log.count_label.text(), log.count_label.text())

    log.filter_edit.setText("dsi")
    log.render()
    check("关键字过滤 dsi → 1 行", "1 / 5" in log.count_label.text(),
          log.count_label.text())

    log.filter_edit.setText("dsi|backlight")
    log.render()
    check("多关键字 dsi|backlight → 2 行", "2 / 5" in log.count_label.text(),
          log.count_label.text())

    log.filter_edit.setText("dsi.*timeout")
    log.regex_check.setChecked(True)
    log.render()
    check("正则模式 → 1 行", "1 / 5" in log.count_label.text(),
          log.count_label.text())

    log.regex_check.setChecked(False)
    log.filter_edit.setText("")
    log.only_error.setChecked(True)
    log.render()
    check("只看错误 → 2 行", "2 / 5" in log.count_label.text(),
          log.count_label.text())
    log.only_error.setChecked(False)

    check("导出内容非空", bool(log.view.toPlainText().strip()))

    print("\n[2] 设备信息：解析函数")
    dev = DeviceInfoSection()
    dev._apply_temp("48500")
    check("温度 48500 → 48.5", "48.5" in dev.cards["temp"].value_label.text(),
          dev.cards["temp"].value_label.text())
    dev._apply_battery("  level: 42\n  scale: 100")
    check("电量解析 → 42", "42" in dev.cards["battery"].value_label.text(),
          dev.cards["battery"].value_label.text())
    dev._apply_memory("MemTotal:       8000000 kB\nMemAvailable:   2000000 kB")
    check("内存占用 → 75", "75" in dev.cards["memory"].value_label.text(),
          dev.cards["memory"].value_label.text())
    dev._apply_storage("/dev/block/dm-5 110000000 90000000 20000000 82% /data")
    check("存储占用（单行 df）→ 82", "82" in dev.cards["storage"].value_label.text(),
          dev.cards["storage"].value_label.text())
    dev._apply_storage(
        "Filesystem 1K-blocks Used Available Use% Mounted on\n"
        "/dev/block/dm-5 110000000 95000000 15000000 91% /data")
    check("存储占用（两行 df）→ 91", "91" in dev.cards["storage"].value_label.text(),
          dev.cards["storage"].value_label.text())
    dev._apply_uptime("93784.20 300000.00")
    check("运行时长格式化", dev.cards["uptime"].value_label.text() == "1d2h",
          dev.cards["uptime"].value_label.text())
    dev._apply("屏幕分辨率", "Physical size: 1220x2712")
    check("分辨率提取", "1220x2712" in dev.cards["resolution"].value_label.text(),
          dev.cards["resolution"].value_label.text())

    print("\n[3] 文件管理：ls -la 解析")
    listing = (
        "total 24\n"
        "drwxrwx--x 4 root sdcard_rw 4096 2026-01-01 10:00 Android\n"
        "-rw-rw---- 1 root sdcard_rw 12345 2026-01-01 10:00 photo.png\n"
        "lrwxrwxrwx 1 root root 21 2026-01-01 10:00 sdcard -> /storage/self/primary\n"
        "ls: /sdcard/nope: No such file or directory\n"
    )
    entries = FileManagerSection._parse_listing(listing)
    names = [e.get('name') for e in entries]
    check("解析 3 个条目", len([e for e in entries if 'name' in e]) == 3, str(names))
    check("目录排在前面", names[0] == "Android", str(names))
    check("符号链接目标被剥离", "sdcard" in names and "sdcard -> /storage/self/primary" not in names,
          str(names))
    check("错误行被识别", any('error' in e for e in entries))
    android = next(e for e in entries if e.get('name') == 'Android')
    check("目录标记为 dir", android['dir'] is True)
    photo = next(e for e in entries if e.get('name') == 'photo.png')
    check("文件大小解析", photo['size'] == 12345, str(photo))
    check("大小格式化 KB", FileManagerSection._human_size(12345) == "12.1 KB",
          FileManagerSection._human_size(12345))

    print("\n[4] 性能监控：采样解析")
    perf = PerfSection()
    output = (
        "CPU:0.42 0.31 0.25 1/234 5678\n"
        "MEM:MemTotal: 8000000 kB MemFree: 1000000 kB MemAvailable: 4000000 kB\n"
        "TEMP:52300\n"
        "BAT:  level: 88\n"
        "FPS:fps=58.3\n"
        "/dev/block/dm-5 110000000 90000000 20000000 82% /data\n"
    )
    sample = perf._parse(output)
    check("采样解析成功", sample is not None)
    check("CPU 负载 0.42", abs(sample['cpu'] - 42.0) < 0.1, str(sample['cpu']))
    check("内存 50%", abs(sample['mem'] - 50.0) < 0.1, str(sample['mem']))
    check("温度 52.3", abs(sample['temp'] - 52.3) < 0.1, str(sample['temp']))
    check("电量 88", sample['bat'] == 88.0, str(sample['bat']))
    check("帧率 58.3", abs(sample['fps'] - 58.3) < 0.1, str(sample['fps']))
    check("Data 82%", sample['df'] == 82.0, str(sample['df']))
    perf._update_cards(sample)
    check("帧率卡片刷新", "58" in perf.cards["fps"].value_label.text(),
          perf.cards["fps"].value_label.text())
    check("空输出返回 None", perf._parse("") is None)

    print("\n[5] 命令收藏：增删改 + 持久化")
    fav = window.pages["tools"].sections["favorites"]
    before = len(fav.items)
    fav.name_edit.setText("自测命令")
    fav.command_edit.setText("adb shell echo self-test")
    fav.group_combo.setCurrentText("自测")
    fav.save_entry()
    check("新增一条收藏", len(fav.items) == before + 1, str(len(fav.items)))
    check("收藏写入文件", os.path.exists(os.path.join(ROOT, "bsp_tools", "favorites.json")))
    fav.search_edit.setText("自测命令")
    fav.render_list()
    check("搜索结果 1 条", fav.list_widget.count() == 1, str(fav.list_widget.count()))
    fav.search_edit.clear()
    fav.render_list()
    check("清空搜索后条目数恢复", fav.list_widget.count() == len(fav.items),
          f"{fav.list_widget.count()} vs {len(fav.items)}")
    # 清理：删掉自测条目
    idx = next(i for i, it in enumerate(fav.items) if it['name'] == "自测命令")
    fav.items.pop(idx)
    fav.save()
    check("清理自测数据", len(fav.items) == before, str(len(fav.items)))

    print("\n[6] 主窗口导航与状态栏")
    for key in ("tools", "shell", "initcode", "lk2kernel", "kernel2lk", "lk2bat"):
        window.nav.select(key)
        app.processEvents()
        check(f"切换到 {key}", window.stack.currentWidget() is window.pages[key])
    window.set_device_status("设备：TEST-1234", True)
    check("设备状态写入状态栏", "TEST-1234" in window.deviceLabel.text(),
          window.deviceLabel.text())
    window.toast("自测提示", "success")
    check("浮层提示可显示", window._toast.isVisible())

    print("\n[7] 文件管理：列表渲染与选中")
    files = window.pages["tools"].sections["files"]
    files.current_path = "/sdcard/"
    files.entries = FileManagerSection._parse_listing(
        "drwxrwx--x 4 root sdcard_rw 4096 2026-01-01 10:00 Android\n"
        "-rw-rw---- 1 root sdcard_rw 12345 2026-01-01 10:00 photo.png\n")
    files.render_entries()
    check("列表渲染 2 项", files.list_widget.count() == 2, str(files.list_widget.count()))
    files.list_widget.setCurrentRow(1)
    check("选中项解析出设备路径",
          files._selected_device_path() == "/sdcard/photo.png",
          str(files._selected_device_path()))
    files.list_widget.setCurrentRow(0)
    check("目录项路径正确",
          files._selected_device_path() == "/sdcard/Android",
          str(files._selected_device_path()))
    files.filter_edit.setText("photo")
    files.render_entries()
    check("文件过滤生效", files.list_widget.count() == 1, str(files.list_widget.count()))
    files.filter_edit.clear()
    files.render_entries()
    check("上级路径计算", posixpath.dirname("/sdcard/Android/".rstrip('/')) == "/sdcard")
    check("根目录上级为 /", (posixpath.dirname("/sdcard".rstrip('/')) or "/") == "/")

    print("\n[8] 常用工具模块：执行命令不跳转、输出落在本页面板")
    tools_page_obj = window.pages["tools"]
    runner = tools_page_obj.runner

    # 拦掉真实执行：只记录命令，避免自测真的去调 adb
    calls = []
    original_run = runner.run

    from command_runner import device_cmd

    def fake_run(command, label=None, **kwargs):
        calls.append((device_cmd(command), label))
        return None

    runner.run = fake_run
    try:
        window.nav.select("tools")
        tools_page_obj.show_section("display")
        app.processEvents()

        display = tools_page_obj.sections["display"]
        display.bright_value.setText("180")
        display.set_brightness()
        check("背光设置命令正确",
              calls and "screen_brightness 180" in calls[-1][0], str(calls[-1:]))
        check("执行后背光仍停在常用工具页",
              window.nav.current_key() == "tools",
              str(window.nav.current_key()))

        # DCS 直接读写节点已按 func-list 移除，这里确认它真的不再产生命令
        check("DCS 写节点按钮已下线",
              not hasattr(display, "write_dcs")
              and not hasattr(display, "dcs_write_path"),
              "仍存在 write_dcs/dcs_write_path")
        check("ESD 重置按钮已下线", not hasattr(display, "esd_reset"))
        check("Panel 参数查询卡片已下线",
              not hasattr(display, "_build_panel_card"))

        display.read_refresh_rate()
        check("刷新率读取命令", "fps=" in calls[-1][0], str(calls[-1:]))

        # 时序计算界面接线：按 t820-lcm-porch.xlsx 的算例填一遍，逐项对数
        for box, value in ((display.t_w, 1200), (display.t_h, 1920),
                           (display.t_fps, 60), (display.t_hfp, 40),
                           (display.t_hbp, 40), (display.t_hsw, 20),
                           (display.t_vfp, 62), (display.t_vbp, 12),
                           (display.t_vsw, 8)):
            box.setValue(value)
        display.t_lanes.setCurrentText("4")
        display.t_dpi_src.setValue(384)
        display.t_dpi_auto.setChecked(True)
        app.processEvents()

        shown = {name: label.text() for name, label in display.timing_values.items()}
        check("界面算出需求 pclk 156.16 MHz",
              shown["需求 pclk"] == "156.16 MHz", shown["需求 pclk"])
        check("界面算出实际 pclk 192.00 MHz",
              shown["实际 pclk"] == "192.00 MHz", shown["实际 pclk"])
        check("界面算出实际帧率 73.8 fps",
              shown["实际帧率"] == "73.8 fps", shown["实际帧率"])
        check("界面算出每 lane 需求 1.280 Gbps",
              shown["每 lane 需求"] == "1.280 Gbps", shown["每 lane 需求"])
        check("自动分频推出分频 2", display.t_dpi_div.value() == 2,
              str(display.t_dpi_div.value()))
        check("自动分频时手动框被锁", not display.t_dpi_div.isEnabled())
        check("DPI 结果行显示实际时钟",
              "192.00 MHz" in display.dpi_result_label.text(),
              display.dpi_result_label.text())

        display.t_dpi_auto.setChecked(False)
        display.t_dpi_div.setValue(3)
        app.processEvents()
        check("手动分频生效：实际 pclk 变 128.00 MHz",
              display.timing_values["实际 pclk"].text() == "128.00 MHz",
              display.timing_values["实际 pclk"].text())
        check("手动分频时框可编辑", display.t_dpi_div.isEnabled())

        display.reset_timing()
        app.processEvents()
        check("复位回到 1080x2400",
              (display.t_w.value(), display.t_h.value()) == (1080, 2400),
              "{}x{}".format(display.t_w.value(), display.t_h.value()))
        check("复位后恢复自动分频", display.t_dpi_auto.isChecked())

        # 走完整剪贴板路径：用户实际粘的是设备树（DTS）片段
        from PyQt5.QtWidgets import QApplication as _QApp
        DTS_SNIPPET = (
            "\t\t\t\t\t\t\thactive = <1080>;\n"
            "\t\t\t\t\t\t\tvactive = <2436>;\n"
            "\t\t\t\t\t\t\thfront-porch = <48>;\n"
            "\t\t\t\t\t\t\thback-porch = <32>;\n"
            "\t\t\t\t\t\t\thsync-len = <4>;\n"
            "\t\t\t\t\t\t\tvfront-porch = <56>;//60hz\n"
            "\t\t\t\t\t\t\tvback-porch = <20>;\n"
            "\t\t\t\t\t\t\tvsync-len = <4>;")
        _QApp.clipboard().setText(DTS_SNIPPET)
        parsed = display.parse_timing_clipboard()
        app.processEvents()
        check("剪贴板 DTS 片段解析出 9 项", len(parsed) >= 9, str(sorted(parsed)))
        check("DTS 片段填进分辨率框",
              (display.t_w.value(), display.t_h.value()) == (1080, 2436),
              "{}x{}".format(display.t_w.value(), display.t_h.value()))
        check("DTS 片段填进水平/垂直肩",
              (display.t_hfp.value(), display.t_hbp.value(), display.t_hsw.value(),
               display.t_vfp.value(), display.t_vbp.value(),
               display.t_vsw.value()) == (48, 32, 4, 56, 20, 4),
              "{}/{}/{} {}/{}/{}".format(
                  display.t_hfp.value(), display.t_hbp.value(),
                  display.t_hsw.value(), display.t_vfp.value(),
                  display.t_vbp.value(), display.t_vsw.value()))
        check("注释里的 60hz 被当成刷新率", display.t_fps.value() == 60,
              str(display.t_fps.value()))
        check("DTS 片段的 h_total 变成 1164",
              display.timing_values["水平总计 h_total"].text() == "1164 px",
              display.timing_values["水平总计 h_total"].text())

        display.reset_timing()
        app.processEvents()

        # 收藏夹执行也不跳转
        fav = tools_page_obj.sections["favorites"]
        fav.items.append({"group": "自测", "name": "路由测试",
                          "command": "adb shell echo hi"})
        fav.render_list()
        fav.list_widget.setCurrentRow(fav.list_widget.count() - 1)
        fav.run_selected()
        check("收藏夹执行命令正确",
              calls and calls[-1][0] == "adb shell echo hi", str(calls[-1:]))
        check("收藏夹执行后仍停在常用工具页",
              window.nav.current_key() == "tools", str(window.nav.current_key()))
        fav.items.pop()
        fav.save()
        fav.render_list()

        # 模块共享同一个 runner（输出面板只有一份）
        check("显示调试用的是本页共享 runner",
              tools_page_obj.sections["display"].runner is runner)
        check("触摸调试用的是本页共享 runner",
              tools_page_obj.sections["touch"].runner is runner)

        # func-list 标记为「否」的模块不能再挂进页面
        for gone in ("guard", "battery"):
            check("已下线模块 {} 不在常用工具页".format(gone),
                  gone not in tools_page_obj.sections
                  and gone not in [key for key, *_rest in tools_page.SECTIONS])
    finally:
        runner.run = original_run

    print("\n[10] 新模块命令拼装校验（离线，不真的执行）")
    from command_runner import device_cmd, DEVICE_COMMANDS

    # 先验证前缀补全规则本身
    check("dumpsys 自动补 adb shell",
          device_cmd("dumpsys battery") == "adb shell dumpsys battery",
          device_cmd("dumpsys battery"))
    check("带管道的设备命令被引号包裹",
          device_cmd("dumpsys display | grep fps")
          == 'adb shell "dumpsys display | grep fps"',
          device_cmd("dumpsys display | grep fps"))
    check("重定向也走设备端 shell",
          device_cmd("cat /proc/meminfo | head -3")
          == 'adb shell "cat /proc/meminfo | head -3"',
          device_cmd("cat /proc/meminfo | head -3"))
    check("echo 写节点走设备端 shell",
          device_cmd("echo 1 > /sys/x") == 'adb shell "echo 1 > /sys/x"',
          device_cmd("echo 1 > /sys/x"))
    check("已是 adb 命令不重复加前缀",
          device_cmd("adb shell dumpsys battery") == "adb shell dumpsys battery",
          device_cmd("adb shell dumpsys battery"))
    check("fastboot 命令不动",
          device_cmd("fastboot reboot") == "fastboot reboot",
          device_cmd("fastboot reboot"))
    check("非设备命令（host 命令）不加前缀",
          device_cmd("adb devices") == "adb devices",
          device_cmd("adb devices"))

    # 关键回归：命令表里的每条命令经 device_cmd() 解析后都必须指向设备，
    # 不能有命令漏到 Windows 的 cmd.exe（那会报「不是内部或外部命令」）。
    # 只列「(标签, 命令)」形状的表：其它形状（如 PACK_ITEMS 的
    # (key, label, file, command, timeout)）会被下面的提取逻辑误当成命令。
    COMMAND_TABLES = [
        ("tools_system", "SYSTEM_QUERIES", "REBOOT_MODES"),
        ("tools_device", "QUERIES"),
    ]
    host_commands = []
    resolved_samples = []
    for module_name, *attrs in COMMAND_TABLES:
        module = __import__(module_name)
        for attr in attrs:
            value = getattr(module, attr, None)
            if isinstance(value, str):
                entries = [value]
            elif isinstance(value, (list, tuple)):
                entries = [v[1] for v in value
                           if isinstance(v, (list, tuple)) and len(v) >= 2
                           and isinstance(v[1], str)]
            else:
                continue
            for command in entries:
                if not command.strip():
                    continue
                resolved = device_cmd(command)
                if not resolved.startswith(("adb ", "fastboot ")):
                    host_commands.append(f"{module_name}.{attr}: {command}")
                elif len(resolved_samples) < 3:
                    resolved_samples.append(resolved)

    check("命令表全部解析为设备端命令（没有命令漏到 cmd.exe）", not host_commands,
          "; ".join(host_commands[:3]) + " | 样例: " + "; ".join(resolved_samples))

    collected = []

    def collect_run(command, label=None, **kwargs):
        collected.append((device_cmd(command), label))

    runner.run = collect_run
    try:
        # 触摸模块
        touch = tools_page_obj.sections["touch"]
        touch.tap_x.setValue(540)
        touch.tap_y.setValue(1200)
        touch.do_tap()
        check("input tap 命令",
              collected[-1][0] == "adb shell input tap 540 1200", collected[-1][0])

        touch.sw_x1.setValue(540); touch.sw_y1.setValue(1800)
        touch.sw_x2.setValue(540); touch.sw_y2.setValue(600)
        touch.sw_duration.setValue(300)
        touch.do_swipe()
        check("input swipe 命令",
              collected[-1][0] == "adb shell input swipe 540 1800 540 600 300",
              collected[-1][0])

        touch.key_input.setText("KEYCODE_HOME")
        touch.send_key()
        check("input keyevent 命令",
              collected[-1][0] == "adb shell input keyevent KEYCODE_HOME",
              collected[-1][0])

        touch.send_key("26")
        check("keyevent 直接用数字键码",
              collected[-1][0] == "adb shell input keyevent 26", collected[-1][0])

        touch.capture_events()
        check("getevent 抓取带超时与过滤",
              "timeout 5 getevent" in collected[-1][0] and "ABS_MT" in collected[-1][0],
              collected[-1][0])
        check("getevent 管道被引号包裹交给设备端解析",
              collected[-1][0].startswith('adb shell "')
              and collected[-1][0].endswith('"'),
              collected[-1][0])

        # 触摸可视化开关
        touch.set_touch_switch("show_touches", "划线界面", True)
        check("打开划线界面命令",
              collected[-1][0] == "adb shell settings put system show_touches 1",
              collected[-1][0])
        touch.set_touch_switch("show_touches", "划线界面", False)
        check("关闭划线界面命令",
              collected[-1][0] == "adb shell settings put system show_touches 0",
              collected[-1][0])
        touch.set_touch_switch("pointer_location", "指针位置", True)
        check("打开指针位置命令",
              collected[-1][0] == "adb shell settings put system pointer_location 1",
              collected[-1][0])
        touch.set_touch_switch("pointer_location", "指针位置", False)
        check("关闭指针位置命令",
              collected[-1][0] == "adb shell settings put system pointer_location 0",
              collected[-1][0])
        touch.read_touch_switches()
        check("读取开关状态为两条独立命令（settings get 一次只接一个键）",
              len(collected) >= 2
              and "settings get system pointer_location" in collected[-1][0]
              and "settings get system show_touches" in collected[-2][0],
              f"{collected[-2][0]} | {collected[-1][0]}")

        # 系统模块
        system = tools_page_obj.sections["system"]
        system.prop_combo.setCurrentText("ro.product.model")
        system.get_property()
        check("getprop 命令",
              collected[-1][0] == "adb shell getprop ro.product.model",
              collected[-1][0])

        system.prop_value.setText("MTP-Test")
        system.set_property()
        check("setprop 命令",
              collected[-1][0] == "adb shell setprop ro.product.model MTP-Test",
              collected[-1][0])

        system.gov_combo.setCurrentText("performance")
        system.apply_governor()
        check("调频策略写入命令",
              "echo performance >" in collected[-1][0], collected[-1][0])

        system.freq_edit.setText("1800000")
        system.apply_max_freq()
        check("最大频率写入命令",
              "1800000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
              in collected[-1][0], collected[-1][0])

        # 显示模块：背光 / 分辨率 / 刷新率（DCS 读写节点已按 func-list 移除）
        before = len(collected)
        display.get_brightness()
        backlight_cmds = [c for c, _l in collected[before:]]
        check("读取背光发了两条（settings + 节点）", len(backlight_cmds) == 2,
              str(backlight_cmds))
        check("第一条读 settings 亮度",
              backlight_cmds and
              "settings get system screen_brightness" in backlight_cmds[0],
              str(backlight_cmds[:1]))
        # 背光节点路径：实测 T820 上 /sys/class/leds/ 下只有 mmc0:: / mmc1::，
        # 根本没有 lcd-backlight；正确的是 /sys/class/backlight/panel0-backlight
        # （通用/高通）或 /sys/class/backlight/sprd_backlight（展锐）
        node_cmd = backlight_cmds[1] if len(backlight_cmds) > 1 else ""
        check("读背光走 panel0-backlight 节点", "panel0-backlight" in node_cmd,
              node_cmd)
        check("读背光带 sprd_backlight 回退", "sprd_backlight" in node_cmd, node_cmd)
        check("不再用不存在的 /sys/class/leds/lcd-backlight",
              "lcd-backlight" not in node_cmd, node_cmd)

        display.bright_value.setText("200")
        display.set_brightness_node()
        check("写节点命令指向 panel0-backlight/brightness",
              "> /sys/class/backlight/panel0-backlight/brightness" in collected[-1][0],
              collected[-1][0])
        check("写节点带回退链",
              "sprd_backlight/brightness" in collected[-1][0], collected[-1][0])
        check("写节点不走 settings",
              "settings put" not in collected[-1][0], collected[-1][0])

        display.res_combo.setCurrentText("1080x2400")
        display.apply_resolution()
        check("分辨率设置命令",
              collected[-1][0] == "adb shell wm size 1080x2400", collected[-1][0])

        # DCS 包构造不碰设备，只算字节序列
        display.dcs_cmd.setText("0x1a")
        display.dcs_params.setText("0x2b 0x3c")
        sequence = display.build_dcs()
        check("DCS 构造生成 0x39 长包",
              sequence == [0x39, 0x00, 0x00, 0x03, 0x1A, 0x2B, 0x3C], str(sequence))
        check("DCS 构造结果落在只读框里",
              display.dcs_data.text() == "0x39 0x00 0x00 0x03 0x1a 0x2b 0x3c",
              display.dcs_data.text())
        check("DCS 构造不产生任何设备命令",
              all("dcs_write" not in c for c, _l in collected),
              str([c for c, _l in collected if "dcs_write" in c]))
        check("DCS 输出框是只读的", display.dcs_data.isReadOnly())

        # 所有命令都应以 adb 开头（或 adb shell 包裹）
        bad = [c for c, _l in collected if not c.strip().startswith("adb ")]
        check("所有命令都以 adb 开头", not bad, str(bad))

        # ylog 的 Project / Sub-Name 输入框宽度：以前各限死 120/160，两个框
        # 加起来比卡片还宽，双双被挤到 70px（Sub-Name 只看得见四五个字）
        shell = window.pages["shell"]
        for name, label in (("ylogpath_2", "Project"), ("ylogpath_3", "Sub-Name")):
            box = getattr(shell, name)
            check("{} 输入框宽度 >= 90px".format(label), box.width() >= 90,
                  "{}px".format(box.width()))
        check("ylog 两个框没有限死最大宽度",
              shell.ylogpath_2.maximumWidth() >= 1000
              and shell.ylogpath_3.maximumWidth() >= 1000,
              "max={}/{}".format(shell.ylogpath_2.maximumWidth(),
                                 shell.ylogpath_3.maximumWidth()))

        # 引号必须成对，否则 shell 会解析出错
        unbalanced = [c for c, _l in collected if c.count('"') % 2 != 0]
        check("命令中双引号成对", not unbalanced, str(unbalanced))
    finally:
        runner.run = original_run

    print("\n[11] 现场包抓取项（离线校验命令拼装）")
    from tools_sitepack import PACK_ITEMS, build_command
    check("抓取项数量合理", len(PACK_ITEMS) >= 15, str(len(PACK_ITEMS)))
    check("每项都是 5 元组",
          all(len(item) == 5 for item in PACK_ITEMS),
          str([len(i) for i in PACK_ITEMS]))
    check("带管道的抓取项被引号包住",
          build_command("getprop | grep dsi") == 'adb shell "getprop | grep dsi"',
          build_command("getprop | grep dsi"))
    check("指定序列号时不会出现两个 -s",
          build_command("dmesg", serial="ABC").count("-s") == 1,
          build_command("dmesg", serial="ABC"))

    print("\n[12] 日志来源列表（含 dmesg 实时）")
    sources = [log.source_combo.itemText(i) for i in range(log.source_combo.count())]
    check("日志来源包含 dmesg -w 实时",
          any("dmesg" in t and "-w" in t for t in sources), str(sources))
    check("日志来源包含 dmesg 快照", any("dmesg" in t and "快照" in t for t in sources))
    check("流式来源配置了积压保留行数",
          all(len(item) == 3 for item in __import__("tools_log").LOG_SOURCES),
          str([len(i) for i in __import__("tools_log").LOG_SOURCES]))

    print("\n[13] 日志着色与「只看错误」过滤")
    COLOR_SAMPLES = [
        ("01-01 10:00:00.123  1234  1234 I ActivityManager: Start proc", "info"),
        ("01-01 10:00:01.789  2345  2345 E DisplayManager: failed to set mode", "error"),
        ("01-01 10:00:02.012  3456  3456 W dsi_panel: set_backlight level=128", "warn"),
        ("01-01 10:00:03.345  3456  3456 F libc: Fatal signal 11", "error"),
        ("01-01 10:00:09.000  9000  9000 D SurfaceFlinger: activeMode=1220x2712", "info"),
    ]

    def classify(line):
        if LEVEL_PATTERNS[0][1].search(line):
            return "error"
        if LEVEL_PATTERNS[1][1].search(line):
            return "warn"
        return "info"

    expected = [tone for _line, tone in COLOR_SAMPLES]
    actual = [classify(line) for line, _tone in COLOR_SAMPLES]
    check("等级判定 E/W/F 正确", actual == expected, f"{actual} != {expected}")

    log.only_error.setChecked(False)
    log._buffer = [line for line, _tone in COLOR_SAMPLES]
    log.render()
    check("全量渲染 5 行", "5 / 5" in log.count_label.text(), log.count_label.text())

    log.only_error.setChecked(True)
    log.render()
    check("只看错误 → 2 行", "2 / 5" in log.count_label.text(), log.count_label.text())
    shown = log.view.toPlainText().splitlines()
    check("过滤后只剩 E/F 行",
          all(("E " in ln or "F " in ln) for ln in shown) and len(shown) == 2,
          str(shown))
    log.only_error.setChecked(False)
    log.render()

    # 关键字高亮：不隐藏不匹配的行，只给命中的词加底色
    log.filter_edit.setText("dsi|backlight")
    log.highlight_check.setChecked(False)
    log.render()
    check("未勾高亮时按关键字过滤 → 1 行",
          "1 / 5" in log.count_label.text(), log.count_label.text())

    log.highlight_check.setChecked(True)
    log.render()
    check("勾上高亮后不隐藏任何行 → 5 / 5",
          "5 / 5" in log.count_label.text(), log.count_label.text())

    # 按文本片段读底色：QTextCursor.charFormat() 取的是光标前一个字符的格式，
    # 逐字符走容易错位，直接遍历 fragment 更可靠
    runs = []
    block = log.view.document().begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                if fmt.background().color().name() == theme.LOG_HIGHLIGHT.lower():
                    runs.append(fragment.text())
            iterator += 1
        block = block.next()
    check("命中关键字确实被加了底色", bool(runs), "高亮片段 {}".format(runs))
    check("高亮的就是关键字本身（不是整行）",
          all(run.lower() in ("dsi", "backlight") for run in runs),
          str(runs))
    check("关键字高亮的颜色取自主题令牌",
          theme.LOG_HIGHLIGHT.lower() not in ("#000000", "#ffffff"),
          theme.LOG_HIGHLIGHT)

    log.highlight_check.setChecked(False)
    log.filter_edit.setText("")
    log.render()
    check("清空过滤后恢复 5 行", "5 / 5" in log.count_label.text(),
          log.count_label.text())

    print("\n[14] 日志导出（拦截文件对话框）")
    from PyQt5.QtWidgets import QFileDialog
    export_path = os.path.join(ROOT, "devtools", "_export_test.txt")
    original_save = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **kw: (export_path, "文本文件 (*.txt)"))
    try:
        log.view.setPlainText("line-a\nline-b E error")
        log.export_log()
    finally:
        QFileDialog.getSaveFileName = original_save
    check("日志导出文件已生成", os.path.exists(export_path))
    if os.path.exists(export_path):
        content = open(export_path, encoding="utf-8").read()
        check("导出内容与视图一致", "line-a" in content and "line-b" in content, content[:60])
        os.remove(export_path)

    # 收尾
    window.pages["tools"].stop_background()
    app.processEvents()
    window.close()

    print(f"\n{'=' * 46}")
    if FAILURES:
        print(f"{len(FAILURES)}/{CHECKS[0]} 项失败：")
        for name in FAILURES:
            print("  -", name)
        return 1
    print(f"全部通过（{CHECKS[0]} 项检查）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
