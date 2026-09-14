from PyQt5.QtWidgets import QWidget
from ui_initcode_builder import Ui_InitcodeBuilder
from base_tool_page import BaseToolPage
import re

import theme


# =====================================================================
# 反向解析：initcode 字节序列 → DCS 命令 + 参数
#
# 一条 initcode 固定是「3 字节包头 + 1 字节长度 + N 字节负载」：
# 负载的第一个字节是 DCS 命令（正向上就是 WriteAddr 那一项），其余是参数，
# 长度字节就等于负载的字节数。包头第一个字节决定包类型，后两个字节只是填充
# （正向写 0x78 / 0x00），解析时不参与语义判断：
#     0x05 = DCS short write, no parameter    （负载 1 字节：只有命令）
#     0x15 = DCS short write, 1 parameter     （负载 2 字节：命令 + 1 个参数）
#     0x39 = DCS long write                   （负载 N 字节）
#
# 下面这一段全是纯函数（不依赖 Qt 控件），可以离线单独测试，
# 见 devtools/_check_initcode.py。
# =====================================================================

# 包类型，即 parse_initcode 返回结果里的 kind 字段
KIND_SHORT = "short"        # 短包写，无参数
KIND_SHORT_1P = "short1"    # 短包写，1 个参数
KIND_SHORT_2P = "short2"    # 通用短包写，2 个参数
KIND_LONG = "long"          # 长包写
KIND_UNKNOWN = "unknown"    # 没见过的包头，仍按 3 + 1 + N 的结构解析

# 包头首字节 → (kind, 可读的类型说明)
PACKET_TYPES = {
    0x03: (KIND_SHORT, "Generic short write（通用短包写，无参数）"),
    0x05: (KIND_SHORT, "DCS short write, no parameter（DCS 短包写，无参数）"),
    0x13: (KIND_SHORT_1P, "Generic short write, 1 parameter（通用短包写，1 个参数）"),
    0x15: (KIND_SHORT_1P, "DCS short write, 1 parameter（DCS 短包写，1 个参数）"),
    0x23: (KIND_SHORT_2P, "Generic short write, 2 parameters（通用短包写，2 个参数）"),
    0x29: (KIND_LONG, "Generic long write（通用长包写）"),
    0x39: (KIND_LONG, "DCS long write（DCS 长包写）"),
}

# 短包的负载长度是固定的；长包由长度字节自己说了算
FIXED_PAYLOAD = {0x03: 1, 0x05: 1, 0x13: 2, 0x15: 2, 0x23: 3}

HEADER_SIZE = 3     # 包头字节数
MIN_ENTRY = 4       # 包头 + 长度字节

# 输出风格：和界面「输出格式」下拉框里每一项的 data 一一对应
STYLE_BYTE = "byte"
STYLE_WRITE = "write"
STYLE_RXX = "rxx"
STYLE_GEN_WR = "gen_wr"
STYLE_LABELS = (
    (STYLE_BYTE, "字节序列 0x39,…"),
    (STYLE_WRITE, "Write(Command)"),
    (STYLE_RXX, "Rxx"),
    (STYLE_GEN_WR, "GEN_WR"),
)

_HEX_DIGITS = "0123456789abcdefABCDEF"


class InitcodeEntry(tuple):
    """一条解析结果：(kind, cmd, params)。

    故意继承 tuple，这样 parse_initcode 的返回值严格就是
    [(kind, cmd, params), ...]，可以 `for kind, cmd, params in ...` 直接拆；
    界面想显示「原始行 / 包头」时再用 entry.raw、entry.header。
    """

    def __new__(cls, kind, cmd, params, raw="", header=0):
        self = super(InitcodeEntry, cls).__new__(cls, (kind, cmd, list(params)))
        self.kind = kind
        self.cmd = cmd
        self.params = list(params)
        self.raw = raw
        self.header = header
        return self


class ParseResult(list):
    """parse_initcode 的返回值：既是 [(kind, cmd, params), ...]，又带错误说明。

    解析失败不抛异常：能认出来的条目照样返回，问题写在 error 里（空串表示没问题）。
    """

    def __init__(self, entries=(), error=""):
        super(ParseResult, self).__init__(entries)
        self.error = error

    @property
    def ok(self):
        return not self.error


