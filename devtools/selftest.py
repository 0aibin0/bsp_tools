"""功能自测：不依赖真机，用合成数据验证第 6 页各子功能的逻辑。

用法（仓库根目录）：
    .venv\\Scripts\\python.exe devtools\\selftest.py
"""

import os
import sys
import json
import time
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


class _QuietHandler(__import__("http.server", fromlist=["SimpleHTTPRequestHandler"])
                   .SimpleHTTPRequestHandler):
    """静音的静态文件服务：自测里起本地 HTTP 时别把请求日志刷到 stderr。"""

    def log_message(self, *args, **kwargs):    # noqa: D102
        pass


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

    print("\n[0] 侧边栏：快捷操作项放得下")
    # 快捷操作是个只增不减的清单（命令往下沉就到这儿），项数一多会把侧边栏
    # 底部的内容顶出去，所以量一下最后一项的底部位置
    from PyQt5.QtWidgets import QPushButton
    nav = window.nav
    nav_buttons = [b for b in nav.findChildren(QPushButton) if b.isVisible()]
    nav_bottom = max(b.mapTo(nav, b.rect().bottomLeft()).y() for b in nav_buttons)
    check("侧边栏内容没超出下边界", nav_bottom < nav.height(),
          "底部 {} / 侧边栏高 {}".format(nav_bottom, nav.height()))
    check("侧边栏按钮全部可见（没被挤掉）",
          len(nav_buttons) == len(nav.findChildren(QPushButton)),
          "{} / {}".format(len(nav_buttons), len(nav.findChildren(QPushButton))))
    quick_labels = [b.text() for b in nav_buttons]
    for label in ("remount", "启动参数"):
        check("快捷操作包含「{}」".format(label), label in quick_labels,
              str(quick_labels))

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

    print("\n[5] 命令收藏：增删改 + 持久化 + 与命令面板共用同一份数据")
    import command_store
    import command_palette
    fav = window.pages["tools"].sections["favorites"]
    fpath = fav.store.path
    backup = None
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as handle:
            backup = handle.read()

    before = len(fav.items)
    fav.name_edit.setText("自测命令")
    fav.command_edit.setText("adb shell echo self-test")
    fav.group_combo.setCurrentText("自测")
    fav.save_entry()
    check("新增一条收藏", len(fav.items) == before + 1, str(len(fav.items)))
    check("收藏写入本地文件", os.path.exists(fpath), fpath)
    check("本地文件就是唯一数据文件 DisplayTools.json",
          os.path.basename(fpath) == "DisplayTools.json", fpath)
    # 新增的这条必须真的在文件里（不是只在内存里）
    import app_data
    _raw = json.load(open(fpath, encoding="utf-8"))
    check("新增的命令真的落进文件的 commands 段",
          any(item.get("command") == "adb shell echo self-test"
              for item in _raw.get(app_data.SECTION_COMMANDS, [])),
          str(_raw.get(app_data.SECTION_COMMANDS, [])[-2:]))
    check("设置也在同一个文件里（config 段）",
          isinstance(_raw.get(app_data.SECTION_CONFIG), dict)
          and bool(_raw.get(app_data.SECTION_CONFIG)),
          str(list(_raw.get(app_data.SECTION_CONFIG, {}))[:4]))
    fav.search_edit.setText("自测命令")
    fav.render_list()
    check("搜索结果 1 条", fav.list_widget.count() == 1, str(fav.list_widget.count()))
    fav.search_edit.clear()
    fav.render_list()
    check("清空搜索后条目数恢复", fav.list_widget.count() == len(fav.items),
          f"{fav.list_widget.count()} vs {len(fav.items)}")

    # ---- 命令面板与命令收藏用的是同一份数据 ----
    check("收藏页与命令面板同一个 store",
          fav.store is command_store.store(), "不是同一个实例")

    def fake_ask(title, label, default):
        return ("面板命令", True) if "名字" in label else ("调试", True)

    dlg = command_palette.CommandPaletteDialog(fav.store, None, ask=fake_ask)
    dlg.filter("self-test")
    check("面板搜得到收藏页里加的命令",
          dlg.listing.count() >= 1 and "self-test" in dlg.current_command(),
          f"count={dlg.listing.count()} cur={dlg.current_command()!r}")

    chosen = []
    dlg.commandChosen.connect(lambda command, label: chosen.append(command))
    dlg.run_current()
    check("面板回车执行选中的命令",
          chosen and chosen[0] == "adb shell echo self-test", str(chosen))

    dlg.search.setText("adb shell echo from-palette")
    added, saved_name = dlg.save_current()
    check("面板「存为收藏」写入本地文件", added, str(added))
    reread = command_store.CommandStore(fpath)
    check("新命令确实落盘",
          any(item["command"] == "adb shell echo from-palette" for item in reread.items),
          str([item["command"] for item in reread.items][-3:]))
    fav.reload()
    check("收藏页立刻看到面板新增的命令",
          any(item["command"] == "adb shell echo from-palette" for item in fav.items),
          str(len(fav.items)))
    again, _ = dlg.save_current()
    check("同一条命令不会重复收藏", again is False, str(again))

    # ---- 删除：走界面上的「删除」按钮流程，本地文件里也必须没有 ----
    from PyQt5.QtWidgets import QMessageBox
    original_question = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.Yes)
    try:
        fav.search_edit.setText("from-palette")
        fav.render_list()
        index = fav.store.find_by_command("adb shell echo from-palette")
        fav.list_widget.setCurrentRow(fav._rendered.index(index))
        fav.delete_selected()
    finally:
        QMessageBox.question = original_question
    fav.search_edit.clear()          # 别把过滤条件留给后面的用例
    fav.render_list()
    check("界面删除后 store 里没有了",
          fav.store.find_by_command("adb shell echo from-palette") is None,
          str(len(fav.items)))
    _raw = json.load(open(fpath, encoding="utf-8"))
    check("删除后文件的 commands 段里没有这条命令",
          not any(item.get("command") == "adb shell echo from-palette"
                  for item in _raw.get(app_data.SECTION_COMMANDS, [])),
          str([i.get("command") for i in _raw.get(app_data.SECTION_COMMANDS, [])][-3:]))
    # 重新开一个 store（等价于重启程序）确认删除是真的生效了
    fresh = command_store.CommandStore(data=app_data.AppData(fpath, migrate=False))
    check("重启后再读也看不到被删的命令",
          fresh.find_by_command("adb shell echo from-palette") is None,
          str(len(fresh.items)))

    # ---- 全删光不能把内置默认塞回来 ----
    keep = list(fresh.items)
    fresh.items = []
    fresh.save()
    reread_empty = command_store.CommandStore(data=app_data.AppData(fpath, migrate=False))
    check("命令全删光后重启仍是空的（不会恢复默认）",
          reread_empty.items == [], str(len(reread_empty.items)))
    fresh.items = keep
    fresh.save()

    # ---- 清理：删掉自测条目并恢复原文件 ----
    for command in ("adb shell echo self-test", "adb shell echo from-palette"):
        index = fav.store.find_by_command(command)
        if index is not None:
            fav.store.remove(index)
    check("清理自测数据", fav.store.find_by_command("adb shell echo self-test") is None,
          str(len(fav.items)))
    if backup is None:
        if os.path.exists(fpath):
            os.remove(fpath)
    else:
        with open(fpath, "w", encoding="utf-8") as handle:
            handle.write(backup)
    fav.reload()

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

        # 收藏夹执行也不跳转。这条临时命令直接落在共享 store 上，用完删掉，
        # 不经过 store.add（免得写盘污染真实 favorites.json）。
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

    print("\n[15] 检查更新：版本比较 + 附件挑选 + 真下载")
    import update_check
    check("解析 v3.2.13", update_check.parse_version("v3.2.13") == (3, 2, 13),
          str(update_check.parse_version("v3.2.13")))
    check("解析 3.2.13（不带 v）", update_check.parse_version("3.2.13") == (3, 2, 13))
    check("解析垃圾返回 None", update_check.parse_version("main") is None)
    check("3.2.13 比 3.2.12 新", update_check.is_newer("v3.2.13", "v3.2.12") is True)
    check("同版本不算新", update_check.is_newer("v3.2.12", "v3.2.12") is False)
    asset = update_check.pick_asset([
        {"name": "README.txt", "size": 10, "url": "u1", "browser_download_url": "b1"},
        {"name": "DisplayTools.zip", "size": 20, "url": "u2", "browser_download_url": "b2"},
        {"name": "DisplayTools.exe", "size": 1024, "url": "u3", "browser_download_url": "b3"}])
    check("优先挑 DisplayTools.exe", asset and asset["name"] == "DisplayTools.exe",
          str(asset))
    check("没有 exe 时退到 zip",
          update_check.pick_asset([{"name": "a.txt"}, {"name": "DisplayTools.zip"}])["name"]
          == "DisplayTools.zip")
    check("空附件列表返回 None", update_check.pick_asset([]) is None)
    check("下载文件名固定 DisplayTools.exe（不带版本号）",
          update_check.default_download_name({"name": "DisplayTools.exe"}, "v3.2.15")
          == "DisplayTools.exe",
          update_check.default_download_name({"name": "DisplayTools.exe"}, "v3.2.15"))
    check("附件名带版本号也会被规范成 DisplayTools.exe",
          update_check.default_download_name({"name": "DisplayTools_v9.9.9.exe"}, "v9.9.9")
          == "DisplayTools_v9.9.9.exe"
          and update_check.default_download_name({"name": "x.zip"}, "v9.9.9")
          == "DisplayTools.exe",
          update_check.default_download_name({"name": "x.zip"}, "v9.9.9"))
    check("从源码跑时不自动替换", update_check.can_self_update() is False)
    check("源码模式下落到数据目录的 DisplayTools.exe",
          os.path.basename(update_check.staged_path({"name": "DisplayTools.exe"}, "v9"))
          == "DisplayTools.exe",
          update_check.staged_path({"name": "DisplayTools.exe"}, "v9"))
    check("大小格式化", update_check.human_size(1536) == "1.5 KB",
          update_check.human_size(1536))

    # 仓库兜底：contents 目录列表里挑 exe（没建 Release 时走这条路）
    listing = [
        {"name": "notes.txt", "path": "bsp_tools/dist/notes.txt", "size": 3, "url": "u0"},
        {"name": "DisplayTools_v3.1.0.exe", "path": "bsp_tools/dist/DisplayTools_v3.1.0.exe",
         "size": 100, "url": "u1"},
        {"name": "DisplayTools.exe", "path": "bsp_tools/dist/DisplayTools.exe",
         "size": 200, "url": "u2"},
    ]
    picked = update_check._pick_from_listing(listing)
    check("仓库目录列表优先挑不带版本号的 exe",
          picked and picked["name"] == "DisplayTools.exe" and picked.get("from_repo"),
          str(picked))
    check("目录里没有 exe 时返回 None",
          update_check._pick_from_listing([{"name": "a.txt"}]) is None)

    repo_file = {"name": "DisplayTools.exe", "path": "bsp_tools/dist/DisplayTools.exe",
                 "size": 1024, "url": "https://api.github.com/x", "from_repo": True}
    url, headers = update_check.download_target(repo_file)
    check("仓库文件走 contents API + raw", url == "https://api.github.com/x"
          and headers["Accept"] == "application/vnd.github.raw", str(headers))
    rel_url, rel_headers = update_check.download_target(
        {"name": "DisplayTools.exe", "browser_download_url": "https://example/b.exe",
         "url": "https://api.github.com/y"})
    check("Release 附件默认走 browser_download_url（无 token）",
          rel_url == "https://example/b.exe"
          and rel_headers["Accept"] == "application/octet-stream", rel_url)

    # 真下载：本地起一个 HTTP 服务，走完整的 download_asset 流程
    import threading
    import http.server
    import functools
    import tempfile
    serve_dir = tempfile.mkdtemp(prefix="dt-upd-")
    # 真实的 exe 头 + 过 1MB 的下限，才能过下载校验（MZ + 大小）
    payload = b"MZ" + os.urandom(1200 * 1024)
    src = os.path.join(serve_dir, "DisplayTools.exe")
    with open(src, "wb") as handle:
        handle.write(payload)
    handler = functools.partial(_QuietHandler, directory=serve_dir)
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local_url = "http://127.0.0.1:{}/DisplayTools.exe".format(server.server_port)
    target = os.path.join(serve_dir, "out", "DisplayTools_v9.9.9.exe")
    seen = []
    try:
        saved = update_check.download_asset(
            {"name": "DisplayTools.exe", "url": local_url,
             "browser_download_url": local_url, "size": len(payload)},
            target, progress=lambda done, total: seen.append((done, total)))
        check("附件下载成功", os.path.exists(saved), saved)
        check("下载内容与源文件一致",
              open(saved, "rb").read() == payload, "字节不一致")
        check("进度回调拿到了总长度", seen and seen[-1][1] == len(payload),
              str(seen[-1:]))
        check("没有留下 .part 残留", not os.path.exists(target + ".part"))
        # 附件声明的大小和实收不符 → 必须拒绝（代理截断就是这种形态）
        bad_target = os.path.join(serve_dir, "out", "wrong.exe")
        raised = None
        try:
            update_check.download_asset(
                {"name": "DisplayTools.exe", "url": local_url,
                 "browser_download_url": local_url, "size": len(payload) + 999},
                bad_target)
        except Exception as exc:                            # noqa: BLE001
            raised = exc
        check("附件声明大小不符时拒绝落盘",
              isinstance(raised, update_check.DownloadError), repr(raised))
        check("拒绝后不留 .new/.part",
              not os.path.exists(bad_target)
              and not os.path.exists(bad_target + ".part"),
              str(sorted(os.listdir(os.path.join(serve_dir, "out")))))
    except Exception as exc:                                # noqa: BLE001
        check("附件下载成功", False, "{}: {}".format(type(exc).__name__, exc))
    finally:
        server.shutdown()
        import shutil
        shutil.rmtree(serve_dir, ignore_errors=True)

    # 主窗口：发现新版本时给出「下载新版本」入口（不联网，用假结果驱动）
    import info_dialog
    window._update_checker = type("FakeChecker", (), {"result": {
        "tag": "v9.9.9",
        "asset": {"name": "DisplayTools.exe", "size": 1024,
                  "url": "", "browser_download_url": ""},
        "notes": "- 自测用的更新说明",
        "html_url": "https://example.invalid/releases/tag/v9.9.9"}})()
    opened = []
    original_exec = info_dialog.InfoDialog.exec_
    info_dialog.InfoDialog.exec_ = lambda self: opened.append(self)
    try:
        window._offer_update("发现新版本 v9.9.9（当前 {}）".format(theme.APP_VERSION))
    finally:
        info_dialog.InfoDialog.exec_ = original_exec
    check("发现新版本会弹出更新说明框", len(opened) == 1, str(len(opened)))
    if opened:
        labels = [label for label, _btn in opened[0]._action_buttons]
        text = opened[0].view.toPlainText()
        check("更新框里有下载与打开发布页两个入口",
              "下载新版本" in labels and "打开发布页" in labels, str(labels))
        check("说明里带附件名与大小", "DisplayTools.exe" in text and "1.0 KB" in text,
              text[:120])
        check("从源码跑时说明里讲清不会自动替换",
              "不会自动替换" in text and "下载并重启" in text, text[-260:])
        check("保存路径是 DisplayTools.exe（不带版本号）",
              "DisplayTools_v" not in text, text[:400])

    # 打包运行时：按钮变成「下载并重启」，说明里交代自动退出与 .old 备份
    real_frozen = getattr(sys, "frozen", False)
    real_exec = sys.executable
    opened2 = []
    info_dialog.InfoDialog.exec_ = lambda self: opened2.append(self)
    try:
        sys.frozen = True
        sys.executable = os.path.join(tempfile.gettempdir(), "DisplayTools.exe")
        window._offer_update("发现新版本 v9.9.9（当前 {}）".format(theme.APP_VERSION))
    finally:
        info_dialog.InfoDialog.exec_ = original_exec
        if not real_frozen and hasattr(sys, "frozen"):
            del sys.frozen
        sys.executable = real_exec
    if opened2:
        labels2 = [label for label, _btn in opened2[0]._action_buttons]
        text2 = opened2[0].view.toPlainText()
        check("打包运行时按钮是「下载并重启」", "下载并重启" in labels2, str(labels2))
        check("说明里交代自动退出、换 exe、启动新版",
              "自动退出" in text2 and "启动新版本" in text2, text2[:400])
        check("说明里交代旧版备份 .old 与回退办法",
              "DisplayTools.exe.old" in text2 and "改回" in text2, text2[:400])
        check("保存到的是 exe 同目录的 .new（换名后即 DisplayTools.exe）",
              "DisplayTools.exe.new" in text2, text2[:400])
    else:
        check("打包运行时按钮是「下载并重启」", False, "对话框没打开")
    window._update_checker = None

    print("\n[16] 单一数据文件：老文件迁移 + 段语义")
    import tempfile
    import shutil
    from app_data import AppData, SECTION_CONFIG, SECTION_COMMANDS, SECTION_BOOKMARKS

    # 老三个文件 → 一个 json
    mdir = tempfile.mkdtemp(prefix="dt-migrate-")
    try:
        with open(os.path.join(mdir, "config.ini"), "w", encoding="utf-8") as handle:
            handle.write("[DEFAULT]\nwindow_width = 1366\nlast_page = tools\n")
        with open(os.path.join(mdir, "favorites.json"), "w", encoding="utf-8") as handle:
            json.dump([{"group": "常用", "name": "列出设备", "command": "adb devices"}],
                      handle, ensure_ascii=False)
        with open(os.path.join(mdir, "path_bookmarks.json"), "w", encoding="utf-8") as handle:
            json.dump(["/sdcard/", "/data/ylog/"], handle)
        mpath = os.path.join(mdir, "DisplayTools.json")
        migrated = AppData(mpath)
        check("迁移后生成唯一数据文件", os.path.isfile(mpath), mpath)
        check("设置迁进来了",
              migrated.get_section(SECTION_CONFIG, {}).get("window_width") == "1366",
              str(migrated.get_section(SECTION_CONFIG)))
        check("命令收藏迁进来了",
              len(migrated.get_section(SECTION_COMMANDS, [])) == 1,
              str(migrated.get_section(SECTION_COMMANDS)))
        check("路径书签迁进来了",
              migrated.get_section(SECTION_BOOKMARKS, []) == ["/sdcard/", "/data/ylog/"],
              str(migrated.get_section(SECTION_BOOKMARKS)))
        check("老文件改名成 .migrated（不删数据）",
              os.path.isfile(os.path.join(mdir, "config.ini.migrated"))
              and os.path.isfile(os.path.join(mdir, "favorites.json.migrated"))
              and os.path.isfile(os.path.join(mdir, "path_bookmarks.json.migrated")),
              str(sorted(os.listdir(mdir))))
        live = [f for f in os.listdir(mdir)
                if not f.endswith(".migrated") and not f.endswith(".tmp")]
        check("目录里只剩一个活的数据文件", live == ["DisplayTools.json"], str(live))
        again = AppData(mpath)
        check("再读一次不丢数据（迁移幂等）",
              len(again.get_section(SECTION_COMMANDS, [])) == 1
              and again.get_section(SECTION_CONFIG, {}).get("last_page") == "tools",
              str(again.get_section(SECTION_CONFIG)))
    finally:
        shutil.rmtree(mdir, ignore_errors=True)

    # 段语义：没有老文件 → 段不存在（用内置默认）；空数组 → 就是空
    edir = tempfile.mkdtemp(prefix="dt-empty-")
    try:
        epath = os.path.join(edir, "DisplayTools.json")
        empty = AppData(epath)
        check("首次运行不写文件（别在空目录里留垃圾）", not os.path.isfile(epath))
        check("没有 commands 段时返回 None（调用方用内置默认）",
              empty.get_section(SECTION_COMMANDS, None) is None)
        check("没有 path_bookmarks 段时返回 None（调用方用默认书签）",
              empty.get_section(SECTION_BOOKMARKS, None) is None)
        win = window.pages["tools"].sections["files"]
        check("文件管理页拿到的是默认书签", len(win.bookmarks) >= 5, str(win.bookmarks))
    finally:
        shutil.rmtree(edir, ignore_errors=True)

    # 设置写盘后仍在同一文件
    import app_config
    key = "selftest_marker"
    app_config.config().update(**{key: "1"})
    raw = json.load(open(app_config.config_path(), encoding="utf-8"))
    check("设置写进同一个文件的 config 段",
          raw.get(SECTION_CONFIG, {}).get(key) == "1", str(raw.get(SECTION_CONFIG, {}).get(key)))
    app_config.config().set(key, "")
    app_config.config().save()

    print("\n[17] 自动更新：换文件 + 重启（用两个假 exe 走真实流程）")
    sandbox = tempfile.mkdtemp(prefix="dt-swap-")
    try:
        fake_target = os.path.join(sandbox, "DisplayTools.exe")
        fake_staged = os.path.join(sandbox, "DisplayTools.exe.new")
        with open(fake_target, "w", encoding="utf-8") as handle:
            handle.write("OLD v3.2.14")
        with open(fake_staged, "w", encoding="utf-8") as handle:
            handle.write("NEW v3.2.15")

        # 暂存路径规则（打包运行时才 同目录 + .new），下面用假 frozen 验证
        real_frozen = getattr(sys, "frozen", False)
        real_exec = sys.executable
        try:
            sys.frozen = True
            sys.executable = fake_target
            check("打包运行时能自动替换", update_check.can_self_update() is True)
            check("暂存在 exe 同目录、名字是 DisplayTools.exe.new",
                  update_check.staged_path({"name": "DisplayTools.exe"}, "v3.2.15")
                  == os.path.join(sandbox, "DisplayTools.exe.new"),
                  update_check.staged_path({"name": "DisplayTools.exe"}, "v3.2.15"))
            check("备份路径是 DisplayTools.exe.old",
                  update_check.old_backup_path() == fake_target + ".old",
                  update_check.old_backup_path())
            script = update_check.swap_command(fake_staged, fake_target, pid=999999)
            check("更新脚本里同时有目标/新文件/备份三个路径",
                  fake_target in script and fake_staged in script
                  and (fake_target + ".old") in script)
            # 真跑一遍：等旧进程（这个假 PID）退出 → 换名 → 启动
            update_check.start_swap(fake_staged, fake_target, pid=999999)
            deadline = time.time() + 30
            while time.time() < deadline and os.path.exists(fake_staged):
                time.sleep(0.3)
            check("新文件已换到 DisplayTools.exe",
                  os.path.isfile(fake_target)
                  and open(fake_target, encoding="utf-8").read().startswith("NEW"),
                  open(fake_target, encoding="utf-8").read() if os.path.isfile(fake_target) else "-")
            check("旧版本留在 DisplayTools.exe.old（起不来能换回去）",
                  os.path.isfile(fake_target + ".old")
                  and open(fake_target + ".old", encoding="utf-8").read().startswith("OLD"),
                  "-")
            check("暂存 .new 文件已消费掉", not os.path.exists(fake_staged))
            check("启动成功后能清理 .old",
                  update_check.cleanup_old_backup() == fake_target + ".old"
                  and not os.path.exists(fake_target + ".old"))
        finally:
            if not real_frozen and hasattr(sys, "frozen"):
                del sys.frozen
            sys.executable = real_exec
    except Exception as exc:                                # noqa: BLE001
        check("自动替换流程跑通", False, "{}: {}".format(type(exc).__name__, exc))
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    print("\n[18] Shell Tools：命令框挪到 func 且吃得满宽度")
    window.resize(1360, 840)
    window.nav.select("shell")
    for _ in range(8):
        app.processEvents()
    shell = window.pages["shell"]
    cmd = shell.debug_shell_cmd
    check("命令框挂在 func 卡上（groupBox_6）",
          cmd.parent() is not None and cmd.parent().objectName() == "groupBox_6",
          cmd.parent().objectName() if cmd.parent() is not None else "无父级")
    check("Debug 卡里已经没有命令框",
          shell.groupBox_debug.findChild(type(cmd), "debug_shell_cmd") is None)
    check("命令框宽度 ≥ 600px（1360 窗口下吃满整行剩余宽度）",
          cmd.width() >= 600, "实得 %d" % cmd.width())
    check("命令框里能装下 60 个以上西文字符",
          cmd.width() / 7.5 >= 60, "%d 个" % int(cmd.width() / 7.5))
    check("Run / Stop 还在命令框右边",
          shell.debug_shell_run.x() > cmd.x() + cmd.width() - 5
          and shell.debug_shell_stop.x() > shell.debug_shell_run.x(),
          "cmd=%d run=%d stop=%d" % (cmd.x(), shell.debug_shell_run.x(),
                                     shell.debug_shell_stop.x()))
    check("Debug 卡搬走命令框后只剩 density / printk（比 ylog 矮）",
          shell.groupBox_debug.minimumSizeHint().height()
          < shell.groupBox_3.minimumSizeHint().height(),
          "debug=%d ylog=%d" % (shell.groupBox_debug.minimumSizeHint().height(),
                                shell.groupBox_3.minimumSizeHint().height()))
    check("命令框回车就是执行（placeholder 不是空话）",
          "回车" in cmd.lineEdit().placeholderText(),
          cmd.lineEdit().placeholderText())

    print("\n[19] 自动更新：下载完整性校验（DLL 报错的根因）")
    import http.server
    import threading
    import functools

    # 1) verify_update_file：完整 / 太小 / 大小不符 / 不是 exe / 不存在
    vdir = tempfile.mkdtemp(prefix="dt-verify-")
    try:
        good = os.path.join(vdir, "good.exe")
        with open(good, "wb") as handle:
            handle.write(b"MZ" + os.urandom(2 * 1024 * 1024))
        small = os.path.join(vdir, "small.exe")
        with open(small, "wb") as handle:
            handle.write(b"MZ" + os.urandom(64 * 1024))
        page = os.path.join(vdir, "page.exe")
        with open(page, "wb") as handle:
            handle.write(b"<html>" + os.urandom(2 * 1024 * 1024))
        check("完整 exe 通过校验", update_check.verify_update_file(good)[0] is True)
        check("太小的文件不通过（截断）",
              update_check.verify_update_file(small)[0] is False,
              str(update_check.verify_update_file(small)))
        check("大小对不上不通过",
              update_check.verify_update_file(good, 999)[0] is False)
        check("不是 PE（下到错误页）不通过",
              update_check.verify_update_file(page)[0] is False,
              str(update_check.verify_update_file(page)))
        check("文件不存在不通过",
              update_check.verify_update_file(os.path.join(vdir, "no.exe"))[0] is False)
    finally:
        shutil.rmtree(vdir, ignore_errors=True)

    # 2) 截断的 HTTP 响应：Content-Length 说 512KB，实际只给 128KB
    class _TruncatingHandler(http.server.BaseHTTPRequestHandler):
        body = os.urandom(512 * 1024)

        def log_message(self, *args, **kwargs):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body[:len(self.body) // 4])   # 只发 1/4 就断
            self.close_connection = True

    server2 = http.server.HTTPServer(("127.0.0.1", 0), _TruncatingHandler)
    threading.Thread(target=server2.serve_forever, daemon=True).start()
    tdir = tempfile.mkdtemp(prefix="dt-trunc-")
    try:
        url = "http://127.0.0.1:{}/DisplayTools.exe".format(server2.server_port)
        dest = os.path.join(tdir, "DisplayTools.exe.new")
        raised = None
        try:
            update_check.download_asset(
                {"name": "DisplayTools.exe", "url": url,
                 "browser_download_url": url, "size": 512 * 1024}, dest)
        except Exception as exc:                            # noqa: BLE001
            raised = exc
        check("截断的下载会被判为失败（不静默接受）",
              isinstance(raised, update_check.DownloadError), repr(raised))
        check("失败后不留半截文件", not os.path.exists(dest), str(os.listdir(tdir)))
        check("也不留 .part 残留",
              not any(name.endswith(".part") for name in os.listdir(tdir)),
              str(os.listdir(tdir)))

        # 3) UpdateDownloader 走一遍：同样必须报 error 且不留下文件
        downloader = update_check.UpdateDownloader(
            {"name": "DisplayTools.exe", "url": url,
             "browser_download_url": url, "size": 512 * 1024}, dest)
        got = []
        downloader.finished_with.connect(lambda kind, msg: got.append((kind, msg)))
        downloader.run()                                    # 直接同步跑，不起线程
        check("下载线程把截断判成 error",
              got and got[0][0] == "error" and "不完整" in got[0][1], str(got[:1]))
        check("下载线程不留下坏文件", not os.path.exists(dest))
    finally:
        server2.shutdown()
        shutil.rmtree(tdir, ignore_errors=True)

    # 4) 换文件脚本的大小闸门：对不上就绝不替换
    gdir = tempfile.mkdtemp(prefix="dt-gate-")
    try:
        gate_target = os.path.join(gdir, "DisplayTools.exe")
        gate_new = os.path.join(gdir, "DisplayTools.exe.new")
        with open(gate_target, "w", encoding="utf-8") as handle:
            handle.write("OLD")
        with open(gate_new, "w", encoding="utf-8") as handle:
            handle.write("NEW-BUT-WRONG-SIZE")
        script = update_check.swap_command(gate_new, gate_target, pid=999999,
                                           expected_size=999999999)
        check("换文件脚本带上了期望大小", "999999999" in script and "$expected" in script)
        update_check.start_swap(gate_new, gate_target, pid=999999,
                                expected_size=999999999)
        time.sleep(6)
        check("大小对不上时旧 exe 原封不动",
              open(gate_target, encoding="utf-8").read() == "OLD",
              open(gate_target, encoding="utf-8").read())
        check("大小对不上时不产生 .old",
              not os.path.exists(gate_target + ".old"))
        check("大小对不上时新文件也不动", os.path.isfile(gate_new))
    finally:
        shutil.rmtree(gdir, ignore_errors=True)

    # 5) 检查更新/下载的结果必须是"留得住"的对话框，不是几秒就没的浮层
    import command_store
    shown = []
    toasts = []
    real_exec = info_dialog.InfoDialog.exec_
    info_dialog.InfoDialog.exec_ = lambda self: shown.append(self)
    original_toast = window.toast
    window.toast = lambda *args, **kwargs: toasts.append(args[:1])
    try:
        # ok 分支：用 UpdateChecker 的替身同步发结果
        original_checker = update_check.UpdateChecker

        class DirectChecker(original_checker):
            def __init__(self, parent=None):
                super(DirectChecker, self).__init__(parent)
                self.result = {"tag": theme.APP_VERSION}

            def isRunning(self):
                return False

            def start(self):
                self.finished_with.emit("ok", "已是最新版本（{}）".format(theme.APP_VERSION))

        update_check.UpdateChecker = DirectChecker
        try:
            window.check_updates()
        finally:
            update_check.UpdateChecker = original_checker
        check("检查更新结果为「已是最新」时弹对话框（不是浮层）",
              len(shown) >= 1, "对话框 %d 个 / 浮层 %s" % (len(shown), toasts))
        if shown:
            check("对话框里写了当前版本与结论",
                  "已是最新" in shown[-1].view.toPlainText()
                  and theme.APP_VERSION in shown[-1].view.toPlainText(),
                  shown[-1].view.toPlainText()[:120])

        # error 分支
        shown[:] = []

        class ErrorChecker(DirectChecker):
            def start(self):
                self.finished_with.emit("error", "连不上 GitHub（URLError）")

        update_check.UpdateChecker = ErrorChecker
        try:
            window.check_updates()
        finally:
            update_check.UpdateChecker = original_checker
        check("检查更新失败也弹对话框并给出发布页",
              len(shown) >= 1 and "发布页" in shown[-1].view.toPlainText()
              or (shown and "github" in shown[-1].view.toPlainText().lower()),
              shown[-1].view.toPlainText()[:160] if shown else "没弹框")
    finally:
        info_dialog.InfoDialog.exec_ = real_exec
        window.toast = original_toast
        window._update_checker = None

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
