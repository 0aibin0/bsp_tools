"""转换工具：LK ↔ Kernel 互转 + LK → BAT + UNISOC → QCOM，合并成一页。

原先这些是独立页面（左侧菜单各占一行），但它们**界面结构完全一致**
——左边输入、右边只读输出、底部 Convert / Clear / Copy，
只是转换函数不同。各占一行会把侧边栏撑得很长。

合并后：顶部一排「转换方向」单选，下面仍是同一套输入/输出布局；
切换方向只换标题、占位符和按下 Convert 时调用的函数。

转换算法：
- LK → Kernel：去掉 0x 前缀、逗号换空格
- Kernel → LK：空格切分、加 0x 前缀、逗号分隔
- LK → BAT：取每行第 5 个字段起，拼成 adb shell echo 写 dcs_write 节点
- UNISOC → QCOM：4 字节头（dtype + 填充 + 长度）+ 负载 → 7 字节头 QCOM 包

UNISOC 的 kernel 格式（本工具里 Kernel 就是它）：

    15 00 00 02 03 01
    39 00 00 05 2A 00 00 04 37

即 `dtype | 0x00 0x00 | payload_len | payload...`，长度是**负载字节数**
（不含前 4 字节头）。QCOM 每包 7 字节头：

    dtype | last | vc | ack | post_wait_ms | tx_len_hi | tx_len_lo | payload

所以转换就是把 4 字节头换成 7 字节头，payload 原样搬过去。
"""

from PyQt5.QtWidgets import QButtonGroup, QHBoxLayout, QRadioButton, QFrame

import theme
import ui_widgets as W
from base_tool_page import BaseToolPage
import ui_transform

# (key, 标题, 副标题, 输入占位符, 输出占位符, Convert 按钮文字)
DIRECTIONS = (
    ("lk2kernel", "LK → Kernel", "LK 十六进制序列转内核格式",
     "Enter lk code (e.g. 0x1a,0x2b,0x3c,0x4d)",
     "generate kernel code (e.g. 1a 2b 3c 4d)",
     "Convert"),
    ("kernel2lk", "Kernel → LK", "内核十六进制序列转 LK 格式",
     "Enter kernel code (e.g. 1a 2b 3c 4d)",
     "generate lk code (e.g. 0x1a,0x2b,0x3c,0x4d)",
     "Convert"),
    ("lk2bat", "LK → BAT", "生成 DCS 写入批处理脚本",
     "Enter lk initcode (e.g. 0x--,0x--,0x--,0x--,0x--)",
     "generate bat code \n(e.g. adb shell echo \"0x01 > /sys/class/display/dsi0/dcs_write\")",
     "Convert"),
    # 待实现：UNISOC kernel 格式 → QCOM kernel 格式
    ("unisoc2qcom", "UNISOC → QCOM", "UNISOC 平台 kernel 命令集转 QCOM 平台格式",
     "Enter UNISOC kernel code",
     "generate QCOM kernel code",
     "Convert"),
)

#: LK → BAT 里写节点的固定节点路径（与原实现保持一致）
BAT_NODE = "/sys/class/display/dsi0/dcs_write"

#: UNISOC kernel 包头字节数：dtype + 2 字节填充 + 1 字节长度
UNISOC_HEADER = 4
#: QCOM 包头字节数：dtype + last + vc + ack + post_wait + tx_len(2)
QCOM_HEADER = 7


def _hex_byte(token):
    """'0x39' / '39' / '0X39' → int；非法返回 None。"""
    text = str(token).strip()
    if text.lower().startswith("0x"):
        text = text[2:]
    if not text or len(text) > 2:
        return None
    try:
        value = int(text, 16)
    except ValueError:
        return None
    return value if 0 <= value <= 0xFF else None


