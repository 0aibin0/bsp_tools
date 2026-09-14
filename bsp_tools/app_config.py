"""全局配置与运行目录（单一收口点）。

以前只有 Shell Tools 自己读写 config.ini，窗口尺寸、上次打开的页面、
adb 路径这些都没地方存。这里统一收口，仍然是同一个 config.ini、
同一套 `[DEFAULT]` 键，旧配置原样可读，不破坏已有文件。

约定：
- 配置文件、崩溃日志都放在 exe（或源码包）同目录，方便打包后携带；
- 读失败一律回退默认值——配置坏了不能让程序起不来；
- 写失败不抛异常，只在返回值里体现（磁盘满/只读目录时不该崩）。
"""

import configparser
import os
import sys

CONFIG_NAME = "config.ini"


def data_dir():
    """exe / 源码所在目录：config.ini、crash.log、favorites.json 都放这里。

    注意 frozen 时要用 sys.executable 的目录，而不是 sys._MEIPASS——
    后者是 onefile 的临时解包目录，退出即删，写进去等于没存。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(data_dir(), CONFIG_NAME)


def crash_log_path():
    return os.path.join(data_dir(), "crash.log")


class AppConfig:
    """config.ini 的薄封装。

    值都用字符串存，取的时候按需转换；`%` 不做插值（路径里可能有）。
    """

    def __init__(self, path=None):
        self.path = path or config_path()
        self._parser = configparser.ConfigParser(interpolation=None)
        self.load()

    # ---------- 读写 ----------

    def load(self):
        self._parser = configparser.ConfigParser(interpolation=None)
        try:
            if os.path.isfile(self.path):
                self._parser.read(self.path, encoding="utf-8")
        except Exception:                                  # noqa: BLE001
            # 编码坏了、文件被占用，都当空配置处理，别拦着启动
            self._parser = configparser.ConfigParser(interpolation=None)

    def get(self, key, fallback=""):
        try:
            return self._parser.get("DEFAULT", key, fallback=fallback)
        except Exception:                                  # noqa: BLE001
            return fallback

    def get_int(self, key, fallback=0):
        try:
            return int(str(self.get(key, fallback)).strip())
        except (TypeError, ValueError):
            return fallback

    def get_bool(self, key, fallback=False):
        raw = str(self.get(key, "")).strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
        if raw in ("0", "false", "no", "off"):
            return False
        return fallback

    def set(self, key, value):
        """只改内存，需要落盘时再调 save()。"""
        if "DEFAULT" not in self._parser:
            self._parser["DEFAULT"] = {}
        self._parser["DEFAULT"][key] = "" if value is None else str(value)

    def update(self, **values):
        for key, value in values.items():
            self.set(key, value)
        return self.save()

    def save(self):
        """写盘；失败返回 False（例如 exe 放在只读目录）。"""
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            # 先写临时文件再替换，避免写一半断电留下半截配置
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                self._parser.write(handle)
            os.replace(tmp, self.path)
            return True
        except Exception:                                  # noqa: BLE001
            return False


_instance = None


def config():
    """进程内单例。"""
    global _instance
    if _instance is None:
        _instance = AppConfig()
    return _instance


def reload_config():
    """测试用：丢掉缓存重新读盘。"""
    global _instance
    _instance = AppConfig()
    return _instance
