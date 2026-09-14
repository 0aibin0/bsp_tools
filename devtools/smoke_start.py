"""真实平台启动冒烟测试：确认 GUI 能正常创建、显示并干净退出。

用法（仓库根目录）：
    .venv\\Scripts\\python.exe devtools\\smoke_start.py
退出码 0 表示启动、显示、关闭全程无异常。
"""

import os
import sys
import traceback

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

STATUS = {"ok": False, "error": ""}


def main():
    try:
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication

        import theme
        from mainwindow import MainWindow

        app = QApplication(sys.argv)
        app.setFont(theme.app_font())
        app.setStyleSheet(theme.build_stylesheet())

        window = MainWindow()
        window.show()

        def report():
            print(f"visible      = {window.isVisible()}")
            print(f"size         = {window.width()}x{window.height()}")
            print(f"current page = {window.stack.currentWidget().objectName()}")
            print(f"pages        = {len(window.pages)}")
            print(f"device       = {window.deviceLabel.text()}")
            STATUS["ok"] = window.isVisible() and len(window.pages) == 6

        def shutdown():
            window.pages["tools"].stop_background()
            window.close()
            app.quit()

        QTimer.singleShot(2500, report)
        QTimer.singleShot(4000, shutdown)
        app.exec_()
        print("event loop exited cleanly")
    except Exception:
        STATUS["error"] = traceback.format_exc()
        print("EXCEPTION:\n" + STATUS["error"])
        return 1

    if STATUS["ok"]:
        print("SMOKE TEST OK")
        return 0
    print("SMOKE TEST FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
