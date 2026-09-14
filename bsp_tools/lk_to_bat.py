from PyQt5.QtWidgets import QMessageBox
from ui_lk_to_bat import Ui_LkToBat
from base_tool_page import BaseToolPage


class LkToBatPage(BaseToolPage, Ui_LkToBat):
    def __init__(self, parent=None):
        super(LkToBatPage, self).__init__(parent)
        self.setupUi(self)

        self.textEdit.setPlaceholderText("Enter lk initcode (e.g. 0x--,0x--,0x--,0x--,0x--)")
        self.textEdit_2.setReadOnly(True)
        self.textEdit_2.setPlaceholderText(
            "generate bat code \n(e.g. adb shell echo \"0x01 > /sys/class/display/dsi/dcs_write\")")

        self.pushButton.clicked.connect(self.lk_to_bat)
        self.pushButton_clear.clicked.connect(self.on_clear)
        self.pushButton_copy.clicked.connect(self.on_copy)

    def on_clear(self):
        self.clear_textedits(self.textEdit, self.textEdit_2)

    def on_copy(self):
        self.copy_to_clipboard(self.textEdit_2)

    def lk_to_bat(self):
        self.input_text = self.textEdit.toPlainText()
        if not self.input_text.strip():
            QMessageBox.information(self, "提示", "请填入lk code", QMessageBox.Ok)
            return
        lines = self.input_text.split('\n')
        output_lines = []
        first_line = "adb shell echo \"0x01 > /sys/class/display/dsi0/dcs_write\""
        output_lines.append(first_line)
        for line in lines:
            values = line.split(',')
            values = [value.strip() for value in values]
            values = values[4:]
            if values:
                output_line = ' '.join(values).ljust(len(values) * 3).rstrip()
                output_line = f"adb shell echo \"{output_line} > /sys/class/display/dsi0/dcs_write\""
                output_lines.append(output_line)
        output_lines.append("pause")
        self.textEdit_2.setPlainText('\n'.join(output_lines))
