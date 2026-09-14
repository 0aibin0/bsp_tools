"""常用工具 · 日志分析

抓取 logcat / dmesg / 内核日志，支持关键字过滤、等级筛选、错误提取与导出。
流式输出，长时间抓取也不会卡住界面。

关于 dmesg -w：内核的 ring buffer 会把**已有的全部历史**先吐出来
（实测某机型一次 15000+ 行），然后才跟随新日志。如果原样渲染会瞬间冲爆界面，
所以对流式来源做了积压截断：只保留最后 BACKLOG_KEEP 行。
"""

import os
import re
from datetime import datetime

from PyQt5.QtCore import QProcess, Qt, QTimer
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QComboBox, QLineEdit, QPlainTextEdit, QFileDialog,
                             QCheckBox, QLabel, QApplication)

import theme
import toolchain
import ui_widgets as W


# (显示名, 命令, 积压保留行数)
# 积压保留只对流式来源有意义：dmesg -w / logcat 实时启动时会先吐历史。
# None 表示不截断（快照类本来就短）。
LOG_SOURCES = [
    ("logcat（最近 3000 行）", ['adb', 'logcat', '-d', '-t', '3000'], None),
    ("logcat（实时）", ['adb', 'logcat', '-v', 'threadtime'], 1000),
    ("dmesg 内核日志（快照）", ['adb', 'shell', 'dmesg'], None),
    ("dmesg 内核日志（实时 -w）", ['adb', 'shell', 'dmesg', '-w'], 300),
    ("printk 等级", ['adb', 'shell', 'cat', '/proc/sys/kernel/printk'], None),
]

LEVEL_PATTERNS = [
    ("E", re.compile(r"(^|\s)E[\s/]|E/|error|failed|fail|fatal|panic|exception|denied|timeout", re.I)),
    ("W", re.compile(r"(^|\s)W[\s/]|W/|warn", re.I)),
    ("I", re.compile(r"(^|\s)I[\s/]|I/|info", re.I)),
    ("D", re.compile(r"(^|\s)D[\s/]|D/|debug", re.I)),
]

MAX_BUFFER_LINES = 20000
# 待渲染队列上限：输出比渲染快时（dmesg -w 启动瞬间）只保留最后这些行
MAX_PENDING_LINES = 3000


