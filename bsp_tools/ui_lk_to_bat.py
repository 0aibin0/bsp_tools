# -*- coding: utf-8 -*-
"""LK → BAT 页面界面（由 ui_transform 统一构建）。"""

from ui_transform import build_transform_ui


class Ui_LkToBat(object):
    def setupUi(self, MainWindow):
        widgets = build_transform_ui(
            MainWindow,
            input_title="LK initcode 输入",
            input_hint="整行 initcode，逗号分隔，例如 0x39,0x00,0x00,0x05,0x1a,0x2b,",
            output_title="BAT 脚本输出",
            output_hint="转换结果（只读），可直接保存为 .bat 在设备上执行",
        )
        self.textEdit = widgets["textEdit"]
        self.textEdit_2 = widgets["textEdit_2"]
        self.pushButton = widgets["pushButton"]
        self.pushButton_clear = widgets["pushButton_clear"]
        self.pushButton_copy = widgets["pushButton_copy"]

    def retranslateUi(self, MainWindow):
        # 文本已在 build_transform_ui 中设置，保留方法以兼容既有调用。
        pass
