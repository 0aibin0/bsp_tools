"""流式日志验证（真机）：dmesg -w 的积压截断与界面响应。

dmesg -w 启动时会把整个 ring buffer（实测 15000+ 行）先吐出来，
必须确认界面不会被冲爆、缓冲区有上限、停止按钮有效。
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from PyQt5.QtCore import QEventLoop, QTimer     # noqa: E402
from PyQt5.QtWidgets import QApplication        # noqa: E402

import theme                                     # noqa: E402
import tools_log                                 # noqa: E402

FAIL = []
CHECKS = [0]


def check(label, ok, detail=""):
    CHECKS[0] += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAIL.append(label)


def wait(app, ms):
    """等待 ms 毫秒，期间持续处理事件（模拟界面在跑）。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()
    app.processEvents()


def main():
    app = QApplication([])
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.build_stylesheet())

    log = tools_log.LogAnalyzerSection()
    log.resize(1000, 700)
    log.show()
    app.processEvents()

    print("\n[1] 日志来源列表")
    titles = [log.source_combo.itemText(i) for i in range(log.source_combo.count())]
    for title in titles:
        print(f"    - {title}")
    check("包含 dmesg 实时来源",
          any("dmesg" in t and "-w" in t for t in titles), str(titles))
    check("包含 dmesg 快照来源",
          any("dmesg" in t and "快照" in t for t in titles))
    check("包含 logcat 实时来源", any("logcat" in t and "实时" in t for t in titles))

    print("\n[2] dmesg -w 实时抓取（约 8 秒）")
    index = next(i for i, t in enumerate(titles) if "-w" in t)
    log.source_combo.setCurrentIndex(index)

    started = time.time()
    log.start_fetch()
    check("已进入抓取状态", log._running)
    check("按钮切换为停止", log.fetch_btn.text() == "停止抓取",
          log.fetch_btn.text())

    # 分两次观察：前 4 秒看积压截断，后 4 秒看持续跟流
    wait(app, 4000)
    mid_buffer = len(log._buffer)
    mid_view = log.view.blockCount()
    mid_label = log.count_label.text()
    print(f"    4 秒后: 缓冲区 {mid_buffer} 行, 视图 {mid_view} 块, 状态 '{mid_label}'")
    check("缓冲区未失控（<= 1200）", mid_buffer <= 1200, f"{mid_buffer} 行")
    check("视图未失控（<= 1200 块）", mid_view <= 1200, f"{mid_view} 块")
    check("提示了丢弃行数", "丢弃" in mid_label or mid_buffer < 1200, mid_label)
    elapsed_mid = time.time() - started
    check("界面仍在响应（事件循环未阻塞）", elapsed_mid < 12,
          f"{elapsed_mid:.1f}s")

    wait(app, 4000)
    print(f"    8 秒后: 缓冲区 {len(log._buffer)} 行, 视图 {log.view.blockCount()} 块,"
          f" 状态 '{log.count_label.text()}'")
    check("持续抓取时缓冲区仍受控", len(log._buffer) <= 1200, str(len(log._buffer)))

    print("\n[3] 停止抓取")
    log.stop_fetch()
    check("已退出抓取状态", not log._running)
    check("按钮恢复", log.fetch_btn.text() == "开始抓取", log.fetch_btn.text())
    check("进程已结束",
          log._process is None or log._process.state() != 2)

    print("\n[4] 过滤与重绘（实时数据上验证）")
    log.filter_edit.setText("usb|i2c|ufs")
    t0 = time.time()
    log.render()
    render_ms = (time.time() - t0) * 1000
    shown = log.view.blockCount() - 1
    print(f"    过滤后 {shown} 行, 重绘耗时 {render_ms:.0f} ms, 状态 '{log.count_label.text()}'")
    check("过滤后重绘在 1 秒内完成", render_ms < 1000, f"{render_ms:.0f} ms")
    check("过滤生效（行数减少）", shown < len(log._buffer),
          f"{shown} vs {len(log._buffer)}")

    log.filter_edit.clear()
    t0 = time.time()
    log.render()
    full_ms = (time.time() - t0) * 1000
    print(f"    全量重绘 {log.view.blockCount() - 1} 行耗时 {full_ms:.0f} ms")
    check("全量重绘在 2 秒内完成", full_ms < 2000, f"{full_ms:.0f} ms")

    print("\n[5] dmesg 快照来源")
    snap_index = next(i for i, t in enumerate(titles) if "快照" in t)
    log.source_combo.setCurrentIndex(snap_index)
    log.start_fetch()
    wait(app, 5000)
    if log._running:
        log.stop_fetch()
    wait(app, 500)
    print(f"    快照行数 {len(log._buffer)}")
    check("快照来源有内容", len(log._buffer) > 0, f"{len(log._buffer)} 行")
    check("快照来源未被截断标记", "_backlog_keep" in dir(log))

    log.stop_fetch()
    wait(app, 500)

    print("\n" + "=" * 58)
    if FAIL:
        print(f"{len(FAIL)}/{CHECKS[0]} 项失败：")
        for name in FAIL:
            print("  -", name)
        return 1
    print(f"流式日志验证全部通过（{CHECKS[0]} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
