"""开发自查脚本：离屏渲染各页面并截图，用于确认视觉效果。

用法（仓库根目录）：
    .venv\\Scripts\\python.exe devtools\\capture_ui.py [输出目录]

注意：Qt 的 offscreen 平台默认找不到字体，必须通过 QT_QPA_FONTDIR 指向
系统字体目录，否则截图里所有文字都不会被绘制。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "bsp_tools")

# 必须在导入/初始化 Qt 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

sys.path.insert(0, SRC)

from PyQt5.QtWidgets import QApplication, QLabel          # noqa: E402
from PyQt5.QtCore import Qt, QTimer                       # noqa: E402

import theme                                              # noqa: E402
from mainwindow import MainWindow                         # noqa: E402


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "devtools", "shots")
    os.makedirs(out_dir, exist_ok=True)

    # 第二个参数可选，格式 1360x840；不传就用窗口默认尺寸（截图要能代表用户首屏）
    width, height = 1360, 840
    if len(sys.argv) > 2 and "x" in sys.argv[2]:
        width, height = (int(v) for v in sys.argv[2].split("x", 1))

    app = QApplication(sys.argv)
    # 第三个参数可选：light / dark / system，用来看深色下的效果
    theme_mode = sys.argv[3] if len(sys.argv) > 3 else "light"
    theme.set_mode(theme_mode)
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())

    window = MainWindow()
    window.resize(width, height)
    window.show()
    app.processEvents()

    def settle(rounds=6):
        for _ in range(rounds):
            app.processEvents()

    shots = []

    def grab(name):
        settle()
        path = os.path.join(out_dir, f"{name}.png")
        window.grab().save(path)
        shots.append(name)
        print("saved", name, flush=True)

    for key in ("tools", "shell", "initcode", "lk2kernel", "kernel2lk", "lk2bat"):
        window.nav.select(key)
        grab(f"page_{key}")

    import tools_page
    tools = window.pages["tools"]
    window.nav.select("tools")
    for key, _label, _icon, _cls in tools_page.SECTIONS:
        tools.show_section(key)
        grab(f"tools_{key}")

    # 关闭前停掉所有后台任务，避免线程在退出时被销毁导致崩溃
    tools.stop_background()
    settle(3)
    for page in window.pages.values():
        hook = getattr(page, 'stop_background', None)
        if callable(hook):
            hook()
    settle(3)
    window.close()
    settle(2)

    print(f"\n共 {len(shots)} 张截图 -> {out_dir}", flush=True)


if __name__ == "__main__":
    main()
