"""检查自动换行标签是否被压得显示不全。

用 inspect_ui 的通用判据（geo < minimumSizeHint）抓不到这种：QLabel 开了
wordWrap 之后 minimumSizeHint 的高度是按"最窄换行"算的，控件比它高就通过，
但实际宽度下需要的行数可能更多。

用法：python devtools/check_wraplabel.py [宽x高 ...]
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

import theme  # noqa: E402
from mainwindow import MainWindow  # noqa: E402

SIZES = sys.argv[1:] or ["1300x840", "1360x840", "1920x1080"]

app = QApplication([])
app.setFont(theme.app_font())
app.setStyleSheet(theme.build_stylesheet())

problems = []
for size in SIZES:
    width, height = (int(v) for v in size.split("x"))
    window = MainWindow()
    window.resize(width, height)
    window.show()
    for _ in range(4):
        app.processEvents()

    # 每个页面/模块都要量：QStackedWidget 只给当前页算尺寸
    pages = [("shell", window.pages["shell"])]
    tools = window.pages["tools"]
    import tools_page
    for key, label, _icon, _cls in tools_page.SECTIONS:
        tools.show_section(key)
        for _ in range(3):
            app.processEvents()
        pages.append(("tools." + key, tools.sections[key]))
    for key in ("initcode", "lk2kernel", "kernel2lk", "lk2bat"):
        pages.append((key, window.pages[key]))
    window.nav.select("tools")
    for _ in range(3):
        app.processEvents()

    for name, page in pages:
        for label in page.findChildren(QLabel):
            if not label.wordWrap() or not label.isVisible():
                continue
            text = label.text()
            if not text.strip() or "<" in text:
                continue
            available = label.width()
            if available < 20:
                continue
            needed = label.fontMetrics().boundingRect(
                0, 0, available, 10000,
                Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text).height()
            if needed > label.height() + 2:
                problems.append((size, name, text[:28], label.height(), needed))
    window.close()
    for _ in range(2):
        app.processEvents()

if problems:
    print("发现 {} 处换行标签高度不足：".format(len(problems)))
    for size, name, text, got, need in problems:
        print("  [{}] {} · {!r} 高 {} < 需要 {}".format(size, name, text, got, need))
    sys.exit(1)
print("所有尺寸下自动换行标签都放得下（{} 个尺寸）".format(len(SIZES)))
