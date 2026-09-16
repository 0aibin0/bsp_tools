"""DisplayTools 设计系统 —— 统一的配色、间距、字体与全局样式表。

所有页面共享这里的设计令牌 (design tokens)，避免样式散落在各个文件中。
修改配色只需改本文件顶部的常量。
"""

import os
import sys
import math

from PyQt5.QtGui import (QColor, QFont, QIcon, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)
from PyQt5.QtCore import Qt, QSize, QRectF, QPointF, QBuffer, QIODevice

# ===== 配色 =====
BG = "#f4f6fa"           # 窗口底色
SURFACE = "#ffffff"      # 卡片 / 输入框
SURFACE_ALT = "#f8fafc"  # 次级卡片底
BORDER = "#e3e8ef"       # 常规描边
BORDER_STRONG = "#cdd5e0"

TEXT = "#1b2436"         # 主文字
TEXT_MUTED = "#67748c"   # 次要文字
TEXT_FAINT = "#98a2b3"   # 提示文字

PRIMARY = "#2f6bff"
PRIMARY_HOVER = "#4a7dff"
PRIMARY_PRESSED = "#1f52d6"
PRIMARY_SOFT = "#eaf0ff"   # 选中态浅底
PRIMARY_SOFT_HOVER = "#dfe8ff"

SUCCESS = "#12a150"
SUCCESS_SOFT = "#e6f6ec"
WARNING = "#c47f17"
WARNING_SOFT = "#fdf3e2"
DANGER = "#e5484d"
DANGER_HOVER = "#f0575c"
DANGER_SOFT = "#fdecec"

SIDEBAR_BG = "#111a2e"
SIDEBAR_TEXT = "#9fb0cc"
SIDEBAR_TEXT_ACTIVE = "#ffffff"
SIDEBAR_HOVER = "#1c2942"
SIDEBAR_SECTION = "#5c6b87"  # 侧边栏分组小标题

# ===== 随主题变化的补充令牌 =====
# 这些是 build_stylesheet 里原本写死的颜色，抽出来才能整体换深色。
# 侧边栏/提示框本来就是深色，不参与切换。
TOOLTIP_BG = "#1b2436"
NAV_HOVER_TEXT = "#e8eefc"
BTN_HOVER_BG = "#f2f6ff"
BTN_PRESSED_BG = "#e6edff"
BTN_DISABLED_BG = "#f1f3f7"
PRIMARY_DISABLED = "#b9c8ee"
PRIMARY_DISABLED_TEXT = "#f2f5ff"
SLIDER_GROOVE = "#e4e9f2"
PROGRESS_BG = "#e9edf5"
LOG_BG = "#fbfcfe"
LOG_TEXT = "#223"
LOG_HIGHLIGHT = "#fff2b8"        # 关键字命中底色（浅色）
LOG_HIGHLIGHT_TEXT = "#4a3405"
SCROLL_HANDLE = "#c8d1e0"
SCROLL_HANDLE_HOVER = "#a9b6cc"

_MODE_TOKENS = (
    "BG", "SURFACE", "SURFACE_ALT", "BORDER", "BORDER_STRONG",
    "TEXT", "TEXT_MUTED", "TEXT_FAINT",
    "PRIMARY", "PRIMARY_HOVER", "PRIMARY_PRESSED",
    "PRIMARY_SOFT", "PRIMARY_SOFT_HOVER",
    "SUCCESS", "SUCCESS_SOFT", "WARNING", "WARNING_SOFT",
    "DANGER", "DANGER_HOVER", "DANGER_SOFT",
    "BTN_HOVER_BG", "BTN_PRESSED_BG", "BTN_DISABLED_BG",
    "PRIMARY_DISABLED", "PRIMARY_DISABLED_TEXT",
    "SLIDER_GROOVE", "PROGRESS_BG", "LOG_BG", "LOG_TEXT",
    "LOG_HIGHLIGHT", "LOG_HIGHLIGHT_TEXT",
    "SCROLL_HANDLE", "SCROLL_HANDLE_HOVER",
)

