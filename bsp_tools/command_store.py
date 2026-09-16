"""命令收藏的单一数据源（命令面板 / 命令收藏页共用）。

以前这里是两份数据：
- Ctrl+K 命令面板读的是 mainwindow 里硬编码的 SHELL_QUICK_COMMANDS（改不了、存不下）
- 常用工具 · 命令收藏页读的是 favorites.json（能增删改）

同一个命令在两处名字不一样、面板里收藏的命令搜不到，改完还要去另一处再加一遍。
现在两处都走这个 store：命令存在 exe 同目录的 favorites.json 里，页面上改完，
命令面板立刻能搜到；面板里新建的命令也直接落盘。

约定：
- 文件不存在或读坏了 → 用内置默认清单（不覆盖用户文件，只在首次写入时生成）；
- 写失败不抛异常（exe 放在只读目录时不该崩），只在返回值里体现；
- 进程内单例，页面和面板拿到的永远是同一份，改完各自 refresh。
"""

import json
import os

from app_config import data_dir

FAVORITES_NAME = "favorites.json"

# 内置默认清单：常用工具 · 命令收藏页打开就是这些。
# 重新挂载按侧边栏的叫法统一成 remount。
DEFAULT_COMMANDS = [
    {"group": "常用", "name": "列出设备", "command": "adb devices"},
    {"group": "常用", "name": "获取 root", "command": "adb root"},
    {"group": "常用", "name": "remount", "command": "adb remount"},
    {"group": "常用", "name": "重启设备", "command": "adb reboot"},
    {"group": "常用", "name": "进入 bootloader", "command": "adb reboot bootloader"},
    {"group": "常用", "name": "挂载 debugfs", "command": "adb shell mount -t debugfs none /d"},
    {"group": "调试", "name": "dmesg 内核日志", "command": "adb shell dmesg | tail -200"},
    {"group": "调试", "name": "logcat 错误", "command": "adb logcat -d *:E"},
    {"group": "调试", "name": "I2C 设备列表", "command": "adb shell ls /sys/bus/i2c/devices/"},
    {"group": "调试", "name": "GPIO 状态", "command": "adb shell cat /d/gpio"},
    {"group": "调试", "name": "printk 等级", "command": "adb shell cat /proc/sys/kernel/printk"},
    {"group": "调试", "name": "输入设备列表", "command": "adb shell cat /proc/bus/input/devices"},
    {"group": "显示", "name": "屏幕分辨率", "command": "adb shell wm size"},
    {"group": "显示", "name": "屏幕密度", "command": "adb shell wm density"},
    {"group": "显示", "name": "显示子系统", "command": "adb shell dumpsys display"},
    {"group": "显示", "name": "当前背光", "command": "adb shell settings get system screen_brightness"},
    {"group": "显示", "name": "DCS 回读", "command": "adb shell cat /sys/class/display/dsi0/dcs_read"},
    {"group": "系统", "name": "启动参数", "command": "adb shell cat /proc/cmdline"},
    {"group": "系统", "name": "CPU 温度", "command": "adb shell cat /sys/class/thermal/thermal_zone0/temp"},
    {"group": "系统", "name": "电池状态", "command": "adb shell dumpsys battery"},
    {"group": "系统", "name": "内存占用", "command": "adb shell cat /proc/meminfo | head -3"},
    {"group": "系统", "name": "系统属性", "command": "adb shell getprop | grep ro.product"},
]


def favorites_path():
    """收藏文件路径：和 config.ini 一样放在 exe / 源码同目录，方便打包携带。"""
    return os.path.join(data_dir(), FAVORITES_NAME)


def normalize(items):
    """只留下结构完整、命令非空的条目，并按 分组+名称 排序稳定化。"""
    result = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        command = str(item.get("command", "")).strip()
        if not command:
            continue
        name = str(item.get("name", "")).strip() or command
        group = str(item.get("group", "")).strip() or "常用"
        result.append({"group": group, "name": name, "command": command})
    return result


class CommandStore:
    """favorites.json 的读写与增删改。"""

    def __init__(self, path=None):
        self.path = path or favorites_path()
        self.items = []
        self.load()

    # ---------- 读写 ----------

    def load(self):
        data = None
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
        except Exception:                                  # noqa: BLE001
            data = None
        if not isinstance(data, list) or not data:
            data = [dict(d) for d in DEFAULT_COMMANDS]
        self.items = normalize(data)
        return self.items

    def save(self):
        """写盘；失败返回 False，调用方自己决定要不要提示。"""
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self.items, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return True
        except Exception:                                  # noqa: BLE001
            return False

    # ---------- 查询 ----------

    def groups(self):
        result = []
        for item in self.items:
            group = item.get("group", "常用")
            if group not in result:
                result.append(group)
        return result

    def search(self, keyword="", group=""):
        """按关键字（名称或命令）和分组过滤，返回 (原始下标, 条目) 列表。"""
        keyword = (keyword or "").strip().lower()
        result = []
        for index, item in enumerate(self.items):
            if group and group not in ("全部分组", "") and item.get("group") != group:
                continue
            if keyword and keyword not in item["name"].lower() \
                    and keyword not in item["command"].lower():
                continue
            result.append((index, item))
        return result

    def find_by_command(self, command):
        command = (command or "").strip()
        for index, item in enumerate(self.items):
            if item["command"] == command:
                return index
        return None

    # ---------- 增删改 ----------

    def add(self, name, command, group="常用"):
        """新增一条；命令已存在时返回 (False, 已有下标)。"""
        existing = self.find_by_command(command)
        if existing is not None:
            return False, existing
        self.items.append({
            "group": (group or "常用").strip() or "常用",
            "name": (name or "").strip() or command.strip(),
            "command": command.strip()})
        self.save()
        return True, len(self.items) - 1

    def update(self, index, name, command, group="常用"):
        if not (0 <= index < len(self.items)):
            return False
        self.items[index] = {
            "group": (group or "常用").strip() or "常用",
            "name": (name or "").strip() or command.strip(),
            "command": command.strip()}
        self.save()
        return True

    def remove(self, index):
        if not (0 <= index < len(self.items)):
            return False
        self.items.pop(index)
        self.save()
        return True

    def reset(self):
        self.items = [dict(d) for d in DEFAULT_COMMANDS]
        self.save()


_instance = None


def store():
    """进程内单例：命令面板与命令收藏页共用同一份数据。"""
    global _instance
    if _instance is None:
        _instance = CommandStore()
    return _instance


def reload_store(path=None):
    """测试用：丢掉缓存重新读盘。"""
    global _instance
    _instance = CommandStore(path)
    return _instance
