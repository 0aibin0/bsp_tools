"""现场包模块自查（离线部分）。

用法：python devtools/_check_sitepack.py
"""

import os
import sys
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtWidgets import QApplication  # noqa: E402

import theme  # noqa: E402
import tools_page  # noqa: E402
import tools_sitepack as SP  # noqa: E402
from mainwindow import MainWindow  # noqa: E402

app = QApplication([])
app.setFont(theme.app_font())
app.setStyleSheet(theme.build_stylesheet())

window = MainWindow()
window.resize(1360, 840)
window.show()
app.processEvents()

page = window.pages["tools"]
print("模块列表:", [k for k, _l, _i, _c in tools_page.SECTIONS])
page.show_section("sitepack")
app.processEvents()

section = page.sections["sitepack"]
print("现场包已显示，右侧面板收起:", page.runner.isHidden())
print("默认勾选项:", len(section.selected_items()), "/", len(SP.PACK_ITEMS))
print("默认保存目录:", section._target_dir())
print("带管道命令拼装:", SP.build_command("getprop | grep -i dsi"))
print("普通命令拼装:", SP.build_command("dmesg"))
print("带序列号命令:", SP.build_command("dmesg", serial="99022393342169"))
print("文件名净化:", SP.safe_name("GK5 / 2.0:test"))

# 真机抓一小部分，验证 zip 结构与内容
if "--live" in sys.argv:
    section.note_edit.setText("selftest")
    for key, box in section.boxes.items():
        box.setChecked(key in ("props", "cmdline", "wm", "brightness"))
    section.start()
    import time
    for _ in range(600):
        app.processEvents()
        time.sleep(0.05)
        if section._collector is None:
            break
    path = getattr(section, "_last_pack", None)
    print("生成:", path)
    if path and os.path.isfile(path):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        print("包内文件:", names)
        print("包含 meta.txt:", "meta.txt" in names)
        with zipfile.ZipFile(path) as archive:
            meta = archive.read("meta.txt").decode("utf-8")
        print("meta 前几行:", meta.splitlines()[:4])
