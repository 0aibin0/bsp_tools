"""界面尺寸查看工具

用途：查任意页面/模块下所有控件的真实几何尺寸，定位「挤在一起」「被裁掉」
「该撑开没撑开」这类布局问题。

用法（仓库根目录）：
    .venv\\Scripts\\python.exe devtools\\inspect_ui.py                 # 全部页面 + 9 个模块
    .venv\\Scripts\\python.exe devtools\\inspect_ui.py shell           # 只看 Shell Tools
    .venv\\Scripts\\python.exe devtools\\inspect_ui.py tools.battery   # 只看电池模块
    .venv\\Scripts\\python.exe devtools\\inspect_ui.py --screen shell  # 附带屏幕像素坐标
    .venv\\Scripts\\python.exe devtools\\inspect_ui.py --flag          # 只列有问题的
    .venv\\Scripts\\python.exe devtools\\inspect_ui.py --size 1368x892 shell

图标含义：
    OK     尺寸正常
    [压]   actual < minimumSizeHint，Qt 已经把它压到底线以下（可能文字糊成一团）
    [裁]   该横向撑开的控件没有撑开（有 Expanding 策略但宽度 <= sizeHint）
    [溢]   超出父容器边界（会被裁掉）
    [隐]   显式隐藏
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bsp_tools"))

from PyQt5.QtCore import Qt                                    # noqa: E402
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel,     # noqa: E402
                             QAbstractScrollArea)

import theme                                                   # noqa: E402
from mainwindow import MainWindow                              # noqa: E402
import tools_page                                              # noqa: E402

TOL = 2


def widget_path(widget, root):
    """widget 相对于 root 的完整层级路径。

    同类控件（比如一堆 Card）objectName 相同，所以路径里补上标题/文字，
    否则一排 Card#card 根本分不清谁是谁。
    """
    parts = []
    node = widget
    while node is not None and node is not root:
        name = node.objectName()
        if name and name.startswith("qt_"):
            node = node.parentWidget()
            continue
        if name:
            parts.append(name)
        else:
            parts.append(display_name(node))
        node = node.parentWidget()
    parts.reverse()
    return "/".join(parts) if parts else display_name(widget)


def display_name(widget):
    name = widget.objectName()
    if name and not name.startswith("qt_"):
        return name
    title = getattr(widget, "title", None)
    if callable(title) and title():
        return f"{type(widget).__name__}({title()})"
    text = getattr(widget, "text", None)
    if callable(text) and text():
        short = text().replace("\n", " ")[:22]
        return f"{type(widget).__name__}({short})"
    return type(widget).__name__


def is_internal(widget):
    """Qt 内部子控件，不参与检查。

    两类：
    1. 名字带 qt_ 前缀的（scrollarea_viewport、滚动条等）
    2. 复合控件内嵌的编辑框（QSpinBox / QComboBox / QDateTimeEdit 里的
       QLineEdit 等），它们的尺寸由父控件决定，单独看没意义，还会误报「被压缩」
    """
    name = widget.objectName()
    if name.startswith("qt_"):
        return True
    if type(widget).__name__ in ("QScrollBar", "QComboBoxPrivateContainer"):
        return True
    parent = widget.parentWidget()
    if parent is not None and type(parent).__name__ in (
            "QSpinBox", "QDoubleSpinBox", "QComboBox", "QDateTimeEdit",
            "QDateEdit", "QTimeEdit", "QFontComboBox"):
        return True
    return False


# 这些类型本该横向撑开，如果明显小于 sizeHint 说明没被撑开。
# 注意：布局容器（QSplitter / QStackedWidget）按可用宽度分配，比 sizeHint
# 窄一点是正常的，只有窄得离谱（< 80%）才算问题。
CONTENT_TYPES = {
    "QTextEdit": 0.85, "QTextBrowser": 0.85, "QPlainTextEdit": 0.85,
    "QTableWidget": 0.9, "QListWidget": 0.9, "QTreeWidget": 0.9,
    "QSplitter": 0.7, "QStackedWidget": 0.7, "QScrollArea": 0.7,
    "QTabWidget": 0.7,
}

# 这些控件的 sizeHint 包含标题/滚动条等"装饰"宽度，窄面板里本来就达不到；
# 单独放宽阈值，只拦真正的"被挤成一条缝"
WIDE_TOLERANCE = {"QTextBrowser": 0.5, "QPlainTextEdit": 0.5, "QTextEdit": 0.5}


def flags_for(widget, parent, inside_scroll=False):
    marks = []
    geo = widget.geometry()
    hint = widget.minimumSizeHint()

    # 隐藏控件还没被布局算过，尺寸没参考价值
    if widget.isHidden():
        return ["隐"]

    if not inside_scroll:
        if geo.width() + TOL < hint.width() or geo.height() + TOL < hint.height():
            marks.append("压")
        ratio = CONTENT_TYPES.get(type(widget).__name__)
        if ratio is not None:
            ratio = WIDE_TOLERANCE.get(type(widget).__name__, ratio)
        if ratio is not None and geo.width() < widget.sizeHint().width() * ratio - TOL:
            marks.append("裁")
        if parent is not None and not parent.isHidden():
            if (geo.right() > parent.width() + TOL
                    or geo.bottom() > parent.height() + TOL
                    or geo.left() < -TOL or geo.top() < -TOL):
                marks.append("溢")
    return marks


def screen_rect(widget):
    """控件在屏幕上的绝对坐标（用于肉眼定位）。"""
    top_left = widget.mapToGlobal(widget.rect().topLeft())
    return top_left.x(), top_left.y()


def walk(widget, root, rows, show_screen=False, depth=0, inside_scroll=False):
    in_scroll = inside_scroll or isinstance(widget, QAbstractScrollArea)
    hidden = widget.isHidden()
    for child in widget.children():
        if not isinstance(child, QWidget) or is_internal(child):
            continue
        if hidden:
            # 父级已隐藏，子级尺寸还没被布局算过，记一行说明后不再往下走
            rows.append({
                "depth": depth, "name": display_name(child),
                "path": "%s [%s]" % (widget_path(child, root), display_name(child))
                        if child.objectName() else widget_path(child, root),
                "x": 0, "y": 0, "w": 0, "h": 0, "mw": 0, "mh": 0,
                "sw": 0, "sh": 0, "marks": ["隐(父级隐藏)"],
            })
            continue

        geo = child.geometry()
        hint = child.minimumSizeHint()
        marks = flags_for(child, widget, in_scroll)
        x, y = screen_rect(child) if show_screen else (geo.x(), geo.y())
        rows.append({
            "depth": depth,
            "name": display_name(child),
            "path": "%s [%s]" % (widget_path(child, root), display_name(child))
                    if child.objectName() else widget_path(child, root),
            "x": x, "y": y, "w": geo.width(), "h": geo.height(),
            "mw": hint.width(), "mh": hint.height(),
            "sw": child.sizeHint().width(), "sh": child.sizeHint().height(),
            "marks": marks,
        })
        if child.children():
            # 滚动区本身的直接子级（viewport 与画布）不算越界
            walk(child, root, rows, show_screen, depth + 1,
                 in_scroll or isinstance(child, QAbstractScrollArea))


def report(title, root, show_screen=False, only_flagged=False):
    rows = []
    walk(root, root, rows, show_screen)
    if only_flagged:
        # 只看「真的有问题」的：隐藏控件单独一类，不混在问题里
        rows = [r for r in rows
                if any(m in ("压", "裁", "溢") for m in r["marks"])]

    print(f"\n{'=' * 104}")
    print(f"{title}   容器 {root.width()}x{root.height()}")
    print(f"{'=' * 104}")
    if not rows:
        print("  （无控件，或没有发现问题）")
        return 0

    print(f"  {'控件路径':<34} {'x':>6} {'y':>6} {'宽':>6} {'高':>5}"
          f" {'最小宽':>7} {'最小高':>7} {'sizeHint':>12}  标记")
    print("  " + "-" * 100)
    for row in rows:
        name = row["path"] or row["name"]
        name = name if len(name) <= 34 else "…" + name[-33:]
        marks = ",".join(row["marks"]) if row["marks"] else "OK"
        print(f"  {name:<34} {row['x']:>6} {row['y']:>6} {row['w']:>6} {row['h']:>5}"
              f" {row['mw']:>7} {row['mh']:>7}"
              f" {str(row['sw']) + 'x' + str(row['sh']):>12}  {marks}")
    bad = [r for r in rows
           if any(m in ("压", "裁", "溢") for m in r["marks"])]
    print(f"  —— 共 {len(rows)} 个控件，{len(bad)} 个有问题")
    return len(bad)


def main():
    argv = sys.argv[1:]
    show_screen = "--screen" in argv
    only_flagged = "--flag" in argv

    size = (1400, 890)
    if "--size" in argv:
        idx = argv.index("--size")
        if idx + 1 < len(argv) and "x" in argv[idx + 1]:
            w, h = argv[idx + 1].lower().split("x")
            size = (int(w), int(h))
            argv = argv[:idx] + argv[idx + 2:]

    args = [a for a in argv if not a.startswith("--")]
    target = args[0].lower() if args else None
    target_page = target.split(".", 1)[0] if target else None

    app = QApplication([])
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())

    window = MainWindow()
    window.resize(*size)
    window.show()
    for _ in range(4):
        app.processEvents()

    total_bad = 0
    pages = [("shell", "Shell Tools"), ("tools", "常用工具"),
             ("initcode", "Initcode Builder"), ("lk2kernel", "LK → Kernel"),
             ("kernel2lk", "Kernel → LK"), ("lk2bat", "LK → BAT")]

    for key, label in pages:
        if target_page and target_page != key:
            continue
        window.nav.select(key)
        for _ in range(3):
            app.processEvents()
        page = window.pages[key]

        if key == "tools":
            if target and "." in target:
                section_key = target.split(".", 1)[1]
                if section_key not in page.sections:
                    print(f"没有名为 {section_key} 的模块，可选："
                          f"{', '.join(page.sections)}")
                    return 2
                picked = [(section_key, page.sections[section_key])]
            else:
                picked = list(page.sections.items())
            for section_key, section in picked:
                page.show_section(section_key)
                for _ in range(3):
                    app.processEvents()
                total_bad += report(f"常用工具 / {section_key} = "
                                    f"{dict((k, l) for k, l, _i, _c in tools_page.SECTIONS).get(section_key, '')}",
                                    section, show_screen, only_flagged)
            if not target:
                total_bad += report("常用工具 / 整页", page, show_screen, only_flagged)
        else:
            total_bad += report(label, page, show_screen, only_flagged)

    if target is None:
        total_bad += report("主窗口", window, show_screen, only_flagged)

    print(f"\n窗口 {window.width()}x{window.height()}（含标记控件 {total_bad} 个）")

    window.pages["tools"].stop_background()
    for _ in range(3):
        app.processEvents()
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
