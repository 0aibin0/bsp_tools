"""adb / fastboot 可执行文件定位。

原来全项目写死 `adb`，靠 PATH 找——exe 发给没装 platform-tools 的同事就
直接全废，而且报错是 Windows 的 `'adb' is not recognized`，很难自查。

规则（按优先级）：
1. 设置里指定的 `adb_path` / `fastboot_path`（可以是可执行文件，也可以是
   它所在的目录，例如 `D:\\01_tools\\platform-tools`）；
2. `toolchain_dir` 目录下的同名文件；
3. PATH 里的 adb / fastboot；
4. 兜底返回裸名字，让系统去报错（错误信息里至少能看到找的是什么）。

两种拼法要分清：
- `shell_exe()` 给 cmd 命令行用（`subprocess(..., shell=True)`）：**只在用户
  显式配置时才换全路径**，没配置就保持裸 `adb`——命令串是要显示给用户看的，
  写成 `C:\\...\\adb.exe shell dumpsys` 又长又乱，而且 platform-tools 挪个
  位置就全错；
- `exe_path()` 给 QProcess 用（不走 shell，是真实程序路径），优先给全路径。
"""

import os
import shutil
import sys

import app_config

EXE_SUFFIX = ".exe" if os.name == "nt" else ""


def _clean(value):
    """去掉用户粘贴路径时带上的引号与多余空白。"""
    text = (value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]
    return os.path.expandvars(os.path.expanduser(text.strip()))


def _resolve(setting, directory, name):
    """把「文件路径」或「目录」统一解析成可执行文件路径。"""
    candidate = _clean(setting)
    if candidate:
        if os.path.isdir(candidate):
            inside = os.path.join(candidate, name + EXE_SUFFIX)
            if os.path.isfile(inside):
                return inside
        elif os.path.isfile(candidate):
            return candidate

    folder = _clean(directory)
    if folder:
        inside = os.path.join(folder, name + EXE_SUFFIX)
        if os.path.isfile(inside):
            return inside
    return None


def configured(name):
    """用户在设置里指定且确实存在的路径；没配置或路径无效返回 None。"""
    cfg = app_config.config()
    return _resolve(cfg.get("{}_path".format(name)), cfg.get("toolchain_dir"), name)


def exe_path(name):
    """真实可执行文件路径（QProcess / 存在性检查用）。"""
    found = configured(name)
    if found:
        return found
    return shutil.which(name) or name


def shell_exe(name):
    """拼进 cmd 命令串的写法：没配置就保持裸名字，配置了才用带引号的全路径。"""
    found = configured(name)
    if not found:
        return name
    if " " in found:
        return '"{}"'.format(found)
    return found


def adb():
    return exe_path("adb")


def fastboot():
    return exe_path("fastboot")


def adb_shell():
    """adb 命令行前缀（含 -s 设备选择）。"""
    base = shell_exe("adb")
    args = serial_args()
    return " ".join([base] + args) if args else base


def fastboot_shell():
    base = shell_exe("fastboot")
    args = serial_args()
    return " ".join([base] + args) if args else base


# ================= 多设备选择 =================
#
# 工位上常同时插着几台板子，不加 -s 时 adb 会随机挑一台（多设备时报
# "more than one device"），调试结果对不上号。选定后所有命令统一带
# `-s <序列号>`。

_selected_serial = ""


def set_serial(serial):
    """设置当前操作的设备序列号；空字符串 = 用 adb 默认（唯一设备）。"""
    global _selected_serial
    _selected_serial = (serial or "").strip()
    return _selected_serial


def selected_serial():
    return _selected_serial


def serial_args():
    """要插在 adb 后面的 -s 参数。"""
    return ["-s", _selected_serial] if _selected_serial else []


def list_devices(timeout=6):
    """返回 [(序列号, 状态)]，失败返回空列表。"""
    try:
        import subprocess
        out = subprocess.run(
            "{} devices".format(shell_exe("adb")), shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout).stdout.decode(errors="replace")
    except Exception:                                      # noqa: BLE001
        return []
    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append((parts[0], parts[1]))
    return devices


def online_devices(timeout=6):
    return [serial for serial, state in list_devices(timeout) if state == "device"]


def adb_program_args(args):
    """QProcess 用：返回 (程序, 参数表)，自动带上 -s。"""
    return exe_path("adb"), serial_args() + list(args)


def available(name):
    """该工具是否真的能找到（用于启动自检）。"""
    if configured(name):
        return True
    return bool(shutil.which(name))


def describe(name):
    """给状态栏/设置界面看的一行说明。"""
    found = configured(name)
    if found:
        return "{}：{}（手动指定）".format(name, found)
    found = shutil.which(name)
    if found:
        return "{}：{}（PATH）".format(name, found)
    return "{}：未找到，请在「设置」里指定 platform-tools 目录".format(name)


# platform-tools 常见的安装位置，供「自动检测」按顺序试
_COMMON_DIRS = [
    r"D:\01_tools\platform-tools",
    r"C:\platform-tools",
    r"D:\platform-tools",
    r"C:\Android\platform-tools",
    r"D:\Android\sdk\platform-tools",
    os.path.join(os.path.expanduser("~"), "AppData", "Local", "Android", "Sdk",
                 "platform-tools"),
]


def detect_platform_tools():
    """自动找一个含 adb 的目录；找不到返回 None。"""
    for folder in _COMMON_DIRS:
        if os.path.isfile(os.path.join(folder, "adb" + EXE_SUFFIX)):
            return folder
    found = shutil.which("adb")
    if found:
        return os.path.dirname(found)
    return None


def detect_report():
    """启动自检用：两个工具的可用状态。"""
    return {name: available(name) for name in ("adb", "fastboot")}