class LogAnalyzerSection(QWidget):
    """日志抓取 + 过滤 + 导出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._buffer = []          # 已抓到的原始行
        self._seen = 0             # 已渲染到视图的行数
        self._running = False

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(160)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._pending = []
        self._backlog_keep = None
        self._backlog_trimmed = 0

        self._build_ui()

    # ================= 界面 =================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---- 工具栏 ----
        bar = W.Card("抓取")
        row = bar.add_row()

        self.source_combo = QComboBox(bar)
        for title, _cmd, _keep in LOG_SOURCES:
            self.source_combo.addItem(title)
        self.source_combo.setMinimumWidth(210)
        self.source_combo.setToolTip("选择日志来源；带「实时」的会持续输出直到点停止")
        row.addWidget(self.source_combo)

        self.fetch_btn = W.accent_button("开始抓取", "download", bar)
        self.fetch_btn.clicked.connect(self.toggle_fetch)
        row.addWidget(self.fetch_btn)

        self.clear_btn = W.soft_button("清空", "trash", bar)
        self.clear_btn.clicked.connect(self.clear_log)
        row.addWidget(self.clear_btn)

        self.export_btn = W.soft_button("导出", "file", bar)
        self.export_btn.clicked.connect(self.export_log)
        self.export_btn.setToolTip("把当前视图内容导出为文本文件")
        row.addWidget(self.export_btn)
        row.addStretch()

        # 三个开关单独一行：和按钮挤一行会把模块撑到 735px
        switch_row = bar.add_row()
        switch_row.addWidget(W.field_label("过滤开关", bar))
        self.regex_check = QCheckBox("正则", bar)
        self.regex_check.stateChanged.connect(lambda _s: self.render())
        switch_row.addWidget(self.regex_check)

        self.only_error = QCheckBox("只看错误", bar)
        self.only_error.stateChanged.connect(lambda _s: self.render())
        switch_row.addWidget(self.only_error)

        # 与「只看错误」相反：不隐藏不匹配的行，只把关键字标出来，
        # 方便带着上下文看
        self.highlight_check = QCheckBox("高亮关键字", bar)
        self.highlight_check.setToolTip(
            "勾上后不隐藏不匹配的行，只给命中的关键字加底色")
        self.highlight_check.stateChanged.connect(lambda _s: self.render())
        switch_row.addWidget(self.highlight_check)

        self.auto_scroll = QCheckBox("自动滚动", bar)
        self.auto_scroll.setChecked(True)
        switch_row.addWidget(self.auto_scroll)

        switch_row.addWidget(W.field_label("关键字", bar))
        self.filter_edit = QLineEdit(bar)
        self.filter_edit.setPlaceholderText("多个用 | 分隔，例如 dsi|lcm")
        self.filter_edit.setMinimumWidth(180)
        self.filter_edit.textChanged.connect(lambda _t: self.render())
        switch_row.addWidget(self.filter_edit, 1)

        layout.addWidget(bar)

        # ---- 日志视图 ----
        view_card = W.Card("日志")
        self.count_label = QLabel("0 行", view_card)
        self.count_label.setStyleSheet(
            f"color: {theme.TEXT_FAINT}; font-size: 12px; background: transparent;")
        view_card.add_trailing(self.count_label)

        self.view = QPlainTextEdit(view_card)
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setFont(theme.mono_font(10))
        self.view.setMaximumBlockCount(MAX_BUFFER_LINES)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setPlaceholderText("选择日志来源后点击「开始抓取」…")
        view_card.add(self.view, 1)
        layout.addWidget(view_card, 1)

    # ================= 抓取 =================

    def toggle_fetch(self):
        if self._running:
            self.stop_fetch()
        else:
            self.start_fetch()

    def start_fetch(self):
        idx = self.source_combo.currentIndex()
        title, command, backlog_keep = LOG_SOURCES[idx]

        self._buffer = []
        self._seen = 0
        self._pending = []
        self._backlog_keep = backlog_keep      # None = 不截断
        self._backlog_trimmed = 0
        self.view.clear()
        self.count_label.setText("0 行")

        self._process = QProcess(self)
        program, args = toolchain.adb_program_args(command[1:])
        self._process.setProgram(program)
        self._process.setArguments(args)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_output)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._process.start()

        self._running = True
        self.fetch_btn.setText("停止抓取")
        self.fetch_btn.setProperty("accent", False)
        self.fetch_btn.setProperty("danger", True)
        self._restyle(self.fetch_btn)
        self._flush_timer.start()
        self._append_system_line(f"$ {' '.join(command)}")
        if backlog_keep:
            self._append_system_line(
                f"流式抓取：启动时会先输出历史日志，界面只保留最后 {backlog_keep} 行")

    def stop_fetch(self):
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1500)
        self._finish_ui()

    def _finish_ui(self):
        self._running = False
        self._flush_timer.stop()
        self._flush_pending()
        self.fetch_btn.setText("开始抓取")
        self.fetch_btn.setProperty("danger", False)
        self.fetch_btn.setProperty("accent", True)
        self._restyle(self.fetch_btn)

    @staticmethod
    def _restyle(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _append_system_line(self, text):
        self._buffer.append(f"── {text}")
        self._pending.append(self._buffer[-1])

    def _on_output(self):
        if self._process is None:
            return
        chunk = bytes(self._process.readAllStandardOutput()).decode(errors='replace')
        if not chunk:
            return
        for line in chunk.splitlines():
            line = line.rstrip('\r')
            self._buffer.append(line)
            if self._matches(line):
                self._pending.append(line)
        # 流式来源：缓冲区也封顶，否则切到「无过滤」重绘上万行会卡住界面
        keep = self._backlog_keep
        buffer_cap = min(MAX_BUFFER_LINES, keep * 4) if keep else MAX_BUFFER_LINES
        if len(self._buffer) > buffer_cap:
            self._backlog_trimmed += len(self._buffer) - buffer_cap
            self._buffer = self._buffer[-buffer_cap:]
        # 输出比渲染快时（dmesg -w 启动瞬间）不能无限堆积待渲染行
        if len(self._pending) > MAX_PENDING_LINES:
            self._backlog_trimmed += len(self._pending) - MAX_PENDING_LINES
            self._pending = self._pending[-MAX_PENDING_LINES:]

    def _flush_pending(self):
        if not self._pending:
            return
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        scrollbar = self.view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4

        for line in self._pending:
            self._insert_line(cursor, line, self._line_match(line))
        self._pending = []

        # 流式来源：视图也要封顶。dmesg -w 启动瞬间会来上万行，
        # 只截断缓冲区不够——已经插进视图的行不会自己消失。
        keep = self._backlog_keep
        if keep:
            cap = keep * 2
            blocks = self.view.blockCount()
            if blocks > cap:
                trim_cursor = self.view.textCursor()
                trim_cursor.movePosition(QTextCursor.Start)
                trim_cursor.movePosition(QTextCursor.Down,
                                         QTextCursor.KeepAnchor, blocks - cap)
                trim_cursor.movePosition(QTextCursor.StartOfBlock,
                                         QTextCursor.KeepAnchor)
                trim_cursor.removeSelectedText()
                self._backlog_trimmed += blocks - cap

        shown = max(self.view.blockCount() - 1, 0)
        text = f"{shown} / {len(self._buffer)} 行"
        if self._backlog_trimmed:
            text += f"（滚动丢弃 {self._backlog_trimmed} 行）"
        self.count_label.setText(text)
        if self.auto_scroll.isChecked() or at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _insert_line(self, cursor, line, match=None):
        """写入一行：按等级着色，命中的关键字再加底色。

        「只看错误」是过滤（不匹配的直接不显示），关键字高亮是标记——
        两种需求不一样：过滤用于缩小范围，高亮用于在上下文里定位。
        """
        fmt = QTextCharFormat()
        if LEVEL_PATTERNS[0][1].search(line):
            fmt.setForeground(QColor(theme.DANGER))
        elif LEVEL_PATTERNS[1][1].search(line):
            fmt.setForeground(QColor(theme.WARNING))
        else:
            fmt.setForeground(QColor(theme.LOG_TEXT))

        if match is None or not match.group(0):
            cursor.insertText(line + "\n", fmt)
            return

        start, end = match.span()
        start = max(0, min(start, len(line)))
        end = max(start, min(end, len(line)))
        if start:
            cursor.insertText(line[:start], fmt)
        hit = QTextCharFormat(fmt)
        hit.setBackground(QColor(theme.LOG_HIGHLIGHT))
        hit.setForeground(QColor(theme.LOG_HIGHLIGHT_TEXT))
        hit.setFontWeight(70)
        cursor.insertText(line[start:end], hit)
        if end < len(line):
            cursor.insertText(line[end:], fmt)
        cursor.insertText("\n", fmt)

    def _on_finished(self, exit_code, _status):
        self._finish_ui()
        if exit_code != 0:
            self._append_system_line(f"进程结束，退出码 {exit_code}")
            self._flush_pending()

    def _on_error(self, _err):
        self._finish_ui()
        self._append_system_line("adb 启动失败，请确认 adb 已在 PATH 中")
        self._flush_pending()

    # ================= 过滤 =================

    def _compile_filter(self):
        text = self.filter_edit.text().strip()
        if not text:
            return None
        pattern = text if self.regex_check.isChecked() else '|'.join(
            re.escape(part) for part in text.split('|') if part)
        if not pattern:
            return None
        try:
            return re.compile(pattern, re.I)
        except re.error:
            return None

    def _matches(self, line):
        if self.only_error.isChecked() and not LEVEL_PATTERNS[0][1].search(line):
            return False
        regex = self._compile_filter()
        if regex is None:
            return True
        return bool(regex.search(line))

    def _line_match(self, line):
        """流式写入时也要高亮关键字，返回该行的匹配对象（没有则 None）。"""
        regex = self._compile_filter()
        if regex is None:
            return None
        if self.only_error.isChecked() and not LEVEL_PATTERNS[0][1].search(line):
            return None
        return regex.search(line)

    def render(self):
        """按当前过滤条件重绘视图。"""
        regex = self._compile_filter()
        only_error = self.only_error.isChecked()
        # 勾了「高亮」就不隐藏不匹配的行，只把它们标出来——
        # 调试时经常要"关键词 + 上下文"，一过滤上下文就没了
        highlight_only = self.highlight_check.isChecked()

        self.view.clear()
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        shown = 0
        for line in self._buffer:
            if only_error and not LEVEL_PATTERNS[0][1].search(line):
                continue
            match = regex.search(line) if regex is not None else None
            if regex is not None and match is None and not highlight_only:
                continue
            self._insert_line(cursor, line, match)
            shown += 1
        self.count_label.setText(f"{shown} / {len(self._buffer)} 行")

    # ================= 操作 =================

    def clear_log(self):
        self._buffer = []
        self._pending = []
        self._backlog_trimmed = 0
        self.view.clear()
        self.count_label.setText("0 行")

    def export_log(self):
        if not self.view.toPlainText().strip():
            return
        default = os.path.join(
            os.path.expanduser("~"),
            f"displaytools_log_{datetime.now():%Y%m%d_%H%M%S}.txt")
        path, _ = QFileDialog.getSaveFileName(self, "导出日志", default, "文本文件 (*.txt)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.view.toPlainText())
        except Exception as e:
            self._append_system_line(f"导出失败：{e}")
            return
        self._append_system_line(f"已导出到 {path}")
        self._flush_pending()

    def copy_all(self):
        text = self.view.toPlainText()
        if text.strip():
            QApplication.clipboard().setText(text)

    def stop(self):
        if self._running:
            self.stop_fetch()