def kind_of(header):
    """包头首字节 → 包类型（kind）。"""
    return PACKET_TYPES.get(header, (KIND_UNKNOWN, ""))[0]


def describe_type(header):
    """包头首字节 → 可读的包类型说明。"""
    text = PACKET_TYPES.get(header, (KIND_UNKNOWN, ""))[1]
    if text:
        return text
    return "未知类型 0x{:02x}（按 3 + 1 + N 结构解析）".format(header & 0xff)


def _bytes_from_run(run):
    """把一段连续的十六进制字符按两位一切，切出字节值。"""
    values = []
    index = 0
    while index < len(run):
        values.append(int(run[index:index + 2], 16))
        index += 2
    return values


def _strip_comments(text):
    """去掉 // 行注释和 /* */ 块注释。

    返回 [(行号, 代码部分, 原始行), ...]：代码部分用于取字节，原始行用于展示。
    """
    rows = []
    in_block = False
    for lineno, raw in enumerate(text.splitlines(), 1):
        out = []
        index = 0
        while index < len(raw):
            if in_block:
                if raw.startswith("*/", index):
                    in_block = False
                    index += 2
                else:
                    index += 1
                continue
            if raw.startswith("//", index):
                break
            if raw.startswith("/*", index):
                in_block = True
                index += 2
                continue
            out.append(raw[index])
            index += 1
        rows.append((lineno, "".join(out), raw))
    return rows


def _scan_line(code):
    """从一行代码里取出所有字节值。

    认三种写法：0x1a / 0X1A、字符串转义 \\x1a、以及裸十六进制 1a（前后不能紧挨
    字母数字，避免把变量名里的数字当成数据）。
    """
    values = []
    index = 0
    length = len(code)
    while index < length:
        char = code[index]

        # \x1a 形式的转义
        if char == "\\" and index + 2 < length and code[index + 1] in "xX" \
                and code[index + 2] in _HEX_DIGITS:
            index += 2
            start = index
            while index < length and code[index] in _HEX_DIGITS:
                index += 1
            values.extend(_bytes_from_run(code[start:index]))
            continue

        # 0x1a 形式
        if char == "0" and index + 2 < length and code[index + 1] in "xX" \
                and code[index + 2] in _HEX_DIGITS:
            index += 2
            start = index
            while index < length and code[index] in _HEX_DIGITS:
                index += 1
            values.extend(_bytes_from_run(code[start:index]))
            continue

        # 裸十六进制，必须独立成段（39 00 00 05 这种）
        if char in _HEX_DIGITS:
            start = index
            while index < length and code[index] in _HEX_DIGITS:
                index += 1
            run = code[start:index]
            before = code[start - 1] if start else ""
            after = code[index] if index < length else ""
            if (not before or not (before.isalnum() or before == "_")) and \
                    (not after or not (after.isalnum() or after == "_")):
                if len(run) <= 2 or len(run) % 2 == 0:
                    values.extend(_bytes_from_run(run))
            continue

        index += 1
    return values


