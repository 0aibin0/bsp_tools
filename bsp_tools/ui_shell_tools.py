# -*- coding: utf-8 -*-
"""Shell Tools 页面界面。

v3.1.1 重排：原布局每个分组框都是单列竖排，垂直方向最小需求 989px，
而普通窗口的内容区只有约 774px，导致分组框被压缩后内部控件互相重叠
（adb 的 9 个按钮 y 间距只剩 15px，文字糊成一团）。

现在改成紧凑网格：
- adb 按钮 3 列排布
- Debug 的 push/pull、density/I2C 合并成行
- fastboot / func 用 2 列网格
- 各分组统一收紧内边距与间距

控件名与 v3.1.0 完全一致，shell_tools.py 无需改动。
"""

from PyQt5 import QtCore, QtWidgets

import theme


class Ui_ShellTools(object):
    # ---------- 构造辅助 ----------

    @staticmethod
    def _accent(button):
        """标记主操作按钮，由全局样式表渲染为品牌色。"""
        button.setProperty("accent", True)
        return button

    @staticmethod
    def _ghost(button):
        """标记次要按钮，渲染为无边框幽灵按钮。"""
        button.setProperty("ghost", True)
        return button

    @staticmethod
    def _button(parent, name, text, height=28, min_width=0):
        btn = QtWidgets.QPushButton(text, parent)
        btn.setObjectName(name)
        btn.setMinimumHeight(height)
        if min_width:
            btn.setMinimumWidth(min_width)
        return btn

    @staticmethod
    def _group(parent, name, title, margins=(9, 13, 9, 6), spacing=4):
        box = QtWidgets.QGroupBox(parent)
        box.setObjectName(name)
        box.setTitle(title)
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        return box, layout

    # ---------- 主界面 ----------

    def setupUi(self, MainWindow):
        """左侧控制区（2 列网格）+ 右侧竖向 Log 面板。

        为什么是 2 列：加进右侧 Log 后，控制区只剩约 820px，
        原来 3 列网格的最小宽度是 1146px，放不下会把第三列挤没。
        改成 2 列后最小宽度降到 ~1030px，配合日志面板默认 300px 可以放得下。
        """
        self.mainLayout = QtWidgets.QVBoxLayout(MainWindow)
        self.mainLayout.setContentsMargins(12, 10, 12, 10)
        self.mainLayout.setSpacing(7)
        self.mainLayout.setObjectName("mainLayout")

        self.split = QtWidgets.QSplitter(QtCore.Qt.Horizontal, MainWindow)
        self.split.setObjectName("shellSplit")
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(8)

        # ================= 左：控制区 =================
        self.controlPanel = QtWidgets.QWidget()
        controls = QtWidgets.QVBoxLayout(self.controlPanel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        # 2 列网格，按「卡片高度配对」摆放。
        # adb 卡已下线（查询搬到显示调试/设备信息，命令搬到侧边栏快捷操作），
        # 剩下 6 张卡的自然高度（约）：GPIO 87 / Debug 155 / ylog 164 /
        # Download Mode 87 / fastboot flash 121 / func 87 / APK 128。
        self.topGrid = QtWidgets.QGridLayout()
        self.topGrid.setSpacing(8)
        self.topGrid.setObjectName("topGrid")

        self._build_debug_group(self.controlPanel)
        self._build_download_group(self.controlPanel)
        self._build_gpio_group(self.controlPanel)
        self._build_ylog(self.controlPanel)
        self._build_flash_group(self.controlPanel)

        # 配对原则：同一行的两张卡自然高度尽量接近，谁也别空一大截
        #   GPIO + Download Mode （87/87，都是"查一下设备"）
        #   Debug + ylog         （155/164，差 9px）
        #   fastboot flash + ???  → flash 与"整宽卡片"不同列，放在下一行整宽
        self.topGrid.addWidget(self.groupBox_gpio, 0, 0)     # GPIO
        self.topGrid.addWidget(self.groupBox_dl, 0, 1)       # Download Mode
        self.topGrid.addWidget(self.groupBox_debug, 1, 0)    # Debug
        self.topGrid.addWidget(self.groupBox_3, 1, 1)        # ylog
        self.topGrid.addWidget(self.groupBox_flash, 2, 0, 1, 2)   # fastboot flash 整宽

        self.topGrid.setColumnStretch(0, 10)
        self.topGrid.setColumnStretch(1, 11)
        self.topGrid.setRowStretch(3, 1)                     # 余量留在底部
        controls.addLayout(self.topGrid)

        # 整宽：func / APK & Tools
        self._build_func_group(self.controlPanel)
        controls.addWidget(self.groupBox_6)
        self._build_tools(self.controlPanel)
        controls.addStretch(1)
        self._build_controls_scroll(controls)

        self.split.addWidget(self.controlScroll)

        # ================= 右：Log =================
        self._build_log(self.split)

        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        # 兜底分栏：日志面板 286px（文本框 240px）。
        #
        # 这两个值只是"布局还没算完时先摆个样子"——真正的宽度由
        # shell_tools._apply_split_sizes() 在页面显示后按实际宽度重算。
        # 但那个函数如果因为布局没算完而跳过，这里就是用户最终看到的值，
        # 所以兜底值必须和约定一致：之前写的是 360（文本框 314px），
        # 一旦 _apply_split_sizes 没跑成，用户量到的就不是 240 了。
        self.split.setSizes([800, 286])
        self.mainLayout.addWidget(self.split)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def _build_controls_scroll(self, controls):
        """控制区套滚动区：窗口偏小时滚动查看，不压扁控件。"""
        self.controlScroll = QtWidgets.QScrollArea()
        self.controlScroll.setObjectName("controlScroll")
        self.controlScroll.setWidgetResizable(True)
        self.controlScroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.controlScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.controlScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.controlScroll.setMinimumWidth(400)
        self.controlScroll.setWidget(self.controlPanel)

    # ---------- 各分组构建（只负责建控件，放置由 setupUi 决定）----------

    def _build_adb_group(self, parent):
        """**已下线**：原来放 wm size / dumpsys / device info。

        三个查询都搬走了：
        - wm size、dumpsys display → 常用工具页「显示调试」（分辨率 / 密度 /
          刷新率 卡片 + Panel / 显示信息 卡片）
        - device info → 常用工具页「设备信息」模块
        - remount / cmdline / devices / root / debugfs / reboot → 侧边栏快捷操作

        保留这个方法是为了不留死引用（setupUi 不再调用它）。
        """
        return None

    def _build_download_group(self, parent):
        self.groupBox_dl, dl_layout = self._group(parent, "groupBox_dl", "Download Mode")
        dl_row = QtWidgets.QHBoxLayout()
        dl_row.setSpacing(5)
        self.dl_autodloader = self._button(
            self.groupBox_dl, "dl_autodloader", "UNISOC autodloader", height=26)
        # 两个按钮平分整行：只按 sizeHint 排会在右边空一截
        dl_row.addWidget(self.dl_autodloader, 1)
        self.dl_edl = self._button(self.groupBox_dl, "dl_edl", "QCOM EDL", height=26)
        dl_row.addWidget(self.dl_edl, 1)
        dl_layout.addLayout(dl_row)

    def _build_gpio_group(self, parent):
        """GPIO 查询：输入框撑满剩余宽度，不用在右边留一截空白。"""
        self.groupBox_gpio, gpio_layout = self._group(
            parent, "groupBox_gpio", "GPIO")
        gpio_row = QtWidgets.QHBoxLayout()
        gpio_row.setSpacing(5)
        gpio_row.addWidget(QtWidgets.QLabel("GPIO:", self.groupBox_gpio))
        self.gpio_num = QtWidgets.QLineEdit(self.groupBox_gpio)
        self.gpio_num.setMinimumHeight(26)
        self.gpio_num.setMinimumWidth(80)
        self.gpio_num.setPlaceholderText("编号，留空查全部")
        self.gpio_num.setToolTip("留空则列出全部 GPIO")
        self.gpio_num.setObjectName("gpio_num")
        gpio_row.addWidget(self.gpio_num, 1)
        self.gpio_check = self._button(
            self.groupBox_gpio, "gpio_check", "查询", height=26)
        # 固定宽度：拉伸占满整行会看着像误标的按钮
        self.gpio_check.setFixedWidth(88)
        gpio_row.addWidget(self.gpio_check)
        gpio_layout.addLayout(gpio_row)

    def _build_debug_group(self, parent):
        self.groupBox_debug, debug_layout = self._group(
            parent, "groupBox_debug", "Debug")

        # 第 1 行：自定义命令 + Run/Stop
        shell_row = QtWidgets.QHBoxLayout()
        shell_row.setSpacing(5)
        self.debug_shell_cmd = QtWidgets.QComboBox(self.groupBox_debug)
        self.debug_shell_cmd.setEditable(True)
        self.debug_shell_cmd.setMinimumHeight(28)
        self.debug_shell_cmd.setMinimumWidth(250)
        self.debug_shell_cmd.lineEdit().setPlaceholderText("adb shell 命令…")
        self.debug_shell_cmd.setObjectName("debug_shell_cmd")
        shell_row.addWidget(self.debug_shell_cmd, 1)
        self.debug_shell_run = self._button(
            self.groupBox_debug, "debug_shell_run", "Run", height=28)
        self._accent(self.debug_shell_run)
        shell_row.addWidget(self.debug_shell_run)
        self.debug_shell_stop = self._button(
            self.groupBox_debug, "debug_shell_stop", "Stop", height=28)
        shell_row.addWidget(self.debug_shell_stop)
        debug_layout.addLayout(shell_row)

        # 第 2 行：density（push/pull/I2C 已下线——文件传输走常用工具页的
        # 「文件管理」，那边是浏览+上传+下载+删除的超集；I2C/SPI 是板级一次性
        # 确认，需要时用上面的自定义命令跑）
        # 三个控件等宽撑满整行：控件挤在左边、右边空一大截会显得没排完
        tools_row = QtWidgets.QHBoxLayout()
        tools_row.setSpacing(5)
        self.debug_density_get = self._button(
            self.groupBox_debug, "debug_density_get", "density", height=26)
        self.debug_density_get.setToolTip("读取当前屏幕密度")
        tools_row.addWidget(self.debug_density_get, 1)
        self.debug_density_val = QtWidgets.QLineEdit(self.groupBox_debug)
        self.debug_density_val.setMinimumHeight(26)
        self.debug_density_val.setPlaceholderText("dpi")
        self.debug_density_val.setObjectName("debug_density_val")
        tools_row.addWidget(self.debug_density_val, 1)
        self.debug_density_set = self._button(
            self.groupBox_debug, "debug_density_set", "Set", height=26)
        self.debug_density_set.setToolTip("把上面的 dpi 写入设备")
        tools_row.addWidget(self.debug_density_set, 1)
        debug_layout.addLayout(tools_row)

        # 第 3 行：printk
        printk_row = QtWidgets.QHBoxLayout()
        printk_row.setSpacing(5)
        printk_row.addWidget(QtWidgets.QLabel("printk:", self.groupBox_debug))
        self.debug_printk_level = QtWidgets.QComboBox(self.groupBox_debug)
        self.debug_printk_level.setEditable(True)
        self.debug_printk_level.setMinimumHeight(26)
        self.debug_printk_level.setObjectName("debug_printk_level")
        printk_row.addWidget(self.debug_printk_level, 1)
        self.debug_printk_get = self._button(
            self.groupBox_debug, "debug_printk_get", "Get", height=26)
        printk_row.addWidget(self.debug_printk_get)
        self.debug_printk_set = self._button(
            self.groupBox_debug, "debug_printk_set", "Set", height=26)
        printk_row.addWidget(self.debug_printk_set)
        debug_layout.addLayout(printk_row)

    def _build_flash_group(self, parent):
        self.groupBox_flash, flash_layout = self._group(
            parent, "groupBox_flash", "fastboot flash")

        # 第 1 行：分区 + 镜像路径 + 浏览
        path_row = QtWidgets.QHBoxLayout()
        path_row.setSpacing(5)
        self.flash_partition = QtWidgets.QComboBox(self.groupBox_flash)
        self.flash_partition.setEditable(True)
        self.flash_partition.setMinimumHeight(26)
        self.flash_partition.setMinimumWidth(118)
        self.flash_partition.setObjectName("flash_partition")
        # 可编辑下拉框留空时看着像坏掉，给个占位提示（Qt 5.15 才有该接口）
        if hasattr(self.flash_partition, "setPlaceholderText"):
            self.flash_partition.setPlaceholderText("分区")
        path_row.addWidget(self.flash_partition)
        self.flash_img_path = QtWidgets.QLineEdit(self.groupBox_flash)
        self.flash_img_path.setMinimumHeight(26)
        self.flash_img_path.setMinimumWidth(40)
        self.flash_img_path.setPlaceholderText("镜像文件…")
        self.flash_img_path.setReadOnly(True)
        self.flash_img_path.setObjectName("flash_img_path")
        path_row.addWidget(self.flash_img_path, 1)
        self.flash_browse = self._button(
            self.groupBox_flash, "flash_browse", "", height=26)
        self.flash_browse.setFixedWidth(46)
        self.flash_browse.setIcon(theme.icon("folder", theme.TEXT_MUTED, 14, 1.7))
        self.flash_browse.setToolTip("浏览镜像文件")
        path_row.addWidget(self.flash_browse)
        flash_layout.addLayout(path_row)

        # 第 2 行：Flash + fastboot mode/reboot
        flash_row = QtWidgets.QHBoxLayout()
        flash_row.setSpacing(5)
        self.flash_btn = self._button(
            self.groupBox_flash, "flash_btn", "Flash", height=28)
        self._accent(self.flash_btn)
        flash_row.addWidget(self.flash_btn)
        self.fb_mode = self._button(
            self.groupBox_flash, "fb_mode", "bootloader", height=28)
        self.fb_mode.setToolTip("adb reboot bootloader")
        flash_row.addWidget(self.fb_mode, 1)
        self.fb_reboot = self._button(
            self.groupBox_flash, "fb_reboot", "reboot", height=28)
        flash_row.addWidget(self.fb_reboot)
        flash_layout.addLayout(flash_row)

    def _build_func_group(self, parent):
        """func：4 个功能键排一行。

        按 func-list 精简：
        - 背光滑块去掉（常用工具页的「显示调试」里有更完整的一份）
        - 「pull」（截图 + 拉取到本地）去掉——侧边栏「快捷操作 → 截图并保存」
          调的是同一个 on_sc_pull()，留着就是重复入口；只截图不拉取的
          「screencap」保留，两者不等价。
        """
        self.groupBox_6, func_layout = self._group(parent, "groupBox_6", "func")

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)

        func_buttons = [
            ("func_power", "power-key"),
            ("func_screencap", "screencap"),
            ("func_rec_start", "rec start"),
            ("func_rec_stop", "rec stop"),
        ]
        for index, (name, text) in enumerate(func_buttons):
            btn = self._button(self.groupBox_6, name, text, height=28)
            setattr(self, name, btn)
            grid.addWidget(btn, 0, index)

        for col in range(len(func_buttons)):
            grid.setColumnStretch(col, 1)
        func_layout.addLayout(grid)
        func_layout.addStretch(1)

    # ---------- ylog ----------

    def _build_ylog(self, MainWindow):
        self.groupBox_3, ylog_layout = self._group(
            MainWindow, "groupBox_3", "ylog", margins=(10, 16, 10, 8), spacing=6)
        ylog_row = QtWidgets.QHBoxLayout()
        ylog_row.setSpacing(8)

        self.label_9 = QtWidgets.QLabel(self.groupBox_3)
        self.label_9.setObjectName("label_9")
        ylog_row.addWidget(self.label_9)
        self.ylogpath = QtWidgets.QLineEdit(self.groupBox_3)
        self.ylogpath.setMinimumHeight(28)
        self.ylogpath.setMinimumWidth(150)
        self.ylogpath.setObjectName("ylogpath")
        ylog_row.addWidget(self.ylogpath, 4)
        self.pushButton_5 = self._button(
            self.groupBox_3, "pushButton_5", "导出ylog", height=28, min_width=92)
        self._accent(self.pushButton_5)
        ylog_row.addWidget(self.pushButton_5)
        ylog_layout.addLayout(ylog_row)

        # Project / Sub-Name 各占一行。
        #
        # 原来两个挤在一行还各限死宽度（120 / 160），加起来比卡片还宽，
        # 结果双双被压到 ~70px，Sub-Name 只看得见四五个字；改成平分一行也只有
        # 104px，名字稍长就滚。各占一行后每个框约 280px（标签只占一行开头）。
        # 代价是卡片高 128 → 158，Shell 页还有 100 多 px 余量，放得下。
        for label_attr, edit_attr, obj_name in (
                ("label_7", "ylogpath_2", "ylogpath_2"),
                ("label_8", "ylogpath_3", "ylogpath_3")):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            label = QtWidgets.QLabel(self.groupBox_3)
            label.setObjectName(label_attr)
            setattr(self, label_attr, label)
            row.addWidget(label)
            edit = QtWidgets.QLineEdit(self.groupBox_3)
            edit.setMinimumHeight(28)
            edit.setMinimumWidth(120)
            edit.setObjectName(obj_name)
            setattr(self, edit_attr, edit)
            row.addWidget(edit, 1)
            ylog_layout.addLayout(row)
        self.controlPanel.layout().addWidget(self.groupBox_3)

    # ---------- APK & Tools ----------

    def _build_tools(self, MainWindow):
        self.groupBox_tools, tools_layout = self._group(
            MainWindow, "groupBox_tools", "APK & Tools",
            margins=(10, 16, 10, 8), spacing=6)
        tools_grid = QtWidgets.QGridLayout()
        tools_grid.setSpacing(6)

        tools_grid.addWidget(QtWidgets.QLabel("APK:", self.groupBox_tools), 0, 0)
        self.apk1_path = QtWidgets.QLineEdit(self.groupBox_tools)
        self.apk1_path.setMinimumHeight(28)
        self.apk1_path.setPlaceholderText("选择要安装的 APK 文件…")
        self.apk1_path.setObjectName("apk1_path")
        tools_grid.addWidget(self.apk1_path, 0, 1)
        self.apk1_browse = self._button(
            self.groupBox_tools, "apk1_browse", "", height=28, min_width=38)
        self.apk1_browse.setMaximumWidth(44)
        self.apk1_browse.setIcon(theme.icon("folder", theme.TEXT_MUTED, 15, 1.7))
        self.apk1_browse.setToolTip("浏览 APK 文件")
        tools_grid.addWidget(self.apk1_browse, 0, 2)
        self.apk1_install = self._button(
            self.groupBox_tools, "apk1_install", "Install", height=28, min_width=84)
        tools_grid.addWidget(self.apk1_install, 0, 3)

        tools_grid.addWidget(QtWidgets.QLabel("投屏:", self.groupBox_tools), 1, 0)
        self.scrcpy_path = QtWidgets.QLineEdit(self.groupBox_tools)
        self.scrcpy_path.setMinimumHeight(28)
        self.scrcpy_path.setPlaceholderText("选择 scrcpy 可执行文件…")
        self.scrcpy_path.setObjectName("scrcpy_path")
        tools_grid.addWidget(self.scrcpy_path, 1, 1)
        self.scrcpy_browse = self._button(
            self.groupBox_tools, "scrcpy_browse", "", height=28, min_width=38)
        self.scrcpy_browse.setMaximumWidth(44)
        self.scrcpy_browse.setIcon(theme.icon("folder", theme.TEXT_MUTED, 15, 1.7))
        self.scrcpy_browse.setToolTip("浏览 scrcpy 程序")
        tools_grid.addWidget(self.scrcpy_browse, 1, 2)
        self.scrcpy_start = self._button(
            self.groupBox_tools, "scrcpy_start", "投屏", height=28, min_width=84)
        self._accent(self.scrcpy_start)
        tools_grid.addWidget(self.scrcpy_start, 1, 3)

        tools_grid.setColumnStretch(1, 1)
        tools_layout.addLayout(tools_grid)
        self.controlPanel.layout().addWidget(self.groupBox_tools)

    # ---------- 右侧 Log 面板 ----------

    def _build_log(self, parent):
        """右侧竖向 Log：占满整屏高度，标题栏放操作按钮。

        控件名沿用原来的 groupBox_2 / textBrowser / pushButton_*_log，
        业务代码（shell_tools.py）无需改动。
        """
        self.groupBox_2, log_layout = self._group(
            parent, "groupBox_log", "Log", margins=(10, 16, 10, 10))

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(6)
        self.log_status = QtWidgets.QLabel("就绪", self.groupBox_2)
        self.log_status.setProperty("hint", True)
        self.log_status.setMinimumWidth(28)
        toolbar.addWidget(self.log_status, 1)

        self.pushButton_copy_log = self._button(
            self.groupBox_2, "pushButton_copy_log", "复制", height=26, min_width=56)
        self._ghost(self.pushButton_copy_log)
        toolbar.addWidget(self.pushButton_copy_log)

        self.pushButton_clear_log = self._button(
            self.groupBox_2, "pushButton_clear_log", "清空", height=26, min_width=56)
        self._ghost(self.pushButton_clear_log)
        toolbar.addWidget(self.pushButton_clear_log)
        log_layout.addLayout(toolbar)

        self.textBrowser = QtWidgets.QTextBrowser(self.groupBox_2)
        self.textBrowser.setObjectName("logView")
        # 下限给 200：宽度由外层 splitter 决定（默认约 240），
        # 硬下限设太大会把分组框的右边距挤没
        self.textBrowser.setMinimumWidth(200)
        self.textBrowser.setMinimumHeight(200)
        log_layout.addWidget(self.textBrowser, 1)

        # 最小宽度给 240：日志是文本，窄了可横向滚动；
        # 再窄连“复制/清空”按钮都放不下
        self.groupBox_2.setMinimumWidth(240)
        parent.addWidget(self.groupBox_2)

        # 兼容旧布局留下的属性引用
        self.logBottomLayout = toolbar

    # ---------- 文案 ----------

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        t = lambda s: _translate("MainWindow", s)  # noqa: E731

        self.groupBox_3.setTitle(t("ylog"))
        self.label_9.setText(t("ylog保存路径:"))
        self.label_7.setText(t("Project:"))
        self.label_8.setText(t("Sub-Name:"))
        self.pushButton_5.setText(t("导出ylog"))
        self.groupBox_3.setTitle(t("ylog"))
        self.groupBox_dl.setTitle(t("Download Mode"))
        self.dl_autodloader.setText(t("UNISOC autodloader"))
        self.dl_edl.setText(t("QCOM EDL"))
        self.groupBox_debug.setTitle(t("Debug"))
        self.debug_shell_run.setText(t("Run"))
        self.debug_shell_stop.setText(t("Stop"))
        self.debug_density_get.setText(t("density"))
        self.debug_density_set.setText(t("Set"))
        self.debug_printk_get.setText(t("Get"))
        self.debug_printk_set.setText(t("Set"))
        self.groupBox_flash.setTitle(t("fastboot flash"))
        self.flash_browse.setText(t(""))
        self.flash_btn.setText(t("Flash"))
        self.fb_mode.setText(t("fastboot mode"))
        self.fb_reboot.setText(t("reboot"))
        self.groupBox_6.setTitle(t("func"))
        self.func_power.setText(t("power-key"))
        self.func_screencap.setText(t("screencap"))
        self.func_rec_start.setText(t("rec start"))
        self.func_rec_stop.setText(t("rec stop"))
        self.groupBox_gpio.setTitle(t("GPIO"))
        self.gpio_check.setText(t("查询"))
        self.groupBox_2.setTitle(t("Log"))
        self.pushButton_clear_log.setText(t("清空"))
        self.pushButton_copy_log.setText(t("复制"))
        self.groupBox_tools.setTitle(t("APK & Tools"))
        self.apk1_browse.setText(t(""))
        self.apk1_install.setText(t("Install"))
        self.scrcpy_browse.setText(t(""))
        self.scrcpy_start.setText(t("投屏"))
