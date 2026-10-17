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

# mipi.write 一行一条命令：`mipi.write <块类型> <负载字节...>`。
# 前缀大小写、点/下划线、有没有空格都认（mipi.write / MIPI.WRITE / mipi_write）。
_MIPI_WRITE_RE = re.compile(r"^\s*mipi\s*[._]?\s*write\b", re.IGNORECASE)

# 另外 4 种输入格式的「行首前缀」。和 mipi.write 一样：只有匹配上的行才解析，
# 其余行（# 注释 / // 注释 / 空行 / 日志里抄来的别的前缀）直接丢弃。
_PREFIX_WRITEADDR = re.compile(r"^Write(?:Addr|Data)\s*\(", re.IGNORECASE)
_PREFIX_WRITE_COMMAND = re.compile(
    r"^Write\s*\(\s*(?:Command|Parameter)\s*,", re.IGNORECASE)
_PREFIX_RXX = re.compile(r"^R[0-9a-fA-F]{1,2}(?:\s|$)")


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
    """去掉 // 行注释、# 行注释和 /* */ 块注释。

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
            if raw.startswith("//", index) or raw[index] == "#":
                break
            if raw.startswith("/*", index):
                in_block = True
                index += 2
                continue
            out.append(raw[index])
            index += 1
        rows.append((lineno, "".join(out), raw))
    return rows


def _prefix_lines(text, prefix_re):
    """按**行首前缀**过滤输入，返回 [(行号, 代码部分, 原始行), ...]。

    只有匹配上 prefix_re 的行才留下；其余内容（# 注释、// 注释、空行、
    日志里别的前缀、别的片段）**一律直接丢弃**，既不解析也不报错。

    为什么要这道闸：以前是「整段文本到处捞十六进制」，把一段混合日志粘进来时，
    别的模块的十六进制也会被吃进 initcode，而且很难发现。
    """
    rows = []
    for lineno, code, raw in _strip_comments(text):
        line = code.strip()
        if line and prefix_re.match(line):
            rows.append((lineno, line, raw.strip()))
    return rows


def _byte_text(value):
    """把 0x1a / 1A / 1a 统一成 0x1a；不是合法字节（0..0xff）时返回 None。"""
    try:
        number = int(str(value).strip(), 16)
    except (TypeError, ValueError):
        return None
    if not 0 <= number <= 0xff:
        return None
    return "0x{:02x}".format(number)


def _initcode_row(command, params):
    """「DCS 命令 + 参数」→ 一行 initcode 字节。正向 4 种格式共用。"""
    payload = [command] + list(params)
    count = len(payload)
    if count <= 1:
        prefix = "0x05,0x78,0x00"
    elif count == 2:
        prefix = "0x15,0x00,0x00"
    else:
        prefix = "0x39,0x00,0x00"
    return ",".join([prefix, "0x{:02x}".format(count)] + payload) + ","


def _instruction_re(names):
    """GEN_WR 那类「指令名(...)」的行首前缀（指令名可在界面上改）。"""
    return re.compile(
        r"^(?:" + "|".join(re.escape(name) for name in names) + r")\s*\(",
        re.IGNORECASE)


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


def parse_mipi_write(text):
    """把 mipi.write 命令清单转成 initcode 条目（**保留行首的块类型**）。

    mipi.write 的写法和 initcode 的对应关系是一行对一条：

        mipi.write 0x39 0xD7 0x10 0x0C 0x36 0x19 0x90 0x90
        ↓
        0x39,0x00,0x00,0x07,0xd7,0x10,0x0c,0x36,0x19,0x90,0x90,

    即「块类型」直接当包头首字节，负载长度 = 负载字节数，负载第一个字节就是
    DCS 命令（0xD7），其余是参数；包头后面两个字节填 0x00。

    认这几种写法（大小写、逗号/空格混用都行）：

        mipi.write 0x39 0xD7 0x10 0x0C
        mipi.write 0x39,0xD7,0x10,0x0C
        MIPI.WRITE 0x29 0x75 0x03 0x04
        mipi_write 0x29 0x75 0x03 0x04

    **过滤规则**：只有以 mipi.write 开头的行才解析。其余内容——# 注释、// 注释、
    空行、日志里别的前缀（如 `[ 12.3 ] mipi.write …`）、裸字节序列——一律直接
    丢弃，不解析也不报错。前缀匹配上但内容残缺的行才会记进 .error。

    解析失败不抛异常：能认的行照样返回，问题写进返回值的 .error。
    """
    result = ParseResult()
    if not text or not text.strip():
        return result

    problems = []
    entries = []
    for lineno, line, raw in _prefix_lines(text, _MIPI_WRITE_RE):
        body = line[_MIPI_WRITE_RE.match(line).end():]   # 去掉前缀，剩下字节
        values = [value & 0xff for value in _scan_line(body)]
        if not values:
            problems.append(
                "第 {} 行只有 mipi.write 前缀，后面没有字节。".format(lineno))
            continue

        header, payload = values[0], values[1:]
        if not payload:
            problems.append(
                "第 {} 行只有块类型 0x{:02x}，后面没有 DCS 命令。".format(
                    lineno, header))
            continue
        if len(payload) > 0xff:
            problems.append(
                "第 {} 行负载 {} 字节，超过长度字节上限 255，无法表示。".format(
                    lineno, len(payload)))
            continue

        fixed = FIXED_PAYLOAD.get(header)
        if fixed is not None and fixed != len(payload):
            problems.append(
                "第 {} 行块类型 0x{:02x} 固定带 {} 个负载字节，实际给了 {} 个。".format(
                    lineno, header, fixed, len(payload)))

        entries.append(InitcodeEntry(
            kind_of(header), payload[0], payload[1:],
            raw=raw, header=header))

    result.extend(entries)
    result.error = "\n".join(problems)
    return result


def to_dcs(entry):
    """把一条解析结果写回 initcode 字节行。

    写法与正向生成完全一致（逗号分隔、小写两位十六进制、行尾带逗号）：
        0x39,0x00,0x00,0x05,0x1a,0x2b,0x3c,0x4d,0x5e,

    块类型优先用条目自己带的 header：mipi.write 里的 0x29（Generic long write）
    和 0x39（DCS long write）负载长度可能完全一样，按长度重推会把 0x29 悄悄
    改写成 0x39，下发到屏体的行为可能不同。只有拿不到 header（例如直接传
    三元组）时才退回按负载长度推断。
    """
    payload = [entry[1]] + list(entry[2])
    count = len(payload)
    header = getattr(entry, "header", 0) or 0
    if not header:
        header = 0x05 if count <= 1 else (0x15 if count == 2 else 0x39)
    # 包头后两个字节只是填充：沿用正向生成的老规矩（1 字节负载写 0x78,0x00）
    values = [header, 0x78 if count <= 1 else 0x00, 0x00, count] + payload
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
            "WriteData(0x2b)\nWriteData(0x3c)\nWriteData(0x4d)\nWriteData(0x5e)\n"
            "**********\n只解析以 WriteAddr( / WriteData( 开头的行，其余自动丢弃")
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
        self.radioButton_5.clicked.connect(self.select_command)

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
                "WriteData(0x2b)\nWriteData(0x3c)\nWriteData(0x4d)\nWriteData(0x5e)\n"
                "**********\n只解析以 WriteAddr( / WriteData( 开头的行，"
                "其余（# 与 // 注释、空行、别的日志）自动丢弃")
            self.pushButton.clicked.connect(self.initcodebuilder_1)
        elif self.radioButton_2.isChecked():
            self.format_hint.setText("当前格式: Write(Command)")
            self.textEdit.setPlaceholderText(
                "Enter hex Write(Command,0xxx)strings\n**********\nWrite(Command,0x1a);\n"
                "Write(Parameter,0x2b);\nWrite(Parameter,0x3c);\nWrite(Parameter,0x4d);\n"
                "Write(Parameter,0x5e);\n"
                "**********\n只解析以 Write(Command, / Write(Parameter, 开头的行，"
                "其余自动丢弃")
            self.pushButton.clicked.connect(self.initcodebuilder_2)
        elif self.radioButton_3.isChecked():
            self.format_hint.setText("当前格式: Rxx")
            self.textEdit.setPlaceholderText(
                "Enter hex Rxx strings\n**********\nR1a 2b 3c 4d 5e\n"
                "**********\n只解析以 R + 十六进制字节开头的行，其余自动丢弃")
            self.pushButton.clicked.connect(self.initcodebuilder_3)
        elif self.radioButton_4.isChecked():
            self.format_hint.setText("当前格式: GEN_WR")
            self.textEdit.setPlaceholderText(
                "Enter hex GEN_WR strings\n**********\nGEN_WR(0x1a,0x2b,0x3c,0x4d,0x5e);\n"
                "**********\n只解析以右侧指令名（默认 GEN_WR）+ ( 开头的行，其余自动丢弃")
            self.pushButton.clicked.connect(self.initcodebuilder_4)
        elif self.radioButton_5.isChecked():
            self.format_hint.setText("当前格式: mipi.write")
            self.textEdit.setPlaceholderText(
                "Enter mipi.write strings\n**********\n"
                "mipi.write 0x39 0xD7 0x10 0x0C 0x36 0x19 0x90 0x90\n"
                "mipi.write 0x29 0x75 0x03 0x04\n**********\n"
                "只解析以 mipi.write 开头的行；# 与 // 注释、空行、别的前缀"
                "（含日志时间戳）一律丢弃。行首那个字节是块类型，原样保留")
            self.pushButton.clicked.connect(self.initcodebuilder_5)

    def initcodebuilder_1(self):
        """处理 WriteAddr / WriteData 格式。

        只解析以 WriteAddr( / WriteData( 开头的行；# 注释、// 注释、空行、
        别的日志片段一律直接丢弃。
        """
        output_rows = []
        current = None
        values = []

        def flush():
            if current is not None:
                output_rows.append(_initcode_row(current, values))

        for _lineno, line, _raw in _prefix_lines(
                self.textEdit.toPlainText(), _PREFIX_WRITEADDR):
            name, _, rest = line.partition("(")
            value = _byte_text(rest.split(")")[0])
            if value is None:
                continue
            if name.strip().lower() == "writeaddr":
                flush()
                current, values = value, []
            elif current is not None:          # WriteData 要跟在 WriteAddr 后面
                values.append(value)
        flush()
        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_2(self):
        """处理 Write(Command) / Write(Parameter) 格式。

        只解析以 Write(Command, / Write(Parameter, 开头的行，其余直接丢弃。
        """
        output_rows = []
        current = None
        values = []

        def flush():
            if current is not None:
                output_rows.append(_initcode_row(current, values))

        for _lineno, line, _raw in _prefix_lines(
                self.textEdit.toPlainText(), _PREFIX_WRITE_COMMAND):
            kind, _, rest = line.split("(", 1)[1].partition(",")
            value = _byte_text(rest.split(")")[0])
            if value is None:
                continue
            if kind.strip().lower() == "command":
                flush()
                current, values = value, []
            elif current is not None:          # Parameter 要跟在 Command 后面
                values.append(value)
        flush()
        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_3(self):
        """处理 Rxx 格式。

        只解析以 R + 1~2 位十六进制字节开头的行（R1a 2b 3c）；其余直接丢弃。
        以前是先把全文的 "R" 全删掉再逐行切，粘一段混合文本时会连别的字母一起
        吃进来，现在按行首前缀卡住。
        """
        output_rows = []
        for _lineno, line, _raw in _prefix_lines(
                self.textEdit.toPlainText(), _PREFIX_RXX):
            values = [_byte_text(token) for token in line[1:].split()]
            values = [value for value in values if value is not None]
            if not values:
                continue
            output_rows.append(_initcode_row(values[0], values[1:]))
        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_4(self):
        """处理 GEN_WR 等格式。

        指令名可在右侧输入框里改（逗号分隔多个，默认 GEN_WR）。只解析以这些
        指令名 + "(" 开头的行，其余直接丢弃——以前没匹配上的行会原样透传到
        输出里，粘一段混合文本时输出会跟着脏。
        """
        names = [name.strip() for name in
                 (self.lineEdit.text() or "GEN_WR").split(",") if name.strip()]
        if not names:
            names = ["GEN_WR"]
        output_rows = []
        for _lineno, line, _raw in _prefix_lines(
                self.textEdit.toPlainText(), _instruction_re(names)):
            body = line.split("(", 1)[1].split(")", 1)[0]
            values = [_byte_text(token) for token in body.split(",")]
            values = [value for value in values if value is not None]
            if not values:
                continue
            output_rows.append(_initcode_row(values[0], values[1:]))
        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_5(self):
        """处理 mipi.write 格式：一行一条命令 → 一条 initcode。

        行首的块类型原样保留（0x39 / 0x29 / 0x05 / 0x15 …），不按负载长度重推：
        0x29 和 0x39 的负载长度可能一样，但包语义不同，重推会改掉下发行为。
        有问题的行不会静默丢掉——条数照样生成，问题写在格式提示里。
        """
        result = parse_mipi_write(self.textEdit.toPlainText())
        entries = list(result)
        self.textEdit_2.setPlainText("\n".join(to_dcs(entry) for entry in entries))

        if not entries:
            first = result.error.splitlines()[0] if result.error else \
                "没有以 mipi.write 开头的行（其余内容已丢弃）"
            self.format_hint.setText("当前格式: mipi.write · " + first)
            return

        if result.error:
            problems = result.error.splitlines()
            self.format_hint.setText(
                "当前格式: mipi.write · 已生成 {} 条，另有 {} 行有问题：{}".format(
                    len(entries), len(problems), problems[0]))
        else:
            self.format_hint.setText(
                "当前格式: mipi.write · 已生成 {} 条 initcode".format(len(entries)))
