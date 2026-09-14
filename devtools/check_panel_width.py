"""面板宽度约定检查：右侧那两个面板的文本框必须都是 240px。

为什么要有这个脚本：界面上"面板"和"里面的文本框"是两层，量错一层就会
各说各话——用户量的是文本框，如果按面板容器算就会差 30~46px。这个约定
踩过两次坑（执行结果 210 vs 240；Shell Log 在宽窗口涨到 354），所以固化成检查。

约定（分隔条分配值 → 文本框实测值）：
    常用工具 · 执行结果面板：270 → 240（卡片左右各 15px 内边距）
    Shell Tools · Log 面板：  286 → 240（分组框左右各 23px 内边距）
两者都**固定**，不随窗口变宽而变宽；想加宽由用户拖分隔条。

用法：python devtools/check_panel_width.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtWidgets import QApplication  # noqa: E402

import theme  # noqa: E402
from mainwindow import MainWindow  # noqa: E402

# 用户量的是文本框：两个面板都必须是 240
TEXTBOX_TARGET = 240
# 覆盖"窗口比默认小 / 默认 / 最大化 / 超宽屏"四种情况
SIZES = ["1280x800", "1300x700", "1360x840", "1440x900", "1920x1080", "2560x1440"]

FAILED = []


def check(label, ok, detail=""):
    print("  {}  {}  {}".format("PASS" if ok else "FAIL", label, detail))
    if not ok:
        FAILED.append(label)


app = QApplication([])
app.setFont(theme.app_font())
app.setStyleSheet(theme.build_stylesheet())

print("[1] Shell Tools · Log 面板文本框 = {}px".format(TEXTBOX_TARGET))
for size in SIZES:
    width, height = (int(v) for v in size.split("x"))
    window = MainWindow()
    window.resize(width, height)
    window.show()
    window.nav.select("shell")
    for _ in range(8):
        app.processEvents()
    page = window.pages["shell"]
    got = page.textBrowser.width()
    check("{} 文本框 {}px".format(size, got), got == TEXTBOX_TARGET,
          "分配 {} / 分组框 {}".format(page.split.sizes()[1],
                                       page.groupBox_2.width()))
    window.close()

print("\n[2] 常用工具 · 执行结果面板文本框 = {}px".format(TEXTBOX_TARGET))
for size in SIZES:
    width, height = (int(v) for v in size.split("x"))
    window = MainWindow()
    window.resize(width, height)
    window.show()
    for _ in range(6):
        app.processEvents()
    # 必须先切到常用工具页：程序会记住上次打开的页面，默认不一定停在它上面，
    # 而没被显示过的页面根本没排版（宽度是假的），量出来的值毫无意义
    window.nav.select("tools")
    for _ in range(6):
        app.processEvents()
    tools = window.pages["tools"]
    tools.show_section("device")       # 选一个会显示右侧面板的模块
    for _ in range(8):
        app.processEvents()
    panel = tools.runner.panel
    got = panel.view.width() if panel is not None and not panel.isHidden() else -1
    check("{} 文本框 {}px".format(size, got), got == TEXTBOX_TARGET,
          "分配 {}".format(tools.splitter.sizes()[-1]))
    window.close()

print("\n[3] 启动就停在 Shell Tools 时也要正确")
# 回归场景：程序会记住上次打开的页面。如果上次停在 Shell Tools，on_page_shown()
# 是在 MainWindow 构造期跑的——那会儿布局没算，splitter 宽度是默认的 100，
# _apply_split_sizes() 会因为太窄直接返回；页面之后不再触发 on_page_shown，
# 日志面板就一直用 setupUi 的兜底值（曾经是 360 → 文本框 314px）。
# 修法是页面 showEvent 里补一次，这一节守的就是它。
for size in ("1360x840", "1920x1080"):
    width, height = (int(v) for v in size.split("x"))
    window = MainWindow()
    # 在 show 之前切到 shell：复刻"上次停在 Shell Tools"的启动路径
    window.nav.select("shell")
    for _ in range(4):
        app.processEvents()
    window.resize(width, height)
    window.show()
    for _ in range(10):
        app.processEvents()
    page = window.pages["shell"]
    got = page.textBrowser.width()
    check("{} 启动即在 Shell 时文本框 {}px".format(size, got),
          got == TEXTBOX_TARGET,
          "sizes={} _split_sized={}".format(page.split.sizes(),
                                            getattr(page, "_split_sized", False)))
    window.close()

print("\n" + "=" * 46)
if FAILED:
    print("失败 {} 项：{}".format(len(FAILED), "、".join(FAILED)))
    sys.exit(1)
print("面板宽度约定全部符合（文本框 {}px）".format(TEXTBOX_TARGET))
