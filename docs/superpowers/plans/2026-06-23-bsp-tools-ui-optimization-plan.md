# BSP Tools UI/布局/功能优化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 DisplayTools 从多独立窗口改为单窗口 QTabWidget 导航，重构 shell_tools 为弹性网格布局，抽取公共基类，添加 Clear/Copy 按钮，清理死代码。

**Architecture:** 创建 BaseToolPage(QWidget) 公共基类 → 5 个工具页面均继承它 → MainWindow 用 QTabWidget 组装所有页面。所有 ui_*.py 从 QMainWindow 模式改为 QWidget 模式。shell_tools 布局从绝对定位改为 QGridLayout。

**Tech Stack:** Python 3.11, PyQt5 5.15.10

## Global Constraints

- 保留现有 .ui 文件不变（ui_*.py 手动修改以适应 QWidget）
- 转换算法（initcodebuilder_1~4、lk_to_kernel、kernel_to_lk、lk_to_bat）逻辑不变
- adb/fastboot 命令逻辑不变
- 图标资源路径保持不变
- 不修改 density 独立工具
- PyInstaller .spec 入口保持 mainwindow.py

---

### Task 1: 创建 BaseToolPage 公共基类

**Files:**
- Create: `bsp_tools/bsp_tools/bsp_tools/base_tool_page.py`

**Produces:** `BaseToolPage(QWidget)` 类，提供 `copy_to_clipboard()`, `clear_textedits()`, `show_status_tip()` 方法

- [ ] **Step 1: 创建 base_tool_page.py**

```python
from PyQt5.QtWidgets import QWidget, QTextEdit, QLabel, QApplication
from PyQt5.QtCore import QTimer


class BaseToolPage(QWidget):
    """所有工具页面的公共基类，提供清空、复制、状态提示等共享方法"""

    def clear_textedits(self, *edits):
        """清空指定的 QTextEdit 控件"""
        for edit in edits:
            if isinstance(edit, QTextEdit):
                edit.clear()

    def copy_to_clipboard(self, edit):
        """将 QTextEdit 内容复制到剪贴板"""
        if isinstance(edit, QTextEdit):
            text = edit.toPlainText()
            if text.strip():
                QApplication.clipboard().setText(text)

    def show_status_tip(self, label, text, duration=3000):
        """在指定 label 显示临时提示文字，duration 毫秒后自动清除"""
        if isinstance(label, QLabel):
            label.setText(text)
            QTimer.singleShot(duration, lambda: label.setText(""))
```

- [ ] **Step 2: 验证文件语法**