LIGHT_TOKENS = {
    "BG": "#f4f6fa", "SURFACE": "#ffffff", "SURFACE_ALT": "#f8fafc",
    "BORDER": "#e3e8ef", "BORDER_STRONG": "#cdd5e0",
    "TEXT": "#1b2436", "TEXT_MUTED": "#67748c", "TEXT_FAINT": "#98a2b3",
    "PRIMARY": "#2f6bff", "PRIMARY_HOVER": "#4a7dff", "PRIMARY_PRESSED": "#1f52d6",
    "PRIMARY_SOFT": "#eaf0ff", "PRIMARY_SOFT_HOVER": "#dfe8ff",
    "SUCCESS": "#12a150", "SUCCESS_SOFT": "#e6f6ec",
    "WARNING": "#c47f17", "WARNING_SOFT": "#fdf3e2",
    "DANGER": "#e5484d", "DANGER_HOVER": "#f0575c", "DANGER_SOFT": "#fdecec",
    "BTN_HOVER_BG": "#f2f6ff", "BTN_PRESSED_BG": "#e6edff",
    "BTN_DISABLED_BG": "#f1f3f7",
    "PRIMARY_DISABLED": "#b9c8ee", "PRIMARY_DISABLED_TEXT": "#f2f5ff",
    "SLIDER_GROOVE": "#e4e9f2", "PROGRESS_BG": "#e9edf5",
    "LOG_BG": "#fbfcfe", "LOG_TEXT": "#223",
    "LOG_HIGHLIGHT": "#fff2b8", "LOG_HIGHLIGHT_TEXT": "#4a3405",
    "SCROLL_HANDLE": "#c8d1e0", "SCROLL_HANDLE_HOVER": "#a9b6cc",
}

# 深色不是把浅色反相：卡片要比背景亮一档（浅色主题里是比背景白），
# 文字用略偏蓝的灰，主色提亮一点，否则在深底上会发闷。
DARK_TOKENS = {
    "BG": "#0d1220", "SURFACE": "#161d2e", "SURFACE_ALT": "#1b2336",
    "BORDER": "#26304a", "BORDER_STRONG": "#364260",
    "TEXT": "#e6ecf7", "TEXT_MUTED": "#9aa8c4", "TEXT_FAINT": "#6d7c9c",
    "PRIMARY": "#4d84ff", "PRIMARY_HOVER": "#6a99ff", "PRIMARY_PRESSED": "#3a6ce0",
    "PRIMARY_SOFT": "#1d2a4a", "PRIMARY_SOFT_HOVER": "#24345c",
    "SUCCESS": "#3ecf7f", "SUCCESS_SOFT": "#16301f",
    "WARNING": "#e0a63c", "WARNING_SOFT": "#33280f",
    "DANGER": "#ff6b6f", "DANGER_HOVER": "#ff8386", "DANGER_SOFT": "#3a1d20",
    "BTN_HOVER_BG": "#212c46", "BTN_PRESSED_BG": "#2a3757",
    "BTN_DISABLED_BG": "#1a2133",
    "PRIMARY_DISABLED": "#2c3a5e", "PRIMARY_DISABLED_TEXT": "#6b7796",
    "SLIDER_GROOVE": "#2a3348", "PROGRESS_BG": "#232c42",
    "LOG_BG": "#0a0f1a", "LOG_TEXT": "#c8d4e8",
    "LOG_HIGHLIGHT": "#5a4711", "LOG_HIGHLIGHT_TEXT": "#ffe9a3",
    "SCROLL_HANDLE": "#39445e", "SCROLL_HANDLE_HOVER": "#4a5878",
}

_active_mode = "light"


