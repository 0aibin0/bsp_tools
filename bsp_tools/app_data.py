"""本机数据文件（**只有一个 JSON**）。

以前 exe 同目录散着三个文件：

- `config.ini`           —— 设置（窗口尺寸、上次页面、adb 路径、输入框记忆…）
- `favorites.json`       —— 命令收藏（Ctrl+K 面板与命令收藏页共用）
- `path_bookmarks.json`  —— 设备路径书签

现在统一进 `DisplayTools.json` 一个文件：

```json
{
  "version": 1,
  "config":         { "window_width": "1360", ... },
  "commands":       [ {"group": "常用", "name": "列出设备", "command": "adb devices"} ],
  "path_bookmarks": [ "/sdcard/" ]
}
```

设计要点：
- 三个「段」各自独立读写，坏掉一段不牵连另外两段（读失败就用默认值）；
- 首次运行如果发现老文件，**自动迁移**：先把老内容并进新文件，再把老文件改名成
  `xxx.migrated`（不删数据，随时能翻回去看）；
- 写盘先写 `.tmp` 再 `os.replace`，写一半断电不会留下半截文件；
- 写失败返回 False，由调用方决定要不要提示（exe 放在只读目录时不该崩）。
"""

import configparser
import json
import os
import sys

#: 唯一的本机数据文件
DATA_NAME = "DisplayTools.json"
#: 老文件 → 迁移后改名成这个后缀
MIGRATED_SUFFIX = ".migrated"
#: 老文件名字（迁移用）
LEGACY_CONFIG = "config.ini"
LEGACY_FAVORITES = "favorites.json"
LEGACY_BOOKMARKS = "path_bookmarks.json"

#: 段名
SECTION_CONFIG = "config"
SECTION_COMMANDS = "commands"
SECTION_BOOKMARKS = "path_bookmarks"


def data_dir():
    """exe / 源码所在目录：DisplayTools.json、crash.log 都放这里。

    注意 frozen 时要用 sys.executable 的目录，而不是 sys._MEIPASS——
    后者是 onefile 的临时解包目录，退出即删，写进去等于没存。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_path():
    """唯一数据文件的完整路径。"""
    return os.path.join(data_dir(), DATA_NAME)


def legacy_paths(base=None):
    """三个老文件的路径（用于迁移与提示）。"""
    base = base or data_dir()
    return {
        SECTION_CONFIG: os.path.join(base, LEGACY_CONFIG),
        SECTION_COMMANDS: os.path.join(base, LEGACY_FAVORITES),
        SECTION_BOOKMARKS: os.path.join(base, LEGACY_BOOKMARKS),
    }


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:                                      # noqa: BLE001
        return None


def _read_ini(path):
    """读老 config.ini 的 [DEFAULT] 段；读不动返回 {}。"""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except Exception:                                      # noqa: BLE001
        return {}
    result = {}
    try:
        for key, value in parser.defaults().items():
            result[str(key)] = str(value)
    except Exception:                                      # noqa: BLE001
        return {}
    return result


class AppData:
    """单个 JSON 文件的读写。"""

    def __init__(self, path=None, migrate=True):
        self.path = path or data_path()
        self.migrated_from = []
        # 注意：commands / path_bookmarks 两个段**先不建键**——"段不存在"和
        # "段存在但是空的"是两件事：前者用内置默认清单（首次运行），后者就是空
        # （用户把命令/书签全删了，不能再把默认塞回来）。见 get_section()。
        self._data = {"version": 1, SECTION_CONFIG: {}}
        self.load(migrate=migrate)

    # ---------- 读 ----------

    def load(self, migrate=True):
        raw = _read_json(self.path) if os.path.isfile(self.path) else None
        if isinstance(raw, dict):
            config = raw.get(SECTION_CONFIG)
            self._data = {
                "version": raw.get("version", 1),
                SECTION_CONFIG: config if isinstance(config, dict) else {},
            }
            for name in (SECTION_COMMANDS, SECTION_BOOKMARKS):
                if isinstance(raw.get(name), list):
                    self._data[name] = raw[name]
            return self._data
        # 没有新文件（或读坏了）：看看有没有老文件要迁移
        if migrate:
            self._migrate()
        return self._data

    def _migrate(self):
        """把 config.ini / favorites.json / path_bookmarks.json 并进新文件。"""
        base = os.path.dirname(os.path.abspath(self.path)) or data_dir()
        legacy = legacy_paths(base)
        found = {name: path for name, path in legacy.items() if os.path.isfile(path)}
        if not found:
            return

        if SECTION_CONFIG in found:
            parsed = _read_ini(found[SECTION_CONFIG])
            if parsed:
                self._data[SECTION_CONFIG] = parsed
        for name in (SECTION_COMMANDS, SECTION_BOOKMARKS):
            if name not in found:
                continue          # 没有老文件 → 段保持不存在 → 用内置默认
            data = _read_json(found[name])
            if isinstance(data, list):
                self._data[name] = data

        if self.save():
            # 迁移成功才动老文件：改名成 xxx.migrated，不删（用户随时能翻回去）
            for name, path in found.items():
                try:
                    os.replace(path, path + MIGRATED_SUFFIX)
                    self.migrated_from.append(os.path.basename(path) + MIGRATED_SUFFIX)
                except Exception:                          # noqa: BLE001
                    pass

    # ---------- 写 ----------

    def save(self):
        try:
            directory = os.path.dirname(os.path.abspath(self.path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return True
        except Exception:                                  # noqa: BLE001
            return False

    # ---------- 段访问 ----------

    def get_section(self, name, default=None):
        value = self._data.get(name)
        if value is None:
            return default
        return value

    def set_section(self, name, value, save=True):
        self._data[name] = value
        return self.save() if save else True


_instance = None


def data():
    """进程内单例：所有模块共用同一份内存数据，避免互相覆盖。"""
    global _instance
    if _instance is None:
        _instance = AppData()
    return _instance


def reload_data(path=None):
    """测试用：丢掉缓存重新读盘。"""
    global _instance
    _instance = AppData(path)
    return _instance
