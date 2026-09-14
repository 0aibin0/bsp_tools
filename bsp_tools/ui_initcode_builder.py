# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets

import ui_widgets


class Ui_InitcodeBuilder(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(662, 630)
        self.gridLayout = QtWidgets.QGridLayout(MainWindow)
        self.gridLayout.setContentsMargins(16, 14, 16, 14)
        self.gridLayout.setSpacing(12)
        self.gridLayout.setObjectName("gridLayout")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSpacing(12)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.textEdit = QtWidgets.QTextEdit(MainWindow)
        self.textEdit.setObjectName("textEdit")
        self.textEdit.setMinimumHeight(260)
        self.horizontalLayout.addWidget(self.textEdit)
        self.textEdit_2 = QtWidgets.QTextEdit(MainWindow)
        self.textEdit_2.setObjectName("textEdit_2")
        self.textEdit_2.setMinimumHeight(260)
        self.horizontalLayout.addWidget(self.textEdit_2)
        self.verticalLayout.addLayout(self.horizontalLayout)

        # 格式提示标签（替代 QMessageBox 弹窗）
        self.format_hint = QtWidgets.QLabel(MainWindow)
        self.format_hint.setObjectName("format_hint")
        self.verticalLayout.addWidget(self.format_hint)

        # 按钮行
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.buttonLayout.setSpacing(8)
        self.pushButton = QtWidgets.QPushButton(MainWindow)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.setProperty("accent", True)
        self.pushButton.setMinimumHeight(32)
        self.pushButton.setMinimumWidth(96)
        self.buttonLayout.addWidget(self.pushButton)
        self.pushButton_clear = QtWidgets.QPushButton(MainWindow)
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.pushButton_clear.setProperty("ghost", True)
        self.pushButton_clear.setMinimumHeight(32)
        self.pushButton_clear.setMinimumWidth(96)
        self.buttonLayout.addWidget(self.pushButton_clear)
        self.pushButton_copy = QtWidgets.QPushButton(MainWindow)
        self.pushButton_copy.setObjectName("pushButton_copy")
        self.pushButton_copy.setProperty("ghost", True)
        self.pushButton_copy.setMinimumHeight(32)
        self.pushButton_copy.setMinimumWidth(96)
        self.buttonLayout.addWidget(self.pushButton_copy)
        self.buttonLayout.addStretch()
        self.verticalLayout.addLayout(self.buttonLayout)

        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(MainWindow)
        self.groupBox.setObjectName("groupBox")
        self.groupBox.setMinimumWidth(232)
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout_2.setSpacing(8)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.radioButton = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton.setObjectName("radioButton")
        self.radioButton.setMinimumHeight(24)
        self.gridLayout_2.addWidget(self.radioButton, 0, 0, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(20, 476, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout_2.addItem(spacerItem, 7, 0, 1, 1)
        self.radioButton_4 = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_4.setObjectName("radioButton_4")
        self.radioButton_4.setMinimumHeight(24)
        self.gridLayout_2.addWidget(self.radioButton_4, 4, 0, 1, 1)
        self.line = QtWidgets.QFrame(self.groupBox)
        self.line.setFrameShape(QtWidgets.QFrame.HLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridLayout_2.addWidget(self.line, 3, 0, 1, 1)
        self.radioButton_3 = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_3.setObjectName("radioButton_3")
        self.radioButton_3.setMinimumHeight(24)
        self.gridLayout_2.addWidget(self.radioButton_3, 2, 0, 1, 1)
        self.radioButton_2 = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_2.setObjectName("radioButton_2")
        self.radioButton_2.setMinimumHeight(24)
        self.gridLayout_2.addWidget(self.radioButton_2, 1, 0, 1, 1)
        self.lineEdit = QtWidgets.QLineEdit(self.groupBox)
        self.lineEdit.setMinimumHeight(28)
        self.lineEdit.setObjectName("lineEdit")
        self.gridLayout_2.addWidget(self.lineEdit, 5, 0, 1, 1)
        self.line_2 = QtWidgets.QFrame(self.groupBox)
        self.line_2.setFrameShape(QtWidgets.QFrame.HLine)
        self.line_2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_2.setObjectName("line_2")
        self.gridLayout_2.addWidget(self.line_2, 6, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 0, 1, 1, 1)
        self.gridLayout.setColumnStretch(0, 1)

        # ================= 反向解析区块（手写扩展，不参与 .ui 重新生成） =================
        # 放在原有两栏下方、横跨两列。三块文本框并排（输入 / 清单 / 输出），
        # 高度靠最小高度兜底，宽度只给最小值，避免把页面最小尺寸需求撑大。
        self.reverse_card = ui_widgets.Card(
            "反向解析：initcode 字节序列 → DCS 命令 + 参数", MainWindow)
        # 行距压到 7px、三个文本框只给 76px 最小高度：整个卡片的最小高度控制在
        # 240px 上下，页面最小尺寸需求才不会把主窗口默认高度顶上去。
        self.reverse_card.body.setSpacing(7)
        self.reverse_card.add(ui_widgets.heading(
            "支持 0x39,0x00,… 逗号序列、C 数组 {…}、裸十六进制（39 00 00 05）、"
            "adb dcs 写命令、// 与 /* */ 注释、反斜杠续行和 \\x1a 转义；"
            "按「3 字节包头 + 1 字节长度 + N 字节负载」逐条还原。"))
        self.reverse_card.add(ui_widgets.separator(self.reverse_card))

        edit_row = self.reverse_card.add_row()
        self.reverse_input = QtWidgets.QTextEdit(self.reverse_card)
        self.reverse_input.setObjectName("reverse_input")
        self.reverse_input.setMinimumSize(196, 76)
        self.reverse_list = QtWidgets.QTextEdit(self.reverse_card)
        self.reverse_list.setObjectName("reverse_list")
        self.reverse_list.setReadOnly(True)
        self.reverse_list.setMinimumSize(196, 76)
        self.reverse_output = QtWidgets.QTextEdit(self.reverse_card)
        self.reverse_output.setObjectName("reverse_output")
        self.reverse_output.setReadOnly(True)
        self.reverse_output.setMinimumSize(196, 76)
        for column_title, column_widget in (("输入 initcode", self.reverse_input),
                                            ("解析清单", self.reverse_list),
                                            ("转换输出", self.reverse_output)):
            column = QtWidgets.QVBoxLayout()
            column.setSpacing(4)
            column.addWidget(ui_widgets.field_label(column_title, self.reverse_card))
            column.addWidget(column_widget)
            edit_row.addLayout(column, 1)

        control_row = self.reverse_card.add_row()
        self.pushButton_parse = ui_widgets.accent_button("解析", parent=self.reverse_card)
        self.pushButton_parse.setObjectName("pushButton_parse")
        control_row.addWidget(self.pushButton_parse)
        control_row.addWidget(ui_widgets.field_label("输出格式", self.reverse_card))
        self.combo_reverse_style = QtWidgets.QComboBox(self.reverse_card)
        self.combo_reverse_style.setObjectName("combo_reverse_style")
        self.combo_reverse_style.setMinimumWidth(168)
        # 下拉项由 initcode_builder 按 STYLE_LABELS 填充（保持单一来源）
        control_row.addWidget(self.combo_reverse_style)
        self.pushButton_reverse_copy = ui_widgets.soft_button("复制结果", parent=self.reverse_card)
        self.pushButton_reverse_copy.setObjectName("pushButton_reverse_copy")
        control_row.addWidget(self.pushButton_reverse_copy)
        self.pushButton_output_copy = ui_widgets.soft_button("复制输出", parent=self.reverse_card)
        self.pushButton_output_copy.setObjectName("pushButton_output_copy")
        control_row.addWidget(self.pushButton_output_copy)
        control_row.addStretch()

        self.reverse_status = QtWidgets.QLabel(MainWindow)
        self.reverse_status.setObjectName("reverse_status")
        self.reverse_status.setWordWrap(True)
        self.reverse_status.setMinimumWidth(64)
        self.reverse_card.add(self.reverse_status)

        self.gridLayout.addWidget(self.reverse_card, 1, 0, 1, 2)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        self.pushButton.setText(_translate("MainWindow", "Build"))
        self.pushButton_clear.setText(_translate("MainWindow", "Clear"))
        self.pushButton_copy.setText(_translate("MainWindow", "Copy"))
        self.format_hint.setText(_translate("MainWindow", "当前格式: WriteAddr"))
        self.groupBox.setTitle(_translate("MainWindow", "命令格式"))
        self.radioButton.setText(_translate("MainWindow", "WriteAddr"))
        self.radioButton_4.setText(_translate("MainWindow", "GEN_WR"))
        self.radioButton_3.setText(_translate("MainWindow", "Rxx"))
        self.radioButton_2.setText(_translate("MainWindow", "Write(Command)"))
