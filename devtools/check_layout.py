"""布局健康检查：在多个窗口尺寸下检测控件重叠、越界、被压扁。

判定规则：
1. 同一父容器内的兄弟控件矩形两两相交面积超过阈值 -> 重叠
2. 控件几何尺寸小于其 minimumSizeHint -> 被压缩（尺寸不足）
3. 控件矩形超出父容器边界 -> 越界/裁切

用法：
    python devtools/check_layout.py [宽x高 ...]
默认检查若干常见窗口尺寸。
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtWidgets import (QApplication, QWidget, QGroupBox,     # noqa: E402
                             QPushButton, QLineEdit, QComboBox, QLabel,
                             QSlider, QTextBrowser, QAbstractScrollArea)
from PyQt5.QtCore import QRect                                     # noqa: E402

import theme                                                        # noqa: E402
import tools_page                                                   # noqa: E402
from mainwindow import MainWindow                                   # noqa: E402

# 允许的取整误差
TOL = 3
OVERLAP_MIN_AREA = 40      # 相交面积小于此值视为取整噪声

# Qt 内部子控件（下拉框内嵌的输入框、表头等），尺寸由 Qt 自己管，不参与检查
INTERNAL_NAMES = {"QLineEdit", "QHeaderView", "QWidget", "qt_scrollarea_viewport",
                  "qt_scrollarea_hcontainer", "qt_scrollarea_vcontainer"}

# 参与尺寸检查的可见控件类型
CHECKED_TYPES = (QPushButton, QLineEdit, QComboBox, QGroupBox, QTextBrowser, QSlider)


def overlap_area(a, b):
    rect = a.intersected(b)
    if rect.isEmpty():
        return 0
    return rect.width() * rect.height()


def display_name(widget):
    name = widget.objectName()
    if name:
        return name
    title = getattr(widget, "title", None)
    if callable(title) and title():
        return f"{type(widget).__name__}({title()})"
    text = getattr(widget, "text", None)
    if callable(text) and text():
        return f"{type(widget).__name__}({text()})"
    return type(widget).__name__


def text_clipped(widget):
    """判断文字是否真的会被裁切。

    比 sizeHint 更贴近真实：按字体度量算文字宽度，再按控件类型减去
    实际留白（按钮的内边距、图标、下拉箭头等）。
    QLabel 没有额外内边距，只要文字宽度不超过控件宽度就不会裁切；
    开了自动换行的标签也不会横向裁切。
    """
    text = getattr(widget, "text", None)
    if not callable(text):
        return False
    value = text()
    if not value:
        return False

    metrics = widget.fontMetrics()
    text_width = metrics.horizontalAdvance(value)

    if isinstance(widget, QLabel):
        if widget.wordWrap():
            return False
        # ElidedLabel 自己会做省略号处理，不会硬裁切
        if type(widget).__name__ == "ElidedLabel":
            return False
        return text_width > widget.width() + TOL

    reserve = 0
    if isinstance(widget, QPushButton):
        reserve = 24                      # 左右内边距 + 边框
        icon = widget.icon()
        if icon is not None and not icon.isNull():
            reserve += 24                 # 图标 + 间距
    elif isinstance(widget, (QLineEdit, QComboBox)):
        reserve = 20
    else:
        reserve = 16

    return text_width + reserve > widget.width() + TOL


def audit_widget(widget, issues, path, depth=0, inside_scroll=False):
    """递归检查一个容器内的兄弟控件。"""
    children = [c for c in widget.children()
                if isinstance(c, QWidget) and c.isVisible() and c.width() > 0]

    # 滚动区的画布本来就比视口大，这是滚动的前提，不算越界
    in_scroll_canvas = inside_scroll or isinstance(widget, QAbstractScrollArea)

    # 1) 两两重叠 —— 最严重的问题（用户看到的"挤成一团"）
    for i in range(len(children)):
        for j in range(i + 1, len(children)):
            a, b = children[i], children[j]
            area = overlap_area(a.geometry(), b.geometry())
            if area > OVERLAP_MIN_AREA:
                issues.append(
                    f"重叠 {area}px²: {path}/{display_name(a)}"
                    f" <-> {path}/{display_name(b)}")

    for child in children:
        name = display_name(child)
        geo = child.geometry()

        # 2) 文字被裁切（用字体度量判断，避免 sizeHint 的误报）
        if type(child).__name__ not in INTERNAL_NAMES and text_clipped(child):
            issues.append(
                f"文字裁切: {path}/{name} 控件宽{geo.width()}"
                f" 放不下 {child.text()!r}")

        # 3) 下拉框被压得放不下内容
        if isinstance(child, QComboBox) and geo.width() + TOL < child.minimumSizeHint().width():
            issues.append(
                f"宽度不足: {path}/{name} 实得{geo.width()} < 需要{child.minimumSizeHint().width()}")

        # 4) 越界（滚动区画布除外：画布比视口大正是滚动的前提）
        if not in_scroll_canvas and child.objectName() != "qt_scrollarea_viewport" and (
                geo.right() > widget.width() + TOL
                or geo.bottom() > widget.height() + TOL
                or geo.left() < -TOL or geo.top() < -TOL):
            issues.append(
                f"越界: {path}/{name} geo={geo.getRect()} "
                f"父容器={widget.width()}x{widget.height()}")

        if child.children() and depth < 8:
            child_inside = in_scroll_canvas or child.objectName() == "qt_scrollarea_viewport"
            audit_widget(child, issues, f"{path}/{name}", depth + 1, child_inside)


def check_size(app, window, width, height):
    window.resize(width, height)
    app.processEvents()
    issues = []
    for key, page in window.pages.items():
        window.nav.select(key)
        app.processEvents()
        audit_widget(page, issues, key)
        if key == "tools":
            for section_key, section in page.sections.items():
                page.show_section(section_key)
                app.processEvents()
                audit_widget(section, issues, f"tools/{section_key}")
    return issues


def main():
    sizes = []
    for arg in sys.argv[1:]:
        if "x" in arg.lower():
            w, h = arg.lower().split("x")
            sizes.append((int(w), int(h)))
    if not sizes:
        sizes = [(1360, 860), (1280, 800), (1100, 840), (1440, 900), (1920, 1080)]

    app = QApplication([])
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())

    window = MainWindow()
    window.show()
    app.processEvents()

    total = 0
    for width, height in sizes:
        issues = check_size(app, window, width, height)
        total += len(issues)
        status = "OK" if not issues else f"{len(issues)} 个问题"
        print(f"\n[{width}x{height}] {status}")
        for issue in issues[:25]:
            print("   -", issue)
        if len(issues) > 25:
            print(f"   ... 另有 {len(issues) - 25} 条")

    window.pages["tools"].stop_background()
    app.processEvents()
    window.close()

    print(f"\n{'=' * 50}")
    if total:
        print(f"共发现 {total} 个布局问题")
        return 1
    print("所有尺寸下均无重叠 / 压缩 / 越界")
    return 0


if __name__ == "__main__":
    sys.exit(main())
