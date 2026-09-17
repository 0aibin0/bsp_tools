"""全局配置（单一收口点）。

设置、命令收藏、路径书签都存进 exe / 源码同目录的**一个** `DisplayTools.json`
（见 app_data.py）。本模块只管其中的 `config` 段，对外 API 没变：
`config().get/get_int/get_bool/set/update/save`，原来读写 config.ini 的地方
一行都不用改。

约定：
- 读失败一律回退默认值——配置坏了不能让程序起不来；
- 写失败不抛异常，只在返回值里体现（磁盘满/只读目录时不该崩）；
- 老的 config.ini 首次运行会自动迁移进新文件并改名成 config.ini.migrated。
"""

import os

import app_data

#: 本机数据文件名（老的 config.ini 已合并进来）
CONFIG_NAME = app_data.DATA_NAME


def data_dir():
    """exe / 源码所在目录：DisplayTools.json、crash.log 都放这里。"""
    return app_data.data_dir()


def config_path():
    """本机数据文件路径（设置 / 命令收藏 / 路径书签都在一个文件里）。"""
    return app_data.data_path()


def crash_log_path():
    return os.path.join(data_dir(), "crash.log")


class AppConfig:
    """`DisplayTools.json` 里 config 段的薄封装。

    值都用字符串存（和原来的 config.ini 一致），取的时候按需转换。
    """

    def __init__(self, path=None):
        self.path = path or config_path()

    # ---------- 读写 ----------

    def _section(self):
        section = app_data.data().get_section(app_data.SECTION_CONFIG)
        return section if isinstance(section, dict) else {}

    def load(self):
        """重新读盘（数据层是单例，这里让它再读一次文件）。"""
        app_data.data().load()
        return self._section()

    def get(self, key, fallback=""):
        try:
            value = self._section().get(key)
        except Exception:                                  # noqa: BLE001
            return fallback
        if value is None:
            return fallback
        return str(value)

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
        section = dict(self._section())
        section[str(key)] = "" if value is None else str(value)
        app_data.data().set_section(app_data.SECTION_CONFIG, section, save=False)
        return True

    def update(self, **values):
        for key, value in values.items():
            self.set(key, value)
        return self.save()

    def save(self):
        """写盘；失败返回 False（例如 exe 放在只读目录）。"""
        return app_data.data().save()

    def keys(self):
        return sorted(self._section().keys())


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
    app_data.reload_data()
    _instance = AppConfig()
    return _instance