def unisoc_to_qcom(text, default_wait=0):
    """UNISOC kernel 命令集 → QCOM mdss-dsi-on-command 数组。

    输入每行是一个包：`dtype pad pad len payload...`（空格分隔）。
    输出每行一包：`dtype last vc ack wait tx_hi tx_lo payload...`，
    只有**最后一行** last=1（与真实 QCOM 配置一致）。

    **输出风格跟随输入**：输入写了 `0x` 就输出 `0x`，输入是裸十六进制
    （`15 00 00 02 03 01`）就输出裸十六进制——贴进 DTS 时不用再手改一遍。

    返回 (输出行列表, 问题列表)。问题非空时该行不产出。
    """
    rows = []
    problems = []
    use_prefix = None          # None = 还没判断；True/False = 跟随第一行输入
    for lineno, raw in enumerate((text or "").splitlines(), 1):
        line = raw.split("#")[0].split("//")[0].strip()
        if not line:
            continue
        tokens = line.replace(",", " ").split()
        if use_prefix is None and tokens:
            use_prefix = any(t.lower().startswith("0x") for t in tokens)
        values = []
        bad = None
        for token in tokens:
            value = _hex_byte(token)
            if value is None:
                bad = token
                break
            values.append(value)
        if bad is not None:
            problems.append("第 {} 行有非法字节 {}".format(lineno, bad))
            continue
        if len(values) < UNISOC_HEADER:
            problems.append(
                "第 {} 行只有 {} 字节，凑不满 {} 字节包头".format(
                    lineno, len(values), UNISOC_HEADER))
            continue

        dtype = values[0]
        length = values[3]
        payload = values[UNISOC_HEADER:]
        if len(payload) != length:
            problems.append(
                "第 {} 行声明长度 {}，实际有 {} 字节负载".format(
                    lineno, length, len(payload)))
            continue
        if length > 0xFF:
            problems.append("第 {} 行负载超过 255 字节".format(lineno))
            continue

        rows.append({
            "dtype": dtype,
            "wait": default_wait & 0xFF,
            "payload": payload,
        })

    if not rows:
        return [], problems

    # 输入里一个带 0x 的都没有 → 输出也不带
    template = "0x{:02x}" if use_prefix else "{:02x}"

    lines = []
    for index, row in enumerate(rows):
        last = 1 if index == len(rows) - 1 else 0
        length = len(row["payload"])
        packet = [row["dtype"], last, 0x00, 0x00, row["wait"],
                  (length >> 8) & 0xFF, length & 0xFF] + row["payload"]
        lines.append(" ".join(template.format(v) for v in packet))
    return lines, problems


