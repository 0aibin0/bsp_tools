"""常用工具页（第 6 个导航项）

三栏结构：左侧模块导航 + 中间模块内容 + **右侧执行结果面板**。

- 点任意模块里的按钮，命令输出都落在右侧面板，页面不跳转
- 右侧面板可拖拽调宽窄、可收起（QSplitter）
- 各模块通过 page.run_command() 执行命令，由本页共享 runner 统一处理

模块：日志分析 · 设备信息 · 显示调试 · 现场包 · 触摸调试 · 系统调试
      · 性能监控 · 文件管理 · 命令收藏
（异常守护与电池调试按 func-list 下线，见下方 SECTIONS 注释）
"""

from PyQt5.QtCore import Qt, QSize, QEvent
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QStackedWidget, QButtonGroup, QFrame, QScrollArea,
                             QSizePolicy, QSplitter)

import theme
import ui_widgets as W
from base_tool_page import BaseToolPage
from command_runner import CommandRunner
from tools_log import LogAnalyzerSection
from tools_device import DeviceInfoSection
from tools_favorites import FavoritesSection
from tools_files import FileManagerSection
from tools_display import DisplayDebugSection
from tools_perf import PerfSection
from tools_touch import TouchSection
from tools_system import SystemSection
from tools_sitepack import SitePackSection


# 按 func-list.md 的标记，异常守护（guard）与电池调试（battery）两个模块已下线：
# 前者 ESD 不做、其余规则与日志分析/现场包重叠；后者本阶段用不到。
# 代码文件仍留在仓库里（tools_guard.py / tools_battery.py），要恢复只需把
# 对应行加回 SECTIONS 与下面的 _inject_runner 名单。
SECTIONS = [
    ("log", "日志分析", "search", LogAnalyzerSection),
    ("device", "设备信息", "phone", DeviceInfoSection),
    ("display", "显示调试", "sun", DisplayDebugSection),
    ("sitepack", "现场包", "package", SitePackSection),
    ("touch", "触摸调试", "grid", TouchSection),
    ("system", "系统调试", "cpu", SystemSection),
    ("perf", "性能监控", "monitor", PerfSection),
    ("files", "文件管理", "folder", FileManagerSection),
    ("favorites", "命令收藏", "star", FavoritesSection),
]


class _SectionStack(QStackedWidget):
    """QStackedWidget 默认按「所有页面里最高的那个」报尺寸提示。

    本页 9 个模块高度差很大（最高 763，当前页往往只要 691），于是滚动区的
    内容区被最高的那个撑高，切到任何模块都会多出一条纵向滚动条。这里改成
    只按当前页面的最小尺寸提示计算，当前页放得下就不出滚动条；确实放不下
    （窗口被拖得很矮）时，minimumSizeHint 仍然是全页最大值，滚动条照常出现。
    """

    def sizeHint(self):
        cur = self.currentWidget()
        return cur.minimumSizeHint() if cur is not None else super().sizeHint()

    def minimumSizeHint(self):
        cur = self.currentWidget()
        return cur.minimumSizeHint() if cur is not None else super().minimumSizeHint()


