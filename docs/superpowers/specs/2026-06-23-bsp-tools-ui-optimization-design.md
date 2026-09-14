# BSP Tools UI/布局/功能优化设计

日期: 2026-06-23
版本: v1.0

## 目标

全面优化 DisplayTools (bsp_tools) 的 UI 布局、代码结构和功能细节，提升用户体验和可维护性。

## 架构变更

### 从多窗口 → 单窗口 Tab 切换

```
DisplayTools (QMainWindow: ~900x650)
├── 菜单栏: [关于]
├── QTabWidget (核心导航)
│   ├── Tab 0: "Initcode Builder"
│   ├── Tab 1: "LK → Kernel"
│   ├── Tab 2: "Kernel → LK"
│   ├── Tab 3: "LK → BAT"
│   └── Tab 4: "Shell Tools"
├── 状态栏: [时钟] [AIBIN 标签]
└── 公共基类 BaseToolPage — 提供共享方法
```

### 代码结构

```
mainwindow.py          — 唯一入口，MainWindow + QTabWidget 组装
base_tool_page.py      — 新建，QWidget 子类，提供共享工具方法

initcode_builder.py    — InitcodeBuilderPage(QWidget, Ui_InitcodeBuilder)
lk_to_kernel.py        — LkToKernelPage(QWidget, Ui_LkToKernel)
kernel_to_lk.py        — KernelToLkPage(QWidget, Ui_KernelToLk)
lk_to_bat.py           — LkToBatPage(QWidget, Ui_LkToBat)
shell_tools.py         — ShellToolsPage(QWidget, Ui_ShellTools)
```

关键变化：
- 页面不再继承 QMainWindow，改为 QWidget
- 页面不再持有独立 statusbar，状态栏统一由 MainWindow 管理
- `return_to_main` 信号和所有 `return_to_main_window_X` 方法全部删除
- shell_tools 的 config.ini 路径改为基于脚本位置的绝对路径

---

## 各 Tab 页面布局

### Tab 0 — Initcode Builder

```
┌─────────────────────────────────────────────────────┐
│ [左侧 60%]              │ [右侧 40%]                │
│ ┌─────────────────┐    │ ┌──────────────────────┐  │
│ │  输入框          │    │ │ 格式选择              │  │
│ │  (QTextEdit)    │    │ │ ○ WriteAddr          │  │
│ │                 │    │ │ ○ Write(Command)     │  │
│ └─────────────────┘    │ │ ○ Rxx                │  │
│ ┌─────────────────┐    │ │ ○ GEN_WR [____]     │  │
│ │  输出框          │    │ └──────────────────────┘  │
│ │  (QTextEdit)    │    │ ┌──────────────────────┐  │
│ │  只读           │    │ │ [Build] [Clear] [Copy]│  │
│ └─────────────────┘    │ └──────────────────────┘  │
│                        │ 格式提示标签               │
└─────────────────────────────────────────────────────┘
```

改动：
- 格式切换不再弹 QMessageBox，改为输出框上方的 QLabel 提示文字
- 新增 Clear 和 Copy 按钮
- 使用 QGridLayout 重新布局

### Tab 1/2/3 — LK↔Kernel、LK→BAT

```
┌─────────────────────────────────────────────────────┐
│ ┌─────────────────┐  ┌─────────────────────────────┐│
│ │  输入框          │  │  输出框 (只读)              ││
│ │  (QTextEdit)    │  │  (QTextEdit)               ││
│ └─────────────────┘  └─────────────────────────────┘│
│              [Convert] [Clear] [Copy]               │
└─────────────────────────────────────────────────────┘
```

改动：
- 统一三个转换工具的布局
- 新增 Clear 和 Copy 按钮
- 确认按钮统一命名（Build → Convert）

### Tab 4 — Shell Tools（弹性网格布局）

```
┌─────────────────────────────────────────────────────┐
│ ┌─ Command ────────────┐ ┌─ adb ───────────────────┐│
│ │ Path: [__________]    │ │ [adb devices] [adb root] ││
│ │ Cmd:  [__________]    │ │ [adb reboot] [autodloader]││
│ │ Split:[___] Method:[v]│ │ [apk_unlock] [lcm_apk_1]  ││
│ │ [Send]               │ │ [lcm_apk_2]              ││
│ └──────────────────────┘ └─────────────────────────┘│
│ ┌─ ylog ───────────────┐ ┌─ fastboot ──────────────┐│
│ │ Path:[________]       │ │ [fastboot mode] [reboot] ││
│ │ Proj:[___] Sub:[___] │ └─────────────────────────┘│
│ │ [导出ylog]            │ ┌─ func ──────────────────┐│
│ └──────────────────────┘ │ [power-key] [一键投屏]    ││
│                          └─────────────────────────┘│
│ ┌─ Log ────────────────────────────────────────────┐│
│ │  (QTextBrowser - 占窗口高度 60%)                  ││
│ │                                                   ││
│ └───────────────────────────────────────────────────┘│
│                                    [Clear Log]       │
└─────────────────────────────────────────────────────┘
```

改动：
- 从绝对定位改为 QGridLayout + QVBoxLayout 弹性布局
- 四个功能分组等宽排列（Command / adb | ylog / fastboot+func）
- Log 区域始终占大部分空间
- 窗口大小改为 ~900x680

---

## 功能增强

### 所有转换工具页面
- **Clear 按钮**：一键清空输入和输出框
- **Copy 按钮**：将输出框内容复制到剪贴板
- **Convert 按钮**：统一命名，替代原来的 Build / lk_to_kernel 等

### Initcode Builder
- 格式切换时不再弹出 QMessageBox，改为小标签显示当前格式提示

### Shell Tools
- 清理死代码：移除 openpyxl 导入、on_startconvert_clicked、on_openfile_clicked 等 Excel 相关方法
- 清理未使用的导入（threading）
- config.ini 路径使用基于文件的绝对路径，避免工作目录变化导致读不到
- 硬编码路径（scrcpy、APK）提取为模块顶部常量

### 全局
- 修复 `SceondWindow` 拼写错误 → `InitcodeBuilderPage`
- 统一所有页面的代码风格

---

## 实现要点

### BaseToolPage 基类

```python
class BaseToolPage(QWidget):
    """所有工具页面的公共基类"""
    
    def clear_textedit(self, *edits):
        """清空指定的 QTextEdit"""
        
    def copy_to_clipboard(self, edit):
        """将 QTextEdit 内容复制到剪贴板"""
        
    def show_status_tip(self, label, text, duration=3000):
        """在指定 label 显示临时提示"""
```

### mainwindow.py 简化

- MainWindow 创建 QTabWidget，addTab 注册 5 个页面
- 状态栏时钟和标签保留在 MainWindow 级别
- 所有 `return_to_main_window_X` 方法和子窗口持有变量删除

### 兼容性

- 保留所有 .ui 文件不变（仅 shell_tools.ui 可能需要微调）
- PyInstaller .spec 文件更新入口
- 图标资源路径保持不变

---

## 不做的事

- 不重写业务逻辑（转换算法、adb 命令均正确）
- 不添加批量文件处理
- 不添加撤销/重做
- 不改 density 独立工具
- 不添加新的配置文件格式