def _system_prefers_dark():
    """Windows 的「应用模式」是不是深色。读不到就按浅色处理。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return int(value) == 0
    except Exception:                                      # noqa: BLE001
        return False


def resolve_mode(mode):
    """把配置里的 system/light/dark 解析成实际生效的 light/dark。"""
    if mode == "dark":
        return "dark"
    if mode == "light":
        return "light"
    return "dark" if _system_prefers_dark() else "light"


def set_mode(mode):
    """切换主题令牌。

    必须在建窗口之前调用：图标是用 QPainter 按当时取到的颜色画成 QIcon 的，
    每个控件的内联样式也在构造时就把颜色烤进去了——换主题要重启程序，
    这不是偷懒，是这套实现下唯一不闪不崩的做法。
    """
    global _active_mode
    _active_mode = resolve_mode(mode)
    tokens = DARK_TOKENS if _active_mode == "dark" else LIGHT_TOKENS
    globals().update(tokens)
    return _active_mode


def current_mode():
    return _active_mode

# 版本信息
APP_NAME = "DisplayTools"
APP_VERSION = "v3.2.13"
APP_AUTHOR = "a1bin"

# ===== 尺寸 =====
RADIUS = 10
RADIUS_SM = 8
GAP = 10
PAD = 14
SIDEBAR_WIDTH = 208

# 中文优先字体族
FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'
MONO_FAMILY = '"Cascadia Mono", "Consolas", "JetBrains Mono", monospace'


def app_font():
    """全局默认字体"""
    font = QFont()
    font.setFamily("Microsoft YaHei UI")
    font.setStyleHint(QFont.SansSerif)
    font.setPointSize(9)
    return font


def mono_font(size=10):
    """等宽字体（日志、hex 等场景）"""
    font = QFont()
    font.setFamily("Consolas")
    font.setPointSize(size)
    font.setStyleHint(QFont.Monospace)
    return font


def _chevron_file(color, size=10):
    """生成下拉箭头 PNG 并返回样式表可用的 url(...) 片段。

    背景：Qt 样式表不支持用 CSS 三角写法写 ::down-arrow（会渲染成实心方块），
    也不解析内联 data URI；但一旦自定义了 ::drop-down，原生箭头就不再绘制。
    所以这里用 QPainter 画一个真箭头存到临时目录，再由样式表按文件引用。
    生成失败时返回 None，调用方会退回 Qt 原生箭头。
    """
    key = (color, size)
    if key in _CHEVRON_CACHE:
        return _CHEVRON_CACHE[key]

    result = None
    try:
        import hashlib
        import tempfile

        folder = os.path.join(tempfile.gettempdir(), "displaytools")
        os.makedirs(folder, exist_ok=True)
        stamp = hashlib.md5(f"{color}-{size}".encode()).hexdigest()[:8]
        path = os.path.join(folder, f"chevron_{stamp}.png")

        if not os.path.exists(path):
            pixmap = QPixmap(size * 3, size * 3)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(color))
            pen.setWidthF(size * 0.30)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            w = h = size * 3.0
            painter.drawPolyline(QPolygonF([
                QPointF(w * 0.20, h * 0.36),
                QPointF(w * 0.50, h * 0.66),
                QPointF(w * 0.80, h * 0.36),
            ]))
            painter.end()
            if not pixmap.save(path, "PNG"):
                path = None
        if path:
            result = "url(%s)" % path.replace("\\", "/")
    except Exception:
        result = None

    _CHEVRON_CACHE[key] = result
    return result


def build_stylesheet():
    """生成全局样式表。"""
    chevron = _chevron_file(TEXT_MUTED)
    chevron_rule = ""
    if chevron:
        chevron_rule = (
            "QComboBox::down-arrow {\n"
            f"    image: {chevron};\n"
            "    width: 10px;\n"
            "    height: 10px;\n"
            "    margin-right: 7px;\n"
            "}\n"
        )
    return f"""
/* ================= 基础 ================= */
QWidget {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QToolTip {{
    background: {TOOLTIP_BG};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
}}

/* ================= 侧边栏 ================= */
QWidget#sidebar {{
    background: {SIDEBAR_BG};
}}
QLabel#brandTitle {{
    color: #ffffff;
    font-size: 15px;
    font-weight: 600;
    background: transparent;
}}
QLabel#brandSub {{
    color: {SIDEBAR_TEXT};
    font-size: 11px;
    background: transparent;
}}
QLabel#navSection {{
    color: #5c6b87;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    padding: 0 6px;
}}
QPushButton#navButton {{
    background: transparent;
    color: {SIDEBAR_TEXT};
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#navButton:hover {{
    background: {SIDEBAR_HOVER};
    color: {NAV_HOVER_TEXT};
}}
QPushButton#navButton:checked {{
    background: {PRIMARY};
    color: {SIDEBAR_TEXT_ACTIVE};
    font-weight: 600;
}}
QPushButton#navButton:checked:hover {{
    background: {PRIMARY_HOVER};
}}
QPushButton#quickAction {{
    background: {SIDEBAR_HOVER};
    color: {SIDEBAR_TEXT};
    border: 1px solid #253352;
    border-radius: {RADIUS_SM}px;
    padding: 5px 10px;
    text-align: left;
    font-size: 12px;
}}
QPushButton#quickAction:hover {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    color: #ffffff;
}}
QPushButton#quickAction:pressed {{
    background: {PRIMARY_PRESSED};
}}
QFrame#sidebarSep {{
    background: #22304c;
    max-height: 1px;
    border: none;
}}
QLabel#sidebarFooter {{
    color: #4d5c78;
    font-size: 11px;
    background: transparent;
}}

/* ================= 顶部标题栏 ================= */
QWidget#headerBar {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QLabel#pageTitle {{
    font-size: 17px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#pageSubtitle {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}
QLabel[hint="true"] {{
    color: {TEXT_FAINT};
    font-size: 12px;
    background: transparent;
}}

