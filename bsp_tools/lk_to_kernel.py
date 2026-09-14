from PyQt5.QtWidgets import QMessageBox
from ui_lk_to_kernel import Ui_LkToKernel
from base_tool_page import BaseToolPage


class LkToKernelPage(BaseToolPage, Ui_LkToKernel):
    def __init__(self, parent=None):
        super(LkToKernelPage, self).__init__(parent)
        self.setupUi(self)

        self.textEdit.setPlaceholderText("Enter lk code (e.g. 0x1a,0x2b,0x3c,0x4d)")
        self.textEdit_2.setReadOnly(True)
        self.textEdit_2.setPlaceholderText("generate kernel code (e.g. 1a 2b 3c 4d)")

        self.pushButton.clicked.connect(self.lk_to_kernel)
        self.pushButton_clear.clicked.connect(self.on_clear)
        self.pushButton_copy.clicked.connect(self.on_copy)

    def on_clear(self):
        self.clear_textedits(self.textEdit, self.textEdit_2)

    def on_copy(self):
        self.copy_to_clipboard(self.textEdit_2)

    def lk_to_kernel(self):
        self.inputtext = self.textEdit.toPlainText()
        if not self.inputtext.strip():
            QMessageBox.information(self, "提示", "请填入lk code", QMessageBox.Ok)
            return
        input_text = self.inputtext.replace("0x", "")
        lines = input_text.split('\n')
        output_lines = []
        for line in lines:
            values = line.split(',')
            values = [value.strip() for value in values]
            col_count = len(values)
            output_line = ' '.join(values).ljust(col_count * 3).rstrip()
            output_lines.append(output_line)
        self.textEdit_2.setPlainText('\n'.join(output_lines))
