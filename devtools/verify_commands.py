"""真实执行校验：把命令表里的命令实际跑一遍。

没有连接设备时，正确的表现是 adb 报 "no devices/emulators found"；
如果报 "'xxx' is not recognized as an internal or external command"，
说明命令漏到了 Windows 的 cmd.exe（就是用户遇到的那个 bug）。

只跑只读查询命令，写节点/重启类的会跳过（避免真机上误操作）。
"""

import os
import re
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "bsp_tools"))

from command_runner import device_cmd   # noqa: E402

# 只读、可安全执行的命令表。
# 注意：这里引用的常量必须是真的还在的——模块精简时删过 INPUT_QUERIES /
# PANEL_QUERIES，而本脚本只在 run_checks.bat device 时才跑，容易长期没人发现
# （真出过一次 AttributeError）。加常量进来前先确认它还在。
import tools_device                      # noqa: E402
import tools_display                     # noqa: E402
import tools_sitepack                    # noqa: E402
import tools_system                      # noqa: E402

# 背光节点：路径跟平台有关，这几条验证的是"按顺序试"的回退链能不能读到值
BACKLIGHT_TABLE = [
    ("背光 brightness", tools_display.BRIGHTNESS_READ),
    ("背光 max_brightness", tools_display.MAX_BRIGHTNESS_READ),
    ("背光 actual_brightness", tools_display.ACTUAL_BRIGHTNESS_READ),
]

TABLES = [
    ("设备", tools_device.QUERIES),
    ("系统", tools_system.SYSTEM_QUERIES),
    ("显示", BACKLIGHT_TABLE),
    # 现场包抓取项是 5 元组 (key, label, 文件名, 命令, 超时)
    ("现场包", [(label, command)
                for _key, label, _name, command, _timeout in tools_sitepack.PACK_ITEMS]),
]

# 跳过带写入/重启语义的（没有真机也会执行到设备侧，保守起见跳过）
SKIP_WORDS = ("reboot", "recovery", "bootloader", " > ", "setprop", "am ", "pm ")


def run(command, timeout=20):
    try:
        proc = subprocess.run(command, shell=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout)
        return proc.returncode, proc.stdout.decode(errors="replace").strip()
    except subprocess.TimeoutExpired:
        return -1, "(超时)"


def main():
    bad = []
    total = 0
    for group, table in TABLES:
        for label, command in table:
            if any(word in command for word in SKIP_WORDS):
                print(f"  skip  [{group}] {label}（写入类，跳过）")
                continue
            resolved = device_cmd(command)
            code, output = run(resolved)
            total += 1

            not_recognized = ("is not recognized" in output
                              or "系统找不到" in output
                              or "operable program" in output)
            if not_recognized:
                bad.append((group, label, resolved, output))
                print(f"  FAIL  [{group}] {label}")
                print(f"        命令: {resolved}")
                print(f"        输出: {output[:120]}")
            else:
                first_line = output.splitlines()[0] if output else "(无输出)"
                print(f"  ok    [{group}] {label:10} → {resolved[:58]}")
                print(f"        返回: {first_line[:90]}")

    print()
    print("=" * 60)
    if bad:
        print(f"{len(bad)}/{total} 条命令漏到了 Windows（必须修）：")
        for group, label, command, output in bad:
            print(f"  [{group}] {label}: {command}")
        return 1
    print(f"全部 {total} 条命令都正确指向设备（无「不是内部或外部命令」错误）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
