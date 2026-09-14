"""常用工具 · 异常守护（ESD / 内核异常实时监控）——**已下线**。

按 func-list.md 的标记（编号 20 = 否）本模块不再挂进常用工具页：
ESD 不做，其余规则与「日志分析 + 现场包」重叠。文件保留是为了把这一行
加回 tools_page.SECTIONS（以及 _inject_runner / SECTIONS_WITHOUT_OUTPUT）
就能恢复，不用翻 git 历史。

---- 以下为原说明 ----

屏体调试最怕的两件事：ESD 导致的花屏闪屏，和 DSI/显示子系统的超时报警。
这些信息都在 dmesg / logcat 里，但它们是滚动的——人盯着看十几分钟就会漏，
而漏掉的那一行往往就是复现证据。

这里挂一个后台流式抓取，逐行匹配关键字，命中就记一条（时间/类别/原文）
并弹提示。命中记录能直接导出，配合「现场包」就是完整的复现材料。
"""

import collections
import os
import re
import subprocess
from datetime import datetime

from PyQt5.QtCore import QProcess, Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QComboBox, QCheckBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QFileDialog, QAbstractItemView)

import theme
import toolchain
import ui_widgets as W

# (类别, 正则, 说明)
GUARD_RULES = [
    ("ESD/复位", r"\besd\b|esd_check|esd reset|panel reset|reset gpio", 
     "ESD 检测与屏体复位"),
    ("DSI 超时/欠载",
     r"dsi[^,;]{0,24}(timeout|underflow|underrun|error)|underrun|"
     r"fence timeout|te timeout|te error|cmdq timeout|mdp underrun",
     "MIPI DSI 时序异常，通常伴随花屏/闪屏"),
    ("显示异常", r"dpu|disp[^,;]{0,16}(timeout|error|fail)|"
                 r"backlight[^,;]{0,16}(fail|error)|crc error",
     "显示控制器 / 背光异常"),
    ("内核崩溃", r"kernel panic|unable to handle kernel|BUG:|"
                 r"watchdog|hard lockup|soft lockup|call trace",
     "内核级崩溃，通常直接重启"),
    ("内存不足", r"out of memory|oom-killer|lowmemorykiller|page allocation failure",
     "内存压力，可能引发丢帧"),
    ("存储 IO", r"ext4-fs error|i/o error|mmc[0-9]?: error|ufs.*error",
     "存储读写异常"),
    ("进程崩溃", r"segfault|signal 11|fatal exception|tombstone",
     "应用/服务进程崩溃"),
]

SOURCES = [
    ("dmesg -w（内核，推荐）", ["shell", "dmesg", "-w"]),
    ("logcat 实时（全部）", ["logcat", "-v", "threadtime"]),
    ("logcat 实时（crash）", ["logcat", "-b", "crash", "-v", "threadtime"]),
    ("logcat 实时（只看错误）", ["logcat", "-v", "threadtime", "*:E"]),
]

MAX_HITS = 500
MAX_LINE = 400
# 命中提示最短间隔：内核报错会成片刷，每条都弹会盖住界面
TOAST_INTERVAL_MS = 4000

# 行首的内核时间戳与各种数字（pid / 地址 / 计数）在去重时折叠掉
_KERNEL_STAMP = re.compile(r"^\[\s*\d+\.\d+\]\s*")
_DIGITS = re.compile(r"\d+")


def _dedupe_key(text):
    return _DIGITS.sub("#", _KERNEL_STAMP.sub("", text))[:200]


