"""说明框（帮助 / 更新日志 / 关于 / 崩溃日志）尺寸与滚动自查。

用法：python devtools/check_info_dialog.py

守的约定：
- 对话框尺寸**固定**，内容再长也不撑大窗口（以前 QMessageBox 会跟着长，
  超出屏幕的部分直接看不到）
- 正文超出可视区域时必须可滚动（滚轮/方向键能翻）
- 尺寸不能超过屏幕可用区域
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtWidgets import QApplication  # noqa: E402

import theme  # noqa: E402
from info_dialog import InfoDialog, fit_to_screen  # noqa: E402
from mainwindow import MainWindow  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print("  {}  {}  {}".format("PASS" if ok else "FAIL", label, detail))
    if not ok:
        FAILED.append(label)


app = QApplication([])
app.setFont(theme.app_font())
app.setStyleSheet(theme.build_stylesheet())

LONG_TEXT = "\n".join("第 {} 行：这是一条比较长的说明文字，用来把对话框撑满。".format(i)
                      for i in range(1, 201))

print("[1] 固定尺寸")
dialog = InfoDialog("测试", LONG_TEXT)
check("最小尺寸 = 最大尺寸（真的固定）",
      dialog.minimumSize() == dialog.maximumSize(),
      "{} vs {}".format(dialog.minimumSize(), dialog.maximumSize()))
wanted = (dialog.width(), dialog.height())
dialog.resize(1200, 900)                 # 外部强行改也改不动
check("外部 resize 无效", (dialog.width(), dialog.height()) == wanted,
      "{} -> {}".format(wanted, (dialog.width(), dialog.height())))

print("\n[2] 内容可滚动")
dialog.show()
for _ in range(4):
    app.processEvents()
bar = dialog.view.verticalScrollBar()
check("长文本触发了纵向滚动条", dialog.is_scrollable(),
      "max={} min={}".format(bar.maximum(), bar.minimum()))
bar.setValue(bar.maximum())
check("能滚到底部", bar.value() == bar.maximum(), str(bar.value()))
dialog.scroll_to_bottom()

short = InfoDialog("短", "只有一行")
short.show()
for _ in range(4):
    app.processEvents()
check("短文本不出现多余滚动条", not short.is_scrollable())

print("\n[3] 尺寸不超过屏幕")
screen = app.primaryScreen().availableGeometry()
for width, height in ((820, 620), (4000, 3000)):
    got = fit_to_screen(width, height)
    check("请求 {}x{} 收成 {}x{} 且在屏内".format(width, height, *got),
          got[0] <= screen.width() and got[1] <= screen.height(),
          "屏幕 {}x{}".format(screen.width(), screen.height()))

print("\n[4] 真实入口：帮助 / 更新日志 / 关于")
window = MainWindow()
window.resize(1360, 840)
window.show()
for _ in range(6):
    app.processEvents()

for name, opener in (("更新日志", window.show_changelog),
                     ("使用说明", window.show_help),
                     ("关于", window.show_about)):
    # 不 exec（会阻塞），直接建对话框量尺寸
    created = {}

    def fake_exec(self, _name=name, _store=created):
        _store["dialog"] = self
        return 0
    original = InfoDialog.exec_
    InfoDialog.exec_ = fake_exec
    try:
        opener()
    finally:
        InfoDialog.exec_ = original
    dialog = created.get("dialog")
    if dialog is None:
        check("{} 弹出了说明框".format(name), False, "没拿到对话框")
        continue
    check("{} 固定尺寸 {}x{}".format(name, dialog.width(), dialog.height()),
          dialog.minimumSize() == dialog.maximumSize())
    if name == "更新日志":
        check("更新日志内容超出可视区（需要滚动）", dialog.is_scrollable(),
              "正文 {} 字".format(len(dialog.view.toPlainText())))
        check("更新日志从顶部开始显示",
              dialog.view.verticalScrollBar().value() == 0)
    dialog.close()

print("\n" + "=" * 46)
if FAILED:
    print("失败 {} 项：{}".format(len(FAILED), "、".join(FAILED)))
    sys.exit(1)
print("说明框尺寸与滚动全部通过")
