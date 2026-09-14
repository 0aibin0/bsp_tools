from PyQt5.QtWidgets import QMessageBox
from ui_kernel_to_lk import Ui_KernelToLk
from base_tool_page import BaseToolPage


class KernelToLkPage(BaseToolPage, Ui_KernelToLk):
    def __init__(self, parent=None):
        super(KernelToLkPage, self).__init__(parent)
        self.setupUi(self)

        self.textEdit.setPlaceholderText("Enter kernel code (e.g. 1a 2b 3c 4d)")
        self.textEdit_2.setReadOnly(True)
        self.textEdit_2.setPlaceholderText("generate lk code (e.g. 0x1a,0x2b,0x3c,0x4d)")

        self.pushButton.clicked.connect(self.kernel_to_lk)
        self.pushButton_clear.clicked.connect(self.on_clear)
        self.pushButton_copy.clicked.connect(self.on_copy)

    def on_clear(self):
        self.clear_textedits(self.textEdit, self.textEdit_2)

    def on_copy(self):
        self.copy_to_clipboard(self.textEdit_2)

    def kernel_to_lk(self):
        self.inputtext = self.textEdit.toPlainText()
        if not self.inputtext.strip():
            QMessageBox.information(self, "提示", "请填入kernel代码", QMessageBox.Ok)
            return
        try:
            lines = self.inputtext.split('\n')
            output_lines = []
            for line in lines:
                if not line.strip():
                    continue
                values = [value.strip() for value in line.split(' ') if value.strip()]
                formatted_line = ', '.join(f"0x{value}" for value in values) + ','
                output_lines.append(formatted_line)
            self.textEdit_2.setPlainText('\n'.join(output_lines))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"格式化失败：{str(e)}", QMessageBox.Ok)