/* ================= 卡片 / 分组 ================= */
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    margin-top: 10px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
    color: {TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_MUTED};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QFrame#statCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QLabel#statLabel {{
    color: {TEXT_FAINT};
    font-size: 11px;
    background: transparent;
}}
QLabel#statValue {{
    color: {TEXT};
    font-size: 16px;
    font-weight: 600;
    background: transparent;
}}
QLabel#statValue[tone="ok"] {{
    color: {SUCCESS};
}}
QLabel#statValue[tone="warn"] {{
    color: {WARNING};
}}
QLabel#statValue[tone="bad"] {{
    color: {DANGER};
}}
QLabel#statValue[tone="muted"] {{
    color: {TEXT_FAINT};
}}
QLabel#kvValue {{
    color: {TEXT};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}
QLabel#kvValue[tone="ok"] {{
    color: {SUCCESS};
}}
QLabel#kvValue[tone="warn"] {{
    color: {WARNING};
}}
QLabel#kvValue[tone="bad"] {{
    color: {DANGER};
}}
QLabel#kvValue[tone="muted"] {{
    color: {TEXT_FAINT};
}}
QFrame#hline {{
    background: {BORDER};
    max-height: 1px;
    border: none;
}}
QFrame#warnBar {{
    background: {WARNING_SOFT};
    border: 1px solid #f0dcb4;
    border-radius: {RADIUS_SM}px;
}}
QFrame#warnBar QLabel {{
    color: #8a5a10;
    font-size: 12px;
    background: transparent;
}}

/* ================= 按钮 ================= */
QPushButton {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 5px 12px;
    font-size: 13px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {BTN_HOVER_BG};
    border-color: {PRIMARY};
    color: {PRIMARY_PRESSED};
}}
QPushButton:pressed {{
    background: {BTN_PRESSED_BG};
}}
QPushButton:disabled {{
    background: {BTN_DISABLED_BG};
    color: {TEXT_FAINT};
    border-color: {BORDER};
}}
QPushButton:focus {{
    outline: none;
}}
QPushButton[accent="true"] {{
    background: {PRIMARY};
    color: #ffffff;
    border: 1px solid {PRIMARY};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{
    background: {PRIMARY_HOVER};
    border-color: {PRIMARY_HOVER};
    color: #ffffff;
}}
QPushButton[accent="true"]:pressed {{
    background: {PRIMARY_PRESSED};
    border-color: {PRIMARY_PRESSED};
}}
QPushButton[accent="true"]:disabled {{
    background: {PRIMARY_DISABLED};
    border-color: {PRIMARY_DISABLED};
    color: {PRIMARY_DISABLED_TEXT};
}}
QPushButton[danger="true"] {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #f6c6c7;
    font-weight: 600;
}}
QPushButton[danger="true"]:hover {{
    background: {DANGER};
    border-color: {DANGER};
    color: #ffffff;
}}
QPushButton[ghost="true"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {TEXT_MUTED};
}}
QPushButton[ghost="true"]:hover {{
    background: {PRIMARY_SOFT};
    border-color: transparent;
    color: {PRIMARY_PRESSED};
}}
QPushButton[segment="true"] {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 6px 16px;
    color: {TEXT_MUTED};
    font-weight: 500;
}}
QPushButton[segment="true"]:hover {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_PRESSED};
}}
QPushButton[segment="true"]:checked {{
    background: {PRIMARY};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#subNav {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 7px 10px;
    text-align: left;
    color: {TEXT_MUTED};
    font-size: 13px;
}}
QPushButton#subNav:hover {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_PRESSED};
}}
QPushButton#subNav:checked {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_PRESSED};
    font-weight: 600;
}}
QPushButton[compact="true"] {{
    padding: 3px 9px;
    min-height: 16px;
    font-size: 12px;
}}

/* ================= 输入控件 ================= */
QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 4px 8px;
    selection-background-color: {PRIMARY};
    selection-color: #ffffff;
}}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QTextBrowser:hover,
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: #b6c2d6;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {PRIMARY};
}}
QLineEdit:read-only {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
}}
QLineEdit[state="ok"] {{
    border: 1px solid {SUCCESS};
}}
QLineEdit[state="error"] {{
    border: 1px solid {DANGER};
}}

/* 说明框正文（帮助 / 更新日志 / 崩溃日志）：像一页文档，不要输入框那种边框感 */
QPlainTextEdit#infoView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 10px 12px;
    color: {TEXT};
}}

/* 数字输入框不要上下调节小箭头：时序计算里有十来个这样的框，箭头一排排
   立在那儿既占宽度又显得碎。数字照样能手输、滚轮调、上下键调。 */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