class GuardSection(QWidget):
    """异常关键字守护。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._buffer = ""
        self._hits = 0
        self._last_toast = 0.0
        self._tail = collections.deque(maxlen=4)
        self._seen = {}
        self._build_ui()

    # ---------- 界面 ----------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_control_card())
        layout.addWidget(self._build_hit_card(), 1)

    def _build_control_card(self):
        card = W.Card("异常守护")
        hint = W.heading(
            "后台盯着内核/日志里的 ESD、DSI 超时、underrun、panic 等关键字，"
            "命中就记录并提示——复现窗口很短，漏掉的那一行往往就是证据。")
        card.add(hint)

        row = card.add_row()
        row.addWidget(W.field_label("来源", card))
        self.source_combo = QComboBox(card)
        self.source_combo.setMinimumHeight(30)
        self.source_combo.setMinimumWidth(210)
        for label, _args in SOURCES:
            self.source_combo.addItem(label)
        row.addWidget(self.source_combo)
        row.addSpacing(6)

        self.start_btn = W.accent_button("开始守护", "shield", card)
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self.start)
        row.addWidget(self.start_btn)

        self.stop_btn = W.danger_button("停止", None, card)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        row.addWidget(self.stop_btn)

        clear = W.soft_button("清空记录", None, card)
        clear.clicked.connect(self.clear_hits)
        row.addWidget(clear)

        export = W.soft_button("导出记录", "download", card)
        export.clicked.connect(self.export_hits)
        row.addWidget(export)
        row.addStretch()

        self.status_label = W.heading("未开始", card)
        card.add(self.status_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self.rule_boxes = {}
        for index, (name, pattern, tip) in enumerate(GUARD_RULES):
            box = QCheckBox(name, card)
            box.setChecked(True)
            box.setToolTip("{}\n匹配：{}".format(tip, pattern))
            self.rule_boxes[name] = box
            grid.addWidget(box, index // 4, index % 4)
        for col in range(4):
            grid.setColumnStretch(col, 1)
        card.add_layout(grid)
        return card

    def _build_hit_card(self):
        card = W.Card("命中记录")
        self.count_label = W.heading("0 条", card)
        card.add_trailing(self.count_label)

        self.table = QTableWidget(0, 5, card)
        self.table.setHorizontalHeaderLabels(["时间", "类别", "关键字", "次数", "原文"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(140)
        header = self.table.horizontalHeader()
        for column in (0, 1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        card.add(self.table, 1)

        note = W.heading(
            "同一条异常反复刷屏时按「次数」合并（pid、地址这类数字会被折叠）；"
            "记录上限 {} 条，复现完建议立刻导出。".format(MAX_HITS), card)
        card.add(note)
        return card

    # ---------- 守护 ----------

    def compiled_rules(self):
        rules = []
        for name, pattern, _tip in GUARD_RULES:
            if not self.rule_boxes[name].isChecked():
                continue
            try:
                rules.append((name, re.compile(pattern, re.I)))
            except re.error:
                continue
        return rules

    def start(self):
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            return
        rules = self.compiled_rules()
        if not rules:
            self._toast("至少选一类要守护的异常", "warning")
            return
        if not toolchain.available("adb"):
            self._toast("没找到 adb，请先在「设置」里指定 platform-tools", "error", 4200)
            return

        args = SOURCES[self.source_combo.currentIndex()][1]
        self._tail.clear()
        self._process = QProcess(self)
        program, full_args = toolchain.adb_program_args(args)
        self._process.setProgram(program)
        self._process.setArguments(full_args)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_output)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._buffer = ""
        self._process.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.source_combo.setEnabled(False)
        self.status_label.setText("守护中…（{}）".format(
            self.source_combo.currentText()))
        self._toast("异常守护已启动", "success", 1800)

    def stop(self):
        """停掉守护。

        QProcess 直接起 adb（没有 shell 包一层），所以 kill 掉的就是 adb 客户端
        本身；adb 客户端一断，设备端的 dmesg -w 也会结束。
        """
        process = self._process
        if process is None:
            return
        self._process = None
        for signal_name in ("readyReadStandardOutput", "finished", "errorOccurred"):
            try:
                getattr(process, signal_name).disconnect()
            except (TypeError, RuntimeError):
                pass

        pid = 0
        try:
            pid = int(process.processId() or 0)
        except Exception:                                  # noqa: BLE001
            pid = 0
        process.kill()
        process.waitForFinished(1500)
        if os.name == "nt" and pid and process.state() != QProcess.NotRunning:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5)
            except Exception:                              # noqa: BLE001
                pass
        self._set_idle("已停止")

    def _set_idle(self, text):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.source_combo.setEnabled(True)
        self.status_label.setText("{} · 累计命中 {} 条".format(text, self._hits))

    def _on_finished(self, exit_code, _status):
        self._process = None
        tail = " / ".join(list(self._tail)[-2:]) if self._tail else ""
        if exit_code == 0:
            self._set_idle("已结束")
            return
        # 失败原因写清楚：最常见的就是设备没 root，dmesg 被内核拒绝
        reason = tail or "没有输出"
        self._set_idle("已结束（退出码 {}）".format(exit_code))
        self.status_label.setText("已结束（退出码 {}）：{}".format(exit_code, reason[:90]))
        if "permission denied" in reason.lower() or "klogctl" in reason.lower():
            self._toast("dmesg 权限不足：设备可能没 root。"
                        "可先执行 adb root，或把来源换成 logcat", "error", 6000)
        elif self._hits == 0:
            self._toast("守护已结束但没有命中：{}".format(reason[:60]), "warning", 4200)

    def _on_error(self, error):
        self.status_label.setText("启动失败：{}".format(error))
        self.stop()

    # ---------- 输出处理 ----------

    def _on_output(self):
        if self._process is None:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode(
            errors="replace")
        self._buffer += chunk
        # 按行切；最后一段可能是不完整的行，留到下次
        lines = re.split(r"\r?\n", self._buffer)
        self._buffer = lines.pop()
        for line in lines:
            self._inspect(line)

    def _inspect(self, line):
        if not line.strip():
            return
        # 留着最近几行原始输出：dmesg 被内核拒了、adb 掉线这类原因都在里面，
        # 只回一个「退出码 1」用户根本不知道发生了什么
        self._tail.append(line.strip())
        for name, regex in self.compiled_rules():
            match = regex.search(line)
            if not match:
                continue
            self._add_hit(name, match.group(0), line)
            # 一行只记一次，避免同一行命中多条规则刷屏
            return

    def _add_hit(self, category, keyword, line):
        """记一条命中；同形状的行只累加次数。

        内核异常经常成片刷（同一句带不同 pid/地址），一条一行的话几秒钟就
        几百行，真正有用的信息被埋掉。这里把数字折成 # 后做去重键。
        """
        self._hits += 1
        text = line.strip()[:MAX_LINE]
        key = (category, _dedupe_key(text))
        row = self._seen.get(key)
        if row is not None:
            item = self.table.item(row, 3)
            count = int(item.text()) + 1 if item else 2
            item.setText(str(count))
            stamp = self.table.item(row, 0)
            if stamp is not None:
                stamp.setText(datetime.now().strftime("%H:%M:%S"))
            self.count_label.setText("{} 条（{} 类）".format(self._hits, self.table.rowCount()))
            self._maybe_toast(category, keyword)
            return

        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [datetime.now().strftime("%H:%M:%S"), category,
                  keyword[:40], "1", text]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col != 4:
                item.setTextAlignment(Qt.AlignCenter)
            if category in ("内核崩溃", "ESD/复位"):
                item.setForeground(QColor(theme.DANGER))
            elif category in ("DSI 超时/欠载", "显示异常"):
                item.setForeground(QColor(theme.WARNING))
            self.table.setItem(row, col, item)
        self._seen[key] = row
        while self.table.rowCount() > MAX_HITS:
            self._drop_first_row()
        self.table.scrollToBottom()
        self.count_label.setText("{} 条（{} 类）".format(self._hits, self.table.rowCount()))
        self._maybe_toast(category, keyword)

    def _drop_first_row(self):
        """超出上限时丢掉最老的一行，并把去重表里的行号整体上移。"""
        for key, row in list(self._seen.items()):
            if row == 0:
                self._seen.pop(key, None)
            else:
                self._seen[key] = row - 1
        self.table.removeRow(0)

    def _maybe_toast(self, category, keyword):
        """提示要限流：异常成片刷的时候每条都弹会把界面盖住。"""
        now = datetime.now().timestamp() * 1000
        if now - self._last_toast <= TOAST_INTERVAL_MS:
            return
        self._last_toast = now
        self._toast("命中 {}：{}".format(category, keyword[:60]),
                    "error" if category in ("内核崩溃", "ESD/复位") else "warning",
                    3600)

    # ---------- 记录操作 ----------

    def clear_hits(self):
        self.table.setRowCount(0)
        self._hits = 0
        self._seen.clear()
        self.count_label.setText("0 条")

    def hits_text(self):
        rows = ["# DisplayTools 异常守护记录",
                "# 导出时间：{}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "# 来源：{}".format(self.source_combo.currentText()),
                "# 说明：「次数」是同一类异常合并后的计数",
                ""]
        for row in range(self.table.rowCount()):
            cells = [self.table.item(row, col).text() if self.table.item(row, col)
                     else "" for col in range(5)]
            rows.append("[{}] {:<10} {:<16} x{:<5} {}".format(*cells))
        return "\n".join(rows) + "\n"

    def export_hits(self):
        if self.table.rowCount() == 0:
            self._toast("还没有命中记录可导出", "warning")
            return None
        default = "guard_{}.txt".format(datetime.now().strftime("%Y%m%d-%H%M%S"))
        path, _ = QFileDialog.getSaveFileName(
            self, "导出守护记录", default, "文本文件 (*.txt)")
        if not path:
            return None
        try:
            with open(path, "w", encoding="utf-8-sig") as handle:
                handle.write(self.hits_text())
        except Exception as exc:                           # noqa: BLE001
            self._toast("导出失败：{}".format(exc), "error")
            return None
        self._toast("已导出到 {}".format(path.rsplit("\\", 1)[-1]), "success")
        return path

    # ---------- 杂项 ----------

    def _toast(self, message, kind="info", duration=2200):
        window = self.window()
        if hasattr(window, "toast"):
            window.toast(message, kind, duration)

    def stop_background(self):
        if self._process is not None:
            self.stop()