```bash
cd bsp_tools/bsp_tools && python -c "from base_tool_page import BaseToolPage; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add bsp_tools/bsp_tools/bsp_tools/base_tool_page.py
git commit -m "feat: add BaseToolPage base class for shared tool page methods

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 转换 initcode_builder 为 Tab 页面

**Files:**
- Modify: `bsp_tools/bsp_tools/bsp_tools/ui_initcode_builder.py` — 去除 QMainWindow 依赖
- Modify: `bsp_tools/bsp_tools/bsp_tools/initcode_builder.py` — 重写为 QWidget 页面，添加 Clear/Copy 按钮

**Consumes:** `BaseToolPage` from Task 1
**Produces:** `InitcodeBuilderPage(BaseToolPage, Ui_InitcodeBuilder)` 类

- [ ] **Step 1: 修改 ui_initcode_builder.py 去除 QMainWindow**

将 `setupUi` 改为接受 QWidget，移除 `setCentralWidget`/`setStatusBar`，去掉 action：

```python
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_InitcodeBuilder(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(662, 630)
        self.gridLayout = QtWidgets.QGridLayout(MainWindow)
        self.gridLayout.setObjectName("gridLayout")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.textEdit = QtWidgets.QTextEdit(MainWindow)
        self.textEdit.setObjectName("textEdit")
        self.horizontalLayout.addWidget(self.textEdit)
        self.textEdit_2 = QtWidgets.QTextEdit(MainWindow)
        self.textEdit_2.setObjectName("textEdit_2")
        self.horizontalLayout.addWidget(self.textEdit_2)
        self.verticalLayout.addLayout(self.horizontalLayout)
        
        # 格式提示标签（替代 QMessageBox 弹窗）
        self.format_hint = QtWidgets.QLabel(MainWindow)
        self.format_hint.setStyleSheet("color: #666; font-size: 12px;")
        self.format_hint.setObjectName("format_hint")
        self.verticalLayout.addWidget(self.format_hint)
        
        # 按钮行
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.pushButton = QtWidgets.QPushButton(MainWindow)
        self.pushButton.setObjectName("pushButton")
        self.buttonLayout.addWidget(self.pushButton)
        self.pushButton_clear = QtWidgets.QPushButton(MainWindow)
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.buttonLayout.addWidget(self.pushButton_clear)
        self.pushButton_copy = QtWidgets.QPushButton(MainWindow)
        self.pushButton_copy.setObjectName("pushButton_copy")
        self.buttonLayout.addWidget(self.pushButton_copy)
        self.verticalLayout.addLayout(self.buttonLayout)
        
        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(MainWindow)
        self.groupBox.setMaximumSize(QtCore.QSize(156, 16777215))
        self.groupBox.setStyleSheet("background-color: rgb(255, 255, 255);")
        self.groupBox.setObjectName("groupBox")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.groupBox)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.radioButton = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton.setObjectName("radioButton")
        self.gridLayout_2.addWidget(self.radioButton, 0, 0, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(20, 476, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.gridLayout_2.addItem(spacerItem, 7, 0, 1, 1)
        self.radioButton_4 = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_4.setObjectName("radioButton_4")
        self.gridLayout_2.addWidget(self.radioButton_4, 4, 0, 1, 1)
        self.line = QtWidgets.QFrame(self.groupBox)
        self.line.setMaximumSize(QtCore.QSize(110, 3))
        self.line.setFrameShape(QtWidgets.QFrame.HLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridLayout_2.addWidget(self.line, 3, 0, 1, 1)
        self.radioButton_3 = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_3.setObjectName("radioButton_3")
        self.gridLayout_2.addWidget(self.radioButton_3, 2, 0, 1, 1)
        self.radioButton_2 = QtWidgets.QRadioButton(self.groupBox)
        self.radioButton_2.setObjectName("radioButton_2")
        self.gridLayout_2.addWidget(self.radioButton_2, 1, 0, 1, 1)
        self.lineEdit = QtWidgets.QLineEdit(self.groupBox)
        self.lineEdit.setMaximumSize(QtCore.QSize(124, 20))
        self.lineEdit.setObjectName("lineEdit")
        self.gridLayout_2.addWidget(self.lineEdit, 5, 0, 1, 1)
        self.line_2 = QtWidgets.QFrame(self.groupBox)
        self.line_2.setMaximumSize(QtCore.QSize(110, 3))
        self.line_2.setFrameShape(QtWidgets.QFrame.HLine)
        self.line_2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_2.setObjectName("line_2")
        self.gridLayout_2.addWidget(self.line_2, 6, 0, 1, 1)
        self.gridLayout.addWidget(self.groupBox, 0, 1, 1, 1)

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
```

- [ ] **Step 2: 重写 initcode_builder.py 为 QWidget 页面**

```python
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QMessageBox
from ui_initcode_builder import Ui_InitcodeBuilder
from base_tool_page import BaseToolPage
import re


class InitcodeBuilderPage(BaseToolPage, Ui_InitcodeBuilder):
    def __init__(self, parent=None):
        super(InitcodeBuilderPage, self).__init__(parent)
        self.setupUi(self)

        self.textEdit.setPlaceholderText(
            "Enter hex WriteAddr/WriteData strings\n**********\nWriteAddr(0x1a)\n"
            "WriteData(0x2b)\nWriteData(0x3c)\nWriteData(0x4d)\nWriteData(0x5e)\n**********\n")
        self.textEdit_2.setReadOnly(True)
        self.textEdit_2.setPlaceholderText(
            "generate initcode \n(e.g. 0x39,0x00,0x00,0x05,0x1a,0x2b,0x3c,0x4d,0x5e)")
        self.lineEdit.setPlaceholderText("GEN_WR")

        self.radioButton.setChecked(True)

        self.pushButton.clicked.connect(self.initcodebuilder_1)
        self.pushButton_clear.clicked.connect(self.on_clear)
        self.pushButton_copy.clicked.connect(self.on_copy)

        self.radioButton.clicked.connect(self.select_command)
        self.radioButton_2.clicked.connect(self.select_command)
        self.radioButton_3.clicked.connect(self.select_command)
        self.radioButton_4.clicked.connect(self.select_command)

    def on_clear(self):
        self.clear_textedits(self.textEdit, self.textEdit_2)

    def on_copy(self):
        self.copy_to_clipboard(self.textEdit_2)

    def select_command(self):
        """根据选中的单选按钮更新文本框和连接的槽函数"""
        self.textEdit.clear()
        self.textEdit_2.clear()

        # 断开 build 按钮的所有连接
        try:
            self.pushButton.clicked.disconnect()
        except TypeError:
            pass

        if self.radioButton.isChecked():
            self.format_hint.setText("当前格式: WriteAddr")
            self.textEdit.setPlaceholderText(
                "Enter hex WriteAddr/WriteData strings\n**********\nWriteAddr(0x1a)\n"
                "WriteData(0x2b)\nWriteData(0x3c)\nWriteData(0x4d)\nWriteData(0x5e)\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_1)
        elif self.radioButton_2.isChecked():
            self.format_hint.setText("当前格式: Write(Command)")
            self.textEdit.setPlaceholderText(
                "Enter hex Write(Command,0xxx)strings\n**********\nWrite(Command,0x1a);\n"
                "Write(Parameter,0x2b);\nWrite(Parameter,0x3c);\nWrite(Parameter,0x4d);\n"
                "Write(Parameter,0x5e);\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_2)
        elif self.radioButton_3.isChecked():
            self.format_hint.setText("当前格式: Rxx")
            self.textEdit.setPlaceholderText("Enter hex Rxx strings\n**********\nR1a 2b 3c 4d 5e\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_3)
        elif self.radioButton_4.isChecked():
            self.format_hint.setText("当前格式: GEN_WR")
            self.textEdit.setPlaceholderText(
                "Enter hex GEN_WR strings\n**********\nGEN_WR(0x1a,0x2b,0x3c,0x4d,0x5e);\n**********\n")
            self.pushButton.clicked.connect(self.initcodebuilder_4)

    def initcodebuilder_1(self):
        """处理 WriteAddr 和 WriteData 格式"""
        input_str = self.textEdit.toPlainText()
        rows = input_str.split('\n')
        output_rows = []
        current_addr = None
        data_values = []

        def generate_output_row(addr, data_values):
            data_count = len(data_values) + 1
            data_count_hex = f"0x{data_count:02x}"
            if data_count == 1:
                prefix = '0x05,0x78,0x00'
            elif data_count == 2:
                prefix = '0x15,0x00,0x00'
            else:
                prefix = '0x39,0x00,0x00'
            row = [prefix, data_count_hex, addr] + data_values
            return ",".join(
                [f"0x{num.lower()}" if not num.startswith("0x") else num.lower() for num in row]) + ","

        for row in rows:
            row = row.split('//')[0].strip()
            if not row:
                continue
            if 'WriteAddr' in row:
                if current_addr is not None:
                    output_rows.append(generate_output_row(current_addr, data_values))
                current_addr = row.split('(')[1].split(')')[0].strip()
                data_values = []
            elif 'WriteData' in row:
                data = row.split('(')[1].split(')')[0].strip()
                data_values.append(data)

        if current_addr is not None:
            output_rows.append(generate_output_row(current_addr, data_values))

        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_2(self):
        """处理 Write(Command) 格式"""
        input_str = self.textEdit.toPlainText()
        rows = input_str.split('\n')
        current_command = None
        data_values = []
        output_rows = []

        def generate_output_row(command, parameters):
            data_count = len(parameters) + 1
            data_count_hex = f"0x{data_count:02x}"
            if data_count == 1:
                prefix = '0x05,0x78,0x00'
            elif data_count == 2:
                prefix = '0x15,0x00,0x00'
            else:
                prefix = '0x39,0x00,0x00'
            row = [prefix, data_count_hex, command] + parameters
            return ",".join(
                [f"0x{num.lower()}" if not num.startswith("0x") else num.lower() for num in row]) + ","

        for row in rows:
            row = row.split('//')[0].strip()
            if not row:
                continue
            if 'Write(' in row:
                content = row.split('(')[1].split(')')[0]
                data_type, value = content.split(',')
                data_type, value = data_type.strip(), value.strip()
                if data_type == "Command":
                    if current_command is not None:
                        output_rows.append(generate_output_row(current_command, data_values))
                    current_command = value
                    data_values = []
                elif data_type == "Parameter":
                    data_values.append(value)

        if current_command is not None:
            output_rows.append(generate_output_row(current_command, data_values))

        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_3(self):
        """处理 Rxx 格式"""
        input_str = self.textEdit.toPlainText()
        input_str = input_str.replace("R", "")
        lines = input_str.splitlines()
        output_rows = []

        for line in lines:
            line = line.split('//')[0].strip()
            if not line:
                continue
            hex_values = line.split()
            hex_count = len(hex_values)
            count_hex = f"0x{hex_count:02x}"
            if hex_count == 1:
                prefix = '0x05,0x78,0x00'
            elif hex_count == 2:
                prefix = '0x15,0x00,0x00'
            else:
                prefix = '0x39,0x00,0x00'
            formatted_values = [f"0x{val.lower()}" for val in hex_values]
            output_str = f"{prefix},{count_hex}," + ",".join(formatted_values) + ","
            output_rows.append(output_str)

        self.textEdit_2.setPlainText("\n".join(output_rows))

    def initcodebuilder_4(self):
        """处理 GEN_WR 等格式"""
        instructions_str = self.lineEdit.text()
        instructions = [cmd.strip() for cmd in instructions_str.split(",")] if instructions_str else ['GEN_WR']
        input_str = self.textEdit.toPlainText()
        lines = input_str.splitlines()
        output_rows = []

        for line in lines:
            if line.strip().startswith("//") and not line.strip()[2:].strip():
                output_rows.append(line)
                continue
            comment_index = line.find("//")
            if comment_index != -1:
                code_part = line[:comment_index].strip()
                comment_part = line[comment_index:].strip()
            else:
                code_part = line.strip()
                comment_part = ""
            if code_part:
                code_part = code_part.split("//")[0].strip()
                if not code_part:
                    continue
                for instruction in instructions:
                    match = re.search(rf"{instruction}\((.*?)\);?", code_part)
                    if match:
                        hex_values = match.group(1).split(",")
                        hex_count = len(hex_values)
                        count_hex = f"0x{hex_count:02x}"
                        if hex_count == 1:
                            prefix = "0x05,0x78,0x00"
                        elif hex_count == 2:
                            prefix = "0x15,0x00,0x00"
                        else:
                            prefix = "0x39,0x00,0x00"
                        formatted_values = [val.strip().lower() for val in hex_values]
                        processed_code = f"{prefix},{count_hex}," + ",".join(formatted_values) + ","
                        break
                else:
                    processed_code = code_part
            else:
                processed_code = ""
            final_line = processed_code + comment_part
            output_rows.append(final_line)

        self.textEdit_2.setPlainText("\n".join(output_rows))
```

- [ ] **Step 3: 验证语法**

```bash
cd bsp_tools/bsp_tools && python -c "from initcode_builder import InitcodeBuilderPage; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add bsp_tools/bsp_tools/bsp_tools/ui_initcode_builder.py bsp_tools/bsp_tools/bsp_tools/initcode_builder.py
git commit -m "refactor: convert initcode_builder to QWidget tab page, add Clear/Copy

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 转换 lk_to_kernel 为 Tab 页面

**Files:**
- Modify: `bsp_tools/bsp_tools/bsp_tools/ui_lk_to_kernel.py`
- Modify: `bsp_tools/bsp_tools/bsp_tools/lk_to_kernel.py`

**Consumes:** `BaseToolPage` from Task 1
**Produces:** `LkToKernelPage(BaseToolPage, Ui_LkToKernel)` 类

- [ ] **Step 1: 修改 ui_lk_to_kernel.py 去除 QMainWindow**

```python
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_LkToKernel(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(662, 500)
        self.gridLayout = QtWidgets.QGridLayout(MainWindow)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.textEdit = QtWidgets.QTextEdit(MainWindow)
        self.textEdit.setObjectName("textEdit")
        self.horizontalLayout.addWidget(self.textEdit)
        self.textEdit_2 = QtWidgets.QTextEdit(MainWindow)
        self.textEdit_2.setObjectName("textEdit_2")
        self.horizontalLayout.addWidget(self.textEdit_2)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 1)
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.pushButton = QtWidgets.QPushButton(MainWindow)
        self.pushButton.setObjectName("pushButton")
        self.buttonLayout.addWidget(self.pushButton)
        self.pushButton_clear = QtWidgets.QPushButton(MainWindow)
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.buttonLayout.addWidget(self.pushButton_clear)
        self.pushButton_copy = QtWidgets.QPushButton(MainWindow)
        self.pushButton_copy.setObjectName("pushButton_copy")
        self.buttonLayout.addWidget(self.pushButton_copy)
        self.gridLayout.addLayout(self.buttonLayout, 1, 0, 1, 1)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        self.pushButton.setText(_translate("MainWindow", "Convert"))
        self.pushButton_clear.setText(_translate("MainWindow", "Clear"))
        self.pushButton_copy.setText(_translate("MainWindow", "Copy"))
```

- [ ] **Step 2: 重写 lk_to_kernel.py 为 QWidget 页面**

```python
from PyQt5.QtWidgets import QWidget, QMessageBox
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
        else:
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
```

- [ ] **Step 3: 验证语法**

```bash
cd bsp_tools/bsp_tools && python -c "from lk_to_kernel import LkToKernelPage; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add bsp_tools/bsp_tools/bsp_tools/ui_lk_to_kernel.py bsp_tools/bsp_tools/bsp_tools/lk_to_kernel.py
git commit -m "refactor: convert lk_to_kernel to QWidget tab page, add Clear/Copy

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 转换 kernel_to_lk 为 Tab 页面

**Files:**
- Modify: `bsp_tools/bsp_tools/bsp_tools/ui_kernel_to_lk.py`
- Modify: `bsp_tools/bsp_tools/bsp_tools/kernel_to_lk.py`

**Consumes:** `BaseToolPage` from Task 1
**Produces:** `KernelToLkPage(BaseToolPage, Ui_KernelToLk)` 类

- [ ] **Step 1: 修改 ui_kernel_to_lk.py — 与 Task 3 的 lk_to_kernel 布局相同，仅按钮文字不同**

```python
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_KernelToLk(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(662, 500)
        self.gridLayout = QtWidgets.QGridLayout(MainWindow)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.textEdit = QtWidgets.QTextEdit(MainWindow)
        self.textEdit.setObjectName("textEdit")
        self.horizontalLayout.addWidget(self.textEdit)
        self.textEdit_2 = QtWidgets.QTextEdit(MainWindow)
        self.textEdit_2.setObjectName("textEdit_2")
        self.horizontalLayout.addWidget(self.textEdit_2)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 1)
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.pushButton = QtWidgets.QPushButton(MainWindow)
        self.pushButton.setObjectName("pushButton")
        self.buttonLayout.addWidget(self.pushButton)
        self.pushButton_clear = QtWidgets.QPushButton(MainWindow)
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.buttonLayout.addWidget(self.pushButton_clear)
        self.pushButton_copy = QtWidgets.QPushButton(MainWindow)
        self.pushButton_copy.setObjectName("pushButton_copy")
        self.buttonLayout.addWidget(self.pushButton_copy)
        self.gridLayout.addLayout(self.buttonLayout, 1, 0, 1, 1)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        self.pushButton.setText(_translate("MainWindow", "Convert"))
        self.pushButton_clear.setText(_translate("MainWindow", "Clear"))
        self.pushButton_copy.setText(_translate("MainWindow", "Copy"))
```

- [ ] **Step 2: 重写 kernel_to_lk.py 为 QWidget 页面**

```python
from PyQt5.QtWidgets import QWidget, QMessageBox
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
```

- [ ] **Step 3: 验证语法**

```bash
cd bsp_tools/bsp_tools && python -c "from kernel_to_lk import KernelToLkPage; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add bsp_tools/bsp_tools/bsp_tools/ui_kernel_to_lk.py bsp_tools/bsp_tools/bsp_tools/kernel_to_lk.py
git commit -m "refactor: convert kernel_to_lk to QWidget tab page, add Clear/Copy

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 转换 lk_to_bat 为 Tab 页面

**Files:**
- Modify: `bsp_tools/bsp_tools/bsp_tools/ui_lk_to_bat.py`
- Modify: `bsp_tools/bsp_tools/bsp_tools/lk_to_bat.py`

**Consumes:** `BaseToolPage` from Task 1
**Produces:** `LkToBatPage(BaseToolPage, Ui_LkToBat)` 类

- [ ] **Step 1: 修改 ui_lk_to_bat.py — 与 Task 3 布局相同**

```python
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_LkToBat(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(700, 500)
        self.gridLayout = QtWidgets.QGridLayout(MainWindow)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.textEdit = QtWidgets.QTextEdit(MainWindow)
        self.textEdit.setObjectName("textEdit")
        self.horizontalLayout.addWidget(self.textEdit)
        self.textEdit_2 = QtWidgets.QTextEdit(MainWindow)
        self.textEdit_2.setObjectName("textEdit_2")
        self.horizontalLayout.addWidget(self.textEdit_2)
        self.gridLayout.addLayout(self.horizontalLayout, 0, 0, 1, 1)
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.pushButton = QtWidgets.QPushButton(MainWindow)
        self.pushButton.setObjectName("pushButton")
        self.buttonLayout.addWidget(self.pushButton)
        self.pushButton_clear = QtWidgets.QPushButton(MainWindow)
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.buttonLayout.addWidget(self.pushButton_clear)
        self.pushButton_copy = QtWidgets.QPushButton(MainWindow)
        self.pushButton_copy.setObjectName("pushButton_copy")
        self.buttonLayout.addWidget(self.pushButton_copy)
        self.gridLayout.addLayout(self.buttonLayout, 1, 0, 1, 1)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        self.pushButton.setText(_translate("MainWindow", "Convert"))
        self.pushButton_clear.setText(_translate("MainWindow", "Clear"))
        self.pushButton_copy.setText(_translate("MainWindow", "Copy"))
```

- [ ] **Step 2: 重写 lk_to_bat.py 为 QWidget 页面**

```python
from PyQt5.QtWidgets import QWidget, QMessageBox
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
        else:
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
```

- [ ] **Step 3: 验证语法**

```bash
cd bsp_tools/bsp_tools && python -c "from lk_to_bat import LkToBatPage; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add bsp_tools/bsp_tools/bsp_tools/ui_lk_to_bat.py bsp_tools/bsp_tools/bsp_tools/lk_to_bat.py
git commit -m "refactor: convert lk_to_bat to QWidget tab page, add Clear/Copy

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: 重写 shell_tools UI 布局 + 清理代码

**Files:**
- Modify: `bsp_tools/bsp_tools/bsp_tools/ui_shell_tools.py` — 从绝对定位改为 QGridLayout
- Modify: `bsp_tools/bsp_tools/bsp_tools/shell_tools.py` — 重写为 QWidget 页面，清理死代码

**Consumes:** `BaseToolPage` from Task 1
**Produces:** `ShellToolsPage(BaseToolPage, Ui_ShellTools)` 类

- [ ] **Step 1: 重写 ui_shell_tools.py 为弹性网格布局**

```python
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_ShellTools(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(900, 680)

        # 顶层：主垂直布局
        self.mainLayout = QtWidgets.QVBoxLayout(MainWindow)
        self.mainLayout.setObjectName("mainLayout")

        # ===== 上半部分：2列网格 =====
        self.topGrid = QtWidgets.QGridLayout()
        self.topGrid.setObjectName("topGrid")

        # ---- 左列 ----

        # Command 分组框（左上）
        self.groupBox = QtWidgets.QGroupBox(MainWindow)
        self.groupBox.setObjectName("groupBox")
        cmdLayout = QtWidgets.QGridLayout(self.groupBox)
        cmdLayout.setObjectName("cmdLayout")

        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        cmdLayout.addWidget(self.label_2, 0, 0, 1, 1)
        self.cmdpath = QtWidgets.QLineEdit(self.groupBox)
        self.cmdpath.setObjectName("cmdpath")
        cmdLayout.addWidget(self.cmdpath, 0, 1, 1, 1)

        self.label_3 = QtWidgets.QLabel(self.groupBox)
        self.label_3.setObjectName("label_3")
        cmdLayout.addWidget(self.label_3, 1, 0, 1, 1)
        self.cmds = QtWidgets.QLineEdit(self.groupBox)
        self.cmds.setObjectName("cmds")
        cmdLayout.addWidget(self.cmds, 1, 1, 1, 1)

        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        cmdLayout.addWidget(self.label, 0, 2, 1, 1)
        self.comboBox = QtWidgets.QComboBox(self.groupBox)
        self.comboBox.setObjectName("comboBox")
        cmdLayout.addWidget(self.comboBox, 0, 3, 1, 1)

        self.label_4 = QtWidgets.QLabel(self.groupBox)
        self.label_4.setObjectName("label_4")
        cmdLayout.addWidget(self.label_4, 1, 2, 1, 1)
        self.splitsymbol = QtWidgets.QLineEdit(self.groupBox)
        self.splitsymbol.setObjectName("splitsymbol")
        cmdLayout.addWidget(self.splitsymbol, 1, 3, 1, 1)

        self.send = QtWidgets.QPushButton(self.groupBox)
        self.send.setObjectName("send")
        cmdLayout.addWidget(self.send, 0, 4, 2, 1)

        self.topGrid.addWidget(self.groupBox, 0, 0, 1, 1)

        # ylog 分组框（左下）
        self.groupBox_3 = QtWidgets.QGroupBox(MainWindow)
        self.groupBox_3.setObjectName("groupBox_3")
        ylogLayout = QtWidgets.QGridLayout(self.groupBox_3)
        ylogLayout.setObjectName("ylogLayout")

        self.label_9 = QtWidgets.QLabel(self.groupBox_3)
        self.label_9.setObjectName("label_9")
        ylogLayout.addWidget(self.label_9, 0, 0, 1, 1)
        self.ylogpath = QtWidgets.QLineEdit(self.groupBox_3)
        self.ylogpath.setObjectName("ylogpath")
        ylogLayout.addWidget(self.ylogpath, 0, 1, 1, 1)

        self.label_7 = QtWidgets.QLabel(self.groupBox_3)
        self.label_7.setObjectName("label_7")
        ylogLayout.addWidget(self.label_7, 1, 0, 1, 1)
        self.ylogpath_2 = QtWidgets.QLineEdit(self.groupBox_3)
        self.ylogpath_2.setObjectName("ylogpath_2")
        ylogLayout.addWidget(self.ylogpath_2, 1, 1, 1, 1)

        self.label_8 = QtWidgets.QLabel(self.groupBox_3)
        self.label_8.setObjectName("label_8")
        ylogLayout.addWidget(self.label_8, 1, 2, 1, 1)
        self.ylogpath_3 = QtWidgets.QLineEdit(self.groupBox_3)
        self.ylogpath_3.setObjectName("ylogpath_3")
        ylogLayout.addWidget(self.ylogpath_3, 1, 3, 1, 1)

        self.pushButton_5 = QtWidgets.QPushButton(self.groupBox_3)
        self.pushButton_5.setObjectName("pushButton_5")
        ylogLayout.addWidget(self.pushButton_5, 0, 2, 2, 1)

        self.topGrid.addWidget(self.groupBox_3, 1, 0, 1, 1)

        # ---- 右列 ----

        # adb 分组框（右上）
        self.groupBox_4 = QtWidgets.QGroupBox(MainWindow)
        self.groupBox_4.setObjectName("groupBox_4")
        adbLayout = QtWidgets.QVBoxLayout(self.groupBox_4)
        adbLayout.setObjectName("adbLayout")
        self.pushButton_2 = QtWidgets.QPushButton(self.groupBox_4)
        self.pushButton_2.setObjectName("pushButton_2")
        adbLayout.addWidget(self.pushButton_2)
        self.pushButton_3 = QtWidgets.QPushButton(self.groupBox_4)
        self.pushButton_3.setObjectName("pushButton_3")
        adbLayout.addWidget(self.pushButton_3)
        self.pushButton_4 = QtWidgets.QPushButton(self.groupBox_4)
        self.pushButton_4.setObjectName("pushButton_4")
        adbLayout.addWidget(self.pushButton_4)
        self.pushButton_11 = QtWidgets.QPushButton(self.groupBox_4)
        self.pushButton_11.setObjectName("pushButton_11")
        adbLayout.addWidget(self.pushButton_11)
        self.pushButton_9 = QtWidgets.QPushButton(self.groupBox_4)
        self.pushButton_9.setObjectName("pushButton_9")
        adbLayout.addWidget(self.pushButton_9)
        self.pushButton_6 = QtWidgets.QPushButton(self.groupBox_4)
        self.pushButton_6.setObjectName("pushButton_6")
        adbLayout.addWidget(self.pushButton_6)
        self.pushButton_10 = QtWidgets.QPushButton(self.groupBox_4)
        self.pushButton_10.setObjectName("pushButton_10")
        adbLayout.addWidget(self.pushButton_10)
        self.topGrid.addWidget(self.groupBox_4, 0, 1, 1, 1)

        # fastboot + func 合并列（右下）
        self.rightBottomLayout = QtWidgets.QVBoxLayout()
        self.rightBottomLayout.setObjectName("rightBottomLayout")

        self.groupBox_5 = QtWidgets.QGroupBox(MainWindow)
        self.groupBox_5.setObjectName("groupBox_5")
        fbLayout = QtWidgets.QVBoxLayout(self.groupBox_5)
        fbLayout.setObjectName("fbLayout")
        self.pushButton_7 = QtWidgets.QPushButton(self.groupBox_5)
        self.pushButton_7.setObjectName("pushButton_7")
        fbLayout.addWidget(self.pushButton_7)
        self.pushButton_8 = QtWidgets.QPushButton(self.groupBox_5)
        self.pushButton_8.setObjectName("pushButton_8")
        fbLayout.addWidget(self.pushButton_8)
        self.rightBottomLayout.addWidget(self.groupBox_5)

        self.groupBox_6 = QtWidgets.QGroupBox(MainWindow)
        self.groupBox_6.setObjectName("groupBox_6")
        funcLayout = QtWidgets.QVBoxLayout(self.groupBox_6)
        funcLayout.setObjectName("funcLayout")
        self.pushButton_12 = QtWidgets.QPushButton(self.groupBox_6)
        self.pushButton_12.setObjectName("pushButton_12")
        funcLayout.addWidget(self.pushButton_12)
        self.pushButton_13 = QtWidgets.QPushButton(self.groupBox_6)
        self.pushButton_13.setObjectName("pushButton_13")
        funcLayout.addWidget(self.pushButton_13)
        self.rightBottomLayout.addWidget(self.groupBox_6)

        self.topGrid.addLayout(self.rightBottomLayout, 1, 1, 1, 1)

        # 设置左右列等宽
        self.topGrid.setColumnStretch(0, 1)
        self.topGrid.setColumnStretch(1, 1)

        self.mainLayout.addLayout(self.topGrid)

        # ===== 下半部分：Log 区域 =====
        self.groupBox_2 = QtWidgets.QGroupBox(MainWindow)
        self.groupBox_2.setObjectName("groupBox_2")
        logLayout = QtWidgets.QVBoxLayout(self.groupBox_2)
        logLayout.setObjectName("logLayout")
        self.textBrowser = QtWidgets.QTextBrowser(self.groupBox_2)
        self.textBrowser.setObjectName("textBrowser")
        logLayout.addWidget(self.textBrowser)
        self.mainLayout.addWidget(self.groupBox_2, 1)  # stretch=1 让 Log 区域占剩余高度

        # Log 底部工具栏
        self.logBottomLayout = QtWidgets.QHBoxLayout()
        self.logBottomLayout.setObjectName("logBottomLayout")
        self.logBottomLayout.addStretch()
        self.pushButton_clear_log = QtWidgets.QPushButton(MainWindow)
        self.pushButton_clear_log.setObjectName("pushButton_clear_log")
        self.logBottomLayout.addWidget(self.pushButton_clear_log)
        self.mainLayout.addLayout(self.logBottomLayout)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        self.groupBox.setTitle(_translate("MainWindow", "Command"))
        self.label_2.setText(_translate("MainWindow", "路径"))
        self.label_3.setText(_translate("MainWindow", "命令"))
        self.label.setText(_translate("MainWindow", "方  法"))
        self.label_4.setText(_translate("MainWindow", "分隔符"))
        self.send.setText(_translate("MainWindow", "Send"))
        self.groupBox_3.setTitle(_translate("MainWindow", "ylog"))
        self.label_9.setText(_translate("MainWindow", "ylog保存路径："))
        self.label_7.setText(_translate("MainWindow", "Project:"))
        self.label_8.setText(_translate("MainWindow", "Sub-Name:"))
        self.pushButton_5.setText(_translate("MainWindow", "导出ylog"))
        self.groupBox_4.setTitle(_translate("MainWindow", "adb"))
        self.pushButton_2.setText(_translate("MainWindow", "adb devices"))
        self.pushButton_3.setText(_translate("MainWindow", "adb root"))
        self.pushButton_4.setText(_translate("MainWindow", "adb reboot"))
        self.pushButton_11.setText(_translate("MainWindow", "autodloader"))
        self.pushButton_9.setText(_translate("MainWindow", "apk_unlock"))
        self.pushButton_6.setText(_translate("MainWindow", "lcm_apk_1"))
        self.pushButton_10.setText(_translate("MainWindow", "lcm_apk_2"))
        self.groupBox_5.setTitle(_translate("MainWindow", "fastboot"))
        self.pushButton_7.setText(_translate("MainWindow", "fastboot mode"))
        self.pushButton_8.setText(_translate("MainWindow", "reboot"))
        self.groupBox_2.setTitle(_translate("MainWindow", "Log"))
        self.pushButton_clear_log.setText(_translate("MainWindow", "Clear Log"))
        self.groupBox_6.setTitle(_translate("MainWindow", "func"))
        self.pushButton_12.setText(_translate("MainWindow", "power-key"))
        self.pushButton_13.setText(_translate("MainWindow", "一键投屏"))
```

- [ ] **Step 2: 重写 shell_tools.py 为 QWidget 页面，清理死代码**

```python
import os
import re
import subprocess
import configparser

from PyQt5.QtCore import pyqtSlot, QTimer, QDateTime, QProcess, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (QWidget, QMainWindow, QLabel, QMessageBox,
                             QTextCursor, QFileDialog, QApplication)
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QDesktopServices

from ui_shell_tools import Ui_ShellTools
from base_tool_page import BaseToolPage

# 硬编码路径提取为模块常量
SCRCPY_PATH = r"D:\01_tools\scrcpy-win64-v2.6.1\scrcpy.exe"
APK_1_PATH = r"D:\00_project\lcm_test_apk\Display-Tester_1.apk"
APK_2_PATH = r"D:\00_project\lcm_test_apk\Display-Tester_2.apk"


class ShellToolsPage(BaseToolPage, Ui_ShellTools):
    def __init__(self, parent=None):
        super(ShellToolsPage, self).__init__(parent)
        self.setupUi(self)

        self.paths = None
        self.splitsymbol = None
        self.historycmd = 'proc/cmdline'
        self.echo = 'echo'

        self._setup_textbrowser_style()
        self._setup_combo()
        self._setup_connections()
        self.load_config()

    def _setup_textbrowser_style(self):
        font = QFont()
        font.setFamily("Consolas")
        font.setPointSize(11)
        font.setStyleHint(QFont.Monospace)
        self.textBrowser.setFont(font)
        self.textBrowser.setStyleSheet("""
            QTextBrowser {
                background-color: #f5f5f5;
                color: #333333;
                padding: 8px;
                border: 1px solid #cccccc;
                font-family: Consolas, monospace;
                line-height: 1.4;
            }
            a {
                color: #1a73e8;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
                color: #1558b0;
            }
        """)

    def _setup_combo(self):
        self.comboBox.addItem('echo')
        self.comboBox.addItem('cat')
        self.comboBox.addItem('cd')
        self.comboBox.addItem('ls')
        self.comboBox.addItem('自定义')
        self.comboBox.setCurrentText('cat')
        self.comboBox.currentIndexChanged.connect(self.activated)
        self.cmdpath.setText(self.historycmd)

    def _setup_connections(self):
        self.pushButton_2.clicked.connect(self.adbdevices_fun)
        self.pushButton_3.clicked.connect(self.adbroot_fun)
        self.pushButton_4.clicked.connect(self.adbreboot_fun)
        self.pushButton_5.clicked.connect(self.ylog_fun)
        self.pushButton_6.clicked.connect(self.lcmapkinstall_1)
        self.pushButton_7.clicked.connect(self.adbrebootbootloader)
        self.pushButton_8.clicked.connect(self.fastbootreboot)
        self.pushButton_9.clicked.connect(self.lcmapkinstallunlock)
        self.pushButton_10.clicked.connect(self.lcmapkinstall_2)
        self.pushButton_11.clicked.connect(self.adbrebootautodloader_fun)
        self.pushButton_12.clicked.connect(self.powerkey_fun)
        self.pushButton_13.clicked.connect(self.Screen_simulator)
        self.ylogpath.setPlaceholderText(r"默认路径为D:\Desktop\allylog")
        self.pushButton_clear_log.clicked.connect(self.on_clear_log)

    # === adb 命令 ===

    def append_text(self, msg):
        self.textBrowser.insertPlainText(msg)
        self.textBrowser.moveCursor(QTextCursor.End)

    def run_command_line(self, command_line='NO_COMMAND_GIVEN'):
        self.textBrowser.clear()
        P = subprocess.Popen(command_line, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, shell=True)
        out = P.communicate()[0]
        out = out.decode()
        out = re.sub(r'\r+\n', r'\n', out)
        result = P.wait()
        self.append_to_log_file(command_line, out)
        return result, out

    def append_to_log_file(self, command_line, output):
        log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'adb_commands.log')
        log_message = f"Command: {command_line}\nOutput: {output}\n{'-' * 40}\n"
        with open(log_file_path, 'a') as log_file:
            log_file.write(log_message)

    def run_adb_command(self, command, success_message):
        self.textBrowser.clear()
        result, out = self.run_command_line(command)
        self.append_text(f"执行命令: {command}\n")
        self.append_text(f"结果:\n{out}\n")
        self.append_text(f"{success_message}\n")

    def adbdevices_fun(self):
        command = 'adb devices'
        success_message = "设备列表：\n" + self.run_command_line(command)[1]
        self.run_adb_command(command, success_message)

    def adbroot_fun(self):
        self.run_adb_command('adb root', "设备已进入 root 模式")

    def adbreboot_fun(self):
        self.run_adb_command('adb reboot', "设备重启成功")

    def lcmapkinstallunlock(self):
        self.run_adb_command(
            'adb shell setprop persist.sys.packageinstall.disabled false',
            "lcmapkinstallunlock 解锁成功")

    def lcmapkinstall_1(self):
        self.run_adb_command(f'adb install {APK_1_PATH}', "lcmapkinstall_1 安装成功")

    def lcmapkinstall_2(self):
        self.run_adb_command(f'adb install {APK_2_PATH}', "lcmapkinstall_2 安装成功")

    def adbrebootbootloader(self):
        self.run_adb_command('adb reboot bootloader', "设备已进入 bootloader 模式")

    def fastbootreboot(self):
        self.run_adb_command('fastboot reboot', "设备重启成功")

    def adbrebootautodloader_fun(self):
        self.run_adb_command('adb reboot autodloader', "设备已进入 Download 模式")

    def powerkey_fun(self):
        self.run_adb_command('adb shell input keyevent 26', "电源键按下")

    def Screen_simulator(self):
        self.adbdevices_fun()
        self.process = QProcess(self)
        self.process.start(SCRCPY_PATH)

    # === 配置持久化 ===

    def _get_config_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    def load_config(self):
        config = configparser.ConfigParser()
        try:
            config.read(self._get_config_path())
            self.ylogpath.setText(config.get('DEFAULT', 'base_path', fallback=''))
            self.ylogpath_2.setText(config.get('DEFAULT', 'project', fallback=''))
            self.ylogpath_3.setText(config.get('DEFAULT', 'sub_name', fallback=''))
        except Exception as e:
            print(f"加载配置失败: {e}")

    def save_config(self):
        config = configparser.ConfigParser()
        config['DEFAULT'] = {
            'base_path': self.ylogpath.text().strip(),
            'project': self.ylogpath_2.text().strip(),
            'sub_name': self.ylogpath_3.text().strip()
        }
        with open(self._get_config_path(), 'w') as configfile:
            config.write(configfile)

    def ylog_fun(self):
        self.save_config()
        base_path = self.ylogpath.text().strip() or r"D:\Desktop\allylog"
        project = self.ylogpath_2.text().strip()
        sub_name = self.ylogpath_3.text().strip()

        if not all([project, sub_name]):
            QMessageBox.warning(self, "参数缺失", "必须填写Project和Sub-Name")
            return

        full_path = os.path.normpath(os.path.join(base_path, project, sub_name))

        try:
            os.makedirs(full_path, exist_ok=True)
            adb_cmd = f"adb pull /data/ylog/ap {full_path}"
            self.run_adb_command(adb_cmd, "ylog抓取成功")
            file_list = "\n".join(os.listdir(full_path)[:5])
            self.textBrowser.setOpenExternalLinks(False)
            uri_path = QUrl.fromLocalFile(full_path)
            html = (
                f"<span style='color:green'>✓</span> ylog抓取成功！<br/>"
                f"<b>存储路径：</b><a href='{uri_path.toString()}' style='color:blue;' title='点击打开文件夹'>"
                f"{full_path}</a><br/>"
                f"<b>文件列表：</b><br/>{file_list}"
            )
            self.textBrowser.setHtml(html)
            try:
                self.textBrowser.anchorClicked.disconnect()
            except TypeError:
                pass
            self.textBrowser.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))
        except Exception as e:
            QMessageBox.critical(self, "操作失败", str(e))

    # === 自定义命令 ===

    @pyqtSlot()
    def on_send_clicked(self):
        self.textBrowser.clear()
        self.cmdss = self.cmds.text()
        self.paths = self.cmdpath.text()
        self.echo = self.comboBox.currentText()
        if self.echo == 'echo':
            commandline = f'adb shell "{self.echo} {self.cmdss} > {self.paths}"'
        else:
            commandline = f'adb shell "{self.echo} {self.paths}"'
        result, out = self.run_command_line(commandline)
        self.append_text(f"执行命令: {commandline}\n")
        self.append_text(f"结果:\n{out}\n")

    def activated(self, index):
        self.echo = self.comboBox.currentText()

    def on_clear_log(self):
        self.textBrowser.clear()
```

- [ ] **Step 3: 验证语法**

```bash
cd bsp_tools/bsp_tools && python -c "from shell_tools import ShellToolsPage; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add bsp_tools/bsp_tools/bsp_tools/ui_shell_tools.py bsp_tools/bsp_tools/bsp_tools/shell_tools.py
git commit -m "refactor: rewrite shell_tools with grid layout, clean up dead code

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 重写 mainwindow.py 为单窗口 QTabWidget

**Files:**
- Modify: `bsp_tools/bsp_tools/bsp_tools/mainwindow.py`
- Modify: `bsp_tools/bsp_tools/bsp_tools/ui_mainwindow.py` — 适配新主窗口

**Consumes:** All 5 page classes from Tasks 2-6
**Produces:** `MainWindow(QMainWindow)` 单窗口应用

- [ ] **Step 1: 修改 ui_mainwindow.py 简化 UI**

去掉旧的 CommandLinkButton 导航，改为只保留主框架结构：

```python
# -*- coding: utf-8 -*-

from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_DisplayTools(object):
    def setupUi(self, DisplayTools):
        DisplayTools.setObjectName("DisplayTools")
        DisplayTools.resize(950, 720)
        self.centralwidget = QtWidgets.QWidget(DisplayTools)
        self.centralwidget.setObjectName("centralwidget")
        self.mainLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.mainLayout.setObjectName("mainLayout")

        # 标题
        self.label = QtWidgets.QLabel(self.centralwidget)
        font = QtGui.QFont()
        font.setPointSize(20)
        font.setBold(True)
        self.label.setFont(font)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setObjectName("label")
        self.mainLayout.addWidget(self.label)

        # TabWidget（核心导航）
        self.tabWidget = QtWidgets.QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName("tabWidget")
        self.mainLayout.addWidget(self.tabWidget)

        DisplayTools.setCentralWidget(self.centralwidget)

        self.menubar = QtWidgets.QMenuBar(DisplayTools)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 950, 21))
        self.menubar.setObjectName("menubar")
        self.menu = QtWidgets.QMenu(self.menubar)
        self.menu.setObjectName("menu")
        DisplayTools.setMenuBar(self.menubar)

        self.statusbar = QtWidgets.QStatusBar(DisplayTools)
        self.statusbar.setObjectName("statusbar")
        DisplayTools.setStatusBar(self.statusbar)

        self.action_2 = QtWidgets.QAction(DisplayTools)
        self.action_2.setObjectName("action_2")
        self.menu.addAction(self.action_2)
        self.menubar.addAction(self.menu.menuAction())

        self.retranslateUi(DisplayTools)
        QtCore.QMetaObject.connectSlotsByName(DisplayTools)

    def retranslateUi(self, DisplayTools):
        _translate = QtCore.QCoreApplication.translate
        DisplayTools.setWindowTitle(_translate("DisplayTools", "DisplayTools"))
        self.label.setText(_translate("DisplayTools", "Display-Tool"))
        self.menu.setTitle(_translate("DisplayTools", "菜单"))
        self.action_2.setText(_translate("DisplayTools", "关于"))
```

- [ ] **Step 2: 重写 mainwindow.py**

```python
import sys

from PyQt5.QtCore import QTimer, QDateTime
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QMessageBox
from PyQt5.QtGui import QIcon

from ui_mainwindow import Ui_DisplayTools
from initcode_builder import InitcodeBuilderPage
from lk_to_kernel import LkToKernelPage
from kernel_to_lk import KernelToLkPage
from lk_to_bat import LkToBatPage
from shell_tools import ShellToolsPage


class MainWindow(QMainWindow, Ui_DisplayTools):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)

        self.setWindowIcon(QIcon('icon_img/classification.png'))
        self.setWindowTitle("DisplayTools v2.1.0")

        # 状态栏：时钟 + 标签
        self.lab = QLabel("AIBIN", self)
        self.statusbar.addPermanentWidget(self.lab)
        self.timer = QTimer()
        self.timer.timeout.connect(self.showTimeCurrent)
        self.timer.start()

        # 关于菜单
        self.action_2.triggered.connect(self.show_about)

        # 初始化 Tab 页面
        self._init_tabs()

    def _init_tabs(self):
        self.initcode_page = InitcodeBuilderPage()
        self.lk_to_kernel_page = LkToKernelPage()
        self.kernel_to_lk_page = KernelToLkPage()
        self.lk_to_bat_page = LkToBatPage()
        self.shell_tools_page = ShellToolsPage()

        self.tabWidget.addTab(self.initcode_page, "01 Initcode Builder")
        self.tabWidget.addTab(self.lk_to_kernel_page, "02 LK → Kernel")
        self.tabWidget.addTab(self.kernel_to_lk_page, "03 Kernel → LK")
        self.tabWidget.addTab(self.lk_to_bat_page, "04 LK → BAT")
        self.tabWidget.addTab(self.shell_tools_page, "05 Shell Tools")

    def showTimeCurrent(self):
        d = QDateTime.currentDateTime()
        text = d.toString("yyyy-MM-dd HH:mm:ss")
        self.statusbar.showMessage(text, 0)

    def show_about(self):
        about_msg = QMessageBox(self)
        about_msg.setWindowTitle("about")
        about_msg.setText(
            "该工具旨在减少BSP-LCM手动转化展锐平台initcode的工作\n"
            "版本：v2.1.0\n"
            "作者：AIBIN")
        about_msg.setIcon(QMessageBox.Information)
        about_msg.setStandardButtons(QMessageBox.Ok)
        about_msg.exec_()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
```

- [ ] **Step 3: 运行应用验证**

```bash
cd bsp_tools/bsp_tools && python mainwindow.py &
```
手动验证：5 个 Tab 均可切换，各工具功能正常，Clear/Copy 按钮可用。

- [ ] **Step 4: 提交**

```bash
git add bsp_tools/bsp_tools/bsp_tools/mainwindow.py bsp_tools/bsp_tools/bsp_tools/ui_mainwindow.py
git commit -m "refactor: switch to single-window QTabWidget navigation

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 最终集成测试与清理

**Files:**
- 无新文件

**Consumes:** 所有 Task 1-7 的输出

- [ ] **Step 1: 运行完整语法检查**

```bash
cd bsp_tools/bsp_tools && python -c "
from base_tool_page import BaseToolPage
from initcode_builder import InitcodeBuilderPage
from lk_to_kernel import LkToKernelPage
from kernel_to_lk import KernelToLkPage
from lk_to_bat import LkToBatPage
from shell_tools import ShellToolsPage
from mainwindow import MainWindow
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 2: 启动 GUI 烟雾测试**

```bash
cd bsp_tools/bsp_tools && timeout 5 python -c "
from PyQt5.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
from mainwindow import MainWindow
w = MainWindow()
w.show()
# 验证 Tab count
assert w.tabWidget.count() == 5, f'Expected 5 tabs, got {w.tabWidget.count()}'
print('GUI smoke test PASSED')
app.quit()
" 2>&1 || true
```

- [ ] **Step 3: 清理旧的中间文件**

```bash
cd bsp_tools/bsp_tools && rm -rf build/ dist/ __pycache__/
```
手动确认：这些目录会在重新打包时重新生成。

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore: cleanup build artifacts and verify integration

Co-Authored-By: Claude <noreply@anthropic.com>"
```