def parse_initcode(text):
    """把 initcode 字节序列还原成 [(kind, cmd, params), ...]。

    吃掉的噪声：0x 大小写、逗号 / 空格 / 换行 / 制表符混用、行尾逗号、
    // 与 /* */ 注释、C 数组的 {} 与 []、字符串反斜杠续行、\\x1a 转义。
    一条 initcode 按「3 字节包头 + 1 字节长度 + N 字节负载」消费，长度字节
    对不上会记进返回值的 .error，而不是把数据悄悄丢掉（也不抛异常）。
    """
    result = ParseResult()
    if not text or not text.strip():
        return result                       # 空输入：没有条目，也不算错误

    tokens = []
    line_text = {}
    for lineno, code, raw in _strip_comments(text):
        line_text[lineno] = raw.strip()
        for value in _scan_line(code):
            tokens.append((value, lineno))

    if not tokens:
        result.error = "没有识别到十六进制字节，请确认粘贴的是 initcode 数据。"
        return result

    problems = []
    index = 0
    total = len(tokens)
    entry_no = 0
    while index < total:
        lineno = tokens[index][1]
        if total - index < MIN_ENTRY:
            problems.append(
                "第 {} 条数据不完整：第 {} 行起只剩 {} 个字节，"
                "凑不满 3 字节包头 + 1 字节长度。".format(
                    entry_no + 1, lineno, total - index))
            break

        header = tokens[index][0]
        count = tokens[index + 3][0]
        entry_no += 1

        if count == 0:
            problems.append(
                "第 {} 条（第 {} 行）长度字节是 0x00，没有 DCS 命令，已跳过。".format(
                    entry_no, lineno))
            index += MIN_ENTRY
            continue

        payload = [value for value, _ in tokens[index + MIN_ENTRY:index + MIN_ENTRY + count]]
        if len(payload) < count:
            problems.append(
                "第 {} 条（第 {} 行）长度字节 0x{:02x} 声明 {} 个负载字节，"
                "但后面只剩 {} 个，数据被截断了。".format(
                    entry_no, lineno, count, count, len(payload)))
            break

        fixed = FIXED_PAYLOAD.get(header)
        if fixed is not None and fixed != count:
            problems.append(
                "第 {} 条（第 {} 行）包头 0x{:02x} 固定带 {} 个负载字节，"
                "长度字节却是 0x{:02x}。".format(entry_no, lineno, header, fixed, count))

        result.append(InitcodeEntry(
            kind_of(header), payload[0], payload[1:],
            raw=line_text.get(lineno, ""), header=header))
        index += MIN_ENTRY + count

    result.error = "\n".join(problems)
    return result


def to_dcs(entry):
    """把一条解析结果写回 initcode 字节行。

    写法与正向生成完全一致（逗号分隔、小写两位十六进制、行尾带逗号）：
        0x39,0x00,0x00,0x05,0x1a,0x2b,0x3c,0x4d,0x5e,
    """
    kind, cmd, params = entry
    payload = [cmd] + list(params)
    count = len(payload)
    if count <= 1:
        prefix = (0x05, 0x78, 0x00)
    elif count == 2:
        prefix = (0x15, 0x00, 0x00)
    else:
        prefix = (0x39, 0x00, 0x00)
    values = list(prefix) + [count] + payload
    return ",".join("0x{:02x}".format(int(value) & 0xff) for value in values) + ","


def format_as(entries, style=STYLE_BYTE):
    """按指定风格输出文本，风格与正向的四种输入格式一一对应。

    byte   -> 0x39,0x00,0x00,0x05,0x1a,0x2b,…
    write  -> Write(Command,0x1a); + Write(Parameter,0x2b);
    rxx    -> R1a 2b 3c
    gen_wr -> GEN_WR(0x1a,0x2b,0x3c);
    没见过的风格退回字节序列，不抛异常。
    """
    blocks = []
    for entry in entries:
        kind, cmd, params = entry
        payload = [cmd] + list(params)
        if style == STYLE_WRITE:
            lines = ["Write(Command,0x{:02x});".format(int(payload[0]) & 0xff)]
            lines += ["Write(Parameter,0x{:02x});".format(int(value) & 0xff)
                      for value in payload[1:]]
            blocks.append("\n".join(lines))
        elif style == STYLE_RXX:
            blocks.append("R" + " ".join("{:02x}".format(int(value) & 0xff)
                                         for value in payload))
        elif style == STYLE_GEN_WR:
            blocks.append("GEN_WR({});".format(
                ",".join("0x{:02x}".format(int(value) & 0xff) for value in payload)))
        else:
            blocks.append(to_dcs(entry))
    if style == STYLE_WRITE:
        return "\n\n".join(blocks)          # 每条之间空一行，看着清爽也便于回填正向
    return "\n".join(blocks)


def describe_entry(index, entry):
    """一行可读说明：第 N 条 · 类型 · 命令 0x?? · 参数 m 个 · 原始行。"""
    kind, cmd, params = entry
    raw = getattr(entry, "raw", "") or "—"
    return "第 {} 条 · {} · 命令 0x{:02x} · 参数 {} 个 · 原始行 {}".format(
        index, describe_type(getattr(entry, "header", 0)), int(cmd) & 0xff,
        len(params), raw)


