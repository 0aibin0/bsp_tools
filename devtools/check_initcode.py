"""Initcode Builder 反向解析自查：不连真机、只跑逻辑。

覆盖：
1. 正向（四种输入格式）→ 反向解析 → 命令 / 参数一致，且 to_dcs 能原样写回
2. 反向 → format_as 四种风格 → 再喂回正向，字节序列一致
3. 带 // /* */ 注释、C 数组花括号、裸十六进制、adb dcs 写命令、反斜杠续行的输入
4. 长度字节不匹配 / 数据截断 / 尾部残缺时报错，且已认出的条目不被丢弃
5. 空输入、纯噪声输入不崩
6. 界面槽函数：解析清单、输出格式切换、复制结果
7. mipi.write 格式（第 5 种输入）：真实 10 条屏体点亮序列 → initcode，
   块类型 0x29 / 0x39 必须原样保留，往返解析后命令/参数/块类型一致
8. 五种输入格式都按**行首前缀**过滤：# 与 // 注释、空行、日志前缀、裸字节
   一律丢弃，只有匹配前缀的行参与解析

用法（仓库根目录）：
    $env:QT_QPA_FONTDIR="C:\\Windows\\Fonts"; .\\.venv\\Scripts\\python.exe devtools\\_check_initcode.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bsp_tools"))

from PyQt5.QtWidgets import QApplication                     # noqa: E402

import initcode_builder as icb                               # noqa: E402
from initcode_builder import (KIND_LONG, KIND_SHORT,         # noqa: E402
                              KIND_SHORT_1P, parse_initcode, format_as,
                              format_list, to_dcs, parse_mipi_write)

FAILURES = []
CHECKS = [0]


def check(label, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        FAILURES.append(label)


# ================= 正向输入样例（四种格式，每条都带 3 种包头） =================
FORWARD_CASES = {
    1: ("WriteAddr",
        "WriteAddr(0x1a)\nWriteData(0x2b)\nWriteData(0x3c)\nWriteData(0x4d)\n"
        "WriteData(0x5e)\nWriteAddr(0x2c)\nWriteAddr(0x3d)\nWriteData(0x4e)\n"),
    2: ("Write(Command)",
        "Write(Command,0x1a);\nWrite(Parameter,0x2b);\nWrite(Parameter,0x3c);\n"
        "Write(Parameter,0x4d);\nWrite(Parameter,0x5e);\nWrite(Command,0x2c);\n"
        "Write(Command,0x3d);\nWrite(Parameter,0x4e);\n"),
    3: ("Rxx", "R1a 2b 3c 4d 5e\nR2c\nR3d 4e\n"),
    4: ("GEN_WR", "GEN_WR(0x1a,0x2b,0x3c,0x4d,0x5e);\nGEN_WR(0x2c);\nGEN_WR(0x3d,0x4e);\n"),
}

# 期望的 initcode 字节行（正向生成结果 = 反向写回结果）
EXPECTED_LINES = [
    "0x39,0x00,0x00,0x05,0x1a,0x2b,0x3c,0x4d,0x5e,",
    "0x05,0x78,0x00,0x01,0x2c,",
    "0x15,0x00,0x00,0x02,0x3d,0x4e,",
]
EXPECTED_ENTRIES = [
    (KIND_LONG, 0x1a, [0x2b, 0x3c, 0x4d, 0x5e]),
    (KIND_SHORT, 0x2c, []),
    (KIND_SHORT_1P, 0x3d, [0x4e]),
]

# 风格 → 正向第几号生成函数（byte 风格本身就是正向的输出格式）
STYLE_TO_FORWARD = {"write": 2, "rxx": 3, "gen_wr": 4}

# mipi.write 真实样本（T820 屏体点亮序列，10 条）。第 8 条用 0x29
# （Generic long write），其余用 0x39（DCS long write）——这两者负载长度
# 可能一样，必须原样保留，不能按长度重推。
MIPI_SAMPLE = "\n".join([
    "mipi.write 0x39 0xD7 0x10 0x0C 0x36 0x19 0x90 0x90",
    "",
    "mipi.write 0x39 0xA3 0x40 0x03 0x80 0xFF 0x04 0x00 0x00 0x00 0x00 0x05 0x00 "
    "0x68 0x00 0x0A 0x00 0x05 0x05 0x00 0x00 0x00 0x00 0x46 0x00 0x00 0x02 0x6F "
    "0x12 0x00 0x05 0x00 0x00 0xFF",
    "",
    "mipi.write 0x39 0xA6 0x0E 0x00 0x04 0x44 0x35 0x00 0x38 0x00 0x78 0x78 0x00 "
    "0x04 0x44 0x36 0x00 0x37 0x00 0x78 0x78 0x02 0xC4 0x77 0x33 0x05 0x00 0x06 "
    "0x2F 0x5E 0x00 0xAC 0x11 0x32 0x06 0x00 0x00 0x2F 0x5E 0x00 0x00 0x06 0x00 "
    "0x00 0x00 0x00",
    "",
    "mipi.write 0x39 0xA7 0x19 0x19 0x00 0x64 0x00 0x07 0x16 0x41 0x02 0x08 0x07 "
    "0x78 0x78 0x00 0x64 0x00 0x25 0x34 0x03 0x04 0x06 0x05 0x78 0x78 0x00 0x64 "
    "0x40 0x4B 0x5A 0x00 0x00 0x02 0x01 0x78 0x78 0x00 0x24 0x00 0x69 0x78 0x00 "
    "0x00 0x00 0x00 0x78 0x78 0x00 0x44",
    "",
    "mipi.write 0x39 0xAC 0x12 0x10 0x0B 0x01 0x09 0x02 0x04 0x1B 0x06 0x02 0x19 "
    "0x1B 0x19 0x19 0x18 0x18 0x13 0x11 0x0A 0x03 0x08 0x00 0x04 0x1B 0x06 0x00 "
    "0x19 0x1B 0x19 0x1B 0x18 0x18 0xFF 0x99 0xFF 0x99 0x00",
    "",
    "mipi.write 0x39 0xAD 0xCC 0x00 0x46 0x00 0x06 0x5E 0x2F",
    "",
    "mipi.write 0x39 0xE8 0x30 0x07 0x00 0x94 0x94 0x9C 0x00 0xE2 0x04 0x00 0x00 "
    "0x00 0x00 0xEF",
    "",
    "mipi.write 0x29 0x75 0x03 0x04",
    "",
    "mipi.write 0x39 0xE7 0x8B 0x3C 0x00 0x0C 0xF0 0x5D 0x00 0x5D 0x00 0x5D 0x00 "
    "0x5D 0x00 0xFF 0x00 0x08 0x7B 0x00 0x00 0xC8 0x6A 0x5A 0x08 0x1A 0x3C 0x00 "
    "0x81 0x01 0x8C 0x01 0x7F 0xF0 0x22",
    "",
    "mipi.write 0x39 0xE9 0x33 0x7F 0x08 0x07 0x0A 0x6A 0x22 0x1A 0x33",
])

MIPI_EXPECTED_FIRST = "0x39,0x00,0x00,0x07,0xd7,0x10,0x0c,0x36,0x19,0x90,0x90,"
MIPI_EXPECTED_GENERIC = "0x29,0x00,0x00,0x03,0x75,0x03,0x04,"


def run_forward(page, index, text):
    """把 text 喂给正向的第 index 号格式，返回生成的 initcode 文本。"""
    radios = {1: page.radioButton, 2: page.radioButton_2,
              3: page.radioButton_3, 4: page.radioButton_4}
    radios[index].setChecked(True)
    page.select_command()
    page.textEdit.setPlainText(text)
    getattr(page, f"initcodebuilder_{index}")()
    return page.textEdit_2.toPlainText()


def same_entries(entry, expected):
    """(kind, cmd, params) 是否与期望一致。"""
    kind, cmd, params = entry
    return (kind, cmd, list(params)) == (expected[0], expected[1], list(expected[2]))


def main():
    app = QApplication([])
    page = icb.InitcodeBuilderPage()
    page.resize(1300, 720)
    page.show()
    app.processEvents()

    print("\n[1] 正向 → 反向：四种格式逐条比对命令与参数")
    for index in sorted(FORWARD_CASES):
        name, text = FORWARD_CASES[index]
        generated = run_forward(page, index, text)
        lines = [line for line in generated.split("\n") if line.strip()]
        check(f"{name}: 正向生成 3 条", lines == EXPECTED_LINES, generated)
        result = parse_initcode(generated)
        check(f"{name}: 反向解析无错误", result.ok, result.error)
        check(f"{name}: 反向解析条数一致", len(result) == len(EXPECTED_ENTRIES),
              str(list(result)))
        check(f"{name}: 命令与参数逐条一致",
              len(result) == len(EXPECTED_ENTRIES) and
              all(same_entries(e, x) for e, x in zip(result, EXPECTED_ENTRIES)),
              str([tuple(e) for e in result]))
        check(f"{name}: to_dcs 原样写回正向输出",
              [to_dcs(e) for e in result] == lines,
              str([to_dcs(e) for e in result]))
        check(f"{name}: 包头类型标注正确",
              [e.kind for e in result] == [x[0] for x in EXPECTED_ENTRIES],
              str([e.kind for e in result]))

    print("\n[2] 反向 → format_as → 再喂回正向：字节序列一致")
    entries = list(parse_initcode("\n".join(EXPECTED_LINES)))
    check("byte 风格等于原始字节行",
          format_as(entries, "byte") == "\n".join(EXPECTED_LINES),
          format_as(entries, "byte"))
    for style, forward_index in STYLE_TO_FORWARD.items():
        text = format_as(entries, style)
        check(f"{style} 风格首行可读", text.split("\n")[0] != "", text.split("\n")[0])
        regenerated = run_forward(page, forward_index, text)
        check(f"{style} 风格回填正向结果一致",
              regenerated == "\n".join(EXPECTED_LINES), regenerated)
    check("未知风格退回字节序列",
          format_as(entries, "没这个风格") == "\n".join(EXPECTED_LINES))
    check("STYLE_LABELS 覆盖四种风格",
          [key for key, _label in icb.STYLE_LABELS] == ["byte", "write", "rxx", "gen_wr"],
          str(icb.STYLE_LABELS))
    check("界面下拉框与 STYLE_LABELS 顺序一致",
          [page.combo_reverse_style.itemData(i)
           for i in range(page.combo_reverse_style.count())] ==
          [key for key, _label in icb.STYLE_LABELS],
          str([page.combo_reverse_style.itemData(i)
               for i in range(page.combo_reverse_style.count())]))

    print("\n[3] 噪声：注释 / C 数组花括号 / 反斜杠续行")
    noisy = (
        "/* lk 源码里的 initcode，块注释里的 0x99,0x99 应当被忽略\n"
        "   这一行还没结束 */\n"
        "static unsigned char panel_init[] = {\n"
        "    0x39, 0x00, 0x00, 0x05, 0x1a, 0x2b, 0x3c, 0x4d, 0x5e,   // 5 字节\n"
        "    0x05,0x00,0x00,0x01,0x2c,                                /* 短包写 */\n"
        "};\n"
        'const char *cmd = "adb shell \\\n'
        " echo 0x15,0x00,0x00,0x02,0x3d,0x4e,\";\n"
    )
    result = parse_initcode(noisy)
    check("带注释与花括号：无错误", result.ok, result.error)
    check("带注释与花括号：3 条", len(result) == 3, str(list(result)))
    check("带注释与花括号：注释里的 0x99 没被吃进来",
          len(result) == 3 and all(0x99 not in list(e.params) + [e.cmd] for e in result),
          str([tuple(e) for e in result]))
    check("带注释与花括号：命令 / 参数正确",
          len(result) == 3 and all(same_entries(e, x)
                                   for e, x in zip(result, EXPECTED_ENTRIES)),
          str([tuple(e) for e in result]))

    print("\n[4] 裸十六进制 / 大写 0X / \\x 转义 / adb 写命令")
    bare = parse_initcode("39 00 00 05 1a 2b 3c 4d 5e\n05 00 00 01 2c\n15 00 00 02 3d 4e\n")
    check("裸十六进制：3 条且命令一致",
          bare.ok and len(bare) == 3 and
          all(same_entries(e, x) for e, x in zip(bare, EXPECTED_ENTRIES)),
          "{} / {}".format(bare.error, [tuple(e) for e in bare]))
    upper = parse_initcode("0X39,0X00,0X00,0X05,0X1A,0X2B,0X3C,0X4D,0X5E,")
    check("大写 0X：解析出命令 0x1a 与 4 个参数",
          upper.ok and len(upper) == 1 and same_entries(upper[0], EXPECTED_ENTRIES[0]),
          "{} / {}".format(upper.error, [tuple(e) for e in upper]))
    escaped = parse_initcode(r'"\x39\x00\x00\x05\x1a\x2b\x3c\x4d\x5e"')
    check(r"\x 转义字符串：解析出命令 0x1a 与 4 个参数",
          escaped.ok and len(escaped) == 1 and same_entries(escaped[0], EXPECTED_ENTRIES[0]),
          "{} / {}".format(escaped.error, [tuple(e) for e in escaped]))
    adb = parse_initcode(
        'adb shell "echo 39 00 00 05 1a 2b 3c 4d 5e > /sys/class/graphics/fb0/dcs"\n')
    check("adb dcs 写命令：只取到 1 条、命令 0x1a",
          adb.ok and len(adb) == 1 and same_entries(adb[0], EXPECTED_ENTRIES[0]),
          "{} / {}".format(adb.error, [tuple(e) for e in adb]))

    print("\n[5] 长度字节对不上 / 数据截断 / 尾部残缺 必须报错")
    truncated = parse_initcode("0x39,0x00,0x00,0x09,0x1a,0x2b,")
    check("长度 9 但只剩 2 字节：报错", bool(truncated.error), truncated.error)
    check("长度 9 但只剩 2 字节：不产出半条数据", len(truncated) == 0, str(list(truncated)))
    mismatch = parse_initcode("0x05,0x78,0x00,0x03,0x1a,0x2b,0x3c,")
    check("0x05 短包带 3 字节负载：报错", "0x05" in mismatch.error, mismatch.error)
    check("短包长度不符仍保留已认出的条目",
          len(mismatch) == 1 and mismatch[0].cmd == 0x1a and mismatch[0].params == [0x2b, 0x3c],
          str([tuple(e) for e in mismatch]))
    tail = parse_initcode("\n".join(EXPECTED_LINES[:1]) + "\n0x15,0x00\n")
    check("尾部残缺：报错且保留前面的条目",
          bool(tail.error) and len(tail) == 1 and same_entries(tail[0], EXPECTED_ENTRIES[0]),
          "{} / {}".format(tail.error, [tuple(e) for e in tail]))
    zero = parse_initcode("0x39,0x00,0x00,0x00,")
    check("长度字节为 0：报错而不是静默丢弃", bool(zero.error), zero.error)

    print("\n[6] 空输入 / 纯噪声不崩")
    for label, text in (("空字符串", ""), ("只有空白", "   \n\t  \n"),
                        ("None", None), ("只有注释", "// 什么也没有\n/* 也没有 */\n")):
        try:
            empty = parse_initcode(text)
            check(f"{label}：不抛异常且没有条目", len(empty) == 0,
                  "{} / {}".format(empty.error, list(empty)))
        except Exception as exc:                                  # noqa: BLE001
            check(f"{label}：不抛异常且没有条目", False, repr(exc))
    check("空输入不算错误（界面自己给提示）", parse_initcode("").error == "")

    print("\n[7] 清单文本与统计")
    listing = format_list(entries)
    first = listing.split("\n")[0]
    check("清单首行形状：第 1 条 · 类型 · 命令 · 参数 m 个 · 原始行",
          first.startswith("第 1 条 · ") and "命令 0x1a" in first and
          "参数 4 个" in first and "原始行 0x39,0x00,0x00,0x05,0x1a,0x2b,0x3c,0x4d,0x5e," in first,
          first)
    check("清单有 3 行", len(listing.split("\n")) == 3, listing)
    check("统计文本含条数", "共 3 条" in icb.summarize_entries(entries),
          icb.summarize_entries(entries))
    check("kind/cmd/params 可三元拆包",
          [tuple(row) == (row.kind, row.cmd, row.params) for row in entries] == [True] * 3)

    print("\n[8] 界面槽函数：解析 / 切换格式 / 复制")
    page.reverse_input.setPlainText("\n".join(EXPECTED_LINES))
    page.on_reverse_parse()
    check("解析按钮：清单 3 行", len(page.reverse_list.toPlainText().split("\n")) == 3,
          page.reverse_list.toPlainText())
    check("解析按钮：输出等于 byte 风格",
          page.reverse_output.toPlainText() == "\n".join(EXPECTED_LINES),
          page.reverse_output.toPlainText())
    check("解析按钮：状态提示含统计", "共 3 条" in page.reverse_status.text(),
          page.reverse_status.text())
    page.combo_reverse_style.setCurrentIndex(2)            # rxx
    app.processEvents()
    check("切换输出格式：输出变成 Rxx",
          page.reverse_output.toPlainText().split("\n")[0] == "R1a 2b 3c 4d 5e",
          page.reverse_output.toPlainText())
    page.on_output_copy()
    check("复制输出：剪贴板内容与输出框一致",
          QApplication.clipboard().text() == page.reverse_output.toPlainText(),
          QApplication.clipboard().text()[:60])
    page.on_reverse_copy()
    check("复制结果：剪贴板内容与清单一致",
          QApplication.clipboard().text() == page.reverse_list.toPlainText())
    page.reverse_input.setPlainText("0x39,0x00,0x00,0x09,0x1a,")
    page.on_reverse_parse()
    check("界面：报错不抛异常，错误写进清单区",
          "长度字节" in page.reverse_list.toPlainText() and
          page.reverse_output.toPlainText() == "",
          page.reverse_list.toPlainText())
    page.reverse_input.setPlainText("")
    page.on_reverse_parse()
    check("界面：空输入后输出框被清空", page.reverse_output.toPlainText() == "",
          page.reverse_output.toPlainText())

    print("\n[9] mipi.write 格式：一行一条命令 → 一条 initcode")
    mipi = parse_mipi_write(MIPI_SAMPLE)
    check("真实样本：10 条且无错误",
          len(mipi) == 10 and mipi.ok, "{} / {}".format(len(mipi), mipi.error))
    mipi_lines = [to_dcs(entry) for entry in mipi]
    check("真实样本：首条字节行与手算一致",
          mipi_lines[0] == MIPI_EXPECTED_FIRST, mipi_lines[0])
    check("真实样本：首条命令 0xD7 + 6 个参数",
          mipi[0].cmd == 0xD7 and
          list(mipi[0].params) == [0x10, 0x0C, 0x36, 0x19, 0x90, 0x90],
          str(tuple(mipi[0])))
    check("真实样本：块类型 0x29 未被改写成 0x39",
           mipi[7].header == 0x29 and mipi_lines[7] == MIPI_EXPECTED_GENERIC,
          "{} / {}".format(hex(mipi[7].header), mipi_lines[7]))
    check("真实样本：其余 9 条仍是 0x39",
          [entry.header for i, entry in enumerate(mipi) if i != 7] == [0x39] * 9,
          str([hex(entry.header) for entry in mipi]))
    check("真实样本：负载长度＝1＋参数个数",
          all(len(entry.params) + 1 ==
              int(mipi_lines[i].split(",")[3], 16)
              for i, entry in enumerate(mipi)),
          str([mipi_lines[i].split(",")[3] for i in range(len(mipi))]))

    print("\n[10] mipi.write 往返：生成 → 反向解析 → 命令 / 参数 / 块类型一致")
    mipi_round = parse_initcode("\n".join(mipi_lines))
    check("往返：反向解析无错误", mipi_round.ok, mipi_round.error)
    check("往返：条数一致", len(mipi_round) == len(mipi),
          "{} vs {}".format(len(mipi_round), len(mipi)))
    check("往返：每条命令 / 参数 / 块类型都一致",
          len(mipi_round) == len(mipi) and all(
              (a.cmd, list(a.params), a.header) == (b.cmd, list(b.params), b.header)
              for a, b in zip(mipi, mipi_round)),
          str([(hex(a.header), a.cmd) for a in mipi]))

    print("\n[11] 行首过滤：只解析以 mipi.write 开头的行，其余全部丢弃")
    variants = parse_mipi_write(
        "# 注释行里的 mipi.write 0x39 0x00 应被丢弃\n"
        "// 注释行里的 mipi.write 0x39 0x01 也丢弃\n"
        "\n"
        "[  12.345 ] mipi.write 0x39 0xFF 0xFE\n"
        "MIPI.WRITE 0x39,0xD7,0x10\n"
        "mipi_write 0x29 0x75 0x03\n"
        "0x15 0x51 0x0A\n"
        "任意中文说明 mipi.write 0x39 0xCC\n"
        "   \t  \n"
        "mipi.write 0x39 0xE9  /* 块注释也忽略 */\n")
    check("过滤：# / // / 日志前缀 / 裸字节都丢弃，只剩 3 条",
          len(variants) == 3 and variants.ok,
          "{} / {}".format(len(variants), variants.error))
    check("过滤：命令依次为 d7 / 75 / e9",
          [entry.cmd for entry in variants] == [0xD7, 0x75, 0xE9],
          str([hex(entry.cmd) for entry in variants]))
    check("过滤：大写前缀与下划线写法都认",
          variants[0].header == 0x39 and variants[1].header == 0x29,
          str([hex(entry.header) for entry in variants]))
    check("过滤：注释与无关行里的字节没被吃进来",
          variants[0].params == [0x10] and variants[2].params == [],
          str([list(entry.params) for entry in variants]))
    nothing = parse_mipi_write("# 只有注释\n// 还是注释\njunk 0x11\n0x39 0xD7\n")
    check("过滤：一行都不匹配时输出为空且不报错",
          len(nothing) == 0 and nothing.error == "",
          "{} / {}".format(len(nothing), nothing.error))

    print("\n[12] mipi.write 异常输入：前缀对上但内容残缺才报错")
    for label, text, expect in (
            ("只有块类型", "mipi.write 0x39\n", "没有 DCS 命令"),
            ("只有前缀", "mipi.write\n", "后面没有字节"),
            ("0x05 却给 3 字节", "mipi.write 0x05 0x1a 0x2b 0x3c\n", "0x05"),
    ):
        try:
            bad = parse_mipi_write(text)
            check("{}：报错且信息可读".format(label),
                  bool(bad.error) and expect in bad.error, bad.error)
        except Exception as exc:                                  # noqa: BLE001
            check("{}：报错且信息可读".format(label), False, repr(exc))
    shape = parse_mipi_write("mipi.write 0x05 0x1a 0x2b 0x3c\n")
    check("块类型与负载不匹配时仍保留条目（不静默丢弃）",
          len(shape) == 1 and shape[0].cmd == 0x1a, str([tuple(e) for e in shape]))
    check("没有前缀的裸文字：静默丢弃，不算错误",
          len(parse_mipi_write("这里没有十六进制\n")) == 0 and
          parse_mipi_write("这里没有十六进制\n").error == "")
    check("空输入不算错误", parse_mipi_write("").error == "")
    check("只有空行不算错误", parse_mipi_write("\n\n  \n").error == "")

    print("\n[13] mipi.write 界面：选格式 → Build → 输出")
    page.radioButton_5.setChecked(True)
    page.select_command()
    check("选中 mipi.write 后格式提示正确",
          "mipi.write" in page.format_hint.text(), page.format_hint.text())
    page.textEdit.setPlainText(MIPI_SAMPLE)
    page.initcodebuilder_5()
    ui_lines = [line for line in page.textEdit_2.toPlainText().split("\n") if line]
    check("界面：输出 10 行 initcode", len(ui_lines) == 10, str(len(ui_lines)))
    check("界面：首行与纯函数结果一致", ui_lines[0] == MIPI_EXPECTED_FIRST, ui_lines[0])
    check("界面：格式提示报出条数",
          "10" in page.format_hint.text(), page.format_hint.text())
    page.textEdit.setPlainText("mipi.write 0x39\n")
    page.initcodebuilder_5()
    check("界面：全部行都有问题时不崩、输出为空",
          page.textEdit_2.toPlainText() == "" and
          "没有 DCS 命令" in page.format_hint.text(),
          "{} / {}".format(page.textEdit_2.toPlainText(), page.format_hint.text()))
    page.textEdit.setPlainText("")
    page.initcodebuilder_5()
    check("界面：空输入不崩", page.textEdit_2.toPlainText() == "",
          page.textEdit_2.toPlainText())

    print("\n[14] 其他 4 种格式同样按行首前缀过滤")
    FILTERED = {
        1: ("WriteAddr",
            "# WriteAddr(0x99)\nWriteAddr(0x1a)\nWriteData(0x2b)\n"
            "junk 0x77\n// WriteAddr(0x88)\nWriteData(0x3c)\n",
            ["0x39,0x00,0x00,0x03,0x1a,0x2b,0x3c,"]),
        2: ("Write(Command)",
            "// Write(Command,0x99);\nWrite(Command,0x1a);\n"
            "Write(Parameter,0x2b);\nother text 0x77\nWrite(Parameter,0x3c);\n",
            ["0x39,0x00,0x00,0x03,0x1a,0x2b,0x3c,"]),
        3: ("Rxx",
            "# R99 88\nR1a 2b 3c\nhello R77\nR2c\n",
            ["0x39,0x00,0x00,0x03,0x1a,0x2b,0x3c,",
             "0x05,0x78,0x00,0x01,0x2c,"]),
        4: ("GEN_WR",
            "// GEN_WR(0x99);\nGEN_WR(0x1a,0x2b,0x3c);\nnoise 0x77\nGEN_WR(0x2c);\n",
            ["0x39,0x00,0x00,0x03,0x1a,0x2b,0x3c,",
             "0x05,0x78,0x00,0x01,0x2c,"]),
    }
    for index, (name, text, expected_rows) in FILTERED.items():
        generated = run_forward(page, index, text)
        rows = [line for line in generated.split("\n") if line.strip()]
        check("{}：只保留匹配行，注释与无关行丢弃".format(name),
              rows == expected_rows, "{} vs {}".format(rows, expected_rows))
    for index, name in ((1, "WriteAddr"), (2, "Write(Command)"),
                        (3, "Rxx"), (4, "GEN_WR")):
        generated = run_forward(page, index, "完全是垃圾\n0x77 0x88\n随手说明\n")
        check("{}：全部不匹配时输出为空".format(name), generated == "", generated)

    page.close()
    app.processEvents()

    print("\n" + "=" * 46)
    if FAILURES:
        print(f"{len(FAILURES)}/{CHECKS[0]} 项失败：")
        for name in FAILURES:
            print("  -", name)
        return 1
    print(f"全部通过（{CHECKS[0]} 项检查）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
