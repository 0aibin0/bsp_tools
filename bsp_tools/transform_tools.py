"""转换工具：LK ↔ Kernel 互转 + LK → BAT，合并成一页。

原先这三个是三个独立页面（左侧菜单各占一行），但它们**界面结构完全一致**
——左边输入、右边只读输出、底部 Convert / Clear / Copy，
只是转换函数不同。三份页面在侧边栏占了 3 行，把菜单撑得很长。

合并后：顶部一排「转换方向」单选，下面仍是同一套输入/输出布局；
切换方向只换标题、占位符和按下 Convert 时调用的函数。

三个转换的算法原样搬过来，没有改动：
- LK → Kernel：去掉 0x 前缀、逗号换空格
- Kernel → LK：空格切分、加 0x 前缀、逗号分隔
- LK → BAT：取每行第 5 个字段起，拼成 adb shell echo 写 dcs_write 节点
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
)

#: LK → BAT 里写节点的固定节点路径（与原实现保持一致）
BAT_NODE = "/sys/class/display/dsi0/dcs_write"


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
