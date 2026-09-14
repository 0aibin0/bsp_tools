# -*- coding: utf-8 -*-
"""LK → Kernel 页面界面（由 ui_transform 统一构建）。"""

from ui_transform import build_transform_ui


class Ui_LkToKernel(object):
    def setupUi(self, MainWindow):
        widgets = build_transform_ui(
            MainWindow,
            input_title="LK 输入",
            input_hint="每行一组，逗号分隔，例如 0x1a,0x2b,0x3c,0x4d",
            output_title="Kernel 输出",
            output_hint="转换结果（只读），空格分隔，例如 1a 2b 3c 4d",
        )
        self.textEdit = widgets["textEdit"]
        self.textEdit_2 = widgets["textEdit_2"]
        self.pushButton = widgets["pushButton"]
        self.pushButton_clear = widgets["pushButton_clear"]
        self.pushButton_copy = widgets["pushButton_copy"]

    def retranslateUi(self, MainWindow):
        # 文本已在 build_transform_ui 中设置，保留方法以兼容既有调用。
        pass