def format_list(entries):
    """把解析结果整理成「一条一行」的清单文本。"""
    return "\n".join(describe_entry(index, entry)
                     for index, entry in enumerate(entries, 1))


def summarize_entries(entries):
    """一句话统计解析结果，例如「共 3 条：DCS 长包写 1 条，DCS 短包写 2 条」。"""
    entries = list(entries)
    if not entries:
        return "没有解析到 initcode 数据。"
    order = []
    counts = {}
    for entry in entries:
        text = describe_type(getattr(entry, "header", 0))
        if text not in counts:
            counts[text] = 0
            order.append(text)
        counts[text] += 1
    return "共 {} 条：{}".format(len(entries),
                                "，".join("{} {} 条".format(t, counts[t]) for t in order))


class InitcodeBuilderPage(BaseToolPage, Ui_InitcodeBuilder):
    def __init__(self, parent=None):
        super(InitcodeBuilderPage, self).__init__(parent)
        self.setupUi(self)

        self.textEdit.setPlaceholderText(
            "Enter hex WriteAddr/WriteData strings\n**********\nWriteAddr(0x1a)\n"
            "WriteData(0x2b)\nWriteData(0x3c)\nWriteData(0x4d)\nWriteData(0x5e)\n**********\n")
        self.textEdit_2.setReadOnly(True)
        self.textEdit_2.setPlaceholderText(
            "generate initcode \n(e.g. 0x39,0x00,0x00,0x05,0x1a,0x2b,0x3c,0x4d,0x5e)")
        self.lineEdit.setPlaceholderText("GEN_WR")
        self.format_hint.setProperty("hint", True)

        self.radioButton.setChecked(True)

        self.pushButton.clicked.connect(self.initcodebuilder_1)
        self.pushButton_clear.clicked.connect(self.on_clear)
        self.pushButton_copy.clicked.connect(self.on_copy)

        self.radioButton.clicked.connect(self.select_command)
        self.radioButton_2.clicked.connect(self.select_command)
        self.radioButton_3.clicked.connect(self.select_command)
        self.radioButton_4.clicked.connect(self.select_command)

        # 反向解析区块（控件本体在 ui_initcode_builder.py 里创建）
        self._reverse_entries = []
        self.reverse_input.setPlaceholderText(
            "粘贴已生成的 initcode，例如：\n"
            "0x39,0x00,0x00,0x05,0x1a,0x2b,0x3c,0x4d,0x5e,\n"
            "也认 C 数组 {0x39,0x00,…}、裸十六进制 39 00 00 05、"
            "adb dcs 写命令以及 // 与 /* */ 注释")
        for style_key, style_label in STYLE_LABELS:
            self.combo_reverse_style.addItem(style_label, style_key)
        self.reverse_list.setPlaceholderText(
            "解析清单：第 N 条 · 类型 · 命令 0x?? · 参数 m 个 · 原始行")
        self.reverse_output.setPlaceholderText("按选定的输出格式生成，可直接对照屏体 spec")
        self._set_reverse_status("等待输入：粘贴 initcode 后点「解析」", "muted")

        self.pushButton_parse.clicked.connect(self.on_reverse_parse)
        self.pushButton_reverse_copy.clicked.connect(self.on_reverse_copy)
        self.pushButton_output_copy.clicked.connect(self.on_output_copy)
        self.combo_reverse_style.currentIndexChanged.connect(self.on_reverse_style_changed)

    def on_clear(self):
        self.clear_textedits(self.textEdit, self.textEdit_2)

    def on_copy(self):
        self.copy_to_clipboard(self.textEdit_2)

    # ================= 反向解析：initcode → DCS 命令 + 参数 =================

    def on_reverse_parse(self):
        """解析左边输入框里的 initcode，列出 DCS 命令与参数，并按格式输出。"""
        try:
            result = parse_initcode(self.reverse_input.toPlainText())
        except Exception as exc:                      # 兜底：绝不让异常冒到界面
            self._reverse_entries = []
            self.reverse_list.setPlainText("解析失败：{}".format(exc))
            self.reverse_output.clear()
            self._set_reverse_status("解析失败：{}".format(exc), "bad")
            return

        self._reverse_entries = list(result)
        if not self._reverse_entries:
            self.reverse_list.setPlainText(
                result.error or "没有解析到 initcode 数据。")
            self.reverse_output.clear()
            self._set_reverse_status(
                result.error or "没有解析到 initcode 数据。",
                "warn" if result.error else "muted")
            return

        self.reverse_list.setPlainText(format_list(self._reverse_entries))
        self._render_reverse_output()
        summary = summarize_entries(self._reverse_entries)
        if result.error:
            self._set_reverse_status("{}；解析中有问题：{}".format(summary, result.error),
                                     "warn")
        else:
            self._set_reverse_status(summary, "ok")

    def on_reverse_style_changed(self):
        """切换输出格式：只重画右边输出，不用重新解析。"""
        self._render_reverse_output()

    def on_reverse_copy(self):
        """复制解析清单。"""
        self.copy_to_clipboard(self.reverse_list)

    def on_output_copy(self):
        """复制按当前格式生成的 initcode。"""
        self.copy_to_clipboard(self.reverse_output)

    def _render_reverse_output(self):
        style = self.combo_reverse_style.currentData() or STYLE_BYTE
        self.reverse_output.setPlainText(format_as(self._reverse_entries, style))

    def _set_reverse_status(self, text, tone="muted"):
        """状态提示：ok / warn / bad / muted，颜色只用 theme 里的 token。"""
        colors = {"ok": theme.SUCCESS, "warn": theme.WARNING,
                  "bad": theme.DANGER, "muted": theme.TEXT_MUTED}
        self.reverse_status.setText(text)
        self.reverse_status.setStyleSheet(
            "color: {}; font-size: 12px; background: transparent;".format(
                colors.get(tone, theme.TEXT_MUTED)))

    def select_command(self):
        """根据选中的单选按钮更新文本框和连接的槽函数"""
        self.textEdit.clear()
        self.textEdit_2.clear()

        # 断开 build 按钮的所有连接
        try:
            self.pushButton.clicked.disconnect()
        except TypeError:
            pass

        if self.radioButton.isChecked():
            self.format_hint.setText("当前格式: WriteAddr")
            self.textEdit.setPlaceholderText(
                "Enter hex WriteAddr/WriteData strings\n**********\nWriteAddr(0x1a)\n"
                "WriteData(0x2b)\nWriteData(0x3c)\nWriteData(0x4d)\nWriteData(0x5e)\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_1)
        elif self.radioButton_2.isChecked():
            self.format_hint.setText("当前格式: Write(Command)")
            self.textEdit.setPlaceholderText(
                "Enter hex Write(Command,0xxx)strings\n**********\nWrite(Command,0x1a);\n"
                "Write(Parameter,0x2b);\nWrite(Parameter,0x3c);\nWrite(Parameter,0x4d);\n"
                "Write(Parameter,0x5e);\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_2)
        elif self.radioButton_3.isChecked():
            self.format_hint.setText("当前格式: Rxx")
            self.textEdit.setPlaceholderText("Enter hex Rxx strings\n**********\nR1a 2b 3c 4d 5e\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_3)
        elif self.radioButton_4.isChecked():
            self.format_hint.setText("当前格式: GEN_WR")
            self.textEdit.setPlaceholderText(
                "Enter hex GEN_WR strings\n**********\nGEN_WR(0x1a,0x2b,0x3c,0x4d,0x5e);\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_4)

    def initcodebuilder_1(self):
        """处理 WriteAddr 和 WriteData 格式"""
        input_str = self.textEdit.toPlainText()
        rows = input_str.split('\n')
        output_rows = []
        current_addr = None
        data_values = []

        def generate_output_row(addr, data_values):
            data_count = len(data_values) + 1
            data_count_hex = f"0x{data_count:02x}"
            if data_count == 1:
                prefix = '0x05,0x78,0x00'
            elif data_count == 2:
                prefix = '0x15,0x00,0x00'
            else:
                prefix = '0x39,0x00,0x00'
            row = [prefix, data_count_hex, addr] + data_values
            return ",".join(
                [f"0x{num.lower()}" if not num.startswith("0x") else num.lower() for num in row]) + ","

        for row in rows:
            row = row.split('//')[0].strip()
            if not row:
                continue
            if 'WriteAddr' in row:
                if current_addr is not None:
                    output_rows.append(generate_output_row(current_addr, data_values))
                current_addr = row.split('(')[1].split(')')[0].strip()
                data_values = []
            elif 'WriteData' in row:
                data = row.split('(')[1].split(')')[0].strip()
                data_values.append(data)

        if current_addr is not None:
            output_rows.append(generate_output_row(current_addr, data_values))

        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_2(self):
        """处理 Write(Command) 格式"""
        input_str = self.textEdit.toPlainText()
        rows = input_str.split('\n')
        current_command = None
        data_values = []
        output_rows = []

        def generate_output_row(command, parameters):
            data_count = len(parameters) + 1
            data_count_hex = f"0x{data_count:02x}"
            if data_count == 1:
                prefix = '0x05,0x78,0x00'
            elif data_count == 2:
                prefix = '0x15,0x00,0x00'
            else:
                prefix = '0x39,0x00,0x00'
            row = [prefix, data_count_hex, command] + parameters
            return ",".join(
                [f"0x{num.lower()}" if not num.startswith("0x") else num.lower() for num in row]) + ","

        for row in rows:
            row = row.split('//')[0].strip()
            if not row:
                continue
            if 'Write(' in row:
                content = row.split('(')[1].split(')')[0]
                data_type, value = content.split(',')
                data_type, value = data_type.strip(), value.strip()
                if data_type == "Command":
                    if current_command is not None:
                        output_rows.append(generate_output_row(current_command, data_values))
                    current_command = value
                    data_values = []
                elif data_type == "Parameter":
                    data_values.append(value)

        if current_command is not None:
            output_rows.append(generate_output_row(current_command, data_values))

        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_3(self):
        """处理 Rxx 格式"""
        input_str = self.textEdit.toPlainText()
        input_str = input_str.replace("R", "")
        lines = input_str.splitlines()
        output_rows = []

        for line in lines:
            line = line.split('//')[0].strip()
            if not line:
                continue
            hex_values = line.split()
            hex_count = len(hex_values)
            count_hex = f"0x{hex_count:02x}"
            if hex_count == 1:
                prefix = '0x05,0x78,0x00'
            elif hex_count == 2:
                prefix = '0x15,0x00,0x00'
            else:
                prefix = '0x39,0x00,0x00'
            formatted_values = [f"0x{val.lower()}" for val in hex_values]
            output_str = f"{prefix},{count_hex}," + ",".join(formatted_values) + ","
            output_rows.append(output_str)

        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_4(self):
        """处理 GEN_WR 等格式"""
        instructions_str = self.lineEdit.text()
        instructions = [cmd.strip() for cmd in instructions_str.split(",")] if instructions_str else ['GEN_WR']
        input_str = self.textEdit.toPlainText()
        lines = input_str.splitlines()
        output_rows = []

        for line in lines:
            if line.strip().startswith("//") and not line.strip()[2:].strip():
                output_rows.append(line)
                continue
            comment_index = line.find("//")
            if comment_index != -1:
                code_part = line[:comment_index].strip()
                comment_part = line[comment_index:].strip()
            else:
                code_part = line.strip()
                comment_part = ""
            if code_part:
                code_part = code_part.split("//")[0].strip()
                if not code_part:
                    continue
                for instruction in instructions:
                    match = re.search(rf"{instruction}\((.*?)\);?", code_part)
                    if match:
                        hex_values = match.group(1).split(",")
                        hex_count = len(hex_values)
                        count_hex = f"0x{hex_count:02x}"
                        if hex_count == 1:
                            prefix = "0x05,0x78,0x00"
                        elif hex_count == 2:
                            prefix = "0x15,0x00,0x00"
                        else:
                            prefix = "0x39,0x00,0x00"
                        formatted_values = [val.strip().lower() for val in hex_values]
                        processed_code = f"{prefix},{count_hex}," + ",".join(formatted_values) + ","
                        break
                else:
                    processed_code = code_part
            else:
                processed_code = ""
            final_line = processed_code + comment_part
            output_rows.append(final_line)

        self.textEdit_2.setPlainText("\n".join(output_rows))