class TransformPage(BaseToolPage):
    """转换工具页（三个转换方向合并）。"""

    def __init__(self, parent=None):
        super(TransformPage, self).__init__(parent)
        self._direction = DIRECTIONS[0][0]
        self._build_ui()
        self.select_direction(self._direction)

    # ================= 界面 =================

    def _build_ui(self):
        # 复用原转换页的输入/输出/按钮布局（控件名不变：textEdit / textEdit_2 …）
        widgets = ui_transform.build_transform_ui(
            self, input_title="输入", output_title="输出")
        self.textEdit = widgets["textEdit"]
        self.textEdit_2 = widgets["textEdit_2"]
        self.pushButton = widgets["pushButton"]
        self.pushButton_clear = widgets["pushButton_clear"]
        self.pushButton_copy = widgets["pushButton_copy"]

        # build_transform_ui 已经把「输入/输出」放在 grid 第 0 行、「按钮」放第 1 行。
        # 不能直接 addLayout(..., 0, 0) —— 那会和新行**重叠**在同一格。必须先用
        # takeAt 把已有项摘出来，整体下移一行，再把方向行插到最上面。
        grid = self.layout()
        existing = []
        while grid.count():
            existing.append(grid.takeAt(0))
        for row, item in enumerate(existing, start=1):
            if item.layout() is not None:
                grid.addLayout(item.layout(), row, 0, 1, 1)
            elif item.widget() is not None:
                grid.addWidget(item.widget(), row, 0, 1, 1)
        grid.addLayout(self._build_direction_row(), 0, 0, 1, 1)

        self.pushButton.clicked.connect(self.convert)
        self.pushButton_clear.clicked.connect(self.on_clear)
        self.pushButton_copy.clicked.connect(self.on_copy)

    def _build_direction_row(self):
        """转换方向选择行（三个单选 + 当前方向说明）。"""
        row = QHBoxLayout()
        row.setSpacing(10)

        label = W.field_label("转换方向", self)
        row.addWidget(label)

        self.direction_group = QButtonGroup(self)
        self.direction_group.setExclusive(True)
        self._radios = {}
        for key, title, _sub, _in, _out, _btn in DIRECTIONS:
            radio = QRadioButton(title, self)
            radio.setMinimumHeight(28)
            radio.toggled.connect(
                lambda checked, k=key: checked and self.select_direction(k))
            self.direction_group.addButton(radio)
            self._radios[key] = radio
            row.addWidget(radio)

        row.addSpacing(12)
        line = QFrame(self)
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        row.addWidget(line)

        self.direction_hint = W.heading("", self)
        self.direction_hint.setWordWrap(False)
        row.addWidget(self.direction_hint, 1)
        return row

    # ================= 方向切换 =================

    @staticmethod
    def _spec(key):
        for item in DIRECTIONS:
            if item[0] == key:
                return item
        return DIRECTIONS[0]

    def select_direction(self, key):
        """切换转换方向：只换文案和占位符，不动输入内容。"""
        spec = self._spec(key)
        self._direction = spec[0]

        radio = self._radios.get(spec[0])
        if radio is not None and not radio.isChecked():
            radio.setChecked(True)

        in_card = self.textEdit.parentWidget()
        out_card = self.textEdit_2.parentWidget()
        if in_card is not None:
            in_card.setTitle("输入 · " + spec[1])
        if out_card is not None:
            out_card.setTitle("输出 · " + spec[1])

        self.textEdit.setPlaceholderText(spec[3])
        self.textEdit_2.setPlaceholderText(spec[4])
        self.pushButton.setText(spec[5])
        self.direction_hint.setText(spec[2])
        return spec[0]

    def current_direction(self):
        return self._direction

    def is_direction(self, key):
        return self._direction == key

    # ================= 按钮 =================

    def on_clear(self):
        self.clear_textedits(self.textEdit, self.textEdit_2)

    def on_copy(self):
        self.copy_to_clipboard(self.textEdit_2)

    def convert(self):
        """按当前方向执行转换。"""
        handler = {
            "lk2kernel": self.lk_to_kernel,
            "kernel2lk": self.kernel_to_lk,
            "lk2bat": self.lk_to_bat,
            "unisoc2qcom": self.unisoc_to_qcom,
        }.get(self._direction)
        if handler is not None:
            handler()

    # ================= 三个转换（算法与原页面一致） =================

    def lk_to_kernel(self):
        """LK → Kernel：去掉 0x、逗号换空格。"""
        text = self.textEdit.toPlainText()
        if not text.strip():
            self._warn("请填入 lk code")
            return ""
        output_lines = []
        for line in text.replace("0x", "").split('\n'):
            if not line.strip():
                output_lines.append("")
                continue
            values = [value.strip() for value in line.split(',')]
            output_lines.append(' '.join(values).rstrip())
        result = '\n'.join(output_lines)
        self.textEdit_2.setPlainText(result)
        return result

    def kernel_to_lk(self):
        """Kernel → LK：空格切分、加 0x、逗号分隔。"""
        text = self.textEdit.toPlainText()
        if not text.strip():
            self._warn("请填入 kernel 代码")
            return ""
        try:
            output_lines = []
            for line in text.split('\n'):
                if not line.strip():
                    continue
                values = [value.strip() for value in line.split(' ') if value.strip()]
                if not values:
                    continue
                output_lines.append(
                    ', '.join("0x" + value for value in values) + ',')
            result = '\n'.join(output_lines)
            self.textEdit_2.setPlainText(result)
            return result
        except Exception as exc:                              # noqa: BLE001
            self._warn("格式化失败：{}".format(exc))
            return ""

    def lk_to_bat(self):
        """LK → BAT：跳过每行前 4 个字段，拼成写 dcs 节点的批处理。"""
        text = self.textEdit.toPlainText()
        if not text.strip():
            self._warn("请填入 lk code")
            return ""
        output_lines = ['adb shell echo "0x01 > {}"'.format(BAT_NODE)]
        for line in text.split('\n'):
            values = [value.strip() for value in line.split(',')]
            values = values[4:]
            if values:
                output = ' '.join(values)
                output_lines.append(
                    'adb shell echo "{} > {}"'.format(output, BAT_NODE))
        output_lines.append("pause")
        result = '\n'.join(output_lines)
        self.textEdit_2.setPlainText(result)
        return result

    def unisoc_to_qcom(self):
        """UNISOC → QCOM：4 字节头换成 QCOM 的 7 字节头，负载原样搬。"""
        text = self.textEdit.toPlainText()
        if not text.strip():
            self._warn("请填入 UNISOC kernel 命令集")
            return ""
        lines, problems = unisoc_to_qcom(text)
        result = "\n".join(lines)
        self.textEdit_2.setPlainText(result)
        if problems:
            self._warn("{}；共 {} 行有问题".format(problems[0], len(problems)))
        elif lines:
            self._warn("已转换 {} 包".format(len(lines)))
        return result

    def _warn(self, message):
        """轻提示：有窗口 Toast 就用 Toast，否则什么也不做（自测里不弹模态框）。"""
        window = self.window()
        if hasattr(window, "toast"):
            window.toast(message, "warning", 2600)
            return
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", message, QMessageBox.Ok)
        except Exception:                                     # noqa: BLE001
            pass
