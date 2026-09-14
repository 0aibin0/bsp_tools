"""运行时杂项：单实例守卫、崩溃日志、上次异常提示。

Qt 没有现成的单实例方案。不用 QSharedMemory 是因为它在"进程被强杀"时会
留下没释放的共享内存，下次启动会误判成"已有实例在跑"；QLocalServer 的
残骸可以用 removeServer 清掉，而且能顺手把已有窗口激活到前台。
"""

import os
import sys
import traceback
from datetime import datetime

from PyQt5.QtCore import QObject
from PyQt5.QtNetwork import QLocalSocket, QLocalServer

import app_config

# 带用户名：同一台机器上多用户各自跑一份互不干扰
SERVER_NAME = "DisplayTools-single-instance-{}".format(
    os.environ.get("USERNAME") or os.environ.get("USER") or "default")

_ACTIVATE = b"activate"


class SingleInstance(QObject):
    """第二个实例启动时，请求第一个实例把窗口激活，然后自己退出。"""

    def __init__(self, on_activate=None, parent=None):
        super().__init__(parent)
        self._on_activate = on_activate
        self._server = None

    def acquire(self):
        """True = 本进程是第一个实例；False = 已有实例在跑（已请求它激活）。"""
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if socket.waitForConnected(300):
            socket.write(_ACTIVATE)
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            return False

        # 连不上：可能真没实例，也可能是上次崩溃留下的僵尸 server
        QLocalServer.removeServer(SERVER_NAME)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        return bool(self._server.listen(SERVER_NAME))

    def _on_connection(self):
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            try:
                conn.waitForReadyRead(200)
                conn.readAll()
            except Exception:                              # noqa: BLE001
                pass
            conn.disconnectFromServer()
        if callable(self._on_activate):
            self._on_activate()


# ================= 崩溃日志 =================


def write_crash_log(text):
    """把异常写到 exe 同目录的 crash.log（追加，保留最近几次）。"""
    path = app_config.crash_log_path()
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n===== {} · {} =====\n".format(stamp, _context()))
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        _trim(path)
        return True
    except Exception:                                      # noqa: BLE001
        return False


def _context():
    from PyQt5.QtCore import QT_VERSION_STR
    return "{} {} / PyQt {} / Python {}".format(
        "exe" if getattr(sys, "frozen", False) else "source",
        _version(), QT_VERSION_STR, sys.version.split()[0])


def _version():
    try:
        import theme
        return theme.APP_VERSION
    except Exception:                                      # noqa: BLE001
        return "?"


def _trim(path, keep_bytes=64 * 1024):
    """日志别无限长，只留最后 64KB。"""
    try:
        if os.path.getsize(path) <= keep_bytes:
            return
        with open(path, "rb") as handle:
            handle.seek(-keep_bytes, os.SEEK_END)
            tail = handle.read()
        with open(path, "wb") as handle:
            handle.write(b"[... earlier crash log trimmed ...]\n")
            handle.write(tail)
    except Exception:                                      # noqa: BLE001
        pass


def install_excepthook(on_crash=None):
    """接管未捕获异常。

    PyQt5 在槽函数里抛异常时会先打印（走 sys.excepthook）再 abort，
    所以这里能抓到槽里的异常——GUI 崩溃不再是"什么都没留下"。
    """

    def hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        write_crash_log(text)
        if callable(on_crash):
            try:
                on_crash(text)
            except Exception:                              # noqa: BLE001
                pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
    return hook


def take_crash_notice(max_lines=6):
    """上次运行崩过就返回一段摘要（只提示一次，之后归档成 .old）。"""
    path = app_config.crash_log_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read().strip()
    except Exception:                                      # noqa: BLE001
        return None
    if not content:
        return None
    try:
        os.replace(path, path + ".old")
    except Exception:                                      # noqa: BLE001
        pass
    lines = [ln for ln in content.splitlines() if ln.strip()]
    return "\n".join(lines[-max_lines:])