/* 箭头去掉后文字区变宽，左右对称的内边距更好看 */
QSpinBox, QDoubleSpinBox {{
    padding: 4px 6px;
}}

QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 4px 8px;
    min-height: 18px;
}}
QComboBox:hover {{
    border-color: #b6c2d6;
}}
QComboBox:focus {{
    border-color: {PRIMARY};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: 22px;
    background: transparent;
}}
{chevron_rule}QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 4px;
    outline: none;
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {PRIMARY_PRESSED};
}}

QCheckBox, QRadioButton {{
    spacing: 7px;
    color: {TEXT};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER_STRONG};
    background: {SURFACE};
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {PRIMARY};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    image: none;
}}
QRadioButton::indicator:checked {{
    background: {PRIMARY};
    border: 4px solid {SURFACE};
    outline: 1px solid {PRIMARY};
}}

/* ================= 滑块 / 进度 ================= */
QSlider::groove:horizontal {{
    height: 5px;
    background: {SLIDER_GROOVE};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {PRIMARY};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {SURFACE};
    border: 2px solid {PRIMARY};
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {PRIMARY_SOFT};
}}
QProgressBar {{
    background: {PROGRESS_BG};
    border: none;
    border-radius: 5px;
    height: 9px;
    text-align: center;
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: 5px;
}}

/* ================= 列表 / 表格 / 树 ================= */
QListWidget, QTreeWidget, QTableWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 3px;
    outline: none;
    alternate-background-color: {SURFACE_ALT};
}}
QListWidget::item, QTreeWidget::item {{
    padding: 6px 8px;
    border-radius: 6px;
    color: {TEXT};
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background: {PRIMARY_SOFT};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_PRESSED};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: 600;
}}
QTableWidget::item {{
    padding: 4px 6px;
}}

/* ================= 日志视图 ================= */
QTextBrowser#logView, QPlainTextEdit#logView {{
    background: {LOG_BG};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 8px;
    font-family: {MONO_FAMILY};
    font-size: 12px;
    color: {LOG_TEXT};
}}

/* ================= 滚动条 ================= */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {SCROLL_HANDLE};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {SCROLL_HANDLE_HOVER};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {SCROLL_HANDLE};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {SCROLL_HANDLE_HOVER};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ================= 状态栏 ================= */
QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QStatusBar::item {{
    border: none;
}}
QLabel#statusChip {{
    color: {TEXT_MUTED};
    font-size: 12px;
    padding: 0 4px;
}}
QLabel#statusChip[tone="ok"] {{
    color: {SUCCESS};
}}
QLabel#statusChip[tone="muted"] {{
    color: {TEXT_FAINT};
}}

