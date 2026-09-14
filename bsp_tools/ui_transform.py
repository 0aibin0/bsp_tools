# -*- coding: utf-8 -*-
"""转换类页面（LK↔Kernel、LK→BAT）共用的界面构建函数。

这三个页面的结构完全一致：左边输入、右边只读输出、底部 Convert/Clear/Copy。
抽成一份，避免三份几乎相同的 UI 代码各自漂移。
"""

from PyQt5 import QtCore, QtWidgets


def build_transform_ui(host, *, input_title="输入", input_hint="",
                       output_title="输出", output_hint="转换结果（只读）",
                       convert_text="Convert", input_height=220):
    """在 host 上构建转换页界面。

    构建出的控件名与原 .ui 保持一致（textEdit / textEdit_2 / pushButton /
    pushButton_clear / pushButton_copy），业务代码无需改动。
    """
    host.setObjectName("MainWindow")
    host.resize(900, 600)

    grid = QtWidgets.QGridLayout(host)
    grid.setContentsMargins(16, 14, 16, 14)
    grid.setSpacing(12)
    grid.setObjectName("gridLayout")

    columns = QtWidgets.QHBoxLayout()
    columns.setSpacing(12)
    columns.setObjectName("horizontalLayout")

    # ---- 输入 ----
    input_card = QtWidgets.QGroupBox(host)
    input_card.setObjectName("inputCard")
    input_layout = QtWidgets.QVBoxLayout(input_card)
    input_layout.setContentsMargins(10, 16, 10, 10)
    input_layout.setSpacing(6)
    if input_hint:
        label_in = QtWidgets.QLabel(input_hint, input_card)
        label_in.setProperty("hint", True)
        label_in.setWordWrap(True)
        input_layout.addWidget(label_in)
    text_edit = QtWidgets.QTextEdit(input_card)
    text_edit.setObjectName("textEdit")
    text_edit.setMinimumHeight(input_height)
    input_layout.addWidget(text_edit)
    columns.addWidget(input_card)

    # ---- 输出 ----
    output_card = QtWidgets.QGroupBox(host)
    output_card.setObjectName("outputCard")
    output_layout = QtWidgets.QVBoxLayout(output_card)
    output_layout.setContentsMargins(10, 16, 10, 10)
    output_layout.setSpacing(6)
    if output_hint:
        label_out = QtWidgets.QLabel(output_hint, output_card)
        label_out.setProperty("hint", True)
        label_out.setWordWrap(True)
        output_layout.addWidget(label_out)
    text_edit_2 = QtWidgets.QTextEdit(output_card)
    text_edit_2.setObjectName("textEdit_2")
    text_edit_2.setMinimumHeight(input_height)
    output_layout.addWidget(text_edit_2)
    columns.addWidget(output_card)

    grid.addLayout(columns, 0, 0, 1, 1)

    # ---- 按钮行 ----
    buttons = QtWidgets.QHBoxLayout()
    buttons.setSpacing(8)
    buttons.setObjectName("buttonLayout")

    push_button = QtWidgets.QPushButton(convert_text, host)
    push_button.setObjectName("pushButton")
    push_button.setProperty("accent", True)
    push_button.setMinimumHeight(32)
    push_button.setMinimumWidth(110)
    buttons.addWidget(push_button)

    clear_button = QtWidgets.QPushButton("Clear", host)
    clear_button.setObjectName("pushButton_clear")
    clear_button.setProperty("ghost", True)
    clear_button.setMinimumHeight(32)
    clear_button.setMinimumWidth(96)
    buttons.addWidget(clear_button)

    copy_button = QtWidgets.QPushButton("Copy", host)
    copy_button.setObjectName("pushButton_copy")
    copy_button.setProperty("ghost", True)
    copy_button.setMinimumHeight(32)
    copy_button.setMinimumWidth(96)
    buttons.addWidget(copy_button)

    buttons.addStretch()
    grid.addLayout(buttons, 1, 0, 1, 1)

    input_card.setTitle(input_title)
    output_card.setTitle(output_title)

    QtCore.QMetaObject.connectSlotsByName(host)

    return {
        "textEdit": text_edit,
        "textEdit_2": text_edit_2,
        "pushButton": push_button,
        "pushButton_clear": clear_button,
        "pushButton_copy": copy_button,
    }
