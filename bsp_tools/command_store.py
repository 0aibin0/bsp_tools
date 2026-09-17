"""命令收藏的单一数据源（命令面板 / 命令收藏页共用）。

以前这里是两份数据：
- Ctrl+K 命令面板读的是 mainwindow 里硬编码的 SHELL_QUICK_COMMANDS（改不了、存不下）
- 常用工具 · 命令收藏页读的是 favorites.json（能增删改）

同一个命令在两处名字不一样、面板里收藏的命令搜不到，改完还要去另一处再加一遍。
现在两处都走这个 store：命令存在本机唯一的数据文件 `DisplayTools.json` 里
（和设置、路径书签同一个文件，见 app_data.py），页面上改完，命令面板立刻能搜到；
面板里新建的命令也直接落盘。

增删改一律**立即写文件**：删一条就少一条，加一条就多一条，重启后不会变回去。

约定：
- 文件里没有 commands 段 → 用内置默认清单（首次运行）；
- 文件里是空数组 → 就是空（用户全删了，不能把默认塞回来）；
- 写失败不抛异常，save() 返回 False，由页面提示用户。
"""

import app_data

FAVORITES_NAME = app_data.DATA_NAME

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
    """兼容旧名字：现在指向本机唯一的数据文件（DisplayTools.json）。"""
    return app_data.data_path()


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
    """命令收藏的读写与增删改。

    数据存在本机唯一的数据文件 `DisplayTools.json` 的 `commands` 段里
    （和设置、路径书签同一个文件，见 app_data.py）。增删改都会立刻落盘——
    页面上删一条，文件里就少一条；加一条，文件里就多一条。
    """

    def __init__(self, path=None, data=None):
        """path: 兼容旧调用（指到某个 json）；data: 直接注入数据层（测试用）。"""
        # 顺手容错：把数据层当第一个参数传进来也认（AppData 有 get_section）
        if data is None and hasattr(path, "get_section"):
            data, path = path, None
        self._own_data = None
        if data is not None:
            self._data = data
        elif path is not None:
            self._own_data = app_data.AppData(path, migrate=False)
            self._data = self._own_data
        else:
            self._data = app_data.data()
        self.path = getattr(self._data, "path", path or favorites_path())
        self.load()

    # ---------- 读写 ----------

    def load(self):
        """从数据文件读 commands 段。

        只有「文件里没有这一段」（首次运行 / 段被破坏）才用内置默认清单；
        用户把命令全删光时文件里是空数组，那就是空——不能再把默认清单塞回来，
        不然删掉的命令下次启动又冒出来了。
        """
        section = self._data.get_section(app_data.SECTION_COMMANDS, None)
        if section is None:
            data = [dict(d) for d in DEFAULT_COMMANDS]
        elif isinstance(section, list):
            data = section
        else:
            data = [dict(d) for d in DEFAULT_COMMANDS]
        self.items = normalize(data)
        return self.items

    def save(self):
        """把 commands 段写进数据文件；失败返回 False，调用方自己决定要不要提示。"""
        return self._data.set_section(app_data.SECTION_COMMANDS, self.items)

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

    # ---------- 增删改（都会立刻落盘） ----------

    def add(self, name, command, group="常用"):
        """新增一条并写文件；命令已存在时返回 (False, 已有下标)。"""
        existing = self.find_by_command(command)
        if existing is not None:
            return False, existing
        self.items.append({
            "group": (group or "常用").strip() or "常用",
            "name": (name or "").strip() or command.strip(),
            "command": command.strip()})
        saved = self.save()
        if saved is False:
            # 写失败：内存里加了但没落盘，把下标交回 None，页面会提示用户
            return True, None
        return True, len(self.items) - 1

    def update(self, index, name, command, group="常用"):
        if not (0 <= index < len(self.items)):
            return False
        self.items[index] = {
            "group": (group or "常用").strip() or "常用",
            "name": (name or "").strip() or command.strip(),
            "command": command.strip()}
        return self.save()

    def remove(self, index):
        """删除一条并写文件；返回是否成功（False = 下标越界或写盘失败）。"""
        if not (0 <= index < len(self.items)):
            return False
        self.items.pop(index)
        return self.save()

    def reset(self):
        self.items = [dict(d) for d in DEFAULT_COMMANDS]
        return self.save()


_instance = None


def store():
    """进程内单例：命令面板与命令收藏页共用同一份数据。"""
    global _instance
    if _instance is None:
        _instance = CommandStore()
    return _instance


def reload_store(path=None, data=None):
    """测试用：丢掉缓存重新读盘（可指定别的文件或直接注入数据层）。"""
    global _instance
    _instance = CommandStore(path, data=data)
    return _instance