/* ================= 其他 ================= */
QSplitter::handle {{
    background: transparent;
    width: 8px;
    height: 8px;
}}
QSplitter::handle:hover {{
    background: {PRIMARY_SOFT};
}}
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 22px 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_PRESSED};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
"""


# ================= 矢量图标 =================
# 用 QPainter 现画线性图标，避免额外资源文件，且能跟随主题色。

_ICON_CACHE = {}
_CHEVRON_CACHE = {}


def _painter_icon(draw, color, size=18, stroke=1.7):
    """构造一个由 draw(painter, rect) 绘制的图标。"""
    key = (id(draw), color, size, stroke)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    pixmap = QPixmap(size * 2, size * 2)  # 2x 抗锯齿
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(2.0, 2.0)
    pen = QPen(QColor(color))
    pen.setWidthF(stroke)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    draw(painter, QRectF(0.5, 0.5, size - 1.0, size - 1.0))
    painter.end()

    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def _polyline(painter, points):
    painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))


def _draw_terminal(p, r):
    p.drawRoundedRect(r.adjusted(0.5, 1.5, -0.5, -1.5), 2.5, 2.5)
    x, y = r.left() + 3.6, r.top() + 6.4
    _polyline(p, [(x, y), (x + 2.8, y + 2.6), (x, y + 5.2)])
    p.drawLine(int(x + 6.4), int(y + 5.2), int(x + 10.4), int(y + 5.2))


def _draw_code(p, r):
    _polyline(p, [(r.left() + 5.4, r.top() + 3.4), (r.left() + 1.8, r.center().y()),
                  (r.left() + 5.4, r.bottom() - 3.4)])
    _polyline(p, [(r.right() - 5.4, r.top() + 3.4), (r.right() - 1.8, r.center().y()),
                  (r.right() - 5.4, r.bottom() - 3.4)])


def _draw_arrow_right(p, r):
    cy = r.center().y()
    p.drawLine(int(r.left() + 2.5), int(cy), int(r.right() - 2.6), int(cy))
    x = r.right() - 2.6
    p.drawLine(int(x), int(cy), int(x - 4.2), int(cy - 4.2))
    p.drawLine(int(x), int(cy), int(x - 4.2), int(cy + 4.2))


def _draw_arrow_left(p, r):
    cy = r.center().y()
    p.drawLine(int(r.left() + 2.6), int(cy), int(r.right() - 2.5), int(cy))
    x = r.left() + 2.6
    p.drawLine(int(x), int(cy), int(x + 4.2), int(cy - 4.2))
    p.drawLine(int(x), int(cy), int(x + 4.2), int(cy + 4.2))


def _draw_file(p, r):
    path = QPainterPath()
    l, t, rt, b = r.left() + 3.2, r.top() + 1.6, r.right() - 3.2, r.bottom() - 1.6
    fold = (rt - l) * 0.42
    path.moveTo(l, t)
    path.lineTo(rt - fold, t)
    path.lineTo(rt, t + fold)
    path.lineTo(rt, b)
    path.lineTo(l, b)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(int(rt - fold), int(t), int(rt - fold), int(t + fold))
    p.drawLine(int(rt - fold), int(t + fold), int(rt), int(t + fold))


def _draw_bat(p, r):
    path = QPainterPath()
    l, t, rt, b = r.left() + 2.2, r.top() + 2.4, r.right() - 2.2, r.bottom() - 2.4
    path.moveTo(l, t)
    path.lineTo(rt - 3.4, t)
    path.lineTo(rt - 3.4, b)
    path.lineTo(l, b)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(int(l + 3), int(t + 5), int(l + 8), int(t + 5))
    p.drawLine(int(l + 3), int(t + 9), int(l + 8), int(t + 9))


def _draw_grid(p, r):
    a = r.adjusted(2.2, 2.2, -2.2, -2.2)
    for i in range(2):
        for j in range(2):
            cell = QRectF(a.left() + i * (a.width() / 2 + 1.2),
                          a.top() + j * (a.height() / 2 + 1.2),
                          a.width() / 2 - 1.2, a.height() / 2 - 1.2)
            p.drawRoundedRect(cell, 1.8, 1.8)


def _draw_search(p, r):
    radius = r.width() * 0.30
    center = QPointF(r.center().x() - 2.0, r.center().y() - 2.0)
    p.drawEllipse(center, radius, radius)
    p.drawLine(int(center.x() + radius * 0.72), int(center.y() + radius * 0.72),
               int(r.right() - 1.6), int(r.bottom() - 1.6))


def _draw_activity(p, r):
    pts = [(3.0, 11.0), (6.4, 11.0), (8.4, 5.4), (10.6, 14.6), (12.6, 9.2), (14.6, 9.2)]
    _polyline(p, [(r.left() + x * (r.width() / 19.0), r.top() + y * (r.height() / 19.0))
                  for x, y in pts])


def _draw_monitor(p, r):
    p.drawRoundedRect(QRectF(r.left() + 1.8, r.top() + 2.6, r.width() - 3.6, r.height() * 0.62), 2.2, 2.2)
    p.drawLine(int(r.center().x()), int(r.top() + 2.6 + r.height() * 0.62),
               int(r.center().x()), int(r.bottom() - 2.6))
    p.drawLine(int(r.left() + 4.6), int(r.bottom() - 2.6), int(r.right() - 4.6), int(r.bottom() - 2.6))


def _draw_help(p, r):
    p.drawEllipse(r.adjusted(1.8, 1.8, -1.8, -1.8))
    p.drawLine(int(r.center().x()), int(r.top() + 5.2), int(r.center().x()), int(r.center().y() + 1.2))
    p.drawPoint(int(r.center().x()), int(r.bottom() - 4.6))


def _draw_info(p, r):
    p.drawEllipse(r.adjusted(1.8, 1.8, -1.8, -1.8))
    p.drawLine(int(r.center().x()), int(r.bottom() - 5.0), int(r.center().x()), int(r.center().y() - 0.4))
    p.drawPoint(int(r.center().x()), int(r.top() + 5.0))


def _draw_history(p, r):
    p.drawEllipse(r.adjusted(2.4, 2.4, -2.4, -2.4))
    p.drawLine(int(r.center().x()), int(r.center().y()), int(r.center().x()), int(r.top() + 5.0))
    p.drawLine(int(r.center().x()), int(r.center().y()), int(r.right() - 5.4), int(r.center().y()))


def _draw_refresh(p, r):
    p.drawArc(r.adjusted(2.4, 2.4, -2.4, -2.4), 60 * 16, 260 * 16)
    x, y = r.right() - 3.0, r.top() + 3.0
    p.drawLine(int(x), int(y), int(x - 4.0), int(y + 0.4))
    p.drawLine(int(x), int(y), int(x - 0.4), int(y + 4.0))


def _draw_folder(p, r):
    path = QPainterPath()
    l, t, rt, b = r.left() + 1.8, r.top() + 3.6, r.right() - 1.8, r.bottom() - 2.4
    path.moveTo(l, b)
    path.lineTo(l, t + 1.4)
    path.lineTo(l + 4.6, t + 1.4)
    path.lineTo(l + 6.2, t + 3.0)
    path.lineTo(rt, t + 3.0)
    path.lineTo(rt, b)
    path.closeSubpath()
    p.drawPath(path)


def _draw_cpu(p, r):
    p.drawRoundedRect(r.adjusted(4.0, 4.0, -4.0, -4.0), 2.0, 2.0)
    for i in range(3):
        off = 5.4 + i * 2.8
        p.drawLine(int(r.left() + off), int(r.top() + 1.2), int(r.left() + off), int(r.top() + 4.0))
        p.drawLine(int(r.left() + off), int(r.bottom() - 4.0), int(r.left() + off), int(r.bottom() - 1.2))
        p.drawLine(int(r.top() * 0 + r.left() + 1.2), int(r.top() + off), int(r.left() + 4.0), int(r.top() + off))
        p.drawLine(int(r.right() - 4.0), int(r.top() + off), int(r.right() - 1.2), int(r.top() + off))


def _draw_phone(p, r):
    p.drawRoundedRect(r.adjusted(4.6, 1.8, -4.6, -1.8), 2.4, 2.4)
    p.drawLine(int(r.center().x() - 1.6), int(r.bottom() - 3.6), int(r.center().x() + 1.6), int(r.bottom() - 3.6))


def _draw_sun(p, r):
    p.drawEllipse(r.center(), r.width() * 0.20, r.height() * 0.20)
    for i in range(8):
        ang = math.radians(i * 45)
        x1 = r.center().x() + math.cos(ang) * r.width() * 0.30
        y1 = r.center().y() + math.sin(ang) * r.height() * 0.30
        x2 = r.center().x() + math.cos(ang) * r.width() * 0.42
        y2 = r.center().y() + math.sin(ang) * r.height() * 0.42
        p.drawLine(int(x1), int(y1), int(x2), int(y2))


def _draw_star(p, r):
    cx, cy = r.center().x(), r.center().y()
    outer, inner = r.width() * 0.42, r.width() * 0.18
    pts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        rad = outer if i % 2 == 0 else inner
        pts.append(QPointF(cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    p.drawPolygon(QPolygonF(pts))


def _draw_trash(p, r):
    p.drawLine(int(r.left() + 3.4), int(r.top() + 4.4), int(r.right() - 3.4), int(r.top() + 4.4))
    p.drawLine(int(r.center().x() - 2.0), int(r.top() + 2.6), int(r.center().x() + 2.0), int(r.top() + 2.6))
    _polyline(p, [(r.left() + 4.4, r.top() + 4.4), (r.left() + 5.2, r.bottom() - 2.4),
                  (r.right() - 5.2, r.bottom() - 2.4), (r.right() - 4.4, r.top() + 4.4)])


def _draw_download(p, r):
    p.drawLine(int(r.center().x()), int(r.top() + 2.6), int(r.center().x()), int(r.bottom() - 5.6))
    x, y = r.center().x(), r.bottom() - 5.6
    p.drawLine(int(x), int(y), int(x - 4.0), int(y - 4.0))
    p.drawLine(int(x), int(y), int(x + 4.0), int(y - 4.0))
    p.drawLine(int(r.left() + 3.0), int(r.bottom() - 2.0), int(r.right() - 3.0), int(r.bottom() - 2.0))


def _draw_upload(p, r):
    p.drawLine(int(r.center().x()), int(r.bottom() - 2.6), int(r.center().x()), int(r.top() + 5.6))
    x, y = r.center().x(), r.top() + 5.6
    p.drawLine(int(x), int(y), int(x - 4.0), int(y + 4.0))
    p.drawLine(int(x), int(y), int(x + 4.0), int(y + 4.0))
    p.drawLine(int(r.left() + 3.0), int(r.bottom() - 2.0), int(r.right() - 3.0), int(r.bottom() - 2.0))


def _draw_settings(p, r):
    """齿轮：外圈八段短齿 + 中间圆孔。"""
    cx, cy = r.center().x(), r.center().y()
    outer, inner = r.width() * 0.42, r.width() * 0.30
    import math as _math
    for index in range(8):
        angle = index * _math.pi / 4
        dx, dy = _math.cos(angle), _math.sin(angle)
        p.drawLine(int(cx + dx * inner), int(cy + dy * inner),
                   int(cx + dx * outer), int(cy + dy * outer))
    p.drawEllipse(r.center(), inner * 0.86, inner * 0.86)
    p.drawEllipse(r.center(), inner * 0.36, inner * 0.36)


def _draw_shield(p, r):
    """盾牌：给「监控/守护」类入口备用。"""
    cx = r.center().x()
    top = r.top() + 2.0
    bottom = r.bottom() - 1.6
    half = r.width() * 0.34
    p.drawLine(int(cx - half), int(top + 1.5), int(cx + half), int(top + 1.5))
    p.drawLine(int(cx - half), int(top + 1.5), int(cx - half), int(r.center().y()))
    p.drawLine(int(cx + half), int(top + 1.5), int(cx + half), int(r.center().y()))
    p.drawLine(int(cx - half), int(r.center().y()), int(cx), int(bottom))
    p.drawLine(int(cx + half), int(r.center().y()), int(cx), int(bottom))


def _draw_tool(p, r):
    """扳手：现场包 / 工具。"""
    p.drawLine(int(r.left() + 4.0), int(r.bottom() - 3.0),
               int(r.center().x() + 1.0), int(r.center().y()))
    p.drawEllipse(r.left() + 2.6, r.top() + 2.6, 7.0, 7.0)


def _draw_package(p, r):
    """包裹箱：打包导出。"""
    p.drawRect(int(r.left() + 2.4), int(r.top() + 4.2),
               int(r.width() - 4.8), int(r.height() - 6.6))
    p.drawLine(int(r.center().x()), int(r.top() + 4.2),
               int(r.center().x()), int(r.bottom() - 2.4))
    p.drawLine(int(r.left() + 2.4), int(r.center().y() - 1.0),
               int(r.right() - 2.4), int(r.center().y() - 1.0))


def _draw_clock(p, r):
    p.drawEllipse(r.center(), r.width() * 0.36, r.height() * 0.36)
    p.drawLine(int(r.center().x()), int(r.center().y()),
               int(r.center().x()), int(r.top() + 3.4))
    p.drawLine(int(r.center().x()), int(r.center().y()),
               int(r.right() - 3.4), int(r.center().y()))


def _draw_calc(p, r):
    """计算器：Panel 参数计算。"""
    p.drawRect(int(r.left() + 2.6), int(r.top() + 1.6),
               int(r.width() - 5.2), int(r.height() - 3.2))
    p.drawLine(int(r.left() + 5.0), int(r.top() + 5.4),
               int(r.right() - 5.0), int(r.top() + 5.4))
    for row in range(2):
        y = r.top() + 9.0 + row * 4.0
        for col in range(3):
            x = r.left() + 5.4 + col * 3.6
            p.drawPoint(int(x), int(y))


ICONS = {
    "terminal": _draw_terminal,
    "code": _draw_code,
    "arrow_right": _draw_arrow_right,
    "arrow_left": _draw_arrow_left,
    "file": _draw_file,
    "bat": _draw_bat,
    "grid": _draw_grid,
    "search": _draw_search,
    "activity": _draw_activity,
    "monitor": _draw_monitor,
    "help": _draw_help,
    "info": _draw_info,
    "history": _draw_history,
    "refresh": _draw_refresh,
    "folder": _draw_folder,
    "cpu": _draw_cpu,
    "phone": _draw_phone,
    "sun": _draw_sun,
    "star": _draw_star,
    "trash": _draw_trash,
    "download": _draw_download,
    "upload": _draw_upload,
    "settings": _draw_settings,
    "shield": _draw_shield,
    "tool": _draw_tool,
    "package": _draw_package,
    "clock": _draw_clock,
    "calc": _draw_calc,
}


def icon(name, color=TEXT_MUTED, size=18, stroke=1.7):
    """按名字取一个线性图标。"""
    draw = ICONS.get(name)
    if draw is None:
        return QIcon()
    return _painter_icon(draw, color, size, stroke)


def icon_size(size=18):
    return QSize(size, size)