class CommonToolsPage(BaseToolPage):
    """常用工具集合页。"""

    def __init__(self, parent=None):
        super(CommonToolsPage, self).__init__(parent)
        self.sections = {}
        self._buttons = {}

        # 全页共享的命令执行器：输出落在右侧面板，页面不跳转
        self.runner = CommandRunner(self, title="执行结果")
        self.runner.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        self._build_ui()
        self._inject_runner()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_nav())

        # 中间内容 / 右侧输出：可拖拽分隔，输出面板可拖窄甚至收起
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(True)
        self.splitter.setHandleWidth(8)
        self.splitter.addWidget(self._build_content())
        self.splitter.addWidget(self._build_output())

        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 0)
        # 输出面板 270px（内含文本框实测 240px），尺寸在 _apply_split_sizes() 里定
        self.splitter.setSizes([700, 270])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        layout.addWidget(self.splitter, 1)

    def _build_output(self):
        """右侧执行结果面板。

        runner 自带「执行结果」标题卡片，直接放进分隔条即可。
        最小宽度给 160：命令输出是文本，窄了可以横向滚动，
        没必要为了好看常驻占 240px（内容区更需要宽度）。
        """
        self.runner.setMinimumWidth(120)
        return self.runner

    def _build_nav(self):
        """左侧模块导航。"""
        self.nav_frame = QFrame(self)
        self.nav_frame.setObjectName("card")
        self.nav_frame.setFixedWidth(150)

        column = QVBoxLayout(self.nav_frame)
        column.setContentsMargins(8, 10, 8, 10)
        column.setSpacing(3)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label, icon_name, _cls in SECTIONS:
            btn = QPushButton(label, self.nav_frame)
            btn.setObjectName("subNav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIconSize(QSize(15, 15))
            btn.setMinimumHeight(32)
            btn.setIcon(theme.icon(icon_name, theme.TEXT_MUTED, 15, 1.6))
            btn.clicked.connect(lambda _checked=False, k=key: self.show_section(k))
            btn.toggled.connect(
                lambda checked, b=btn, i=icon_name: self._refresh_icon(b, i, checked))
            self._group.addButton(btn)
            self._buttons[key] = btn
            column.addWidget(btn)

        column.addStretch()
        return self.nav_frame

    def _build_content(self):
        """右侧内容区，套滚动区兜底。

        注意这里是 **widgetResizable(False) + 手动定尺**：QStackedWidget 的尺寸
        提示天然按「所有模块里最高的那个」算，交给 QScrollArea 自动伸缩时，切到
        任意模块都会多出一条纵向滚动条（哪怕当前模块只要 380px）。改成自己按
        「当前模块的最小需求」和「视口」取大值，放得下就不出滚动条，放不下才出。
        """
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        inner = QWidget()
        self.scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = _SectionStack(inner)
        for key, _label, _icon, section_class in SECTIONS:
            section = section_class(self)
            section.setObjectName(f"section_{key}")
            self.sections[key] = section
            self.stack.addWidget(section)
        layout.addWidget(self.stack)
        # 视口尺寸变化（窗口缩放）和内容需求变化（模块运行后长出结果行）都要重算；
        # 手动定尺意味着 QScrollArea 不会再自动帮我们追内容，这两个事件就是触发点
        self._fitting = False
        self.scroll.viewport().installEventFilter(self)
        inner.installEventFilter(self)
        self.stack.installEventFilter(self)
        return self.scroll

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.LayoutRequest):
            if obj in (self.scroll.viewport(), self.scroll.widget(), self.stack):
                self._fit_content()
        return super(CommonToolsPage, self).eventFilter(obj, event)

    def _fit_content(self):
        """内容区定尺：宽度/高度取「当前模块需求」与「视口可用」的较大者。

        用 maximumViewportSize()（不含滚动条的那份尺寸）而不是实际视口尺寸计算，
        避免「出滚动条→视口变小→再算一次」的来回抖动。
        """
        if self._fitting:
            return
        self._fitting = True
        try:
            inner = self.scroll.widget()
            if inner is None:
                return
            avail = self.scroll.maximumViewportSize()
            cur = self.stack.currentWidget()
            if cur is None:
                inner.resize(avail)
                return
            need = cur.minimumSizeHint()
            want = QSize(max(avail.width(), need.width()),
                         max(avail.height(), need.height()))
            if inner.size() != want:
                inner.resize(want)
        finally:
            self._fitting = False

    @staticmethod
    def _refresh_icon(button, icon_name, checked):
        color = "#ffffff" if checked else theme.TEXT_MUTED
        button.setIcon(theme.icon(icon_name, color, 15, 1.6))

    # ================= 依赖注入 =================

    def _inject_runner(self):
        """把共享执行器交给使用即时命令的模块。

        这些模块内部原本自带 CommandRunner（带自己的输出面板），
        换成共享实例后输出统一落在本页底部面板，模块里不用再放一份。
        性能监控有自己的采样定时器 + 独立 runner，不在此列。
        """
        for key in ("display", "favorites", "touch", "system"):
            section = self.sections.get(key)
            if section is None:
                continue
            old = getattr(section, "runner", None)
            if isinstance(old, CommandRunner) and old is not self.runner:
                old.setParent(None)
                old.deleteLater()
            section.runner = self.runner

    # ================= 对外 API =================

    def run_command(self, command, label=None, **kwargs):
        """供各模块调用：在本页底部面板执行并显示。"""
        return self.runner.run(command, label, **kwargs)

    def show_output(self):
        """确保底部输出面板可见（窗口矮时可能被压缩）。"""
        self.runner.panel.view.setMinimumHeight(120)

    # ================= 导航 =================

    # 这些模块自己有日志区/结果区，不需要右侧「执行结果」面板，
    # 选中它们时把面板收起来，模块就能用满宽度（日志分析尤其需要）。
    # 现场包也是——它自己有抓取明细，右侧再挂个空面板纯属浪费宽度。
    SECTIONS_WITHOUT_OUTPUT = ("log", "files", "favorites", "sitepack")

    def show_section(self, key):
        section = self.sections.get(key)
        if section is None:
            return
        self.stack.setCurrentWidget(section)
        # 切换模块后内容区高度需求变了，重算滚动区尺寸（见 _fit_content）
        self.stack.updateGeometry()
        self._fit_content()
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self._apply_output_visibility(key)
        hook = getattr(section, 'on_page_shown', None)
        if callable(hook):
            hook()

    def _apply_output_visibility(self, key):
        """按模块决定右侧执行结果面板是否需要。

        日志分析/文件管理/命令收藏 各自有日志或列表区，
        再挂一个空面板只是白占宽度，收起来让内容用满。
        用户手动拖过面板宽度的话就不再自动干预。

        注意用 isHidden() 而不是 isVisible()：页面在 QStackedWidget 里
        未显示时 isVisible() 恒为 False，会把面板误判成已收起。
        """
        if getattr(self, "_output_user_adjusted", False):
            return
        want = key not in self.SECTIONS_WITHOUT_OUTPUT
        if self.runner.isHidden() == want:
            self.runner.setHidden(not want)
            self._apply_split_sizes()

    def current_key(self):
        return next((k for k, b in self._buttons.items() if b.isChecked()), None)

    def _set_split_sizes(self, sizes):
        """程序化设置分栏（用标志位屏蔽 splitterMoved，避免误判为用户拖动）。"""
        self._programmatic_split = True
        try:
            self.splitter.setSizes(sizes)
        finally:
            self._programmatic_split = False

    def _on_splitter_moved(self, _pos, _index):
        """用户手动拖过分隔条后，就尊重用户的选择，不再自动收起面板。"""
        if not getattr(self, "_programmatic_split", False):
            self._output_user_adjusted = True

    def on_page_shown(self):
        key = self.current_key() or SECTIONS[0][0]
        self.show_section(key)
        self._apply_split_sizes()

    def _apply_split_sizes(self):
        """按实际可用宽度校正分栏：优先保证模块内容不被横向裁切。

        控件在构造阶段还没拿到真实尺寸，setSizes 会被布局重算覆盖，
        所以在页面真正显示后再算一次。
        """
        splitter = getattr(self, "splitter", None)
        if splitter is None or splitter.width() < 200:
            return
        # 布局还没算完时（构造期 / 刚 show 完还没 processEvents）splitter 只有
        # 一两百像素，这时候按公式算出来的宽度是错的，而且会一直留着。
        # 直接跳过，等下一次 show_section（用户点模块时）用真实宽度重算。
        if splitter.width() < 400:
            return
        total = splitter.width() - splitter.handleWidth()
        if self.runner.isHidden():
            # 面板收起时内容区直接用满
            self._set_split_sizes([total, 0])
            return
        content_need = 610          # 最宽模块（触摸屏 600）的最小宽度 + 余量
        # 输出面板给 270px：卡片左右各有 15px 内边距，所以里面文本框实测 240px
        # （用户按文本框宽度要求 240）。窗口不够宽时优先保内容区，
        # 面板退让但不少于 150px，避免内容被裁。
        output_width = 270
        content_width = total - output_width
        if content_width < content_need:
            output_width = max(total - content_need, 150)
            content_width = total - output_width
        self._set_split_sizes([content_width, output_width])

    def stop_background(self):
        """主窗口关闭前调用，停掉各模块正在跑的任务。

        各模块的 runner 各管各的（共享 runner 的 worker 只归它自己停），
        所以这里逐个调用是安全的。停不干净会导致退出时 QThread
        在运行中被销毁而崩溃，所以 stop / stop_background 都要试。
        """
        for section in self.sections.values():
            for name in ("stop_background", "stop"):
                hook = getattr(section, name, None)
                if callable(hook):
                    try:
                        hook()
                    except Exception:
                        pass
        self.runner.stop_all()
