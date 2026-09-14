"""诊断 Shell Tools 页在给定窗口尺寸下的实际布局。

用法：
    python devtools/diag_shell_layout.py [宽] [高]
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtWidgets import QApplication, QGroupBox, QPushButton, QLineEdit, QComboBox  # noqa: E402

import theme                                     # noqa: E402
from mainwindow import MainWindow                # noqa: E402

WIDTH = int(sys.argv[1]) if len(sys.argv) > 1 else 1360
HEIGHT = int(sys.argv[2]) if len(sys.argv) > 2 else 860

app = QApplication([])
app.setFont(theme.app_font())
app.setStyleSheet(theme.build_stylesheet())

window = MainWindow()
window.resize(WIDTH, HEIGHT)
window.show()
window.nav.select("shell")
app.processEvents()
app.processEvents()

page = window.pages["shell"]
print(f"窗口 {WIDTH}x{HEIGHT}")
print(f"内容区 stack: {window.stack.width()}x{window.stack.height()}")
print(f"Shell 页:     {page.width()}x{page.height()}")
print(f"页面最小尺寸: {page.minimumSizeHint().width()}x{page.minimumSizeHint().height()}")
print(f"页面 sizeHint: {page.sizeHint().width()}x{page.sizeHint().height()}")
print()

print("=== 分组框几何 / 最小需求 ===")
groups = page.findChildren(QGroupBox)
for g in groups:
    title = g.title()
    geo = g.geometry()
    minw = g.minimumSizeHint().width()
    minh = g.minimumSizeHint().height()
    flag = ""
    if geo.width() < minw:
        flag += " <宽不足!"
    if geo.height() < minh:
        flag += " <高不足!"
    print(f"  {title:18} geo={geo.width():4}x{geo.height():4}  min={minw:4}x{minh:4}{flag}")

print()
print("=== 关键控件几何 / 最小需求 ===")
names = [
    ("debug_shell_cmd", "Debug 命令输入"),
    ("debug_shell_run", "Run"),
    ("debug_shell_stop", "Stop"),
    ("debug_density_val", "density 值"),
    ("debug_printk_level", "printk 等级"),
    ("flash_partition", "烧录分区"),
    ("flash_img_path", "镜像路径"),
    ("flash_browse", "浏览按钮"),
    ("gpio_num", "GPIO 编号"),
    ("func_screencap", "screencap 按钮"),
    ("ylogpath", "ylog 路径"),
    ("ylogpath_2", "Project"),
    ("ylogpath_3", "Sub-Name"),
    ("apk1_path", "APK 路径"),
    ("scrcpy_path", "scrcpy 路径"),
    ("textBrowser", "日志区"),
]
for attr, label in names:
    widget = getattr(page, attr, None)
    if widget is None:
        print(f"  {label:16} 缺失!")
        continue
    geo = widget.geometry()
    minw = widget.minimumSizeHint().width()
    flag = ""
    if geo.width() < minw:
        flag += " <宽不足!"
    if geo.width() <= 0 or geo.height() <= 0:
        flag += " <尺寸为0!"
    print(f"  {label:16} geo={geo.width():4}x{geo.height():4}  min={minw:4}{flag}")

print()
print("=== adb 分组内按钮（用户说这里糊成一团）===")
adb_box = page.groupBox_4
print(f"  adb 框: {adb_box.width()}x{adb_box.height()}")
for btn in adb_box.findChildren(QPushButton):
    geo = btn.geometry()
    txt = btn.text()
    print(f"    {txt:20} geo={geo.width():4}x{geo.height():3} y={geo.y():4}")

print()
print("=== 底部日志区 ===")
print(f"  groupBox_2(log): {page.groupBox_2.width()}x{page.groupBox_2.height()}")
print(f"  textBrowser:     {page.textBrowser.width()}x{page.textBrowser.height()}")

print()
vertical_need = page.minimumSizeHint().height()
print(f"结论：页面最小高度需求 {vertical_need}px，当前可用 {page.height()}px"
      f" -> {'放不下，会被压缩' if vertical_need > page.height() else '放得下'}")
